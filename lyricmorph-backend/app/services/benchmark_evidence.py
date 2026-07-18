"""Load public status from the release-audited ACE-Step benchmark manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FORMAT = "skarly_ace_step_benchmark_evidence_v1"


def public_status(path: str | Path) -> dict[str, Any]:
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_file():
        return {
            "available": False,
            "passed": False,
            "path": str(candidate),
            "note": "ACE-Step profile_inference benchmark evidence is missing.",
        }
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "passed": False,
            "path": str(candidate),
            "note": f"ACE-Step benchmark evidence is unreadable: {exc}",
        }
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        return {
            "available": False,
            "passed": False,
            "path": str(candidate),
            "note": "ACE-Step benchmark evidence has an unsupported format.",
        }
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    passed = payload.get("passed") is True and bool(checks) and all(value is True for value in checks.values())
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
    return {
        "available": True,
        "passed": passed,
        "path": str(candidate),
        "created_at": payload.get("created_at"),
        "ace_step_repo_commit": source.get("ace_step_repo_commit"),
        "raw_results_sha256": source.get("raw_results_sha256"),
        "device_name": runtime.get("device_name"),
        "device_capability": runtime.get("device_capability"),
        "torch_version": runtime.get("torch_version"),
        "torch_cuda_runtime": runtime.get("torch_cuda_runtime"),
        "matrix": payload.get("matrix"),
        "timings": payload.get("timings"),
        "checks": checks,
        "note": "Official ACE-Step profile_inference matrix passed." if passed else "One or more benchmark checks failed.",
    }
