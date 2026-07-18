"""Add explicit licence and provenance fields to existing Skarly public-data manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_metadata(row: dict[str, Any]) -> dict[str, Any] | None:
    source = str(row.get("source") or "").strip().lower()
    audio = Path(str(row.get("audio_path") or "unknown"))
    if "fleurs" in source:
        split = str(row.get("split") or "unknown")
        return {
            "contributor_id": f"google-fleurs:{audio.stem}",
            "consent_record_id": "google/fleurs:CC-BY-4.0",
            "copyright_owner": "Upstream FLEURS contributor; individual identity is not provided in the local manifest",
            "permitted_training_use": "Language and speaking-representation prototype under CC-BY-4.0 with attribution",
            "commercial_use_permission": True,
            "revocation_policy": "Follow an upstream dataset takedown by rebuilding the pinned local manifest",
            "audio_role": "speech_only",
            "recording_conditions": "FLEURS speech recording; detailed microphone conditions are not supplied locally",
            "singer_id": None,
            "recording_id": audio.stem,
            "dataset_version": f"google-fleurs-{split}-local-snapshot",
            "dataset_usage_permission_version": "CC-BY-4.0",
            "quality_review_status": "dataset_import_unreviewed",
            "label_origin": row.get("label_origin") or "dataset_role",
            "singing_speech": row.get("singing_speech") or "speaking",
        }
    if "mmgenre" in source:
        return {
            "contributor_id": f"mmgenre:{audio.stem}",
            "consent_record_id": "Leaky-ReLU/MMGenre:CC-BY-4.0",
            "copyright_owner": "Upstream MMGenre contributor; individual identity is not provided in the local manifest",
            "permitted_training_use": "Broad prototype genre prior under CC-BY-4.0 with attribution",
            "commercial_use_permission": True,
            "revocation_policy": "Follow an upstream dataset takedown by rebuilding the pinned local manifest",
            "audio_role": "full_mix",
            "recording_conditions": "MMGenre benchmark full-mix clip; singer and microphone conditions are not supplied locally",
            "singer_id": None,
            "recording_id": audio.stem,
            "dataset_version": "Leaky-ReLU-MMGenre-local-snapshot",
            "dataset_usage_permission_version": "CC-BY-4.0",
            "quality_review_status": "dataset_import_unreviewed",
            "label_origin": row.get("label_origin") or "dataset_role",
            "singing_speech": row.get("singing_speech") or "singing",
        }
    return None


def enrich_manifest(path: Path) -> dict[str, Any]:
    original_sha256 = sha256_file(path)
    rows: list[dict[str, Any]] = []
    enriched = 0
    unsupported = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number} must be a JSON object")
        additions = public_metadata(row)
        if additions is None:
            unsupported += 1
        else:
            for key, value in additions.items():
                if row.get(key) in (None, "") and key != "singer_id":
                    row[key] = value
                elif key not in row:
                    row[key] = value
            enriched += 1
        rows.append(row)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    temporary.replace(path)
    return {
        "manifest": str(path),
        "rows": len(rows),
        "enriched": enriched,
        "unsupported": unsupported,
        "original_sha256": original_sha256,
        "updated_sha256": sha256_file(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    args = parser.parse_args()
    reports = [enrich_manifest(path.resolve()) for path in args.manifest]
    print(json.dumps({"reports": reports}, ensure_ascii=False))


if __name__ == "__main__":
    main()

