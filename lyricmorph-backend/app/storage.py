from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

import google.auth
from google.auth.transport.requests import Request
from google.cloud import storage as gcs_storage
from google.oauth2 import service_account

from .config import settings
from .models import CreatorMode, SignedUploadRequest, SignedUploadResponse, UserContext, new_id


SIGNED_URL_TTL_SECONDS = 900


def safe_object_name(value: str) -> str:
    cleaned = value.replace("\\", "_").replace("/", "_").strip()
    return cleaned or "audio-file"


def safe_storage_segment(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:48] or "creator"


def safe_download_filename(value: str, fallback_extension: str = ".mp3") -> str:
    cleaned = safe_object_name(value).replace('"', "'")
    known_extensions = (".mp3", ".wav", ".mid", ".midi", ".txt", ".json", ".zip")
    return cleaned if cleaned.lower().endswith(known_extensions) else f"{cleaned}{fallback_extension}"


def content_type_from_path(object_path: str) -> str:
    lower = object_path.lower()
    if lower.endswith(".wav"):
        return "audio/wav"
    if lower.endswith((".mid", ".midi")):
        return "audio/midi"
    if lower.endswith(".zip"):
        return "application/zip"
    if lower.endswith(".txt"):
        return "text/plain"
    if lower.endswith(".json"):
        return "application/json"
    if lower.endswith(".m4a"):
        return "audio/m4a"
    if lower.endswith(".webm"):
        return "audio/webm"
    return "audio/mpeg"


def storage_owner_id(user: UserContext) -> str:
    if user.creator_mode == CreatorMode.guest:
        return f"guest/{safe_storage_segment(user.user_id or 'demo-session')}"

    readable = (user.email or user.user_id).split("@", 1)[0]
    return f"saved/{safe_storage_segment(readable)}--{safe_storage_segment(user.user_id)[:8]}"


def user_storage_prefix(user: UserContext) -> str:
    return f"users/{storage_owner_id(user)}"


def legacy_user_storage_prefix(user: UserContext) -> str:
    return f"users/{user.user_id}"


def allowed_user_storage_prefixes(user: UserContext) -> list[str]:
    prefixes = [user_storage_prefix(user), legacy_user_storage_prefix(user)]
    unique: list[str] = []
    for prefix in prefixes:
        if prefix not in unique:
            unique.append(prefix)
    return unique


def user_raw_prefixes(user: UserContext) -> list[str]:
    return [f"{prefix}/raw/" for prefix in allowed_user_storage_prefixes(user)]


def user_final_prefixes(user: UserContext) -> list[str]:
    return [f"{prefix}/final/" for prefix in allowed_user_storage_prefixes(user)]


def raw_audio_path(storage_owner: str, upload_id: str, filename: str) -> str:
    return f"users/{storage_owner}/raw/{upload_id}/{safe_object_name(filename)}"


class MockStorageService:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def create_signed_upload(self, storage_owner: str, request: SignedUploadRequest) -> SignedUploadResponse:
        upload_id = new_id("upload")
        path = raw_audio_path(storage_owner, upload_id, request.filename)
        return SignedUploadResponse(
            upload_id=upload_id,
            upload_url=f"{settings.local_base_url}/test-storage/upload/{quote(path, safe='')}",
            raw_audio_path=path,
            expires_in_seconds=SIGNED_URL_TTL_SECONDS,
        )

    def signed_download_url(self, final_mp3_path: str, download_name: str | None = None) -> str:
        return f"{settings.local_base_url}/test-storage/download/{quote(final_mp3_path, safe='')}"

    def download_bytes(self, object_path: str) -> bytes:
        if object_path not in self.objects:
            raise FileNotFoundError(object_path)
        return self.objects[object_path][0]

    def upload_bytes(self, object_path: str, data: bytes, content_type: str = "audio/mpeg") -> None:
        self.objects[object_path] = (data, content_type)

    def delete_object(self, object_path: str) -> None:
        self.objects.pop(object_path, None)

    def object_exists(self, object_path: str) -> bool:
        return object_path in self.objects

    def list_objects(self, prefix: str) -> list[str]:
        return sorted(path for path in self.objects if path.startswith(prefix))


