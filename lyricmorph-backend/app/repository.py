from __future__ import annotations

import json
import sqlite3
from typing import Any

from .config import settings
from .models import (
    AdminUserSnapshot,
    ItemStatus,
    JobRecord,
    JobStatus,
    SongAnalysis,
    SongBlueprint,
    UserProfile,
    UserProfileRequest,
    VoiceTakeRecord,
    VoiceTakeRequest,
    new_id,
    now_utc,
)

try:
    from firebase_admin import firestore
except ImportError:  # pragma: no cover - dependency is present in normal backend installs.
    firestore = None


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}

    def create(self, job: JobRecord) -> JobRecord:
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def list_for_user(self, user_id: str) -> list[JobRecord]:
        jobs = [job for job in self._jobs.values() if job.user_id == user_id and job.status != JobStatus.deleted]
        return sorted(jobs, key=lambda job: job.created_at, reverse=True)

    def list_deleted_for_user(self, user_id: str) -> list[JobRecord]:
        jobs = [job for job in self._jobs.values() if job.user_id == user_id and job.status == JobStatus.deleted]
        return sorted(jobs, key=lambda job: job.deleted_at or job.updated_at, reverse=True)

    def clear(self) -> None:
        self._jobs.clear()

    def list_recent(self, limit: int = 25) -> list[JobRecord]:
        jobs = sorted(self._jobs.values(), key=lambda job: job.updated_at, reverse=True)
        return jobs[:limit]

    def list_deleted_recent(self, limit: int = 25) -> list[JobRecord]:
        jobs = [job for job in self._jobs.values() if job.status == JobStatus.deleted]
        return sorted(jobs, key=lambda job: job.deleted_at or job.updated_at, reverse=True)[:limit]

    def update_status(self, job_id: str, status: JobStatus, stage: str, error: str | None = None) -> JobRecord:
        job = self._require(job_id)
        job.status = status
        job.stage = stage
        job.error = error
        job.updated_at = now_utc()
        if status == JobStatus.ready:
            job.completed_at = job.updated_at
        self._jobs[job_id] = job
        return job

    def set_final_mp3(self, job_id: str, final_mp3_path: str) -> JobRecord:
        job = self._require(job_id)
        job.final_mp3_path = final_mp3_path
        job.updated_at = now_utc()
        self._jobs[job_id] = job
        return job

    def set_worker_artifacts(
        self,
        job_id: str,
        isolated_vocal_path: str | None = None,
        backing_audio_path: str | None = None,
        worker_notes: str | None = None,
        export_paths: dict[str, str] | None = None,
        analysis: SongAnalysis | None = None,
        blueprint: SongBlueprint | None = None,
        final_generation_settings: dict[str, Any] | None = None,
        generation_diagnostics: dict[str, Any] | None = None,
        job_logs: list[str] | None = None,
        quality_report: dict[str, Any] | None = None,
    ) -> JobRecord:
        job = self._require(job_id)
        job.isolated_vocal_path = isolated_vocal_path
        job.backing_audio_path = backing_audio_path
        job.worker_notes = worker_notes
        if export_paths is not None:
            job.export_paths = export_paths
        if analysis is not None:
            job.analysis = analysis
        if blueprint is not None:
            job.blueprint = blueprint
        if final_generation_settings is not None:
            job.final_generation_settings = final_generation_settings
        if generation_diagnostics is not None:
            job.generation_diagnostics = generation_diagnostics
        if job_logs is not None:
            job.job_logs = job_logs
        if quality_report is not None:
            job.quality_report = quality_report
        job.updated_at = now_utc()
        self._jobs[job_id] = job
        return job

    def delete_raw(self, job_id: str) -> JobRecord:
        job = self._require(job_id)
        job.raw_audio_path = None
        job.updated_at = now_utc()
        self._jobs[job_id] = job
        return job

    def update_library(self, job_id: str, track_name: str | None = None, library_status: str | None = None) -> JobRecord:
        job = self._require(job_id)
        if track_name is not None:
            job.track_name = track_name
        if library_status is not None:
            job.library_status = library_status
        job.updated_at = now_utc()
        self._jobs[job_id] = job
        return job

    def mark_deleted(self, job_id: str) -> JobRecord:
        job = self.update_status(job_id, JobStatus.deleted, "deleted")
        job.deleted_at = job.updated_at
        self._jobs[job_id] = job
        return job

    def restore(self, job_id: str) -> JobRecord:
        job = self._require(job_id)
        job.status = JobStatus.ready if job.final_mp3_path else JobStatus.queued
        job.stage = "ready" if job.final_mp3_path else "queued"
        job.deleted_at = None
        job.updated_at = now_utc()
        self._jobs[job_id] = job
        return job

    def permanent_delete(self, job_id: str) -> JobRecord:
        job = self._require(job_id)
        self._jobs.pop(job_id, None)
        return job

    def _require(self, job_id: str) -> JobRecord:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job


