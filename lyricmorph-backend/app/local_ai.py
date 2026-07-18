from __future__ import annotations

import ctypes
import os
import platform
import shlex
import shutil
import subprocess
from typing import Any

from .config import settings

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


def local_capabilities() -> dict[str, Any]:
    return {
        "system": system_snapshot(),
        "gpu": gpu_snapshot(),
        "audio": {
            "ffmpeg_path": resolved_executable(settings.ffmpeg_path),
            "ffmpeg_available": executable_available(settings.ffmpeg_path),
            "music_generator_backend": settings.music_generator_backend,
            "stem_separator_backend": settings.stem_separator_backend,
            "melody_analyzer_backend": settings.melody_analyzer_backend,
            "demucs_path": settings.demucs_path,
            "demucs_available": executable_available(settings.demucs_path),
            "basic_pitch_path": settings.basic_pitch_path,
            "basic_pitch_available": executable_available(settings.basic_pitch_path),
        },
        "ai": local_ai_snapshot(),
        "model_stack": model_stack_snapshot(),
        "prototype_mode": {
            "storage_backend": settings.storage_backend,
            "repository_backend": settings.repository_backend,
        },
        "timeouts": {
            "analysis_timeout_sec": settings.analysis_timeout_sec,
            "separation_timeout_sec": settings.separation_timeout_sec,
            "melody_timeout_sec": settings.melody_timeout_sec,
            "backing_generation_timeout_sec": settings.backing_generation_timeout_sec,
            "mixing_timeout_sec": settings.mixing_timeout_sec,
            "export_timeout_sec": settings.export_timeout_sec,
            "studio_poll_timeout_sec": settings.studio_poll_timeout_sec,
        },
    }


def agent_generation_plan(payload: dict[str, Any]) -> dict[str, Any]:
    genre = str(payload.get("genre") or "Lo-fi")
    production_style = str(payload.get("production_style") or genre)
    arrangement_style = str(payload.get("arrangement_style") or "")
    source_type = str(payload.get("source_type") or "recording")
    arrangement_mode = str(payload.get("arrangement_mode") or "vocal_to_song")
    duration = int(float(payload.get("duration_seconds") or 30))
    prompt = (
        "You are the local Skarly studio agent. Create a concise production plan "
        f"for a {duration}s {production_style} track using compatible genre {genre} from source type {source_type} "
        f"in arrangement mode {arrangement_mode}. Arrangement: {arrangement_style or 'infer from style'}. "
        "Mention arrangement, mix focus, and quality checks."
    )

    llm_text = ask_local_llm(prompt)
    if llm_text:
        return {"mode": "local_llm", "plan": llm_text, "model": settings.local_llm_model}

    plan = fallback_plan(genre, source_type, duration, arrangement_mode, production_style, arrangement_style)
    return {"mode": "rule_agent", "plan": plan, "model": None}


def fallback_plan(
    genre: str,
    source_type: str,
    duration: int,
    arrangement_mode: str = "vocal_to_song",
    production_style: str | None = None,
    arrangement_style: str | None = None,
) -> str:
    if arrangement_mode == "music_to_music":
        source_note = "Use the upload as a music reference only; create a fresh instrumental and do not mix the old instrumental back into the final."
    elif arrangement_mode == "full_song":
        source_note = "Treat the upload as a full song; isolate the vocal when available, then build a new arrangement around the lead source."
    elif source_type == "recording":
        source_note = "Use the recording directly as the lead vocal timing source."
    else:
        source_note = "Treat the upload as vocal-first; isolate vocals when available before creating the new backing."
    genre_notes = {
        "Lo-fi": "soft drums, warm keys, relaxed bass, low-detail lead accents",
        "Piano": "felt piano chords, light bass, wide room ambience",
        "Pop": "clean four-on-floor pulse, bright bass, short synth stabs",
        "Rock": "steady kick/snare, bass movement, restrained distorted rhythm texture",
        "R&B": "half-time drums, sub bass, airy keys, open midrange",
        "Hip-hop": "808-style bass movement, crisp hats, sparse melodic motif",
        "Acoustic": "fingerpicked guitar feel, soft percussion, warm bass",
        "Cinematic": "low strings, piano pulses, subtle phrase-ending drums",
    }
    style = genre_notes.get(genre, "supportive rhythm bed and simple chord movement")
    style_label = production_style or genre
    arrangement_text = f" with a {arrangement_style} arrangement" if arrangement_style else ""
    return (
        f"Plan: create a {duration}s {style_label} backing{arrangement_text} using {style}. "
        f"{source_note} Use section changes, drum fills, guitar or key movement, and separate stem exports. "
        "Limit the final mix, then check source preview, backing-only preview, instrument stems, and final MP3."
    )


