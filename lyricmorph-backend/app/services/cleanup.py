from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..models import CleanupRequest, CleanupResponse
from . import safe_paths


def cleanup_outputs(
    request: CleanupRequest,
    *,
    allowed_dirs: list[str | Path],
    default_retention_days: int = 14,
) -> CleanupResponse:
    older_than_days = request.older_than_days if request.older_than_days is not None else default_retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    files_found = 0
    files_deleted = 0
    bytes_found = 0
    bytes_deleted = 0
    warnings: list[str] = []

    for root_value in allowed_dirs:
        root = safe_paths.resolve_output_dir(root_value)
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if _is_protected_project_metadata(path):
                continue
            if not safe_paths.is_within_allowed_dirs(path, allowed_dirs):
                warnings.append(f"Skipped unsafe path: {path}")
                continue
            try:
                stat = path.stat()
            except OSError as exc:
                warnings.append(f"Could not inspect {path}: {exc}")
                continue
            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if modified > cutoff:
                continue
            files_found += 1
            bytes_found += stat.st_size
            if request.dry_run:
                continue
            if not request.include_outputs:
                continue
            try:
                path.unlink()
                files_deleted += 1
                bytes_deleted += stat.st_size
            except OSError as exc:
                warnings.append(f"Could not delete {path}: {exc}")

    if not request.dry_run and not request.include_outputs:
        warnings.append("No files were deleted because include_outputs=false.")

    return CleanupResponse(
        status="dry_run" if request.dry_run else "completed",
        dry_run=request.dry_run,
        files_found=files_found,
        files_deleted=files_deleted,
        bytes_found=bytes_found,
        bytes_deleted=bytes_deleted,
        warnings=_dedupe(warnings),
    )


def _is_protected_project_metadata(path: Path) -> bool:
    return "projects" in [part.lower() for part in path.parts] and path.name == "project.json"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
