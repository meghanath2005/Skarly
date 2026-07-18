from __future__ import annotations

import json
import sqlite3
from typing import Any

from .config import settings
from .models import (
    ItemStatus,
    JobRecord,
    JobStatus,
    SongAnalysis,
    SongBlueprint,
    VoiceTakeRecord,
    VoiceTakeRequest,
    new_id,
    now_utc,
)

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


def _voice_take_to_document(take: VoiceTakeRecord) -> dict[str, Any]:
    data = take.model_dump(mode="json")
    data["status"] = take.status.value
    return data


def _json_dump_model(model: Any) -> str:
    return model.model_dump_json()


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



def _build_repositories() -> tuple[Any, Any, Any]:
    if settings.repository_backend == "memory":
        return InMemoryJobRepository(), InMemoryVoiceTakeRepository(), InMemoryUsageRepository()
    if settings.repository_backend == "sqlite":
        store = SqliteStore()
        return SqliteJobRepository(store), SqliteVoiceTakeRepository(store), SqliteUsageRepository(store)
    raise ValueError(f"Unsupported SKARLY_REPOSITORY_BACKEND: {settings.repository_backend}")


jobs, voice_takes, usage = _build_repositories()
