import math
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.models import StemSeparationResponse
from app.services import music_source


def write_wav(path: Path, *, frequency: float, amplitude: float, seconds: float = 3.0, sample_rate: int = 22050) -> Path:
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


def write_mixed_wav(
    path: Path,
    *,
    components: list[tuple[float, float]],
    seconds: float = 3.0,
    sample_rate: int = 22050,
) -> Path:
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    samples = sum(amplitude * np.sin(2 * math.pi * frequency * t) for frequency, amplitude in components)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path


def settings(tmp_path: Path):
    return SimpleNamespace(
        stems_output_dir=str(tmp_path / "stems"),
        stems_engine="demucs",
        stems_timeout_seconds=30,
        stems_enabled=True,
        demucs_cli_path="fake-demucs",
        music_to_music_vocal_threshold_db=-24.0,
        music_to_music_min_vocal_activity=0.04,
    )


def test_instrumental_mode_skips_separation(monkeypatch, tmp_path):
    source = write_wav(tmp_path / "instrumental.wav", frequency=220, amplitude=0.3)
    monkeypatch.setattr(music_source.stems_service, "separate_stems", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should not separate")))

    result = music_source.prepare_music_source(
        source_audio_path=str(source),
        requested_mode="instrumental",
        preserve_original_vocal=False,
        job_id="job",
        settings=settings(tmp_path),
        url_for_path=lambda value: f"/audio/{Path(value).name}" if value else None,
    )

    assert result.detected_mode == "instrumental"
    assert result.separation_status == "not_required"
    assert result.instrumental_audio_path == str(source.resolve())
    assert result.vocal_detected is False


def test_auto_mode_uses_clean_instrumental_and_preserves_detected_vocal(monkeypatch, tmp_path):
    source = write_wav(tmp_path / "song.wav", frequency=220, amplitude=0.35)
    vocal = write_wav(tmp_path / "vocals.wav", frequency=440, amplitude=0.22)
    instrumental = write_wav(tmp_path / "no_vocals.wav", frequency=220, amplitude=0.25)
    monkeypatch.setattr(
        music_source.stems_service,
        "separate_stems",
        lambda **_kwargs: StemSeparationResponse(
            status="completed",
            engine="demucs",
            stem_paths={"vocals": str(vocal), "no_vocals": str(instrumental)},
        ),
    )

    result = music_source.prepare_music_source(
        source_audio_path=str(source),
        requested_mode="auto",
        preserve_original_vocal=True,
        job_id="job",
        settings=settings(tmp_path),
        url_for_path=lambda value: f"/audio/{Path(value).name}" if value else None,
    )

    assert result.detected_mode == "full_song"
    assert result.vocal_detected is True
    assert result.vocal_preserved is True
    assert result.instrumental_audio_path == str(instrumental)
    assert result.vocal_audio_path == str(vocal)
    assert result.vocal_energy_db_below_mix > -24


def test_auto_mode_keeps_original_when_vocal_stem_is_below_threshold(monkeypatch, tmp_path):
    source = write_wav(tmp_path / "instrumental.wav", frequency=220, amplitude=0.35)
    vocal = write_wav(tmp_path / "vocals.wav", frequency=440, amplitude=0.001)
    instrumental = write_wav(tmp_path / "no_vocals.wav", frequency=220, amplitude=0.34)
    monkeypatch.setattr(
        music_source.stems_service,
        "separate_stems",
        lambda **_kwargs: StemSeparationResponse(
            status="completed",
            engine="demucs",
            stem_paths={"vocals": str(vocal), "no_vocals": str(instrumental)},
        ),
    )

    result = music_source.prepare_music_source(
        source_audio_path=str(source),
        requested_mode="auto",
        preserve_original_vocal=True,
        job_id="job",
        settings=settings(tmp_path),
        url_for_path=lambda value: value,
    )

    assert result.detected_mode == "instrumental"
    assert result.vocal_detected is False
    assert result.vocal_preserved is False
    assert result.instrumental_audio_path == str(source.resolve())


def test_auto_mode_fails_closed_when_clean_stems_are_missing(monkeypatch, tmp_path):
    source = write_wav(tmp_path / "song.wav", frequency=220, amplitude=0.35)
    monkeypatch.setattr(
        music_source.stems_service,
        "separate_stems",
        lambda **_kwargs: StemSeparationResponse(status="failed", engine="demucs", warnings=["mock failure"]),
    )

    result = music_source.prepare_music_source(
        source_audio_path=str(source),
        requested_mode="auto",
        preserve_original_vocal=False,
        job_id="job",
        settings=settings(tmp_path),
        url_for_path=lambda value: value,
    )

    assert result.detected_mode == "unknown"
    assert result.instrumental_audio_path is None
    assert "mock failure" in result.warnings


def test_clean_separated_vocal_passes_pre_mix_leakage_gate(tmp_path):
    vocal = write_wav(tmp_path / "vocals.wav", frequency=440, amplitude=0.25)
    instrumental = write_wav(tmp_path / "no_vocals.wav", frequency=220, amplitude=0.30)

    report = music_source.assess_vocal_leakage(str(vocal), str(instrumental))

    assert report.status == "passed"
    assert report.passed is True
    assert report.waveform_correlation < 0.30
    assert report.analysed_frames > 0


def test_instrument_contaminated_vocal_fails_pre_mix_leakage_gate(monkeypatch, tmp_path):
    source = write_mixed_wav(tmp_path / "song.wav", components=[(220, 0.30), (440, 0.20)])
    instrumental = write_wav(tmp_path / "no_vocals.wav", frequency=220, amplitude=0.30)
    contaminated_vocal = write_mixed_wav(
        tmp_path / "vocals.wav",
        components=[(440, 0.20), (220, 0.22)],
    )
    monkeypatch.setattr(
        music_source.stems_service,
        "separate_stems",
        lambda **_kwargs: StemSeparationResponse(
            status="completed",
            engine="demucs",
            stem_paths={"vocals": str(contaminated_vocal), "no_vocals": str(instrumental)},
        ),
    )

    result = music_source.prepare_music_source(
        source_audio_path=str(source),
        requested_mode="full_song",
        preserve_original_vocal=True,
        job_id="job",
        settings=settings(tmp_path),
        url_for_path=lambda value: value,
    )

    assert result.separation_status == "failed_vocal_leakage"
    assert result.instrumental_audio_path is None
    assert result.vocal_audio_path is None
    assert result.vocal_preserved is False
    assert result.vocal_leakage_quality is not None
    assert result.vocal_leakage_quality.passed is False
    assert any("stopped before" in warning for warning in result.warnings)
