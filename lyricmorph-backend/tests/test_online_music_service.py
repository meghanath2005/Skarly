import math
import wave
from pathlib import Path

import numpy as np

from app.config import Settings
from app.models import VocalAnalysisReport, VocalToMusicRequest
from app.services.online_music import (
    build_composition_plan,
    build_elevenlabs_payload,
    sanitize_generation_text,
)


def analysis_report() -> VocalAnalysisReport:
    return VocalAnalysisReport(
        upload_id="upload_vocal",
        source_audio_path="vocal.wav",
        normalized_wav_path="normalized.wav",
        duration_seconds=42.0,
        sample_rate=44100,
        channels=1,
        is_silent=False,
        estimated_bpm=88.0,
        estimated_key="A minor",
        phrase_boundaries=[{"phrase": 1, "start_seconds": 0.0, "end_seconds": 4.0}],
        section_candidates=[
            {"name": "intro", "start_seconds": 0.0, "end_seconds": 4.0},
            {"name": "mukhda", "start_seconds": 4.0, "end_seconds": 18.0},
            {"name": "hook", "start_seconds": 18.0, "end_seconds": 30.0},
            {"name": "outro", "start_seconds": 30.0, "end_seconds": 42.0},
        ],
    )


def test_sanitize_generation_text_removes_famous_copying_language():
    sanitized = sanitize_generation_text("make it exactly like Tum Hi Ho by Arijit Singh and copy the melody")

    assert "Tum Hi Ho" not in sanitized
    assert "Arijit" not in sanitized
    assert "copy the melody" not in sanitized
    assert "Hindi romantic Bollywood ballad" in sanitized


def test_composition_plan_uses_vocal_analysis_and_originality_rules():
    request = VocalToMusicRequest(
        upload_id="upload_vocal",
        lyrics="mera dil tumhare bina adhoora hai, make it like Tum Hi Ho",
        production_style="Sufi Rock",
        arrangement_style="Indie band arrangement",
        mood_tags=["sad", "rock"],
        instruments=["piano", "electric guitar", "drums"],
        rights_confirmed=True,
    )

    plan = build_composition_plan(request, analysis=analysis_report(), mode="vocal_to_music", provider_order=["elevenlabs"])

    assert plan.bpm == 88
    assert plan.key == "A minor"
    assert plan.duration_seconds == 42
    assert "hook" in plan.provider_prompt
    assert "Tum Hi Ho" not in plan.provider_prompt
    assert "artist voice" in plan.provider_prompt
    assert plan.provider_preferences == ["elevenlabs"]
    assert plan.warnings


def test_elevenlabs_payload_requests_instrumental_duration():
    request = VocalToMusicRequest(upload_id="upload_vocal", duration_seconds=30, rights_confirmed=True)
    plan = build_composition_plan(request, analysis=analysis_report(), mode="vocal_to_music")

    payload = build_elevenlabs_payload(plan, Settings(elevenlabs_music_model="music_v2_test"))

    assert payload["force_instrumental"] is True
    assert payload["music_length_ms"] == 30000
    assert payload["model_id"] == "music_v2_test"
    assert "instrumental" in payload["prompt"]
