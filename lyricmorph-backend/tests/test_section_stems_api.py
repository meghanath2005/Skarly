from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.main import app


client = TestClient(app)


def phase9_settings(tmp_path: Path, *, stems_enabled: bool = True, section_mode: str = "prompt_only") -> Settings:
    return Settings(
        ace_step_enabled=False,
        stems_enabled=stems_enabled,
        stems_engine="demucs",
        stems_output_dir=str(tmp_path / "stems"),
        demucs_cli_path="fake-demucs",
        section_editing_enabled=True,
        section_editing_mode=section_mode,
        section_output_dir=str(tmp_path / "sections"),
    )


def section_payload() -> dict:
    return {
        "section_name": "hook",
        "edit_instruction": "Make hook more emotional with cinematic strings.",
        "lyrics": "mera dil adhoora hai",
        "language": "Hindi",
        "genre": "Pop",
        "production_style": "Bollywood Ballad",
        "arrangement_style": "Piano-led cinematic",
        "mood_tags": ["heartbreak"],
        "instruments": ["piano", "strings"],
        "bpm": 88,
        "key": "A minor",
    }


def test_sections_edit_works_in_prompt_only_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase9_settings(tmp_path, section_mode="prompt_only"))

    response = client.post("/sections/edit", json=section_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "prompt_ready"
    assert data["mode"] == "prompt_only"
    assert "hook" in data["edit_prompt"].lower()
    assert data["message"] == "Section edit prompt prepared without changing audio."


def test_sections_prompt_works(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase9_settings(tmp_path, section_mode="ace_step"))

    response = client.post("/sections/prompt", json=section_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "prompt_ready"
    assert data["mode"] == "prompt_only"
    assert "Create original audio" in data["edit_prompt"]


def test_stems_separate_missing_file_returns_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase9_settings(tmp_path, stems_enabled=True))

    response = client.post(
        "/stems/separate",
        json={"audio_path": str(tmp_path / "missing.wav"), "stems": ["vocals", "drums", "bass", "other"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_found"
    assert data["diagnostics"]["failed_step"] == "stem_separation"
    assert any("does not exist" in warning for warning in data["warnings"])


def test_stems_separate_disabled_returns_not_enabled(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase9_settings(tmp_path, stems_enabled=False))

    response = client.post(
        "/stems/separate",
        json={"audio_path": str(tmp_path / "missing.wav"), "stems": ["vocals"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_enabled"
    assert "STEMS_ENABLED" in data["diagnostics"]["suggested_fix"]


def test_existing_presets_endpoint_still_works():
    response = client.get("/presets")

    assert response.status_code == 200
    data = response.json()
    assert data["default_preset_id"] == "bollywood_ballad_piano"
    assert data["presets"]
