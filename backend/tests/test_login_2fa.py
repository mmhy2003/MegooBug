"""Password → second step login (POST /auth/login, /auth/2fa/*)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pyotp

from app.models.webauthn_credential import WebAuthnCredential
from app.services import passkeys
from app.services.mfa import begin_totp_setup, confirm_totp_setup
from tests.conftest import cookie_header

PASSWORD = "correct-horse-1"


async def _totp_user(make_user, db, **kwargs):
    """A user with TOTP enabled five minutes ago (so current codes are unused)."""
    user = await make_user(**kwargs)
    secret, _ = begin_totp_setup(user)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert confirm_totp_setup(user, pyotp.TOTP(secret).at(past), now=past)
    await db.flush()
    return user, secret


async def _login(client, user) -> tuple[dict, dict]:
    resp = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    cookies = dict(resp.cookies)
    client.cookies.clear()
    return resp.json(), cookies


def _pending(cookies: dict) -> dict:
    return {"Cookie": f"mfa_pending={cookies['mfa_pending']}"}


async def _totp(client, cookies: dict, code: str, extra_cookie: str = ""):
    headers = _pending(cookies)
    if extra_cookie:
        headers["Cookie"] += f"; {extra_cookie}"
    resp = await client.post("/api/v1/auth/2fa/totp", json={"code": code}, headers=headers)
    out = dict(resp.cookies)
    client.cookies.clear()
    return resp, out


async def test_login_without_2fa_unchanged(user_client, make_user):
    user = await make_user()
    body, cookies = await _login(user_client, user)
    assert body["id"] == str(user.id)
    assert "access_token" in cookies


async def test_login_enrolled_returns_challenge_without_session(user_client, make_user, db):
    user, _ = await _totp_user(make_user, db)
    body, cookies = await _login(user_client, user)
    assert body == {"mfa_required": "verify", "methods": ["totp"], "email": user.email}
    assert "access_token" not in cookies
    assert "mfa_pending" in cookies


async def test_pending_cookie_cannot_access_me(user_client, make_user, db):
    user, _ = await _totp_user(make_user, db)
    _, cookies = await _login(user_client, user)
    resp = await user_client.get("/api/v1/users/me", headers=_pending(cookies))
    assert resp.status_code == 401


async def test_totp_verify_completes_login(user_client, make_user, db):
    user, secret = await _totp_user(make_user, db)
    _, cookies = await _login(user_client, user)

    resp, out = await _totp(user_client, cookies, pyotp.TOTP(secret).now())
    assert resp.status_code == 200, resp.text
    assert "access_token" in out and "refresh_token" in out
    me = await user_client.get("/api/v1/users/me", headers=cookie_header(out["access_token"]))
    assert me.status_code == 200


async def test_totp_wrong_code_400_and_counts(user_client, make_user, db):
    user, _ = await _totp_user(make_user, db)
    _, cookies = await _login(user_client, user)

    resp, _ = await _totp(user_client, cookies, "000000")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Incorrect code"
    await db.refresh(user)
    assert user.mfa_pending_failures == 1
    assert user.mfa_failed_streak == 1


async def test_totp_five_failures_invalidate_pending(user_client, make_user, db):
    user, secret = await _totp_user(make_user, db)
    _, cookies = await _login(user_client, user)

    for _ in range(4):
        await _totp(user_client, cookies, "000000")
    resp, _ = await _totp(user_client, cookies, "000000")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Your sign-in expired. Enter your password again."

    resp, _ = await _totp(user_client, cookies, pyotp.TOTP(secret).now())
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Your sign-in expired. Enter your password again."


async def test_backoff_across_logins_returns_429(user_client, make_user, db):
    user, secret = await _totp_user(make_user, db)
    for _ in range(2):
        _, cookies = await _login(user_client, user)
        await _totp(user_client, cookies, "000000")
        await _totp(user_client, cookies, "000000")
    _, cookies = await _login(user_client, user)
    await _totp(user_client, cookies, "000000")  # 5th consecutive failure

    _, cookies = await _login(user_client, user)
    resp, _ = await _totp(user_client, cookies, pyotp.TOTP(secret).now())
    assert resp.status_code == 429
    assert resp.json()["detail"].startswith("Too many attempts, try again in")


async def test_success_resets_streak(user_client, make_user, db):
    user, secret = await _totp_user(make_user, db)
    _, cookies = await _login(user_client, user)
    for _ in range(3):
        await _totp(user_client, cookies, "000000")
    resp, _ = await _totp(user_client, cookies, pyotp.TOTP(secret).now())
    assert resp.status_code == 200
    await db.refresh(user)
    assert user.mfa_failed_streak == 0


async def test_totp_replay_rejected(user_client, make_user, db):
    user, secret = await _totp_user(make_user, db)
    code = pyotp.TOTP(secret).now()
    _, cookies = await _login(user_client, user)
    resp, _ = await _totp(user_client, cookies, code)
    assert resp.status_code == 200

    _, cookies = await _login(user_client, user)
    resp, _ = await _totp(user_client, cookies, code)
    assert resp.status_code == 400


async def test_new_login_invalidates_previous_pending(user_client, make_user, db):
    user, secret = await _totp_user(make_user, db)
    _, first = await _login(user_client, user)
    await _login(user_client, user)

    resp, _ = await _totp(user_client, first, pyotp.TOTP(secret).now())
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Your sign-in expired. Enter your password again."


async def test_totp_verify_ignores_stale_access_cookie(user_client, make_user, db):
    user, secret = await _totp_user(make_user, db)
    _, cookies = await _login(user_client, user)
    resp, _ = await _totp(
        user_client, cookies, pyotp.TOTP(secret).now(), extra_cookie="access_token=garbage"
    )
    assert resp.status_code == 200


async def test_required_unenrolled_login_returns_setup(user_client, make_user, db):
    user = await make_user()
    user.mfa_required = True
    await db.flush()

    body, cookies = await _login(user_client, user)
    assert body == {"mfa_required": "setup", "methods": [], "email": user.email}
    assert "access_token" not in cookies


async def test_passkey_login_flow(user_client, make_user, db, monkeypatch):
    user = await make_user()
    user.webauthn_credentials.append(
        WebAuthnCredential(credential_id="Y2lk", public_key=b"pk", name="Key", sign_count=0)
    )
    await db.flush()
    monkeypatch.setattr(
        passkeys, "verify_authentication_response", lambda **_: SimpleNamespace(new_sign_count=1)
    )

    body, cookies = await _login(user_client, user)
    assert body["methods"] == ["passkey"]

    opts = await user_client.post("/api/v1/auth/2fa/passkey/options", headers=_pending(cookies))
    assert opts.status_code == 200
    assert "challenge" in opts.json()

    resp = await user_client.post(
        "/api/v1/auth/2fa/passkey", json={"credential": {"id": "Y2lk"}}, headers=_pending(cookies)
    )
    assert resp.status_code == 200, resp.text
    assert "access_token" in resp.cookies
    user_client.cookies.clear()
