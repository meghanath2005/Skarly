from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import math
import wave

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIXER_NAME = "vocal_backing_mixer"


@dataclass(frozen=True)
class MixResult:
    success: bool
    preview_path: str | None
    final_wav_path: str | None
    final_mp3_path: str | None
    duration_seconds: float | None
    error_message: str | None = None
    logs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggested_fix: str | None = None


@dataclass(frozen=True)
class LoadedAudio:
    samples: np.ndarray
    sample_rate: int


def mix_vocal_with_backing(
    vocal_path: str | Path,
    backing_path: str | Path,
    output_dir: str | Path,
    job_id: str,
    vocal_gain_db: float = 2.0,
    backing_gain_db: float = -3.0,
    ducking_enabled: bool = True,
    ducking_amount: float = 0.35,
    output_format: str = "mp3",
    sample_rate: int = 44100,
) -> MixResult:
    logs: list[str] = []
    warnings: list[str] = []
    vocal_file = Path(vocal_path)
    backing_file = Path(backing_path)
    output_root = resolve_output_dir(output_dir)

    if not vocal_file.exists() or not vocal_file.is_file():
        return _failure(
            "Vocal audio file does not exist.",
            "Upload a valid vocal audio file or remove vocal_audio_path.",
            logs,
            warnings,
        )
    if not backing_file.exists() or not backing_file.is_file():
        return _failure(
            "Backing audio file does not exist.",
            "Generate backing audio first or provide a valid backing_audio_path.",
            logs,
            warnings,
        )

    try:
        rate = max(16000, int(sample_rate or 44100))
        vocal = _load_audio(vocal_file, rate)
        backing = _load_audio(backing_file, rate)
        logs.append(f"Loaded vocal: {vocal_file} at {vocal.sample_rate} Hz")
        logs.append(f"Loaded backing: {backing_file} at {backing.sample_rate} Hz")
    except Exception as exc:
        return _failure(
            f"Audio file could not be decoded: {exc}",
            "Vocal file could not be decoded. Try WAV or MP3.",
            logs,
            warnings,
        )

    try:
        backing_samples = _to_stereo(backing.samples)
        vocal_samples = _to_stereo(vocal.samples)
        target_frames = len(backing_samples)
        if target_frames <= 0:
            return _failure(
                "Backing audio contains no samples.",
                "Generate backing audio first or provide a valid backing_audio_path.",
                logs,
                warnings,
            )

        vocal_samples = _match_duration(vocal_samples, target_frames)
        backing_samples = _match_duration(backing_samples, target_frames)
        duration = target_frames / float(rate)

        vocal_normalized = _normalize_track(vocal_samples, target_peak=0.48)
        backing_normalized = _normalize_track(backing_samples, target_peak=0.42)
        vocal_gain = _db_to_gain(vocal_gain_db)
        backing_gain = _db_to_gain(backing_gain_db)
        vocal_bus = vocal_normalized * vocal_gain
        backing_bus = backing_normalized * backing_gain

        if ducking_enabled:
            amount = float(np.clip(ducking_amount, 0.0, 1.0))
            backing_bus = _apply_ducking(backing_bus, vocal_bus, amount, rate)
            logs.append(f"Applied envelope ducking amount={amount:.2f}")
        else:
            logs.append("Ducking disabled")

        mixed = _limit_mix(vocal_bus + backing_bus)
        output_root.mkdir(parents=True, exist_ok=True)
        safe_job = _safe_name(job_id)
        final_wav = output_root / f"{safe_job}_final.wav"
        _write_wav(final_wav, mixed, rate)
        logs.append(f"Wrote final WAV: {final_wav}")

        normalized_format = _normalize_format(output_format)
        final_mp3: Path | None = None
        preview_path: Path = final_wav
        if normalized_format == "mp3":
            preview_mp3 = output_root / f"{safe_job}_preview.mp3"
            final_mp3_candidate = output_root / f"{safe_job}_final.mp3"
            preview_ok, preview_warning = _export_mp3(final_wav, preview_mp3)
            final_ok, final_warning = _export_mp3(final_wav, final_mp3_candidate)
            if preview_ok:
                preview_path = preview_mp3
                logs.append(f"Wrote preview MP3: {preview_mp3}")
            elif preview_warning:
                warnings.append(preview_warning)
            if final_ok:
                final_mp3 = final_mp3_candidate
                logs.append(f"Wrote final MP3: {final_mp3_candidate}")
            elif final_warning and final_warning not in warnings:
                warnings.append(final_warning)
            if not preview_ok:
                logs.append("MP3 preview unavailable; WAV preview path was kept.")

        return MixResult(
            success=True,
            preview_path=str(preview_path),
            final_wav_path=str(final_wav),
            final_mp3_path=str(final_mp3) if final_mp3 else None,
            duration_seconds=round(duration, 3),
            logs=logs[-40:],
            warnings=_dedupe(warnings),
            suggested_fix="MP3 export failed because FFmpeg may be unavailable. WAV export was kept." if warnings else None,
        )
    except Exception as exc:
        return _failure(
            f"Vocal/backing mix failed: {exc}",
            "Check that both audio files are valid and try lower gain settings.",
            logs,
            warnings,
        )


