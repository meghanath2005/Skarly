from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import QualityReport

MIN_AUDIO_FILE_BYTES = 4 * 1024
MIN_SAMPLE_RATE_HZ = 16_000
MAX_REASONABLE_CHANNELS = 8
MIN_REASONABLE_DURATION_SECONDS = 3.0
SILENT_PEAK_DBFS = -60.0
VERY_QUIET_PEAK_DBFS = -35.0
CLIPPING_ABS_THRESHOLD = 0.98
CLIPPING_FRACTION_THRESHOLD = 0.001


@dataclass
class DecodedAudio:
    samples: Any
    sample_rate: int
    channels: int
    duration_seconds: float
    format: str | None


def validate_audio_file(
    path: str | Path,
    expected_duration_seconds: int | None = None,
    generator_name: str | None = None,
    fallback_used: bool = False,
) -> QualityReport:
    audio_path = Path(path)
    warnings: list[str] = []
    validation_errors: list[str] = []
    report = QualityReport(
        audio_exists=False,
        generator_name=generator_name,
        fallback_used=fallback_used,
        warnings=warnings,
        validation_errors=validation_errors,
        passed=False,
    )

    if not audio_path.exists():
        _fail(report, "Generated audio file does not exist.")
        return report

    report.audio_exists = True
    file_size = audio_path.stat().st_size
    report.file_size_bytes = file_size
    if file_size < MIN_AUDIO_FILE_BYTES:
        _fail(report, "Generated audio file is too small and may be invalid.")

    decoded, decode_errors = _decode_audio(audio_path)
    if decoded is None:
        _fail(report, "Generated audio could not be decoded.")
        if decode_errors:
            report.warnings.extend(_dedupe(f"Decode attempt failed: {error}" for error in decode_errors))
        report.passed = False
        return report

    report.sample_rate = decoded.sample_rate
    report.channels = decoded.channels
    report.duration_seconds = round(decoded.duration_seconds, 3)
    report.format = decoded.format

    _validate_format(audio_path, decoded.format, report)
    _validate_duration(decoded.duration_seconds, expected_duration_seconds, report)
    _validate_sample_rate(decoded.sample_rate, report)
    _validate_channels(decoded.channels, report)
    _validate_levels(decoded.samples, report)

    report.warnings = _dedupe(report.warnings)
    report.validation_errors = _dedupe(report.validation_errors)
    report.passed = (
        report.audio_exists
        and report.file_size_bytes is not None
        and report.file_size_bytes >= MIN_AUDIO_FILE_BYTES
        and not report.validation_errors
    )
    return report


def _decode_audio(path: Path) -> tuple[DecodedAudio | None, list[str]]:
    errors: list[str] = []
    for decoder in (_decode_with_soundfile, _decode_with_librosa, _decode_with_pydub):
        try:
            decoded = decoder(path)
        except Exception as exc:
            errors.append(f"{decoder.__name__}: {exc}")
            continue
        if decoded is not None:
            return decoded, errors
    return None, errors


def _decode_with_soundfile(path: Path) -> DecodedAudio | None:
    import soundfile as sf

    info = sf.info(str(path))
    samples, sample_rate = sf.read(str(path), always_2d=True, dtype="float32")
    channels = int(samples.shape[1]) if len(samples.shape) > 1 else 1
    duration = float(info.duration or (len(samples) / sample_rate if sample_rate else 0.0))
    return DecodedAudio(samples=samples, sample_rate=int(sample_rate), channels=channels, duration_seconds=duration, format=info.format)


def _decode_with_librosa(path: Path) -> DecodedAudio | None:
    import librosa
    import numpy as np

    samples, sample_rate = librosa.load(str(path), sr=None, mono=False)
    array = np.asarray(samples, dtype=np.float32)
    if array.ndim == 1:
        frames = array.shape[0]
        channels = 1
        array = array.reshape(frames, 1)
    else:
        channels = int(array.shape[0])
        frames = int(array.shape[1])
        array = array.T
    duration = frames / float(sample_rate) if sample_rate else 0.0
    return DecodedAudio(samples=array, sample_rate=int(sample_rate), channels=channels, duration_seconds=duration, format=None)


