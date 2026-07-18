from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import math
import re
import wave

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_NAME = "procedural_v2"

NOTE_TO_SEMITONE = {
    "C": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
}
MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)


@dataclass(frozen=True)
class GenerationResult:
    success: bool
    output_path: str | None
    generator_name: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    error_message: str | None = None
    logs: list[str] | None = None
    suggested_fix: str | None = None


def generate_backing(
    job_id: str,
    output_dir: str | Path,
    duration_seconds: int,
    bpm: int,
    key: str | None,
    genre: str | None,
    production_style: str | None,
    arrangement_style: str | None,
    instruments: list[str],
    mood_tags: list[str],
    sample_rate: int = 44100,
) -> GenerationResult:
    started_at = _now()
    logs: list[str] = []
    output_path: Path | None = None

    try:
        resolved_output_dir = resolve_output_dir(output_dir)
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        output_path = resolved_output_dir / f"{_safe_name(job_id)}.wav"

        duration = int(duration_seconds or 90)
        duration = max(3, min(duration, 600))
        tempo = int(bpm or 88)
        tempo = max(40, min(tempo, 220))
        rate = int(sample_rate or 44100)
        if rate < 16000:
            rate = 44100

        seed = int(hashlib.sha256(job_id.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        family = _style_family(genre, production_style, arrangement_style, instruments, mood_tags)
        root_name, root_semitone, mode = parse_key(key)
        scale = build_scale(key)

        logs.append(f"procedural_v2 style={family} bpm={tempo} key={root_name} {mode} duration={duration}s")
        audio = _render_arrangement(
            duration_seconds=duration,
            sample_rate=rate,
            bpm=tempo,
            root_semitone=root_semitone,
            mode=mode,
            scale=scale,
            style_family=family,
            rng=rng,
        )
        audio = normalize_audio(audio)
        write_wav(output_path, audio, rate)
        logs.append(f"Wrote procedural fallback WAV: {output_path}")

        finished_at = _now()
        return GenerationResult(
            success=True,
            output_path=str(output_path),
            generator_name=GENERATOR_NAME,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=(finished_at - started_at).total_seconds(),
            logs=logs[-40:],
        )
    except Exception as exc:
        finished_at = _now()
        logs.append(f"procedural_v2 failed: {exc}")
        return GenerationResult(
            success=False,
            output_path=str(output_path) if output_path else None,
            generator_name=GENERATOR_NAME,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=(finished_at - started_at).total_seconds(),
            error_message=f"procedural_v2 fallback generation failed: {exc}",
            logs=logs[-40:],
            suggested_fix="Check PROCEDURAL_OUTPUT_DIR permissions and fallback synthesis settings.",
        )


def note_to_frequency(note_name: str) -> float:
    match = re.match(r"^\s*([A-Ga-g])([#bB]?)(-?\d+)?\s*$", note_name or "")
    if not match:
        raise ValueError(f"Invalid note name: {note_name!r}")
    note = match.group(1).upper()
    accidental = match.group(2).replace("b", "B").upper()
    octave = int(match.group(3) if match.group(3) is not None else 4)
    semitone = NOTE_TO_SEMITONE[f"{note}{accidental}"]
    midi = (octave + 1) * 12 + semitone
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def parse_key(key: str | None) -> tuple[str, int, str]:
    text = (key or "").strip()
    if not text:
        return "A", NOTE_TO_SEMITONE["A"], "minor"

    match = re.search(r"([A-Ga-g])\s*([#bB]?)(?:\s*(major|minor|maj|min|m)\b)?", text)
    if not match:
        return "A", NOTE_TO_SEMITONE["A"], "minor"

    note = match.group(1).upper()
    accidental = match.group(2).replace("b", "B").upper()
    root = f"{note}{accidental}"
    display_root = f"{note}{'#' if accidental == '#' else 'b' if accidental == 'B' else ''}"
    mode_token = (match.group(3) or "").lower()
    lowered = text.lower()
    if mode_token in {"major", "maj"} or "major" in lowered:
        mode = "major"
    elif mode_token in {"minor", "min", "m"} or "minor" in lowered:
        mode = "minor"
    else:
        mode = "minor"
    return display_root, NOTE_TO_SEMITONE[root], mode


def build_scale(key: str | None) -> list[int]:
    _root_name, root_semitone, mode = parse_key(key)
    intervals = MAJOR_SCALE if mode == "major" else MINOR_SCALE
    return [(root_semitone + interval) % 12 for interval in intervals]


def chord_progression_for_style(style: str, key: str | None) -> list[int]:
    _root_name, _root_semitone, mode = parse_key(key)
    family = _normalize_text(style)
    if "qawwali" in family or "bhajan" in family or "devotional" in family:
        return [1, 4, 5, 1] if mode == "major" else [1, 6, 4, 5]
    if "trap" in family or "lofi" in family or "lo-fi" in family:
        return [1, 7, 6, 7] if mode == "minor" else [1, 6, 4, 5]
    if "sufi" in family or "rock" in family:
        return [1, 6, 7, 5] if mode == "minor" else [1, 5, 6, 4]
    if "acoustic" in family:
        return [1, 5, 6, 4]
    return [1, 6, 4, 5] if mode == "minor" else [1, 5, 6, 4]


def envelope(
    length: int,
    sample_rate: int,
    attack: float = 0.01,
    decay: float = 0.08,
    sustain: float = 0.7,
    release: float = 0.12,
) -> np.ndarray:
    total = max(1, int(length))
    env = np.ones(total, dtype=np.float32) * float(sustain)
    attack_frames = max(0, int(attack * sample_rate))
    decay_frames = max(0, int(decay * sample_rate))
    release_frames = max(0, int(release * sample_rate))
    envelope_frames = attack_frames + decay_frames + release_frames
    if envelope_frames > total:
        ratio = total / float(envelope_frames)
        attack_frames = int(attack_frames * ratio)
        decay_frames = int(decay_frames * ratio)
        release_frames = max(0, total - attack_frames - decay_frames)

    cursor = 0
    if attack_frames:
        env[:attack_frames] = np.linspace(0.0, 1.0, attack_frames, endpoint=False, dtype=np.float32)
        cursor += attack_frames
    if decay_frames:
        env[cursor : cursor + decay_frames] = np.linspace(1.0, sustain, decay_frames, dtype=np.float32)
        cursor += decay_frames
    if release_frames:
        env[-release_frames:] *= np.linspace(1.0, 0.0, release_frames, dtype=np.float32)
    return env


def normalize_audio(audio: np.ndarray, target_peak: float = 0.74) -> np.ndarray:
    rendered = np.asarray(audio, dtype=np.float32)
    if rendered.size == 0:
        return rendered
    rendered = rendered - np.mean(rendered, axis=0, keepdims=True)
    peak = float(np.max(np.abs(rendered)))
    if peak <= 1e-9:
        return rendered
    if peak > target_peak:
        rendered = rendered * (target_peak / peak)
    elif peak < 0.22:
        rendered = rendered * min(target_peak / peak, 2.5)
    fade_frames = min(int(0.03 * 44100), max(1, len(rendered) // 12))
    fade = np.linspace(0.0, 1.0, fade_frames, dtype=np.float32)
    rendered[:fade_frames] *= fade[:, None]
    rendered[-fade_frames:] *= fade[::-1, None]
    return np.clip(rendered, -0.9, 0.9).astype(np.float32)


def write_wav(path: str | Path, audio: np.ndarray, sample_rate: int) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    stereo = np.asarray(audio, dtype=np.float32)
    if stereo.ndim == 1:
        stereo = np.column_stack([stereo, stereo])
    if stereo.shape[1] == 1:
        stereo = np.repeat(stereo, 2, axis=1)
    pcm = (np.clip(stereo, -0.95, 0.95) * 32767.0).astype("<i2")
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm.tobytes())


def resolve_output_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()


def _render_arrangement(
    *,
    duration_seconds: int,
    sample_rate: int,
    bpm: int,
    root_semitone: int,
    mode: str,
    scale: list[int],
    style_family: str,
    rng: np.random.Generator,
) -> np.ndarray:
    frames = int(duration_seconds * sample_rate)
    audio = np.zeros((frames, 2), dtype=np.float32)
    beat = 60.0 / bpm
    bar = beat * 4.0
    bars = max(1, int(math.ceil(duration_seconds / bar)))
    progression = chord_progression_for_style(style_family, None if mode == "minor" else "C major")

    _add_chord_pad(audio, progression, bars, bar, sample_rate, root_semitone, mode, style_family)
    _add_bass(audio, progression, bars, beat, bar, sample_rate, root_semitone, mode, style_family)
    _add_drums(audio, duration_seconds, beat, sample_rate, style_family, rng)

    if style_family in {"bollywood_ballad", "lofi", "acoustic", "sufi_rock", "default"}:
        _add_motif(audio, progression, bars, beat, bar, sample_rate, root_semitone, mode, style_family)
    if style_family in {"qawwali", "bhajan"}:
        _add_drone(audio, duration_seconds, sample_rate, root_semitone, style_family)
        _add_harmonium_pulses(audio, progression, bars, beat, bar, sample_rate, root_semitone, mode)
    if style_family == "lofi":
        _add_lofi_texture(audio, sample_rate, rng)
    if style_family == "trap_soul":
        _add_trap_hats(audio, duration_seconds, beat, sample_rate, rng)

    return audio


def _add_chord_pad(
    audio: np.ndarray,
    progression: list[int],
    bars: int,
    bar_duration: float,
    sample_rate: int,
    root_semitone: int,
    mode: str,
    style_family: str,
) -> None:
    waveform = {
        "lofi": "electric",
        "qawwali": "harmonium",
        "bhajan": "harmonium",
        "trap_soul": "pad",
        "acoustic": "pluck",
    }.get(style_family, "pad")
    gain = {
        "trap_soul": 0.07,
        "sufi_rock": 0.12,
        "qawwali": 0.11,
        "bhajan": 0.1,
    }.get(style_family, 0.095)

    for bar_index in range(bars):
        start = int(bar_index * bar_duration * sample_rate)
        duration = min(bar_duration * 1.08, len(audio) / sample_rate - bar_index * bar_duration)
        if duration <= 0:
            continue
        chord = _chord_frequencies(progression[bar_index % len(progression)], root_semitone, mode, octave=3)
        for note_index, frequency in enumerate(chord):
            detune = 1.0 + (note_index - 1) * 0.0018
            tone = _tone(frequency * detune, duration, sample_rate, waveform)
            if waveform == "pad":
                tone *= envelope(len(tone), sample_rate, attack=0.25, decay=0.25, sustain=0.82, release=0.4)
            elif waveform == "harmonium":
                tone *= envelope(len(tone), sample_rate, attack=0.08, decay=0.12, sustain=0.78, release=0.22)
            elif waveform == "pluck":
                tone *= envelope(len(tone), sample_rate, attack=0.006, decay=0.18, sustain=0.18, release=0.18)
            else:
                tone *= envelope(len(tone), sample_rate, attack=0.04, decay=0.14, sustain=0.58, release=0.24)
            _add_mono(audio, tone, start, gain / max(1, len(chord)), pan=(note_index - 1) * 0.28)


def _add_bass(
    audio: np.ndarray,
    progression: list[int],
    bars: int,
    beat_duration: float,
    bar_duration: float,
    sample_rate: int,
    root_semitone: int,
    mode: str,
    style_family: str,
) -> None:
    gain = 0.13 if style_family in {"trap_soul", "lofi"} else 0.095
    for bar_index in range(bars):
        degree = progression[bar_index % len(progression)]
        root = _degree_frequency(degree, root_semitone, mode, octave=2)
        starts = (0.0, 2.0) if style_family != "trap_soul" else (0.0, 1.5, 2.75)
        for beat_offset in starts:
            start = int((bar_index * bar_duration + beat_offset * beat_duration) * sample_rate)
            duration = beat_duration * (1.8 if style_family == "trap_soul" else 0.86)
            if start >= len(audio):
                continue
            wave_kind = "sub" if style_family in {"trap_soul", "lofi"} else "bass"
            tone = _tone(root, duration, sample_rate, wave_kind)
            release = 0.36 if style_family == "trap_soul" else 0.12
            tone *= envelope(len(tone), sample_rate, attack=0.006, decay=0.08, sustain=0.55, release=release)
            _add_mono(audio, tone, start, gain, pan=0.0)


def _add_drums(
    audio: np.ndarray,
    duration_seconds: int,
    beat_duration: float,
    sample_rate: int,
    style_family: str,
    rng: np.random.Generator,
) -> None:
    total_beats = int(math.ceil(duration_seconds / beat_duration))
    kick_gain = 0.13 if style_family in {"sufi_rock", "trap_soul"} else 0.1
    snare_gain = 0.11 if style_family == "sufi_rock" else 0.075
    hat_gain = 0.028 if style_family != "bhajan" else 0.012

    for beat_index in range(total_beats):
        beat_in_bar = beat_index % 4
        start = int(beat_index * beat_duration * sample_rate)
        if beat_in_bar in {0, 2}:
            _add_mono(audio, _kick(sample_rate), start, kick_gain, pan=0.0)
        if beat_in_bar in {1, 3}:
            if style_family in {"qawwali", "bhajan"}:
                _add_mono(audio, _tabla(sample_rate), start, 0.07, pan=-0.08)
            else:
                _add_mono(audio, _snare(sample_rate, rng), start, snare_gain, pan=0.06)
        if style_family not in {"qawwali", "bhajan"}:
            for subdivision in (0.0, 0.5):
                hat_start = int((beat_index * beat_duration + subdivision * beat_duration) * sample_rate)
                _add_mono(audio, _hat(sample_rate, rng), hat_start, hat_gain, pan=-0.22 if subdivision == 0 else 0.22)

    if style_family == "qawwali":
        for beat_index in range(1, total_beats, 2):
            start = int(beat_index * beat_duration * sample_rate)
            _add_mono(audio, _clap(sample_rate, rng), start, 0.095, pan=0.18)
    if style_family == "bhajan":
        for beat_index in range(total_beats):
            start = int((beat_index + 0.5) * beat_duration * sample_rate)
            _add_mono(audio, _tabla(sample_rate, high=True), start, 0.04, pan=0.18)


def _add_motif(
    audio: np.ndarray,
    progression: list[int],
    bars: int,
    beat_duration: float,
    bar_duration: float,
    sample_rate: int,
    root_semitone: int,
    mode: str,
    style_family: str,
) -> None:
    waveform = "electric" if style_family == "lofi" else "pluck" if style_family in {"acoustic", "sufi_rock"} else "piano"
    gain = 0.055 if style_family != "sufi_rock" else 0.045
    step = beat_duration / 2.0
    for bar_index in range(bars):
        chord = _chord_frequencies(progression[bar_index % len(progression)], root_semitone, mode, octave=4)
        pattern = [chord[0], chord[1], chord[2], chord[1], chord[2], chord[1], chord[0] * 2.0, chord[1]]
        for note_index, frequency in enumerate(pattern):
            start_time = bar_index * bar_duration + note_index * step
            if start_time >= len(audio) / sample_rate:
                break
            tone = _tone(frequency, min(step * 0.82, 0.45), sample_rate, waveform)
            tone *= envelope(len(tone), sample_rate, attack=0.004, decay=0.12, sustain=0.24, release=0.15)
            _add_mono(audio, tone, int(start_time * sample_rate), gain, pan=-0.14 if note_index % 2 == 0 else 0.14)


def _add_drone(audio: np.ndarray, duration_seconds: int, sample_rate: int, root_semitone: int, style_family: str) -> None:
    root = _semitone_frequency(root_semitone, 3)
    fifth = _semitone_frequency((root_semitone + 7) % 12, 3)
    duration = len(audio) / sample_rate
    gain = 0.055 if style_family == "bhajan" else 0.045
    for frequency, pan in ((root, -0.24), (fifth, 0.24), (root * 2.0, 0.0)):
        tone = _tone(frequency, duration, sample_rate, "drone")
        tone *= envelope(len(tone), sample_rate, attack=0.4, decay=0.2, sustain=0.9, release=0.5)
        _add_mono(audio, tone, 0, gain, pan=pan)


def _add_harmonium_pulses(
    audio: np.ndarray,
    progression: list[int],
    bars: int,
    beat_duration: float,
    bar_duration: float,
    sample_rate: int,
    root_semitone: int,
    mode: str,
) -> None:
    for bar_index in range(bars):
        chord = _chord_frequencies(progression[bar_index % len(progression)], root_semitone, mode, octave=3)
        for beat_index in (0, 1, 2, 3):
            start = int((bar_index * bar_duration + beat_index * beat_duration) * sample_rate)
            for frequency in chord:
                tone = _tone(frequency, beat_duration * 0.75, sample_rate, "harmonium")
                tone *= envelope(len(tone), sample_rate, attack=0.03, decay=0.1, sustain=0.5, release=0.18)
                _add_mono(audio, tone, start, 0.018, pan=0.0)


def _add_lofi_texture(audio: np.ndarray, sample_rate: int, rng: np.random.Generator) -> None:
    noise = rng.normal(0.0, 1.0, len(audio)).astype(np.float32)
    smoothed = np.convolve(noise, np.ones(64, dtype=np.float32) / 64.0, mode="same")
    wobble = 0.5 + 0.5 * np.sin(2.0 * np.pi * 0.19 * np.arange(len(audio)) / sample_rate)
    _add_mono(audio, smoothed * wobble.astype(np.float32), 0, 0.012, pan=0.0)


def _add_trap_hats(
    audio: np.ndarray,
    duration_seconds: int,
    beat_duration: float,
    sample_rate: int,
    rng: np.random.Generator,
) -> None:
    step = beat_duration / 4.0
    total_steps = int(math.ceil(duration_seconds / step))
    for step_index in range(total_steps):
        if step_index % 4 in {1, 3} or step_index % 16 in {10, 11}:
            start = int(step_index * step * sample_rate)
            _add_mono(audio, _hat(sample_rate, rng, length=0.045), start, 0.026, pan=-0.28 if step_index % 2 else 0.28)


def _tone(frequency: float, seconds: float, sample_rate: int, kind: str) -> np.ndarray:
    length = max(1, int(seconds * sample_rate))
    t = np.arange(length, dtype=np.float32) / float(sample_rate)
    phase = 2.0 * np.pi * float(frequency) * t
    if kind == "pad":
        return (0.72 * np.sin(phase) + 0.18 * _triangle(phase * 0.998) + 0.1 * np.sin(phase * 2.01)).astype(np.float32)
    if kind == "harmonium":
        return (0.56 * np.sin(phase) + 0.24 * _triangle(phase) + 0.12 * np.sin(2.0 * phase) + 0.08 * np.sin(3.0 * phase)).astype(np.float32)
    if kind == "electric":
        return (0.68 * np.sin(phase) + 0.22 * np.sin(2.0 * phase) + 0.1 * np.sin(3.0 * phase)).astype(np.float32)
    if kind == "piano":
        return (0.78 * np.sin(phase) + 0.16 * np.sin(2.0 * phase) + 0.06 * np.sin(4.0 * phase)).astype(np.float32)
    if kind == "pluck":
        return (0.65 * np.sin(phase) + 0.22 * np.sin(2.0 * phase) + 0.13 * _triangle(phase * 1.005)).astype(np.float32)
    if kind == "bass":
        return (0.8 * np.sin(phase) + 0.2 * np.sin(2.0 * phase)).astype(np.float32)
    if kind == "sub":
        return (0.92 * np.sin(phase) + 0.08 * np.sin(2.0 * phase)).astype(np.float32)
    if kind == "drone":
        return (0.7 * np.sin(phase) + 0.2 * _triangle(phase) + 0.1 * np.sin(phase * 1.5)).astype(np.float32)
    return np.sin(phase).astype(np.float32)


def _triangle(phase: np.ndarray) -> np.ndarray:
    return (2.0 / np.pi * np.arcsin(np.sin(phase))).astype(np.float32)


def _kick(sample_rate: int) -> np.ndarray:
    length = int(0.34 * sample_rate)
    t = np.arange(length, dtype=np.float32) / sample_rate
    frequency = 48.0 + 58.0 * np.exp(-t * 24.0)
    phase = 2.0 * np.pi * np.cumsum(frequency) / sample_rate
    return (np.sin(phase) * np.exp(-t * 9.2)).astype(np.float32)


def _snare(sample_rate: int, rng: np.random.Generator) -> np.ndarray:
    length = int(0.22 * sample_rate)
    t = np.arange(length, dtype=np.float32) / sample_rate
    noise = rng.normal(0.0, 1.0, length).astype(np.float32)
    noise = noise - np.roll(noise, 1)
    tone = 0.35 * np.sin(2.0 * np.pi * 190.0 * t)
    return (0.72 * noise + tone).astype(np.float32) * np.exp(-t * 17.0)


def _hat(sample_rate: int, rng: np.random.Generator, length: float = 0.075) -> np.ndarray:
    frames = int(length * sample_rate)
    t = np.arange(frames, dtype=np.float32) / sample_rate
    noise = rng.normal(0.0, 1.0, frames).astype(np.float32)
    noise = noise - np.roll(noise, 1)
    return (noise * np.exp(-t * 55.0)).astype(np.float32)


def _clap(sample_rate: int, rng: np.random.Generator) -> np.ndarray:
    length = int(0.24 * sample_rate)
    t = np.arange(length, dtype=np.float32) / sample_rate
    noise = rng.normal(0.0, 1.0, length).astype(np.float32)
    bursts = (
        np.exp(-((t - 0.01) ** 2) / 0.00005)
        + np.exp(-((t - 0.04) ** 2) / 0.00008)
        + np.exp(-((t - 0.075) ** 2) / 0.00013)
    )
    return (noise * bursts * np.exp(-t * 5.5)).astype(np.float32)


def _tabla(sample_rate: int, high: bool = False) -> np.ndarray:
    length = int((0.18 if high else 0.26) * sample_rate)
    t = np.arange(length, dtype=np.float32) / sample_rate
    frequency = 210.0 if high else 115.0
    tone = np.sin(2.0 * np.pi * frequency * t) + 0.4 * np.sin(2.0 * np.pi * frequency * 1.7 * t)
    return (tone * np.exp(-t * (22.0 if high else 12.0))).astype(np.float32)


def _add_mono(audio: np.ndarray, mono: np.ndarray, start_frame: int, gain: float, pan: float = 0.0) -> None:
    if start_frame >= len(audio) or len(mono) == 0:
        return
    start = max(0, int(start_frame))
    end = min(len(audio), start + len(mono))
    segment = np.asarray(mono[: end - start], dtype=np.float32) * float(gain)
    angle = (float(np.clip(pan, -1.0, 1.0)) + 1.0) * math.pi / 4.0
    left = math.cos(angle)
    right = math.sin(angle)
    audio[start:end, 0] += segment * left
    audio[start:end, 1] += segment * right


def _chord_frequencies(degree: int, root_semitone: int, mode: str, octave: int) -> list[float]:
    return [
        _degree_frequency(degree, root_semitone, mode, octave),
        _degree_frequency(degree + 2, root_semitone, mode, octave),
        _degree_frequency(degree + 4, root_semitone, mode, octave),
    ]


def _degree_frequency(degree: int, root_semitone: int, mode: str, octave: int) -> float:
    intervals = MAJOR_SCALE if mode == "major" else MINOR_SCALE
    zero_based = degree - 1
    octave_shift, scale_index = divmod(zero_based, 7)
    semitone = root_semitone + intervals[scale_index]
    return _semitone_frequency(semitone % 12, octave + octave_shift + semitone // 12)


def _semitone_frequency(semitone: int, octave: int) -> float:
    midi = (octave + 1) * 12 + semitone
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def _style_family(
    genre: str | None,
    production_style: str | None,
    arrangement_style: str | None,
    instruments: list[str],
    mood_tags: list[str],
) -> str:
    text = _normalize_text(" ".join([genre or "", production_style or "", arrangement_style or "", *instruments, *mood_tags]))
    if "qawwali" in text:
        return "qawwali"
    if "bhajan" in text or "devotional" in text:
        return "bhajan"
    if "trap" in text or "808" in text:
        return "trap_soul"
    if "lo-fi" in text or "lofi" in text or "lo fi" in text:
        return "lofi"
    if "acoustic" in text or "unplugged" in text:
        return "acoustic"
    if "sufi" in text and "rock" in text:
        return "sufi_rock"
    if "bollywood" in text or "piano-led" in text or "piano led" in text or "cinematic" in text:
        return "bollywood_ballad"
    return "default"


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)[:120] or "procedural_v2_output"


def _now() -> datetime:
    return datetime.now(timezone.utc)
