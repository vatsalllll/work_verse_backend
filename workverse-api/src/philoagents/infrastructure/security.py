"""Security primitives: password hashing and JWT tokens.

Password hashing uses the standard library ``hashlib.pbkdf2_hmac`` so there is
no extra dependency to install.  Tokens use PyJWT (already a transitive dep).
"""

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from loguru import logger

from philoagents.config import settings

_PBKDF2_ALGORITHM = "sha256"
_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Return a salted PBKDF2 hash, encoded as ``pbkdf2_sha256$iters$salt$hash``."""
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        _PBKDF2_ALGORITHM, password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"pbkdf2_{_PBKDF2_ALGORITHM}${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time verification of a password against a stored hash."""
    if not stored:
        return False
    try:
        algo_label, iterations_s, salt_hex, hash_hex = stored.split("$")
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False

    algorithm = algo_label.replace("pbkdf2_", "")
    candidate = hashlib.pbkdf2_hmac(
        algorithm, password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(candidate, expected)


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

def create_access_token(user_id: str, email: str, name: str) -> str:
    """Create a signed JWT carrying the user's identity."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRY_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT.  Returns the payload, or None if invalid."""
    try:
        return jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError as e:
        logger.debug(f"Rejected token: {e}")
        return None


# ---------------------------------------------------------------------------
# OAuth CSRF state tokens (short-lived, signed)
# ---------------------------------------------------------------------------

def create_state_token(provider: str) -> str:
    """A short-lived signed token used as the OAuth ``state`` parameter."""
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": "oauth_state",
        "provider": provider,
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_state_token(token: str, provider: str) -> bool:
    """Validate a state token returned by the provider."""
    payload = decode_access_token(token)
    return bool(
        payload
        and payload.get("purpose") == "oauth_state"
        and payload.get("provider") == provider
    )
