import math
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.models import StemSeparationResponse
from app.services import music_transform_quality
from app.services.music_transform_quality import assess_transformation


def write_wav(path: Path, frequency: float, seconds: float = 3.0, sample_rate: int = 22050) -> Path:
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    samples = 0.3 * np.sin(2 * math.pi * frequency * t)
    pcm = (samples * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path


def test_distinct_audio_passes_originality_and_duration(tmp_path):
    source = write_wav(tmp_path / "source.wav", 220)
    output = write_wav(tmp_path / "output.wav", 337)
    settings = SimpleNamespace(music_to_music_verify_generated_vocals=False)

    report = assess_transformation(
        source_audio_path=str(source),
        output_audio_path=str(output),
        expected_duration_seconds=3,
        candidate_id="candidate",
        settings=settings,
        url_for_path=lambda value: value,
    )

    assert report.hashes_differ is True
    assert report.original_enough is True
    assert report.duration_match is True
    assert report.passed is True


def test_identical_audio_fails_originality_gate(tmp_path):
    source = write_wav(tmp_path / "source.wav", 220)
    settings = SimpleNamespace(music_to_music_verify_generated_vocals=False)

    report = assess_transformation(
        source_audio_path=str(source),
        output_audio_path=str(source),
        expected_duration_seconds=3,
        candidate_id="candidate",
        settings=settings,
        url_for_path=lambda value: value,
    )

    assert report.hashes_differ is False
    assert report.original_enough is False
    assert report.passed is False


def test_generated_vocal_leakage_fails_quality_gate(monkeypatch, tmp_path):
    source = write_wav(tmp_path / "source.wav", 220)
    output = write_wav(tmp_path / "output.wav", 337)
    vocal = write_wav(tmp_path / "detected-vocal.wav", 440)
    monkeypatch.setattr(
        music_transform_quality.stems_service,
        "separate_stems",
        lambda **_kwargs: StemSeparationResponse(
            status="completed",
            engine="demucs",
            stem_paths={"vocals": str(vocal), "no_vocals": str(output)},
        ),
    )
    settings = SimpleNamespace(
        music_to_music_verify_generated_vocals=True,
        music_to_music_vocal_threshold_db=-24.0,
        music_to_music_min_vocal_activity=0.04,
        stems_output_dir=str(tmp_path / "stems"),
        stems_engine="demucs",
        stems_timeout_seconds=30,
        stems_enabled=True,
        demucs_cli_path="fake-demucs",
    )

    report = assess_transformation(
        source_audio_path=str(source),
        output_audio_path=str(output),
        expected_duration_seconds=3,
        candidate_id="candidate",
        settings=settings,
        url_for_path=lambda value: value,
    )

    assert report.vocal_check_status == "leakage_detected"
    assert report.vocal_leakage_detected is True
    assert report.passed is False


def test_full_song_guide_vocal_is_removed_before_original_singer_mix(monkeypatch, tmp_path):
    source = write_wav(tmp_path / "source-vocal.wav", 220)
    raw_output = write_wav(tmp_path / "raw-output.wav", 337)
    detected_vocal = write_wav(tmp_path / "generated-vocal.wav", 440)
    clean_instrumental = write_wav(tmp_path / "clean-instrumental.wav", 523.25)
    clean_hash = music_transform_quality._sha256(str(clean_instrumental))
    monkeypatch.setattr(
        music_transform_quality.stems_service,
        "separate_stems",
        lambda **_kwargs: StemSeparationResponse(
            status="completed",
            engine="demucs",
            stem_paths={"vocals": str(detected_vocal), "no_vocals": str(clean_instrumental)},
        ),
    )
    settings = SimpleNamespace(
        music_to_music_verify_generated_vocals=True,
        music_to_music_clean_generated_vocals=True,
        music_to_music_vocal_threshold_db=-24.0,
        music_to_music_min_vocal_activity=0.04,
        stems_output_dir=str(tmp_path / "stems"),
        stems_engine="demucs",
        stems_timeout_seconds=30,
        stems_enabled=True,
        demucs_cli_path="fake-demucs",
    )

    report = assess_transformation(
        source_audio_path=str(source),
        output_audio_path=str(raw_output),
        expected_duration_seconds=3,
        candidate_id="candidate",
        settings=settings,
        url_for_path=lambda value: value,
    )

    assert report.vocal_check_status == "removed"
    assert report.vocal_leakage_detected is False
    assert report.passed is True
    assert music_transform_quality._sha256(str(raw_output)) == clean_hash
    assert any("guide-vocal material was removed" in warning for warning in report.warnings)
