from fastapi.testclient import TestClient
from urllib.parse import quote

import app.main as main_module
from app.config import Settings
from app.main import app
from app.models import ArrangementMode, JobStatus
from app.repository import jobs, usage, voice_takes
from app.storage import MockStorageService
from app.tasks import InMemoryTaskQueue
from app.worker import MockAIWorker


client = TestClient(app)


def setup_function():
    jobs.clear()
    voice_takes.clear()
    usage.clear()
    main_module.settings = Settings(app_env="local", storage_backend="mock", repository_backend="memory", worker_backend="mock", music_generator_backend="procedural_v2")
    main_module.worker = MockAIWorker(jobs)
    main_module.storage = MockStorageService()
    main_module.task_queue = InMemoryTaskQueue()


def auth(user: str = "demo-user") -> dict[str, str]:
    return {"Authorization": f"Bearer guest:{user}"}


def seed_raw_audio(path: str, data: bytes = b"raw-audio") -> None:
    main_module.storage.upload_bytes(path, data, "audio/webm")


def test_health_smoke():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["timeouts"]["backing_generation_timeout_sec"] == 600


def test_local_capabilities_and_agent_plan():
    capabilities = client.get("/v1/local/capabilities")
    plan = client.post("/v1/local/agent", json={"genre": "Lo-fi", "source_type": "recording", "duration_seconds": 12})

    assert capabilities.status_code == 200
    assert "gpu" in capabilities.json()
    assert plan.status_code == 200
    assert plan.json()["mode"] in {"rule_agent", "local_llm"}


def test_local_storage_routes_round_trip_uploaded_audio():
    object_path = "users/demo-user/raw/upload_route/voice.webm"

    upload = client.put(
        f"/test-storage/upload/{quote(object_path, safe='')}",
        content=b"voice-bytes",
        headers={"Content-Type": "audio/webm"},
    )
    download = client.get(f"/test-storage/download/{quote(object_path, safe='')}")

    assert upload.status_code == 204
    assert download.status_code == 200
    assert download.content == b"voice-bytes"


def create_uploaded_job(user: str = "demo-user", delete_raw_after_mix: bool = True) -> str:
    raw_path = f"users/{user}/raw/upload_test/voice.mp3"
    seed_raw_audio(raw_path)
    response = client.post(
        "/v1/jobs",
        headers=auth(user),
        json={
            "raw_audio_path": raw_path,
            "genre": "Lo-fi",
            "track_name": "Ocean Demo",
            "source_type": "localUpload",
            "delete_raw_after_mix": delete_raw_after_mix,
        },
    )
    assert response.status_code == 200
    return response.json()["job"]["job_id"]


def test_auth_failure_returns_401():
    response = client.get("/v1/history")

    assert response.status_code == 401


def test_guest_session_token_is_accepted():
    response = client.get("/v1/history", headers=auth("demo-user"))

    assert response.status_code == 200


def test_unscoped_bearer_token_is_rejected():
    response = client.get("/v1/history", headers={"Authorization": "Bearer demo-user"})

    assert response.status_code == 401


def test_create_job_accepts_arrangement_mode():
    raw_path = "users/demo-user/raw/upload_test/music.mp3"
    seed_raw_audio(raw_path)

    response = client.post(
        "/v1/jobs",
        headers=auth(),
        json={
            "raw_audio_path": raw_path,
            "genre": "Rock",
            "track_name": "Music Remake",
            "source_type": "localUpload",
            "arrangement_mode": ArrangementMode.music_to_music.value,
            "delete_raw_after_mix": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["job"]["arrangement_mode"] == "music_to_music"


def test_create_job_accepts_optional_production_style_fields():
    raw_path = "users/demo-user/raw/upload_test/style.mp3"
    seed_raw_audio(raw_path)

    response = client.post(
        "/v1/jobs",
        headers=auth(),
        json={
            "raw_audio_path": raw_path,
            "genre": "Pop",
            "production_style": "Bollywood Ballad",
            "arrangement_style": "Piano-led cinematic",
            "main_instruments": ["piano", "strings", "pads", "soft drums", "bass"],
            "production_bpm": 62.5,
            "key_override": "C major",
            "energy_override": "medium-low",
            "output_duration_seconds": 30,
            "vocal_gain_db": 1.5,
            "backing_gain_db": -3.0,
            "ducking_strength": "medium",
            "track_name": "Styled Demo",
            "source_type": "localUpload",
            "delete_raw_after_mix": False,
        },
    )

    assert response.status_code == 200
    job = response.json()["job"]
    assert job["genre"] == "Pop"
    assert job["production_style"] == "Bollywood Ballad"
    assert job["arrangement_style"] == "Piano-led cinematic"
    assert job["main_instruments"] == ["piano", "strings", "pads", "soft drums", "bass"]
    assert job["user_overrides"]["production_bpm"] == 62.5
    assert job["user_overrides"]["key"] == "C major"
    assert job["user_overrides"]["energy"] == "medium-low"
    assert job["user_overrides"]["output_duration_seconds"] == 30
    assert job["user_overrides"]["vocal_gain_db"] == 1.5
    assert job["user_overrides"]["backing_gain_db"] == -3.0
    assert job["user_overrides"]["ducking_strength"] == "medium"


def test_signed_upload_response_shape():
    response = client.post(
        "/v1/uploads/sign",
        headers=auth(),
        json={
            "filename": "voice_take_01.mp3",
            "content_type": "audio/mpeg",
            "size_bytes": 2500000,
            "source_type": "localUpload",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["upload_id"].startswith("upload_")
    assert data["raw_audio_path"].startswith("users/guest/demo-user/raw/")
    assert "/test-storage/upload/" in data["upload_url"]
    assert data["expires_in_seconds"] == 900


def test_guest_signed_uploads_share_guest_workspace():
    response = client.post(
        "/v1/uploads/sign",
        headers=auth("demo-session"),
        json={
            "filename": "guest_take.webm",
            "content_type": "audio/webm",
            "size_bytes": 250000,
            "source_type": "recording",
        },
    )

    assert response.status_code == 200
    assert response.json()["raw_audio_path"].startswith("users/guest/demo-session/raw/")


def test_upload_verification_reports_existing_and_missing_raw_audio():
    raw_path = "users/demo-user/raw/upload_test/voice.webm"
    seed_raw_audio(raw_path)

    existing = client.post(
        "/v1/uploads/verify",
        headers=auth(),
        json={"raw_audio_path": raw_path},
    )
    missing = client.post(
        "/v1/uploads/verify",
        headers=auth(),
        json={"raw_audio_path": "users/demo-user/raw/upload_test/missing.webm"},
    )

    assert existing.status_code == 200
    assert existing.json()["exists"] is True
    assert missing.status_code == 200
    assert missing.json()["exists"] is False


def test_upload_bytes_fallback_writes_raw_audio():
    raw_path = "users/demo-user/raw/upload_test/fallback.webm"

    response = client.post(
        f"/v1/uploads/bytes?raw_audio_path={raw_path}&content_type=audio/webm",
        headers=auth(),
        content=b"voice-bytes",
    )

    assert response.status_code == 200
    assert response.json()["exists"] is True
    assert main_module.storage.download_bytes(raw_path) == b"voice-bytes"


def test_voice_take_metadata_can_be_saved_listed_and_deleted():
    seed_raw_audio("users/demo-user/raw/upload_test/voice.webm")
    create = client.post(
        "/v1/voice-takes",
        headers=auth(),
        json={
            "title": "Voice take 1",
            "duration": 12,
            "raw_audio_path": "users/demo-user/raw/upload_test/voice.webm",
            "content_type": "audio/webm",
            "size_bytes": 12000,
        },
    )

    assert create.status_code == 200
    take_id = create.json()["take"]["take_id"]

    listed = client.get("/v1/voice-takes", headers=auth())
    assert listed.status_code == 200
    assert listed.json()["takes"][0]["title"] == "Voice take 1"

    deleted = client.delete(f"/v1/voice-takes/{take_id}", headers=auth())
    assert deleted.status_code == 200
    assert client.get("/v1/voice-takes", headers=auth()).json()["takes"] == []


def test_voice_take_playback_returns_signed_raw_url():
    seed_raw_audio("users/demo-user/raw/upload_test/voice.webm")
    create = client.post(
        "/v1/voice-takes",
        headers=auth(),
        json={
            "title": "Voice take 1",
            "duration": 12,
            "raw_audio_path": "users/demo-user/raw/upload_test/voice.webm",
            "content_type": "audio/webm",
            "size_bytes": 12000,
        },
    )
    take_id = create.json()["take"]["take_id"]

    response = client.get(f"/v1/voice-takes/{take_id}/play", headers=auth())

    assert response.status_code == 200
    assert response.json()["take_id"] == take_id
    assert "/test-storage/download/" in response.json()["raw_audio_url"]


def test_voice_take_recycle_restore_and_permanent_delete_removes_storage():
    raw_path = "users/demo-user/raw/upload_test/recyclable.webm"
    seed_raw_audio(raw_path, b"raw")
    create = client.post(
        "/v1/voice-takes",
        headers=auth(),
        json={
            "title": "Recyclable take",
            "duration": 12,
            "raw_audio_path": raw_path,
            "content_type": "audio/webm",
            "size_bytes": 12000,
        },
    )
    take_id = create.json()["take"]["take_id"]

    deleted = client.delete(f"/v1/voice-takes/{take_id}", headers=auth())
    assert deleted.status_code == 200
    assert deleted.json()["take"]["status"] == "deleted"
    assert client.get("/v1/voice-takes", headers=auth()).json()["takes"] == []
    assert client.get("/v1/recycle-bin", headers=auth()).json()["voice_takes"][0]["take_id"] == take_id

    restored = client.post(f"/v1/voice-takes/{take_id}/restore", headers=auth())
    assert restored.status_code == 200
    assert restored.json()["take"]["status"] == "active"
    assert client.get("/v1/voice-takes", headers=auth()).json()["takes"][0]["take_id"] == take_id

    client.delete(f"/v1/voice-takes/{take_id}", headers=auth())
    permanent = client.delete(f"/v1/voice-takes/{take_id}/permanent", headers=auth())
    assert permanent.status_code == 200
    try:
        main_module.storage.download_bytes(raw_path)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Permanent delete should remove raw storage object")


def test_voice_take_rejects_other_user_raw_path():
    response = client.post(
        "/v1/voice-takes",
        headers=auth("user-one"),
        json={
            "title": "Bad take",
            "duration": 8,
            "raw_audio_path": "users/user-two/raw/upload_test/voice.webm",
            "content_type": "audio/webm",
        },
    )

    assert response.status_code == 403


def test_library_recovery_builds_metadata_from_storage_objects():
    main_module.storage.upload_bytes("users/demo-user/raw/upload_old/Voice take 1.webm", b"raw", "audio/webm")
    main_module.storage.upload_bytes("users/demo-user/final/job_old/My Mix.mp3", b"mp3", "audio/mpeg")
    main_module.storage.upload_bytes("users/demo-user/final/job_stale/final.mp3", b"mp3", "audio/mpeg")
    main_module.storage.upload_bytes("users/guest/demo-user--demo-use/raw/upload_new/New take.webm", b"raw", "audio/webm")

    response = client.post("/v1/library/recover", headers=auth())

    assert response.status_code == 200
    data = response.json()
    assert data["recovered_voice_takes"] == 0
    assert data["recovered_tracks"] == 1
    assert data["takes"] == []
    assert data["tracks"][0]["final_mp3_path"] == "users/demo-user/final/job_old/My Mix.mp3"


def test_history_hides_stale_placeholder_jobs():
    stale_id = create_uploaded_job("demo-user", delete_raw_after_mix=False)
    ready_id = create_uploaded_job("demo-user", delete_raw_after_mix=False)
    main_module.jobs.update_library(stale_id, "Pending backend draft", None)
    main_module.jobs.update_library(ready_id, "Named Track", None)
    main_module.jobs.update_status(stale_id, JobStatus.ready, "ready")
    main_module.jobs.set_final_mp3(stale_id, "users/demo-user/final/job_stale/final.mp3")
    main_module.jobs.update_status(ready_id, JobStatus.ready, "ready")
    main_module.jobs.set_final_mp3(ready_id, "users/demo-user/final/job_ready/named-track.mp3")

    response = client.get("/v1/history", headers=auth())

    assert response.status_code == 200
    titles = [track["track_name"] for track in response.json()["tracks"]]
    assert titles == ["Named Track"]


def test_create_job_rejects_raw_audio_path_from_another_user():
    response = client.post(
        "/v1/jobs",
        headers=auth("user-one"),
        json={
            "raw_audio_path": "users/user-two/raw/upload_test/voice.mp3",
            "genre": "Lo-fi",
            "track_name": "Cross User Attempt",
            "source_type": "localUpload",
            "delete_raw_after_mix": True,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Raw audio path belongs to another user"


def test_create_job_rejects_missing_raw_audio_object():
    response = client.post(
        "/v1/jobs",
        headers=auth(),
        json={
            "raw_audio_path": "users/demo-user/raw/upload_missing/voice.mp3",
            "genre": "Lo-fi",
            "track_name": "Missing Raw",
            "source_type": "localUpload",
            "delete_raw_after_mix": True,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Raw audio file was not uploaded. Upload the audio before generating."


def test_voice_take_rejects_missing_raw_audio_object():
    response = client.post(
        "/v1/voice-takes",
        headers=auth(),
        json={
            "title": "Missing take",
            "duration": 8,
            "raw_audio_path": "users/demo-user/raw/upload_missing/voice.webm",
            "content_type": "audio/webm",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Raw audio file was not uploaded. Upload the audio before saving."


def test_job_ownership_is_enforced():
    job_id = create_uploaded_job("owner-user")

    response = client.get(f"/v1/jobs/{job_id}", headers=auth("other-user"))

    assert response.status_code == 403


def test_job_library_metadata_can_be_updated_by_owner():
    job_id = create_uploaded_job("owner-user")

    response = client.patch(
        f"/v1/jobs/{job_id}/library",
        headers=auth("owner-user"),
        json={"track_name": "Ocean Demo Final", "library_status": "Saved"},
    )

    assert response.status_code == 200
    assert response.json()["job"]["track_name"] == "Ocean Demo Final"
    assert response.json()["job"]["library_status"] == "Saved"


def test_job_library_metadata_update_enforces_ownership():
    job_id = create_uploaded_job("owner-user")

    response = client.patch(
        f"/v1/jobs/{job_id}/library",
        headers=auth("other-user"),
        json={"track_name": "Steal Attempt", "library_status": "Saved"},
    )

    assert response.status_code == 403


def test_retry_fails_after_raw_audio_deleted():
    job_id = create_uploaded_job(delete_raw_after_mix=True)
    worker_response = client.post(f"/v1/worker/jobs/{job_id}/run")
    assert worker_response.status_code == 200
    assert worker_response.json()["job"]["raw_audio_path"] is None

    retry_response = client.post(f"/v1/jobs/{job_id}/retry", headers=auth())

    assert retry_response.status_code == 409


def test_worker_produces_ready_job_with_download_url():
    job_id = create_uploaded_job(delete_raw_after_mix=False)

    response = client.post(f"/v1/worker/jobs/{job_id}/run")

    assert response.status_code == 200
    data = response.json()
    assert data["job"]["status"] == "ready"
    assert data["job"]["raw_audio_path"] == "users/demo-user/raw/upload_test/voice.mp3"
    assert data["job"]["final_mp3_path"].startswith("users/demo-user/final/")
    assert "/test-storage/download/" in data["final_mp3_url"]

