"""Build auditable JSONL training manifests for Skarly's local classifier."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".opus"}


def write_rows(rows: list[dict[str, object]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(output), "examples": len(rows)}, ensure_ascii=False))


def common_voice_rows(dataset_root: Path, language: str, split: str) -> list[dict[str, object]]:
    tsv = dataset_root / f"{split}.tsv"
    clips = dataset_root / "clips"
    if not tsv.exists():
        raise FileNotFoundError(f"Could not find {tsv}. Extract the Common Voice language archive first.")
    if not clips.exists():
        raise FileNotFoundError(f"Could not find {clips}. Expected Common Voice clips directory.")
    rows: list[dict[str, object]] = []
    with tsv.open("r", encoding="utf-8", newline="") as handle:
        for item in csv.DictReader(handle, delimiter="\t"):
            relative = str(item.get("path") or "").strip()
            audio_path = clips / relative
            if relative and audio_path.is_file():
                rows.append({
                    "audio_path": str(audio_path.resolve()),
                    "language": language,
                    "genre": None,
                    "source": "common_voice",
                    "split": split,
                    "rights_confirmed": True,
                })
    return rows


def owned_music_rows(audio_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for audio_path in sorted(audio_root.rglob("*")):
        if not audio_path.is_file() or audio_path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        relative = audio_path.relative_to(audio_root)
        if len(relative.parts) < 3:
            raise ValueError(
                f"{audio_path} must be under language/genre/file.ext (for example Hindi/indie_pop/song.wav)."
            )
        language, genre = relative.parts[0], relative.parts[1]
        rows.append({
            "audio_path": str(audio_path.resolve()),
            "language": language,
            "genre": genre,
            "source": "owned_or_consented_music",
            "rights_confirmed": True,
        })
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    common_voice = subparsers.add_parser("common-voice", help="Create a language-only manifest from an extracted Common Voice archive.")
    common_voice.add_argument("--dataset-root", type=Path, required=True)
    common_voice.add_argument("--language", required=True)
    common_voice.add_argument("--split", default="validated", choices=("validated", "train", "dev", "test"))
    common_voice.add_argument("--output", type=Path, required=True)

    owned_music = subparsers.add_parser("owned-music", help="Create a language+genre manifest from rights-cleared music.")
    owned_music.add_argument("--audio-root", type=Path, required=True)
    owned_music.add_argument("--output", type=Path, required=True)
    owned_music.add_argument("--rights-confirmed", action="store_true", help="Required acknowledgement that every file is licensed for this ML training.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "common-voice":
        write_rows(common_voice_rows(args.dataset_root, args.language, args.split), args.output)
        return
    if not args.rights_confirmed:
        raise SystemExit("Refusing to create a music-training manifest without --rights-confirmed.")
    write_rows(owned_music_rows(args.audio_root), args.output)


if __name__ == "__main__":
    main()
