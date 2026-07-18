from fastapi.testclient import TestClient

from app.main import app
from app.services import jobs as producer_jobs


client = TestClient(app)


def setup_function():
    producer_jobs.clear_jobs()


def test_get_presets_works():
    response = client.get("/presets")

    assert response.status_code == 200
    data = response.json()
    assert data["default_preset_id"] == "bollywood_ballad_piano"
    assert "Pop" in data["available_genres"]
    assert "Bollywood Ballad" in data["available_production_styles"]
    assert "Piano-led cinematic" in data["available_arrangement_styles"]
    assert len(data["presets"]) >= 7


def test_get_preset_by_id_works():
    response = client.get("/presets/bollywood_ballad_piano")

    assert response.status_code == 200
    assert response.json()["name"] == "Hindi Romantic Ballad"


def test_prompt_preview_works():
    response = client.post(
        "/prompt/preview",
        json={
            "preset_id": "bollywood_ballad_piano",
            "lyrics": "Tum yaad aaye",
            "language": "Hindi",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "positive_prompt" in data
    assert data["structured_summary"]["production_style"] == "Bollywood Ballad"
    assert data["recommended_settings"]["bpm"] == 88


def test_generate_returns_mock_job_and_status_can_be_loaded():
    response = client.post(
        "/generate",
        json={
            "preset_id": "bollywood_ballad_piano",
            "lyrics": "Tum yaad aaye",
            "language": "Hindi",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"]
    assert data["status"] == "completed_mock"
    assert data["message"] == "Prompt generated successfully. Real audio generation is disabled."
    assert data["generation_mode"] == "mock"
    assert data["diagnostics"]["generator_name"] == "mock_prompt_builder"
    assert data["quality_report"]["audio_exists"] is False

    status = client.get(f"/jobs/{data['job_id']}")
    assert status.status_code == 200
    assert status.json()["positive_prompt"] == data["positive_prompt"]


def test_invalid_preset_id_returns_clear_404():
    response = client.post("/prompt/preview", json={"preset_id": "missing_preset", "genre": "Pop"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Preset 'missing_preset' not found"


def test_analyze_returns_mock_song_analysis():
    response = client.post("/analyze", json={"preset_id": "qawwali_fusion"})

    assert response.status_code == 200
    data = response.json()
    assert data["production_style"] == "Qawwali Fusion"
    assert data["arrangement_style"] == "Qawwali harmonium + claps"
    assert "harmonium" in data["main_instruments"]
    assert data["production_recommendations"]


def test_improve_lyrics_returns_rule_based_rewrite():
    response = client.post(
        "/improve-lyrics",
        json={
            "lyrics": "Dil ki baat",
            "language": "Hindi",
            "mood_tags": ["romantic"],
            "production_style": "Bollywood Ballad",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["original_lyrics"] == "Dil ki baat"
    assert data["assistant_mode"] == "rules"
    assert data["improved_lyrics"]
    assert data["pronunciation_notes"]


def test_mix_requires_audio_inputs_and_export_is_mocked():
    mix = client.post("/mix")
    export = client.post("/export")

    assert mix.status_code == 200
    assert mix.json()["status"] == "mix_failed"
    assert "vocal_audio_path" in mix.json()["diagnostics"]["error_message"]
    assert export.status_code == 200
    assert export.json()["status"] == "not_implemented"
