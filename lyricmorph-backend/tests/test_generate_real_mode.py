from pathlib import Path
import math
import wave

from fastapi.testclient import TestClient
import numpy as np

import app.main as main_module
from app.config import Settings
from app.generators.ace_step import GenerationResult
from app.main import app
from app.models import now_utc
from app.services import jobs as producer_jobs


client = TestClient(app)


def setup_function():
    producer_jobs.clear_jobs()


def write_valid_wav(path: Path, seconds: float = 90.0, sample_rate: int = 22050) -> Path:
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    samples = (0.4 * np.sin(2 * math.pi * 440 * t) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(samples.tobytes())
    return path


def test_generate_mock_mode_does_not_call_ace_step(monkeypatch):
    monkeypatch.setattr(main_module, "settings", Settings(ace_step_enabled=False))

    def fail_if_called(**_kwargs):
        raise AssertionError("ACE-Step should not be called when disabled")

    monkeypatch.setattr(main_module.ace_step, "generate_song", fail_if_called)

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed_mock"
    assert data["generation_mode"] == "mock"
    assert data["message"] == "Prompt generated successfully. Real audio generation is disabled."


def test_generate_real_mode_success(monkeypatch, tmp_path):
    monkeypatch.setattr(
        main_module,
        "settings",
        Settings(
            ace_step_enabled=True,
            ace_step_output_dir=str(tmp_path),
            ace_step_default_format="wav",
            ace_step_cli_path="fake-acestep",
            ace_step_timeout_seconds=12,
        ),
    )

    def fake_generate_song(**kwargs):
        output = Path(kwargs["output_dir"]) / f"{kwargs['job_id']}.wav"
        write_valid_wav(output)
        started = now_utc()
        return GenerationResult(
            success=True,
            output_path=str(output),
            generator_name="ACE-Step",
            started_at=started,
            finished_at=now_utc(),
            duration_seconds=0.01,
            logs=["render complete"],
            command_used="fake-acestep --output song.wav",
        )

    monkeypatch.setattr(main_module.ace_step, "generate_song", fake_generate_song)

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano", "lyrics": "Tum yaad aaye"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["generation_mode"] == "ace_step"
    assert data["generated_audio_path"].endswith(".wav")
    assert data["audio_url"].startswith("/outputs/ace_step/")
    assert data["preview_url"] == data["audio_url"]
    assert data["diagnostics"]["generator_name"] == "ACE-Step"
    assert data["diagnostics"]["status"] == "success"
    assert data["quality_report"]["audio_exists"] is True
    assert data["quality_report"]["passed"] is True


def test_generate_real_mode_failure(monkeypatch, tmp_path):
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

    def fake_generate_song(**_kwargs):
        started = now_utc()
        return GenerationResult(
            success=False,
            output_path=str(tmp_path / "missing.wav"),
            generator_name="ACE-Step",
            started_at=started,
            finished_at=now_utc(),
            duration_seconds=0.01,
            error_message="weights missing",
            logs=["loading model", "weights missing"],
            command_used="fake-acestep",
            suggested_fix="Verify ACE-Step environment and model weights.",
        )

    monkeypatch.setattr(main_module.ace_step, "generate_song", fake_generate_song)

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["generation_mode"] == "ace_step"
    assert data["diagnostics"]["failed_step"] == "ace_step_generation"
    assert data["diagnostics"]["error_message"] == "weights missing"
    assert data["diagnostics"]["suggested_fix"] == "Verify ACE-Step environment and model weights."
    assert data["positive_prompt"]
    assert data["quality_report"]["audio_exists"] is False
    assert "ACE-Step output file is missing." in data["quality_report"]["warnings"]
