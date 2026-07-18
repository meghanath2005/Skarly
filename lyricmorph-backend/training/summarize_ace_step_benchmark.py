"""Create release-auditable evidence from ACE-Step profile_inference results."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
from typing import Any, Mapping, Sequence


FORMAT = "skarly_ace_step_benchmark_evidence_v1"
REQUIRED_DURATIONS = {30, 60, 120}
REQUIRED_BATCHES = {1, 2}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_json(command: Sequence[str]) -> dict[str, Any]:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "command failed").strip()
        raise RuntimeError(detail[:1000])
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise ValueError("Runtime probe did not return a JSON object")
    return payload


def probe_cuda(python_executable: Path) -> dict[str, Any]:
    source = """
import json, torch
index = torch.cuda.current_device()
capability = torch.cuda.get_device_capability(index)
print(json.dumps({
    "cuda_available": torch.cuda.is_available(),
    "device_name": torch.cuda.get_device_name(index),
    "device_capability": f"{capability[0]}.{capability[1]}",
    "torch_version": torch.__version__,
    "torch_cuda_runtime": torch.version.cuda,
    "compiled_architectures": torch.cuda.get_arch_list(),
}))
"""
    return run_json([str(python_executable), "-c", source])


def git_commit(repo: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or "git rev-parse failed").strip())
    return completed.stdout.strip()


def timing_summary(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, float]:
    values = [float(row.get(field) or 0.0) for row in rows]
    return {
        "minimum_seconds": round(min(values), 6),
        "mean_seconds": round(statistics.fmean(values), 6),
        "maximum_seconds": round(max(values), 6),
    }


def build_evidence(
    rows: Sequence[Mapping[str, Any]],
    *,
    cuda: Mapping[str, Any],
    raw_sha256: str,
    profile_script_sha256: str,
    ace_repo_commit: str,
    command: str,
) -> dict[str, Any]:
    if not rows:
        raise ValueError("ACE-Step benchmark output is empty")
    durations = {int(row.get("config", {}).get("duration") or 0) for row in rows}
    batches = {int(row.get("config", {}).get("batch_size") or 0) for row in rows}
    thinking = {bool(row.get("config", {}).get("thinking")) for row in rows}
    failed = [row for row in rows if row.get("success") is not True]
    capability = str(cuda.get("device_capability") or "0.0")
    try:
        capability_major = int(capability.split(".", 1)[0])
    except ValueError:
        capability_major = 0
    checks = {
        "all_configurations_succeeded": not failed,
        "required_durations_profiled": REQUIRED_DURATIONS.issubset(durations),
        "batch_sizes_one_and_two_profiled": REQUIRED_BATCHES.issubset(batches),
        "language_model_path_profiled": thinking == {False, True} and any(float(row.get("lm_time") or 0) > 0 for row in rows),
        "dit_path_profiled": all(float(row.get("dit_time") or 0) > 0 for row in rows),
        "vae_path_profiled": all(float(row.get("vae_time") or 0) > 0 for row in rows),
        "cuda_available": cuda.get("cuda_available") is True,
        "rtx_5070_device": "RTX 5070" in str(cuda.get("device_name") or ""),
        "blackwell_capability": capability_major >= 12,
        "sm_120_compiled": "sm_120" in (cuda.get("compiled_architectures") or []),
    }
    return {
        "format": FORMAT,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "ace_step_repo_commit": ace_repo_commit,
            "profile_script_sha256": profile_script_sha256,
            "raw_results_sha256": raw_sha256,
            "command": command,
        },
        "runtime": dict(cuda),
        "matrix": {
            "configuration_count": len(rows),
            "success_count": len(rows) - len(failed),
            "failure_count": len(failed),
            "durations_seconds": sorted(durations),
            "batch_sizes": sorted(batches),
            "thinking_modes": sorted(thinking),
            "inference_steps": sorted({int(row.get("config", {}).get("inference_steps") or 0) for row in rows}),
        },
        "timings": {
            "wall": timing_summary(rows, "wall_time"),
            "language_model": timing_summary(rows, "lm_time"),
            "dit": timing_summary(rows, "dit_time"),
            "vae": timing_summary(rows, "vae_time"),
        },
        "checks": checks,
        "passed": all(checks.values()),
        "results": [dict(row) for row in rows],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ace-repo", type=Path, required=True)
    parser.add_argument("--ace-python", type=Path, required=True)
    parser.add_argument("--command", required=True)
    args = parser.parse_args()

    raw_path = args.raw.resolve()
    rows = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Raw ACE-Step benchmark output must be a JSON array")
    repo = args.ace_repo.resolve()
    evidence = build_evidence(
        rows,
        cuda=probe_cuda(args.ace_python.resolve()),
        raw_sha256=sha256_file(raw_path),
        profile_script_sha256=sha256_file(repo / "profile_inference.py"),
        ace_repo_commit=git_commit(repo),
        command=args.command,
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"output": str(output), "passed": evidence["passed"], **evidence["matrix"]}))


if __name__ == "__main__":
    main()
