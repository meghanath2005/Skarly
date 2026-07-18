"""Download a rights-documented Hindi + English FLEURS speech subset for language ID."""

from __future__ import annotations

import argparse
import csv
import json
import tarfile
from pathlib import Path


LANGUAGES = {"hi_in": "Hindi", "en_us": "English"}
REPO_ID = "google/fleurs"


def safe_extract(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    resolved_destination = destination.resolve()
    with tarfile.open(archive_path, "r:gz") as archive:
        safe_members = []
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if not str(target).startswith(str(resolved_destination) + "\\") and target != resolved_destination:
                raise ValueError(f"Unsafe path in archive: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"Refusing link entry in archive: {member.name}")
            safe_members.append(member)
        archive.extractall(destination, members=safe_members)


def build_manifest(language_root: Path, *, language: str, split: str) -> list[dict[str, object]]:
    tsv_path = language_root / f"{split}.tsv"
    # Each FLEURS archive contains a top-level directory named after its split.
    # Limiting the manifest to that directory prevents a prior ``dev`` extract
    # from being silently reused when we download the larger ``train`` split.
    clips_root = language_root / "clips" / split
    audio_by_name = {audio_path.name: audio_path for audio_path in clips_root.rglob("*.wav")}
    rows: list[dict[str, object]] = []
    with tsv_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if len(row) < 2:
                continue
            audio_path = audio_by_name.get(row[1].strip())
            if audio_path is None:
                continue
            rows.append({
                "audio_path": str(audio_path.resolve()),
                "language": language,
                "genre": None,
                "singing_speech": "speaking",
                "label_origin": "dataset_role",
                "source": "google_fleurs_cc_by",
                "split": split,
                "rights_confirmed": True,
                "contributor_id": f"google-fleurs:{audio_path.stem}",
                "consent_record_id": "google/fleurs:CC-BY-4.0",
                "copyright_owner": "Upstream FLEURS contributor; individual identity is not provided in the local manifest",
                "permitted_training_use": "Language and speaking-representation prototype under CC-BY-4.0 with attribution",
                "commercial_use_permission": True,
                "revocation_policy": "Follow an upstream dataset takedown by rebuilding the pinned local manifest",
                "audio_role": "speech_only",
                "recording_conditions": "FLEURS speech recording; detailed microphone conditions are not supplied locally",
                "singer_id": None,
                "dataset_version": f"google-fleurs-{split}-local-snapshot",
                "dataset_usage_permission_version": "CC-BY-4.0",
                "quality_review_status": "dataset_import_unreviewed",
            })
    return rows


def download_language(output_root: Path, *, code: str, split: str) -> list[dict[str, object]]:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise SystemExit("Install huggingface_hub in the selected training Python environment first.") from exc

    language_root = output_root / code
    language_root.mkdir(parents=True, exist_ok=True)
    archive_name = f"data/{code}/audio/{split}.tar.gz"
    metadata_name = f"data/{code}/{split}.tsv"
    archive_path = Path(hf_hub_download(repo_id=REPO_ID, repo_type="dataset", filename=archive_name, local_dir=language_root))
    metadata_path = Path(hf_hub_download(repo_id=REPO_ID, repo_type="dataset", filename=metadata_name, local_dir=language_root))
    target_metadata = language_root / f"{split}.tsv"
    if metadata_path.resolve() != target_metadata.resolve():
        target_metadata.write_bytes(metadata_path.read_bytes())
    clips_root = language_root / "clips"
    marker = clips_root / f".{split}.complete"
    legacy_dev_marker = clips_root / ".complete"
    extracted = marker.exists() or (split == "dev" and legacy_dev_marker.exists())
    if not extracted:
        safe_extract(archive_path, clips_root)
    marker.write_text(f"FLEURS {split} archive extracted successfully.\n", encoding="utf-8")
    return build_manifest(language_root, language=LANGUAGES[code], split=split)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("data/fleurs"))
    parser.add_argument("--split", choices=("dev", "train", "test"), default="dev", help="Use train for the larger production language model; dev is the fast bootstrap set.")
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/fleurs_hindi_english.jsonl"))
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    for code in LANGUAGES:
        rows.extend(download_language(args.output_root, code=code, split=args.split))
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"dataset": REPO_ID, "license": "CC-BY", "split": args.split, "examples": len(rows), "manifest": str(args.manifest)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
