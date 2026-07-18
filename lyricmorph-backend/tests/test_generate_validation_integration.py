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


def write_wav(path: Path, seconds: float = 4.0, amplitude: float = 0.4, sample_rate: int = 22050) -> Path:
    if amplitude == 0:
        samples = np.zeros(int(sample_rate * seconds), dtype=np.int16)
    else:
        t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
        samples = (amplitude * np.sin(2 * math.pi * 440 * t) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(samples.tobytes())
    return path


def enable_ace_step(monkeypatch, tmp_path):
    monkeypatch.setattr(
        main_module,
        "settings",
        Settings(
            ace_step_enabled=True,
            ace_step_output_dir=str(tmp_path),
            ace_step_default_format="wav",
            ace_step_cli_path="fake-acestep",
            procedural_fallback_enabled=False,
        ),
    )


def result_for(path: Path, success: bool = True) -> GenerationResult:
    started = now_utc()
    return GenerationResult(
        success=success,
        output_path=str(path),
        generator_name="ACE-Step",
        started_at=started,
        finished_at=now_utc(),
        duration_seconds=0.01,
        logs=["render complete"],
        command_used="fake-acestep",
    )


def test_generate_success_validates_audio(monkeypatch, tmp_path):
    enable_ace_step(monkeypatch, tmp_path)

    def fake_generate_song(**kwargs):
        output = Path(kwargs["output_dir"]) / f"{kwargs['job_id']}.wav"
        write_wav(output, seconds=10.0, amplitude=0.4)
        return result_for(output)

    monkeypatch.setattr(main_module.ace_step, "generate_song", fake_generate_song)

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano", "duration_seconds": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["message"] == "Audio generated and validated successfully."
    assert data["quality_report"]["passed"] is True
    assert data["quality_report"]["duration_seconds"] is not None
    assert data["quality_report"]["peak_db"] is not None


def test_generate_success_with_silent_audio_returns_failed_validation(monkeypatch, tmp_path):
    enable_ace_step(monkeypatch, tmp_path)

    def fake_generate_song(**kwargs):
        output = Path(kwargs["output_dir"]) / f"{kwargs['job_id']}.wav"
        write_wav(output, seconds=10.0, amplitude=0.0)
        return result_for(output)

    monkeypatch.setattr(main_module.ace_step, "generate_song", fake_generate_song)

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano", "duration_seconds": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed_validation"
    assert data["message"] == "Audio was generated but failed validation."
    assert data["audio_url"]
    assert data["diagnostics"]["failed_step"] == "audio_validation"
    assert data["diagnostics"]["status"] == "failed_validation"
    assert data["quality_report"]["passed"] is False
    assert data["quality_report"]["is_silent"] is True


def test_generate_success_missing_output_returns_failed_validation(monkeypatch, tmp_path):
    enable_ace_step(monkeypatch, tmp_path)

    def fake_generate_song(**kwargs):
        output = Path(kwargs["output_dir"]) / f"{kwargs['job_id']}.wav"
        return result_for(output)

    monkeypatch.setattr(main_module.ace_step, "generate_song", fake_generate_song)

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano", "duration_seconds": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed_validation"
    assert data["audio_url"] is None
    assert data["diagnostics"]["failed_step"] == "audio_validation"
    assert "does not exist" in data["diagnostics"]["error_message"]
    assert data["quality_report"]["audio_exists"] is False
    assert "Generated audio file does not exist." in data["quality_report"]["warnings"]
