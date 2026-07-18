import math
import wave
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.main import app
from app.models import MusicSourcePreparation
from app.services import jobs as producer_jobs
from app.services import online_music


client = TestClient(app)


def setup_function():
    producer_jobs.clear_jobs()


def online_settings(tmp_path: Path, require_rights: bool = True) -> Settings:
    return Settings(
        ace_step_enabled=False,
        online_music_enabled=True,
        require_rights_confirmation=require_rights,
        generate_candidate_count=1,
        uploads_dir=str(tmp_path / "uploads"),
        online_music_output_dir=str(tmp_path / "online_music"),
        procedural_output_dir=str(tmp_path / "procedural"),
        mix_output_dir=str(tmp_path / "mixes"),
        projects_dir=str(tmp_path / "projects"),
        exports_dir=str(tmp_path / "exports"),
        stems_output_dir=str(tmp_path / "stems"),
        section_output_dir=str(tmp_path / "sections"),
        mix_default_format="wav",
        music_to_music_verify_generated_vocals=False,
    )


def write_wav(path: Path, seconds: float = 4.0, frequency: float = 330.0, amplitude: float = 0.35, sample_rate: int = 22050) -> Path:
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    samples = amplitude * np.sin(2 * math.pi * frequency * t)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path


def upload_wav(tmp_path: Path, name: str = "vocal.wav", frequency: float = 330.0) -> dict:
    wav_path = write_wav(tmp_path / name, frequency=frequency)
    with wav_path.open("rb") as handle:
        response = client.post("/uploads/audio", files={"file": (name, handle, "audio/wav")})
    assert response.status_code == 200
    return response.json()


