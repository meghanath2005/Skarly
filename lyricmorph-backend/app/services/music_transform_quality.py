from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import shutil
from typing import Any, Callable

import numpy as np

from ..models import MusicTransformationQuality
from . import stems as stems_service
from .music_source import measure_vocal_presence


def assess_transformation(
    *,
    source_audio_path: str,
    output_audio_path: str,
    expected_duration_seconds: float | None,
    candidate_id: str,
    settings: Any,
    url_for_path: Callable[[str | None], str | None],
) -> MusicTransformationQuality:
    warnings: list[str] = []
    try:
        measurements = _measure_transformation(source_audio_path, output_audio_path, expected_duration_seconds)
    except Exception as exc:
        return MusicTransformationQuality(
            original_enough=False,
            duration_match=False,
            passed=False,
            warnings=[f"Transformation analysis failed: {exc}"],
        )

    vocal_status = "disabled"
    vocal_energy_db: float | None = None
    vocal_leakage: bool | None = None
    verify_vocals = bool(getattr(settings, "music_to_music_verify_generated_vocals", True))
    if verify_vocals:
        separation = stems_service.separate_stems(
            audio_path=output_audio_path,
            output_dir=getattr(settings, "stems_output_dir", "outputs/stems"),
            job_id=f"{candidate_id}_vocal_check",
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
        if separation.status in {"completed", "completed_partial"} and vocal_path:
            vocal_energy_db, activity_ratio = measure_vocal_presence(output_audio_path, vocal_path)
            energy_threshold = float(getattr(settings, "music_to_music_vocal_threshold_db", -24.0))
            activity_threshold = float(getattr(settings, "music_to_music_min_vocal_activity", 0.04))
            vocal_leakage = vocal_energy_db >= energy_threshold and activity_ratio >= activity_threshold
            vocal_status = "passed" if not vocal_leakage else "leakage_detected"
            if vocal_leakage:
                clean_generated_vocals = bool(getattr(settings, "music_to_music_clean_generated_vocals", False))
                if clean_generated_vocals and instrumental_path and Path(instrumental_path).is_file():
                    shutil.copyfile(instrumental_path, output_audio_path)
                    try:
                        measurements = _measure_transformation(
                            source_audio_path,
                            output_audio_path,
                            expected_duration_seconds,
                        )
                        vocal_status = "removed"
                        vocal_leakage = False
                        warnings.append(
                            "Generated guide-vocal material was removed with Demucs before the original singer was mixed "
                            f"({vocal_energy_db:.1f} dB detected in the raw render)."
                        )
                    except Exception as exc:
                        vocal_status = "failed"
                        warnings.append(f"Generated-vocal cleanup could not be validated: {str(exc)[:180]}")
                else:
                    warnings.append(
                        f"Generated backing may contain vocal material ({vocal_energy_db:.1f} dB vocal-stem energy relative to mix)."
                    )
        else:
            vocal_status = "failed"
            warnings.extend(separation.warnings)
            warnings.append("Generated-vocal verification could not complete; review the backing before using it.")

    source_sha = measurements["source_sha"]
    output_sha = measurements["output_sha"]
    hashes_differ = measurements["hashes_differ"]
    waveform_correlation = measurements["waveform_correlation"]
    onset_similarity = measurements["onset_similarity"]
    source_bpm = measurements["source_bpm"]
    output_bpm = measurements["output_bpm"]
    tempo_delta = measurements["tempo_delta"]
    duration_match = measurements["duration_match"]
    original_enough = measurements["original_enough"]
    if not duration_match:
        warnings.append("Generated duration does not match the prepared source duration.")
    if not original_enough:
        warnings.append("Generated audio is too similar to the prepared reference or originality analysis was inconclusive.")
    vocal_gate = not verify_vocals or vocal_status in {"passed", "removed"}
    passed = bool(duration_match and original_enough and vocal_gate)
    return MusicTransformationQuality(
        source_sha256=source_sha,
        output_sha256=output_sha,
        hashes_differ=hashes_differ,
        waveform_correlation=round(waveform_correlation, 6),
        onset_similarity=round(onset_similarity, 6),
        source_bpm=round(source_bpm, 3) if source_bpm else None,
        output_bpm=round(output_bpm, 3) if output_bpm else None,
        tempo_family_delta_bpm=round(tempo_delta, 3) if tempo_delta is not None else None,
        duration_match=duration_match,
        original_enough=original_enough,
        vocal_check_status=vocal_status,
        vocal_energy_db_below_mix=round(vocal_energy_db, 3) if vocal_energy_db is not None else None,
        vocal_leakage_detected=vocal_leakage,
        passed=passed,
        warnings=_dedupe(warnings),
    )


def _measure_transformation(
    source_audio_path: str,
    output_audio_path: str,
    expected_duration_seconds: float | None,
) -> dict[str, Any]:
    source_sha = _sha256(source_audio_path)
    output_sha = _sha256(output_audio_path)
    source, source_rate = _read_audio(source_audio_path)
    output, output_rate = _read_audio(output_audio_path)
    source_feature = _feature_signal(source, source_rate)
    output_feature = _feature_signal(output, output_rate)
    waveform_correlation = _correlation(source_feature, output_feature)
    onset_similarity = _correlation(_onset_envelope(source_feature), _onset_envelope(output_feature))
    output_duration = len(output) / max(1, output_rate)
    duration_match = expected_duration_seconds is None or abs(output_duration - expected_duration_seconds) <= max(
        1.5,
        expected_duration_seconds * 0.04,
    )
    hashes_differ = source_sha != output_sha
    original_enough = bool(hashes_differ and (abs(waveform_correlation) < 0.98 or onset_similarity < 0.98))
    source_bpm = _tempo(source, source_rate)
    output_bpm = _tempo(output, output_rate)
    return {
        "source_sha": source_sha,
        "output_sha": output_sha,
        "hashes_differ": hashes_differ,
        "waveform_correlation": waveform_correlation,
        "onset_similarity": onset_similarity,
        "source_bpm": source_bpm,
        "output_bpm": output_bpm,
        "tempo_delta": _tempo_family_delta(source_bpm, output_bpm),
        "duration_match": duration_match,
        "original_enough": original_enough,
    }


def _sha256(path: str) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_audio(path: str) -> tuple[np.ndarray, int]:
    import soundfile as sf

    samples, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    return np.asarray(samples, dtype=np.float32).mean(axis=1), int(sample_rate)


def _feature_signal(samples: np.ndarray, sample_rate: int, target_rate: int = 4000) -> np.ndarray:
    if samples.size == 0:
        return np.zeros(1, dtype=np.float32)
    max_samples = max(1, min(len(samples), sample_rate * 180))
    samples = samples[:max_samples]
    target_length = max(1, int(round(len(samples) * target_rate / max(1, sample_rate))))
    source_positions = np.linspace(0.0, 1.0, len(samples), endpoint=False)
    target_positions = np.linspace(0.0, 1.0, target_length, endpoint=False)
    result = np.interp(target_positions, source_positions, samples).astype(np.float32)
    peak = float(np.max(np.abs(result))) if result.size else 0.0
    return result / peak if peak > 1e-8 else result


def _onset_envelope(samples: np.ndarray, frame_size: int = 200) -> np.ndarray:
    levels = np.asarray(
        [float(np.sqrt(np.mean(np.square(samples[start : start + frame_size])))) for start in range(0, len(samples), frame_size)],
        dtype=np.float32,
    )
    if levels.size < 2:
        return np.zeros(1, dtype=np.float32)
    return np.maximum(0.0, np.diff(levels))


def _correlation(left: np.ndarray, right: np.ndarray) -> float:
    length = min(len(left), len(right))
    if length < 4:
        return 0.0
    left = left[:length]
    right = right[:length]
    if float(np.std(left)) < 1e-8 or float(np.std(right)) < 1e-8:
        return 0.0
    return float(np.clip(np.corrcoef(left, right)[0, 1], -1.0, 1.0))


def _tempo(samples: np.ndarray, sample_rate: int) -> float | None:
    try:
        import librosa

        value = librosa.feature.rhythm.tempo(y=samples.astype(np.float32), sr=sample_rate, aggregate=np.median)
        return float(np.asarray(value).reshape(-1)[0]) if np.asarray(value).size else None
    except Exception:
        return None


def _tempo_family_delta(source_bpm: float | None, output_bpm: float | None) -> float | None:
    if not source_bpm or not output_bpm:
        return None
    candidates = [output_bpm / 2.0, output_bpm, output_bpm * 2.0]
    return min(abs(source_bpm - candidate) for candidate in candidates)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result
