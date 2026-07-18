from __future__ import annotations

from pathlib import Path
import hashlib
import json
import math
import struct
import time
import wave

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.main import app
from app.models import SkarlyDetected, SkarlyStudioResponse, SkarlyVersion
from app.services import skarly_studio, studio_v2_jobs


client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer guest:v2-owner"}


def test_v2_restart_marks_unfinished_jobs_retryable(tmp_path):
    queued = studio_v2_jobs.create_job(
        tmp_path,
        job_type="generation",
        owner_id="restart-owner",
        total_arrangements=1,
    )

    assert studio_v2_jobs.recover_interrupted_jobs(tmp_path) == 1
    recovered = studio_v2_jobs.get_job(tmp_path, queued["job_id"])
    assert recovered is not None
    assert recovered["status"] == "failed"
    assert recovered["stage"] == "interrupted"
    assert recovered["error"]["retryable"] is True
    assert "completed source arrangements remain available" in recovered["error"]["message"]


def v2_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        uploads_dir=str(tmp_path / "uploads"),
        skarly_output_dir=str(tmp_path / "skarly"),
        skarly_generator_backend="procedural_v2",
        require_cuda=False,
        allow_cpu_generation_fallback=False,
        melody_analyzer_backend="off",
        stem_separator_backend="off",
        whisper_path=str(tmp_path / "missing-whisper"),
        audio_classifier_checkpoint=None,
        training_feedback_enabled=True,
        training_feedback_dir=str(tmp_path / "consented-feedback"),
        training_feedback_manifest=str(tmp_path / "manifests" / "v2-feedback.jsonl"),
        ffmpeg_path="ffmpeg",
        mixing_timeout_sec=30,
        ace_step_max_duration_seconds=300,
    )


