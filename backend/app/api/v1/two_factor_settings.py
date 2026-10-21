"""Managing your own 2FA methods (/users/me/2fa/*).

Adding, replacing or removing a method asks for the current password, like
changing the password does: a stolen session alone must not be enough to
strip 2FA or plant an attacker's passkey. Renaming a passkey doesn't.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser
from app.models.user import User
from app.schemas.auth import PasskeyRegistrationRequest, TotpCodeRequest, TotpSetupResponse
from app.schemas.user import PasskeyInfo, PasskeyRename, PasswordConfirm, TwoFactorStatus
from app.services.auth import verify_password
from app.services.mfa import begin_totp_setup, confirm_totp_setup, remove_totp
from app.services.passkeys import PasskeyError, finish_registration, registration_options

router = APIRouter()

KEEP_ONE_METHOD = "2FA is required for your account, so you must keep at least one method."


def two_factor_status(user: User) -> TwoFactorStatus:
    return TwoFactorStatus(
        enabled=user.mfa_enrolled,
        required=user.mfa_required,
        methods=user.mfa_methods,
        totp_enabled_at=user.totp_enabled_at,
        passkeys=[PasskeyInfo.model_validate(c) for c in user.webauthn_credentials],
    )


def _check_password(user: User, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password is incorrect")


def _check_keeps_a_method(user: User, removing: str, remaining_passkeys: int) -> None:
    """Refuse a removal that would leave a required user with no method."""
    if not user.mfa_required:
        return
    has_totp = user.totp_enabled_at is not None and removing != "totp"
    if not has_totp and remaining_passkeys == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=KEEP_ONE_METHOD)


def _own_passkey(user: User, passkey_id: uuid.UUID):
    cred = next((c for c in user.webauthn_credentials if c.id == passkey_id), None)
    if cred is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found")
    return cred


@router.get("/me/2fa", response_model=TwoFactorStatus)
async def get_two_factor_status(current_user: CurrentUser):
    return two_factor_status(current_user)


@router.post("/me/2fa/totp", response_model=TotpSetupResponse)
async def begin_totp(
    data: PasswordConfirm, current_user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    """Start setting up (or replacing) the authenticator app.

    The current secret stays active until the new one is confirmed.
    """
    _check_password(current_user, data.password)
    secret, uri = begin_totp_setup(current_user)
    await db.flush()
    return TotpSetupResponse(secret=secret, otpauth_uri=uri)


@router.post("/me/2fa/totp/confirm", response_model=TwoFactorStatus)
async def confirm_totp(
    data: TotpCodeRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    if not confirm_totp_setup(current_user, data.code):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "Incorrect code"})
    await db.flush()
    return two_factor_status(current_user)


@router.post("/me/2fa/totp/remove", response_model=TwoFactorStatus)
async def delete_totp(
    data: PasswordConfirm, current_user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    _check_password(current_user, data.password)
    _check_keeps_a_method(current_user, "totp", len(current_user.webauthn_credentials))
    remove_totp(current_user)
    await db.flush()
    return two_factor_status(current_user)


@router.post("/me/2fa/passkeys/options")
async def passkey_options(
    data: PasswordConfirm, current_user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    _check_password(current_user, data.password)
    options = registration_options(current_user)
    await db.flush()
    return options


@router.post("/me/2fa/passkeys", response_model=TwoFactorStatus)
async def add_passkey(
    data: PasskeyRegistrationRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    """Finish registration; the challenge from the password-checked options call is the proof."""
    try:
        finish_registration(current_user, data.credential, data.name)
    except PasskeyError:
        await db.flush()
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "Passkey setup failed"})
    await db.flush()
    return two_factor_status(current_user)


@router.patch("/me/2fa/passkeys/{passkey_id}", response_model=TwoFactorStatus)
async def rename_passkey(
    passkey_id: uuid.UUID,
    data: PasskeyRename,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _own_passkey(current_user, passkey_id).name = data.name
    await db.flush()
    return two_factor_status(current_user)


@router.post("/me/2fa/passkeys/{passkey_id}/remove", response_model=TwoFactorStatus)
async def remove_passkey(
    passkey_id: uuid.UUID,
    data: PasswordConfirm,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    cred = _own_passkey(current_user, passkey_id)
    _check_password(current_user, data.password)
    _check_keeps_a_method(current_user, "passkey", len(current_user.webauthn_credentials) - 1)
    current_user.webauthn_credentials.remove(cred)
    await db.flush()
    return two_factor_status(current_user)
