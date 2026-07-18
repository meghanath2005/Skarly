"""Fit Skarly's arrangement-similarity thresholds from human pair ratings."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


FORMAT = "skarly_diversity_calibration_v1"
RATING_FIELDS = {
    "embedding": "embedding_similarity",
    "drum_onset": "drum_onset_similarity",
    "chord_change": "chord_change_similarity",
    "instrumentation": "instrumentation_similarity",
    "perceptual": "perceptual_similarity",
}
MIN_RATINGS = 50
MIN_CLASS_RATINGS = 10
MIN_RATERS = 3


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_ratings(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number} is not valid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number} must be a JSON object")
        missing = [field for field in (*RATING_FIELDS.values(), "too_similar", "rater_id", "pair_id") if field not in row]
        if missing:
            raise ValueError(f"{path}:{line_number} is missing: {', '.join(missing)}")
        if not isinstance(row["too_similar"], bool):
            raise ValueError(f"{path}:{line_number} too_similar must be true or false")
        if not str(row["rater_id"]).strip() or not str(row["pair_id"]).strip():
            raise ValueError(f"{path}:{line_number} requires non-empty rater_id and pair_id")
        for field in RATING_FIELDS.values():
            try:
                value = float(row[field])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{path}:{line_number} {field} must be numeric") from exc
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{path}:{line_number} {field} must be between 0 and 1")
            row[field] = value
        rows.append(row)
    if not rows:
        raise ValueError("The ratings manifest is empty")
    return rows


def classification_metrics(labels: Sequence[bool], predictions: Sequence[bool]) -> dict[str, float | int]:
    tp = sum(label and prediction for label, prediction in zip(labels, predictions))
    tn = sum((not label) and (not prediction) for label, prediction in zip(labels, predictions))
    fp = sum((not label) and prediction for label, prediction in zip(labels, predictions))
    fn = sum(label and (not prediction) for label, prediction in zip(labels, predictions))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "specificity": round(specificity, 6),
        "balanced_accuracy": round((recall + specificity) / 2.0, 6),
        "f1": round(f1, 6),
    }


def candidate_thresholds(values: Iterable[float]) -> list[float]:
    unique = sorted(set(float(value) for value in values))
    candidates = {0.0, 1.0}
    candidates.update(unique)
    candidates.update((left + right) / 2.0 for left, right in zip(unique, unique[1:]))
    return sorted(candidates)


def choose_threshold(rows: Sequence[Mapping[str, Any]], field: str) -> tuple[float, dict[str, float | int]]:
    labels = [bool(row["too_similar"]) for row in rows]
    best: tuple[tuple[float, float, float, float], float, dict[str, float | int]] | None = None
    for threshold in candidate_thresholds(float(row[field]) for row in rows):
        predictions = [float(row[field]) >= threshold for row in rows]
        metrics = classification_metrics(labels, predictions)
        # Missing a too-similar pair is costlier than an unnecessary reroll.
        score = (
            float(metrics["recall"]),
            float(metrics["balanced_accuracy"]),
            float(metrics["f1"]),
            float(metrics["precision"]),
        )
        if best is None or score > best[0] or (score == best[0] and threshold > best[1]):
            best = (score, threshold, metrics)
    assert best is not None
    return round(best[1], 6), best[2]


def calibrate_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    approve: bool = False,
    approved_by: str | None = None,
    ratings_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    labels = [bool(row["too_similar"]) for row in rows]
    positive_count = sum(labels)
    negative_count = len(labels) - positive_count
    raters = {str(row["rater_id"]).strip() for row in rows}
    pairs = {str(row["pair_id"]).strip() for row in rows}
    readiness_errors: list[str] = []
    if len(rows) < MIN_RATINGS:
        readiness_errors.append(f"need at least {MIN_RATINGS} ratings")
    if positive_count < MIN_CLASS_RATINGS or negative_count < MIN_CLASS_RATINGS:
        readiness_errors.append(f"need at least {MIN_CLASS_RATINGS} ratings in each class")
    if len(raters) < MIN_RATERS:
        readiness_errors.append(f"need at least {MIN_RATERS} independent raters")
    if len(pairs) < MIN_RATINGS:
        readiness_errors.append(f"need at least {MIN_RATINGS} distinct arrangement pairs")
    if approve and not str(approved_by or "").strip():
        readiness_errors.append("--approved-by is required with --approve")
    if approve and readiness_errors:
        raise ValueError("Cannot approve diversity calibration: " + "; ".join(readiness_errors))

    thresholds: dict[str, float] = {}
    per_view: dict[str, Any] = {}
    for public_name, field in RATING_FIELDS.items():
        threshold, metrics = choose_threshold(rows, field)
        thresholds[public_name] = threshold
        per_view[public_name] = {"source_field": field, "threshold": threshold, "metrics": metrics}
    thresholds["near_identical_embedding"] = round(max(0.995, thresholds["embedding"]), 6)
    thresholds["near_identical_instrumentation"] = round(max(0.990, thresholds["instrumentation"]), 6)
    thresholds["perceptual_embedding_floor"] = thresholds["embedding"]

    combined_predictions = [float(row["perceptual_similarity"]) >= thresholds["perceptual"] for row in rows]
    combined_metrics = classification_metrics(labels, combined_predictions)
    digest = ratings_manifest_sha256 or hashlib.sha256(
        "\n".join(json.dumps(dict(row), sort_keys=True, ensure_ascii=False) for row in rows).encode("utf-8")
    ).hexdigest()
    return {
        "format": FORMAT,
        "calibration_id": f"human-rated-{digest[:12]}",
        "approved": bool(approve),
        "approved_by": str(approved_by or "").strip() or None,
        "ratings_manifest_sha256": digest,
        "sample_count": len(rows),
        "distinct_pair_count": len(pairs),
        "rater_count": len(raters),
        "class_counts": {"too_similar": positive_count, "different": negative_count},
        "thresholds": thresholds,
        "metrics": {"per_view": per_view, "combined_perceptual_gate": combined_metrics},
        "ready_for_review": not readiness_errors,
        "readiness_errors": readiness_errors,
        "selection_policy": "maximize too-similar recall, then balanced accuracy, F1, and precision",
        "note": "Human-rated thresholds require explicit release approval before Skarly activates them.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratings", type=Path, required=True, help="Human pair ratings as JSONL")
    parser.add_argument("--output", type=Path, required=True, help="Calibration JSON output")
    parser.add_argument("--approve", action="store_true", help="Mark the result release-approved after coverage checks")
    parser.add_argument("--approved-by", type=str, default=None, help="Reviewer identity required with --approve")
    args = parser.parse_args()

    ratings_path = args.ratings.resolve()
    rows = read_ratings(ratings_path)
    result = calibrate_rows(
        rows,
        approve=args.approve,
        approved_by=args.approved_by,
        ratings_manifest_sha256=sha256_file(ratings_path),
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"output": str(output), **{key: result[key] for key in ("calibration_id", "approved", "sample_count", "rater_count", "class_counts", "ready_for_review", "readiness_errors")}}, ensure_ascii=False))


if __name__ == "__main__":
    main()

