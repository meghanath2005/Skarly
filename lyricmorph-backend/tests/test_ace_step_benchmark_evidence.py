from __future__ import annotations

import pytest

from training.summarize_ace_step_benchmark import build_evidence


def benchmark_rows(*, fail_last: bool = False) -> list[dict]:
    rows = []
    for duration in (30, 60, 120):
        for batch in (1, 2):
            for thinking in (False, True):
                rows.append(
                    {
                        "config": {
                            "duration": duration,
                            "batch_size": batch,
                            "thinking": thinking,
                            "inference_steps": 8,
                        },
                        "wall_time": 4.0 + duration / 10,
                        "success": True,
                        "error": None,
                        "lm_time": 2.0 if thinking else 0.0,
                        "dit_time": 2.5,
                        "vae_time": 1.5,
                        "n_audios": batch,
                    }
                )
    if fail_last:
        rows[-1]["success"] = False
        rows[-1]["error"] = "out of memory"
    return rows


def cuda_runtime() -> dict:
    return {
        "cuda_available": True,
        "device_name": "NVIDIA GeForce RTX 5070 Laptop GPU",
        "device_capability": "12.0",
        "torch_version": "2.7.1+cu128",
        "torch_cuda_runtime": "12.8",
        "compiled_architectures": ["sm_120"],
    }


def test_complete_official_matrix_produces_passing_evidence():
    evidence = build_evidence(
        benchmark_rows(),
        cuda=cuda_runtime(),
        raw_sha256="a" * 64,
        profile_script_sha256="b" * 64,
        ace_repo_commit="c" * 40,
        command="python profile_inference.py --mode benchmark --thinking",
    )

    assert evidence["passed"] is True
    assert evidence["matrix"]["configuration_count"] == 12
    assert evidence["matrix"]["success_count"] == 12
    assert evidence["checks"]["language_model_path_profiled"] is True
    assert evidence["checks"]["blackwell_capability"] is True
    assert evidence["timings"]["dit"]["minimum_seconds"] == 2.5


def test_failed_configuration_cannot_pass_evidence_gate():
    evidence = build_evidence(
        benchmark_rows(fail_last=True),
        cuda=cuda_runtime(),
        raw_sha256="a" * 64,
        profile_script_sha256="b" * 64,
        ace_repo_commit="c" * 40,
        command="benchmark",
    )

    assert evidence["passed"] is False
    assert evidence["matrix"]["failure_count"] == 1
    assert evidence["checks"]["all_configurations_succeeded"] is False


def test_empty_benchmark_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        build_evidence(
            [],
            cuda=cuda_runtime(),
            raw_sha256="a" * 64,
            profile_script_sha256="b" * 64,
            ace_repo_commit="c" * 40,
            command="benchmark",
        )
