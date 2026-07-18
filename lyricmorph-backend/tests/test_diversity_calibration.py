from __future__ import annotations

import json

import pytest

from app.services import diversity_calibration
from training.calibrate_diversity import calibrate_rows


def human_rating_rows(count: int = 60) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(count):
        too_similar = index < count // 2
        base = 0.94 + ((index % 5) * 0.008) if too_similar else 0.25 + ((index % 5) * 0.03)
        rows.append(
            {
                "pair_id": f"pair-{index:03d}",
                "rater_id": f"rater-{index % 3}",
                "too_similar": too_similar,
                "embedding_similarity": min(1.0, base + 0.01),
                "drum_onset_similarity": min(1.0, base - 0.01),
                "chord_change_similarity": min(1.0, base - 0.02),
                "instrumentation_similarity": min(1.0, base + 0.005),
                "perceptual_similarity": base,
            }
        )
    return rows


def test_calibrator_requires_reviewed_coverage_before_approval():
    with pytest.raises(ValueError, match="Cannot approve"):
        calibrate_rows(human_rating_rows(12), approve=True, approved_by="release-reviewer")


def test_human_calibration_round_trip_is_release_auditable(tmp_path):
    result = calibrate_rows(
        human_rating_rows(),
        approve=True,
        approved_by="release-reviewer",
        ratings_manifest_sha256="a" * 64,
    )
    assert result["approved"] is True
    assert result["ready_for_review"] is True
    assert result["sample_count"] == 60
    assert result["rater_count"] == 3
    assert result["metrics"]["combined_perceptual_gate"]["balanced_accuracy"] == 1.0

    path = tmp_path / "calibration.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    loaded = diversity_calibration.load_diversity_calibration(path)
    assert loaded.approved is True
    assert loaded.sample_count == 60
    assert loaded.rater_count == 3
    assert loaded.approved_by == "release-reviewer"
    assert loaded.manifest_sha256 == "a" * 64
    assert loaded.thresholds == result["thresholds"]


def test_unapproved_calibration_cannot_replace_prototype_thresholds(tmp_path):
    result = calibrate_rows(human_rating_rows(), approve=False)
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(result), encoding="utf-8")

    loaded = diversity_calibration.load_diversity_calibration(path)
    assert loaded.approved is False
    assert loaded.calibration_id == "prototype-conservative-v1"
    assert loaded.thresholds == diversity_calibration.DEFAULT_THRESHOLDS
    assert "release approval is false" in (loaded.note or "")

