import math
import wave
from pathlib import Path

import numpy as np

from app.audio_validation import validate_audio_file


def write_wav(path: Path, samples: np.ndarray, sample_rate: int = 22050) -> Path:
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path


def sine_wave(seconds: float, sample_rate: int = 22050, amplitude: float = 0.5) -> np.ndarray:
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    return amplitude * np.sin(2 * math.pi * 440 * t)


def test_missing_file_fails():
    report = validate_audio_file("missing.wav", generator_name="ACE-Step")

    assert report.passed is False
    assert report.audio_exists is False
    assert "Generated audio file does not exist." in report.warnings


def test_valid_sine_wave_passes(tmp_path):
    path = write_wav(tmp_path / "valid.wav", sine_wave(4.0))

    report = validate_audio_file(path, expected_duration_seconds=4, generator_name="ACE-Step")

    assert report.passed is True
    assert report.audio_exists is True
    assert report.duration_seconds is not None
    assert report.peak_db is not None
    assert report.is_silent is False
    assert report.sample_rate == 22050
    assert report.channels == 1


def test_silent_wav_fails(tmp_path):
    path = write_wav(tmp_path / "silent.wav", np.zeros(22050 * 4, dtype=np.float32))

    report = validate_audio_file(path, expected_duration_seconds=4, generator_name="ACE-Step")

    assert report.passed is False
    assert report.is_silent is True
    assert any("silent" in warning.lower() for warning in report.warnings)


def test_tiny_invalid_file_fails(tmp_path):
    path = tmp_path / "tiny.wav"
    path.write_bytes(b"bad")

    report = validate_audio_file(path, generator_name="ACE-Step")

    assert report.passed is False
    assert report.audio_exists is True
    assert any("too small" in warning.lower() or "decoded" in warning.lower() for warning in report.warnings)


def test_clipped_wav_warns_and_fails(tmp_path):
    path = write_wav(tmp_path / "clipped.wav", np.ones(22050 * 4, dtype=np.float32))

    report = validate_audio_file(path, expected_duration_seconds=4, generator_name="ACE-Step")

    assert report.passed is False
    assert report.clipping_detected is True
    assert any("clipping" in warning.lower() for warning in report.warnings)


def test_duration_mismatch_warns_and_fails_when_extremely_short(tmp_path):
    path = write_wav(tmp_path / "short.wav", sine_wave(2.0))

    report = validate_audio_file(path, expected_duration_seconds=90, generator_name="ACE-Step")

    assert report.passed is False
    assert report.duration_seconds is not None
    assert any("short" in warning.lower() for warning in report.warnings)
