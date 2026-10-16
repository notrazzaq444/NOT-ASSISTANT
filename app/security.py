"""Rate limiting + Firebase auth dependency."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque, Optional

from fastapi import Depends, Header, HTTPException, Request, status

from . import database as db
from .auth import verify_firebase_token
from .config import get_settings

_buckets: dict[str, Deque[float]] = defaultdict(deque)
_lock = Lock()


def rate_limit(request: Request) -> None:
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = settings.rate_limit_window
    limit = settings.rate_limit_requests

    with _lock:
        bucket = _buckets[client_ip]
        while bucket and bucket[0] < now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = int(window - (now - bucket[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down.",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)


async def current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """Extract the logged-in user from a Firebase ID token (Bearer).

    Returns the local DB user row (dict). Creates the row on first sight.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    claims = verify_firebase_token(token)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    uid = claims.get("uid") or claims.get("user_id") or claims.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Token missing uid.")

    user = db.upsert_user(
        uid=str(uid),
        email=claims.get("email"),
        display_name=claims.get("name"),
        photo_url=claims.get("picture"),
    )
    return user