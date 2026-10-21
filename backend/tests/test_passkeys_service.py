"""Passkey (WebAuthn) service — the library's verify calls are faked at the boundary."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from app.config import settings
from app.models.webauthn_credential import WebAuthnCredential
from app.services import passkeys
from app.services.passkeys import (
    PasskeyError,
    authentication_options,
    finish_authentication,
    finish_registration,
    registration_options,
)

NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)


def _fake_registration(monkeypatch, **kwargs):
    result = SimpleNamespace(credential_id=b"cid", credential_public_key=b"pk", sign_count=0)
    monkeypatch.setattr(passkeys, "verify_registration_response", lambda **_: result)


async def _with_passkey(make_user, credential_id="Y2lk"):
    user = await make_user()
    user.webauthn_credentials.append(
        WebAuthnCredential(credential_id=credential_id, public_key=b"pk", name="Key", sign_count=1)
    )
    return user


async def test_registration_options_stores_challenge(make_user):
    user = await make_user()
    opts = registration_options(user, now=NOW)

    assert opts["rp"]["id"] == urlparse(settings.APP_URL).hostname
    assert opts["challenge"] == user.webauthn_challenge
    assert user.webauthn_challenge_expires_at == NOW + timedelta(minutes=5)


async def test_finish_registration_saves_credential(make_user, monkeypatch):
    user = await make_user()
    registration_options(user, now=NOW)
    _fake_registration(monkeypatch)

    cred = finish_registration(
        user, {"id": "Y2lk", "response": {"transports": ["internal"]}}, "  MacBook  ", now=NOW
    )
    assert cred.credential_id == "Y2lk"
    assert cred.name == "MacBook"
    assert cred.transports == ["internal"]
    assert user.webauthn_credentials == [cred]
    assert user.webauthn_challenge is None


async def test_finish_registration_expired_challenge_raises(make_user, monkeypatch):
    user = await make_user()
    registration_options(user, now=NOW)
    _fake_registration(monkeypatch)

    with pytest.raises(PasskeyError):
        finish_registration(user, {"id": "Y2lk"}, "Key", now=NOW + timedelta(minutes=6))
    assert user.webauthn_credentials == []


async def test_finish_authentication_updates_sign_count(make_user, monkeypatch):
    user = await _with_passkey(make_user)
    authentication_options(user, now=NOW)
    monkeypatch.setattr(
        passkeys, "verify_authentication_response", lambda **_: SimpleNamespace(new_sign_count=5)
    )

    cred = finish_authentication(user, {"id": "Y2lk"}, now=NOW)
    assert cred.sign_count == 5
    assert cred.last_used_at == NOW
    assert user.webauthn_challenge is None


async def test_finish_authentication_rejects_foreign_credential(make_user, monkeypatch):
    await _with_passkey(make_user, credential_id="Zm9yZWlnbg")
    user_a = await make_user()
    authentication_options(user_a, now=NOW)
    monkeypatch.setattr(
        passkeys, "verify_authentication_response", lambda **_: SimpleNamespace(new_sign_count=5)
    )

    with pytest.raises(PasskeyError):
        finish_authentication(user_a, {"id": "Zm9yZWlnbg"}, now=NOW)


async def test_finish_authentication_verify_error_raises(make_user, monkeypatch):
    user = await _with_passkey(make_user)
    authentication_options(user, now=NOW)

    def _boom(**_):
        raise ValueError("bad signature")

    monkeypatch.setattr(passkeys, "verify_authentication_response", _boom)
    with pytest.raises(PasskeyError):
        finish_authentication(user, {"id": "Y2lk"}, now=NOW)
