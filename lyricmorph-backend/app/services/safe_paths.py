from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import quote
from typing import Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_ALLOWED_RELATIVE_DIRS = (
    "outputs/ace_step",
    "outputs/procedural_v2",
    "outputs/mixes",
    "outputs/stems",
    "outputs/sections",
    "outputs/projects",
    "outputs/exports",
    "outputs/uploads",
    "outputs/online_music",
    "outputs/skarly",
)


def default_allowed_dirs() -> list[Path]:
    return [resolve_output_dir(path) for path in DEFAULT_ALLOWED_RELATIVE_DIRS]


def resolve_output_dir(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = BACKEND_ROOT / candidate
    return candidate.resolve()


def resolve_safe_output_path(path: str | Path, allowed_dirs: Iterable[str | Path] | None = None) -> Path:
    resolved = resolve_output_dir(path)
    if not is_within_allowed_dirs(resolved, allowed_dirs):
        raise ValueError("Path is outside allowed output directories.")
    return resolved


def is_within_allowed_dirs(path: str | Path, allowed_dirs: Iterable[str | Path] | None = None) -> bool:
    try:
        resolved = resolve_output_dir(path)
    except (OSError, RuntimeError):
        return False
    for allowed in _resolved_allowed_dirs(allowed_dirs):
        try:
            resolved.relative_to(allowed)
            return True
        except ValueError:
            continue
    return False


def safe_url_for_output(
    path: str | Path,
    allowed_dirs: Iterable[str | Path] | None = None,
    route_prefixes: dict[str, str] | None = None,
) -> str | None:
    try:
        resolved = resolve_safe_output_path(path, allowed_dirs)
    except ValueError:
        return None

    for allowed in _resolved_allowed_dirs(allowed_dirs):
        try:
            relative = resolved.relative_to(allowed)
        except ValueError:
            continue
        prefix = _route_prefix_for_allowed_dir(allowed, route_prefixes)
        encoded = quote(relative.as_posix(), safe="/")
        return f"{prefix}/{encoded}" if encoded else prefix
    return None


def ensure_dir(path: str | Path, allowed_dirs: Iterable[str | Path] | None = None) -> Path:
    resolved = resolve_safe_output_path(path, allowed_dirs)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def sanitize_filename(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "").strip())
    normalized = normalized.strip("._-")
    return normalized[:160] or "untitled"


def _resolved_allowed_dirs(allowed_dirs: Iterable[str | Path] | None) -> list[Path]:
    return [resolve_output_dir(path) for path in (allowed_dirs or DEFAULT_ALLOWED_RELATIVE_DIRS)]


def _route_prefix_for_allowed_dir(allowed: Path, route_prefixes: dict[str, str] | None) -> str:
    if route_prefixes:
        for key, value in route_prefixes.items():
            try:
                if allowed == resolve_output_dir(key):
                    return value.rstrip("/")
            except (OSError, RuntimeError):
                continue
    parts = allowed.parts
    if "outputs" in parts:
        index = parts.index("outputs")
        route = "/".join(parts[index:])
        return f"/{route}".rstrip("/")
    return f"/outputs/{allowed.name}".rstrip("/")
