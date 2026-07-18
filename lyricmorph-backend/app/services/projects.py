from __future__ import annotations

from pathlib import Path
import json
import shutil
from typing import Callable
from uuid import uuid4

from ..models import (
    GenerationDiagnostics,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
    QualityReport,
    now_utc,
)
from . import safe_paths


def create_project(
    request: ProjectCreateRequest,
    *,
    projects_dir: str | Path = "outputs/projects",
    allowed_dirs: list[str | Path] | None = None,
    url_for_path: Callable[[str], str | None] | None = None,
    quality_report: QualityReport | dict | None = None,
    diagnostics: GenerationDiagnostics | dict | None = None,
) -> ProjectResponse:
    project_id = f"project_{uuid4().hex}"
    timestamp = now_utc()
    settings = _settings_from_create_request(request)
    audio_paths = _validated_audio_paths(request.audio_paths, allowed_dirs)
    project = ProjectResponse(
        project_id=project_id,
        name=request.name.strip(),
        description=request.description,
        created_at=timestamp,
        updated_at=timestamp,
        lyrics=request.lyrics,
        settings=settings,
        audio_paths=audio_paths,
        audio_urls=_audio_urls(audio_paths, url_for_path),
        source_job_id=request.source_job_id,
        quality_report=_quality_report(quality_report),
        diagnostics=_diagnostics(diagnostics),
        notes=request.notes,
    )
    _write_project(project, projects_dir)
    return project


def get_project(
    project_id: str,
    *,
    projects_dir: str | Path = "outputs/projects",
    url_for_path: Callable[[str], str | None] | None = None,
) -> ProjectResponse | None:
    path = _project_json_path(projects_dir, project_id)
    if not path.exists():
        return None
    project = ProjectResponse.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if url_for_path:
        project.audio_urls = _audio_urls(project.audio_paths, url_for_path)
    return project


def update_project(
    project_id: str,
    request: ProjectUpdateRequest,
    *,
    projects_dir: str | Path = "outputs/projects",
    allowed_dirs: list[str | Path] | None = None,
    url_for_path: Callable[[str], str | None] | None = None,
) -> ProjectResponse | None:
    project = get_project(project_id, projects_dir=projects_dir, url_for_path=url_for_path)
    if project is None:
        return None

    updates = request.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        project.name = str(updates["name"]).strip()
    if "description" in updates:
        project.description = updates["description"]
    if "lyrics" in updates:
        project.lyrics = updates["lyrics"]
    if "settings" in updates and updates["settings"] is not None:
        project.settings.update(updates["settings"])
    if "audio_paths" in updates and updates["audio_paths"] is not None:
        project.audio_paths.update(_validated_audio_paths(updates["audio_paths"], allowed_dirs))
        project.audio_urls = _audio_urls(project.audio_paths, url_for_path)
    if "notes" in updates:
        project.notes = updates["notes"]
    project.updated_at = now_utc()
    _write_project(project, projects_dir)
    return project


def delete_project(project_id: str, *, projects_dir: str | Path = "outputs/projects") -> bool:
    project_dir = _project_dir(projects_dir, project_id)
    if not project_dir.exists():
        return False
    root = safe_paths.resolve_output_dir(projects_dir)
    try:
        project_dir.relative_to(root)
    except ValueError:
        raise ValueError("Project directory is outside the configured projects directory.")
    shutil.rmtree(project_dir)
    return True


def list_projects(
    *,
    projects_dir: str | Path = "outputs/projects",
    limit: int = 100,
    url_for_path: Callable[[str], str | None] | None = None,
) -> ProjectListResponse:
    root = safe_paths.resolve_output_dir(projects_dir)
    if not root.exists():
        return ProjectListResponse(projects=[], count=0)
    projects: list[ProjectResponse] = []
    for path in root.glob("*/project.json"):
        try:
            project = ProjectResponse.model_validate(json.loads(path.read_text(encoding="utf-8")))
            if url_for_path:
                project.audio_urls = _audio_urls(project.audio_paths, url_for_path)
            projects.append(project)
        except Exception:
            continue
    projects.sort(key=lambda item: item.updated_at, reverse=True)
    limited = projects[: max(0, limit)]
    return ProjectListResponse(projects=limited, count=len(limited))


