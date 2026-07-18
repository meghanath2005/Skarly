from pathlib import Path

from app.models import ProjectCreateRequest, ProjectUpdateRequest
from app.services import projects, safe_paths


def url_for_path_factory(allowed_dirs):
    prefixes = {str(path): f"/outputs/{Path(path).name}" for path in allowed_dirs}
    return lambda path: safe_paths.safe_url_for_output(path, allowed_dirs, prefixes)


def test_create_list_get_update_delete_project(tmp_path):
    projects_dir = tmp_path / "projects"
    audio_dir = tmp_path / "ace_step"
    audio_path = audio_dir / "song.wav"
    allowed_dirs = [projects_dir, audio_dir]
    url_for_path = url_for_path_factory(allowed_dirs)

    project = projects.create_project(
        ProjectCreateRequest(
            name="Monsoon Ballad",
            lyrics="mera dil adhoora hai",
            genre="Pop",
            production_style="Bollywood Ballad",
            audio_paths={"backing": str(audio_path)},
        ),
        projects_dir=projects_dir,
        allowed_dirs=allowed_dirs,
        url_for_path=url_for_path,
    )

    assert project.project_id.startswith("project_")
    assert project.audio_urls["backing"].startswith("/outputs/ace_step/")

    listed = projects.list_projects(projects_dir=projects_dir, url_for_path=url_for_path)
    assert listed.count == 1
    assert listed.projects[0].name == "Monsoon Ballad"

    loaded = projects.get_project(project.project_id, projects_dir=projects_dir, url_for_path=url_for_path)
    assert loaded is not None
    assert loaded.lyrics == "mera dil adhoora hai"

    updated = projects.update_project(
        project.project_id,
        ProjectUpdateRequest(name="Updated Ballad", settings={"bpm": 88}, notes="ready"),
        projects_dir=projects_dir,
        allowed_dirs=allowed_dirs,
        url_for_path=url_for_path,
    )
    assert updated is not None
    assert updated.name == "Updated Ballad"
    assert updated.settings["bpm"] == 88

    assert projects.delete_project(project.project_id, projects_dir=projects_dir) is True
    assert projects.get_project(project.project_id, projects_dir=projects_dir) is None


def test_create_project_from_mock_job(tmp_path):
    projects_dir = tmp_path / "projects"
    allowed_dirs = [projects_dir]
    job = {
        "job_id": "job123",
        "status": "completed_mock",
        "message": "Prompt generated.",
        "structured_summary": {"language": "Hindi", "genre": "Pop"},
        "recommended_settings": {"bpm": 88},
        "generation_mode": "mock",
        "quality_report": {"audio_exists": False, "passed": False, "warnings": ["mock"]},
        "diagnostics": {"status": "completed_mock", "generator_name": "mock_prompt_builder"},
    }

    project = projects.create_project_from_job(
        "job123",
        job_lookup=lambda job_id: job if job_id == "job123" else None,
        projects_dir=projects_dir,
        allowed_dirs=allowed_dirs,
        name="From job",
    )

    assert project.name == "From job"
    assert project.source_job_id == "job123"
    assert project.settings["generation_mode"] == "mock"
    assert project.quality_report is not None
