from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.parse import urljoin

import numpy as np

try:
    import requests
except Exception:  # pragma: no cover - surfaced as a clear runtime failure
    requests = None

try:
    import soundfile as sf
except Exception:  # pragma: no cover - surfaced as a clear runtime failure
    sf = None

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class GenerationResult:
    success: bool
    output_path: str | None
    generator_name: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    error_message: str | None = None
    logs: list[str] | None = None
    command_used: str | None = None
    suggested_fix: str | None = None
    metadata: dict[str, Any] | None = None


def health_check(
    *,
    mode: str = "cli",
    cli_path: str | None = None,
    output_dir: str | Path = "outputs/ace_step",
) -> dict[str, Any]:
    resolved_output_dir = resolve_output_dir(output_dir)
    diagnostics: dict[str, Any] = {"resolved_output_dir": str(resolved_output_dir)}
    normalized_mode = (mode or "cli").strip().lower()
    command_head = _command_head(cli_path)

    if normalized_mode != "cli":
        return {
            "available": False,
            "mode": normalized_mode,
            "cli_path": cli_path or "",
            "output_dir": str(resolved_output_dir),
            "message": f"ACE-Step mode '{normalized_mode}' is not supported in Phase 4.",
            "diagnostics": diagnostics,
        }

    available = _command_available(command_head)
    diagnostics["command_head"] = command_head
    if available:
        message = "ACE-Step CLI mode is configured. Generation will be attempted when enabled."
    else:
        message = "ACE-Step CLI command was not found. Check ACE_STEP_CLI_PATH or the Python environment."

    return {
        "available": available,
        "mode": normalized_mode,
        "cli_path": cli_path or "",
        "output_dir": str(resolved_output_dir),
        "message": message,
        "diagnostics": diagnostics,
    }


