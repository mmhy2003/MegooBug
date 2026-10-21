"""PATCH /users/me and /users/me/password."""
from sqlalchemy import select

from app.models.api_token import ApiToken
from app.models.user import User
from app.services.token import generate_api_token
from tests.conftest import cookie_header

PASSWORD = "correct-horse-1"
NEW_PASSWORD = "battery-staple-2"


async def _login(client, email: str, password: str = PASSWORD) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200
    access, refresh = resp.cookies["access_token"], resp.cookies["refresh_token"]
    client.cookies.clear()
    return access, refresh


async def _change_password(client, access: str, current: str, new: str):
    resp = await client.patch(
        "/api/v1/users/me/password",
        json={"current_password": current, "new_password": new},
        headers=cookie_header(access),
    )
    cookies = dict(resp.cookies)
    client.cookies.clear()
    return resp, cookies


# ── PATCH /me ──


async def test_patch_me_trims_name(user_client, make_user):
    user = await make_user()
    access, _ = await _login(user_client, user.email)

    resp = await user_client.patch(
        "/api/v1/users/me", json={"name": "  Alex Morgan  "}, headers=cookie_header(access)
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Alex Morgan"


async def test_patch_me_rejects_blank_name(user_client, make_user, db):
    user = await make_user()
    access, _ = await _login(user_client, user.email)

    resp = await user_client.patch(
        "/api/v1/users/me", json={"name": "   "}, headers=cookie_header(access)
    )
    assert resp.status_code == 422
    await db.refresh(user)
    assert user.name == "Test User"


async def test_patch_me_duplicate_email_409(user_client, make_user):
    user = await make_user()
    other = await make_user()
    access, _ = await _login(user_client, user.email)

    resp = await user_client.patch(
        "/api/v1/users/me", json={"email": other.email}, headers=cookie_header(access)
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Email already in use"


# ── PATCH /me/password ──


async def test_password_wrong_current_400(user_client, make_user):
    user = await make_user()
    access, _ = await _login(user_client, user.email)

    resp, _ = await _change_password(user_client, access, "wrong-password", NEW_PASSWORD)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Current password is incorrect"


async def test_password_same_as_current_400(user_client, make_user):
    user = await make_user()
    access, _ = await _login(user_client, user.email)

    resp, _ = await _change_password(user_client, access, PASSWORD, PASSWORD)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "New password must be different from the current password"


async def test_password_change_bumps_version_and_sets_cookies(user_client, make_user, db):
    user = await make_user()
    access, _ = await _login(user_client, user.email)

    resp, cookies = await _change_password(user_client, access, PASSWORD, NEW_PASSWORD)
    assert resp.status_code == 200
    assert resp.json() == {"message": "Password updated"}
    assert "access_token" in cookies and "refresh_token" in cookies
    await db.refresh(user)
    assert user.token_version == 1


async def test_password_change_keeps_caller_signed_in(user_client, make_user):
    user = await make_user()
    access, _ = await _login(user_client, user.email)

    _, cookies = await _change_password(user_client, access, PASSWORD, NEW_PASSWORD)
    resp = await user_client.get(
        "/api/v1/users/me", headers=cookie_header(cookies["access_token"])
    )
    assert resp.status_code == 200


async def test_old_access_token_rejected_after_password_change(user_client, make_user):
    user = await make_user()
    access, _ = await _login(user_client, user.email)

    await _change_password(user_client, access, PASSWORD, NEW_PASSWORD)
    resp = await user_client.get("/api/v1/users/me", headers=cookie_header(access))
    assert resp.status_code == 401


async def test_old_refresh_token_rejected_after_password_change(user_client, make_user):
    user = await make_user()
    access, refresh = await _login(user_client, user.email)

    await _change_password(user_client, access, PASSWORD, NEW_PASSWORD)
    resp = await user_client.post(
        "/api/v1/auth/refresh", headers=cookie_header(refresh=refresh)
    )
    assert resp.status_code == 401


async def test_login_with_new_password_after_change(user_client, make_user):
    user = await make_user()
    access, _ = await _login(user_client, user.email)

    await _change_password(user_client, access, PASSWORD, NEW_PASSWORD)
    await _login(user_client, user.email, NEW_PASSWORD)
    resp = await user_client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert resp.status_code == 401


async def test_api_token_survives_password_change(user_client, make_user, db):
    user = await make_user()
    raw, prefix, token_hash = generate_api_token()
    db.add(ApiToken(user_id=user.id, name="CI", token_hash=token_hash, token_prefix=prefix))
    await db.flush()
    access, _ = await _login(user_client, user.email)

    await _change_password(user_client, access, PASSWORD, NEW_PASSWORD)
    resp = await user_client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {raw}"}
    )
    assert resp.status_code == 200
