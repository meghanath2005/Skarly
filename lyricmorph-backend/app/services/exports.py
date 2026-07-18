from __future__ import annotations

from pathlib import Path
import json
from typing import Callable
from uuid import uuid4

from ..models import ExportRequest, ExportResponse, ProjectResponse, now_utc
from . import projects as project_service
from . import safe_paths


def create_export_manifest(
    request: ExportRequest,
    *,
    exports_dir: str | Path = "outputs/exports",
    projects_dir: str | Path = "outputs/projects",
    project_lookup: Callable[[str], ProjectResponse | None] | None = None,
    job_lookup: Callable[[str], dict | None] | None = None,
    url_for_path: Callable[[str], str | None] | None = None,
    allowed_dirs: list[str | Path] | None = None,
    app_summary: dict | None = None,
) -> ExportResponse:
    export_id = f"export_{uuid4().hex}"
    warnings: list[str] = []

    project = None
    if request.project_id:
        project = project_lookup(request.project_id) if project_lookup else project_service.get_project(request.project_id, projects_dir=projects_dir, url_for_path=url_for_path)
        if project is None:
            return _failed_response(export_id, f"Project not found: {request.project_id}")

    job = None
    if request.job_id:
        job = job_lookup(request.job_id) if job_lookup else None
        if job is None:
            return _failed_response(export_id, f"Job not found: {request.job_id}")

    if project is None and job is None:
        return _failed_response(export_id, "Provide project_id or job_id to export.")

    export_dir = safe_paths.resolve_output_dir(exports_dir) / export_id
    export_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = export_dir / "manifest.json"
    manifest = _build_manifest(
        export_id=export_id,
        request=request,
        project=project,
        job=job,
        url_for_path=url_for_path,
        allowed_dirs=allowed_dirs,
        app_summary=app_summary or {},
        warnings=warnings,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest_url = url_for_path(str(manifest_path)) if url_for_path else None
    files = {"manifest": str(manifest_path)}
    if manifest_url:
        files["manifest_url"] = manifest_url
    return ExportResponse(
        status="completed",
        export_id=export_id,
        export_dir=str(export_dir),
        manifest_path=str(manifest_path),
        manifest_url=manifest_url,
        files=files,
        warnings=warnings,
        message="Export manifest created.",
    )


def get_export_manifest(export_id: str, *, exports_dir: str | Path = "outputs/exports") -> dict | None:
    path = safe_paths.resolve_output_dir(exports_dir) / safe_paths.sanitize_filename(export_id) / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _build_manifest(
    *,
    export_id: str,
    request: ExportRequest,
    project: ProjectResponse | None,
    job: dict | None,
    url_for_path: Callable[[str], str | None] | None,
    allowed_dirs: list[str | Path] | None,
    app_summary: dict,
    warnings: list[str],
) -> dict:
    audio_paths: dict[str, str] = {}
    audio_urls: dict[str, str] = {}
    if request.include_audio:
        audio_paths.update(_project_audio_paths(project, request.include_stems))
        audio_paths.update(_job_audio_paths(job, request.include_stems, allowed_dirs))
        for key, value in audio_paths.items():
            url = url_for_path(value) if url_for_path else None
            if url:
                audio_urls[key] = url
            else:
                warnings.append(f"Audio path is not safely exposable as a URL: {key}")

    return {
        "export_id": export_id,
        "created_at": now_utc().isoformat(),
        "format": request.format,
        "app": app_summary,
        "project": project.model_dump(mode="json") if project else None,
        "job": _job_manifest(job, request) if job else None,
        "audio_paths": audio_paths,
        "audio_urls": audio_urls,
        "warnings": warnings,
    }


def _project_audio_paths(project: ProjectResponse | None, include_stems: bool) -> dict[str, str]:
    if project is None:
        return {}
    if include_stems:
        return dict(project.audio_paths)
    return {key: value for key, value in project.audio_paths.items() if "stem" not in key.lower()}


def _job_audio_paths(job: dict | None, include_stems: bool, allowed_dirs: list[str | Path] | None) -> dict[str, str]:
    if job is None:
        return {}
    candidates = {
        "job_generated_audio": job.get("generated_audio_path"),
        "job_backing_audio": job.get("backing_audio_path"),
        "job_mixed_preview": job.get("mixed_preview_path"),
        "job_final_mix_wav": job.get("final_mix_wav_path"),
        "job_final_mix_mp3": job.get("final_mix_mp3_path"),
    }
    export = job.get("audio_export") or {}
    candidates.update(
        {
            "job_export_final_wav": export.get("final_wav_path"),
            "job_export_final_mp3": export.get("final_mp3_path"),
            "job_export_backing": export.get("backing_audio_path"),
            "job_export_mixed_preview": export.get("mixed_preview_path"),
            "job_export_final_mix_wav": export.get("final_mix_wav_path"),
            "job_export_final_mix_mp3": export.get("final_mix_mp3_path"),
            "job_export_stems_dir": export.get("stems_dir") if include_stems else None,
        }
    )
    audio_paths: dict[str, str] = {}
    for key, value in candidates.items():
        if not value or str(value).startswith("/"):
            continue
        try:
            audio_paths[key] = str(safe_paths.resolve_safe_output_path(value, allowed_dirs))
        except ValueError:
            continue
    return audio_paths


def _job_manifest(job: dict, request: ExportRequest) -> dict:
    manifest = {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "message": job.get("message"),
        "generation_mode": job.get("generation_mode"),
    }
    if request.include_prompts:
        manifest.update(
            {
                "positive_prompt": job.get("positive_prompt"),
                "negative_prompt": job.get("negative_prompt"),
                "structured_summary": job.get("structured_summary"),
                "recommended_settings": job.get("recommended_settings"),
            }
        )
    if request.include_quality_report:
        manifest["quality_report"] = job.get("quality_report")
    if request.include_diagnostics:
        manifest["diagnostics"] = job.get("diagnostics")
        manifest["mix_diagnostics"] = job.get("mix_diagnostics")
    return manifest


def _failed_response(export_id: str, warning: str) -> ExportResponse:
    return ExportResponse(
        status="failed",
        export_id=export_id,
        warnings=[warning],
        message=warning,
    )
