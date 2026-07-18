from __future__ import annotations

from pathlib import Path
import math
import wave
from typing import Any

import numpy as np

from ..audio_validation import validate_audio_file
from ..models import (
    SongIntelligenceMap,
    SongTempoInfo,
    SongTonalityInfo,
    SongVocalRange,
    VocalAnalysisReport,
)
from . import safe_paths

DEFAULT_KEY = "A minor"
DEFAULT_BPM = 88.0
KEY_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
MAX_REPRESENTATIVE_DETAIL_SECONDS = 18.0
MAX_PITCH_TRACKING_SECONDS = 8.0
MAX_MELODY_MAP_POINTS = 3000
MAX_ONSET_MAP_POINTS = 1500


def analyze_vocal_audio(
    audio_path: str | Path,
    *,
    upload_id: str | None = None,
    normalized_output_dir: str | Path | None = None,
    url_for_path=None,
    expected_duration_seconds: int | None = None,
) -> VocalAnalysisReport:
    """Create a deterministic, full-timeline vocal analysis report.

    Expensive detail estimators use bounded full-song representations, while
    activity, phrase, melody, rhythm, and structure evidence always retain
    coverage from the beginning through the end of the decoded recording.
    """

    source_path = Path(audio_path)
    warnings: list[str] = []
    quality_report = validate_audio_file(
        source_path,
        expected_duration_seconds=expected_duration_seconds,
        generator_name="vocal_analysis_input",
        fallback_used=False,
    )

    if not quality_report.audio_exists:
        warnings.append("Vocal audio file does not exist.")
        return VocalAnalysisReport(
            upload_id=upload_id,
            source_audio_path=str(source_path),
            quality_report=quality_report,
            warnings=_dedupe([*warnings, *quality_report.validation_errors, *quality_report.warnings]),
            is_silent=True,
        )

    try:
        samples, sample_rate = _load_audio(source_path)
    except Exception as exc:
        warnings.append(f"Vocal audio could not be decoded for analysis: {exc}")
        return VocalAnalysisReport(
            upload_id=upload_id,
            source_audio_path=str(source_path),
            duration_seconds=quality_report.duration_seconds,
            sample_rate=quality_report.sample_rate,
            channels=quality_report.channels,
            is_silent=quality_report.is_silent,
            peak_db=quality_report.peak_db,
            loudness_estimate=quality_report.loudness_estimate,
            quality_report=quality_report,
            warnings=_dedupe([*warnings, *quality_report.validation_errors, *quality_report.warnings]),
        )

    samples = _ensure_2d(samples)
    mono = samples.mean(axis=1).astype(np.float32) if samples.size else np.zeros(0, dtype=np.float32)
    duration = len(mono) / float(sample_rate) if sample_rate else (quality_report.duration_seconds or 0.0)
    normalized_path = _write_normalized_wav(
        samples,
        sample_rate,
        source_path=source_path,
        upload_id=upload_id,
        normalized_output_dir=normalized_output_dir,
    )

    activity = _detect_activity(mono, sample_rate)
    phrases = _phrase_boundaries(activity, duration)
    detail_audio, detail_note = _representative_detail_audio(mono, sample_rate)
    if detail_note:
        warnings.append(detail_note)
    bpm, bpm_note = _estimate_bpm(detail_audio, sample_rate, activity)
    if bpm_note:
        warnings.append(bpm_note)
    key, key_confidence, pitch_status, key_note = _estimate_key_and_pitch(detail_audio, sample_rate)
    if key_note:
        warnings.append(key_note)

    energy_curve = _energy_curve(mono, sample_rate, duration, activity)
    melody_curve, pitch_method = _melody_curve(mono, sample_rate, duration, activity)
    silence_regions = _silence_regions(activity, duration)
    breath_regions = _breath_regions(silence_regions)
    tempo = _tempo_details(bpm, bpm_note, activity, duration)
    key_name, scale_name = _split_key_scale(key)
    key_changes = _estimate_key_changes(mono, sample_rate, duration, key)
    stable_notes = _stable_notes(melody_curve, duration)
    note_transitions, pitch_slides = _note_transitions_and_slides(stable_notes, melody_curve)
    ornamentation = _ornamentation_candidates(melody_curve, pitch_slides)
    melodic_motifs, phrase_motif_ids = _melodic_motifs(phrases, melody_curve)
    onset_times, onset_source = _onset_times(mono, sample_rate, duration, activity)
    phrases = _enrich_phrases(
        phrases,
        melody_curve=melody_curve,
        stable_notes=stable_notes,
        onset_times=onset_times,
        tempo=tempo,
        phrase_motif_ids=phrase_motif_ids,
    )
    sections = _section_candidates(duration, phrases)
    sections = _enrich_sections(
        sections,
        phrases=phrases,
        energy_curve=energy_curve,
        onset_times=onset_times,
    )
    rhythm_analysis = _rhythm_analysis(tempo, phrases, sections, onset_times, onset_source)
    structure_analysis = _structure_analysis(sections, phrases, melodic_motifs)
    chord_compatibility = _chord_compatibility(key_name, scale_name, melody_curve)
    song_map = SongIntelligenceMap(
        duration_seconds=round(duration, 3),
        tempo=tempo,
        tonality=SongTonalityInfo(
            key=key_name,
            scale=scale_name,
            confidence=round(float(key_confidence or 0), 3),
            key_changes=key_changes,
            source="audio_chroma" if key_confidence else "planning_fallback",
        ),
        time_signature="4/4",
        time_signature_confidence=0.35 if bpm else 0.0,
        vocal_range=_vocal_range(melody_curve),
        phrases=phrases,
        sections=sections,
        energy_curve=energy_curve,
        melody_curve=melody_curve,
        stable_notes=stable_notes,
        note_transitions=note_transitions,
        pitch_slides=pitch_slides,
        ornamentation=ornamentation,
        melodic_motifs=melodic_motifs,
        chord_compatibility=chord_compatibility,
        rhythm_analysis=rhythm_analysis,
        structure_analysis=structure_analysis,
        silence_regions=silence_regions,
        breath_regions=breath_regions,
        pitch_method=pitch_method,
    )
    if quality_report.is_silent:
        warnings.append("Vocal audio appears silent or nearly silent.")
    if not phrases:
        warnings.append("No clear vocal phrase boundaries were detected; section timing is approximate.")

    return VocalAnalysisReport(
        upload_id=upload_id,
        source_audio_path=str(source_path),
        normalized_wav_path=str(normalized_path) if normalized_path else None,
        normalized_wav_url=url_for_path(str(normalized_path)) if url_for_path and normalized_path else None,
        duration_seconds=round(duration, 3) if duration else quality_report.duration_seconds,
        sample_rate=int(sample_rate) if sample_rate else quality_report.sample_rate,
        channels=int(samples.shape[1]) if samples.ndim == 2 else quality_report.channels,
        is_silent=quality_report.is_silent,
        estimated_bpm=round(float(bpm), 2) if bpm else None,
        estimated_key=key,
        key_confidence=round(float(key_confidence), 3) if key_confidence is not None else None,
        pitch_contour_status=pitch_status,
        phrase_boundaries=phrases,
        section_candidates=sections,
        vocal_activity=activity,
        song_intelligence_map=song_map,
        peak_db=quality_report.peak_db,
        loudness_estimate=quality_report.loudness_estimate,
        quality_report=quality_report,
        warnings=_dedupe([*warnings, *quality_report.validation_errors, *quality_report.warnings]),
    )