class LocalFileStorageService:
    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir or settings.local_storage_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def create_signed_upload(self, storage_owner: str, request: SignedUploadRequest) -> SignedUploadResponse:
        upload_id = new_id("upload")
        path = raw_audio_path(storage_owner, upload_id, request.filename)
        return SignedUploadResponse(
            upload_id=upload_id,
            upload_url=f"{settings.local_base_url}/local-storage/upload/{quote(path, safe='')}",
            raw_audio_path=path,
            expires_in_seconds=SIGNED_URL_TTL_SECONDS,
        )

    def signed_download_url(self, final_mp3_path: str, download_name: str | None = None) -> str:
        url = f"{settings.local_base_url}/local-storage/download/{quote(final_mp3_path, safe='')}"
        if download_name:
            url = f"{url}?download_name={quote(safe_download_filename(download_name, Path(final_mp3_path).suffix or '.mp3'), safe='')}"
        return url

    def download_bytes(self, object_path: str) -> bytes:
        path = self._object_path(object_path)
        if not path.exists():
            raise FileNotFoundError(object_path)
        return path.read_bytes()

    def upload_bytes(self, object_path: str, data: bytes, content_type: str = "audio/mpeg") -> None:
        path = self._object_path(object_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete_object(self, object_path: str) -> None:
        path = self._object_path(object_path)
        if path.exists():
            path.unlink()

    def object_exists(self, object_path: str) -> bool:
        return self._object_path(object_path).exists()

    def list_objects(self, prefix: str) -> list[str]:
        if not self.root_dir.exists():
            return []
        normalized_prefix = prefix.replace("\\", "/").lstrip("/")
        objects: list[str] = []
        for path in self.root_dir.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(self.root_dir).as_posix()
            if relative.startswith(normalized_prefix):
                objects.append(relative)
        return sorted(objects)

    def _object_path(self, object_path: str) -> Path:
        normalized = object_path.replace("\\", "/").lstrip("/")
        candidate = (self.root_dir / normalized).resolve()
        if not candidate.is_relative_to(self.root_dir):
            raise ValueError("Storage path escapes local storage root")
        return candidate


class GcsStorageService:
    def __init__(self, client: gcs_storage.Client | None = None, bucket_name: str | None = None) -> None:
        self.client = client or build_gcs_client()
        self.bucket_name = bucket_name or settings.storage_bucket

    def create_signed_upload(self, storage_owner: str, request: SignedUploadRequest) -> SignedUploadResponse:
        upload_id = new_id("upload")
        path = raw_audio_path(storage_owner, upload_id, request.filename)
        blob = self.client.bucket(self.bucket_name).blob(path)
        upload_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=SIGNED_URL_TTL_SECONDS),
            method="PUT",
            content_type=request.content_type,
            **self._cloud_run_signing_options(),
        )
        return SignedUploadResponse(
            upload_id=upload_id,
            upload_url=upload_url,
            raw_audio_path=path,
            expires_in_seconds=SIGNED_URL_TTL_SECONDS,
        )

    def signed_download_url(self, final_mp3_path: str, download_name: str | None = None) -> str:
        blob = self.client.bucket(self.bucket_name).blob(final_mp3_path)
        options = {
            "version": "v4",
            "expiration": timedelta(seconds=SIGNED_URL_TTL_SECONDS),
            "method": "GET",
        }
        if download_name:
            filename = safe_download_filename(download_name, Path(final_mp3_path).suffix or ".mp3")
            options["response_disposition"] = f'attachment; filename="{filename}"'
            options["response_type"] = content_type_from_path(final_mp3_path)
        options.update(self._cloud_run_signing_options())
        return blob.generate_signed_url(**options)

    def _cloud_run_signing_options(self) -> dict[str, str]:
        credentials = getattr(self.client, "_credentials", None)
        if not credentials or hasattr(credentials, "sign_bytes"):
            return {}

        signing_credentials = credentials
        if settings.app_env == "production":
            signing_credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])

        service_account_email = settings.gcs_signing_service_account or getattr(
            signing_credentials, "service_account_email", None
        ) or getattr(
            credentials, "service_account_email", None
        )
        if not service_account_email:
            return {}

        if not getattr(signing_credentials, "valid", False):
            signing_credentials.refresh(Request())

        access_token = getattr(signing_credentials, "token", None)
        if not access_token:
            return {}

        return {
            "service_account_email": service_account_email,
            "access_token": access_token,
        }

    def download_bytes(self, object_path: str) -> bytes:
        blob = self.client.bucket(self.bucket_name).blob(object_path)
        return blob.download_as_bytes()

    def upload_bytes(self, object_path: str, data: bytes, content_type: str = "audio/mpeg") -> None:
        blob = self.client.bucket(self.bucket_name).blob(object_path)
        blob.upload_from_string(data, content_type=content_type)

    def delete_object(self, object_path: str) -> None:
        blob = self.client.bucket(self.bucket_name).blob(object_path)
        blob.delete()

    def object_exists(self, object_path: str) -> bool:
        blob = self.client.bucket(self.bucket_name).blob(object_path)
        return blob.exists()

    def list_objects(self, prefix: str) -> list[str]:
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
        return sorted(blob.name for blob in blobs if not blob.name.endswith("/"))


def build_gcs_client() -> gcs_storage.Client:
    if settings.firebase_service_account_json:
        info = json.loads(settings.firebase_service_account_json)
        credentials = service_account.Credentials.from_service_account_info(info)
        return gcs_storage.Client(project=settings.firebase_project_id, credentials=credentials)

    if settings.firebase_credentials_path:
        return gcs_storage.Client.from_service_account_json(
            settings.firebase_credentials_path,
            project=settings.firebase_project_id,
        )

    return gcs_storage.Client(project=settings.firebase_project_id)


def build_storage_service():
    if settings.storage_backend == "mock":
        return MockStorageService()
    if settings.storage_backend in {"local", "filesystem"}:
        return LocalFileStorageService()
    if settings.storage_backend == "gcs":
        return GcsStorageService()
    raise ValueError(f"Unsupported SKARLY_STORAGE_BACKEND: {settings.storage_backend}")


storage = build_storage_service()