class DuplicateEmailError(ValueError):
    pass


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._profiles: dict[str, UserProfile] = {}
        self._email_to_user: dict[str, str] = {}

    def upsert(self, user_id: str, request: UserProfileRequest) -> UserProfile:
        email = request.email.strip().lower()
        existing_user_id = self._email_to_user.get(email)
        if existing_user_id is not None and existing_user_id != user_id:
            raise DuplicateEmailError(email)

        timestamp = now_utc()
        existing = self._profiles.get(user_id)
        if existing and existing.email != email:
            self._email_to_user.pop(existing.email, None)

        profile = UserProfile(
            user_id=user_id,
            name=request.name.strip(),
            email=email,
            bio=request.bio.strip() or "Private Skarly workspace",
            photo_url=request.photo_url,
            created_at=existing.created_at if existing else timestamp,
            updated_at=timestamp,
        )
        self._profiles[user_id] = profile
        self._email_to_user[email] = user_id
        return profile

    def get(self, user_id: str) -> UserProfile | None:
        return self._profiles.get(user_id)

    def email_exists_for_other_user(self, email: str, user_id: str) -> bool:
        existing_user_id = self._email_to_user.get(email.strip().lower())
        return existing_user_id is not None and existing_user_id != user_id

    def clear(self) -> None:
        self._profiles.clear()
        self._email_to_user.clear()

    def list_recent(self, limit: int = 25) -> list[AdminUserSnapshot]:
        profiles = sorted(self._profiles.values(), key=lambda profile: profile.updated_at, reverse=True)
        return [
            AdminUserSnapshot(user_id=profile.user_id, name=profile.name, email=profile.email, updated_at=profile.updated_at)
            for profile in profiles[:limit]
        ]