def make_wav(path: Path, *, seconds: float = 1.25, sample_rate: int = 16000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        for index in range(frame_count):
            envelope = 0.75 if 0.10 < (index / sample_rate) < seconds - 0.10 else 0.0
            sample = int(12000 * envelope * math.sin(2 * math.pi * 220 * index / sample_rate))
            stream.writeframesraw(struct.pack("<h", sample))
    return path


def upload_wav(tmp_path: Path) -> dict:
    source = make_wav(tmp_path / "v2-vocal.wav")
    response = client.post(
        "/uploads/audio",
        files={"file": (source.name, source.read_bytes(), "audio/wav")},
    )
    assert response.status_code == 200
    return response.json()


def wait_for_job(job_id: str, *, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v2/jobs/{job_id}", headers=AUTH_HEADERS)
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"ready", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"V2 job {job_id} did not finish within {timeout}s")


def test_v2_profiles_expose_five_defaults_and_replacements(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", v2_settings(tmp_path))

    response = client.get("/api/v2/producer-profiles", headers=AUTH_HEADERS)

    assert response.status_code == 200
    profiles = response.json()
    assert [item["profile_id"] for item in profiles if item["is_default"]] == list(
        skarly_studio.DEFAULT_HINDI_PRODUCER_PROFILE_IDS
    )
    assert {"lofi", "rock", "edm", "ghazal", "orchestral", "indie", "rnb_urban"}.issubset(
        {item["profile_id"] for item in profiles}
    )
    assert all(item["instruments"] and len(item["blueprint"]) >= 9 for item in profiles)


def test_v2_generation_preserves_full_song_mode_into_studio_pipeline(monkeypatch, tmp_path):
    runtime_settings = v2_settings(tmp_path)
    monkeypatch.setattr(main_module, "settings", runtime_settings)
    upload = upload_wav(tmp_path)
    queued_analysis = client.post(
        "/api/v2/analyse",
        headers=AUTH_HEADERS,
        json={"upload_id": upload["upload_id"]},
    )
    analysis = wait_for_job(queued_analysis.json()["job_id"])
    captured: dict = {}

    def fake_generate_versions(**kwargs):
        captured.update(kwargs)
        versions = [
            SkarlyVersion(
                name=f"Version {index}",
                backing_url=f"/outputs/skarly/fake/backing_{index}.wav",
                final_mix_url=f"/outputs/skarly/fake/final_mix_{index}.mp3",
                style_family=profile,
            )
            for index, profile in enumerate(skarly_studio.DEFAULT_HINDI_PRODUCER_PROFILE_IDS, start=1)
        ]
        return SkarlyStudioResponse(
            job_id="skarly_job_v2_full_song",
            detected=SkarlyDetected(language="Hindi", mood="Romantic", bpm=96, key="D minor"),
            versions=versions,
            generator_backend="ace_step",
        )

    monkeypatch.setattr(skarly_studio, "generate_versions", fake_generate_versions)
    queued = client.post(
        "/api/v2/generations",
        headers=AUTH_HEADERS,
        json={
            "analysis_id": analysis["job_id"],
            "duration_seconds": upload["duration_seconds"],
            "require_cuda": False,
            "arrangement_mode": "full_song",
            "preserve_original_vocal": True,
            "reference_strength": 0.42,
        },
    )

    completed = wait_for_job(queued.json()["job_id"])

    assert completed["status"] == "ready"
    assert captured["arrangement_mode"] == "full_song"
    assert captured["preserve_original_vocal"] is True
    assert captured["reference_strength"] == 0.42
    assert captured["verify_music_transform_vocals"] is True


def test_v2_analysis_and_generation_are_persisted_async_jobs(monkeypatch, tmp_path):
    runtime_settings = v2_settings(tmp_path)
    monkeypatch.setattr(main_module, "settings", runtime_settings)
    upload = upload_wav(tmp_path)

    started = time.monotonic()
    queued_analysis = client.post(
        "/api/v2/analyse",
        headers=AUTH_HEADERS,
        json={"upload_id": upload["upload_id"], "language_override": "Hindi", "mood_override": "Romantic"},
    )
    request_seconds = time.monotonic() - started

    assert queued_analysis.status_code == 202
    assert request_seconds < 2
    analysis_id = queued_analysis.json()["job_id"]
    assert analysis_id.startswith("analysis_")
    analysis = wait_for_job(analysis_id)
    assert analysis["status"] == "ready", analysis.get("error")
    assert analysis["stage"] == "awaiting_confirmation"
    assert analysis["result"]["song_intelligence_map"]["duration_seconds"] == upload["duration_seconds"]
    assert analysis["result"]["song_intelligence_map"]["language"]["primary"] == "hi"

    persisted_analysis = Path(runtime_settings.skarly_output_dir) / "_v2_jobs" / f"{analysis_id}.json"
    assert persisted_analysis.is_file()
    assert json.loads(persisted_analysis.read_text(encoding="utf-8"))["status"] == "ready"

    wrong_duration = client.post(
        "/api/v2/generations",
        headers=AUTH_HEADERS,
        json={"analysis_id": analysis_id, "duration_seconds": 10, "require_cuda": False},
    )
    assert wrong_duration.status_code == 400
    assert "decoded vocal duration" in wrong_duration.json()["detail"]

    queued_generation = client.post(
        "/api/v2/generations",
        headers=AUTH_HEADERS,
        json={
            "analysis_id": analysis_id,
            "duration_seconds": upload["duration_seconds"],
            "mix_profile": "vocal_forward",
            "require_cuda": False,
            "number_of_outputs": 5,
            "bpm_override": 96,
            "key_override": "D minor",
        },
    )
    assert queued_generation.status_code == 202
    generation_id = queued_generation.json()["job_id"]
    assert generation_id.startswith("generation_")

    generation = wait_for_job(generation_id, timeout=45)
    assert generation["status"] == "ready", generation.get("error")
    assert generation["stage"] == "ready"
    assert generation["completed_arrangements"] == 5
    assert generation["total_arrangements"] == 5
    assert generation["model"] == "procedural_v2"
    assert len(generation["completed_outputs"]) == 5
    assert [item["name"] for item in generation["result"]["versions"]] == list(
        skarly_studio.HINDI_BOLLYWOOD_VERSION_NAMES
    )
    assert [item["style_family"] for item in generation["result"]["versions"]] == list(
        skarly_studio.DEFAULT_HINDI_PRODUCER_PROFILE_IDS
    )
    assert generation["result"]["mix_preset"] == "vocal_forward"
    assert generation["result"]["detected"]["bpm"] == 96
    assert generation["result"]["detected"]["key"] == "D minor"
    corrected_map = generation["result"]["song_intelligence_map"]
    assert corrected_map["tempo"]["bpm"] == 96
    assert corrected_map["tempo"]["confidence"] == 1.0
    assert corrected_map["tempo"]["source"] == "creator_confirmed_global_bpm"
    assert corrected_map["tonality"]["key"] == "D"
    assert corrected_map["tonality"]["scale"] == "minor"
    assert corrected_map["tonality"]["confidence"] == 1.0
    assert corrected_map["tonality"]["source"] == "creator_confirmed_key"
    assert corrected_map["confirmed_corrections"]["bpm"]["confirmed"] == 96
    assert corrected_map["confirmed_corrections"]["key"]["confirmed"] == "D minor"
    diversity = generation["result"]["arrangement_diversity"]
    assert diversity["passed"] is True
    assert diversity["evaluated_pairs"] == 10
    assert diversity["rejected_pairs"] == 0
    assert len(diversity["pairs"]) == 10

    persisted_generation = Path(runtime_settings.skarly_output_dir) / "_v2_jobs" / f"{generation_id}.json"
    assert persisted_generation.is_file()
    persisted_generation_data = json.loads(persisted_generation.read_text(encoding="utf-8"))
    assert persisted_generation_data["completed_arrangements"] == 5
    assert persisted_generation_data["request"]["bpm_override"] == 96
    assert persisted_generation_data["request"]["key_override"] == "D minor"
    analysis_manifest = (
        Path(runtime_settings.skarly_output_dir)
        / generation["result"]["analysis_url"].removeprefix("/outputs/skarly/")
    )
    assert json.loads(analysis_manifest.read_text(encoding="utf-8"))["arrangement_diversity"]["evaluated_pairs"] == 10

    invalid_section = client.post(
        "/api/v2/generations/regenerate-section",
        headers=AUTH_HEADERS,
        json={
            "generation_id": generation_id,
            "version_index": 0,
            "section_name": "hook",
            "section_start_seconds": 0.9,
            "section_end_seconds": 0.8,
            "edit_instruction": "Add a warmer string response.",
        },
    )
    assert invalid_section.status_code == 400
    assert "later than section start" in invalid_section.json()["detail"]

    section_without_ace = client.post(
        "/api/v2/generations/regenerate-section",
        headers=AUTH_HEADERS,
        json={
            "generation_id": generation_id,
            "version_index": 0,
            "section_name": "hook",
            "section_start_seconds": 0.2,
            "section_end_seconds": 1.0,
            "edit_instruction": "Add a warmer string response.",
        },
    )
    assert section_without_ace.status_code == 503
    assert "ACE-Step generator" in section_without_ace.json()["detail"]

    exported = client.post(
        "/api/v2/exports",
        headers=AUTH_HEADERS,
        json={"generation_id": generation_id, "version_index": 0, "include_optional_stems": True},
    )
    assert exported.status_code == 201, exported.text
    export = exported.json()
    assert export["duration_seconds"] == upload["duration_seconds"]
    assert {
        "final_wav",
        "final_mp3",
        "instrumental",
        "processed_vocal",
        "analysis_json",
        "song_map_json",
        "ai_generation_metadata",
        "bundle_zip",
    }.issubset(export["files"])
    core_duration_keys = {"final_wav", "final_mp3", "instrumental", "processed_vocal"}
    assert core_duration_keys.issubset(export["durations_seconds"])
    assert all(value == pytest.approx(upload["duration_seconds"], abs=0.08) for value in export["durations_seconds"].values())
    assert len(set(export["sha256"].values())) == len(export["sha256"])
    export_root = Path(runtime_settings.exports_dir)
    metadata_path = export_root / export["files"]["ai_generation_metadata"].removeprefix("/outputs/exports/")
    disclosure = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert disclosure["model"] == "procedural_v2"
    assert disclosure["disclosure"]["voice_cloning"] is False
    assert disclosure["arrangement_diversity"]["evaluated_pairs"] == 10
    optional_stem_keys = {"stem_drums", "stem_bass", "stem_other"}
    if optional_stem_keys.issubset(export["files"]):
        assert optional_stem_keys.issubset(export["durations_seconds"])
    else:
        assert any("Optional" in warning and "stems" in warning for warning in export["warnings"]), export["warnings"]

    first_version = generation["result"]["versions"][0]
    backing_path = (
        Path(runtime_settings.skarly_output_dir)
        / first_version["backing_url"].removeprefix("/outputs/skarly/")
    ).resolve()
    backing_hash_before = hashlib.sha256(backing_path.read_bytes()).hexdigest()
    # A music-to-music job can expose the separated singer per version while
    # leaving the top-level vocal URL empty until the creator asks for a mix.
    # The adaptive mixer must use that real processed-vocal stem.
    generation_without_mixed_vocal = json.loads(json.dumps(generation["result"]))
    generation_without_mixed_vocal["vocal_url"] = None
    studio_v2_jobs.update_job(
        runtime_settings.skarly_output_dir,
        generation_id,
        result=generation_without_mixed_vocal,
    )
    queued_mix = client.post(
        "/api/v2/mixes",
        headers=AUTH_HEADERS,
        json={
            "generation_id": generation_id,
            "version_index": 0,
            "mix_profile": "beat_forward",
            "vocal_music_balance": -0.35,
        },
    )
    assert queued_mix.status_code == 202
    remix = wait_for_job(queued_mix.json()["job_id"])
    assert remix["status"] == "ready", remix.get("error")
    assert remix["result"]["regenerated_arrangement"] is False
    assert remix["result"]["mix_profile"] == "beat_forward"
    assert remix["result"]["duration_seconds"] == upload["duration_seconds"]
    assert "multiband ducking protects the presence range" in remix["result"]["mix_note"]
    assert hashlib.sha256(backing_path.read_bytes()).hexdigest() == backing_hash_before
    persisted_remix_parent = wait_for_job(generation_id)
    assert persisted_remix_parent["result"]["vocal_url"] == first_version["input_vocal_url"]
    assert persisted_remix_parent["result"]["versions"][0]["final_mix_url"] == remix["result"]["final_mix_url"]
    assert persisted_remix_parent["completed_outputs"][0]["final_mix_url"] == remix["result"]["final_mix_url"]

    feedback_without_consent = client.post(
        "/api/v2/feedback",
        headers=AUTH_HEADERS,
        json={
            "generation_id": generation_id,
            "selected_arrangement": 0,
            "mix_preference": "beat_forward",
            "user_rating": 4,
            "explicit_training_consent": False,
        },
    )
    assert feedback_without_consent.status_code == 201
    assert feedback_without_consent.json()["status"] == "ready"
    assert feedback_without_consent.json()["result"]["retained_audio_path"] is None
    assert not Path(runtime_settings.training_feedback_manifest).exists()

    invalid_consent = client.post(
        "/api/v2/feedback",
        headers=AUTH_HEADERS,
        json={"generation_id": generation_id, "explicit_training_consent": True},
    )
    assert invalid_consent.status_code == 400
    assert "Training consent requires" in invalid_consent.json()["detail"]

    consented_feedback = client.post(
        "/api/v2/feedback",
        headers=AUTH_HEADERS,
        json={
            "generation_id": generation_id,
            "selected_arrangement": 0,
            "corrected_genre": "Bollywood ballad",
            "corrected_language": "Hindi",
            "mix_preference": "balanced",
            "user_rating": 5,
            "explicit_training_consent": True,
            "dataset_usage_permission_version": "creator-terms-2026-07",
            "rights_confirmed": True,
            "copyright_owner": "Test creator",
            "commercial_use_permission": True,
            "revocation_policy": "Delete from future dataset versions on request.",
            "singer_id": "test-singer-001",
            "recording_conditions": "Creator-owned home recording",
            "confirmed_singing_speech": "singing",
            "confirmed_vocal_techniques": ["vibrato", "ornamented"],
            "confirmed_moods": ["romantic", "intimate"],
            "confirmed_tempo_family": "medium",
            "confirmed_melodic_character": "indian",
            "confirmed_in_distribution": True,
        },
    )
    assert consented_feedback.status_code == 201
    consented = consented_feedback.json()
    assert consented["result"]["retained_audio_path"]
    assert Path(consented["result"]["retained_audio_path"]).is_file()
    manifest_rows = [
        json.loads(line)
        for line in Path(runtime_settings.training_feedback_manifest).read_text(encoding="utf-8").splitlines()
    ]
    assert len(manifest_rows) == 1
    assert manifest_rows[0]["label_origin"] == "creator_confirmed"
    assert manifest_rows[0]["dataset_usage_permission_version"] == "creator-terms-2026-07"
    assert manifest_rows[0]["commercial_use_permission"] is True
    assert manifest_rows[0]["singing_speech"] == "singing"
    assert manifest_rows[0]["vocal_techniques"] == ["vibrato", "ornamented"]
    assert manifest_rows[0]["moods"] == ["romantic", "intimate"]
    assert manifest_rows[0]["tempo_family"] == "medium"
    assert manifest_rows[0]["melodic_character"] == "indian"
    assert manifest_rows[0]["in_distribution"] is True

    generation_before = client.get(f"/api/v2/jobs/{generation_id}", headers=AUTH_HEADERS).json()
    before_hashes = []
    for version in generation_before["result"]["versions"]:
        path = Path(runtime_settings.skarly_output_dir) / version["backing_url"].removeprefix("/outputs/skarly/")
        before_hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
    queued_regeneration = client.post(
        "/api/v2/generations/regenerate",
        headers=AUTH_HEADERS,
        json={
            "generation_id": generation_id,
            "version_index": 0,
            "energy_delta": 1,
            "instrument_change": "replace acoustic guitar with sitar",
        },
    )
    assert queued_regeneration.status_code == 202, queued_regeneration.text
    regeneration = wait_for_job(queued_regeneration.json()["job_id"], timeout=45)
    assert regeneration["status"] == "ready", regeneration.get("error")
    assert regeneration["completed_arrangements"] == 1
    assert regeneration["total_arrangements"] == 1
    assert regeneration["result"]["preserved_versions"] == 4
    assert regeneration["result"]["regenerated_arrangement"] is True
    regeneration_telemetry = regeneration["result"]["generation_telemetry"]
    assert regeneration_telemetry["cuda_available"] is False
    assert regeneration_telemetry["generation_backend"] == "cpu"
    assert regeneration_telemetry["compiled_architectures"] == []
    assert regeneration_telemetry["cpu_fallback"] is True
    updated = regeneration["result"]["updated_generation"]
    assert len(updated["versions"]) == 5
    assert updated["arrangement_diversity"]["passed"] is True
    assert updated["arrangement_diversity"]["evaluated_pairs"] == 10
    assert "sitar" in updated["versions"][0]["instruments"]
    assert "increased energy" in updated["versions"][0]["energy"]
    after_hashes = []
    for version in updated["versions"]:
        path = Path(runtime_settings.skarly_output_dir) / version["backing_url"].removeprefix("/outputs/skarly/")
        after_hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
    assert after_hashes[0] != before_hashes[0]
    assert after_hashes[1:] == before_hashes[1:]
    persisted_after = client.get(f"/api/v2/jobs/{generation_id}", headers=AUTH_HEADERS).json()
    assert persisted_after["result"]["versions"][0]["backing_url"] == updated["versions"][0]["backing_url"]
    assert len(persisted_after["result"]["regeneration_history"]) == 1


def test_v2_generation_telemetry_preserves_complete_cuda_evidence():
    telemetry = main_module._v2_generation_telemetry(
        cuda_info={
            "cuda_available": True,
            "device": "NVIDIA GeForce RTX 5070 Laptop GPU",
            "device_capability": "12.0",
            "torch_version": "2.7.1+cu128",
            "torch_cuda_runtime": "12.8",
            "compiled_architectures": ["sm_90", "sm_120"],
        },
        generator_backend="ace_step",
        model="acestep-v15-turbo",
        peak_vram_mb=6390.126,
        generation_seconds=6.2824,
        cpu_fallback=False,
    )

    assert telemetry == {
        "cuda_available": True,
        "device": "NVIDIA GeForce RTX 5070 Laptop GPU",
        "device_capability": "12.0",
        "torch_version": "2.7.1+cu128",
        "torch_cuda_runtime": "12.8",
        "compiled_architectures": ["sm_90", "sm_120"],
        "generation_backend": "cuda",
        "model": "acestep-v15-turbo",
        "peak_vram_mb": 6390.13,
        "generation_seconds": 6.282,
        "cpu_fallback": False,
    }


def test_v2_jobs_are_owner_scoped_and_generation_validates_profiles(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", v2_settings(tmp_path))
    upload = upload_wav(tmp_path)
    queued = client.post(
        "/api/v2/analyse",
        headers=AUTH_HEADERS,
        json={"upload_id": upload["upload_id"]},
    )
    assert queued.status_code == 202
    analysis = wait_for_job(queued.json()["job_id"])
    assert analysis["status"] == "ready"

    forbidden = client.get(
        f"/api/v2/jobs/{analysis['job_id']}",
        headers={"Authorization": "Bearer guest:someone-else"},
    )
    assert forbidden.status_code == 403

    duplicate_profiles = client.post(
        "/api/v2/generations",
        headers=AUTH_HEADERS,
        json={
            "analysis_id": analysis["job_id"],
            "require_cuda": False,
            "arrangement_profiles": ["lofi", "lofi", "rock", "edm", "ghazal"],
        },
    )
    assert duplicate_profiles.status_code == 422

    invalid_corrections = client.post(
        "/api/v2/generations",
        headers=AUTH_HEADERS,
        json={
            "analysis_id": analysis["job_id"],
            "require_cuda": False,
            "bpm_override": 20,
            "key_override": "D dorian",
        },
    )
    assert invalid_corrections.status_code == 422
    invalid_fields = {item["loc"][-1] for item in invalid_corrections.json()["detail"]}
    assert {"bpm_override", "key_override"}.issubset(invalid_fields)
