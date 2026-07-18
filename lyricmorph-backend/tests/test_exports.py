import json
from pathlib import Path

from app.models import ExportRequest, ProjectCreateRequest
from app.services import exports, projects, safe_paths


def url_for_path_factory(allowed_dirs):
    prefixes = {str(path): f"/outputs/{Path(path).name}" for path in allowed_dirs}
    return lambda path: safe_paths.safe_url_for_output(path, allowed_dirs, prefixes)


def test_create_manifest_from_project_and_job(tmp_path):
    projects_dir = tmp_path / "projects"
    exports_dir = tmp_path / "exports"
    audio_dir = tmp_path / "mixes"
    audio_path = audio_dir / "preview.wav"
    allowed_dirs = [projects_dir, exports_dir, audio_dir]
    url_for_path = url_for_path_factory(allowed_dirs)
    project = projects.create_project(
        ProjectCreateRequest(
            name="Export Me",
            lyrics="dil ki awaaz",
            production_style="Bollywood Ballad",
            audio_paths={"mixed_preview": str(audio_path)},
        ),
        projects_dir=projects_dir,
        allowed_dirs=allowed_dirs,
        url_for_path=url_for_path,
    )
    job = {
        "job_id": "job_export",
        "status": "completed",
        "positive_prompt": "Create an original Hindi ballad.",
        "negative_prompt": "Do not copy any existing song.",
        "structured_summary": {"genre": "Pop"},
        "recommended_settings": {"bpm": 88},
        "quality_report": {"passed": True, "audio_exists": True},
        "diagnostics": {"status": "success"},
        "mixed_preview_path": str(audio_path),
    }

    response = exports.create_export_manifest(
        ExportRequest(project_id=project.project_id, job_id="job_export"),
        exports_dir=exports_dir,
        projects_dir=projects_dir,
        project_lookup=lambda _project_id: project,
        job_lookup=lambda _job_id: job,
        url_for_path=url_for_path,
        allowed_dirs=allowed_dirs,
        app_summary={"version": "test"},
    )

    assert response.status == "completed"
    assert response.manifest_url is not None
    assert response.manifest_url.startswith("/outputs/exports/")
    manifest = json.loads(Path(response.manifest_path).read_text(encoding="utf-8"))
    assert manifest["project"]["name"] == "Export Me"
    assert manifest["job"]["positive_prompt"] == "Create an original Hindi ballad."
    assert manifest["job"]["recommended_settings"]["bpm"] == 88
    assert manifest["audio_paths"]["mixed_preview"].endswith("preview.wav")


def test_missing_project_handled_cleanly(tmp_path):
    response = exports.create_export_manifest(
        ExportRequest(project_id="missing"),
        exports_dir=tmp_path / "exports",
        projects_dir=tmp_path / "projects",
        project_lookup=lambda _project_id: None,
    )

    assert response.status == "failed"
    assert response.warnings
    assert "Project not found" in response.message


def test_get_export_manifest(tmp_path):
    exports_dir = tmp_path / "exports"
    response = exports.create_export_manifest(
        ExportRequest(job_id="job1"),
        exports_dir=exports_dir,
        job_lookup=lambda _job_id: {"job_id": "job1", "status": "completed_mock"},
    )

    manifest = exports.get_export_manifest(response.export_id, exports_dir=exports_dir)
    assert manifest is not None
    assert manifest["job"]["job_id"] == "job1"