def generate_song(
    positive_prompt: str,
    negative_prompt: str,
    lyrics: str | None,
    duration_seconds: int | None,
    bpm: int | None,
    key: str | None,
    output_dir: str | Path,
    job_id: str,
    timeout_seconds: int,
    *,
    mode: str = "cli",
    cli_path: str | None = None,
    device: str | None = "cuda",
    output_format: str = "wav",
) -> GenerationResult:
    started_at = _now()
    resolved_output_dir = resolve_output_dir(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = resolved_output_dir / f"{_safe_name(job_id)}.{_normalize_format(output_format)}"
    command = build_command(
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        lyrics=lyrics,
        duration_seconds=duration_seconds,
        bpm=bpm,
        key=key,
        output_path=output_path,
        cli_path=cli_path,
        device=device,
    )
    command_used = _command_for_display(command)

    normalized_mode = (mode or "cli").strip().lower()
    if normalized_mode != "cli":
        return _failure_result(
            started_at,
            output_path,
            command_used,
            f"ACE-Step mode '{normalized_mode}' is not supported in Phase 4.",
            ["Only ACE_STEP_MODE=cli is implemented in this phase."],
            "Set ACE_STEP_MODE=cli or ACE_STEP_ENABLED=false to return to mock mode.",
        )

    if not _command_available(command[0]):
        return _failure_result(
            started_at,
            output_path,
            command_used,
            f"ACE-Step CLI command was not found: {command[0]}",
            [],
            "Check ACE_STEP_CLI_PATH or verify the ACE-Step environment is installed.",
        )

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logs = _logs_from_output(exc.stdout, exc.stderr)
        return _failure_result(
            started_at,
            output_path,
            command_used,
            f"ACE-Step generation timed out after {timeout_seconds} seconds.",
            logs,
            "Increase ACE_STEP_TIMEOUT_SECONDS or try a shorter duration.",
        )
    except Exception as exc:
        return _failure_result(
            started_at,
            output_path,
            command_used,
            f"ACE-Step generation could not start: {exc}",
            [],
            "Check ACE_STEP_CLI_PATH, model weights, and the active Python environment.",
        )

    logs = _logs_from_output(completed.stdout, completed.stderr)
    if completed.returncode != 0:
        return _failure_result(
            started_at,
            output_path,
            command_used,
            f"ACE-Step exited with code {completed.returncode}.",
            logs,
            "Verify ACE-Step environment and model weights, then try a shorter duration.",
        )

    if not output_path.exists():
        return _failure_result(
            started_at,
            output_path,
            command_used,
            "ACE-Step completed but did not create the expected output file.",
            logs,
            "Check the ACE-Step output flag mapping in app/generators/ace_step.py.",
        )

    finished_at = _now()
    return GenerationResult(
        success=True,
        output_path=str(output_path),
        generator_name="ACE-Step",
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=(finished_at - started_at).total_seconds(),
        logs=logs[-40:],
        command_used=command_used,
    )


def transform_reference_audio(
    *,
    source_audio_path: str | Path,
    prompt: str,
    negative_prompt: str,
    output_dir: str | Path,
    job_id: str,
    timeout_seconds: int,
    base_url: str = "http://127.0.0.1:8001",
    api_key: str | None = None,
    model: str | None = None,
    inference_steps: int = 8,
    guidance_scale: float = 1.0,
    poll_interval_seconds: float = 2.0,
    reference_strength: float = 0.35,
    bpm: int | None = None,
    key: str | None = None,
    duration_seconds: float | None = None,
) -> GenerationResult:
    """Create new music from a reference track with ACE-Step cover conditioning."""
    started_at = _now()
    resolved_output_dir = resolve_output_dir(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = resolved_output_dir / f"{_safe_name(job_id)}_music_to_music.wav"
    source = Path(source_audio_path).resolve()
    logs = ["ACE-Step reference-conditioned music-to-music generation requested."]
    command_used = f"POST {base_url.rstrip('/')}/release_task task_type=cover"

    if not source.is_file():
        return _failure_result(
            started_at,
            output_path,
            command_used,
            "A readable music reference is required for music-to-music generation.",
            logs,
            "Upload a valid WAV or normalized reference track and retry.",
        )
    if requests is None:
        return _failure_result(
            started_at,
            output_path,
            command_used,
            "The requests package is required for ACE-Step music-to-music generation.",
            logs,
            "Install the backend requirements and restart Skarly.",
        )

    root = base_url.rstrip("/") + "/"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    strength = _clamp(float(reference_strength), 0.05, 0.95)
    stable_seed = int(hashlib.sha256(f"{job_id}|{source}|{prompt}".encode("utf-8")).hexdigest()[:8], 16)
    payload: dict[str, Any] = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "lyrics": "[Instrumental]",
        "task_type": "cover",
        "audio_cover_strength": strength,
        "audio_format": "wav",
        "inference_steps": max(1, int(inference_steps or 8)),
        "guidance_scale": float(guidance_scale or 1.0),
        "batch_size": 1,
        "use_random_seed": False,
        "seed": stable_seed,
        "thinking": False,
        "use_cot_caption": False,
        "use_cot_language": False,
        "use_cot_metas": False,
    }
    if model:
        payload["model"] = model
    if bpm:
        payload["bpm"] = int(bpm)
    if key:
        payload["key_scale"] = key
    if duration_seconds:
        payload["audio_duration"] = round(max(3.0, float(duration_seconds)), 6)

    try:
        request_timeout = min(600, max(120, int(timeout_seconds)))
        with source.open("rb") as handle:
            release = requests.post(
                urljoin(root, "release_task"),
                headers=headers,
                data=payload,
                files={"src_audio": (source.name, handle, "audio/wav")},
                timeout=request_timeout,
            )
        if release.status_code >= 400:
            raise RuntimeError(f"ACE-Step release failed: {release.status_code} {release.text[:240]}")
        task_id = _extract_task_id(release.json())
        if not task_id:
            raise RuntimeError("ACE-Step music-to-music response did not include a task id")
        logs.append(f"ACE-Step task {task_id} queued with reference strength {strength:.2f}.")
        task_result = _poll_ace_step(
            root,
            task_id,
            headers,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        audio_url = _extract_audio_url(task_result)
        if not audio_url:
            raise RuntimeError("ACE-Step music-to-music result did not include an audio URL")
        endpoint = urljoin(root, audio_url.lstrip("/")) if not audio_url.startswith("http") else audio_url
        audio_response = requests.get(endpoint, headers=headers, timeout=max(120, int(timeout_seconds)))
        if audio_response.status_code >= 400:
            raise RuntimeError(
                f"ACE-Step music-to-music download failed: {audio_response.status_code} "
                f"{audio_response.text[:240]}"
            )
        if not audio_response.content:
            raise RuntimeError("ACE-Step music-to-music download was empty")
        output_path.write_bytes(audio_response.content)
    except Exception as exc:
        return _failure_result(
            started_at,
            output_path,
            command_used,
            f"ACE-Step music-to-music generation failed: {exc}",
            logs,
            "Confirm ACE-Step is running with cover support, then retry or use another provider.",
        )

    finished_at = _now()
    return GenerationResult(
        success=True,
        output_path=str(output_path),
        generator_name="ACE-Step music-to-music",
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=(finished_at - started_at).total_seconds(),
        logs=[*logs, "Reference-conditioned transformation completed."][-40:],
        command_used=command_used,
        metadata={
            "task_type": "cover",
            "reference_conditioned": True,
            "reference_strength": strength,
            "seed": stable_seed,
        },
    )


def edit_section(
    *,
    source_audio_path: str | None,
    section_name: str,
    edit_prompt: str,
    output_dir: str | Path,
    job_id: str,
    timeout_seconds: int,
    section_start_seconds: float | None = None,
    section_end_seconds: float | None = None,
    mode: str = "cli",
    cli_path: str | None = None,
    output_format: str = "wav",
    base_url: str = "http://127.0.0.1:8001",
    api_key: str | None = None,
    model: str | None = None,
    inference_steps: int = 8,
    guidance_scale: float = 1.0,
    poll_interval_seconds: float = 2.0,
    repaint_mode: str = "balanced",
    repaint_strength: float = 0.65,
    bpm: int | None = None,
    key: str | None = None,
    language: str | None = None,
    duration_seconds: float | None = None,
    boundary_crossfade_seconds: float = 0.025,
) -> GenerationResult:
    started_at = _now()
    resolved_output_dir = resolve_output_dir(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = resolved_output_dir / f"{_safe_name(job_id)}_{_safe_name(section_name)}.{_normalize_format(output_format)}"
    source = Path(source_audio_path).resolve() if source_audio_path else None
    logs = ["ACE-Step repaint section edit requested."]
    command_used = f"POST {base_url.rstrip('/')}/release_task task_type=repaint"

    if source is None or not source.is_file():
        return _failure_result(
            started_at,
            output_path,
            command_used,
            "A readable source instrumental is required for section regeneration.",
            logs,
            "Pass the selected Skarly version's backing WAV as source_audio_path.",
        )
    if section_start_seconds is None or section_end_seconds is None:
        return _failure_result(
            started_at,
            output_path,
            command_used,
            "Section regeneration requires both section_start_seconds and section_end_seconds.",
            logs,
            "Choose a non-empty range inside the source instrumental.",
        )
    try:
        source_info = _audio_info(source)
        source_duration = float(source_info["duration_seconds"])
    except Exception as exc:
        return _failure_result(
            started_at,
            output_path,
            command_used,
            f"Could not read the source instrumental: {exc}",
            logs,
            "Use a valid WAV, FLAC, MP3, M4A, or AAC instrumental.",
        )
    start = float(section_start_seconds)
    end = float(section_end_seconds)
    if start < 0 or end <= start or end > source_duration + 0.01:
        return _failure_result(
            started_at,
            output_path,
            command_used,
            f"Invalid section range {start:.3f}-{end:.3f}s for {source_duration:.3f}s audio.",
            logs,
            "Choose a non-empty section fully inside the instrumental duration.",
        )
    if requests is None:
        return _failure_result(
            started_at,
            output_path,
            command_used,
            "The requests package is required for ACE-Step repaint mode.",
            logs,
            "Install the backend requirements and restart Skarly.",
        )

    root = base_url.rstrip("/") + "/"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    stable_seed = int(hashlib.sha256(f"{job_id}|{section_name}|{start:.6f}|{end:.6f}|{edit_prompt}".encode("utf-8")).hexdigest()[:8], 16)
    payload: dict[str, Any] = {
        "prompt": edit_prompt,
        "lyrics": "[Instrumental]",
        "task_type": "repaint",
        "audio_duration": round(float(duration_seconds or source_duration), 6),
        "repainting_start": round(start, 6),
        "repainting_end": round(end, 6),
        "chunk_mask_mode": "explicit",
        "repaint_mode": _normalize_repaint_mode(repaint_mode),
        "repaint_strength": _clamp(float(repaint_strength), 0.0, 1.0),
        "audio_format": "wav",
        "inference_steps": max(1, int(inference_steps or 8)),
        "guidance_scale": float(guidance_scale or 1.0),
        "batch_size": 1,
        "use_random_seed": False,
        "seed": stable_seed,
        "thinking": False,
        "use_cot_caption": False,
        "use_cot_language": False,
        "use_cot_metas": False,
        "vocal_language": _ace_language_code(language),
    }
    if model:
        payload["model"] = model
    if bpm:
        payload["bpm"] = int(bpm)
    if key:
        payload["key_scale"] = key

    generated_path: Path | None = None
    try:
        logs.append(f"Submitting repaint for {start:.3f}-{end:.3f}s of {source_duration:.3f}s source audio.")
        request_timeout = min(600, max(120, int(timeout_seconds)))
        with source.open("rb") as handle:
            release = requests.post(
                urljoin(root, "release_task"),
                headers=headers,
                data=payload,
                files={"ctx_audio": (source.name, handle, "audio/wav")},
                timeout=request_timeout,
            )
        if release.status_code >= 400:
            raise RuntimeError(f"ACE-Step release failed: {release.status_code} {release.text[:240]}")
        task_id = _extract_task_id(release.json())
        if not task_id:
            raise RuntimeError("ACE-Step repaint response did not include a task id")
        logs.append(f"ACE-Step task {task_id} queued.")
        task_result = _poll_ace_step(
            root,
            task_id,
            headers,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        audio_url = _extract_audio_url(task_result)
        if not audio_url:
            raise RuntimeError("ACE-Step repaint result did not include an audio URL")
        audio_endpoint = urljoin(root, audio_url.lstrip("/")) if not audio_url.startswith("http") else audio_url
        audio_response = requests.get(audio_endpoint, headers=headers, timeout=max(120, int(timeout_seconds)))
        if audio_response.status_code >= 400:
            raise RuntimeError(f"ACE-Step repaint download failed: {audio_response.status_code} {audio_response.text[:240]}")
        if not audio_response.content:
            raise RuntimeError("ACE-Step repaint download was empty")
        with tempfile.NamedTemporaryFile(prefix="skarly_repaint_", suffix=".wav", delete=False) as temp_file:
            temp_file.write(audio_response.content)
            generated_path = Path(temp_file.name)
        splice = _splice_repaint_region(
            source_path=source,
            generated_path=generated_path,
            output_path=output_path,
            start_seconds=start,
            end_seconds=end,
            boundary_crossfade_seconds=boundary_crossfade_seconds,
        )
        logs.extend(
            [
                "Skarly restored the original instrumental outside the selected section.",
                f"section_changed={splice['section_changed']}",
                f"outside_max_abs_error={splice['outside_max_abs_error']:.10f}",
            ]
        )
        if not splice["preserved_outside_section"]:
            raise RuntimeError("Section repaint failed the outside-region preservation check")
        if not splice["section_changed"]:
            raise RuntimeError("ACE-Step repaint did not materially change the selected section")
    except Exception as exc:
        return _failure_result(
            started_at,
            output_path,
            command_used,
            f"ACE-Step section repaint failed: {exc}",
            logs,
            "Confirm ACE-Step is running with repaint support, then retry a section of at least one second.",
        )
    finally:
        if generated_path is not None:
            generated_path.unlink(missing_ok=True)

    finished_at = _now()
    return GenerationResult(
        success=True,
        output_path=str(output_path),
        generator_name="ACE-Step repaint",
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=(finished_at - started_at).total_seconds(),
        logs=logs[-40:],
        command_used=command_used,
        metadata={
            **splice,
            "task_type": "repaint",
            "source_duration_seconds": source_duration,
            "output_duration_seconds": float(splice["output_duration_seconds"]),
            "section_start_seconds": start,
            "section_end_seconds": end,
            "repaint_mode": payload["repaint_mode"],
            "repaint_strength": payload["repaint_strength"],
            "seed": stable_seed,
            "cpu_fallback": False,
        },
    )


def _audio_info(path: Path) -> dict[str, Any]:
    if sf is None:
        raise RuntimeError("soundfile is not installed")
    info = sf.info(str(path))
    if info.frames <= 0 or info.samplerate <= 0:
        raise RuntimeError("audio has no decodable frames")
    return {
        "duration_seconds": float(info.frames) / float(info.samplerate),
        "frames": int(info.frames),
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "subtype": str(info.subtype or "FLOAT"),
    }


def _splice_repaint_region(
    *,
    source_path: Path,
    generated_path: Path,
    output_path: Path,
    start_seconds: float,
    end_seconds: float,
    boundary_crossfade_seconds: float,
) -> dict[str, Any]:
    """Replace only the selected source interval and verify decoded preservation."""
    if sf is None:
        raise RuntimeError("soundfile is not installed")
    source, source_rate = sf.read(str(source_path), dtype="float32", always_2d=True)
    generated, generated_rate = sf.read(str(generated_path), dtype="float32", always_2d=True)
    if source.size == 0 or generated.size == 0:
        raise RuntimeError("source or generated repaint audio is empty")
    if generated_rate != source_rate:
        generated = _resample_audio(generated, generated_rate, source_rate)
    generated = _match_channels(generated, source.shape[1])
    if generated.shape[0] < source.shape[0]:
        generated = np.pad(generated, ((0, source.shape[0] - generated.shape[0]), (0, 0)))
    elif generated.shape[0] > source.shape[0]:
        generated = generated[: source.shape[0]]

    start_frame = max(0, min(source.shape[0], int(round(start_seconds * source_rate))))
    end_frame = max(start_frame, min(source.shape[0], int(round(end_seconds * source_rate))))
    if end_frame <= start_frame:
        raise RuntimeError("selected repaint interval has no audio frames")
    output = source.copy()
    output[start_frame:end_frame] = generated[start_frame:end_frame]
    fade_frames = min(
        max(0, int(round(float(boundary_crossfade_seconds) * source_rate))),
        (end_frame - start_frame) // 2,
    )
    if fade_frames > 0:
        fade_in = np.linspace(0.0, 1.0, fade_frames, endpoint=False, dtype=np.float32)[:, None]
        fade_out = np.linspace(1.0, 0.0, fade_frames, endpoint=False, dtype=np.float32)[:, None]
        output[start_frame : start_frame + fade_frames] = (
            source[start_frame : start_frame + fade_frames] * (1.0 - fade_in)
            + generated[start_frame : start_frame + fade_frames] * fade_in
        )
        tail_start = end_frame - fade_frames
        output[tail_start:end_frame] = (
            source[tail_start:end_frame] * (1.0 - fade_out)
            + generated[tail_start:end_frame] * fade_out
        )

    subtype = _safe_output_subtype(str(sf.info(str(source_path)).subtype or "FLOAT"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output_path.with_name(f".{output_path.stem}.writing{output_path.suffix}")
    sf.write(str(temp_output), output, source_rate, format="WAV", subtype=subtype)
    temp_output.replace(output_path)

    decoded, decoded_rate = sf.read(str(output_path), dtype="float32", always_2d=True)
    if decoded_rate != source_rate or decoded.shape != source.shape:
        raise RuntimeError("spliced output changed sample rate, channel count, or duration")
    outside_error = 0.0
    if start_frame:
        outside_error = max(outside_error, float(np.max(np.abs(decoded[:start_frame] - source[:start_frame]))))
    if end_frame < source.shape[0]:
        outside_error = max(outside_error, float(np.max(np.abs(decoded[end_frame:] - source[end_frame:]))))
    section_delta = float(np.mean(np.abs(decoded[start_frame:end_frame] - source[start_frame:end_frame])))
    preservation_tolerance = 1e-7 if subtype in {"FLOAT", "DOUBLE"} else 1.0 / 32768.0
    return {
        "preserved_outside_section": outside_error <= preservation_tolerance,
        "section_changed": section_delta > max(preservation_tolerance * 2.0, 1e-5),
        "outside_max_abs_error": outside_error,
        "section_mean_abs_delta": section_delta,
        "preservation_tolerance": preservation_tolerance,
        "boundary_crossfade_seconds": float(boundary_crossfade_seconds),
        "sample_rate": int(source_rate),
        "channels": int(source.shape[1]),
        "source_frames": int(source.shape[0]),
        "output_frames": int(decoded.shape[0]),
        "output_duration_seconds": float(decoded.shape[0]) / float(source_rate),
    }


def _resample_audio(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    from scipy.signal import resample_poly

    divisor = math.gcd(int(source_rate), int(target_rate))
    return np.asarray(
        resample_poly(audio, target_rate // divisor, source_rate // divisor, axis=0),
        dtype=np.float32,
    )


def _match_channels(audio: np.ndarray, channels: int) -> np.ndarray:
    if audio.shape[1] == channels:
        return audio
    if audio.shape[1] == 1 and channels > 1:
        return np.repeat(audio, channels, axis=1)
    if channels == 1:
        return np.mean(audio, axis=1, keepdims=True, dtype=np.float32)
    if audio.shape[1] > channels:
        return audio[:, :channels]
    return np.pad(audio, ((0, 0), (0, channels - audio.shape[1])), mode="edge")


def _safe_output_subtype(subtype: str) -> str:
    return subtype if subtype in {"PCM_16", "PCM_24", "PCM_32", "FLOAT", "DOUBLE"} else "FLOAT"


def _poll_ace_step(
    root: str,
    task_id: str,
    headers: dict[str, str],
    *,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> Any:
    deadline = time.monotonic() + max(1, int(timeout_seconds))
    last: Any = None
    while time.monotonic() < deadline:
        response = requests.post(
            urljoin(root, "query_result"),
            headers=headers,
            json={"task_id_list": [task_id]},
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"ACE-Step query failed: {response.status_code} {response.text[:240]}")
        last = response.json()
        task = _extract_task_result(last, task_id) or last
        status = str(task.get("status") or task.get("state") or task.get("task_status") or "").lower()
        if status in {"2", "failed", "error", "canceled", "cancelled"}:
            raise RuntimeError(f"ACE-Step repaint task failed: {last}")
        decoded = _decode_ace_step_result(task)
        if status in {"1", "completed", "complete", "done", "succeeded", "success", "finished"} or _extract_audio_url(decoded):
            return decoded
        time.sleep(max(0.25, float(poll_interval_seconds or 2.0)))
    raise RuntimeError(f"ACE-Step repaint timed out after {timeout_seconds} seconds: {last}")


def _extract_task_id(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    for key_name in ("task_id", "taskId", "id"):
        value = data.get(key_name)
        if isinstance(value, str) and value:
            return value
    for nested_name in ("data", "result"):
        nested = data.get(nested_name)
        if isinstance(nested, dict):
            found = _extract_task_id(nested)
            if found:
                return found
    return None


def _extract_task_result(data: Any, task_id: str) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    candidates = data.get("data")
    if isinstance(candidates, list):
        for item in candidates:
            if isinstance(item, dict) and item.get("task_id") == task_id:
                return item
        return next((item for item in candidates if isinstance(item, dict)), None)
    return candidates if isinstance(candidates, dict) else None


def _decode_ace_step_result(data: Any) -> Any:
    if not isinstance(data, dict) or not isinstance(data.get("result"), str):
        return data
    try:
        return json.loads(data["result"])
    except (TypeError, json.JSONDecodeError):
        return data


def _extract_audio_url(data: Any) -> str | None:
    if isinstance(data, dict):
        for key_name in ("audio_url", "audioUrl", "url", "path", "file", "wave", "output_path", "file_url", "download_url"):
            value = data.get(key_name)
            if isinstance(value, str) and value:
                return value
        for value in data.values():
            found = _extract_audio_url(value)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _extract_audio_url(item)
            if found:
                return found
    elif isinstance(data, str):
        text = data.strip()
        if text.startswith(("{", "[")):
            try:
                return _extract_audio_url(json.loads(text))
            except (TypeError, json.JSONDecodeError):
                return None
        if text.startswith(("http", "/")) or text.endswith((".wav", ".mp3", ".flac")):
            return text
    return None


def _ace_language_code(language: str | None) -> str:
    normalized = " ".join(str(language or "").lower().replace("-", " ").split())
    return {
        "hindi": "hi",
        "hinglish": "hi",
        "hi": "hi",
        "urdu": "ur",
        "punjabi": "pa",
        "tamil": "ta",
        "telugu": "te",
        "bengali": "bn",
    }.get(normalized, "en")


def _normalize_repaint_mode(value: str) -> str:
    normalized = str(value or "balanced").strip().lower()
    return normalized if normalized in {"conservative", "balanced", "aggressive"} else "balanced"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def build_command(
    *,
    positive_prompt: str,
    negative_prompt: str,
    lyrics: str | None,
    duration_seconds: int | None,
    bpm: int | None,
    key: str | None,
    output_path: str | Path,
    cli_path: str | None = None,
    device: str | None = "cuda",
) -> list[str]:
    base_command = _base_command(cli_path)
    command = [
        *base_command,
        "--prompt",
        positive_prompt,
        "--negative_prompt",
        negative_prompt,
        "--output",
        str(output_path),
    ]
    if lyrics:
        command.extend(["--lyrics", lyrics])
    if duration_seconds:
        command.extend(["--duration", str(duration_seconds)])
    if bpm:
        command.extend(["--bpm", str(bpm)])
    if key:
        command.extend(["--key", key])
    if device:
        command.extend(["--device", device])

    # ACE-Step CLI packaging differs by install. Keep all CLI flag adaptation here.
    # For example, change the base command to an executable path via ACE_STEP_CLI_PATH,
    # or adjust flag names here if your ACE-Step checkout exposes a different CLI.
    return command


def resolve_output_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()


def _base_command(cli_path: str | None) -> list[str]:
    if cli_path and cli_path.strip():
        raw = cli_path.strip()
        path_candidate = Path(raw.strip("\"'"))
        if path_candidate.exists():
            return [str(path_candidate)]
        return shlex.split(raw)
    return [sys.executable, "-m", "acestep.generate"]


def _command_head(cli_path: str | None) -> str:
    return _base_command(cli_path)[0]


def _command_available(command_head: str) -> bool:
    if Path(command_head).is_file():
        return True
    return shutil.which(command_head) is not None


def _failure_result(
    started_at: datetime,
    output_path: Path,
    command_used: str,
    error_message: str,
    logs: list[str],
    suggested_fix: str,
) -> GenerationResult:
    finished_at = _now()
    return GenerationResult(
        success=False,
        output_path=str(output_path) if output_path else None,
        generator_name="ACE-Step",
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=(finished_at - started_at).total_seconds(),
        error_message=error_message,
        logs=logs[-40:],
        command_used=command_used,
        suggested_fix=suggested_fix,
    )


def _logs_from_output(stdout: Any, stderr: Any) -> list[str]:
    logs: list[str] = []
    for value in (stdout, stderr):
        if value is None:
            continue
        if isinstance(value, bytes):
            text = value.decode("utf-8", errors="replace")
        else:
            text = str(value)
        logs.extend(line.strip() for line in text.splitlines() if line.strip())
    return logs


def _command_for_display(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _normalize_format(output_format: str) -> str:
    normalized = (output_format or "wav").strip().lower().lstrip(".")
    return normalized if normalized in {"wav", "mp3"} else "wav"


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)[:120] or "ace_step_output"


def _now() -> datetime:
    return datetime.now(timezone.utc)