def create_project_from_job(
    job_id: str,
    *,
    job_lookup: Callable[[str], dict | None],
    projects_dir: str | Path = "outputs/projects",
    allowed_dirs: list[str | Path] | None = None,
    url_for_path: Callable[[str], str | None] | None = None,
    name: str | None = None,
) -> ProjectResponse:
    job = job_lookup(job_id)
    if job is None:
        raise KeyError(job_id)

    audio_paths = _audio_paths_from_job(job, allowed_dirs)
    settings = {
        "structured_summary": job.get("structured_summary") or {},
        "recommended_settings": job.get("recommended_settings") or {},
        "generation_mode": job.get("generation_mode"),
        "status": job.get("status"),
    }
    request = ProjectCreateRequest(
        name=name or f"Project from {job_id[:8]}",
        lyrics=(job.get("structured_summary") or {}).get("lyrics"),
        source_job_id=job_id,
        audio_paths=audio_paths,
        notes=job.get("message"),
    )
    project = create_project(
        request,
        projects_dir=projects_dir,
        allowed_dirs=allowed_dirs,
        url_for_path=url_for_path,
        quality_report=job.get("quality_report"),
        diagnostics=job.get("diagnostics"),
    )
    project.settings.update(settings)
    project.updated_at = now_utc()
    _write_project(project, projects_dir)
    return project


def _settings_from_create_request(request: ProjectCreateRequest) -> dict:
    return {
        "language": request.language,
        "genre": request.genre,
        "production_style": request.production_style,
        "arrangement_style": request.arrangement_style,
        "mood_tags": request.mood_tags,
        "instruments": request.instruments,
        "bpm": request.bpm,
        "key": request.key,
        "duration_seconds": request.duration_seconds,
    }


def _validated_audio_paths(audio_paths: dict[str, str], allowed_dirs: list[str | Path] | None) -> dict[str, str]:
    validated: dict[str, str] = {}
    for key, value in (audio_paths or {}).items():
        if not value:
            continue
        try:
            safe_path = safe_paths.resolve_safe_output_path(value, allowed_dirs)
        except ValueError as exc:
            raise ValueError(f"Unsafe audio path for '{key}': {value}") from exc
        validated[str(key)] = str(safe_path)
    return validated


def _audio_urls(audio_paths: dict[str, str], url_for_path: Callable[[str], str | None] | None) -> dict[str, str]:
    if not url_for_path:
        return {}
    urls: dict[str, str] = {}
    for key, value in audio_paths.items():
        url = url_for_path(value)
        if url:
            urls[key] = url
    return urls


def _audio_paths_from_job(job: dict, allowed_dirs: list[str | Path] | None) -> dict[str, str]:
    candidates = {
        "audio": job.get("generated_audio_path"),
        "preview": job.get("preview_url"),
        "backing": job.get("backing_audio_path"),
        "mixed_preview": job.get("mixed_preview_path"),
        "final_mix_wav": job.get("final_mix_wav_path"),
        "final_mix_mp3": job.get("final_mix_mp3_path"),
    }
    export = job.get("audio_export") or {}
    candidates.update(
        {
            "export_final_wav": export.get("final_wav_path"),
            "export_final_mp3": export.get("final_mp3_path"),
            "export_backing": export.get("backing_audio_path"),
            "export_mixed_preview": export.get("mixed_preview_path"),
            "export_final_mix_wav": export.get("final_mix_wav_path"),
            "export_final_mix_mp3": export.get("final_mix_mp3_path"),
        }
    )
    safe: dict[str, str] = {}
    for key, value in candidates.items():
        if not value or str(value).startswith("/"):
            continue
        try:
            safe[key] = str(safe_paths.resolve_safe_output_path(value, allowed_dirs))
        except ValueError:
            continue
    return safe


def _quality_report(value: QualityReport | dict | None) -> QualityReport | None:
    if value is None:
        return None
    return value if isinstance(value, QualityReport) else QualityReport.model_validate(value)


def _diagnostics(value: GenerationDiagnostics | dict | None) -> GenerationDiagnostics | None:
    if value is None:
        return None
    return value if isinstance(value, GenerationDiagnostics) else GenerationDiagnostics.model_validate(value)


def _write_project(project: ProjectResponse, projects_dir: str | Path) -> None:
    path = _project_json_path(projects_dir, project.project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(project.model_dump(mode="json"), indent=2), encoding="utf-8")


def _project_json_path(projects_dir: str | Path, project_id: str) -> Path:
    return _project_dir(projects_dir, project_id) / "project.json"


def _project_dir(projects_dir: str | Path, project_id: str) -> Path:
    safe_id = safe_paths.sanitize_filename(project_id)
    return safe_paths.resolve_output_dir(projects_dir) / safe_id
