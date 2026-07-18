from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.main import app
from app.services import health as health_service


client = TestClient(app)


def health_settings(tmp_path: Path) -> Settings:
    return Settings(
        ace_step_enabled=False,
        procedural_output_dir=str(tmp_path / "procedural"),
        mix_output_dir=str(tmp_path / "mixes"),
        stems_output_dir=str(tmp_path / "stems"),
        section_output_dir=str(tmp_path / "sections"),
        projects_dir=str(tmp_path / "projects"),
        exports_dir=str(tmp_path / "exports"),
        uploads_dir=str(tmp_path / "uploads"),
        demucs_cli_path="definitely-not-demucs",
        ffmpeg_path="definitely-not-ffmpeg",
    )


def output_dirs(settings: Settings) -> dict[str, str]:
    return {
        "procedural_v2": settings.procedural_output_dir,
        "mixes": settings.mix_output_dir,
        "stems": settings.stems_output_dir,
        "sections": settings.section_output_dir,
        "projects": settings.projects_dir,
        "exports": settings.exports_dir,
        "uploads": settings.uploads_dir,
    }


def test_full_health_service_returns_checks_and_warnings(tmp_path):
    settings = health_settings(tmp_path)
    response = health_service.build_full_health(settings, output_dirs=output_dirs(settings), version="test")

    assert response.status == "ok"
    assert response.checks["config"]["ok"] is True
    assert response.checks["demucs"]["available"] is False
    assert response.warnings


def test_full_health_endpoint_returns_checks(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", health_settings(tmp_path))

    response = client.get("/health/full")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "producer_assistant" in data["checks"]
    assert "demucs" in data["checks"]


def test_output_dirs_writable_check_creates_dirs(tmp_path):
    settings = health_settings(tmp_path)
    response = health_service.build_full_health(settings, output_dirs=output_dirs(settings), version="test")

    assert response.checks["dir:projects"]["ok"] is True
    assert (tmp_path / "projects").exists()
