from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4


_JOB_ID_PATTERN = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$")


def save(output_dir: str | Path, job_id: str, payload: dict[str, Any]) -> Path:
    path = _job_path(output_dir, job_id)
    if path is None:
        raise ValueError("Invalid online music job ID")
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(path)
    return path


def load(output_dir: str | Path, job_id: str) -> dict[str, Any] | None:
    path = _job_path(output_dir, job_id)
    if path is None or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _job_path(output_dir: str | Path, job_id: str) -> Path | None:
    normalized = str(job_id or "").strip().lower()
    if not _JOB_ID_PATTERN.fullmatch(normalized):
        return None
    return Path(output_dir).expanduser().resolve() / "_jobs" / f"{normalized}.json"
