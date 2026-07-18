import pytest
from pydantic import ValidationError

from app.models import CreateJobRequest, Genre, ProductionStyle, SongGenerateRequest, SourceType


def test_song_generate_request_accepts_existing_genres():
    for genre in ["Rock", "Pop", "Hip-hop", "R&B", "Lo-fi", "Piano", "Acoustic", "Cinematic"]:
        request = SongGenerateRequest(genre=genre)

        assert request.genre == genre


def test_song_generate_request_accepts_unknown_genre_without_crashing():
    request = SongGenerateRequest(genre="Hindi Indie Folk")

    assert request.genre == "Hindi Indie Folk"


def test_bpm_validation():
    with pytest.raises(ValidationError):
        SongGenerateRequest(genre="Pop", bpm=39)

    with pytest.raises(ValidationError):
        SongGenerateRequest(genre="Pop", bpm=221)

    assert SongGenerateRequest(genre="Pop", bpm=88).bpm == 88


def test_duration_validation():
    with pytest.raises(ValidationError):
        SongGenerateRequest(genre="Pop", duration_seconds=9)

    with pytest.raises(ValidationError):
        SongGenerateRequest(genre="Pop", duration_seconds=601)

    assert SongGenerateRequest(genre="Pop", duration_seconds=90).duration_seconds == 90


def test_song_generate_defaults():
    request = SongGenerateRequest()

    assert request.language == "Hindi"
    assert request.genre == "Pop"
    assert request.mood_tags == []
    assert request.instruments == []
    assert request.ducking_enabled is True
    assert request.vocal_forward_mix is True
    assert request.output_format == "mp3"


def test_create_job_accepts_multilingual_vocal_to_music_intent():
    request = CreateJobRequest(
        raw_audio_path="users/guest/guest-session/raw/upload/voice.wav",
        genre=Genre.pop,
        track_name="Hinglish Demo",
        source_type=SourceType.recording,
        language="Hinglish",
        lyrics="mera dil tumhare bina adhoora hai",
        production_style=ProductionStyle.sufi_rock,
        arrangement_style="Indie band arrangement",
        main_instruments=["piano", "electric guitar", "dholak"],
        mood_tags=["romantic", "emotional"],
        output_duration_seconds=60,
        vocal_gain_db=2.5,
        backing_gain_db=-4.0,
        ducking_strength="medium",
    )

    assert request.language == "Hinglish"
    assert request.lyrics.startswith("mera dil")
    assert request.production_style == ProductionStyle.sufi_rock
    assert request.mood_tags == ["romantic", "emotional"]


def test_output_format_validation():
    assert SongGenerateRequest(output_format="WAV").output_format == "wav"

    with pytest.raises(ValidationError):
        SongGenerateRequest(output_format="flac")
