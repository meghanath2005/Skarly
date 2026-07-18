from app.models import LyricsImproveRequest
from app.services.producer_assistant import (
    add_song_sections,
    detect_language_style,
    improve_lyrics_rules,
    pronunciation_notes_for_hinglish,
)


def test_improves_rough_hinglish_romantic_lyrics():
    response = improve_lyrics_rules(
        LyricsImproveRequest(
            lyrics="mera dil tumhare bina adhoora hai tum aa jao",
            language="Hinglish",
            production_style="Bollywood Ballad",
        )
    )

    assert response.assistant_mode == "rules"
    assert response.detected_language_style == "Hinglish"
    assert "[Mukhda]" in response.improved_lyrics
    assert "Mera dil adhoora" in response.improved_lyrics
    assert "Aa jao" in response.improved_lyrics


def test_adds_section_labels():
    improved = add_song_sections("mera dil tumhare bina adhoora hai tum aa jao", "Bollywood Ballad")

    assert "[Mukhda]" in improved
    assert "[Hook]" in improved


def test_preserves_core_meaning():
    response = improve_lyrics_rules(
        LyricsImproveRequest(lyrics="mera dil tumhare bina adhoora hai tum aa jao", language="Hinglish")
    )
    lowered = response.improved_lyrics.lower()

    assert "dil" in lowered
    assert "adhoora" in lowered
    assert "tere bina" in lowered
    assert "aa jao" in lowered


def test_returns_pronunciation_notes():
    notes = pronunciation_notes_for_hinglish("Mere khwaab aur yaad saath hain")

    assert any("kh" in note.lower() for note in notes)
    assert any("khwaab" in note.lower() for note in notes)


def test_handles_empty_lyrics_safely():
    response = improve_lyrics_rules(LyricsImproveRequest(lyrics=""))

    assert response.improved_lyrics == ""
    assert response.warnings
    assert response.detected_language_style == "Unknown"


def test_does_not_put_copy_instruction_in_improved_lyrics():
    response = improve_lyrics_rules(
        LyricsImproveRequest(lyrics="make it like Tum Hi Ho mera dil adhoora hai", language="Hinglish")
    )

    assert "copy existing song" not in response.improved_lyrics.lower()
    assert "tum hi ho" not in response.improved_lyrics.lower()


def test_detect_language_style_handles_urdu_touch():
    assert detect_language_style("ishq aur khwaab ki rooh") == "Urdu-touch Hindi"
