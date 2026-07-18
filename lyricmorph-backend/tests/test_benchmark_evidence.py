from __future__ import annotations

import json

from app.services import benchmark_evidence


def valid_payload() -> dict:
    return {
        "format": benchmark_evidence.FORMAT,
        "created_at": "2026-07-15T00:00:00+00:00",
        "source": {
            "ace_step_repo_commit": "a" * 40,
            "raw_results_sha256": "b" * 64,
        },
        "runtime": {
            "device_name": "NVIDIA GeForce RTX 5070 Laptop GPU",
            "device_capability": "12.0",
            "torch_version": "2.7.1+cu128",
            "torch_cuda_runtime": "12.8",
        },
        "matrix": {"configuration_count": 12, "success_count": 12, "failure_count": 0},
        "timings": {"wall": {"maximum_seconds": 54.0}},
        "checks": {"all_configurations_succeeded": True, "sm_120_compiled": True},
        "passed": True,
    }


def test_public_benchmark_status_exposes_evidence_without_full_results(tmp_path):
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(valid_payload()), encoding="utf-8")

    status = benchmark_evidence.public_status(path)

    assert status["available"] is True
    assert status["passed"] is True
    assert status["matrix"]["configuration_count"] == 12
    assert status["device_capability"] == "12.0"
    assert "results" not in status


def test_missing_or_failed_benchmark_is_not_reported_as_passed(tmp_path):
    missing = benchmark_evidence.public_status(tmp_path / "missing.json")
    assert missing["available"] is False
    assert missing["passed"] is False

    payload = valid_payload()
    payload["checks"]["sm_120_compiled"] = False
    path = tmp_path / "failed.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    failed = benchmark_evidence.public_status(path)
    assert failed["available"] is True
    assert failed["passed"] is False
