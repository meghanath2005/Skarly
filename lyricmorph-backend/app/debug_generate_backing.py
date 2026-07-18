from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import ArrangementMode, Genre
from .worker import (
    apply_user_overrides_to_analysis,
    build_producer_negative_prompt,
    build_producer_prompt,
    build_song_blueprint,
    create_music_bed_with_report,
    fallback_song_analysis,
    media_duration_seconds,
)
from .config import settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a backing track without running the full upload pipeline.")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--bpm", type=float, default=None)
    parser.add_argument("--key", default=None)
    parser.add_argument("--genre", default="Pop")
    parser.add_argument("--production-style", default=None)
    parser.add_argument("--arrangement-style", default=None)
    parser.add_argument("--energy", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--arrangement-mode", default=ArrangementMode.vocal_to_song.value)
    return parser.parse_args()


def genre_from_value(value: str) -> Genre:
    for genre in Genre:
        if genre.value.lower() == value.strip().lower():
            return genre
    raise SystemExit(f"Unsupported genre: {value}")


def main() -> None:
    args = parse_args()
    genre = genre_from_value(args.genre)
    output = Path(args.output) if args.output else Path.cwd() / "debug-backing.wav"
    output.parent.mkdir(parents=True, exist_ok=True)

    timing = {
        "duration": args.duration,
        "tempo_bpm": args.bpm,
        "production_style": args.production_style,
        "arrangement_style": args.arrangement_style,
        "arrangement_mode": args.arrangement_mode,
    }
    overrides = {
        "production_bpm": args.bpm,
        "key": args.key,
        "energy": args.energy,
        "output_duration_seconds": args.duration,
    }
    analysis = apply_user_overrides_to_analysis(fallback_song_analysis(genre, timing), overrides)
    blueprint = build_song_blueprint(analysis, genre, timing)
    producer_prompt = build_producer_prompt(genre, analysis, blueprint, ArrangementMode(args.arrangement_mode), timing)
    producer_negative_prompt = build_producer_negative_prompt(genre, analysis)
    timing.update(
        {
            "production_bpm": analysis.production_bpm,
            "primary_key": analysis.primary_key,
            "energy": analysis.energy,
            "production_style": analysis.production_style,
            "arrangement_style": analysis.arrangement_style,
            "main_instruments": analysis.main_instruments,
            "producer_prompt": producer_prompt,
            "producer_negative_prompt": producer_negative_prompt,
        }
    )

    report = create_music_bed_with_report(output, genre, "debug_backing", args.duration, timing=timing, ffmpeg_path=settings.ffmpeg_path)
    summary = {
        "selected_generator": report.get("selected_generator"),
        "fallback_enabled": settings.ace_step_fallback_to_procedural,
        "fallback_attempted": report.get("fallback_attempted"),
        "fallback_result": report.get("fallback_result"),
        "final_generator_used": report.get("final_generator_used"),
        "duration": args.duration,
        "bpm": analysis.production_bpm,
        "key": analysis.primary_key,
        "genre": genre.value,
        "production_style": analysis.production_style,
        "arrangement_style": analysis.arrangement_style,
        "producer_prompt": producer_prompt,
        "output_path": str(output),
        "file_exists": output.exists(),
        "file_size": output.stat().st_size if output.exists() else 0,
        "ffprobe_duration": media_duration_seconds(output, settings.ffmpeg_path),
        "success": bool(report.get("final_generator_used")),
        "failure_reason": report.get("ace_step_error") or report.get("lyria_error"),
        "generation_report": report,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
