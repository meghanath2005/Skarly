from app.models import CreatorMode, SignedUploadRequest, SourceType, UserContext
from app.storage import GcsStorageService, LocalFileStorageService, MockStorageService, storage_owner_id, user_storage_prefix


class FakeBlob:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = []
        self.data = b""
        self.content_type = ""

    def generate_signed_url(self, **kwargs):
        self.calls.append(kwargs)
        return f"https://signed.example/{self.name}?method={kwargs['method']}"

    def download_as_bytes(self):
        return self.data

    def upload_from_string(self, data: bytes, content_type: str):
        self.data = data
        self.content_type = content_type

    def delete(self):
        self.data = b""

    def exists(self):
        return bool(self.data)


class FakeBucket:
    def __init__(self) -> None:
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, name: str) -> FakeBlob:
        if name not in self.blobs:
            self.blobs[name] = FakeBlob(name)
        return self.blobs[name]


class FakeClient:
    def __init__(self, credentials=None) -> None:
        self.bucket_name = ""
        self.bucket_obj = FakeBucket()
        self._credentials = credentials

    def bucket(self, name: str) -> FakeBucket:
        self.bucket_name = name
        return self.bucket_obj


class FakeCloudRunCredentials:
    service_account_email = "293181449428-compute@developer.gserviceaccount.com"
    token = "ya29.test-token"
    valid = True


def test_mock_storage_uses_user_owned_raw_path():
    response = MockStorageService().create_signed_upload(
        "user_test",
        SignedUploadRequest(
            filename="voice/take.mp3",
            content_type="audio/mpeg",
            size_bytes=1000,
            source_type=SourceType.local_upload,
        ),
    )

    assert response.raw_audio_path.startswith("users/user_test/raw/upload_")
    assert response.raw_audio_path.endswith("/voice_take.mp3")
    assert "/test-storage/upload/" in response.upload_url


def test_gcs_storage_generates_signed_upload_and_download_urls():
    client = FakeClient()
    service = GcsStorageService(client=client, bucket_name="lyricmorph-user")

    upload = service.create_signed_upload(
        "firebase_uid",
        SignedUploadRequest(
            filename="take.m4a",
            content_type="audio/m4a",
            size_bytes=2048,
            source_type=SourceType.local_upload,
        ),
    )
    raw_playback_url = service.signed_download_url("users/firebase_uid/raw/upload_1/take.m4a")
    download_url = service.signed_download_url("users/firebase_uid/final/job_1/final.mp3", "Ocean Demo - Rock")

    assert client.bucket_name == "lyricmorph-user"
    assert upload.raw_audio_path.startswith("users/firebase_uid/raw/upload_")
    assert upload.upload_url.startswith("https://signed.example/")
    assert "method=PUT" in upload.upload_url
    assert "method=GET" in raw_playback_url
    assert "method=GET" in download_url
    raw_blob = client.bucket_obj.blobs["users/firebase_uid/raw/upload_1/take.m4a"]
    assert "response_disposition" not in raw_blob.calls[-1]
    download_blob = client.bucket_obj.blobs["users/firebase_uid/final/job_1/final.mp3"]
    assert download_blob.calls[-1]["response_disposition"] == 'attachment; filename="Ocean Demo - Rock.mp3"'
    assert download_blob.calls[-1]["response_type"] == "audio/mpeg"


def test_gcs_storage_uses_cloud_run_iam_signing_options_without_private_key():
    client = FakeClient(credentials=FakeCloudRunCredentials())
    service = GcsStorageService(client=client, bucket_name="lyricmorph-user")

    service.signed_download_url("users/firebase_uid/raw/upload_1/take.webm")

    blob = client.bucket_obj.blobs["users/firebase_uid/raw/upload_1/take.webm"]
    assert blob.calls[-1]["service_account_email"] == "293181449428-compute@developer.gserviceaccount.com"
    assert blob.calls[-1]["access_token"] == "ya29.test-token"


def test_storage_byte_operations_round_trip():
    mock = MockStorageService()
    mock.upload_bytes("users/user/final/job/demo.mp3", b"mp3-bytes", "audio/mpeg")
    assert mock.download_bytes("users/user/final/job/demo.mp3") == b"mp3-bytes"
    mock.delete_object("users/user/final/job/demo.mp3")

    client = FakeClient()
    service = GcsStorageService(client=client, bucket_name="lyricmorph-user")
    service.upload_bytes("users/user/final/job/demo.mp3", b"real-mp3", "audio/mpeg")
    assert service.download_bytes("users/user/final/job/demo.mp3") == b"real-mp3"
    assert service.object_exists("users/user/final/job/demo.mp3")


def test_local_file_storage_persists_objects(tmp_path):
    service = LocalFileStorageService(tmp_path)
    object_path = "users/user/raw/upload_1/take.wav"

    service.upload_bytes(object_path, b"wav-bytes", "audio/wav")

    assert service.object_exists(object_path)
    assert service.download_bytes(object_path) == b"wav-bytes"
    assert service.list_objects("users/user/raw/") == [object_path]


def test_storage_owner_paths_group_guest_and_name_saved_accounts():
    guest = UserContext(user_id="demo-session", creator_mode=CreatorMode.guest)
    saved = UserContext(user_id="g9IFzWsRAWM2CB1N3", creator_mode=CreatorMode.saved, email="artist@example.com")

    assert storage_owner_id(guest) == "guest/demo-session"
    assert user_storage_prefix(saved) == "users/saved/artist--g9ifzwsr"

