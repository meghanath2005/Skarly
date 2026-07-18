"""Load release-reviewed human calibration for the arrangement diversity gate."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Any, Mapping


CALIBRATION_ENV = "SKARLY_DIVERSITY_CALIBRATION_PATH"
CALIBRATION_FORMAT = "skarly_diversity_calibration_v1"
MIN_RATINGS = 50
MIN_CLASS_RATINGS = 10
MIN_RATERS = 3

DEFAULT_THRESHOLDS: dict[str, float] = {
    "embedding": 0.985,
    "drum_onset": 0.940,
    "chord_change": 0.940,
    "instrumentation": 0.980,
    "perceptual": 0.975,
    "near_identical_embedding": 0.997,
    "near_identical_instrumentation": 0.995,
    "perceptual_embedding_floor": 0.975,
}


@dataclass(frozen=True)
class DiversityCalibration:
    calibration_id: str
    thresholds: dict[str, float]
    approved: bool
    sample_count: int
    positive_count: int
    negative_count: int
    rater_count: int
    manifest_sha256: str | None = None
    approved_by: str | None = None
    source_path: str | None = None
    note: str | None = None

    def public_status(self) -> dict[str, Any]:
        return {
            "calibration_id": self.calibration_id,
            "approved": self.approved,
            "sample_count": self.sample_count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "rater_count": self.rater_count,
            "manifest_sha256": self.manifest_sha256,
            "approved_by": self.approved_by,
            "source_path": self.source_path,
            "note": self.note,
            "thresholds": dict(self.thresholds),
        }


def prototype_calibration(note: str | None = None) -> DiversityCalibration:
    return DiversityCalibration(
        calibration_id="prototype-conservative-v1",
        thresholds=dict(DEFAULT_THRESHOLDS),
        approved=False,
        sample_count=0,
        positive_count=0,
        negative_count=0,
        rater_count=0,
        note=note or "Human-rated diversity calibration has not been release-approved.",
    )


def _safe_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _validated_thresholds(value: Any) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None
    thresholds = dict(DEFAULT_THRESHOLDS)
    for key in DEFAULT_THRESHOLDS:
        if key not in value:
            return None
        try:
            threshold = float(value[key])
        except (TypeError, ValueError):
            return None
        if not 0.0 <= threshold <= 1.0:
            return None
        thresholds[key] = threshold
    return thresholds


def load_diversity_calibration(path: str | Path | None = None) -> DiversityCalibration:
    configured = str(path or os.getenv(CALIBRATION_ENV, "")).strip()
    if not configured:
        return prototype_calibration()
    candidate = Path(configured).expanduser().resolve()
    if not candidate.is_file():
        return prototype_calibration(f"Configured calibration file does not exist: {candidate}")
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return prototype_calibration(f"Configured calibration file is unreadable: {exc}")
    if not isinstance(payload, Mapping) or payload.get("format") != CALIBRATION_FORMAT:
        return prototype_calibration("Configured diversity calibration has an unsupported format.")
    thresholds = _validated_thresholds(payload.get("thresholds"))
    if thresholds is None:
        return prototype_calibration("Configured diversity calibration has invalid thresholds.")

    sample_count = _safe_count(payload.get("sample_count"))
    class_counts = payload.get("class_counts") if isinstance(payload.get("class_counts"), Mapping) else {}
    positive_count = _safe_count(class_counts.get("too_similar"))
    negative_count = _safe_count(class_counts.get("different"))
    rater_count = _safe_count(payload.get("rater_count"))
    approved_by = str(payload.get("approved_by") or "").strip() or None
    approved = bool(payload.get("approved"))
    readiness_errors: list[str] = []
    if sample_count < MIN_RATINGS:
        readiness_errors.append(f"need at least {MIN_RATINGS} ratings")
    if positive_count < MIN_CLASS_RATINGS or negative_count < MIN_CLASS_RATINGS:
        readiness_errors.append(f"need at least {MIN_CLASS_RATINGS} ratings in each class")
    if rater_count < MIN_RATERS:
        readiness_errors.append(f"need at least {MIN_RATERS} independent raters")
    if not approved_by:
        readiness_errors.append("approved_by is required")
    if not approved:
        readiness_errors.append("release approval is false")
    if readiness_errors:
        return prototype_calibration(
            "Human calibration was not activated: " + "; ".join(readiness_errors) + "."
        )

    return DiversityCalibration(
        calibration_id=str(payload.get("calibration_id") or candidate.stem),
        thresholds=thresholds,
        approved=True,
        sample_count=sample_count,
        positive_count=positive_count,
        negative_count=negative_count,
        rater_count=rater_count,
        manifest_sha256=str(payload.get("ratings_manifest_sha256") or "").strip() or None,
        approved_by=approved_by,
        source_path=str(candidate),
        note=str(payload.get("note") or "Human-rated calibration is release-approved."),
    )


@lru_cache(maxsize=1)
def active_diversity_calibration() -> DiversityCalibration:
    """Return the process-wide calibration selected at startup."""

    return load_diversity_calibration()