def _decode_with_pydub(path: Path) -> DecodedAudio | None:
    import numpy as np
    from pydub import AudioSegment

    segment = AudioSegment.from_file(str(path))
    channels = int(segment.channels or 0)
    sample_rate = int(segment.frame_rate or 0)
    raw = np.array(segment.get_array_of_samples())
    if channels > 1 and raw.size:
        raw = raw.reshape((-1, channels))
    elif raw.size:
        raw = raw.reshape((-1, 1))
    sample_width_bits = max(1, int(segment.sample_width) * 8)
    max_int = float(2 ** (sample_width_bits - 1))
    samples = raw.astype(np.float32) / max_int if raw.size else raw.astype(np.float32)
    duration = len(segment) / 1000.0
    return DecodedAudio(samples=samples, sample_rate=sample_rate, channels=channels, duration_seconds=duration, format=path.suffix.lstrip(".").upper() or None)


def _validate_format(path: Path, detected_format: str | None, report: QualityReport) -> None:
    if not detected_format:
        return
    suffix = path.suffix.lower().lstrip(".")
    normalized = detected_format.lower()
    expected = {"wav": ("wav", "wave"), "mp3": ("mp3", "mpeg")}.get(suffix)
    if expected and not any(token in normalized for token in expected):
        report.warnings.append("Generated audio format does not appear to match the file extension.")


def _validate_duration(actual: float, expected: int | None, report: QualityReport) -> None:
    if actual <= 0:
        _fail(report, "Generated audio has no measurable duration.")
        return
    if actual < MIN_REASONABLE_DURATION_SECONDS:
        _fail(report, "Generated audio is extremely short.")
    if expected:
        if actual < expected * 0.5:
            report.warnings.append("Generated audio is much shorter than requested.")
        if actual > expected * 1.5:
            report.warnings.append("Generated audio is much longer than requested.")


def _validate_sample_rate(sample_rate: int, report: QualityReport) -> None:
    if sample_rate <= 0:
        _fail(report, "Generated audio has an invalid sample rate.")
    elif sample_rate < MIN_SAMPLE_RATE_HZ:
        report.warnings.append("Generated audio sample rate is below 16000 Hz.")


def _validate_channels(channels: int, report: QualityReport) -> None:
    if channels <= 0:
        _fail(report, "Generated audio has an invalid channel count.")
    elif channels > MAX_REASONABLE_CHANNELS:
        report.warnings.append("Generated audio channel count is unusual.")


def _validate_levels(samples: Any, report: QualityReport) -> None:
    import numpy as np

    array = np.asarray(samples, dtype=np.float32)
    if array.size == 0:
        _fail(report, "Generated audio contains no samples.")
        report.is_silent = True
        report.peak_db = -120.0
        report.loudness_estimate = -120.0
        report.clipping_detected = False
        return

    absolute = np.abs(array)
    peak = float(np.max(absolute))
    rms = float(np.sqrt(np.mean(np.square(array))))
    peak_db = _amplitude_to_db(peak)
    rms_db = _amplitude_to_db(rms)
    clipping_fraction = float(np.mean(absolute >= CLIPPING_ABS_THRESHOLD))

    report.peak_db = round(peak_db, 2)
    report.loudness_estimate = round(rms_db, 2)
    report.is_silent = peak_db < SILENT_PEAK_DBFS
    report.clipping_detected = clipping_fraction > CLIPPING_FRACTION_THRESHOLD

    if report.is_silent:
        _fail(report, "Generated audio appears silent.")
    elif peak_db < VERY_QUIET_PEAK_DBFS:
        report.warnings.append("Generated audio peak level is very low.")

    if report.clipping_detected:
        _fail(report, "Generated audio is clipping.")


def _amplitude_to_db(value: float) -> float:
    import math

    if value <= 0:
        return -120.0
    return 20.0 * math.log10(max(value, 1e-12))


def _fail(report: QualityReport, message: str) -> None:
    report.warnings.append(message)
    report.validation_errors.append(message)


def _dedupe(values) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result
