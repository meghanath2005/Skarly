"""Run the CUDA checks required by Skarly's local generation contract.

This module is executed with the same Python environment used by ACE-Step so
the result describes the runtime that will actually generate the music.
"""

from __future__ import annotations

import json
import sys


def verify_cuda() -> dict[str, object]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required, but PyTorch cannot access an NVIDIA GPU.")

    device_index = torch.cuda.current_device()
    device_name = torch.cuda.get_device_name(device_index)
    capability = tuple(int(value) for value in torch.cuda.get_device_capability(device_index))
    architectures = list(torch.cuda.get_arch_list())
    if capability < (12, 0):
        raise RuntimeError(
            f"Unexpected GPU capability {capability}. Skarly requires RTX 50-series Blackwell CUDA capability 12.0 or newer."
        )
    if "sm_120" not in architectures:
        raise RuntimeError(
            "The installed PyTorch build does not include sm_120 support. Install a CUDA 12.8-or-newer Blackwell-compatible build."
        )

    torch.cuda.reset_peak_memory_stats(device_index)
    tensor_a = torch.randn((2048, 2048), dtype=torch.float16, device="cuda")
    tensor_b = torch.randn((2048, 2048), dtype=torch.float16, device="cuda")
    result = tensor_a @ tensor_b
    torch.cuda.synchronize(device_index)
    payload = {
        "cuda_available": True,
        "device": device_name,
        "device_index": device_index,
        "device_capability": f"{capability[0]}.{capability[1]}",
        "torch_version": torch.__version__,
        "torch_cuda_runtime": torch.version.cuda,
        "compiled_architectures": architectures,
        "test_result_device": str(result.device),
        "allocated_memory_mb": round(torch.cuda.memory_allocated(device_index) / 1024**2, 2),
        "peak_memory_mb": round(torch.cuda.max_memory_allocated(device_index) / 1024**2, 2),
    }
    del tensor_a, tensor_b, result
    torch.cuda.empty_cache()
    return payload


if __name__ == "__main__":
    try:
        print(json.dumps(verify_cuda()))
    except Exception as exc:
        print(json.dumps({"cuda_available": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
