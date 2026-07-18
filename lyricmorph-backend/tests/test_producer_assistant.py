from app.models import ProducerSuggestionRequest, QualityExplanationRequest, QualityReport
from app.services.producer_assistant import explain_quality_report_rules, suggest_producer_settings


def test_heartbreak_lyrics_suggest_hindi_romantic_ballad():
    response = suggest_producer_settings(
        ProducerSuggestionRequest(lyrics="yaad tanha adhoora dil judaai aansu", mood_tags=["heartbreak"])
    )

    assert response.recommended_preset_id == "bollywood_ballad_piano"
    assert response.recommended_production_style == "Bollywood Ballad"


def test_devotional_terms_suggest_bhajan():
    response = suggest_producer_settings(
        ProducerSuggestionRequest(lyrics="ram krishna shiv mandir bhajan devotion")
    )

    assert response.recommended_preset_id == "devotional_bhajan"
    assert response.recommended_production_style == "Bhajan / Devotional"


def test_sufi_terms_suggest_qawwali_or_sufi_rock():
    response = suggest_producer_settings(
        ProducerSuggestionRequest(lyrics="maula allah dua ibadat rooh sufi")
    )

    assert response.recommended_preset_id in {"qawwali_fusion", "sufi_rock"}


def test_lofi_mood_suggests_lofi_cover():
    response = suggest_producer_settings(
        ProducerSuggestionRequest(mood_tags=["late-night", "nostalgic", "soft"], lyrics="rain memory")
    )

    assert response.recommended_preset_id == "lofi_hindi_cover"
    assert response.recommended_arrangement_style == "Lo-fi warm tape"


def test_trap_modern_mood_suggests_trap_soul():
    response = suggest_producer_settings(
        ProducerSuggestionRequest(lyrics="dark modern toxic nightlife moody 808")
    )

    assert response.recommended_preset_id == "trap_soul_hindi"


def test_unknown_input_returns_default_preset():
    response = suggest_producer_settings(ProducerSuggestionRequest(lyrics=""))

    assert response.recommended_preset_id == "bollywood_ballad_piano"


def test_quality_explanation_for_silent_audio_is_simple():
    response = explain_quality_report_rules(
        QualityExplanationRequest(
            quality_report=QualityReport(audio_exists=True, is_silent=True, passed=False, warnings=["silent"])
        )
    )

    assert response.user_friendly_status == "Needs attention"
    assert any("silent" in issue.lower() for issue in response.issues)
    assert response.suggested_fixes