def _load_audio(path: Path) -> tuple[np.ndarray, int]:
    errors: list[str] = []
    try:
        import soundfile as sf

        samples, sample_rate = sf.read(str(path), always_2d=True, dtype="float32")
        return np.asarray(samples, dtype=np.float32), int(sample_rate)
    except Exception as exc:
        errors.append(f"soundfile: {exc}")

    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as handle:
                channels = int(handle.getnchannels())
                sample_rate = int(handle.getframerate())
                width = int(handle.getsampwidth())
                frames = handle.readframes(handle.getnframes())
            if width != 2:
                raise RuntimeError("Only 16-bit PCM WAV fallback is supported.")
            raw = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
            samples = raw.reshape((-1, channels)) if channels > 1 else raw.reshape((-1, 1))
            return samples.astype(np.float32), sample_rate
        except Exception as exc:
            errors.append(f"wave: {exc}")

    try:
        from pydub import AudioSegment

        segment = AudioSegment.from_file(str(path))
        channels = int(segment.channels or 1)
        raw = np.array(segment.get_array_of_samples())
        samples = raw.reshape((-1, channels)).astype(np.float32) if channels > 1 else raw.reshape((-1, 1)).astype(np.float32)
        max_int = float(2 ** (8 * segment.sample_width - 1))
        return samples / max_int, int(segment.frame_rate)
    except Exception as exc:
        errors.append(f"pydub: {exc}")

    raise RuntimeError("; ".join(errors))


def _ensure_2d(samples: np.ndarray) -> np.ndarray:
    array = np.asarray(samples, dtype=np.float32)
    if array.ndim == 1:
        return array.reshape((-1, 1))
    if array.ndim == 2:
        return array
    return array.reshape((array.shape[0], -1))


def _write_normalized_wav(
    samples: np.ndarray,
    sample_rate: int,
    *,
    source_path: Path,
    upload_id: str | None,
    normalized_output_dir: str | Path | None,
) -> Path | None:
    if samples.size == 0 or sample_rate <= 0:
        return None

    if normalized_output_dir is not None:
        base_dir = safe_paths.resolve_output_dir(normalized_output_dir)
        target_dir = base_dir / safe_paths.sanitize_filename(upload_id or source_path.stem)
    else:
        target_dir = source_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = target_dir / "normalized.wav"

    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    normalized = samples.copy()
    if peak > 0:
        normalized = normalized * min(1.0, 0.72 / peak)
    normalized = np.clip(normalized, -0.98, 0.98)
    pcm = (normalized * 32767.0).astype("<i2")
    with wave.open(str(normalized_path), "wb") as handle:
        handle.setnchannels(int(pcm.shape[1]) if pcm.ndim == 2 else 1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm.tobytes())
    return normalized_path


def _detect_activity(mono: np.ndarray, sample_rate: int) -> list[dict[str, Any]]:
    if mono.size == 0 or sample_rate <= 0:
        return []
    window = max(512, int(sample_rate * 0.12))
    hop = max(256, int(sample_rate * 0.06))
    padded = np.pad(mono, (0, max(0, window - len(mono) % hop)), mode="constant")
    rms_values: list[float] = []
    starts: list[int] = []
    for start in range(0, max(1, len(padded) - window + 1), hop):
        chunk = padded[start : start + window]
        rms_values.append(float(np.sqrt(np.mean(np.square(chunk))) if chunk.size else 0.0))
        starts.append(start)
    if not rms_values:
        return []
    rms = np.asarray(rms_values, dtype=np.float32)
    active_floor = max(0.006, float(np.percentile(rms, 65)) * 0.45, float(np.max(rms)) * 0.08)
    active = rms >= active_floor
    intervals: list[dict[str, Any]] = []
    current_start: int | None = None
    current_energy = 0.0
    count = 0
    for frame_index, is_active in enumerate(active):
        if is_active and current_start is None:
            current_start = starts[frame_index]
            current_energy = 0.0
            count = 0
        if is_active:
            current_energy += float(rms[frame_index])
            count += 1
        if current_start is not None and (not is_active or frame_index == len(active) - 1):
            end_sample = starts[frame_index] + window
            start_sec = current_start / float(sample_rate)
            end_sec = min(len(mono) / float(sample_rate), end_sample / float(sample_rate))
            if end_sec - start_sec >= 0.25:
                intervals.append(
                    {
                        "start_seconds": round(start_sec, 3),
                        "end_seconds": round(end_sec, 3),
                        "average_rms": round(current_energy / max(1, count), 5),
                    }
                )
            current_start = None
    return _merge_close_intervals(intervals, gap_seconds=0.35)


def _merge_close_intervals(intervals: list[dict[str, Any]], gap_seconds: float) -> list[dict[str, Any]]:
    if not intervals:
        return []
    merged = [dict(intervals[0])]
    for interval in intervals[1:]:
        last = merged[-1]
        if float(interval["start_seconds"]) - float(last["end_seconds"]) <= gap_seconds:
            last["end_seconds"] = interval["end_seconds"]
            last["average_rms"] = round((float(last["average_rms"]) + float(interval["average_rms"])) / 2.0, 5)
        else:
            merged.append(dict(interval))
    return merged


