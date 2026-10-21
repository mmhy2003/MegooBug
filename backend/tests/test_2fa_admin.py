"""Admin require/reset of a user's 2FA, and the server-side reset command."""
from datetime import datetime, timedelta, timezone

import pyotp

from app.models.user import UserRole
from app.models.webauthn_credential import WebAuthnCredential
from app.scripts.reset_2fa import reset_2fa
from app.services.mfa import begin_totp_setup, confirm_totp_setup
from tests.conftest import cookie_header

PASSWORD = "correct-horse-1"


async def _session(client, user) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    access = resp.cookies["access_token"]
    client.cookies.clear()
    return access


def _enroll(user):
    secret, _ = begin_totp_setup(user)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert confirm_totp_setup(user, pyotp.TOTP(secret).at(past), now=past)
    user.webauthn_credentials.append(
        WebAuthnCredential(credential_id="Y2lk", public_key=b"pk", name="Key", sign_count=0)
    )


async def _admin(client, make_user):
    admin = await make_user(role=UserRole.ADMIN)
    return admin, cookie_header(await _session(client, admin))


async def test_require_is_admin_only(user_client, make_user):
    dev = await make_user()
    target = await make_user()
    headers = cookie_header(await _session(user_client, dev))
    resp = await user_client.patch(
        f"/api/v1/users/{target.id}/2fa-required", json={"required": True}, headers=headers
    )
    assert resp.status_code == 403


async def test_require_self_400(user_client, make_user):
    admin, headers = await _admin(user_client, make_user)
    resp = await user_client.patch(
        f"/api/v1/users/{admin.id}/2fa-required", json={"required": True}, headers=headers
    )
    assert resp.status_code == 400


async def test_require_unenrolled_bumps_token_version(user_client, make_user):
    _, headers = await _admin(user_client, make_user)
    target = await make_user()
    target_access = await _session(user_client, target)

    resp = await user_client.patch(
        f"/api/v1/users/{target.id}/2fa-required", json={"required": True}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["mfa_required"] is True
    me = await user_client.get("/api/v1/users/me", headers=cookie_header(target_access))
    assert me.status_code == 401


async def test_require_enrolled_keeps_sessions(user_client, make_user, db):
    _, headers = await _admin(user_client, make_user)
    target = await make_user()
    target_access = await _session(user_client, target)
    _enroll(target)
    await db.flush()

    await user_client.patch(f"/api/v1/users/{target.id}/2fa-required", json={"required": True}, headers=headers)
    assert target.token_version == 0
    me = await user_client.get("/api/v1/users/me", headers=cookie_header(target_access))
    assert me.status_code == 200


async def test_unrequire_then_login_is_plain(user_client, make_user):
    _, headers = await _admin(user_client, make_user)
    target = await make_user()
    for required in (True, False):
        await user_client.patch(
            f"/api/v1/users/{target.id}/2fa-required", json={"required": required}, headers=headers
        )

    resp = await user_client.post("/api/v1/auth/login", json={"email": target.email, "password": PASSWORD})
    assert resp.status_code == 200
    assert resp.json()["id"] == str(target.id)
    assert "access_token" in resp.cookies
    user_client.cookies.clear()


async def test_reset_clears_methods_and_bumps_version(user_client, make_user, db):
    _, headers = await _admin(user_client, make_user)
    target = await make_user()
    _enroll(target)
    target.mfa_failed_streak = 3
    await db.flush()

    resp = await user_client.post(f"/api/v1/users/{target.id}/2fa/reset", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["mfa_methods"] == []
    assert target.webauthn_credentials == []
    assert target.totp_secret is None
    assert target.token_version == 1
    assert target.mfa_failed_streak == 0


async def test_reset_self_400(user_client, make_user):
    admin, headers = await _admin(user_client, make_user)
    resp = await user_client.post(f"/api/v1/users/{admin.id}/2fa/reset", headers=headers)
    assert resp.status_code == 400


async def test_reset_keeps_required_flag(user_client, make_user, db):
    _, headers = await _admin(user_client, make_user)
    target = await make_user()
    _enroll(target)
    target.mfa_required = True
    await db.flush()

    resp = await user_client.post(f"/api/v1/users/{target.id}/2fa/reset", headers=headers)
    assert resp.json()["mfa_required"] is True


async def test_cli_reset_2fa(make_user, db):
    user = await make_user()
    _enroll(user)
    await db.flush()

    assert await reset_2fa(db, user.email) is True
    assert user.mfa_methods == []
    assert user.token_version == 1
    assert await reset_2fa(db, "nobody@example.com") is False