def test_uploads_audio_endpoint_and_analyze(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", online_settings(tmp_path))
    upload = upload_wav(tmp_path)

    assert upload["upload_id"].startswith("upload_")
    assert upload["audio_url"].startswith("/outputs/uploads/")
    assert upload["quality_report"]["passed"] is True

    analysis = client.post(f"/uploads/{upload['upload_id']}/analyze")
    assert analysis.status_code == 200
    data = analysis.json()
    assert data["estimated_bpm"] is not None
    assert data["estimated_key"]


def test_vocal_to_music_requires_rights_confirmation(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", online_settings(tmp_path, require_rights=True))
    upload = upload_wav(tmp_path)

    response = client.post("/v2/vocal-to-music", json={"upload_id": upload["upload_id"], "candidate_count": 1})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rights_required"
    assert data["diagnostics"]["failed_step"] == "rights_confirmation"


def test_vocal_to_music_mocked_online_provider_success(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", online_settings(tmp_path, require_rights=True))
    upload = upload_wav(tmp_path)

    def fake_generate(self, *, plan, candidate_id, settings, output_format):
        output = write_wav(Path(settings.online_music_output_dir) / f"{candidate_id}.wav", seconds=plan.duration_seconds or 4, frequency=120.0)
        return online_music.ProviderGenerationResult(
            success=True,
            provider_name="elevenlabs",
            output_path=str(output),
            logs=["mock online provider generated backing"],
        )

    monkeypatch.setattr(online_music.ElevenMusicProvider, "generate", fake_generate)

    response = client.post(
        "/v2/vocal-to-music",
        json={
            "upload_id": upload["upload_id"],
            "rights_confirmed": True,
            "candidate_count": 1,
            "provider_preference": "elevenlabs",
            "duration_seconds": 4,
            "output_format": "wav",
            "production_style": "Sufi Rock",
            "arrangement_style": "Indie band arrangement",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"completed", "completed_needs_review"}
    assert data["best_candidate"]["provider_name"] == "elevenlabs"
    assert data["best_candidate"]["mixed_preview_url"].startswith("/outputs/mixes/")
    assert data["best_candidate"]["mix_quality_report"]["passed"] is True

    job = client.get(f"/jobs/{data['job_id']}")
    assert job.status_code == 200
    assert job.json()["online_response"]["best_candidate"]["provider_name"] == "elevenlabs"


def test_vocal_to_music_without_keys_uses_local_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", online_settings(tmp_path, require_rights=True))
    upload = upload_wav(tmp_path)

    response = client.post(
        "/v2/vocal-to-music",
        json={
            "upload_id": upload["upload_id"],
            "rights_confirmed": True,
            "candidate_count": 1,
            "duration_seconds": 4,
            "output_format": "wav",
            "provider_preference": "elevenlabs",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed_needs_review"
    assert data["best_candidate"]["provider_name"] == "local_fallback"
    assert data["diagnostics"]["fallback_used"] is True
    assert data["best_candidate"]["backing_audio_url"].startswith("/outputs/procedural_v2/")


def test_music_to_music_reference_flow_and_regenerate(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", online_settings(tmp_path, require_rights=True))
    reference = upload_wav(tmp_path, name="reference.wav", frequency=220.0)
    reference_paths = []

    def fake_ace_generate(self, *, plan, candidate_id, settings, output_format, reference_audio_path=None):
        reference_paths.append(reference_audio_path)
        output = write_wav(
            Path(settings.online_music_output_dir) / f"{candidate_id}_transformed.wav",
            seconds=plan.duration_seconds or 4,
            frequency=165.0,
        )
        return online_music.ProviderGenerationResult(
            success=True,
            provider_name="ace_step",
            output_path=str(output),
            logs=["mock ACE-Step reference transformation"],
            metadata={"reference_conditioned": True, "reference_strength": plan.reference_strength},
        )

    monkeypatch.setattr(online_music.LocalAceStepProvider, "generate", fake_ace_generate)

    response = client.post(
        "/v2/music-to-music",
        json={
            "reference_upload_id": reference["upload_id"],
            "rights_confirmed": True,
            "candidate_count": 1,
            "duration_seconds": 4,
            "output_format": "wav",
            "reference_strength": 0.3,
            "source_mode": "instrumental",
            "style_instruction": "make it sad piano rock Bollywood style, not a copy",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["mode"] == "music_to_music"
    assert data["best_candidate"]["provider_name"] == "ace_step"
    assert data["best_candidate"]["reference_conditioned"] is True
    assert data["best_candidate"]["reference_strength"] == 0.3
    assert data["best_candidate"]["backing_audio_url"].startswith("/outputs/online_music/")
    assert reference_paths[0] and reference_paths[0].endswith("normalized.wav")

    # Simulate a backend restart: the legacy in-memory producer job table is
    # empty, while the durable online response remains on disk.
    main_module.producer_jobs.clear_jobs()
    recovered = client.get(f"/jobs/{data['job_id']}")
    assert recovered.status_code == 200
    assert recovered.json()["online_response"]["job_id"] == data["job_id"]

    regen = client.post(
        f"/v2/jobs/{data['job_id']}/regenerate",
        json={"edit_instruction": "stronger rock drums and sadder piano", "rights_confirmed": True, "candidate_count": 1, "reference_strength": 0.45},
    )
    assert regen.status_code == 200
    regen_data = regen.json()
    assert regen_data["status"] == "completed"
    assert regen_data["best_candidate"]["reference_conditioned"] is True
    assert regen_data["best_candidate"]["reference_strength"] == 0.45
    assert len(reference_paths) == 2
    assert "Regeneration edit" in regen_data["composition_plan"]["provider_prompt"]


def test_music_to_music_auto_separates_full_song_and_preserves_original_vocal(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", online_settings(tmp_path, require_rights=True))
    reference = upload_wav(tmp_path, name="full-song.wav", frequency=220.0)
    separated_vocal = write_wav(tmp_path / "separated" / "vocals.wav", seconds=4, frequency=440.0)
    clean_instrumental = write_wav(tmp_path / "separated" / "no_vocals.wav", seconds=4, frequency=220.0)

    monkeypatch.setattr(
        online_music.music_source,
        "prepare_music_source",
        lambda **_kwargs: MusicSourcePreparation(
            requested_mode="auto",
            detected_mode="full_song",
            separation_status="completed",
            vocal_detected=True,
            vocal_preserved=True,
            detection_confidence=0.94,
            source_audio_path=reference["original_path"],
            instrumental_audio_path=str(clean_instrumental),
            instrumental_audio_url="/outputs/stems/no_vocals.wav",
            vocal_audio_path=str(separated_vocal),
            vocal_audio_url="/outputs/stems/vocals.wav",
            vocal_energy_db_below_mix=-8.0,
            vocal_activity_ratio=0.8,
        ),
    )
    reference_paths = []

    def fake_ace_generate(self, *, plan, candidate_id, settings, output_format, reference_audio_path=None):
        reference_paths.append(reference_audio_path)
        output = write_wav(
            Path(settings.online_music_output_dir) / f"{candidate_id}_transformed.wav",
            seconds=plan.duration_seconds or 4,
            frequency=165.0,
        )
        return online_music.ProviderGenerationResult(
            success=True,
            provider_name="ace_step",
            output_path=str(output),
            metadata={"reference_conditioned": True, "reference_strength": plan.reference_strength},
        )

    monkeypatch.setattr(online_music.LocalAceStepProvider, "generate", fake_ace_generate)
    response = client.post(
        "/v2/music-to-music",
        json={
            "reference_upload_id": reference["upload_id"],
            "rights_confirmed": True,
            "candidate_count": 1,
            "duration_seconds": 4,
            "output_format": "wav",
            "source_mode": "auto",
            "preserve_original_vocal": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["source_preparation"]["detected_mode"] == "full_song"
    assert data["source_preparation"]["vocal_preserved"] is True
    assert data["best_candidate"]["mixed_preview_url"].startswith("/outputs/mixes/")
    assert data["best_candidate"]["transformation_quality"]["passed"] is True
    assert reference_paths[0].endswith("normalized.wav")
    assert "_instrumental" in reference_paths[0]


def test_music_to_music_auto_separation_failure_does_not_generate(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", online_settings(tmp_path, require_rights=True))
    reference = upload_wav(tmp_path, name="full-song.wav", frequency=220.0)
    monkeypatch.setattr(
        online_music.music_source,
        "prepare_music_source",
        lambda **_kwargs: MusicSourcePreparation(
            requested_mode="auto",
            detected_mode="unknown",
            separation_status="failed",
            source_audio_path=reference["original_path"],
            warnings=["mock Demucs failure"],
        ),
    )
    monkeypatch.setattr(
        online_music.LocalAceStepProvider,
        "generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("generation must not run")),
    )

    response = client.post(
        "/v2/music-to-music",
        json={
            "reference_upload_id": reference["upload_id"],
            "rights_confirmed": True,
            "candidate_count": 1,
            "source_mode": "auto",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "separation_failed"
    assert data["diagnostics"]["failed_step"] == "source_separation"
    assert data["source_preparation"]["instrumental_audio_path"] is None


def test_existing_generate_mock_mode_still_works_with_online_additions(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", online_settings(tmp_path))

    response = client.post("/generate", json={"preset_id": "bollywood_ballad_piano"})

    assert response.status_code == 200
    assert response.json()["status"] == "completed_mock"
