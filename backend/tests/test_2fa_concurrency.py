"""Second-step state under real commits and concurrent requests."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pyotp
from sqlalchemy import select

from app.models.user import User, UserRole
from app.services.auth import hash_password
from app.services.mfa import begin_totp_setup, confirm_totp_setup

PASSWORD = "correct-horse-1"


async def _committed_totp_user(factory) -> tuple[str, str]:
    """Insert and commit a TOTP-enrolled user; returns (email, secret)."""
    email = f"committed-{uuid.uuid4().hex}@example.com"
    async with factory() as session:
        user = User(email=email, name="C", password_hash=hash_password(PASSWORD), role=UserRole.DEVELOPER)
        secret, _ = begin_totp_setup(user)
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        assert confirm_totp_setup(user, pyotp.TOTP(secret).at(past), now=past)
        session.add(user)
        await session.commit()
    return email, secret


async def _pending_cookie(client, email: str) -> dict:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    cookie = resp.cookies["mfa_pending"]
    client.cookies.clear()
    return {"Cookie": f"mfa_pending={cookie}"}


async def _reload(factory, email: str) -> User:
    async with factory() as session:
        return (await session.execute(select(User).where(User.email == email))).scalar_one()


async def test_failure_counter_persists_after_commit(committed_client):
    client, factory = committed_client
    email, _ = await _committed_totp_user(factory)
    headers = await _pending_cookie(client, email)

    resp = await client.post("/api/v1/auth/2fa/totp", json={"code": "000000"}, headers=headers)
    assert resp.status_code == 400
    user = await _reload(factory, email)
    assert user.mfa_pending_failures == 1
    assert user.mfa_failed_streak == 1


async def test_concurrent_wrong_codes_all_counted(committed_client):
    client, factory = committed_client
    email, _ = await _committed_totp_user(factory)
    headers = await _pending_cookie(client, email)

    await asyncio.gather(*[
        client.post("/api/v1/auth/2fa/totp", json={"code": "000000"}, headers=headers)
        for _ in range(10)
    ])
    user = await _reload(factory, email)
    # Exactly five are counted; the pending sign-in then dies and the rest are refused
    assert user.mfa_failed_streak == 5
    assert user.mfa_pending_jti is None


async def test_concurrent_same_code_accepted_once(committed_client):
    client, factory = committed_client
    email, secret = await _committed_totp_user(factory)
    headers = await _pending_cookie(client, email)
    code = pyotp.TOTP(secret).now()

    results = await asyncio.gather(*[
        client.post("/api/v1/auth/2fa/totp", json={"code": code}, headers=headers)
        for _ in range(3)
    ])
    client.cookies.clear()
    assert sorted(r.status_code for r in results) == [200, 400, 400]
