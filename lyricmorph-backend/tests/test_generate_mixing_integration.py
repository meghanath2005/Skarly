import math
import wave
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.generators.ace_step import GenerationResult
from app.main import app
from app.models import now_utc
from app.services import jobs as producer_jobs


client = TestClient(app)


def setup_function():
    producer_jobs.clear_jobs()


def write_wav(path: Path, seconds: float = 10.0, frequency: float = 440.0, amplitude: float = 0.35, sample_rate: int = 22050) -> Path:
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


def real_mode_settings(tmp_path: Path) -> Settings:
    return Settings(
        ace_step_enabled=True,
        ace_step_output_dir=str(tmp_path / "ace"),
        ace_step_default_format="wav",
        ace_step_cli_path="fake-acestep",
        procedural_fallback_enabled=True,
        procedural_output_dir=str(tmp_path / "procedural"),
        mix_output_dir=str(tmp_path / "mixes"),
        mix_preview_format="wav",
        mix_default_format="wav",
        mix_sample_rate=22050,
    )


def fake_success_result(output: Path) -> GenerationResult:
    started = now_utc()
    return GenerationResult(
        success=True,
        output_path=str(output),
        generator_name="ACE-Step",
        started_at=started,
        finished_at=now_utc(),
        duration_seconds=0.01,
        logs=["render complete"],
        command_used="fake-acestep",
    )


def test_generate_with_vocal_audio_path_returns_mixed_preview(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", real_mode_settings(tmp_path))
    vocal = write_wav(tmp_path / "vocal.wav", seconds=6.0, frequency=330.0, amplitude=0.32)

    def fake_generate_song(**kwargs):
        output = Path(kwargs["output_dir"]) / f"{kwargs['job_id']}.wav"
        write_wav(output, seconds=10.0, frequency=110.0, amplitude=0.28)
        return fake_success_result(output)

    monkeypatch.setattr(main_module.ace_step, "generate_song", fake_generate_song)

    response = client.post(
        "/generate",
        json={
            "preset_id": "bollywood_ballad_piano",
            "duration_seconds": 10,
            "vocal_audio_path": str(vocal),
            "vocal_gain_db": 2.0,
            "backing_gain_db": -3.0,
            "ducking_enabled": True,
            "ducking_amount": 0.35,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["audio_url"].startswith("/outputs/mixes/")
    assert data["backing_audio_url"].startswith("/outputs/ace_step/")
    assert data["mixed_preview_url"].startswith("/outputs/mixes/")
    assert data["audio_export"]["backing_audio_path"].endswith(".wav")
    assert data["audio_export"]["mixed_preview_path"].endswith(".wav")
    assert data["mix_diagnostics"]["status"] == "mix_success"
    assert data["quality_report"]["generator_name"] == "vocal_backing_mixer"
    assert data["quality_report"]["passed"] is True


def test_generate_without_vocal_audio_path_keeps_phase6_behavior(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", real_mode_settings(tmp_path))

    def fake_generate_song(**kwargs):
        output = Path(kwargs["output_dir"]) / f"{kwargs['job_id']}.wav"
        write_wav(output, seconds=10.0, frequency=110.0, amplitude=0.28)
        return fake_success_result(output)

    monkeypatch.setattr(main_module.ace_step, "generate_song", fake_generate_song)

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano", "duration_seconds": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["audio_url"].startswith("/outputs/ace_step/")
    assert data["backing_audio_url"].startswith("/outputs/ace_step/")
    assert data["mixed_preview_url"] is None
    assert data["mix_diagnostics"] is None
    assert data["quality_report"]["generator_name"] == "ACE-Step"


def test_mix_endpoint_mixes_two_valid_files(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", real_mode_settings(tmp_path))
    vocal = write_wav(tmp_path / "vocal.wav", seconds=4.0, frequency=330.0, amplitude=0.32)
    backing = write_wav(tmp_path / "backing.wav", seconds=4.0, frequency=110.0, amplitude=0.28)

    response = client.post(
        "/mix",
        json={
            "vocal_audio_path": str(vocal),
            "backing_audio_path": str(backing),
            "vocal_gain_db": 2.0,
            "backing_gain_db": -3.0,
            "ducking_enabled": True,
            "ducking_amount": 0.35,
            "output_format": "wav",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "mix_success"
    assert data["audio_export"]["mixed_preview_url"].startswith("/outputs/mixes/")
    assert data["audio_export"]["final_mix_wav_path"].endswith(".wav")
    assert data["diagnostics"]["status"] == "mix_success"
    assert data["quality_report"]["passed"] is True


def test_mix_endpoint_returns_clear_failure_for_missing_files(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", real_mode_settings(tmp_path))

    response = client.post(
        "/mix",
        json={
            "vocal_audio_path": str(tmp_path / "missing-vocal.wav"),
            "backing_audio_path": str(tmp_path / "missing-backing.wav"),
            "output_format": "wav",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "mix_failed"
    assert "Vocal audio file does not exist" in data["diagnostics"]["error_message"]
    assert data["quality_report"]["passed"] is False


def test_generate_mix_failure_keeps_backing_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", real_mode_settings(tmp_path))

    def fake_generate_song(**kwargs):
        output = Path(kwargs["output_dir"]) / f"{kwargs['job_id']}.wav"
        write_wav(output, seconds=10.0, frequency=110.0, amplitude=0.28)
        return fake_success_result(output)

    monkeypatch.setattr(main_module.ace_step, "generate_song", fake_generate_song)

    response = client.post(
        "/generate",
        json={
            "preset_id": "bollywood_ballad_piano",
            "duration_seconds": 10,
            "vocal_audio_path": str(tmp_path / "missing-vocal.wav"),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "mix_failed"
    assert data["audio_url"].startswith("/outputs/ace_step/")
    assert data["backing_audio_url"].startswith("/outputs/ace_step/")
    assert data["mixed_preview_url"] is None
    assert data["diagnostics"]["failed_step"] == "vocal_backing_mix"
    assert "Upload a valid vocal audio file" in data["mix_diagnostics"]["suggested_fix"]
