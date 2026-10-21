"""Login second step: verify a TOTP code or passkey after the password.

Every route here is authorised by the short-lived mfa_pending cookie, never
by session cookies. Failure paths *return* a JSONResponse instead of raising:
get_db rolls back on exceptions, which would discard the failure counters.
"""
from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import MFA_PENDING_EXPIRED, MfaPendingUser
from app.models.user import User
from app.schemas.auth import PasskeyAssertionRequest, TotpCodeRequest
from app.schemas.user import UserResponse
from app.services.auth import clear_mfa_pending, issue_auth_cookies
from app.services.mfa import (
    mfa_backoff_remaining,
    record_mfa_failure,
    reset_mfa_counters,
    verify_totp,
)
from app.services.passkeys import PasskeyError, authentication_options, finish_authentication

router = APIRouter()

MAX_PENDING_FAILURES = 5


def _error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _wait_message(seconds: int) -> str:
    if seconds >= 60:
        minutes = -(-seconds // 60)
        unit = "minute" if minutes == 1 else "minutes"
        return f"Too many attempts, try again in {minutes} {unit}"
    unit = "second" if seconds == 1 else "seconds"
    return f"Too many attempts, try again in {seconds} {unit}"


def backoff_response(user: User) -> JSONResponse | None:
    """429 while the account is in its post-failure wait, else None."""
    remaining = mfa_backoff_remaining(user)
    if remaining is None:
        return None
    return _error(status.HTTP_429_TOO_MANY_REQUESTS, _wait_message(remaining))


async def failure_response(user: User, db: AsyncSession, detail: str) -> JSONResponse:
    """Count a failed second step; the 5th on one pending cookie invalidates it."""
    record_mfa_failure(user)
    user.mfa_pending_failures = (user.mfa_pending_failures or 0) + 1
    if user.mfa_pending_failures >= MAX_PENDING_FAILURES:
        user.mfa_pending_jti = None
        detail = MFA_PENDING_EXPIRED
    await db.flush()
    return _error(status.HTTP_400_BAD_REQUEST, detail)


async def complete_login(response: Response, user: User, db: AsyncSession) -> User:
    """Second step passed: drop the pending cookie and issue session cookies."""
    reset_mfa_counters(user)
    clear_mfa_pending(response, user)
    issue_auth_cookies(response, user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/totp", response_model=UserResponse)
async def verify_login_totp(
    data: TotpCodeRequest,
    response: Response,
    user: MfaPendingUser,
    db: AsyncSession = Depends(get_db),
):
    """Finish signing in with a code from the authenticator app."""
    if (blocked := backoff_response(user)) is not None:
        return blocked
    if not verify_totp(user, data.code):
        return await failure_response(user, db, "Incorrect code")
    return await complete_login(response, user, db)


@router.post("/passkey/options")
async def login_passkey_options(user: MfaPendingUser, db: AsyncSession = Depends(get_db)):
    """WebAuthn request options for the user's registered passkeys."""
    if not user.webauthn_credentials:
        return _error(status.HTTP_400_BAD_REQUEST, "No passkey is set up for this account")
    options = authentication_options(user)
    await db.flush()
    return options


@router.post("/passkey", response_model=UserResponse)
async def verify_login_passkey(
    data: PasskeyAssertionRequest,
    response: Response,
    user: MfaPendingUser,
    db: AsyncSession = Depends(get_db),
):
    """Finish signing in with a passkey assertion."""
    if (blocked := backoff_response(user)) is not None:
        return blocked
    try:
        finish_authentication(user, data.credential)
    except PasskeyError:
        return await failure_response(user, db, "Passkey verification failed")
    return await complete_login(response, user, db)
