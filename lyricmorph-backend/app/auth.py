from __future__ import annotations

from fastapi import Header, HTTPException

from .models import CreatorMode, UserContext


async def get_current_user(authorization: str | None = Header(default=None)) -> UserContext:
    """Resolve the local guest session used by every Skarly API request."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing guest session token")

    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith("guest:"):
        raise HTTPException(status_code=401, detail="Invalid guest session token")

    user_id = token.removeprefix("guest:").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid guest session token")

    return UserContext(user_id=user_id, creator_mode=CreatorMode.guest)


def test_user_context(token: str) -> UserContext:
    user_id = token.removeprefix("guest:").strip() if token.startswith("guest:") else token.strip()
    return UserContext(user_id=user_id or "test-session", creator_mode=CreatorMode.guest)