def _representative_detail_audio(mono: np.ndarray, sample_rate: int) -> tuple[np.ndarray, str | None]:
    """Bound expensive key/pitch work while retaining coverage of a long song.

    Activity, phrase boundaries, and section mapping always operate on every
    sample in the upload.  Chroma, tempo, and pitch tracking are much more
    expensive; sampling the opening, middle, and closing sections makes a
    two-minute upload responsive without basing the musical read on only its
    first verse.
    """
    if mono.size == 0 or sample_rate <= 0:
        return mono, None
    max_frames = max(1, int(MAX_REPRESENTATIVE_DETAIL_SECONDS * sample_rate))
    if mono.size <= max_frames:
        return mono, None

    window_frames = max(1, max_frames // 3)
    last_start = max(0, mono.size - window_frames)
    middle_start = max(0, min(last_start, (mono.size - window_frames) // 2))
    starts = (0, middle_start, last_start)
    windows = [mono[start : start + window_frames] for start in starts]
    sampled = np.concatenate(windows).astype(np.float32, copy=False)
    sampled_seconds = len(sampled) / float(sample_rate)
    total_seconds = len(mono) / float(sample_rate)
    return sampled, (
        f"Detailed tempo, key, and pitch analysis sampled {sampled_seconds:.0f}s across the beginning, middle, and end; "
        f"timing and section mapping covered all {total_seconds:.0f}s."
    )


def _phrase_boundaries(activity: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    phrases: list[dict[str, Any]] = []
    for index, interval in enumerate(activity, start=1):
        start = max(0.0, float(interval.get("start_seconds", 0.0)))
        end = min(float(duration or interval.get("end_seconds", start)), float(interval.get("end_seconds", start)))
        if end <= start:
            continue
        phrases.append(
            {
                "phrase": index,
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "duration_seconds": round(end - start, 3),
                "type": "vocal_phrase",
                "delivery": "unclassified_vocal",
                "average_rms": interval.get("average_rms"),
                "sustained_candidate": bool(end - start >= 3.5),
                "confidence": 0.8,
            }
        )
    for index, phrase in enumerate(phrases):
        previous_end = float(phrases[index - 1]["end_seconds"]) if index else 0.0
        next_start = float(phrases[index + 1]["start_seconds"]) if index + 1 < len(phrases) else float(duration)
        phrase["preceding_gap_seconds"] = round(max(0.0, float(phrase["start_seconds"]) - previous_end), 3)
        phrase["following_gap_seconds"] = round(max(0.0, next_start - float(phrase["end_seconds"])), 3)
    return phrases


def _estimate_bpm(mono: np.ndarray, sample_rate: int, activity: list[dict[str, Any]]) -> tuple[float, str | None]:
    if mono.size and sample_rate > 0:
        try:
            import librosa

            tempo = librosa.beat.tempo(y=mono.astype(np.float32), sr=sample_rate, aggregate=np.median)
            bpm = float(np.ravel(tempo)[0])
            if 40 <= bpm <= 220:
                return bpm, None
        except Exception:
            pass
    if len(activity) >= 3:
        starts = [float(item["start_seconds"]) for item in activity[:12]]
        gaps = [gap for gap in np.diff(starts) if 0.25 <= gap <= 3.0]
        if gaps:
            bpm = 60.0 / float(np.median(gaps))
            while bpm < 70:
                bpm *= 2
            while bpm > 140:
                bpm /= 2
            if 40 <= bpm <= 220:
                return bpm, "BPM was estimated from phrase spacing; treat it as approximate."
    return DEFAULT_BPM, "No reliable beat was detected in the vocal; using 88 BPM as a planning fallback."


def _estimate_key_and_pitch(mono: np.ndarray, sample_rate: int) -> tuple[str, float, str, str | None]:
    if mono.size and sample_rate > 0:
        try:
            import librosa

            chroma = librosa.feature.chroma_stft(y=mono.astype(np.float32), sr=sample_rate)
            key, confidence = _key_from_chroma(chroma.mean(axis=1))
            pitch_status = "available"
            try:
                pitch_probe = mono[: max(1, int(MAX_PITCH_TRACKING_SECONDS * sample_rate))].astype(np.float32)
                f0, _, _ = librosa.pyin(
                    pitch_probe,
                    fmin=librosa.note_to_hz("C2"),
                    fmax=librosa.note_to_hz("C6"),
                    sr=sample_rate,
                )
                pitch_status = "available" if np.isfinite(f0).sum() > 2 else "fallback"
            except Exception:
                pitch_status = "fallback"
            return key, confidence, pitch_status, "Key estimate is approximate and should be checked by ear."
        except Exception:
            pass
    return DEFAULT_KEY, 0.0, "unavailable", "Key could not be estimated; using A minor as a safe fallback."


def _key_from_chroma(chroma: np.ndarray) -> tuple[str, float]:
    vector = np.asarray(chroma, dtype=np.float32)
    if vector.size != 12 or float(np.sum(vector)) <= 0:
        return DEFAULT_KEY, 0.0
    vector = vector / max(1e-9, float(np.linalg.norm(vector)))
    major = MAJOR_PROFILE / np.linalg.norm(MAJOR_PROFILE)
    minor = MINOR_PROFILE / np.linalg.norm(MINOR_PROFILE)
    scores: list[tuple[float, str]] = []
    for root in range(12):
        scores.append((float(np.dot(vector, np.roll(major, root))), f"{KEY_NAMES[root]} major"))
        scores.append((float(np.dot(vector, np.roll(minor, root))), f"{KEY_NAMES[root]} minor"))
    scores.sort(reverse=True, key=lambda item: item[0])
    best, label = scores[0]
    second = scores[1][0] if len(scores) > 1 else 0.0
    confidence = max(0.0, min(1.0, best - second + 0.35))
    return label, confidence


def _split_key_scale(value: str | None) -> tuple[str, str]:
    parts = str(value or DEFAULT_KEY).strip().split()
    key = parts[0] if parts else "A"
    scale = parts[1].lower() if len(parts) > 1 else "minor"
    return key, scale if scale in {"major", "minor"} else "unknown"


def _estimate_key_changes(
    mono: np.ndarray,
    sample_rate: int,
    duration: float,
    global_key: str,
) -> list[dict[str, Any]]:
    """Return only persistent coarse key-change candidates.

    Monophonic vocals make modulation detection ambiguous, so candidates need
    support from at least two overlapping windows and remain explicitly marked
    for user confirmation.
    """
    if mono.size == 0 or sample_rate <= 0 or duration < 24.0:
        return []
    try:
        import librosa

        analysis_audio = mono.astype(np.float32, copy=False)
        analysis_rate = int(sample_rate)
        if analysis_rate > 22050:
            analysis_audio = librosa.resample(
                analysis_audio,
                orig_sr=analysis_rate,
                target_sr=22050,
            ).astype(np.float32, copy=False)
            analysis_rate = 22050
        hop_length = 2048
        chroma = librosa.feature.chroma_stft(
            y=analysis_audio,
            sr=analysis_rate,
            n_fft=4096,
            hop_length=hop_length,
        )
        times = librosa.frames_to_time(
            np.arange(chroma.shape[1]),
            sr=analysis_rate,
            hop_length=hop_length,
        )
        window_seconds = min(18.0, max(10.0, duration / 18.0))
        hop_seconds = window_seconds / 2.0
        windows: list[dict[str, Any]] = []
        for start in np.arange(0.0, max(0.01, duration - window_seconds / 2.0), hop_seconds):
            end = min(duration, float(start + window_seconds))
            mask = (times >= start) & (times < end)
            if int(np.count_nonzero(mask)) < 3:
                continue
            vector = np.mean(chroma[:, mask], axis=1)
            label, confidence = _key_from_chroma(vector)
            windows.append(
                {
                    "start_seconds": float(start),
                    "end_seconds": float(end),
                    "key": label,
                    "confidence": float(confidence),
                }
            )
        return _consolidate_key_windows(windows, global_key)
    except Exception:
        return []


def _consolidate_key_windows(
    windows: list[dict[str, Any]],
    global_key: str,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for window in windows:
        label = str(window.get("key") or "").strip()
        if not label:
            continue
        start = float(window.get("start_seconds") or 0.0)
        end = max(start, float(window.get("end_seconds") or start))
        confidence = max(0.0, min(1.0, float(window.get("confidence") or 0.0)))
        if groups and groups[-1]["key"] == label:
            groups[-1]["end_seconds"] = end
            groups[-1]["confidences"].append(confidence)
            groups[-1]["window_count"] += 1
        else:
            groups.append(
                {
                    "key": label,
                    "start_seconds": start,
                    "end_seconds": end,
                    "confidences": [confidence],
                    "window_count": 1,
                }
            )

    persistent = [
        group
        for group in groups
        if int(group["window_count"]) >= 2
        and float(np.mean(group["confidences"])) >= 0.38
        and float(group["end_seconds"]) - float(group["start_seconds"]) >= 8.0
    ]
    if not persistent:
        return []

    current_key = str(global_key or persistent[0]["key"]).strip()
    if float(persistent[0]["start_seconds"]) <= 0.1:
        current_key = str(persistent[0]["key"])
    changes: list[dict[str, Any]] = []
    for group in persistent:
        label = str(group["key"])
        if label == current_key:
            continue
        confidence = float(np.mean(group["confidences"]))
        changes.append(
            {
                "start_seconds": round(float(group["start_seconds"]), 3),
                "previous_key": current_key,
                "key": label,
                "confidence": round(min(0.82, confidence), 3),
                "supporting_windows": int(group["window_count"]),
                "source": "coarse_full_song_chroma",
                "candidate": True,
                "requires_confirmation": True,
            }
        )
        current_key = label
    return changes


def _tempo_details(
    bpm: float | None,
    bpm_note: str | None,
    activity: list[dict[str, Any]],
    duration: float,
) -> SongTempoInfo:
    value = float(bpm or DEFAULT_BPM)
    note = str(bpm_note or "").lower()
    if not bpm_note:
        confidence = 0.72
        source = "audio_onset"
    elif "phrase spacing" in note:
        confidence = 0.42
        source = "phrase_spacing"
    else:
        confidence = 0.15
        source = "planning_fallback"

    starts = np.asarray([float(item.get("start_seconds", 0)) for item in activity], dtype=np.float64)
    intervals = np.diff(starts)
    intervals = intervals[(intervals >= 0.25) & (intervals <= 12.0)]
    drift_percent = 0.0
    interval_cv = 0.0
    if intervals.size >= 4:
        mean_interval = float(np.mean(intervals))
        interval_cv = float(np.std(intervals) / mean_interval) if mean_interval > 0 else 0.0
        split = max(1, intervals.size // 2)
        early = float(np.median(intervals[:split]))
        late = float(np.median(intervals[split:])) if intervals[split:].size else early
        drift_percent = min(100.0, abs(late - early) / max(0.001, early) * 100.0)
    rubato = bool(confidence < 0.5 or interval_cv >= 0.35 or drift_percent >= 12.0)
    bar_seconds = 4.0 * 60.0 / max(1.0, value)
    downbeats = [round(float(point), 3) for point in np.arange(0.0, max(0.0, duration), bar_seconds)[:300]]
    return SongTempoInfo(
        bpm=round(value, 2),
        confidence=round(confidence, 3),
        rubato=rubato,
        tempo_drift_percent=round(drift_percent, 2),
        half_time_bpm=round(value / 2.0, 2) if value / 2.0 >= 40 else None,
        double_time_bpm=round(value * 2.0, 2) if value * 2.0 <= 220 else None,
        downbeats=downbeats,
        source=source,
    )


def _energy_curve(
    mono: np.ndarray,
    sample_rate: int,
    duration: float,
    activity: list[dict[str, Any]],
    *,
    max_points: int = 300,
) -> list[dict[str, Any]]:
    if mono.size == 0 or sample_rate <= 0 or duration <= 0:
        return []
    window_seconds = max(1.0, duration / max(1, max_points))
    window_frames = max(1, int(round(window_seconds * sample_rate)))
    raw: list[tuple[float, float]] = []
    for start in range(0, len(mono), window_frames):
        chunk = mono[start : start + window_frames]
        if chunk.size == 0:
            continue
        rms = float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64))))
        raw.append((start / float(sample_rate), 20.0 * math.log10(max(1e-8, rms))))
    if not raw:
        return []
    db_values = np.asarray([item[1] for item in raw], dtype=np.float64)
    low = float(np.percentile(db_values, 10))
    high = float(np.percentile(db_values, 95))
    span = max(1.0, high - low)
    curve: list[dict[str, Any]] = []
    for start, db in raw:
        center = min(duration, start + window_seconds / 2.0)
        active = any(float(item["start_seconds"]) <= center <= float(item["end_seconds"]) for item in activity)
        curve.append(
            {
                "time_seconds": round(center, 3),
                "rms_db": round(db, 2),
                "relative_energy": round(max(0.0, min(1.0, (db - low) / span)), 3),
                "vocal_active": active,
            }
        )
    return curve[:max_points]


def _melody_curve(
    mono: np.ndarray,
    sample_rate: int,
    duration: float,
    activity: list[dict[str, Any]],
    *,
    max_points: int = MAX_MELODY_MAP_POINTS,
) -> tuple[list[dict[str, Any]], str]:
    if mono.size == 0 or sample_rate <= 0 or duration <= 0:
        return [], "unavailable"
    try:
        import librosa

        frame_length = 2048 if sample_rate >= 16000 else 1024
        hop_length = max(frame_length // 2, int(math.ceil(len(mono) / max(1, max_points))))
        f0 = librosa.yin(
            mono.astype(np.float32, copy=False),
            fmin=float(librosa.note_to_hz("C2")),
            fmax=float(librosa.note_to_hz("C6")),
            sr=sample_rate,
            frame_length=frame_length,
            hop_length=hop_length,
        )
        activity_peak = max((float(item.get("average_rms") or 0) for item in activity), default=0.0)
        points: list[dict[str, Any]] = []
        half = max(1, frame_length // 2)
        for index, frequency in enumerate(np.asarray(f0).ravel()):
            time_seconds = index * hop_length / float(sample_rate)
            if time_seconds > duration + 0.01:
                break
            center = min(len(mono) - 1, max(0, int(round(time_seconds * sample_rate))))
            chunk = mono[max(0, center - half) : min(len(mono), center + half)]
            local_rms = float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64)))) if chunk.size else 0.0
            active = any(float(item["start_seconds"]) <= time_seconds <= float(item["end_seconds"]) for item in activity)
            voiced = bool(active and np.isfinite(frequency) and 65.0 <= float(frequency) <= 1100.0)
            midi = 69.0 + 12.0 * math.log2(float(frequency) / 440.0) if voiced else None
            confidence = min(0.95, 0.45 + 0.5 * local_rms / max(1e-6, activity_peak)) if voiced else 0.0
            points.append(
                {
                    "time_seconds": round(time_seconds, 3),
                    "frequency_hz": round(float(frequency), 2) if voiced else None,
                    "midi": round(float(midi), 2) if midi is not None else None,
                    "note": _midi_to_note(midi) if midi is not None else None,
                    "voiced": voiced,
                    "confidence": round(float(confidence), 3),
                }
            )
        return points[:max_points], "full_song_sparse_yin"
    except Exception:
        return [], "unavailable"


