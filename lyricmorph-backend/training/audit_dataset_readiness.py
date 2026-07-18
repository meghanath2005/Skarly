"""Audit Skarly training manifests against legal, label, and singer coverage targets."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from .audio_taxonomy import DEFAULT_HEAD_CLASSES, normalize_genre, normalize_language, normalize_token, normalize_values
except ImportError:  # pragma: no cover - direct script execution
    from audio_taxonomy import DEFAULT_HEAD_CLASSES, normalize_genre, normalize_language, normalize_token, normalize_values


LEGAL_METADATA_FIELDS = (
    "contributor_id",
    "consent_record_id",
    "copyright_owner",
    "permitted_training_use",
    "commercial_use_permission",
    "revocation_policy",
    "audio_role",
    "recording_conditions",
    "singer_id",
    "dataset_version",
    "label_origin",
    "quality_review_status",
)

HEAD_FIELDS: dict[str, tuple[str, ...]] = {
    "language": ("language",),
    "singing_speech": ("singing_speech",),
    "vocal_technique": ("vocal_techniques", "vocal_technique"),
    "mood": ("moods", "mood"),
    "genre": ("genres", "genre"),
    "tempo_family": ("tempo_family",),
    "melodic_character": ("melodic_character",),
    "in_distribution": ("in_distribution",),
}

PRODUCTION_TARGETS: dict[str, tuple[int, int]] = {
    "language": (150, 20),
    "singing_speech": (100, 20),
    "vocal_technique": (50, 10),
    "mood": (50, 10),
    "genre": (150, 20),
    "tempo_family": (100, 20),
    "melodic_character": (100, 20),
    "in_distribution": (100, 10),
}


def read_manifests(paths: Sequence[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number} is invalid JSON: {exc}") from exc
                if not isinstance(row, dict):
                    raise ValueError(f"{path}:{line_number} must be a JSON object")
                row["_manifest"] = str(path.resolve())
                row["_line"] = line_number
                rows.append(row)
    if not rows:
        raise ValueError("No manifest rows were found")
    return rows


def first_value(row: Mapping[str, Any], fields: Iterable[str]) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, "", []):
            return value
    return None


def labels_for_head(row: Mapping[str, Any], head: str) -> list[str]:
    value = first_value(row, HEAD_FIELDS[head])
    source = str(row.get("source") or "").strip().lower()
    if value is None and head == "singing_speech":
        if "fleurs" in source:
            value = "speaking"
        elif "mmgenre" in source:
            value = "singing"
    if value is None and head == "in_distribution" and row.get("rights_confirmed") is True:
        value = True
    if value is None:
        return []
    if head == "language":
        label = normalize_language(value)
        return [label] if label else []
    if head == "genre":
        return normalize_values(value, mapper=normalize_genre)
    if head == "in_distribution":
        if isinstance(value, bool):
            return ["in_distribution" if value else "out_of_distribution"]
        token = normalize_token(value)
        return [token] if token in DEFAULT_HEAD_CLASSES[head] else []
    labels = normalize_values(value)
    allowed = set(DEFAULT_HEAD_CLASSES[head])
    return [label for label in labels if label in allowed]


def audit_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    missing_legal = Counter()
    rights_missing = 0
    role_violations: list[dict[str, Any]] = []
    source_counts = Counter(str(row.get("source") or "unknown") for row in rows)
    for row in rows:
        if row.get("rights_confirmed") is not True:
            rights_missing += 1
        for field in LEGAL_METADATA_FIELDS:
            if row.get(field) in (None, ""):
                missing_legal[field] += 1
        source = str(row.get("source") or "").lower()
        if "fleurs" in source:
            prohibited = [field for field in ("genre", "genres", "mood", "moods", "vocal_technique", "vocal_techniques", "melodic_character") if row.get(field) not in (None, "", [])]
            if prohibited:
                role_violations.append({"manifest": row.get("_manifest"), "line": row.get("_line"), "source": source, "prohibited_labels": prohibited})

    head_reports: dict[str, Any] = {}
    all_heads_ready = True
    for head, classes in DEFAULT_HEAD_CLASSES.items():
        label_counts: Counter[str] = Counter()
        singer_sets: dict[str, set[str]] = defaultdict(set)
        supervised_rows = 0
        rows_missing_singer = 0
        for row in rows:
            labels = labels_for_head(row, head)
            if not labels:
                continue
            supervised_rows += 1
            singer_id = str(row.get("singer_id") or "").strip()
            if not singer_id:
                rows_missing_singer += 1
            for label in labels:
                label_counts[label] += 1
                if singer_id:
                    singer_sets[label].add(singer_id)
        min_examples, min_singers = PRODUCTION_TARGETS[head]
        missing_classes = [label for label in classes if label_counts[label] < min_examples]
        singer_shortfalls = [label for label in classes if len(singer_sets[label]) < min_singers]
        production_ready = not missing_classes and not singer_shortfalls and rows_missing_singer == 0
        all_heads_ready = all_heads_ready and production_ready
        head_reports[head] = {
            "supervised_rows": supervised_rows,
            "label_counts": {label: label_counts[label] for label in classes},
            "independent_singers": {label: len(singer_sets[label]) for label in classes},
            "rows_missing_singer_id": rows_missing_singer,
            "minimum_examples_per_label": min_examples,
            "minimum_singers_per_label": min_singers,
            "labels_below_example_target": missing_classes,
            "labels_below_singer_target": singer_shortfalls,
            "trainable_prototype": sum(count > 0 for count in label_counts.values()) >= 2 and supervised_rows >= 20,
            "production_target_met": production_ready,
        }

    metadata_complete = rights_missing == 0 and not any(missing_legal.values())
    return {
        "format": "skarly_dataset_readiness_v1",
        "rows": len(rows),
        "sources": dict(source_counts),
        "rights_confirmed_missing": rights_missing,
        "required_metadata_missing": dict(missing_legal),
        "metadata_complete": metadata_complete,
        "dataset_role_violations": role_violations,
        "heads": head_reports,
        "all_eight_heads_production_ready": all_heads_ready,
        "release_ready": metadata_complete and not role_violations and all_heads_ready,
        "policy_note": "Genre uses the specification target of 150 examples and 20 singers per label; other per-head targets are conservative release-audit defaults and may be raised after validation design review.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    paths = [path.resolve() for path in args.manifest]
    report = audit_rows(read_manifests(paths))
    report["manifests"] = [str(path) for path in paths]
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(output)
    print(rendered, end="")


if __name__ == "__main__":
    main()
