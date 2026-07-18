from __future__ import annotations

from pathlib import Path
import json
from uuid import uuid4

from ..audio_validation import validate_audio_file
from ..models import AudioUploadResponse
from . import safe_paths

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg"}


def save_audio_upload(
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    uploads_dir: str | Path,
    max_upload_mb: int,
    url_for_path,
) -> AudioUploadResponse:
    if not data:
        raise ValueError("Uploaded audio file is empty.")
    max_bytes = max(1, int(max_upload_mb or 100)) * 1024 * 1024
    if len(data) > max_bytes:
        raise ValueError(f"Uploaded audio file exceeds {max_upload_mb} MB.")

    safe_name = safe_paths.sanitize_filename(filename or "audio.wav")
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise ValueError("Unsupported audio format. Use wav, mp3, m4a, flac, aac, or ogg.")

    upload_id = f"upload_{uuid4().hex}"
    upload_dir = safe_paths.resolve_output_dir(uploads_dir) / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    original_path = upload_dir / f"original{suffix}"
    original_path.write_bytes(data)

    quality_report = validate_audio_file(original_path, generator_name="audio_upload")
    response = AudioUploadResponse(
        upload_id=upload_id,
        filename=safe_name,
        content_type=content_type,
        original_path=str(original_path),
        audio_url=url_for_path(str(original_path)) if url_for_path else None,
        duration_seconds=quality_report.duration_seconds,
        quality_report=quality_report,
        warnings=[*quality_report.validation_errors, *quality_report.warnings],
    )
    _metadata_path(upload_dir).write_text(json.dumps(response.model_dump(mode="json"), indent=2), encoding="utf-8")
    return response


def get_upload(upload_id: str, *, uploads_dir: str | Path, url_for_path=None) -> AudioUploadResponse | None:
    upload_dir = safe_paths.resolve_output_dir(uploads_dir) / safe_paths.sanitize_filename(upload_id)
    metadata = _metadata_path(upload_dir)
    if not metadata.exists():
        return None
    response = AudioUploadResponse.model_validate(json.loads(metadata.read_text(encoding="utf-8")))
    if url_for_path:
        response.audio_url = url_for_path(response.original_path)
    return response


def _metadata_path(upload_dir: Path) -> Path:
    return upload_dir / "metadata.json"
