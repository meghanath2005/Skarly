from __future__ import annotations

from pathlib import Path
import math
from typing import Any, Callable

import numpy as np

from ..audio_validation import validate_audio_file
from ..models import MusicSourcePreparation, VocalLeakageQuality
from . import stems as stems_service


VOCAL_LEAKAGE_WAVEFORM_CORRELATION_THRESHOLD = 0.30
VOCAL_LEAKAGE_SPECTRAL_SIMILARITY_THRESHOLD = 0.55
VOCAL_LEAKAGE_LOW_ACTIVITY_DB_THRESHOLD = -18.0


def prepare_music_source(
    *,
    source_audio_path: str,
    requested_mode: str,
    preserve_original_vocal: bool,
    job_id: str,
    settings: Any,
    url_for_path: Callable[[str | None], str | None],
) -> MusicSourcePreparation:
    source = str(Path(source_audio_path).resolve())
    normalized_mode = (requested_mode or "auto").strip().lower().replace("-", "_")
    source_quality = validate_audio_file(source, generator_name="music_source")
    if normalized_mode == "instrumental":
        return MusicSourcePreparation(
            requested_mode=normalized_mode,
            detected_mode="instrumental",
            separation_status="not_required",
            vocal_detected=False,
            vocal_preserved=False,
            detection_confidence=1.0,
            source_audio_path=source,
            instrumental_audio_path=source,
            instrumental_audio_url=url_for_path(source),
            quality_reports={"source": source_quality},
        )

    separation = stems_service.separate_stems(
        audio_path=source,
        output_dir=getattr(settings, "stems_output_dir", "outputs/stems"),
        job_id=f"{job_id}_source",
        stems=["vocals", "no_vocals"],
        engine=getattr(settings, "stems_engine", "demucs"),
        timeout_seconds=int(getattr(settings, "stems_timeout_seconds", 900)),
        enabled=bool(getattr(settings, "stems_enabled", True)),
        demucs_cli_path=getattr(settings, "demucs_cli_path", "python -m demucs"),
        demucs_model=getattr(settings, "demucs_model", "htdemucs_ft"),
        demucs_device=getattr(settings, "demucs_device", "cuda"),
        url_for_path=url_for_path,
    )
    vocal_path = separation.stem_paths.get("vocals")
    instrumental_path = separation.stem_paths.get("no_vocals")
    separation_ok = separation.status in {"completed", "completed_partial"} and bool(vocal_path and instrumental_path)
    if not separation_ok:
        warnings = [
            *separation.warnings,
            "Automatic source preparation requires both vocals and no_vocals stems; generation was not started from the mixed source.",
        ]
        return MusicSourcePreparation(
            requested_mode=normalized_mode,
            detected_mode="unknown",
            separation_status=separation.status or "failed",
            vocal_detected=False,
            vocal_preserved=False,
            detection_confidence=0.0,
            source_audio_path=source,
            quality_reports={"source": source_quality, **separation.quality_reports},
            warnings=_dedupe(warnings),
        )

    energy_db, activity_ratio = measure_vocal_presence(source, vocal_path)
    energy_threshold = float(getattr(settings, "music_to_music_vocal_threshold_db", -24.0))
    activity_threshold = float(getattr(settings, "music_to_music_min_vocal_activity", 0.04))
    detected_by_signal = energy_db >= energy_threshold and activity_ratio >= activity_threshold
    vocal_detected = normalized_mode == "full_song" or detected_by_signal
    detected_mode = "full_song" if vocal_detected else "instrumental"
    margin = energy_db - energy_threshold
    if normalized_mode == "full_song":
        confidence = 1.0 if detected_by_signal else 0.65
    elif vocal_detected:
        confidence = min(0.99, max(0.55, 0.7 + margin / 40.0 + activity_ratio / 4.0))
    else:
        confidence = min(0.99, max(0.55, 0.72 + (-margin) / 50.0))
    warnings = list(separation.warnings)
    if normalized_mode == "full_song" and not detected_by_signal:
        warnings.append("Full-song mode was forced even though the separated vocal measured below the automatic vocal threshold.")

    leakage_quality = assess_vocal_leakage(vocal_path, instrumental_path) if vocal_detected else None
    if leakage_quality is not None and not leakage_quality.passed:
        warnings.extend(leakage_quality.warnings)
        warnings.append("Separated vocals failed the pre-mix leakage gate; generation was stopped before the singer could be mixed with new music.")
        return MusicSourcePreparation(
            requested_mode=normalized_mode,
            detected_mode="full_song",
            separation_status="failed_vocal_leakage",
            vocal_detected=True,
            vocal_preserved=False,
            detection_confidence=round(confidence, 3),
            source_audio_path=source,
            vocal_energy_db_below_mix=round(energy_db, 3),
            vocal_activity_ratio=round(activity_ratio, 4),
            vocal_leakage_quality=leakage_quality,
            quality_reports={"source": source_quality, **separation.quality_reports},
            warnings=_dedupe(warnings),
        )

    prepared_instrumental = instrumental_path if vocal_detected else source
    preserve = bool(preserve_original_vocal and vocal_detected)
    return MusicSourcePreparation(
        requested_mode=normalized_mode,
        detected_mode=detected_mode,
        separation_status=separation.status,
        vocal_detected=vocal_detected,
        vocal_preserved=preserve,
        detection_confidence=round(confidence, 3),
        source_audio_path=source,
        instrumental_audio_path=prepared_instrumental,
        instrumental_audio_url=url_for_path(prepared_instrumental),
        vocal_audio_path=vocal_path if vocal_detected else None,
        vocal_audio_url=url_for_path(vocal_path) if vocal_detected else None,
        vocal_energy_db_below_mix=round(energy_db, 3),
        vocal_activity_ratio=round(activity_ratio, 4),
        vocal_leakage_quality=leakage_quality,
        quality_reports={"source": source_quality, **separation.quality_reports},
        warnings=_dedupe(warnings),
    )


def measure_vocal_presence(source_audio_path: str, vocal_audio_path: str) -> tuple[float, float]:
    source, source_rate = _read_audio(source_audio_path)
    vocal, vocal_rate = _read_audio(vocal_audio_path)
    if source_rate != vocal_rate:
        vocal = _resample(vocal, vocal_rate, source_rate)
    length = min(len(source), len(vocal))
    if length <= 0:
        return -120.0, 0.0
    source = source[:length]
    vocal = vocal[:length]
    source_rms = _rms(source)
    vocal_rms = _rms(vocal)
    energy_db = 20.0 * math.log10(max(vocal_rms, 1e-9) / max(source_rms, 1e-9))

    frame_size = max(256, int(source_rate * 0.10))
    threshold = max(1e-4, source_rms * 0.08)
    frame_levels = [
        _rms(vocal[start : start + frame_size])
        for start in range(0, length, frame_size)
        if len(vocal[start : start + frame_size]) >= frame_size // 2
    ]
    activity_ratio = float(np.mean(np.asarray(frame_levels) >= threshold)) if frame_levels else 0.0
    return float(max(-120.0, min(20.0, energy_db))), float(max(0.0, min(1.0, activity_ratio)))


def assess_vocal_leakage(
    vocal_audio_path: str,
    instrumental_audio_path: str,
    *,
    max_duration_seconds: float = 300.0,
) -> VocalLeakageQuality:
    """Reject a vocal stem when accompaniment remains phase/spectrally tied to the instrumental stem."""
    try:
        vocal, vocal_rate = _read_audio(vocal_audio_path)
        instrumental, instrumental_rate = _read_audio(instrumental_audio_path)
        if instrumental_rate != vocal_rate:
            instrumental = _resample(instrumental, instrumental_rate, vocal_rate)
        length = min(len(vocal), len(instrumental), max(1, int(vocal_rate * max_duration_seconds)))
        if length < max(2048, vocal_rate // 2):
            raise RuntimeError("separated stems are too short for leakage analysis")
        vocal = np.asarray(vocal[:length], dtype=np.float32)
        instrumental = np.asarray(instrumental[:length], dtype=np.float32)
        vocal -= float(np.mean(vocal))
        instrumental -= float(np.mean(instrumental))

        stride = max(1, vocal_rate // 8000)
        vocal_feature = vocal[::stride].astype(np.float64)
        instrumental_feature = instrumental[::stride].astype(np.float64)
        denominator = float(np.linalg.norm(vocal_feature) * np.linalg.norm(instrumental_feature))
        waveform_correlation = abs(float(np.dot(vocal_feature, instrumental_feature) / denominator)) if denominator > 1e-12 else 0.0

        frame_size = max(2048, int(vocal_rate * 0.5))
        frames: list[tuple[float, float, int]] = []
        for start in range(0, length - frame_size + 1, frame_size):
            vocal_rms = _rms(vocal[start : start + frame_size])
            instrumental_rms = _rms(instrumental[start : start + frame_size])
            if instrumental_rms >= 1e-5:
                frames.append((vocal_rms, instrumental_rms, start))
        if len(frames) < 4:
            raise RuntimeError("not enough instrument-active frames for leakage analysis")

        low_activity_cutoff = float(np.percentile([item[0] for item in frames], 35.0))
        low_activity_frames = [item for item in frames if item[0] <= low_activity_cutoff]
        if len(low_activity_frames) > 240:
            indices = np.linspace(0, len(low_activity_frames) - 1, 240, dtype=int)
            low_activity_frames = [low_activity_frames[int(index)] for index in indices]

        window = np.hanning(frame_size).astype(np.float32)
        frequencies = np.fft.rfftfreq(frame_size, d=1.0 / vocal_rate)
        band = (frequencies >= 80.0) & (frequencies <= 8000.0)
        spectral_similarities: list[float] = []
        leakage_levels_db: list[float] = []
        for vocal_rms, instrumental_rms, start in low_activity_frames:
            vocal_spectrum = np.abs(np.fft.rfft(vocal[start : start + frame_size] * window))[band]
            instrumental_spectrum = np.abs(np.fft.rfft(instrumental[start : start + frame_size] * window))[band]
            spectrum_denominator = float(np.linalg.norm(vocal_spectrum) * np.linalg.norm(instrumental_spectrum))
            if spectrum_denominator > 1e-12:
                spectral_similarities.append(float(np.dot(vocal_spectrum, instrumental_spectrum) / spectrum_denominator))
            leakage_levels_db.append(20.0 * math.log10(max(vocal_rms, 1e-9) / max(instrumental_rms, 1e-9)))

        spectral_similarity = float(np.median(spectral_similarities)) if spectral_similarities else 0.0
        leakage_db = float(np.median(leakage_levels_db)) if leakage_levels_db else -120.0
        correlated_leakage = waveform_correlation >= VOCAL_LEAKAGE_WAVEFORM_CORRELATION_THRESHOLD
        low_activity_leakage = (
            spectral_similarity >= VOCAL_LEAKAGE_SPECTRAL_SIMILARITY_THRESHOLD
            and leakage_db >= VOCAL_LEAKAGE_LOW_ACTIVITY_DB_THRESHOLD
        )
        passed = not (correlated_leakage or low_activity_leakage)
        warnings: list[str] = []
        if not passed:
            warnings.append(
                "Vocal stem contains probable instrumental leakage "
                f"(correlation {waveform_correlation:.3f}, low-activity spectral similarity {spectral_similarity:.3f}, "
                f"level {leakage_db:.1f} dB)."
            )
        return VocalLeakageQuality(
            status="passed" if passed else "leakage_detected",
            waveform_correlation=round(waveform_correlation, 6),
            low_activity_spectral_similarity=round(spectral_similarity, 6),
            low_activity_leakage_db=round(max(-120.0, min(40.0, leakage_db)), 3),
            analysed_duration_seconds=round(length / vocal_rate, 3),
            analysed_frames=len(low_activity_frames),
            passed=passed,
            warnings=warnings,
        )
    except Exception as exc:
        return VocalLeakageQuality(
            status="failed",
            passed=False,
            warnings=[f"Vocal leakage analysis could not complete: {str(exc)[:200]}"],
        )


def _read_audio(path: str) -> tuple[np.ndarray, int]:
    try:
        import soundfile as sf

        samples, sample_rate = sf.read(path, always_2d=True, dtype="float32")
        mono = np.asarray(samples, dtype=np.float32).mean(axis=1)
        return mono, int(sample_rate)
    except Exception as exc:
        raise RuntimeError(f"Could not read audio for vocal detection: {exc}") from exc


def _resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate <= 0 or target_rate <= 0 or source_rate == target_rate or samples.size == 0:
        return samples
    target_length = max(1, int(round(len(samples) * target_rate / source_rate)))
    source_positions = np.linspace(0.0, 1.0, len(samples), endpoint=False)
    target_positions = np.linspace(0.0, 1.0, target_length, endpoint=False)
    return np.interp(target_positions, source_positions, samples).astype(np.float32)


def _rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64)))) if samples.size else 0.0


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result