def resolve_output_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()


def _load_audio(path: Path, target_sample_rate: int) -> LoadedAudio:
    errors: list[str] = []
    try:
        import soundfile as sf

        samples, sample_rate = sf.read(str(path), always_2d=True, dtype="float32")
        audio = np.asarray(samples, dtype=np.float32)
        if sample_rate != target_sample_rate:
            audio = _resample_linear(audio, int(sample_rate), target_sample_rate)
        return LoadedAudio(samples=audio, sample_rate=target_sample_rate)
    except Exception as exc:
        errors.append(f"soundfile: {exc}")

    if path.suffix.lower() == ".wav":
        try:
            return _load_wav_with_stdlib(path, target_sample_rate)
        except Exception as exc:
            errors.append(f"wave: {exc}")

    try:
        from pydub import AudioSegment

        segment = AudioSegment.from_file(str(path)).set_frame_rate(target_sample_rate).set_channels(2)
        raw = np.array(segment.get_array_of_samples())
        if raw.size == 0:
            return LoadedAudio(samples=np.zeros((0, 2), dtype=np.float32), sample_rate=target_sample_rate)
        audio = raw.reshape((-1, 2)).astype(np.float32)
        max_int = float(2 ** (8 * segment.sample_width - 1))
        return LoadedAudio(samples=audio / max_int, sample_rate=target_sample_rate)
    except Exception as exc:
        errors.append(f"pydub: {exc}")

    raise RuntimeError("; ".join(errors))


def _load_wav_with_stdlib(path: Path, target_sample_rate: int) -> LoadedAudio:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if sample_width != 2:
        raise RuntimeError("Only 16-bit PCM WAV fallback is supported")
    raw = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = raw.reshape((-1, channels))
    else:
        audio = raw.reshape((-1, 1))
    if sample_rate != target_sample_rate:
        audio = _resample_linear(audio, int(sample_rate), target_sample_rate)
    return LoadedAudio(samples=audio.astype(np.float32), sample_rate=target_sample_rate)


