"""TOTP, secret encryption and attempt backoff (app/services/mfa.py)."""
from datetime import datetime, timedelta, timezone

import pyotp

from app.models.webauthn_credential import WebAuthnCredential
from app.services.mfa import (
    begin_totp_setup,
    confirm_totp_setup,
    decrypt_secret,
    encrypt_secret,
    mfa_backoff_remaining,
    record_mfa_failure,
    reset_mfa_counters,
    verify_totp,
)

NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)


async def _enrolled(make_user, at: datetime = NOW - timedelta(minutes=5)):
    """A user with TOTP enabled at `at`, so steps after it are still unused."""
    user = await make_user()
    secret, _ = begin_totp_setup(user)
    assert confirm_totp_setup(user, pyotp.TOTP(secret).at(at), now=at)
    return user, secret


def test_encrypt_roundtrip():
    token = encrypt_secret("ABC")
    assert token != "ABC"
    assert decrypt_secret(token) == "ABC"


async def test_confirm_totp_setup_enables(make_user):
    user = await make_user()
    secret, uri = begin_totp_setup(user)
    assert uri.startswith("otpauth://totp/MegooBug:")
    assert "issuer=MegooBug" in uri

    assert confirm_totp_setup(user, pyotp.TOTP(secret).at(NOW), now=NOW) is True
    assert user.totp_enabled_at is not None
    assert user.totp_pending_secret is None
    assert decrypt_secret(user.totp_secret) == secret


async def test_confirm_totp_setup_wrong_code_keeps_disabled(make_user):
    user = await make_user()
    begin_totp_setup(user)

    assert confirm_totp_setup(user, "000000", now=NOW) is False
    assert user.totp_enabled_at is None
    assert user.totp_secret is None


async def test_verify_totp_window(make_user):
    for offset in (-30, 0, 30):
        user, secret = await _enrolled(make_user)
        code = pyotp.TOTP(secret).at(NOW + timedelta(seconds=offset))
        assert verify_totp(user, code, now=NOW) is True, offset

    user, secret = await _enrolled(make_user)
    assert verify_totp(user, pyotp.TOTP(secret).at(NOW - timedelta(seconds=90)), now=NOW) is False


async def test_verify_totp_rejects_replay(make_user):
    user, secret = await _enrolled(make_user)
    code = pyotp.TOTP(secret).at(NOW)
    assert verify_totp(user, code, now=NOW) is True
    assert verify_totp(user, code, now=NOW) is False


async def test_verify_totp_accepts_spaced_code(make_user):
    user, secret = await _enrolled(make_user)
    code = pyotp.TOTP(secret).at(NOW)
    assert verify_totp(user, f"{code[:3]} {code[3:]}", now=NOW) is True

    user, secret = await _enrolled(make_user)
    code = pyotp.TOTP(secret).at(NOW)
    assert verify_totp(user, f"{code[:3]}-{code[3:]}", now=NOW) is True


async def test_mfa_methods_order(make_user):
    fresh = await make_user()
    assert fresh.mfa_methods == []
    assert fresh.mfa_enrolled is False

    user, _ = await _enrolled(make_user)
    user.webauthn_credentials.append(
        WebAuthnCredential(credential_id="Y2lk", public_key=b"pk", name="Key", sign_count=0)
    )
    assert user.mfa_methods == ["passkey", "totp"]
    assert user.mfa_enrolled is True


async def test_backoff_progression(make_user):
    user = await make_user()
    for _ in range(4):
        record_mfa_failure(user, now=NOW)
    assert mfa_backoff_remaining(user, now=NOW) is None

    record_mfa_failure(user, now=NOW)  # 5th
    assert mfa_backoff_remaining(user, now=NOW) == 30
    record_mfa_failure(user, now=NOW)  # 6th
    assert mfa_backoff_remaining(user, now=NOW) == 60
    for _ in range(4):  # 10th
        record_mfa_failure(user, now=NOW)
    assert mfa_backoff_remaining(user, now=NOW) == 900

    reset_mfa_counters(user)
    assert mfa_backoff_remaining(user, now=NOW) is None
