from app.models import CreatorMode, SignedUploadRequest, SourceType, UserContext
from app.storage import LocalFileStorageService, MockStorageService, storage_owner_id, user_storage_prefix


def test_mock_storage_uses_user_owned_raw_path():
    response = MockStorageService().create_signed_upload(
        "guest/demo-session",
        SignedUploadRequest(
            filename="voice/take.mp3",
            content_type="audio/mpeg",
            size_bytes=1000,
            source_type=SourceType.local_upload,
        ),
    )

    assert response.raw_audio_path.startswith("users/guest/demo-session/raw/upload_")
    assert response.raw_audio_path.endswith("/voice_take.mp3")
    assert "/test-storage/upload/" in response.upload_url


def test_storage_byte_operations_round_trip():
    mock = MockStorageService()
    mock.upload_bytes("users/guest/demo/final/job/demo.mp3", b"mp3-bytes", "audio/mpeg")
    assert mock.download_bytes("users/guest/demo/final/job/demo.mp3") == b"mp3-bytes"
    mock.delete_object("users/guest/demo/final/job/demo.mp3")


def test_local_file_storage_persists_objects(tmp_path):
    service = LocalFileStorageService(tmp_path)
    object_path = "users/guest/demo/raw/upload_1/take.wav"

    service.upload_bytes(object_path, b"wav-bytes", "audio/wav")

    assert service.object_exists(object_path)
    assert service.download_bytes(object_path) == b"wav-bytes"
    assert service.list_objects("users/guest/demo/raw/") == [object_path]


def test_storage_owner_paths_are_guest_scoped():
    guest = UserContext(user_id="demo-session", creator_mode=CreatorMode.guest)

    assert storage_owner_id(guest) == "guest/demo-session"
    assert user_storage_prefix(guest) == "users/guest/demo-session"