def _resample_linear(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate <= 0 or target_rate <= 0 or source_rate == target_rate or audio.size == 0:
        return audio.astype(np.float32)
    duration = len(audio) / float(source_rate)
    target_frames = max(1, int(round(duration * target_rate)))
    source_x = np.linspace(0.0, duration, len(audio), endpoint=False)
    target_x = np.linspace(0.0, duration, target_frames, endpoint=False)
    channels = []
    for channel in range(audio.shape[1]):
        channels.append(np.interp(target_x, source_x, audio[:, channel]).astype(np.float32))
    return np.column_stack(channels).astype(np.float32)


def _to_stereo(audio: np.ndarray) -> np.ndarray:
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim == 1:
        return np.column_stack([data, data])
    if data.shape[1] == 1:
        return np.repeat(data, 2, axis=1)
    if data.shape[1] > 2:
        mono = np.mean(data, axis=1, keepdims=True)
        return np.repeat(mono, 2, axis=1)
    return data


def _match_duration(audio: np.ndarray, target_frames: int) -> np.ndarray:
    if len(audio) == target_frames:
        return audio.astype(np.float32)
    if len(audio) > target_frames:
        return audio[:target_frames].astype(np.float32)
    padding = np.zeros((target_frames - len(audio), audio.shape[1]), dtype=np.float32)
    return np.vstack([audio, padding]).astype(np.float32)


def _normalize_track(audio: np.ndarray, target_peak: float) -> np.ndarray:
    data = np.asarray(audio, dtype=np.float32)
    if data.size == 0:
        return data
    data = data - np.mean(data, axis=0, keepdims=True)
    peak = float(np.max(np.abs(data)))
    if peak <= 1e-9:
        return data
    return (data * (target_peak / peak)).astype(np.float32)


def _apply_ducking(backing: np.ndarray, vocal: np.ndarray, amount: float, sample_rate: int) -> np.ndarray:
    if amount <= 0 or backing.size == 0 or vocal.size == 0:
        return backing
    vocal_mono = np.mean(np.abs(vocal), axis=1)
    window = max(1, int(0.05 * sample_rate))
    kernel = np.ones(window, dtype=np.float32) / float(window)
    rms = np.sqrt(np.convolve(np.square(vocal_mono), kernel, mode="same"))
    threshold = max(0.012, float(np.percentile(rms, 68)) * 0.45, float(np.max(rms)) * 0.08)
    active = (rms > threshold).astype(np.float32)
    smooth_window = max(1, int(0.12 * sample_rate))
    smooth = np.ones(smooth_window, dtype=np.float32) / float(smooth_window)
    envelope = np.convolve(active, smooth, mode="same")
    envelope = np.clip(envelope, 0.0, 1.0)
    gain = 1.0 - (amount * envelope)
    gain = np.clip(gain, 0.15, 1.0).astype(np.float32)
    return backing * gain[:, None]


def _limit_mix(audio: np.ndarray) -> np.ndarray:
    data = np.asarray(audio, dtype=np.float32)
    if data.size == 0:
        return data
    peak = float(np.max(np.abs(data)))
    if peak > 0.88:
        data = data * (0.88 / peak)
    return np.clip(data, -0.92, 0.92).astype(np.float32)


def _write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    pcm = (np.clip(audio, -0.95, 0.95) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm.tobytes())


def _export_mp3(source_wav: Path, output_mp3: Path) -> tuple[bool, str | None]:
    try:
        from pydub import AudioSegment

        segment = AudioSegment.from_wav(str(source_wav))
        segment.export(str(output_mp3), format="mp3")
        return True, None
    except Exception:
        if output_mp3.exists():
            try:
                output_mp3.unlink()
            except Exception:
                pass
        return False, "MP3 export failed because FFmpeg may be unavailable. WAV export was kept."


def _db_to_gain(value: float) -> float:
    return float(10.0 ** (float(value) / 20.0))


def _normalize_format(value: str) -> str:
    normalized = (value or "mp3").strip().lower().lstrip(".")
    return normalized if normalized in {"mp3", "wav"} else "mp3"


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)[:120] or "mix"


def _failure(error_message: str, suggested_fix: str, logs: list[str], warnings: list[str]) -> MixResult:
    return MixResult(
        success=False,
        preview_path=None,
        final_wav_path=None,
        final_mp3_path=None,
        duration_seconds=None,
        error_message=error_message,
        logs=logs[-40:],
        warnings=_dedupe(warnings),
        suggested_fix=suggested_fix,
    )


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result
