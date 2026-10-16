"""Firebase token verification for FastAPI.

We do NOT manage passwords or issue our own JWTs. The browser signs the user
in with Firebase (Google or Email/Password). The browser sends the Firebase
ID token to us in the Authorization header, and we verify it here.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import firebase_admin
from firebase_admin import auth as fb_auth
from firebase_admin import credentials as fb_credentials

from .config import BASE_DIR, get_settings

log = logging.getLogger("not.auth")

_initialized = False


def _resolve_credentials_path(raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = BASE_DIR / p
    return p


def init_firebase() -> None:
    """Initialize the Firebase Admin SDK. Idempotent."""
    global _initialized
    if _initialized:
        return

    settings = get_settings()
    raw = settings.firebase_credentials_path

    if not raw:
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS is not set. "
            "Add it to .env (path to your Firebase service-account JSON)."
        )

    path = _resolve_credentials_path(raw)
    if not path.exists():
        raise RuntimeError(f"Firebase credentials file not found: {path}")

    try:
        cred = fb_credentials.Certificate(str(path))
        firebase_admin.initialize_app(cred)
        _initialized = True
        log.info("Firebase Admin SDK initialized (%s)", path.name)
    except Exception as e:
        log.error("Firebase init failed: %s", e)
        raise


def verify_firebase_token(id_token: str) -> Optional[dict]:
    """Verify a Firebase ID token. Returns decoded claims, or None on failure.

    Decoded claims include: uid, email, email_verified, name, picture, etc.
    """
    try:
        init_firebase()
        return fb_auth.verify_id_token(id_token, check_revoked=False)
    except fb_auth.ExpiredIdTokenError:
        log.info("Firebase token expired")
        return None
    except fb_auth.RevokedIdTokenError:
        log.info("Firebase token revoked")
        return None
    except fb_auth.InvalidIdTokenError:
        log.info("Firebase token invalid")
        return None
    except Exception as e:
        log.warning("Firebase token verification failed: %s", e)
        return None