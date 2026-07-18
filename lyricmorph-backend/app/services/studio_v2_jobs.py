from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import re
from threading import RLock
from typing import Any, Callable
from uuid import uuid4


_JOB_ID_PATTERN = re.compile(r"^(analysis|generation|section|mix|feedback)_[a-f0-9]{32}$")
_LOCK = RLock()
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="skarly-v2")
_FUTURES: dict[str, Future[Any]] = {}


def jobs_root(output_dir: str | Path) -> Path:
    root = Path(output_dir).expanduser().resolve() / "_v2_jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_job(
    output_dir: str | Path,
    *,
    job_type: str,
    owner_id: str,
    upload_id: str | None = None,
    analysis_id: str | None = None,
    total_arrangements: int = 0,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_type = str(job_type).strip().lower()
    if normalized_type not in {"analysis", "generation", "section", "mix", "feedback"}:
        raise ValueError(f"Unsupported V2 job type: {job_type}")
    now = _now()
    job = {
        "job_id": f"{normalized_type}_{uuid4().hex}",
        "job_type": normalized_type,
        "owner_id": owner_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0.0,
        "created_at": now,
        "updated_at": now,
        "upload_id": upload_id,
        "analysis_id": analysis_id,
        "current_arrangement": None,
        "completed_arrangements": 0,
        "total_arrangements": int(total_arrangements),
        "completed_duration_seconds": 0.0,
        "cuda_device": None,
        "model": None,
        "warnings": [],
        "completed_outputs": [],
        "result": None,
        "error": None,
        "request": deepcopy(request or {}),
    }
    with _LOCK:
        _write_job(output_dir, job)
    return deepcopy(job)


def get_job(output_dir: str | Path, job_id: str) -> dict[str, Any] | None:
    path = _job_path(output_dir, job_id)
    if path is None or not path.is_file():
        return None
    with _LOCK:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None


def update_job(output_dir: str | Path, job_id: str, **fields: Any) -> dict[str, Any]:
    with _LOCK:
        job = get_job(output_dir, job_id)
        if job is None:
            raise KeyError(job_id)
        if "progress" in fields:
            fields["progress"] = max(float(job.get("progress") or 0), min(100.0, float(fields["progress"])))
        job.update(deepcopy(fields))
        job["updated_at"] = _now()
        _write_job(output_dir, job)
        return deepcopy(job)


def progress_callback(output_dir: str | Path, job_id: str) -> Callable[..., None]:
    def report(*, stage: str, progress: float, **fields: Any) -> None:
        update_job(
            output_dir,
            job_id,
            status="running",
            stage=stage,
            progress=progress,
            **fields,
        )

    return report


def submit(job_id: str, function: Callable[[], Any]) -> Future[Any]:
    future = _EXECUTOR.submit(function)
    with _LOCK:
        _FUTURES[job_id] = future

    def remove_finished(_future: Future[Any]) -> None:
        with _LOCK:
            _FUTURES.pop(job_id, None)

    future.add_done_callback(remove_finished)
    return future


def active_job_ids() -> list[str]:
    with _LOCK:
        return list(_FUTURES)


def recover_interrupted_jobs(output_dir: str | Path) -> int:
    """Fail persisted work that cannot survive a backend process restart."""
    recovered = 0
    with _LOCK:
        for path in jobs_root(output_dir).glob("*.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if job.get("status") not in {"queued", "running"}:
                continue
            job["status"] = "failed"
            job["stage"] = "interrupted"
            job["updated_at"] = _now()
            job["error"] = {
                "stage": "interrupted",
                "type": "ProcessRestart",
                "message": "The backend restarted before this job finished. Retry this operation; completed source arrangements remain available.",
                "retryable": True,
            }
            _write_job(output_dir, job)
            recovered += 1
    return recovered


def _job_path(output_dir: str | Path, job_id: str) -> Path | None:
    normalized = str(job_id or "").strip().lower()
    if not _JOB_ID_PATTERN.fullmatch(normalized):
        return None
    return jobs_root(output_dir) / f"{normalized}.json"


def _write_job(output_dir: str | Path, job: dict[str, Any]) -> None:
    path = _job_path(output_dir, str(job.get("job_id") or ""))
    if path is None:
        raise ValueError("Invalid V2 job ID")
    payload = json.dumps(job, indent=2, ensure_ascii=False, allow_nan=False)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
