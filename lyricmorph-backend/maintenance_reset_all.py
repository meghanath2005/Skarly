from __future__ import annotations

import argparse
from typing import Iterable

from firebase_admin import auth, firestore

from app.auth import get_firebase_app
from app.config import settings
from app.storage import build_gcs_client


BATCH_SIZE = 100


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def delete_collection(client, collection_path: str) -> int:
    deleted = 0
    collection = client.collection(collection_path)
    while True:
        snapshots = list(collection.limit(BATCH_SIZE).stream())
        if not snapshots:
            return deleted
        batch = client.batch()
        for snapshot in snapshots:
            batch.delete(snapshot.reference)
            deleted += 1
        batch.commit()


def delete_user_documents(client) -> int:
    deleted = 0
    for user_snapshot in client.collection("users").stream():
        user_ref = user_snapshot.reference
        for subcollection in user_ref.collections():
            while True:
                snapshots = list(subcollection.limit(BATCH_SIZE).stream())
                if not snapshots:
                    break
                batch = client.batch()
                for snapshot in snapshots:
                    batch.delete(snapshot.reference)
                    deleted += 1
                batch.commit()
        user_ref.delete()
        deleted += 1
    return deleted


def delete_auth_users() -> int:
    deleted = 0
    page = auth.list_users(app=get_firebase_app())
    while page:
        user_ids = [user.uid for user in page.users]
        for user_chunk in chunked(user_ids, 1000):
            if not user_chunk:
                continue
            result = auth.delete_users(user_chunk, app=get_firebase_app())
            deleted += result.success_count
            if result.failure_count:
                for error in result.errors:
                    print(f"Auth delete failed for index {error.index}: {error.reason}")
        page = page.get_next_page()
    return deleted


def delete_bucket_users_prefix() -> int:
    if settings.storage_backend != "gcs":
        print("Skipping Cloud Storage wipe because SKARLY_STORAGE_BACKEND is not gcs.")
        return 0

    client = build_gcs_client()
    blobs = list(client.list_blobs(settings.storage_bucket, prefix="users/"))
    for blob_chunk in chunked(blobs, BATCH_SIZE):
        bucket = client.bucket(settings.storage_bucket)
        bucket.delete_blobs(blob_chunk)
    return len(blobs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dangerously wipe all Skarly user test data.")
    parser.add_argument("--yes-delete-everything", action="store_true", help="Required safety confirmation.")
    args = parser.parse_args()

    if not args.yes_delete_everything:
        raise SystemExit("Refusing to run. Pass --yes-delete-everything to wipe Auth, Firestore, and Storage.")

    get_firebase_app()
    firestore_client = firestore.client(app=get_firebase_app())

    storage_deleted = delete_bucket_users_prefix()
    profile_email_docs_deleted = delete_collection(firestore_client, "profile_emails")
    user_docs_deleted = delete_user_documents(firestore_client)
    auth_users_deleted = delete_auth_users()

    print("Skarly reset complete.")
    print(f"Cloud Storage objects deleted under users/: {storage_deleted}")
    print(f"Firestore profile_emails docs deleted: {profile_email_docs_deleted}")
    print(f"Firestore user/profile/job/voice docs deleted: {user_docs_deleted}")
    print(f"Firebase Auth users deleted: {auth_users_deleted}")


if __name__ == "__main__":
    main()
