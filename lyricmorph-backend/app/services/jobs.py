from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

JOB_STATUSES = {
    "queued",
    "prompt_ready",
    "generating",
    "completed_mock",
    "completed",
    "completed_fallback",
    "failed",
    "failed_validation",
    "mix_failed",
    "fallback_pending",
    "rights_required",
    "analysis_failed",
    "separation_failed",
    "completed_needs_review",
    "regenerating",
}

_jobs: dict[str, dict[str, Any]] = {}


def create_job(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(uuid4())
    job = {"job_id": job_id, "status": "queued", "progress": 0.0, **deepcopy(payload)}
    _jobs[job_id] = job
    return deepcopy(job)


def get_job(job_id: str) -> dict[str, Any] | None:
    job = _jobs.get(job_id)
    return deepcopy(job) if job is not None else None


def update_job(job_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    if job_id not in _jobs:
        raise KeyError(job_id)
    status = fields.get("status")
    if status is not None and status not in JOB_STATUSES:
        raise ValueError(f"Unsupported job status: {status}")
    _jobs[job_id].update(deepcopy(fields))
    return deepcopy(_jobs[job_id])


def list_jobs() -> list[dict[str, Any]]:
    return [deepcopy(job) for job in _jobs.values()]


def clear_jobs() -> None:
    _jobs.clear()
