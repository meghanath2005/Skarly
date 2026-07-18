from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.main import app
from app.services import jobs as producer_jobs


client = TestClient(app)


def setup_function():
    producer_jobs.clear_jobs()


def phase10_settings(tmp_path: Path) -> Settings:
    return Settings(
        ace_step_enabled=False,
        projects_enabled=True,
        projects_dir=str(tmp_path / "projects"),
        exports_dir=str(tmp_path / "exports"),
        uploads_dir=str(tmp_path / "uploads"),
        ace_step_output_dir=str(tmp_path / "ace"),
        procedural_output_dir=str(tmp_path / "procedural"),
        mix_output_dir=str(tmp_path / "mixes"),
        stems_output_dir=str(tmp_path / "stems"),
        section_output_dir=str(tmp_path / "sections"),
        demucs_cli_path="definitely-not-demucs",
        ffmpeg_path="definitely-not-ffmpeg",
    )


def test_projects_api_create_and_list(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase10_settings(tmp_path))

    create = client.post(
        "/projects",
        json={
            "name": "API Project",
            "lyrics": "mera dil adhoora hai",
            "language": "Hindi",
            "genre": "Pop",
            "production_style": "Bollywood Ballad",
        },
    )
    assert create.status_code == 200
    project = create.json()
    assert project["name"] == "API Project"

    listed = client.get("/projects")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1


def test_project_from_job_after_mock_generate(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase10_settings(tmp_path))

    generated = client.post("/generate", json={"preset_id": "bollywood_ballad_piano", "lyrics": "dil ki baat"})
    assert generated.status_code == 200
    job_id = generated.json()["job_id"]

    response = client.post(f"/projects/from-job/{job_id}?name=Saved%20Job")
    assert response.status_code == 200
    data = response.json()
    assert data["source_job_id"] == job_id
    assert data["name"] == "Saved Job"


def test_exports_api_creates_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase10_settings(tmp_path))
    project = client.post("/projects", json={"name": "Export API Project"}).json()

    response = client.post("/exports", json={"project_id": project["project_id"]})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["manifest_url"].startswith("/outputs/exports/")

    manifest = client.get(f"/exports/{data['export_id']}/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["project"]["project_id"] == project["project_id"]


def test_health_full_and_cleanup_dry_run(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase10_settings(tmp_path))

    health = client.get("/health/full")
    assert health.status_code == 200
    assert "checks" in health.json()

    cleanup = client.post("/cleanup", json={"dry_run": True})
    assert cleanup.status_code == 200
    assert cleanup.json()["dry_run"] is True


def test_existing_generate_mock_mode_still_works(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase10_settings(tmp_path))

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano"})

    assert response.status_code == 200
    assert response.json()["status"] == "completed_mock"
