from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from fastapi import Header, HTTPException

from .config import settings
from .models import CreatorMode, UserContext

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth
    from firebase_admin import credentials
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    firebase_admin = None
    firebase_auth = None
    credentials = None


async def get_current_user(authorization: str | None = Header(default=None)) -> UserContext:
    """Verify Firebase ID tokens, with a temporary guest-session token for guest mode."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Firebase ID token")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Invalid Firebase ID token")

    if settings.app_env == "test":
        return test_user_context(token)

    if settings.auth_mode not in {"firebase_with_guest", "firebase_only"}:
        raise HTTPException(status_code=500, detail="Invalid AUTH_MODE")

    firebase_error: Exception | None = None
    try:
        return verify_firebase_token(token)
    except Exception as exc:
        firebase_error = exc

    if settings.auth_mode == "firebase_only":
        raise HTTPException(status_code=401, detail="Invalid Firebase ID token") from firebase_error

    return guest_user_context(token, firebase_error)


def guest_user_context(token: str, firebase_error: Exception) -> UserContext:
    if token.startswith("guest:"):
        return UserContext(user_id=token.removeprefix("guest:"), creator_mode=CreatorMode.guest)
    raise HTTPException(status_code=401, detail="Invalid Firebase ID token") from firebase_error


def test_user_context(token: str) -> UserContext:
    if token.startswith("guest:"):
        return UserContext(user_id=token.removeprefix("guest:"), creator_mode=CreatorMode.guest)
    return UserContext(user_id=token, creator_mode=CreatorMode.saved, email=token if "@" in token else None)


def verify_firebase_token(token: str) -> UserContext:
    if firebase_admin is None or firebase_auth is None:
        raise RuntimeError("firebase-admin is not installed")

    decoded = firebase_auth.verify_id_token(token, app=get_firebase_app())
    user_id = decoded.get("uid") or decoded.get("sub")
    if not user_id:
        raise ValueError("Firebase token did not include uid")

    return UserContext(
        user_id=user_id,
        creator_mode=CreatorMode.saved,
        email=decoded.get("email"),
    )


@lru_cache(maxsize=1)
def get_firebase_app() -> Any:
    if firebase_admin is None or credentials is None:
        raise RuntimeError("firebase-admin is not installed")

    if firebase_admin._apps:
        return firebase_admin.get_app()

    options = {"projectId": settings.firebase_project_id} if settings.firebase_project_id else None
    if settings.firebase_service_account_json:
        service_account = json.loads(settings.firebase_service_account_json)
        credential = credentials.Certificate(service_account)
    elif settings.firebase_credentials_path:
        credential = credentials.Certificate(settings.firebase_credentials_path)
    else:
        credential = credentials.ApplicationDefault()

    return firebase_admin.initialize_app(credential, options)