def local_ai_snapshot() -> dict[str, Any]:
    ollama_path = shutil.which("ollama")
    server = False
    models: list[str] = []
    if requests is not None:
        try:
            response = requests.get(f"{settings.local_llm_base_url.rstrip('/')}/api/tags", timeout=1.0)
            server = response.ok
            if response.ok:
                models = [str(item.get("name")) for item in response.json().get("models", []) if item.get("name")]
        except Exception:
            server = False
    return {
        "ollama_path": ollama_path,
        "ollama_server": server,
        "configured_base_url": settings.local_llm_base_url,
        "configured_model": settings.local_llm_model,
        "available_models": models,
        "agent_fallback": "rule_agent",
    }


def model_stack_snapshot() -> dict[str, Any]:
    return {
        "ace_step": {
            "role": "primary vocal-to-music generator",
            "base_url": settings.ace_step_base_url,
            "api_command": settings.ace_step_api_command,
            "api_command_available": executable_available(settings.ace_step_api_command),
            "send_source_audio": settings.ace_step_use_source_audio,
            "send_lyrics": settings.ace_step_send_lyrics,
        },
        "audiocraft": {
            "role": "optional research backend",
            "status": settings.audiocraft_backend_status,
            "local_repo": os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "skarly-ai-repos", "audiocraft")),
            "note": "Local build status says AudioCraft is blocked on Windows by native av/FFmpeg development libraries; ACE-Step remains the enabled path.",
        },
        "demucs": {
            "role": "vocal isolation and backing cleanup",
            "path": settings.demucs_path,
            "available": executable_available(settings.demucs_path),
            "model": settings.demucs_model,
            "device": settings.demucs_device,
            "timeout_seconds": settings.separation_timeout_sec,
        },
        "basic_pitch": {
            "role": "melody/MIDI analysis",
            "path": settings.basic_pitch_path,
            "available": executable_available(settings.basic_pitch_path),
        },
    }


def ask_local_llm(prompt: str) -> str | None:
    if requests is None:
        return None
    try:
        response = requests.post(
            f"{settings.local_llm_base_url.rstrip('/')}/api/generate",
            json={"model": settings.local_llm_model, "prompt": prompt, "stream": False},
            timeout=8,
        )
    except Exception:
        return None
    if not response.ok:
        return None
    text = str(response.json().get("response") or "").strip()
    return text or None


def system_snapshot() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "memory_total_gb": round(total_memory_bytes() / (1024**3), 2) if total_memory_bytes() else None,
    }


def total_memory_bytes() -> int:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return int(status.ullTotalPhys)
    return 0


def gpu_snapshot() -> dict[str, Any]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return {"nvidia_smi": None, "gpus": []}
    try:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
    except Exception:
        return {"nvidia_smi": nvidia_smi, "gpus": []}
    gpus = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 3:
            gpus.append({"name": parts[0], "memory_total": parts[1], "driver_version": parts[2]})
    return {"nvidia_smi": nvidia_smi, "gpus": gpus}


def executable_available(value: str) -> bool:
    return bool(resolved_executable(value))


def resolved_executable(value: str) -> str | None:
    if not value:
        return None
    parts = shlex.split(value, posix=os.name != "nt")
    if len(parts) > 1:
        value = parts[0]
    if shutil.which(value):
        return shutil.which(value)
    if os.path.exists(value):
        return value
    return None
