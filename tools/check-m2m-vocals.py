from __future__ import annotations

import argparse
import json
from pathlib import Path

import whisper


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", nargs="+", type=Path)
    parser.add_argument("--model", default="base")
    args = parser.parse_args()

    model = whisper.load_model(args.model, device="cpu")
    results = []
    for path in args.audio:
        transcription = model.transcribe(
            str(path),
            fp16=False,
            temperature=0,
            condition_on_previous_text=False,
        )
        segments = transcription.get("segments") or []
        results.append(
            {
                "path": str(path.resolve()),
                "language": transcription.get("language"),
                "text": str(transcription.get("text") or "").strip(),
                "segment_count": len(segments),
                "average_no_speech_probability": round(
                    sum(float(item.get("no_speech_prob") or 0) for item in segments) / max(1, len(segments)),
                    6,
                ),
            }
        )
    print(json.dumps({"model": args.model, "device": "cpu", "outputs": results}, indent=2))


if __name__ == "__main__":
    main()