def _midi_to_note(value: float | None) -> str | None:
    if value is None or not math.isfinite(value):
        return None
    rounded = int(round(value))
    names = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
    return f"{names[rounded % 12]}{rounded // 12 - 1}"


def _vocal_range(melody_curve: list[dict[str, Any]]) -> SongVocalRange:
    midi_values = np.asarray(
        [float(point["midi"]) for point in melody_curve if point.get("voiced") and point.get("midi") is not None],
        dtype=np.float64,
    )
    if midi_values.size == 0:
        return SongVocalRange()
    lowest = float(np.percentile(midi_values, 5))
    highest = float(np.percentile(midi_values, 95))
    return SongVocalRange(
        lowest_note=_midi_to_note(lowest),
        highest_note=_midi_to_note(highest),
        lowest_midi=round(lowest, 2),
        highest_midi=round(highest, 2),
    )


def _curve_step_seconds(melody_curve: list[dict[str, Any]]) -> float:
    times = np.asarray(
        [float(point.get("time_seconds") or 0.0) for point in melody_curve],
        dtype=np.float64,
    )
    differences = np.diff(times)
    differences = differences[differences > 1e-4]
    if differences.size == 0:
        return 0.05
    return max(0.01, min(1.0, float(np.median(differences))))


def _stable_notes(
    melody_curve: list[dict[str, Any]],
    duration: float,
) -> list[dict[str, Any]]:
    """Summarise stable pitch regions without modifying the raw pitch curve."""
    if not melody_curve:
        return []
    step_seconds = _curve_step_seconds(melody_curve)
    maximum_gap = max(0.12, step_seconds * 2.6)
    regions: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    def finish() -> None:
        nonlocal current
        if current:
            regions.append(current)
            current = []

    for point in melody_curve:
        if not point.get("voiced") or point.get("midi") is None:
            finish()
            continue
        if current:
            time_gap = float(point["time_seconds"]) - float(current[-1]["time_seconds"])
            recent_pitch = float(np.median([float(item["midi"]) for item in current[-8:]]))
            if time_gap > maximum_gap or abs(float(point["midi"]) - recent_pitch) > 0.62:
                finish()
        current.append(point)
    finish()

    stable: list[dict[str, Any]] = []
    minimum_duration = max(0.16, step_seconds * 1.45)
    for region in regions:
        if len(region) < 2:
            continue
        start = float(region[0]["time_seconds"])
        end = min(float(duration), float(region[-1]["time_seconds"]) + step_seconds)
        if end - start < minimum_duration:
            continue
        pitches = np.asarray([float(point["midi"]) for point in region], dtype=np.float64)
        median_pitch = float(np.median(pitches))
        deviation_cents = float(np.std(pitches) * 100.0)
        stable.append(
            {
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "duration_seconds": round(end - start, 3),
                "median_midi": round(median_pitch, 3),
                "nearest_note": _midi_to_note(median_pitch),
                "pitch_deviation_cents": round(deviation_cents, 1),
                "sustained_candidate": bool(end - start >= 0.55),
                "confidence": round(
                    min(0.95, float(np.mean([float(point.get("confidence") or 0.0) for point in region]))),
                    3,
                ),
                "source": "raw_pitch_stability_no_quantization",
            }
        )
    return stable[:1200]


