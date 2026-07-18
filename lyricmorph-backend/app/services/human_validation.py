"""Safe public-file resolution for blinded human validation panels."""

from __future__ import annotations

from pathlib import Path
import re


PANEL_ID_PATTERN = re.compile(r"^human_panel_[a-f0-9]{16}$")


def public_panel_file(
    *,
    skarly_output_dir: str | Path,
    panel_id: str,
    asset_path: str = "index.html",
) -> Path:
    """Resolve only files below a panel's public directory.

    Admin mappings and reviewer ratings live beside ``public/`` and can never
    be reached through this resolver, including with encoded traversal input.
    """

    normalized_id = str(panel_id or "").strip().lower()
    if not PANEL_ID_PATTERN.fullmatch(normalized_id):
        raise ValueError("Invalid human validation panel ID")
    requested = str(asset_path or "index.html").replace("\\", "/").lstrip("/")
    validation_root = Path(skarly_output_dir).expanduser().resolve().parent / "validation"
    public_root = (validation_root / normalized_id / "public").resolve()
    candidate = (public_root / requested).resolve()
    try:
        candidate.relative_to(public_root)
    except ValueError as exc:
        raise PermissionError("Validation panel asset escapes the public directory") from exc
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate
