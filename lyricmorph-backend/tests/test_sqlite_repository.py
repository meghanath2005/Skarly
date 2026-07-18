from app.models import CreatorMode, Genre, JobRecord, JobStatus, SourceType, UserProfileRequest, VoiceTakeRequest, now_utc
from app.repository import SqliteJobRepository, SqliteStore, SqliteUsageRepository, SqliteUserRepository, SqliteVoiceTakeRepository
from app.worker import build_song_blueprint, fallback_song_analysis


def test_sqlite_project_vault_persists_jobs_profiles_takes_and_usage(tmp_path):
    store = SqliteStore(str(tmp_path / "skarly.sqlite3"))
    jobs = SqliteJobRepository(store)
    users = SqliteUserRepository(store)
    takes = SqliteVoiceTakeRepository(store)
    usage = SqliteUsageRepository(store)

    profile = users.upsert("user_1", UserProfileRequest(name="Demo Artist", email="artist@example.com"))
    assert profile.email == "artist@example.com"

    take = takes.create(
        "user_1",
        VoiceTakeRequest(
            title="Verse idea",
            duration=12,
            raw_audio_path="users/user_1/raw/upload/voice.webm",
            content_type="audio/webm",
        ),
    )
    assert take.take_id.startswith("take_")

    timestamp = now_utc()
    analysis = fallback_song_analysis(Genre.rnb, {"duration": 32, "tempo_bpm": 84})
    blueprint = build_song_blueprint(analysis, Genre.rnb)
    job = JobRecord(
        job_id="job_demo",
        user_id="user_1",
        creator_mode=CreatorMode.saved,
        genre=Genre.rnb,
        track_name="Late Night Idea",
        source_type=SourceType.recording,
        raw_audio_path="users/user_1/raw/upload/voice.webm",
        status=JobStatus.ready,
        stage="ready",
        final_mp3_path="users/user_1/final/job_demo/late-night-idea.mp3",
        export_paths={"producer_pack": "users/user_1/exports/job_demo/producer-pack.zip"},
        analysis=analysis,
        blueprint=blueprint,
        created_at=timestamp,
        updated_at=timestamp,
    )
    jobs.create(job)
    assert usage.increment("lyria_2026_07") == 1

    reloaded_store = SqliteStore(str(tmp_path / "skarly.sqlite3"))
    reloaded_jobs = SqliteJobRepository(reloaded_store)
    reloaded_users = SqliteUserRepository(reloaded_store)
    reloaded_takes = SqliteVoiceTakeRepository(reloaded_store)
    reloaded_usage = SqliteUsageRepository(reloaded_store)

    reloaded_job = reloaded_jobs.get("job_demo")
    assert reloaded_job is not None
    assert reloaded_job.analysis.key == "A minor"
    assert reloaded_job.blueprint.chords == ["Am", "F", "C", "G"]
    assert reloaded_users.get("user_1").name == "Demo Artist"
    assert reloaded_takes.list_for_user("user_1")[0].title == "Verse idea"
    assert reloaded_usage.get("lyria_2026_07") == 1

