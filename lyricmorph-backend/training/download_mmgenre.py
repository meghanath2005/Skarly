"""Download a balanced CC-BY 4.0 MMGenre subset for broad music-genre routing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ID = "Leaky-ReLU/MMGenre"
GENRES = ("blues", "classical", "country", "electronic", "jazz", "pop", "rap", "rnb", "rock", "world")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("data/mmgenre"))
    parser.add_argument("--per-genre", type=int, default=60, help="Balanced number of clips per broad genre; 60 is roughly 1 GB.")
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/mmgenre_cc_by.jsonl"))
    args = parser.parse_args()
    if args.per_genre < 1:
        raise SystemExit("--per-genre must be positive")
    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise SystemExit("Install huggingface_hub in the selected training Python environment first.") from exc

    api = HfApi()
    files = list(api.list_repo_tree(REPO_ID, repo_type="dataset", recursive=True))
    rows: list[dict[str, object]] = []
    for genre in GENRES:
        paths = sorted(
            item.path for item in files
            if item.path.startswith(f"{genre}/wavs/") and item.path.lower().endswith(".wav")
        )[: args.per_genre]
        if len(paths) < args.per_genre:
            raise RuntimeError(f"Only {len(paths)} MMGenre clips found for {genre}; expected {args.per_genre}.")
        for path in paths:
            downloaded = hf_hub_download(repo_id=REPO_ID, repo_type="dataset", filename=path, local_dir=args.output_root)
            rows.append({
                "audio_path": str(Path(downloaded).resolve()),
                "language": None,
                "genre": genre,
                "singing_speech": "singing",
                "label_origin": "dataset_role",
                "source": "mmgenre_cc_by_4_0",
                "rights_confirmed": True,
                "contributor_id": f"mmgenre:{Path(path).stem}",
                "consent_record_id": "Leaky-ReLU/MMGenre:CC-BY-4.0",
                "copyright_owner": "Upstream MMGenre contributor; individual identity is not provided in the local manifest",
                "permitted_training_use": "Broad prototype genre prior under CC-BY-4.0 with attribution",
                "commercial_use_permission": True,
                "revocation_policy": "Follow an upstream dataset takedown by rebuilding the pinned local manifest",
                "audio_role": "full_mix",
                "recording_conditions": "MMGenre benchmark full-mix clip; singer and microphone conditions are not supplied locally",
                "singer_id": None,
                "dataset_version": "Leaky-ReLU-MMGenre-local-snapshot",
                "dataset_usage_permission_version": "CC-BY-4.0",
                "quality_review_status": "dataset_import_unreviewed",
            })
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"dataset": REPO_ID, "license": "CC-BY-4.0", "examples": len(rows), "genres": list(GENRES), "manifest": str(args.manifest)}))


if __name__ == "__main__":
    main()
