from __future__ import annotations

from pathlib import Path
import os
import shlex
import shutil
from typing import Any

from ..models import AppHealthResponse
from . import safe_paths


def build_full_health(
    settings: Any,
    *,
    output_dirs: dict[str, str | Path],
    version: str = "0.10.0",
) -> AppHealthResponse:
    checks: dict[str, dict[str, Any]] = {
        "app": {"ok": True, "message": "Application is running."},
        "config": {"ok": True, "message": "Configuration loaded."},
    }
    warnings: list[str] = []

    for name, directory in output_dirs.items():
        check = _writable_dir_check(directory)
        checks[f"dir:{name}"] = check
        if not check["ok"]:
            warnings.append(f"Output directory is not writable: {name}")

    ace_enabled = bool(getattr(settings, "ace_step_enabled", False))
    ace_cli_path = getattr(settings, "ace_step_cli_path", "")
    checks["ace_step"] = {
        "ok": (not ace_enabled) or _command_available(_command_head(ace_cli_path) if ace_cli_path else "python"),
        "enabled": ace_enabled,
        "mode": getattr(settings, "ace_step_mode", "cli"),
        "message": "ACE-Step is disabled." if not ace_enabled else "ACE-Step generation will be attempted when configured.",
    }
    if ace_enabled and not checks["ace_step"]["ok"]:
        warnings.append("ACE-Step is enabled but its command was not found.")

    checks["procedural_fallback"] = {
        "ok": True,
        "enabled": bool(getattr(settings, "procedural_fallback_enabled", True)),
        "output_dir": getattr(settings, "procedural_output_dir", None),
    }
    checks["mixer"] = {
        "ok": True,
        "output_dir": getattr(settings, "mix_output_dir", None),
        "preview_format": getattr(settings, "mix_preview_format", None),
    }
    checks["producer_assistant"] = {
        "ok": True,
        "enabled": bool(getattr(settings, "producer_assistant_enabled", True)),
        "mode": getattr(settings, "producer_assistant_mode", "rules"),
    }
    online_enabled = bool(getattr(settings, "online_music_enabled", True))
    eleven_key = bool(getattr(settings, "elevenlabs_api_key", None))
    gemini_key = bool(getattr(settings, "gemini_api_key", None))
    checks["online_music"] = {
        "ok": True,
        "enabled": online_enabled,
        "primary": getattr(settings, "music_provider_primary", "elevenlabs"),
        "secondary": getattr(settings, "music_provider_secondary", "lyria"),
        "elevenlabs_configured": eleven_key,
        "lyria_configured": gemini_key,
        "candidate_count": getattr(settings, "generate_candidate_count", 3),
        "message": (
            "Online providers configured."
            if online_enabled and (eleven_key or gemini_key)
            else "Online generation will use local_fallback until provider API keys are configured."
            if online_enabled
            else "Online music generation is disabled."
        ),
    }
    if online_enabled and not (eleven_key or gemini_key):
        warnings.append("No online music provider API key is configured; v2 generation will use local_fallback.")
    checks["stems"] = {
        "ok": True,
        "enabled": bool(getattr(settings, "stems_enabled", True)),
        "engine": getattr(settings, "stems_engine", "demucs"),
    }
    checks["section_editing"] = {
        "ok": True,
        "enabled": bool(getattr(settings, "section_editing_enabled", True)),
        "mode": getattr(settings, "section_editing_mode", "ace_step"),
    }

    ffmpeg = getattr(settings, "ffmpeg_path", "ffmpeg")
    checks["ffmpeg"] = _tool_check(ffmpeg, optional=True)
    if not checks["ffmpeg"]["available"]:
        warnings.append("FFmpeg was not found; MP3 export may fall back to WAV.")

    demucs = getattr(settings, "demucs_cli_path", None) or getattr(settings, "demucs_path", "demucs")
    checks["demucs"] = _tool_check(demucs, optional=True)
    if not checks["demucs"]["available"]:
        warnings.append("Demucs was not found; stem separation will report unavailable until configured.")

    disk = _disk_check(output_dirs)
    checks["disk"] = disk
    if not disk["ok"]:
        warnings.append("Could not inspect disk space.")

    required_ok = all(check["ok"] for key, check in checks.items() if key.startswith("dir:") or key in {"app", "config"})
    status = "ok" if required_ok else "degraded"
    return AppHealthResponse(status=status, app_env=getattr(settings, "app_env", "local"), version=version, checks=checks, warnings=_dedupe(warnings))


def _writable_dir_check(directory: str | Path) -> dict[str, Any]:
    try:
        path = safe_paths.resolve_output_dir(directory)
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".healthcheck"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"ok": True, "path": str(path), "message": "Writable."}
    except Exception as exc:
        return {"ok": False, "path": str(directory), "message": str(exc)}


def _tool_check(command_text: str | None, *, optional: bool) -> dict[str, Any]:
    head = _command_head(command_text or "")
    available = _command_available(head)
    return {
        "ok": available or optional,
        "available": available,
        "command": command_text or "",
        "message": "Available." if available else "Not found.",
    }


def _disk_check(output_dirs: dict[str, str | Path]) -> dict[str, Any]:
    try:
        first_dir = next(iter(output_dirs.values()))
        usage = shutil.disk_usage(safe_paths.resolve_output_dir(first_dir))
        return {
            "ok": True,
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "message": "Disk usage inspected.",
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def _command_head(command_text: str) -> str:
    parts = shlex.split(command_text) if command_text.strip() else []
    return parts[0] if parts else ""


def _command_available(command_head: str) -> bool:
    if not command_head:
        return False
    if Path(command_head).is_file():
        return True
    return shutil.which(command_head) is not None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
