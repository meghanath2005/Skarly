"""Persist explicitly consented vocal examples for future local classifier training."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from .safe_paths import sanitize_filename


_MANIFEST_LOCK = Lock()
SUPPORTED_LANGUAGES = {"Hindi", "English"}


@dataclass(frozen=True)
class TrainingFeedbackResult:
    """Outcome of saving one creator-consented training example."""

    audio_path: Path
    manifest_path: Path


def save_opt_in_vocal_example(
    source_audio: Path,
    *,
    feedback_dir: str | Path,
    manifest_path: str | Path,
    language: str,
    genre: str,
    job_id: str,
    consent_metadata: dict[str, Any] | None = None,
) -> TrainingFeedbackResult:
    """Copy a labelled vocal and append an auditable JSONL training-manifest row.

    The caller is responsible for collecting explicit creator consent before this
    function is used. Only Hindi and English labels are accepted by the current
    shared-encoder audio-intelligence training programme.
    """
    if not source_audio.is_file():
        raise FileNotFoundError(source_audio)
    normalized_language = str(language or "").strip().title()
    if normalized_language not in SUPPORTED_LANGUAGES:
        raise ValueError("Consent training currently supports Hindi and English vocals only")
    normalized_genre = str(genre or "").strip()
    if not normalized_genre:
        raise ValueError("A creator-confirmed genre is required for consent training")

    safe_job_id = sanitize_filename(job_id)
    if safe_job_id != job_id:
        raise ValueError("Invalid Skarly job id")
    safe_genre = sanitize_filename(normalized_genre)
    destination_root = Path(feedback_dir).resolve()
    destination = destination_root / normalized_language / safe_genre / f"{safe_job_id}.wav"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_audio, destination)

    resolved_manifest = Path(manifest_path).resolve()
    row = {
        "audio_path": str(destination.resolve()),
        "language": normalized_language,
        "genre": normalized_genre,
        "source": "creator_opt_in_vocal",
        "label_origin": "creator_confirmed",
        "rights_confirmed": True,
        "job_id": job_id,
        "audio_role": "vocal_only",
    }
    allowed_metadata = {
        "contributor_id",
        "consent_record_id",
        "copyright_owner",
        "permitted_training_use",
        "commercial_use_permission",
        "revocation_policy",
        "recording_conditions",
        "singer_id",
        "dataset_version",
        "dataset_usage_permission_version",
        "quality_review_status",
        "singing_speech",
        "vocal_techniques",
        "moods",
        "tempo_family",
        "melodic_character",
        "in_distribution",
    }
    for key, value in (consent_metadata or {}).items():
        if key in allowed_metadata:
            row[key] = value
    with _MANIFEST_LOCK:
        resolved_manifest.parent.mkdir(parents=True, exist_ok=True)
        with resolved_manifest.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return TrainingFeedbackResult(audio_path=destination, manifest_path=resolved_manifest)
