"""Auth endpoints — Firebase-backed."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from .. import database as db
from ..models import SyncUserRequest, UserOut
from ..security import current_user, rate_limit

log = logging.getLogger("not.routes.auth")

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
    dependencies=[Depends(rate_limit)],
)


def _to_out(user: dict) -> UserOut:
    return UserOut(
        uid=user["uid"],
        email=user.get("email"),
        display_name=user.get("display_name"),
        photo_url=user.get("photo_url"),
        is_admin=bool(user.get("is_admin", 0)),
    )


@router.post("/sync", response_model=UserOut)
async def sync_user(
    payload: SyncUserRequest,
    user: dict = Depends(current_user),
) -> UserOut:
    """Called by the frontend right after Firebase login.

    The `current_user` dependency already upserts the user (with name/picture
    from Firebase claims). This endpoint lets the frontend override the
    display name / photo if it wants to.
    """
    if payload.display_name or payload.photo_url:
        db.upsert_user(
            uid=user["uid"],
            email=user.get("email"),
            display_name=payload.display_name or user.get("display_name"),
            photo_url=payload.photo_url or user.get("photo_url"),
        )
        user = db.get_user(user["uid"])
    return _to_out(user)


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(current_user)) -> UserOut:
    return _to_out(user)