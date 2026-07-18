import wave
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.generators.ace_step import GenerationResult
from app.models import now_utc
from app.main import app
from app.services import jobs as producer_jobs


client = TestClient(app)


def setup_function():
    producer_jobs.clear_jobs()


def fallback_settings(tmp_path: Path, enabled: bool = True) -> Settings:
    return Settings(
        ace_step_enabled=True,
        ace_step_output_dir=str(tmp_path / "ace"),
        ace_step_default_format="wav",
        ace_step_cli_path="fake-acestep",
        procedural_fallback_enabled=enabled,
        procedural_output_dir=str(tmp_path / "procedural"),
    )


def ace_result(path: Path | None, success: bool, error_message: str | None = None) -> GenerationResult:
    started = now_utc()
    return GenerationResult(
        success=success,
        output_path=str(path) if path else None,
        generator_name="ACE-Step",
        started_at=started,
        finished_at=now_utc(),
        duration_seconds=0.01,
        error_message=error_message,
        logs=["ACE-Step test log"],
        command_used="fake-acestep",
        suggested_fix="Verify ACE-Step environment and model weights." if error_message else None,
    )


def write_silent_wav(path: Path, seconds: float = 10.0, sample_rate: int = 22050) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = np.zeros(int(sample_rate * seconds), dtype=np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(samples.tobytes())
    return path


def test_ace_failure_uses_procedural_fallback_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", fallback_settings(tmp_path, enabled=True))

    def fake_generate_song(**kwargs):
        return ace_result(Path(kwargs["output_dir"]) / f"{kwargs['job_id']}.wav", False, "weights missing")

    monkeypatch.setattr(main_module.ace_step, "generate_song", fake_generate_song)

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano", "duration_seconds": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed_fallback"
    assert data["generation_mode"] == "procedural_v2_fallback"
    assert data["audio_url"].startswith("/outputs/procedural_v2/")
    assert data["diagnostics"]["fallback_used"] is True
    assert "weights missing" in data["diagnostics"]["fallback_reason"]
    assert data["quality_report"]["generator_name"] == "procedural_v2"
    assert data["quality_report"]["fallback_used"] is True
    assert data["quality_report"]["passed"] is True


def test_ace_validation_failure_uses_procedural_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", fallback_settings(tmp_path, enabled=True))

    def fake_generate_song(**kwargs):
        output = Path(kwargs["output_dir"]) / f"{kwargs['job_id']}.wav"
        write_silent_wav(output)
        return ace_result(output, True)

    monkeypatch.setattr(main_module.ace_step, "generate_song", fake_generate_song)

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano", "duration_seconds": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed_fallback"
    assert data["audio_url"].startswith("/outputs/procedural_v2/")
    assert data["quality_report"]["passed"] is True
    assert "audio_validation" in data["diagnostics"]["fallback_reason"]
    assert any("audio_validation" in line or "silent" in line for line in data["diagnostics"]["last_logs"])


def test_ace_failure_returns_failed_when_fallback_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", fallback_settings(tmp_path, enabled=False))

    def fake_generate_song(**kwargs):
        return ace_result(Path(kwargs["output_dir"]) / f"{kwargs['job_id']}.wav", False, "weights missing")

    monkeypatch.setattr(main_module.ace_step, "generate_song", fake_generate_song)

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano", "duration_seconds": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["diagnostics"]["failed_step"] == "ace_step_generation"
    assert data["diagnostics"]["fallback_used"] is False


def test_fallback_generation_failure_returns_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", fallback_settings(tmp_path, enabled=True))

    def fake_generate_song(**kwargs):
        return ace_result(Path(kwargs["output_dir"]) / f"{kwargs['job_id']}.wav", False, "weights missing")

    def fake_generate_backing(**_kwargs):
        started = now_utc()
        return main_module.procedural_v2.GenerationResult(
            success=False,
            output_path=None,
            generator_name="procedural_v2",
            started_at=started,
            finished_at=now_utc(),
            duration_seconds=0.01,
            error_message="disk full",
            logs=["procedural_v2 could not write output"],
            suggested_fix="Free disk space.",
        )

    monkeypatch.setattr(main_module.ace_step, "generate_song", fake_generate_song)
    monkeypatch.setattr(main_module.procedural_v2, "generate_backing", fake_generate_backing)

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano", "duration_seconds": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["diagnostics"]["status"] == "fallback_failed"
    assert data["diagnostics"]["failed_step"] == "procedural_v2_generation"
    assert data["diagnostics"]["fallback_used"] is True
    assert "disk full" in data["diagnostics"]["error_message"]


def test_mock_mode_still_returns_completed_mock(monkeypatch):
    monkeypatch.setattr(main_module, "settings", Settings(ace_step_enabled=False, procedural_fallback_enabled=True))

    def fail_if_called(**_kwargs):
        raise AssertionError("ACE-Step should not be called in mock mode")

    monkeypatch.setattr(main_module.ace_step, "generate_song", fail_if_called)

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed_mock"
    assert data["generation_mode"] == "mock"
