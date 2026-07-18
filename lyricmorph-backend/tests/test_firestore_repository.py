from __future__ import annotations

from app.models import CreatorMode, Genre, JobRecord, JobStatus, SourceType, UserProfileRequest, VoiceTakeRequest, now_utc
from app.repository import DuplicateEmailError, FirestoreJobRepository, FirestoreUsageRepository, FirestoreUserRepository, FirestoreVoiceTakeRepository


class FakeSnapshot:
    def __init__(self, data=None) -> None:
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class FakeDocument:
    def __init__(self, client: "FakeFirestoreClient", path: str) -> None:
        self.client = client
        self.path = path

    def collection(self, name: str):
        return FakeCollection(self.client, f"{self.path}/{name}")

    def get(self):
        data = self.client.store.get(self.path)
        return FakeSnapshot(dict(data) if data is not None else None)

    def set(self, data):
        self.client.store[self.path] = dict(data)

    def delete(self):
        self.client.store.pop(self.path, None)


class FakeCollection:
    def __init__(self, client: "FakeFirestoreClient", path: str) -> None:
        self.client = client
        self.path = path

    def document(self, document_id: str):
        return FakeDocument(self.client, f"{self.path}/{document_id}")

    def order_by(self, field: str, direction: str = "ASCENDING"):
        documents = [
            dict(data)
            for path, data in self.client.store.items()
            if path.startswith(f"{self.path}/") and "/" not in path.removeprefix(f"{self.path}/")
        ]
        reverse = direction == "DESCENDING"
        documents.sort(key=lambda item: item[field], reverse=reverse)
        return FakeQuery(documents)


class FakeCollectionGroup:
    def __init__(self, client: "FakeFirestoreClient", collection_name: str) -> None:
        self.client = client
        self.collection_name = collection_name
        self.field = ""
        self.value = None
        self.limit_count = None

    def where(self, field: str, operator: str, value):
        assert operator == "=="
        self.field = field
        self.value = value
        return self

    def limit(self, count: int):
        self.limit_count = count
        return self

    def stream(self):
        matches = []
        needle = f"/{self.collection_name}/"
        for path, data in self.client.store.items():
            if needle in path and data.get(self.field) == self.value:
                matches.append(FakeSnapshot(dict(data)))
        if self.limit_count is not None:
            matches = matches[: self.limit_count]
        return matches


class FakeQuery:
    def __init__(self, documents) -> None:
        self.documents = documents

    def stream(self):
        return [FakeSnapshot(dict(document)) for document in self.documents]


class FakeFirestoreClient:
    def __init__(self) -> None:
        self.store = {}

    def collection(self, name: str):
        return FakeCollection(self, name)

    def collection_group(self, name: str):
        return FakeCollectionGroup(self, name)


def make_job(job_id: str, user_id: str, status: JobStatus = JobStatus.queued) -> JobRecord:
    timestamp = now_utc()
    return JobRecord(
        job_id=job_id,
        user_id=user_id,
        creator_mode=CreatorMode.saved,
        genre=Genre.lofi,
        track_name=f"Track {job_id}",
        source_type=SourceType.local_upload,
        raw_audio_path=f"users/{user_id}/raw/upload/file.mp3",
        status=status,
        stage=status.value,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_firestore_profile_save_load_and_duplicate_email():
    client = FakeFirestoreClient()
    users = FirestoreUserRepository(client)

    profile = users.upsert("uid_1", UserProfileRequest(name="Yesh", email="YESH@example.com", bio=""))

    assert profile.email == "yesh@example.com"
    assert profile.bio == "Private Skarly workspace"
    assert users.get("uid_1").name == "Yesh"

    try:
        users.upsert("uid_2", UserProfileRequest(name="Other", email="yesh@example.com", bio="Other"))
    except DuplicateEmailError:
        pass
    else:
        raise AssertionError("Duplicate email should be rejected")


def test_firestore_jobs_history_and_deleted_filter():
    client = FakeFirestoreClient()
    jobs = FirestoreJobRepository(client)
    first = jobs.create(make_job("job_1", "uid_1"))
    second = jobs.create(make_job("job_2", "uid_1"))
    jobs.create(make_job("job_other", "uid_2"))

    jobs.mark_deleted(second.job_id)

    history = jobs.list_for_user("uid_1")
    assert [job.job_id for job in history] == [first.job_id]
    assert jobs.list_for_user("uid_2")[0].job_id == "job_other"


def test_firestore_job_mutations_and_retry_failure_state():
    client = FakeFirestoreClient()
    jobs = FirestoreJobRepository(client)
    jobs.create(make_job("job_1", "uid_1"))

    ready = jobs.update_status("job_1", JobStatus.ready, "ready")
    assert ready.completed_at is not None

    final = jobs.set_final_mp3("job_1", "users/uid_1/final/job_1/Track.mp3")
    assert final.final_mp3_path.endswith("Track.mp3")

    renamed = jobs.update_library("job_1", "Final Name", "Saved")
    assert renamed.track_name == "Final Name"
    assert renamed.library_status == "Saved"

    raw_deleted = jobs.delete_raw("job_1")
    assert raw_deleted.raw_audio_path is None
    assert jobs.get("job_1").raw_audio_path is None


def test_firestore_voice_take_save_list_delete():
    client = FakeFirestoreClient()
    takes = FirestoreVoiceTakeRepository(client)

    take = takes.create(
        "uid_1",
        VoiceTakeRequest(
            title="Voice take 1",
            duration=9,
            raw_audio_path="users/uid_1/raw/upload/voice.webm",
            content_type="audio/webm",
            size_bytes=9000,
        ),
    )
    takes.create(
        "uid_2",
        VoiceTakeRequest(
            title="Other take",
            duration=5,
            raw_audio_path="users/uid_2/raw/upload/voice.webm",
            content_type="audio/webm",
        ),
    )

    assert [item.take_id for item in takes.list_for_user("uid_1")] == [take.take_id]
    deleted = takes.delete("uid_1", take.take_id)
    assert deleted.title == "Voice take 1"
    assert takes.list_for_user("uid_1") == []


def test_firestore_usage_counter():
    client = FakeFirestoreClient()
    usage = FirestoreUsageRepository(client)

    assert usage.get("lyria_2026_06") == 0
    assert usage.increment("lyria_2026_06") == 1
    assert usage.increment("lyria_2026_06") == 2
    assert usage.get("lyria_2026_06") == 2