class InMemoryVoiceTakeRepository:
    def __init__(self) -> None:
        self._takes: dict[str, VoiceTakeRecord] = {}

    def create(self, user_id: str, request: VoiceTakeRequest) -> VoiceTakeRecord:
        timestamp = now_utc()
        take = VoiceTakeRecord(
            take_id=new_id("take"),
            user_id=user_id,
            title=request.title.strip(),
            duration=request.duration,
            raw_audio_path=request.raw_audio_path,
            content_type=request.content_type,
            size_bytes=request.size_bytes,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._takes[take.take_id] = take
        return take

    def list_for_user(self, user_id: str) -> list[VoiceTakeRecord]:
        takes = [take for take in self._takes.values() if take.user_id == user_id and take.status != ItemStatus.deleted]
        return sorted(takes, key=lambda take: take.created_at, reverse=True)

    def list_deleted_for_user(self, user_id: str) -> list[VoiceTakeRecord]:
        takes = [take for take in self._takes.values() if take.user_id == user_id and take.status == ItemStatus.deleted]
        return sorted(takes, key=lambda take: take.deleted_at or take.updated_at, reverse=True)

    def delete(self, user_id: str, take_id: str) -> VoiceTakeRecord:
        take = self._takes.get(take_id)
        if take is None:
            raise KeyError(take_id)
        if take.user_id != user_id:
            raise PermissionError(take_id)
        take.status = ItemStatus.deleted
        take.deleted_at = now_utc()
        take.updated_at = take.deleted_at
        self._takes[take_id] = take
        return take

    def restore(self, user_id: str, take_id: str) -> VoiceTakeRecord:
        take = self._takes.get(take_id)
        if take is None:
            raise KeyError(take_id)
        if take.user_id != user_id:
            raise PermissionError(take_id)
        take.status = ItemStatus.active
        take.deleted_at = None
        take.updated_at = now_utc()
        self._takes[take_id] = take
        return take

    def permanent_delete(self, user_id: str, take_id: str) -> VoiceTakeRecord:
        take = self._takes.get(take_id)
        if take is None:
            raise KeyError(take_id)
        if take.user_id != user_id:
            raise PermissionError(take_id)
        self._takes.pop(take_id, None)
        return take

    def clear(self) -> None:
        self._takes.clear()

    def list_recent(self, limit: int = 25) -> list[VoiceTakeRecord]:
        takes = sorted(self._takes.values(), key=lambda take: take.updated_at, reverse=True)
        return takes[:limit]

    def list_deleted_recent(self, limit: int = 25) -> list[VoiceTakeRecord]:
        takes = [take for take in self._takes.values() if take.status == ItemStatus.deleted]
        return sorted(takes, key=lambda take: take.deleted_at or take.updated_at, reverse=True)[:limit]


class InMemoryUsageRepository:
    def __init__(self) -> None:
        self._usage: dict[str, int] = {}

    def get(self, key: str) -> int:
        return self._usage.get(key, 0)

    def increment(self, key: str) -> int:
        self._usage[key] = self.get(key) + 1
        return self._usage[key]

    def clear(self) -> None:
        self._usage.clear()


def _job_to_document(job: JobRecord) -> dict[str, Any]:
    data = job.model_dump(mode="json")
    data["creator_mode"] = job.creator_mode.value
    data["genre"] = job.genre.value
    data["source_type"] = job.source_type.value
    data["status"] = job.status.value
    return data


def _profile_to_document(profile: UserProfile) -> dict[str, Any]:
    data = profile.model_dump(mode="json")
    data["creator_mode"] = profile.creator_mode.value
    return data


def _voice_take_to_document(take: VoiceTakeRecord) -> dict[str, Any]:
    data = take.model_dump(mode="json")
    data["status"] = take.status.value
    return data


class FirestoreJobRepository:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or _firestore_client()

    def create(self, job: JobRecord) -> JobRecord:
        self._job_ref(job.user_id, job.job_id).set(_job_to_document(job))
        return job

    def get(self, job_id: str) -> JobRecord | None:
        for snapshot in self.client.collection_group("jobs").stream():
            job = JobRecord.model_validate(snapshot.to_dict())
            if job.job_id == job_id:
                return job
        return None

    def list_for_user(self, user_id: str) -> list[JobRecord]:
        query = self._jobs_ref(user_id).order_by("created_at", direction="DESCENDING")
        jobs = [JobRecord.model_validate(snapshot.to_dict()) for snapshot in query.stream()]
        return [job for job in jobs if job.status != JobStatus.deleted]

    def list_deleted_for_user(self, user_id: str) -> list[JobRecord]:
        query = self._jobs_ref(user_id).order_by("updated_at", direction="DESCENDING")
        jobs = [JobRecord.model_validate(snapshot.to_dict()) for snapshot in query.stream()]
        return [job for job in jobs if job.status == JobStatus.deleted]

    def list_recent(self, limit: int = 25) -> list[JobRecord]:
        jobs = [JobRecord.model_validate(snapshot.to_dict()) for snapshot in self.client.collection_group("jobs").stream()]
        return sorted(jobs, key=lambda job: job.updated_at, reverse=True)[:limit]

    def list_deleted_recent(self, limit: int = 25) -> list[JobRecord]:
        jobs = [JobRecord.model_validate(snapshot.to_dict()) for snapshot in self.client.collection_group("jobs").stream()]
        jobs = [job for job in jobs if job.status == JobStatus.deleted]
        return sorted(jobs, key=lambda job: job.deleted_at or job.updated_at, reverse=True)[:limit]

    def clear(self) -> None:
        raise RuntimeError("Firestore repository clear is not supported")

    def update_status(self, job_id: str, status: JobStatus, stage: str, error: str | None = None) -> JobRecord:
        job = self._require(job_id)
        job.status = status
        job.stage = stage
        job.error = error
        job.updated_at = now_utc()
        if status == JobStatus.ready:
            job.completed_at = job.updated_at
        self._job_ref(job.user_id, job.job_id).set(_job_to_document(job))
        return job

    def set_final_mp3(self, job_id: str, final_mp3_path: str) -> JobRecord:
        job = self._require(job_id)
        job.final_mp3_path = final_mp3_path
        job.updated_at = now_utc()
        self._job_ref(job.user_id, job.job_id).set(_job_to_document(job))
        return job

    def set_worker_artifacts(
        self,
        job_id: str,
        isolated_vocal_path: str | None = None,
        backing_audio_path: str | None = None,
        worker_notes: str | None = None,
        export_paths: dict[str, str] | None = None,
        analysis: SongAnalysis | None = None,
        blueprint: SongBlueprint | None = None,
        final_generation_settings: dict[str, Any] | None = None,
        generation_diagnostics: dict[str, Any] | None = None,
        job_logs: list[str] | None = None,
        quality_report: dict[str, Any] | None = None,
    ) -> JobRecord:
        job = self._require(job_id)
        job.isolated_vocal_path = isolated_vocal_path
        job.backing_audio_path = backing_audio_path
        job.worker_notes = worker_notes
        if export_paths is not None:
            job.export_paths = export_paths
        if analysis is not None:
            job.analysis = analysis
        if blueprint is not None:
            job.blueprint = blueprint
        if final_generation_settings is not None:
            job.final_generation_settings = final_generation_settings
        if generation_diagnostics is not None:
            job.generation_diagnostics = generation_diagnostics
        if job_logs is not None:
            job.job_logs = job_logs
        if quality_report is not None:
            job.quality_report = quality_report
        job.updated_at = now_utc()
        self._job_ref(job.user_id, job.job_id).set(_job_to_document(job))
        return job

    def delete_raw(self, job_id: str) -> JobRecord:
        job = self._require(job_id)
        job.raw_audio_path = None
        job.updated_at = now_utc()
        self._job_ref(job.user_id, job.job_id).set(_job_to_document(job))
        return job

    def update_library(self, job_id: str, track_name: str | None = None, library_status: str | None = None) -> JobRecord:
        job = self._require(job_id)
        if track_name is not None:
            job.track_name = track_name
        if library_status is not None:
            job.library_status = library_status
        job.updated_at = now_utc()
        self._job_ref(job.user_id, job.job_id).set(_job_to_document(job))
        return job

    def mark_deleted(self, job_id: str) -> JobRecord:
        job = self.update_status(job_id, JobStatus.deleted, "deleted")
        job.deleted_at = job.updated_at
        self._job_ref(job.user_id, job.job_id).set(_job_to_document(job))
        return job

    def restore(self, job_id: str) -> JobRecord:
        job = self._require(job_id)
        job.status = JobStatus.ready if job.final_mp3_path else JobStatus.queued
        job.stage = "ready" if job.final_mp3_path else "queued"
        job.deleted_at = None
        job.updated_at = now_utc()
        self._job_ref(job.user_id, job.job_id).set(_job_to_document(job))
        return job

    def permanent_delete(self, job_id: str) -> JobRecord:
        job = self._require(job_id)
        self._job_ref(job.user_id, job.job_id).delete()
        return job

    def _require(self, job_id: str) -> JobRecord:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def _jobs_ref(self, user_id: str) -> Any:
        return self.client.collection("users").document(user_id).collection("jobs")

    def _job_ref(self, user_id: str, job_id: str) -> Any:
        return self._jobs_ref(user_id).document(job_id)


class FirestoreUserRepository:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or _firestore_client()

    def upsert(self, user_id: str, request: UserProfileRequest) -> UserProfile:
        email = request.email.strip().lower()
        email_ref = self.client.collection("profile_emails").document(email)
        existing_email = email_ref.get()
        if existing_email.exists:
            existing_user_id = existing_email.to_dict().get("user_id")
            if existing_user_id != user_id:
                raise DuplicateEmailError(email)

        timestamp = now_utc()
        profile_ref = self._profile_ref(user_id)
        existing_snapshot = profile_ref.get()
        existing = UserProfile.model_validate(existing_snapshot.to_dict()) if existing_snapshot.exists else None
        if existing and existing.email != email:
            self.client.collection("profile_emails").document(existing.email).delete()

        profile = UserProfile(
            user_id=user_id,
            name=request.name.strip(),
            email=email,
            bio=request.bio.strip() or "Private Skarly workspace",
            photo_url=request.photo_url,
            created_at=existing.created_at if existing else timestamp,
            updated_at=timestamp,
        )
        profile_ref.set(_profile_to_document(profile))
        email_ref.set({"user_id": user_id, "updated_at": timestamp})
        return profile

    def get(self, user_id: str) -> UserProfile | None:
        snapshot = self._profile_ref(user_id).get()
        if not snapshot.exists:
            return None
        return UserProfile.model_validate(snapshot.to_dict())

    def email_exists_for_other_user(self, email: str, user_id: str) -> bool:
        snapshot = self.client.collection("profile_emails").document(email.strip().lower()).get()
        return snapshot.exists and snapshot.to_dict().get("user_id") != user_id

    def clear(self) -> None:
        raise RuntimeError("Firestore repository clear is not supported")

    def list_recent(self, limit: int = 25) -> list[AdminUserSnapshot]:
        query = self.client.collection("users").order_by("updated_at", direction="DESCENDING").limit(limit)
        snapshots = query.stream()
        profiles = [UserProfile.model_validate(snapshot.to_dict()) for snapshot in snapshots]
        return [
            AdminUserSnapshot(user_id=profile.user_id, name=profile.name, email=profile.email, updated_at=profile.updated_at)
            for profile in profiles
        ]

    def _profile_ref(self, user_id: str) -> Any:
        return self.client.collection("users").document(user_id)


class FirestoreVoiceTakeRepository:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or _firestore_client()

    def create(self, user_id: str, request: VoiceTakeRequest) -> VoiceTakeRecord:
        timestamp = now_utc()
        take = VoiceTakeRecord(
            take_id=new_id("take"),
            user_id=user_id,
            title=request.title.strip(),
            duration=request.duration,
            raw_audio_path=request.raw_audio_path,
            content_type=request.content_type,
            size_bytes=request.size_bytes,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._take_ref(user_id, take.take_id).set(_voice_take_to_document(take))
        return take

    def list_for_user(self, user_id: str) -> list[VoiceTakeRecord]:
        query = self._takes_ref(user_id).order_by("created_at", direction="DESCENDING")
        return [take for take in (VoiceTakeRecord.model_validate(snapshot.to_dict()) for snapshot in query.stream()) if take.status != ItemStatus.deleted]

    def list_deleted_for_user(self, user_id: str) -> list[VoiceTakeRecord]:
        query = self._takes_ref(user_id).order_by("updated_at", direction="DESCENDING")
        return [take for take in (VoiceTakeRecord.model_validate(snapshot.to_dict()) for snapshot in query.stream()) if take.status == ItemStatus.deleted]

    def list_recent(self, limit: int = 25) -> list[VoiceTakeRecord]:
        takes = [VoiceTakeRecord.model_validate(snapshot.to_dict()) for snapshot in self.client.collection_group("voice_takes").stream()]
        return sorted(takes, key=lambda take: take.updated_at, reverse=True)[:limit]

    def list_deleted_recent(self, limit: int = 25) -> list[VoiceTakeRecord]:
        takes = [VoiceTakeRecord.model_validate(snapshot.to_dict()) for snapshot in self.client.collection_group("voice_takes").stream()]
        takes = [take for take in takes if take.status == ItemStatus.deleted]
        return sorted(takes, key=lambda take: take.deleted_at or take.updated_at, reverse=True)[:limit]

    def delete(self, user_id: str, take_id: str) -> VoiceTakeRecord:
        snapshot = self._take_ref(user_id, take_id).get()
        if not snapshot.exists:
            raise KeyError(take_id)
        take = VoiceTakeRecord.model_validate(snapshot.to_dict())
        take.status = ItemStatus.deleted
        take.deleted_at = now_utc()
        take.updated_at = take.deleted_at
        self._take_ref(user_id, take_id).set(_voice_take_to_document(take))
        return take

    def restore(self, user_id: str, take_id: str) -> VoiceTakeRecord:
        snapshot = self._take_ref(user_id, take_id).get()
        if not snapshot.exists:
            raise KeyError(take_id)
        take = VoiceTakeRecord.model_validate(snapshot.to_dict())
        take.status = ItemStatus.active
        take.deleted_at = None
        take.updated_at = now_utc()
        self._take_ref(user_id, take_id).set(_voice_take_to_document(take))
        return take

    def permanent_delete(self, user_id: str, take_id: str) -> VoiceTakeRecord:
        snapshot = self._take_ref(user_id, take_id).get()
        if not snapshot.exists:
            raise KeyError(take_id)
        take = VoiceTakeRecord.model_validate(snapshot.to_dict())
        self._take_ref(user_id, take_id).delete()
        return take

    def clear(self) -> None:
        raise RuntimeError("Firestore voice take repository clear is not supported")

    def _takes_ref(self, user_id: str) -> Any:
        return self.client.collection("users").document(user_id).collection("voice_takes")

    def _take_ref(self, user_id: str, take_id: str) -> Any:
        return self._takes_ref(user_id).document(take_id)


class FirestoreUsageRepository:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or _firestore_client()

    def get(self, key: str) -> int:
        snapshot = self._usage_ref(key).get()
        if not snapshot.exists:
            return 0
        return int(snapshot.to_dict().get("used", 0))

    def increment(self, key: str) -> int:
        timestamp = now_utc()
        current = self.get(key) + 1
        self._usage_ref(key).set({"used": current, "updated_at": timestamp})
        return current

    def clear(self) -> None:
        raise RuntimeError("Firestore usage repository clear is not supported")

    def _usage_ref(self, key: str) -> Any:
        return self.client.collection("usage").document(key)


def _json_dump_model(value: Any) -> str:
    return json.dumps(value.model_dump(mode="json"), separators=(",", ":"))


class SqliteStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or settings.sqlite_path
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,
                    data TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at DESC);

                CREATE TABLE IF NOT EXISTS profiles (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    data TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_email ON profiles(email);

                CREATE TABLE IF NOT EXISTS profile_emails (
                    email TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS voice_takes (
                    take_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,
                    data TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_voice_takes_user_created ON voice_takes(user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_voice_takes_updated ON voice_takes(updated_at DESC);

                CREATE TABLE IF NOT EXISTS usage (
                    key TEXT PRIMARY KEY,
                    used INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )


class SqliteJobRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def create(self, job: JobRecord) -> JobRecord:
        self._save(job)
        return job

    def get(self, job_id: str) -> JobRecord | None:
        with self.store.connect() as connection:
            row = connection.execute("SELECT data FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return JobRecord.model_validate_json(row["data"]) if row else None

    def list_for_user(self, user_id: str) -> list[JobRecord]:
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT data FROM jobs WHERE user_id = ? AND status != ? ORDER BY created_at DESC",
                (user_id, JobStatus.deleted.value),
            ).fetchall()
        return [JobRecord.model_validate_json(row["data"]) for row in rows]

    def list_deleted_for_user(self, user_id: str) -> list[JobRecord]:
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT data FROM jobs WHERE user_id = ? AND status = ? ORDER BY COALESCE(deleted_at, updated_at) DESC",
                (user_id, JobStatus.deleted.value),
            ).fetchall()
        return [JobRecord.model_validate_json(row["data"]) for row in rows]

    def list_recent(self, limit: int = 25) -> list[JobRecord]:
        with self.store.connect() as connection:
            rows = connection.execute("SELECT data FROM jobs ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [JobRecord.model_validate_json(row["data"]) for row in rows]

    def list_deleted_recent(self, limit: int = 25) -> list[JobRecord]:
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT data FROM jobs WHERE status = ? ORDER BY COALESCE(deleted_at, updated_at) DESC LIMIT ?",
                (JobStatus.deleted.value, limit),
            ).fetchall()
        return [JobRecord.model_validate_json(row["data"]) for row in rows]

    def clear(self) -> None:
        with self.store.connect() as connection:
            connection.execute("DELETE FROM jobs")

    def update_status(self, job_id: str, status: JobStatus, stage: str, error: str | None = None) -> JobRecord:
        job = self._require(job_id)
        job.status = status
        job.stage = stage
        job.error = error
        job.updated_at = now_utc()
        if status == JobStatus.ready:
            job.completed_at = job.updated_at
        self._save(job)
        return job

    def set_final_mp3(self, job_id: str, final_mp3_path: str) -> JobRecord:
        job = self._require(job_id)
        job.final_mp3_path = final_mp3_path
        job.updated_at = now_utc()
        self._save(job)
        return job

    def set_worker_artifacts(
        self,
        job_id: str,
        isolated_vocal_path: str | None = None,
        backing_audio_path: str | None = None,
        worker_notes: str | None = None,
        export_paths: dict[str, str] | None = None,
        analysis: SongAnalysis | None = None,
        blueprint: SongBlueprint | None = None,
        final_generation_settings: dict[str, Any] | None = None,
        generation_diagnostics: dict[str, Any] | None = None,
        job_logs: list[str] | None = None,
        quality_report: dict[str, Any] | None = None,
    ) -> JobRecord:
        job = self._require(job_id)
        job.isolated_vocal_path = isolated_vocal_path
        job.backing_audio_path = backing_audio_path
        job.worker_notes = worker_notes
        if export_paths is not None:
            job.export_paths = export_paths
        if analysis is not None:
            job.analysis = analysis
        if blueprint is not None:
            job.blueprint = blueprint
        if final_generation_settings is not None:
            job.final_generation_settings = final_generation_settings
        if generation_diagnostics is not None:
            job.generation_diagnostics = generation_diagnostics
        if job_logs is not None:
            job.job_logs = job_logs
        if quality_report is not None:
            job.quality_report = quality_report
        job.updated_at = now_utc()
        self._save(job)
        return job

    def delete_raw(self, job_id: str) -> JobRecord:
        job = self._require(job_id)
        job.raw_audio_path = None
        job.updated_at = now_utc()
        self._save(job)
        return job

    def update_library(self, job_id: str, track_name: str | None = None, library_status: str | None = None) -> JobRecord:
        job = self._require(job_id)
        if track_name is not None:
            job.track_name = track_name
        if library_status is not None:
            job.library_status = library_status
        job.updated_at = now_utc()
        self._save(job)
        return job

    def mark_deleted(self, job_id: str) -> JobRecord:
        job = self.update_status(job_id, JobStatus.deleted, "deleted")
        job.deleted_at = job.updated_at
        self._save(job)
        return job

    def restore(self, job_id: str) -> JobRecord:
        job = self._require(job_id)
        job.status = JobStatus.ready if job.final_mp3_path else JobStatus.queued
        job.stage = "ready" if job.final_mp3_path else "queued"
        job.deleted_at = None
        job.updated_at = now_utc()
        self._save(job)
        return job

    def permanent_delete(self, job_id: str) -> JobRecord:
        job = self._require(job_id)
        with self.store.connect() as connection:
            connection.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        return job

    def _save(self, job: JobRecord) -> None:
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs(job_id, user_id, status, created_at, updated_at, deleted_at, data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    deleted_at = excluded.deleted_at,
                    data = excluded.data
                """,
                (
                    job.job_id,
                    job.user_id,
                    job.status.value,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                    job.deleted_at.isoformat() if job.deleted_at else None,
                    _json_dump_model(job),
                ),
            )

    def _require(self, job_id: str) -> JobRecord:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job


class SqliteUserRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def upsert(self, user_id: str, request: UserProfileRequest) -> UserProfile:
        email = request.email.strip().lower()
        timestamp = now_utc()
        with self.store.connect() as connection:
            existing_email = connection.execute("SELECT user_id FROM profile_emails WHERE email = ?", (email,)).fetchone()
            if existing_email and existing_email["user_id"] != user_id:
                raise DuplicateEmailError(email)

            existing_row = connection.execute("SELECT data FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
            existing = UserProfile.model_validate_json(existing_row["data"]) if existing_row else None
            if existing and existing.email != email:
                connection.execute("DELETE FROM profile_emails WHERE email = ?", (existing.email,))

            profile = UserProfile(
                user_id=user_id,
                name=request.name.strip(),
                email=email,
                bio=request.bio.strip() or "Private Skarly workspace",
                photo_url=request.photo_url,
                created_at=existing.created_at if existing else timestamp,
                updated_at=timestamp,
            )
            connection.execute(
                """
                INSERT INTO profiles(user_id, email, updated_at, data)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    email = excluded.email,
                    updated_at = excluded.updated_at,
                    data = excluded.data
                """,
                (user_id, email, timestamp.isoformat(), _json_dump_model(profile)),
            )
            connection.execute(
                """
                INSERT INTO profile_emails(email, user_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    user_id = excluded.user_id,
                    updated_at = excluded.updated_at
                """,
                (email, user_id, timestamp.isoformat()),
            )
        return profile

    def get(self, user_id: str) -> UserProfile | None:
        with self.store.connect() as connection:
            row = connection.execute("SELECT data FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
        return UserProfile.model_validate_json(row["data"]) if row else None

    def email_exists_for_other_user(self, email: str, user_id: str) -> bool:
        with self.store.connect() as connection:
            row = connection.execute("SELECT user_id FROM profile_emails WHERE email = ?", (email.strip().lower(),)).fetchone()
        return bool(row and row["user_id"] != user_id)

    def clear(self) -> None:
        with self.store.connect() as connection:
            connection.execute("DELETE FROM profiles")
            connection.execute("DELETE FROM profile_emails")

    def list_recent(self, limit: int = 25) -> list[AdminUserSnapshot]:
        with self.store.connect() as connection:
            rows = connection.execute("SELECT data FROM profiles ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        profiles = [UserProfile.model_validate_json(row["data"]) for row in rows]
        return [
            AdminUserSnapshot(user_id=profile.user_id, name=profile.name, email=profile.email, updated_at=profile.updated_at)
            for profile in profiles
        ]


class SqliteVoiceTakeRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def create(self, user_id: str, request: VoiceTakeRequest) -> VoiceTakeRecord:
        timestamp = now_utc()
        take = VoiceTakeRecord(
            take_id=new_id("take"),
            user_id=user_id,
            title=request.title.strip(),
            duration=request.duration,
            raw_audio_path=request.raw_audio_path,
            content_type=request.content_type,
            size_bytes=request.size_bytes,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._save(take)
        return take

    def list_for_user(self, user_id: str) -> list[VoiceTakeRecord]:
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT data FROM voice_takes WHERE user_id = ? AND status != ? ORDER BY created_at DESC",
                (user_id, ItemStatus.deleted.value),
            ).fetchall()
        return [VoiceTakeRecord.model_validate_json(row["data"]) for row in rows]

    def list_deleted_for_user(self, user_id: str) -> list[VoiceTakeRecord]:
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT data FROM voice_takes WHERE user_id = ? AND status = ? ORDER BY COALESCE(deleted_at, updated_at) DESC",
                (user_id, ItemStatus.deleted.value),
            ).fetchall()
        return [VoiceTakeRecord.model_validate_json(row["data"]) for row in rows]

    def delete(self, user_id: str, take_id: str) -> VoiceTakeRecord:
        take = self._require(take_id)
        if take.user_id != user_id:
            raise PermissionError(take_id)
        take.status = ItemStatus.deleted
        take.deleted_at = now_utc()
        take.updated_at = take.deleted_at
        self._save(take)
        return take

    def restore(self, user_id: str, take_id: str) -> VoiceTakeRecord:
        take = self._require(take_id)
        if take.user_id != user_id:
            raise PermissionError(take_id)
        take.status = ItemStatus.active
        take.deleted_at = None
        take.updated_at = now_utc()
        self._save(take)
        return take

    def permanent_delete(self, user_id: str, take_id: str) -> VoiceTakeRecord:
        take = self._require(take_id)
        if take.user_id != user_id:
            raise PermissionError(take_id)
        with self.store.connect() as connection:
            connection.execute("DELETE FROM voice_takes WHERE take_id = ?", (take_id,))
        return take

    def clear(self) -> None:
        with self.store.connect() as connection:
            connection.execute("DELETE FROM voice_takes")

    def list_recent(self, limit: int = 25) -> list[VoiceTakeRecord]:
        with self.store.connect() as connection:
            rows = connection.execute("SELECT data FROM voice_takes ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [VoiceTakeRecord.model_validate_json(row["data"]) for row in rows]

    def list_deleted_recent(self, limit: int = 25) -> list[VoiceTakeRecord]:
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT data FROM voice_takes WHERE status = ? ORDER BY COALESCE(deleted_at, updated_at) DESC LIMIT ?",
                (ItemStatus.deleted.value, limit),
            ).fetchall()
        return [VoiceTakeRecord.model_validate_json(row["data"]) for row in rows]

    def _save(self, take: VoiceTakeRecord) -> None:
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT INTO voice_takes(take_id, user_id, status, created_at, updated_at, deleted_at, data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(take_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    deleted_at = excluded.deleted_at,
                    data = excluded.data
                """,
                (
                    take.take_id,
                    take.user_id,
                    take.status.value,
                    take.created_at.isoformat(),
                    take.updated_at.isoformat(),
                    take.deleted_at.isoformat() if take.deleted_at else None,
                    _json_dump_model(take),
                ),
            )

    def _require(self, take_id: str) -> VoiceTakeRecord:
        with self.store.connect() as connection:
            row = connection.execute("SELECT data FROM voice_takes WHERE take_id = ?", (take_id,)).fetchone()
        if not row:
            raise KeyError(take_id)
        return VoiceTakeRecord.model_validate_json(row["data"])


class SqliteUsageRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def get(self, key: str) -> int:
        with self.store.connect() as connection:
            row = connection.execute("SELECT used FROM usage WHERE key = ?", (key,)).fetchone()
        return int(row["used"]) if row else 0

    def increment(self, key: str) -> int:
        timestamp = now_utc()
        current = self.get(key) + 1
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT INTO usage(key, used, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    used = excluded.used,
                    updated_at = excluded.updated_at
                """,
                (key, current, timestamp.isoformat()),
            )
        return current

    def clear(self) -> None:
        with self.store.connect() as connection:
            connection.execute("DELETE FROM usage")


def _firestore_client() -> Any:
    if firestore is None:
        raise RuntimeError("firebase-admin Firestore support is not installed")

    from .auth import get_firebase_app

    return firestore.client(app=get_firebase_app())


def _build_repositories() -> tuple[Any, Any, Any, Any]:
    if settings.repository_backend == "memory":
        return InMemoryJobRepository(), InMemoryUserRepository(), InMemoryVoiceTakeRepository(), InMemoryUsageRepository()
    if settings.repository_backend == "sqlite":
        store = SqliteStore()
        return SqliteJobRepository(store), SqliteUserRepository(store), SqliteVoiceTakeRepository(store), SqliteUsageRepository(store)
    if settings.repository_backend == "firestore":
        client = _firestore_client()
        return FirestoreJobRepository(client), FirestoreUserRepository(client), FirestoreVoiceTakeRepository(client), FirestoreUsageRepository(client)
    raise ValueError(f"Unsupported SKARLY_REPOSITORY_BACKEND: {settings.repository_backend}")


jobs, users, voice_takes, usage = _build_repositories()
