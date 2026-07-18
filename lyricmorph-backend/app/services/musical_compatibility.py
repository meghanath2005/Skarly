from __future__ import annotations

from pathlib import Path
import math
import subprocess
from typing import Any

import numpy as np

from ..models import MusicalCompatibilityQuality
from . import vocal_analysis


MELODY_CHORD_TONE_RATIO_MIN = 0.32
PHRASE_BEAT_ALIGNMENT_MIN = 0.70
DOWNBEAT_ALIGNMENT_MIN = 0.70
ALIGNMENT_TOLERANCE_SECONDS = 0.25
EXACT_KEY_CONFIDENCE_MIN = 0.55


def assess_vocal_arrangement(
    *,
    backing_audio_path: str | Path,
    target_bpm: float,
    target_key: str,
    song_map: Any,
) -> MusicalCompatibilityQuality:
    """Fail-closed musical QA for a backing that will be mixed with a preserved singer."""

    tempo_tolerance = max(3.0, float(target_bpm) * 0.03)
    warnings: list[str] = []
    try:
        import librosa
        import soundfile as sf

        samples, sample_rate = sf.read(str(backing_audio_path), always_2d=True, dtype="float32")
        mono = np.asarray(samples, dtype=np.float32).mean(axis=1)
        if mono.size < max(2048, sample_rate * 3):
            raise RuntimeError("backing is too short for musical compatibility analysis")

        detail, _note = vocal_analysis._representative_detail_audio(mono, sample_rate)
        output_key, key_confidence, _pitch_status, _key_note = vocal_analysis._estimate_key_and_pitch(detail, sample_rate)
        output_bpm, bpm_note = vocal_analysis._estimate_bpm(detail, sample_rate, [])
        if bpm_note and output_bpm == vocal_analysis.DEFAULT_BPM:
            output_bpm = None

        tempo_delta = _tempo_family_delta(float(target_bpm), output_bpm)
        tempo_match = tempo_delta is not None and tempo_delta <= tempo_tolerance
        exact_key_match = bool(key_confidence > 0 and _normalized_key(output_key) == _normalized_key(target_key))

        analysis_rate = 22_050
        if sample_rate != analysis_rate:
            mono = librosa.resample(mono, orig_sr=sample_rate, target_sr=analysis_rate).astype(np.float32, copy=False)
            sample_rate = analysis_rate
        hop_length = 1024
        onset_envelope = librosa.onset.onset_strength(y=mono, sr=sample_rate, hop_length=hop_length)
        _beat_tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_envelope,
            sr=sample_rate,
            hop_length=hop_length,
            units="frames",
        )
        beat_times = librosa.frames_to_time(np.asarray(beat_frames).reshape(-1), sr=sample_rate, hop_length=hop_length)

        payload = song_map.model_dump(mode="json") if hasattr(song_map, "model_dump") else dict(song_map or {})
        phrases = payload.get("phrases") or []
        phrase_starts = [
            float(item["start_seconds"])
            for item in phrases
            if item.get("start_seconds") is not None and math.isfinite(float(item["start_seconds"]))
        ]
        tempo_payload = payload.get("tempo") or {}
        downbeats = [
            float(value)
            for value in (tempo_payload.get("downbeats") or [])
            if math.isfinite(float(value))
        ]
        phrase_alignment = _nearest_beat_ratio(phrase_starts, beat_times)
        downbeat_alignment = _nearest_beat_ratio(downbeats, beat_times)
        phrase_match = phrase_alignment is not None and phrase_alignment >= PHRASE_BEAT_ALIGNMENT_MIN
        downbeat_match = downbeat_alignment is not None and downbeat_alignment >= DOWNBEAT_ALIGNMENT_MIN

        melody_points = [
            item
            for item in (payload.get("melody_curve") or [])
            if item.get("voiced") and item.get("midi") is not None and item.get("time_seconds") is not None
        ]
        melody_ratio = _melody_chord_tone_ratio(
            mono,
            sample_rate,
            hop_length=hop_length,
            melody_points=melody_points,
            librosa=librosa,
        )
        melody_match = melody_ratio is not None and melody_ratio >= MELODY_CHORD_TONE_RATIO_MIN
        low_confidence_melody_match = bool(
            not exact_key_match
            and 0 < float(key_confidence) < EXACT_KEY_CONFIDENCE_MIN
            and melody_match
        )
        key_match = bool(exact_key_match or low_confidence_melody_match)
        key_match_method = (
            "exact"
            if exact_key_match
            else "timed_melody_support"
            if low_confidence_melody_match
            else "mismatch"
        )

        if not tempo_match:
            warnings.append(
                f"Backing tempo {output_bpm:.2f} BPM does not match {target_bpm:.2f} BPM within {tempo_tolerance:.2f} BPM."
                if output_bpm
                else "Backing tempo could not be measured reliably."
            )
        if low_confidence_melody_match:
            warnings.append(
                f"Global backing key estimate {output_key or 'unknown'} was low-confidence ({key_confidence:.3f}); "
                "timed preserved-vocal melody support passed, so no destructive pitch correction was applied."
            )
        elif not key_match:
            warnings.append(
                f"Backing key {output_key or 'unknown'} does not match preserved vocal key {target_key}."
            )
        if not melody_match:
            warnings.append(
                "Backing harmony does not support enough timed vocal melody notes "
                f"({(melody_ratio or 0.0):.3f} chord-tone ratio)."
            )
        if not phrase_match:
            warnings.append(
                "Backing beat grid does not align with enough vocal phrase starts "
                f"({(phrase_alignment or 0.0):.3f} aligned)."
            )
        if not downbeat_match:
            warnings.append(
                "Backing beat grid does not align with enough planned downbeats "
                f"({(downbeat_alignment or 0.0):.3f} aligned)."
            )

        passed = bool(tempo_match and key_match and melody_match and phrase_match and downbeat_match)
        return MusicalCompatibilityQuality(
            target_bpm=round(float(target_bpm), 3),
            output_bpm=round(float(output_bpm), 3) if output_bpm else None,
            tempo_delta_bpm=round(float(tempo_delta), 3) if tempo_delta is not None else None,
            tempo_tolerance_bpm=round(tempo_tolerance, 3),
            tempo_match=tempo_match,
            target_key=str(target_key),
            output_key=output_key,
            output_key_confidence=round(float(key_confidence), 3),
            key_match=key_match,
            key_match_method=key_match_method,
            melody_chord_tone_ratio=round(float(melody_ratio), 6) if melody_ratio is not None else None,
            melody_match=melody_match,
            phrase_beat_alignment_ratio=round(float(phrase_alignment), 6) if phrase_alignment is not None else None,
            phrase_match=phrase_match,
            downbeat_alignment_ratio=round(float(downbeat_alignment), 6) if downbeat_alignment is not None else None,
            downbeat_match=downbeat_match,
            analysed_phrase_count=len(phrase_starts),
            analysed_downbeat_count=len(downbeats),
            analysed_melody_points=len(melody_points),
            passed=passed,
            warnings=warnings,
        )
    except Exception as exc:
        return MusicalCompatibilityQuality(
            target_bpm=round(float(target_bpm), 3),
            tempo_tolerance_bpm=round(tempo_tolerance, 3),
            target_key=str(target_key),
            passed=False,
            warnings=[f"Musical compatibility analysis could not complete: {str(exc)[:240]}"],
        )


