import math
import wave
from pathlib import Path

import numpy as np

from app.audio_validation import validate_audio_file
from app.mixer import mix_vocal_with_backing


def write_wav(path: Path, seconds: float = 4.0, frequency: float = 440.0, amplitude: float = 0.35, sample_rate: int = 22050) -> Path:
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    samples = amplitude * np.sin(2 * math.pi * frequency * t)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path


def mix_pair(tmp_path: Path, vocal_seconds: float = 4.0, backing_seconds: float = 4.0, **kwargs):
    vocal = write_wav(tmp_path / "vocal.wav", seconds=vocal_seconds, frequency=330.0, amplitude=0.32)
    backing = write_wav(tmp_path / "backing.wav", seconds=backing_seconds, frequency=110.0, amplitude=0.28)
    return mix_vocal_with_backing(
        vocal_path=vocal,
        backing_path=backing,
        output_dir=tmp_path / "mixes",
        job_id="job_mix",
        output_format="wav",
        sample_rate=22050,
        **kwargs,
    )


def test_mix_valid_vocal_and_backing(tmp_path):
    result = mix_pair(tmp_path)

    assert result.success is True
    assert result.final_wav_path is not None
    assert Path(result.final_wav_path).exists()
    report = validate_audio_file(result.preview_path, expected_duration_seconds=4, generator_name="vocal_backing_mixer")
    assert report.passed is True
    assert report.duration_seconds is not None


def test_missing_vocal_file_returns_clear_failure(tmp_path):
    backing = write_wav(tmp_path / "backing.wav")

    result = mix_vocal_with_backing(
        vocal_path=tmp_path / "missing.wav",
        backing_path=backing,
        output_dir=tmp_path / "mixes",
        job_id="missing_vocal",
        output_format="wav",
        sample_rate=22050,
    )

    assert result.success is False
    assert "Vocal audio file does not exist" in result.error_message
    assert "Upload a valid vocal audio file" in result.suggested_fix


def test_missing_backing_file_returns_clear_failure(tmp_path):
    vocal = write_wav(tmp_path / "vocal.wav")

    result = mix_vocal_with_backing(
        vocal_path=vocal,
        backing_path=tmp_path / "missing.wav",
        output_dir=tmp_path / "mixes",
        job_id="missing_backing",
        output_format="wav",
        sample_rate=22050,
    )

    assert result.success is False
    assert "Backing audio file does not exist" in result.error_message
    assert "Generate backing audio first" in result.suggested_fix


def test_ducking_enabled_outputs_valid_non_clipped_mix(tmp_path):
    result = mix_pair(tmp_path, ducking_enabled=True, ducking_amount=0.5)

    report = validate_audio_file(result.preview_path, expected_duration_seconds=4, generator_name="vocal_backing_mixer")
    assert result.success is True
    assert report.passed is True
    assert report.clipping_detected is False


def test_vocal_shorter_than_backing_matches_backing_duration(tmp_path):
    result = mix_pair(tmp_path, vocal_seconds=2.0, backing_seconds=5.0)

    report = validate_audio_file(result.preview_path, expected_duration_seconds=5, generator_name="vocal_backing_mixer")
    assert result.success is True
    assert report.passed is True
    assert report.duration_seconds is not None
    assert 4.8 <= report.duration_seconds <= 5.2


def test_vocal_gain_keeps_mix_valid_without_clipping(tmp_path):
    result = mix_pair(tmp_path, vocal_gain_db=8.0, backing_gain_db=-4.0)

    report = validate_audio_file(result.preview_path, expected_duration_seconds=4, generator_name="vocal_backing_mixer")
    assert result.success is True
    assert report.passed is True
    assert report.clipping_detected is False