def _note_transitions_and_slides(
    stable_notes: list[dict[str, Any]],
    melody_curve: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    transitions: list[dict[str, Any]] = []
    slides: list[dict[str, Any]] = []
    if len(stable_notes) < 2:
        return transitions, slides
    step_seconds = _curve_step_seconds(melody_curve)
    for previous, current in zip(stable_notes, stable_notes[1:]):
        gap = float(current["start_seconds"]) - float(previous["end_seconds"])
        if gap > 2.5:
            continue
        delta = float(current["median_midi"]) - float(previous["median_midi"])
        if abs(delta) < 0.25:
            continue
        path_start = max(0.0, float(previous["end_seconds"]) - step_seconds * 1.5)
        path_end = float(current["start_seconds"]) + step_seconds * 1.5
        path = [
            point
            for point in melody_curve
            if point.get("voiced")
            and point.get("midi") is not None
            and path_start <= float(point.get("time_seconds") or 0.0) <= path_end
        ]
        differences = np.diff([float(point["midi"]) for point in path]) if len(path) >= 2 else np.zeros(0)
        path_time_differences = (
            np.diff([float(point["time_seconds"]) for point in path])
            if len(path) >= 2
            else np.zeros(0)
        )
        continuous_path = bool(
            path_time_differences.size
            and float(np.max(path_time_differences)) <= max(0.16, step_seconds * 2.7)
        )
        significant = differences[np.abs(differences) >= 0.04]
        if significant.size:
            directional_ratio = float(np.mean(np.sign(significant) == np.sign(delta)))
        else:
            directional_ratio = 0.0
        transition = {
            "start_seconds": round(float(previous["end_seconds"]), 3),
            "end_seconds": round(float(current["start_seconds"]), 3),
            "from_note": previous["nearest_note"],
            "to_note": current["nearest_note"],
            "semitones": round(delta, 3),
            "direction": "up" if delta > 0 else "down",
            "gap_seconds": round(max(0.0, gap), 3),
            "path_direction_agreement": round(directional_ratio, 3),
            "continuous_pitch_path": continuous_path,
            "source": "adjacent_stable_pitch_regions",
        }
        transitions.append(transition)
        path_duration = max(step_seconds, path_end - path_start)
        if abs(delta) >= 0.75 and path_duration <= 3.0 and directional_ratio >= 0.62 and continuous_path:
            slides.append(
                {
                    **transition,
                    "start_seconds": round(path_start, 3),
                    "end_seconds": round(path_end, 3),
                    "duration_seconds": round(path_duration, 3),
                    "smoothness": round(directional_ratio, 3),
                    "candidate": True,
                    "requires_confirmation": True,
                }
            )
    return transitions[:1200], slides[:600]


def _ornamentation_candidates(
    melody_curve: list[dict[str, Any]],
    pitch_slides: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ornaments: list[dict[str, Any]] = []
    for slide in pitch_slides:
        interval = abs(float(slide.get("semitones") or 0.0))
        if 0.9 <= interval <= 12.0:
            ornaments.append(
                {
                    "type": "possible_meend",
                    "start_seconds": slide["start_seconds"],
                    "end_seconds": slide["end_seconds"],
                    "semitones": slide["semitones"],
                    "direction": slide["direction"],
                    "confidence": round(min(0.82, 0.42 + 0.4 * float(slide.get("smoothness") or 0.0)), 3),
                    "source": "smooth_pitch_slide",
                    "candidate": True,
                    "requires_confirmation": True,
                }
            )

    voiced = [point for point in melody_curve if point.get("voiced") and point.get("midi") is not None]
    if len(voiced) < 7:
        return ornaments
    step_seconds = _curve_step_seconds(melody_curve)
    window_points = max(7, int(round(0.9 / max(0.01, step_seconds))))
    window_points = min(31, window_points)
    stride = max(3, window_points // 2)
    oscillations: list[dict[str, Any]] = []
    for start_index in range(0, max(1, len(voiced) - window_points + 1), stride):
        window = voiced[start_index : start_index + window_points]
        if len(window) < 7:
            continue
        times = np.asarray([float(point["time_seconds"]) for point in window], dtype=np.float64)
        if float(times[-1] - times[0]) > max(1.8, step_seconds * window_points * 1.8):
            continue
        pitches = np.asarray([float(point["midi"]) for point in window], dtype=np.float64)
        pitch_span = float(np.ptp(pitches))
        differences = np.diff(pitches)
        signs = np.sign(differences[np.abs(differences) >= 0.05])
        direction_changes = int(np.count_nonzero(signs[1:] != signs[:-1])) if signs.size >= 2 else 0
        if not (0.3 <= pitch_span <= 3.5 and direction_changes >= 3):
            continue
        ornament_type = "andolan_or_gamak_candidate" if pitch_span >= 0.8 else "vibrato_candidate"
        confidence = min(0.78, 0.35 + 0.06 * direction_changes + 0.05 * min(2.0, pitch_span))
        candidate = {
            "type": ornament_type,
            "start_seconds": round(float(times[0]), 3),
            "end_seconds": round(float(times[-1]), 3),
            "pitch_span_semitones": round(pitch_span, 3),
            "direction_changes": direction_changes,
            "confidence": round(confidence, 3),
            "source": "unquantized_pitch_oscillation",
            "candidate": True,
            "requires_confirmation": True,
        }
        if oscillations and candidate["start_seconds"] <= oscillations[-1]["end_seconds"]:
            if candidate["confidence"] > oscillations[-1]["confidence"]:
                oscillations[-1] = candidate
            else:
                oscillations[-1]["end_seconds"] = max(
                    oscillations[-1]["end_seconds"],
                    candidate["end_seconds"],
                )
        else:
            oscillations.append(candidate)
    return [*ornaments, *oscillations[:200]]


def _phrase_contour(
    phrase: dict[str, Any],
    melody_curve: list[dict[str, Any]],
    *,
    sample_points: int = 24,
) -> np.ndarray | None:
    start = float(phrase.get("start_seconds") or 0.0)
    end = float(phrase.get("end_seconds") or start)
    if end - start < 0.35:
        return None
    points = [
        point
        for point in melody_curve
        if point.get("voiced")
        and point.get("midi") is not None
        and start <= float(point.get("time_seconds") or 0.0) <= end
    ]
    if len(points) < 5:
        return None
    times = np.asarray([float(point["time_seconds"]) for point in points], dtype=np.float64)
    pitches = np.asarray([float(point["midi"]) for point in points], dtype=np.float64)
    unique_times, unique_indices = np.unique(times, return_index=True)
    if unique_times.size < 4:
        return None
    pitches = pitches[unique_indices]
    normalized_times = (unique_times - start) / max(1e-6, end - start)
    contour = np.interp(np.linspace(0.0, 1.0, sample_points), normalized_times, pitches)
    return contour - float(np.median(contour))


def _melodic_motifs(
    phrases: list[dict[str, Any]],
    melody_curve: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, str]]:
    contours: dict[int, np.ndarray] = {}
    phrase_by_number: dict[int, dict[str, Any]] = {}
    for phrase in phrases:
        number = int(phrase.get("phrase") or len(phrase_by_number) + 1)
        contour = _phrase_contour(phrase, melody_curve)
        if contour is not None:
            contours[number] = contour
            phrase_by_number[number] = phrase
    numbers = sorted(contours)
    parent = {number: number for number in numbers}
    pair_scores: dict[tuple[int, int], float] = {}

    def find(number: int) -> int:
        while parent[number] != number:
            parent[number] = parent[parent[number]]
            number = parent[number]
        return number

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index, left_number in enumerate(numbers):
        left_phrase = phrase_by_number[left_number]
        left_duration = float(left_phrase.get("duration_seconds") or 0.0)
        for right_number in numbers[left_index + 1 :]:
            right_phrase = phrase_by_number[right_number]
            right_duration = float(right_phrase.get("duration_seconds") or 0.0)
            duration_ratio = min(left_duration, right_duration) / max(1e-6, max(left_duration, right_duration))
            if duration_ratio < 0.55:
                continue
            left_contour, right_contour = contours[left_number], contours[right_number]
            left_std, right_std = float(np.std(left_contour)), float(np.std(right_contour))
            if left_std < 0.08 and right_std < 0.08:
                correlation = 1.0
            elif left_std < 0.08 or right_std < 0.08:
                correlation = 0.0
            else:
                correlation = float(np.corrcoef(left_contour, right_contour)[0, 1])
            mean_error = float(np.mean(np.abs(left_contour - right_contour)))
            score = 0.65 * max(0.0, (correlation + 1.0) / 2.0) + 0.35 * math.exp(-mean_error / 1.5)
            if correlation >= 0.78 and mean_error <= 1.35 and score >= 0.78:
                union(left_number, right_number)
                pair_scores[(left_number, right_number)] = score

    grouped: dict[int, list[int]] = {}
    for number in numbers:
        grouped.setdefault(find(number), []).append(number)
    motifs: list[dict[str, Any]] = []
    phrase_motif_ids: dict[int, str] = {}
    for members in sorted((items for items in grouped.values() if len(items) >= 2), key=lambda items: items[0]):
        motif_id = f"motif_{len(motifs) + 1}"
        scores = [
            score
            for pair, score in pair_scores.items()
            if pair[0] in members and pair[1] in members
        ]
        confidence = float(np.mean(scores)) if scores else 0.78
        occurrences = [
            {
                "phrase": number,
                "start_seconds": phrase_by_number[number]["start_seconds"],
                "end_seconds": phrase_by_number[number]["end_seconds"],
            }
            for number in members
        ]
        motifs.append(
            {
                "motif_id": motif_id,
                "phrase_numbers": members,
                "occurrences": occurrences,
                "occurrence_count": len(members),
                "confidence": round(min(0.95, confidence), 3),
                "chorus_like_candidate": True,
                "source": "transposition_invariant_phrase_pitch_contour",
                "requires_confirmation": True,
            }
        )
        for number in members:
            phrase_motif_ids[number] = motif_id
    return motifs[:100], phrase_motif_ids


def _onset_times(
    mono: np.ndarray,
    sample_rate: int,
    duration: float,
    activity: list[dict[str, Any]],
) -> tuple[list[float], str]:
    if mono.size and sample_rate > 0:
        try:
            import librosa

            values = librosa.onset.onset_detect(
                y=mono.astype(np.float32, copy=False),
                sr=sample_rate,
                units="time",
                backtrack=False,
            )
            times = sorted({round(float(value), 3) for value in np.ravel(values) if 0 <= float(value) <= duration})
            if len(times) > MAX_ONSET_MAP_POINTS:
                indices = np.linspace(0, len(times) - 1, MAX_ONSET_MAP_POINTS).round().astype(int)
                times = [times[int(index)] for index in np.unique(indices)]
            return times, "full_song_spectral_onsets"
        except Exception:
            pass
    fallback = sorted(
        {
            round(float(item.get("start_seconds") or 0.0), 3)
            for item in activity
            if 0 <= float(item.get("start_seconds") or 0.0) <= duration
        }
    )
    return fallback, "vocal_activity_starts_fallback"


def _fold_tempo(value: float) -> float:
    while value < 40.0:
        value *= 2.0
    while value > 220.0:
        value /= 2.0
    return value


def _enrich_phrases(
    phrases: list[dict[str, Any]],
    *,
    melody_curve: list[dict[str, Any]],
    stable_notes: list[dict[str, Any]],
    onset_times: list[float],
    tempo: SongTempoInfo,
    phrase_motif_ids: dict[int, str],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    beat_seconds = 60.0 / float(tempo.bpm) if tempo.bpm else None
    for item in phrases:
        phrase = dict(item)
        number = int(phrase.get("phrase") or len(enriched) + 1)
        start = float(phrase.get("start_seconds") or 0.0)
        end = float(phrase.get("end_seconds") or start)
        phrase_duration = max(1e-6, end - start)
        phrase_points = [
            point
            for point in melody_curve
            if start <= float(point.get("time_seconds") or 0.0) <= end
        ]
        voiced_points = [point for point in phrase_points if point.get("voiced") and point.get("midi") is not None]
        pitches = np.asarray([float(point["midi"]) for point in voiced_points], dtype=np.float64)
        pitch_span = float(np.percentile(pitches, 95) - np.percentile(pitches, 5)) if pitches.size >= 2 else 0.0
        voiced_ratio = len(voiced_points) / max(1, len(phrase_points))
        phrase_onsets = [value for value in onset_times if start <= value <= end]
        onset_density = len(phrase_onsets) / phrase_duration
        local_bpm: float | None = None
        if len(phrase_onsets) >= 3:
            intervals = np.diff(phrase_onsets)
            intervals = intervals[(intervals >= 0.12) & (intervals <= 2.5)]
            if intervals.size:
                local_bpm = _fold_tempo(60.0 / float(np.median(intervals)))
        overlapping_stable = [
            note
            for note in stable_notes
            if float(note["end_seconds"]) > start and float(note["start_seconds"]) < end
        ]

        if onset_density >= 2.4 and pitch_span <= 2.5 and voiced_ratio >= 0.15:
            delivery = "spoken_or_rap_candidate"
            delivery_confidence = 0.52
        elif voiced_ratio >= 0.25:
            delivery = "sung_candidate"
            delivery_confidence = min(0.62, 0.42 + voiced_ratio * 0.2)
        else:
            delivery = "unclassified_vocal"
            delivery_confidence = 0.25

        pickup_candidate = False
        pickup_offset: float | None = None
        if beat_seconds and tempo.confidence >= 0.35 and start > 0.0:
            phase = start % beat_seconds
            distance_to_next = 0.0 if phase <= 0.02 else beat_seconds - phase
            preceding_gap = float(phrase.get("preceding_gap_seconds") or 0.0)
            pickup_candidate = bool(
                preceding_gap >= 0.12
                and beat_seconds * 0.08 <= distance_to_next <= beat_seconds * 0.65
            )
            if pickup_candidate:
                pickup_offset = distance_to_next

        motif_id = phrase_motif_ids.get(number)
        phrase.update(
            {
                "delivery": delivery,
                "delivery_confidence": round(delivery_confidence, 3),
                "delivery_source": "phrase_pitch_and_onset_candidate",
                "delivery_requires_confirmation": True,
                "voiced_ratio": round(voiced_ratio, 3),
                "pitch_span_semitones": round(pitch_span, 3),
                "stable_note_count": len(overlapping_stable),
                "sustained_candidate": any(float(note["duration_seconds"]) >= 0.55 for note in overlapping_stable),
                "onset_count": len(phrase_onsets),
                "rhythmic_density_onsets_per_second": round(onset_density, 3),
                "relative_tempo_bpm": round(local_bpm, 2) if local_bpm else None,
                "relative_tempo_ratio": round(local_bpm / float(tempo.bpm), 3) if local_bpm and tempo.bpm else None,
                "pickup_candidate": pickup_candidate,
                "pickup_to_next_beat_seconds": round(pickup_offset, 3) if pickup_offset is not None else None,
                "motif_id": motif_id,
                "repeated_melody": bool(motif_id),
                "chorus_like_candidate": bool(motif_id),
            }
        )
        enriched.append(phrase)
    return enriched


def _enrich_sections(
    sections: list[dict[str, Any]],
    *,
    phrases: list[dict[str, Any]],
    energy_curve: list[dict[str, Any]],
    onset_times: list[float],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in sections:
        section = dict(item)
        start = float(section.get("start_seconds") or 0.0)
        end = float(section.get("end_seconds") or start)
        section_duration = max(1e-6, end - start)
        overlapping_phrases = [
            phrase
            for phrase in phrases
            if float(phrase.get("end_seconds") or 0.0) > start
            and float(phrase.get("start_seconds") or 0.0) < end
        ]
        energies = [
            float(point.get("relative_energy") or 0.0)
            for point in energy_curve
            if start <= float(point.get("time_seconds") or 0.0) <= end
        ]
        mean_energy = float(np.mean(energies)) if energies else 0.0
        section_onsets = [value for value in onset_times if start <= value < end]
        motif_ids = sorted(
            {
                str(phrase["motif_id"])
                for phrase in overlapping_phrases
                if phrase.get("motif_id")
            }
        )
        evidence = ["phrase_aligned_boundaries"] if section.get("source") == "phrase_aligned" else ["duration_prior"]
        if motif_ids:
            evidence.append("repeated_melodic_motif")
        if energies and (mean_energy >= 0.65 or mean_energy <= 0.25):
            evidence.append("energy_contrast")
        name = str(section.get("name") or "section")
        confidence = 0.52 if section.get("source") == "phrase_aligned" else 0.28
        if motif_ids and "hook" in name:
            confidence += 0.23
        elif motif_ids:
            confidence += 0.12
        section.update(
            {
                "phrase_numbers": [int(phrase.get("phrase") or 0) for phrase in overlapping_phrases],
                "motif_ids": motif_ids,
                "mean_relative_energy": round(mean_energy, 3),
                "rhythmic_density_onsets_per_second": round(len(section_onsets) / section_duration, 3),
                "chorus_like_candidate": bool(motif_ids),
                "label_confidence": round(min(0.85, confidence), 3),
                "label_evidence": evidence,
                "semantic_label_is_candidate": True,
            }
        )
        enriched.append(section)
    return enriched


def _rhythm_analysis(
    tempo: SongTempoInfo,
    phrases: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    onset_times: list[float],
    onset_source: str,
) -> dict[str, Any]:
    phrase_tempos = [
        {
            "phrase": phrase.get("phrase"),
            "bpm": phrase.get("relative_tempo_bpm"),
            "ratio_to_global": phrase.get("relative_tempo_ratio"),
            "onset_density": phrase.get("rhythmic_density_onsets_per_second"),
        }
        for phrase in phrases
    ]
    return {
        "source": onset_source,
        "onset_times": onset_times,
        "onset_count": len(onset_times),
        "beat_map_mode": "flexible" if tempo.rubato or tempo.confidence < 0.5 else "global_grid",
        "free_timing_recommended": bool(tempo.rubato or tempo.confidence < 0.5),
        "phrase_relative_tempo": phrase_tempos,
        "section_rhythmic_density": [
            {
                "section": section.get("name"),
                "start_seconds": section.get("start_seconds"),
                "end_seconds": section.get("end_seconds"),
                "onsets_per_second": section.get("rhythmic_density_onsets_per_second"),
            }
            for section in sections
        ],
    }


def _structure_analysis(
    sections: list[dict[str, Any]],
    phrases: list[dict[str, Any]],
    melodic_motifs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "method": "phrase_gaps_plus_melodic_repetition_plus_energy",
        "semantic_labels_are_candidates": True,
        "phrase_count": len(phrases),
        "phrase_aligned_boundary_count": sum(1 for section in sections if section.get("source") == "phrase_aligned"),
        "repeated_motif_count": len(melodic_motifs),
        "repetition_bearing_sections": [
            section.get("name")
            for section in sections
            if section.get("motif_ids")
        ],
        "hook_candidate_sections": [
            section.get("name")
            for section in sections
            if section.get("chorus_like_candidate")
            and "hook" in str(section.get("name") or "").lower()
        ],
    }


def _chord_compatibility(
    key_name: str,
    scale_name: str,
    melody_curve: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pitch_class_names = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
    aliases = {
        "DB": 1,
        "D#": 3,
        "GB": 6,
        "G#": 8,
        "A#": 10,
        **{name.upper(): index for index, name in enumerate(pitch_class_names)},
    }
    tonic = aliases.get(str(key_name or "A").strip().upper(), 9)
    scale_intervals = (0, 2, 4, 5, 7, 9, 11) if scale_name == "major" else (0, 2, 3, 5, 7, 8, 10)
    histogram = np.zeros(12, dtype=np.float64)
    for point in melody_curve:
        if point.get("voiced") and point.get("midi") is not None:
            histogram[int(round(float(point["midi"]))) % 12] += max(0.1, float(point.get("confidence") or 0.0))
    total = float(np.sum(histogram))
    scale_pitch_classes = {(tonic + interval) % 12 for interval in scale_intervals}
    scale_fit = float(np.sum(histogram[list(scale_pitch_classes)]) / total) if total > 0 else 0.5
    suggestions: list[dict[str, Any]] = []
    roman_major = ("I", "ii", "iii", "IV", "V", "vi", "vii°")
    roman_minor = ("i", "ii°", "III", "iv", "v", "VI", "VII")
    romans = roman_major if scale_name == "major" else roman_minor
    for degree in range(7):
        chord_intervals = [
            scale_intervals[degree],
            scale_intervals[(degree + 2) % 7] + (12 if degree + 2 >= 7 else 0),
            scale_intervals[(degree + 4) % 7] + (12 if degree + 4 >= 7 else 0),
        ]
        chord_pitch_classes = {(tonic + interval) % 12 for interval in chord_intervals}
        chord_fit = float(np.sum(histogram[list(chord_pitch_classes)]) / total) if total > 0 else 1.0 / 3.0
        root = (tonic + scale_intervals[degree]) % 12
        relative = sorted((pitch_class - root) % 12 for pitch_class in chord_pitch_classes)
        quality = "major" if relative == [0, 4, 7] else "minor" if relative == [0, 3, 7] else "diminished"
        suffix = "" if quality == "major" else "m" if quality == "minor" else "dim"
        compatibility = 0.68 * chord_fit + 0.32 * scale_fit
        suggestions.append(
            {
                "scale_degree": degree + 1,
                "roman_numeral": romans[degree],
                "chord": f"{pitch_class_names[root]}{suffix}",
                "quality": quality,
                "compatibility": round(max(0.0, min(1.0, compatibility)), 3),
                "source": "key_scale_and_vocal_pitch_class_fit",
                "planning_candidate_not_detected_progression": True,
            }
        )
    return suggestions


def _silence_regions(activity: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    if duration <= 0:
        return []
    regions: list[dict[str, Any]] = []
    cursor = 0.0
    intervals = sorted(activity, key=lambda item: float(item.get("start_seconds", 0)))
    for interval in intervals:
        start = max(cursor, float(interval.get("start_seconds", cursor)))
        if start - cursor >= 0.12:
            regions.append(_silence_region(cursor, start, duration))
        cursor = max(cursor, float(interval.get("end_seconds", start)))
    if duration - cursor >= 0.12:
        regions.append(_silence_region(cursor, duration, duration))
    return regions


def _silence_region(start: float, end: float, duration: float) -> dict[str, Any]:
    if start <= 0.05:
        kind = "intro_silence"
    elif end >= duration - 0.05:
        kind = "outro_silence"
    else:
        kind = "phrase_gap"
    return {
        "start_seconds": round(start, 3),
        "end_seconds": round(end, 3),
        "duration_seconds": round(end - start, 3),
        "type": kind,
    }


def _breath_regions(silence_regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    breaths: list[dict[str, Any]] = []
    for region in silence_regions:
        duration = float(region.get("duration_seconds") or 0)
        if region.get("type") != "phrase_gap" or not 0.18 <= duration <= 1.6:
            continue
        confidence = max(0.35, 1.0 - abs(duration - 0.55) / 1.4)
        breaths.append(
            {
                "start_seconds": region["start_seconds"],
                "end_seconds": region["end_seconds"],
                "duration_seconds": region["duration_seconds"],
                "confidence": round(min(0.9, confidence), 3),
                "source": "short_inter_phrase_gap",
            }
        )
    return breaths


def _section_candidates(duration: float, phrases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build an arrangement map that prefers real silent phrase gaps.

    Section names remain a planning convention, not a claim that the vocal
    alone can semantically recognise a chorus.  Their boundaries, however,
    should land between actual phrases wherever the full-song voice activity
    gives us a safe musical transition point.
    """
    if not duration or duration <= 0:
        return []
    if duration < 24:
        names = ["intro", "mukhda", "hook", "outro"]
        weights = [0.12, 0.43, 0.35, 0.10]
    else:
        names = ["intro", "mukhda", "hook", "antara", "final_hook", "outro"]
        weights = [0.10, 0.22, 0.20, 0.24, 0.18, 0.06]
    targets: list[float] = []
    cursor = 0.0
    for weight in weights[:-1]:
        cursor += duration * weight
        targets.append(cursor)
    boundaries, used_phrase_boundaries = _align_section_boundaries(duration, targets, phrases)
    cursor = 0.0
    sections: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        end = duration if index == len(names) - 1 else boundaries[index]
        boundary_is_phrase_aligned = (
            used_phrase_boundaries[index]
            if index < len(used_phrase_boundaries)
            else bool(used_phrase_boundaries and used_phrase_boundaries[-1])
        )
        sections.append(
            {
                "name": name,
                "start_seconds": round(cursor, 3),
                "end_seconds": round(end, 3),
                "source": "phrase_aligned" if boundary_is_phrase_aligned else "duration_fallback",
            }
        )
        cursor = end
    return sections


def _align_section_boundaries(
    duration: float,
    targets: list[float],
    phrases: list[dict[str, Any]],
) -> tuple[list[float], list[bool]]:
    """Choose ordered phrase-gap midpoints nearest to desired section lengths."""
    phrase_intervals: list[tuple[float, float]] = []
    for phrase in phrases:
        try:
            start = max(0.0, float(phrase.get("start_seconds", phrase.get("start", 0.0))))
            end = min(duration, float(phrase.get("end_seconds", phrase.get("end", start))))
        except (AttributeError, TypeError, ValueError):
            continue
        if end > start:
            phrase_intervals.append((start, end))
    phrase_intervals.sort()

    gap_points: list[float] = []
    if phrase_intervals and phrase_intervals[0][0] >= 0.25:
        gap_points.append(phrase_intervals[0][0])
    previous_end: float | None = None
    for start, end in phrase_intervals:
        if previous_end is not None and start - previous_end >= 0.20:
            gap_points.append((previous_end + start) / 2.0)
        previous_end = max(previous_end or end, end)
    if previous_end is not None and duration - previous_end >= 0.25:
        gap_points.append(previous_end)
    candidates = sorted({round(point, 4) for point in gap_points if 0 < point < duration})

    boundaries: list[float] = []
    used_phrase_boundaries: list[bool] = []
    minimum_section_seconds = max(2.0, duration * 0.04)
    previous_boundary = 0.0
    for index, target in enumerate(targets):
        remaining_sections = len(targets) - index
        minimum_end = previous_boundary + minimum_section_seconds
        maximum_end = duration - remaining_sections * minimum_section_seconds
        available = [
            point
            for point in candidates
            if minimum_end <= point <= maximum_end and point > previous_boundary
        ]
        if available:
            chosen = min(available, key=lambda point: abs(point - target))
            candidates.remove(chosen)
            used_phrase_boundaries.append(True)
        else:
            chosen = min(maximum_end, max(minimum_end, target))
            used_phrase_boundaries.append(False)
        boundaries.append(round(chosen, 3))
        previous_boundary = chosen
    return boundaries, used_phrase_boundaries


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result
