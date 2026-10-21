"""Profile 2FA management (/users/me/2fa/*)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pyotp

from app.models.webauthn_credential import WebAuthnCredential
from app.services import passkeys
from app.services.mfa import begin_totp_setup, confirm_totp_setup, decrypt_secret, verify_totp
from tests.conftest import cookie_header

PASSWORD = "correct-horse-1"
BASE = "/api/v1/users/me/2fa"


async def _session(client, user) -> dict:
    """Session cookie header; log in before enrolling so no second step is needed."""
    resp = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    access = resp.cookies["access_token"]
    client.cookies.clear()
    return cookie_header(access)


def _enroll_totp(user) -> str:
    secret, _ = begin_totp_setup(user)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert confirm_totp_setup(user, pyotp.TOTP(secret).at(past), now=past)
    return secret


def _add_passkey(user, credential_id="Y2lk", name="Key"):
    cred = WebAuthnCredential(credential_id=credential_id, public_key=b"pk", name=name, sign_count=0)
    user.webauthn_credentials.append(cred)
    return cred


async def test_status_defaults(user_client, make_user):
    user = await make_user()
    headers = await _session(user_client, user)
    resp = await user_client.get(BASE, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert {k: body[k] for k in ("enabled", "required", "methods", "passkeys")} == {
        "enabled": False, "required": False, "methods": [], "passkeys": []
    }


async def test_begin_totp_requires_password(user_client, make_user):
    user = await make_user()
    headers = await _session(user_client, user)
    bad = await user_client.post(f"{BASE}/totp", json={"password": "wrong-pass"}, headers=headers)
    assert bad.status_code == 400
    assert bad.json()["detail"] == "Password is incorrect"
    ok = await user_client.post(f"{BASE}/totp", json={"password": PASSWORD}, headers=headers)
    assert ok.status_code == 200
    assert ok.json()["secret"]


async def test_confirm_totp_enables(user_client, make_user):
    user = await make_user()
    headers = await _session(user_client, user)
    secret = (await user_client.post(f"{BASE}/totp", json={"password": PASSWORD}, headers=headers)).json()["secret"]

    resp = await user_client.post(
        f"{BASE}/totp/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["methods"] == ["totp"]
    assert resp.json()["enabled"] is True


async def test_confirm_totp_wrong_code(user_client, make_user):
    user = await make_user()
    headers = await _session(user_client, user)
    await user_client.post(f"{BASE}/totp", json={"password": PASSWORD}, headers=headers)
    resp = await user_client.post(f"{BASE}/totp/confirm", json={"code": "000000"}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Incorrect code"


async def test_replace_totp_keeps_old_until_confirmed(user_client, make_user, db):
    user = await make_user()
    headers = await _session(user_client, user)
    old = _enroll_totp(user)
    await db.flush()

    new = (await user_client.post(f"{BASE}/totp", json={"password": PASSWORD}, headers=headers)).json()["secret"]
    assert verify_totp(user, pyotp.TOTP(old).now()) is True

    resp = await user_client.post(
        f"{BASE}/totp/confirm", json={"code": pyotp.TOTP(new).now()}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert decrypt_secret(user.totp_secret) == new


async def test_remove_totp_requires_password(user_client, make_user, db):
    user = await make_user()
    headers = await _session(user_client, user)
    _enroll_totp(user)
    await db.flush()
    resp = await user_client.post(f"{BASE}/totp/remove", json={"password": "wrong-pass"}, headers=headers)
    assert resp.status_code == 400
    assert user.totp_enabled_at is not None


async def test_remove_totp(user_client, make_user, db):
    user = await make_user()
    headers = await _session(user_client, user)
    _enroll_totp(user)
    await db.flush()
    resp = await user_client.post(f"{BASE}/totp/remove", json={"password": PASSWORD}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["methods"] == []


async def test_add_passkey(user_client, make_user, monkeypatch):
    user = await make_user()
    headers = await _session(user_client, user)
    monkeypatch.setattr(
        passkeys,
        "verify_registration_response",
        lambda **_: SimpleNamespace(credential_id=b"cid", credential_public_key=b"pk", sign_count=0),
    )
    bad = await user_client.post(f"{BASE}/passkeys/options", json={"password": "wrong-pass"}, headers=headers)
    assert bad.status_code == 400
    opts = await user_client.post(f"{BASE}/passkeys/options", json={"password": PASSWORD}, headers=headers)
    assert opts.status_code == 200

    resp = await user_client.post(
        f"{BASE}/passkeys", json={"credential": {"id": "Y2lk"}, "name": "Laptop"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["methods"] == ["passkey"]
    assert resp.json()["passkeys"][0]["name"] == "Laptop"


async def test_rename_passkey_no_password(user_client, make_user, db):
    user = await make_user()
    other = await make_user()
    headers = await _session(user_client, user)
    mine = _add_passkey(user)
    theirs = _add_passkey(other, credential_id="b3RoZXI")
    await db.flush()

    resp = await user_client.patch(f"{BASE}/passkeys/{mine.id}", json={"name": "Work laptop"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["passkeys"][0]["name"] == "Work laptop"

    resp = await user_client.patch(f"{BASE}/passkeys/{theirs.id}", json={"name": "x"}, headers=headers)
    assert resp.status_code == 404


async def test_remove_passkey_requires_password(user_client, make_user, db):
    user = await make_user()
    headers = await _session(user_client, user)
    cred = _add_passkey(user)
    await db.flush()
    bad = await user_client.post(f"{BASE}/passkeys/{cred.id}/remove", json={"password": "wrong-pass"}, headers=headers)
    assert bad.status_code == 400
    ok = await user_client.post(f"{BASE}/passkeys/{cred.id}/remove", json={"password": PASSWORD}, headers=headers)
    assert ok.status_code == 200
    assert ok.json()["passkeys"] == []


async def test_cannot_remove_last_method_when_required(user_client, make_user, db):
    user = await make_user()
    headers = await _session(user_client, user)
    _enroll_totp(user)
    user.mfa_required = True
    await db.flush()

    resp = await user_client.post(f"{BASE}/totp/remove", json={"password": PASSWORD}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "2FA is required for your account, so you must keep at least one method."


async def test_can_remove_one_of_two_when_required(user_client, make_user, db):
    user = await make_user()
    headers = await _session(user_client, user)
    _enroll_totp(user)
    cred = _add_passkey(user)
    user.mfa_required = True
    await db.flush()

    resp = await user_client.post(f"{BASE}/passkeys/{cred.id}/remove", json={"password": PASSWORD}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["methods"] == ["totp"]