def key_transposition_semitones(output_key: str | None, target_key: str | None) -> int | None:
    """Return the shortest root transposition when source and target modes match."""

    output = _normalized_key(output_key)
    target = _normalized_key(target_key)
    if output is None or target is None or output[1] != target[1]:
        return None
    delta = (target[0] - output[0]) % 12
    if delta > 6:
        delta -= 12
    return int(delta)


def transpose_backing_to_key(
    *,
    input_audio_path: str | Path,
    output_audio_path: str | Path,
    semitones: int,
    ffmpeg_path: str,
    timeout_seconds: int | float,
) -> Path:
    """Pitch-shift a complete backing without changing its tempo or duration."""

    shift = int(semitones)
    if shift < -6 or shift > 6 or shift == 0:
        raise ValueError("Key correction must be between -6 and +6 non-zero semitones")
    source = Path(input_audio_path).expanduser().resolve()
    target = Path(output_audio_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Backing for key correction was not found: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    pitch_ratio = 2.0 ** (shift / 12.0)
    subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-i",
            str(source),
            "-af",
            f"rubberband=pitch={pitch_ratio:.10f}",
            "-ac",
            "2",
            "-ar",
            "48000",
            str(target),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=max(30.0, float(timeout_seconds)),
    )
    if not target.is_file() or target.stat().st_size <= 44:
        raise RuntimeError("FFmpeg did not create the key-corrected backing")
    return target


def _nearest_beat_ratio(values: list[float], beat_times: np.ndarray) -> float | None:
    if not values or beat_times.size == 0:
        return None
    aligned = [
        float(np.min(np.abs(beat_times - value))) <= ALIGNMENT_TOLERANCE_SECONDS
        for value in values
    ]
    return float(np.mean(aligned)) if aligned else None


def _melody_chord_tone_ratio(
    mono: np.ndarray,
    sample_rate: int,
    *,
    hop_length: int,
    melody_points: list[dict[str, Any]],
    librosa: Any,
) -> float | None:
    if not melody_points:
        return None
    chroma = librosa.feature.chroma_cqt(y=mono, sr=sample_rate, hop_length=hop_length)
    if chroma.size == 0 or chroma.shape[1] == 0:
        return None
    supported: list[bool] = []
    for point in melody_points:
        frame = int(round(float(point["time_seconds"]) * sample_rate / hop_length))
        frame = min(chroma.shape[1] - 1, max(0, frame))
        column = chroma[:, frame]
        pitch_class = int(round(float(point["midi"]))) % 12
        rank = 1 + int(np.sum(column > column[pitch_class]))
        supported.append(rank <= 4)
    return float(np.mean(supported)) if supported else None


def _tempo_family_delta(target_bpm: float, output_bpm: float | None) -> float | None:
    if not output_bpm or output_bpm <= 0:
        return None
    return min(abs(target_bpm - candidate) for candidate in (output_bpm / 2.0, output_bpm, output_bpm * 2.0))


def _normalized_key(value: str | None) -> tuple[int, str] | None:
    parts = str(value or "").strip().replace("♭", "b").replace("♯", "#").split()
    if len(parts) < 2:
        return None
    root_map = {
        "c": 0,
        "b#": 0,
        "c#": 1,
        "db": 1,
        "d": 2,
        "d#": 3,
        "eb": 3,
        "e": 4,
        "fb": 4,
        "e#": 5,
        "f": 5,
        "f#": 6,
        "gb": 6,
        "g": 7,
        "g#": 8,
        "ab": 8,
        "a": 9,
        "a#": 10,
        "bb": 10,
        "b": 11,
        "cb": 11,
    }
    root = root_map.get(parts[0].lower())
    mode = parts[1].lower()
    if root is None or mode not in {"major", "minor"}:
        return None
    return root, mode
