"""Token version: JWTs carry a `tv` claim and stale ones are rejected."""
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.config import settings
from app.models.user import User
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    token_version_matches,
)
from tests.conftest import cookie_header

PASSWORD = "correct-horse-1"


async def _login(client, user: User) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert resp.status_code == 200
    access, refresh = resp.cookies["access_token"], resp.cookies["refresh_token"]
    client.cookies.clear()
    return access, refresh


# ── Unit ──


def test_access_token_carries_tv():
    token = create_access_token(uuid.uuid4(), "developer", 3)
    assert decode_token(token)["tv"] == 3


def test_refresh_token_carries_tv():
    token = create_refresh_token(uuid.uuid4(), 3)
    assert decode_token(token)["tv"] == 3


def test_token_version_matches_missing_claim_is_zero():
    assert token_version_matches({"sub": "x"}, User(token_version=0)) is True
    assert token_version_matches({"sub": "x"}, User(token_version=1)) is False


def test_token_version_matches_mismatch():
    assert token_version_matches({"tv": 1}, User(token_version=2)) is False


# ── HTTP ──


async def test_login_sets_cookies_that_authenticate(user_client, make_user):
    user = await make_user()
    access, _ = await _login(user_client, user)

    resp = await user_client.get("/api/v1/users/me", headers=cookie_header(access))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(user.id)


async def test_legacy_access_token_without_tv_accepted(user_client, make_user):
    user = await make_user()
    legacy = jwt.encode(
        {
            "sub": str(user.id),
            "role": "developer",
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    resp = await user_client.get("/api/v1/users/me", headers=cookie_header(legacy))
    assert resp.status_code == 200


async def test_stale_access_token_rejected(user_client, make_user, db):
    user = await make_user()
    access = create_access_token(user.id, user.role.value, 0)
    user.token_version = 1
    await db.flush()

    resp = await user_client.get("/api/v1/users/me", headers=cookie_header(access))
    assert resp.status_code == 401


async def test_stale_refresh_token_rejected(user_client, make_user, db):
    user = await make_user()
    refresh = create_refresh_token(user.id, 0)
    user.token_version = 1
    await db.flush()

    resp = await user_client.post(
        "/api/v1/auth/refresh", headers=cookie_header(refresh=refresh)
    )
    assert resp.status_code == 401


async def test_refresh_issues_tokens_with_current_tv(user_client, make_user, db):
    user = await make_user()
    user.token_version = 2
    await db.flush()
    refresh = create_refresh_token(user.id, 2)

    resp = await user_client.post(
        "/api/v1/auth/refresh", headers=cookie_header(refresh=refresh)
    )
    assert resp.status_code == 200
    assert decode_token(resp.cookies["access_token"])["tv"] == 2
    user_client.cookies.clear()
