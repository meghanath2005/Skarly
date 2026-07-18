"""CUDA preflight and lightweight job-level VRAM telemetry."""

from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
import subprocess
import threading
from typing import Any


@lru_cache(maxsize=8)
def verify_cuda_runtime(python_path: str, timeout_seconds: int = 90) -> dict[str, Any]:
    """Verify CUDA using ACE-Step's Python, caching the successful startup test."""
    executable = Path(python_path)
    if not executable.is_file():
        raise RuntimeError(f"CUDA preflight failed: ACE-Step Python was not found at {executable}.")
    probe = Path(__file__).with_name("cuda_probe.py")
    completed = subprocess.run(
        [str(executable), str(probe)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(30, int(timeout_seconds)),
    )
    raw = (completed.stdout if completed.returncode == 0 else completed.stderr).strip()
    try:
        payload = json.loads(raw.splitlines()[-1]) if raw else {}
    except (json.JSONDecodeError, IndexError):
        payload = {}
    if completed.returncode != 0 or not payload.get("cuda_available"):
        detail = str(payload.get("error") or raw or "CUDA probe returned no details")[:500]
        raise RuntimeError(f"CUDA preflight failed: {detail}")
    if payload.get("test_result_device") != "cuda:0":
        raise RuntimeError(f"CUDA preflight failed: matrix test ran on {payload.get('test_result_device')!r}.")
    return payload


def query_gpu_memory_mb() -> float | None:
    """Return total memory currently used on the first NVIDIA GPU."""
    executable = os.getenv("NVIDIA_SMI_PATH", "nvidia-smi")
    try:
        completed = subprocess.run(
            [executable, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        if completed.returncode != 0:
            return None
        first = completed.stdout.strip().splitlines()[0].strip()
        return float(first)
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


class GpuMemorySampler:
    """Sample device VRAM while one model request is running."""

    def __init__(self, *, enabled: bool, interval_seconds: float = 0.5) -> None:
        self.enabled = enabled
        self.interval_seconds = max(0.1, float(interval_seconds))
        self.peak_vram_mb = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "GpuMemorySampler":
        if not self.enabled:
            return self
        self._sample()
        self._thread = threading.Thread(target=self._run, name="skarly-vram-sampler", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        if not self.enabled:
            return
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 3))
        self._sample()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._sample()

    def _sample(self) -> None:
        current = query_gpu_memory_mb()
        if current is not None:
            self.peak_vram_mb = max(self.peak_vram_mb, current)
