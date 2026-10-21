"""Two-factor authentication: TOTP secrets, code checks and attempt backoff.

TOTP follows RFC 6238 (SHA-1, 6 digits, 30 s step) and accepts one step of
clock drift either way. A step at or below the last accepted one is rejected,
so a code can't be replayed.
"""
import base64
import hashlib
from datetime import datetime, timedelta, timezone

import pyotp
from cryptography.fernet import Fernet

from app.config import settings
from app.models.user import User

ISSUER = "MegooBug"
STEP_SECONDS = 30
BACKOFF_FREE_FAILURES = 5
BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 900


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _fernet() -> Fernet:
    digest = hashlib.sha256(b"megoobug-mfa:" + settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def normalize_code(code: str) -> str | None:
    """Strip spaces and dashes; return the code only if it is exactly 6 digits."""
    cleaned = code.replace(" ", "").replace("-", "")
    if len(cleaned) == 6 and cleaned.isdigit():
        return cleaned
    return None


def _matching_step(secret: str, code: str, now: datetime) -> int | None:
    """The time step (within ±1 of now) whose code equals `code`, if any."""
    totp = pyotp.TOTP(secret)
    current = int(now.timestamp()) // STEP_SECONDS
    for step in (current - 1, current, current + 1):
        if totp.at(step * STEP_SECONDS) == code:
            return step
    return None


# ── TOTP enrolment ──


def begin_totp_setup(user: User) -> tuple[str, str]:
    """Generate a pending secret; returns (base32 secret, otpauth:// URI)."""
    secret = pyotp.random_base32()
    user.totp_pending_secret = encrypt_secret(secret)
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)
    return secret, uri


def confirm_totp_setup(user: User, code: str, now: datetime | None = None) -> bool:
    """Activate the pending secret if `code` matches it."""
    if user.totp_pending_secret is None:
        return False
    normalized = normalize_code(code)
    if normalized is None:
        return False
    secret = decrypt_secret(user.totp_pending_secret)
    step = _matching_step(secret, normalized, _now(now))
    if step is None:
        return False
    user.totp_secret = user.totp_pending_secret
    user.totp_pending_secret = None
    user.totp_enabled_at = _now(now)
    user.totp_last_step = step
    return True


def verify_totp(user: User, code: str, now: datetime | None = None) -> bool:
    """Check a login code against the active secret, with replay protection."""
    if user.totp_secret is None or user.totp_enabled_at is None:
        return False
    normalized = normalize_code(code)
    if normalized is None:
        return False
    step = _matching_step(decrypt_secret(user.totp_secret), normalized, _now(now))
    if step is None:
        return False
    if user.totp_last_step is not None and step <= user.totp_last_step:
        return False
    user.totp_last_step = step
    return True


def remove_totp(user: User) -> None:
    user.totp_secret = None
    user.totp_pending_secret = None
    user.totp_enabled_at = None
    user.totp_last_step = None


# ── Attempt limits ──


def mfa_backoff_remaining(user: User, now: datetime | None = None) -> int | None:
    """Seconds until the next second-step attempt is allowed, or None."""
    if user.mfa_retry_after is None:
        return None
    remaining = (user.mfa_retry_after - _now(now)).total_seconds()
    if remaining <= 0:
        return None
    return int(-(-remaining // 1))  # ceil


def record_mfa_failure(user: User, now: datetime | None = None) -> None:
    """Count a failed second step; from the 5th in a row, impose a growing wait."""
    user.mfa_failed_streak = (user.mfa_failed_streak or 0) + 1
    extra = user.mfa_failed_streak - BACKOFF_FREE_FAILURES
    if extra >= 0:
        wait = min(BACKOFF_BASE_SECONDS * 2**extra, BACKOFF_MAX_SECONDS)
        user.mfa_retry_after = _now(now) + timedelta(seconds=wait)


def reset_mfa_counters(user: User) -> None:
    user.mfa_failed_streak = 0
    user.mfa_retry_after = None
    user.mfa_pending_failures = 0
    user.mfa_pending_jti = None


def clear_all_mfa(user: User) -> None:
    """Remove every enrolled method (admin / server reset). Keeps mfa_required."""
    remove_totp(user)
    user.webauthn_credentials.clear()
    user.webauthn_challenge = None
    user.webauthn_challenge_expires_at = None
    reset_mfa_counters(user)
