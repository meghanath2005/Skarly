from fastapi.testclient import TestClient

from app.main import app
from app.services import jobs as producer_jobs


client = TestClient(app)


def setup_function():
    producer_jobs.clear_jobs()


def test_improve_lyrics_api_works():
    response = client.post(
        "/improve-lyrics",
        json={
            "lyrics": "mera dil tumhare bina adhoora hai tum aa jao",
            "language": "Hinglish",
            "production_style": "Bollywood Ballad",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["assistant_mode"] == "rules"
    assert "[Mukhda]" in data["improved_lyrics"]
    assert data["pronunciation_notes"]


def test_producer_suggest_api_works():
    response = client.post(
        "/producer/suggest",
        json={"lyrics": "yaad tanha adhoora dil judaai aansu", "mood_tags": ["heartbreak"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["recommended_preset_id"] == "bollywood_ballad_piano"
    assert data["recommended_instruments"]
    assert data["reasoning"]


def test_producer_explain_quality_api_works():
    response = client.post(
        "/producer/explain-quality",
        json={
            "quality_report": {
                "audio_exists": True,
                "is_silent": True,
                "warnings": ["Generated audio appears silent."],
                "passed": False,
            }
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_friendly_status"] == "Needs attention"
    assert any("silent" in issue.lower() for issue in data["issues"])


def test_analyze_returns_assistant_recommendations():
    response = client.post("/analyze", json={"lyrics": "maula dua ibadat rooh", "language": "Hindi"})

    assert response.status_code == 200
    data = response.json()
    assert data["production_recommendations"]
    assert any("Suggested preset" in item for item in data["production_recommendations"])


def test_existing_prompt_preview_still_works_with_assistant_reasoning():
    response = client.post("/prompt/preview", json={"preset_id": "bollywood_ballad_piano", "lyrics": "Tum yaad aaye"})

    assert response.status_code == 200
    data = response.json()
    assert data["positive_prompt"]
    assert data["assistant_reasoning"]
