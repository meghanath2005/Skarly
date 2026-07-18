from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path


def write_status(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: ace_step_direct_runner.py request.json", file=sys.stderr)
        return 2

    request_path = Path(sys.argv[1])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    project_root = Path(request["project_root"])
    output_path = Path(request["output_path"])
    status_path = Path(request.get("status_path") or output_path.with_suffix(".ace_step_status.json"))
    save_dir = Path(request.get("save_dir") or output_path.parent)
    save_dir.mkdir(parents=True, exist_ok=True)

    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["ACESTEP_DISABLE_TQDM"] = "1"
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        os.environ.pop(key, None)

    sys.path.insert(0, str(project_root))

    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music

    started = time.time()
    handler = AceStepHandler()
    status_message, ok = handler.initialize_service(
        project_root=str(project_root),
        config_path=request.get("model") or "acestep-v15-turbo",
        device=request.get("device") or "auto",
        use_flash_attention=False,
        compile_model=False,
        offload_to_cpu=bool(request.get("offload_to_cpu", True)),
        offload_dit_to_cpu=False,
        quantization=request.get("quantization"),
        use_mlx_dit=False,
    )
    if not ok:
        write_status(
            status_path,
            {
                "generation_engine": "ace_step_1_5",
                "is_fallback": False,
                "status": "failed",
                "message": status_message,
                "backing_path": None,
            },
        )
        return 1

    seed = int(request.get("seed") or 18484)
    params = GenerationParams(
        task_type="text2music",
        caption=str(request["prompt"]),
        lyrics="[Instrumental]",
        instrumental=True,
        vocal_language=str(request.get("vocal_language") or "hi"),
        bpm=int(request.get("bpm") or 84),
        keyscale=str(request.get("key") or "A minor"),
        timesignature=str(request.get("timesignature") or "4"),
        duration=float(request.get("duration") or 30.0),
        inference_steps=int(request.get("inference_steps") or 8),
        guidance_scale=float(request.get("guidance_scale") or 1.0),
        seed=seed,
        thinking=False,
        use_cot_metas=False,
        use_cot_caption=False,
        use_cot_language=False,
        use_cot_lyrics=False,
        use_constrained_decoding=False,
        enable_normalization=True,
        normalization_db=-1.0,
    )
    config = GenerationConfig(
        batch_size=1,
        audio_format="wav",
        use_random_seed=False,
        seeds=[seed],
    )
    result = generate_music(handler, None, params=params, config=config, save_dir=str(save_dir))
    if not result.success or not result.audios:
        write_status(
            status_path,
            {
                "generation_engine": "ace_step_1_5",
                "is_fallback": False,
                "status": "failed",
                "message": result.status_message or result.error or "ACE-Step did not return audio",
                "backing_path": None,
            },
        )
        return 1

    produced = Path(result.audios[0].get("path") or "")
    if not produced.exists():
        write_status(
            status_path,
            {
                "generation_engine": "ace_step_1_5",
                "is_fallback": False,
                "status": "failed",
                "message": f"ACE-Step returned missing audio path: {produced}",
                "backing_path": None,
            },
        )
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(produced, output_path)
    write_status(
        status_path,
        {
            "generation_engine": "ace_step_1_5",
            "is_fallback": False,
            "status": "ready",
            "message": "ACE-Step produced backing WAV",
            "source_output": str(produced),
            "backing_path": str(output_path),
            "elapsed_seconds": round(time.time() - started, 2),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
