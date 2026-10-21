import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Response
from jose import JWTError, jwt

from app.config import settings
from app.models.user import User


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(user_id: uuid.UUID, role: str, token_version: int) -> str:
    """Create a JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "tv": token_version,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: uuid.UUID, token_version: int) -> str:
    """Create a JWT refresh token with longer expiry."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "tv": token_version,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),  # unique token ID for rotation
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT token. Returns payload or None if invalid."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


def token_version_matches(payload: dict, user: User) -> bool:
    """Whether a decoded JWT was issued at the user's current token version.

    Tokens issued before the claim existed carry no "tv" and count as 0, so
    sessions that predate it stay valid until the first password change.
    """
    return payload.get("tv", 0) == user.token_version


def issue_auth_cookies(response: Response, user: User) -> None:
    """Issue fresh access + refresh tokens for the user as HTTP-only cookies."""
    access_token = create_access_token(user.id, user.role.value, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)

    # Derive Secure flag from the configured APP_URL scheme — this is more
    # reliable than checking ENVIRONMENT, which may be "development" even
    # when the instance is served over HTTPS behind a reverse proxy.
    is_https = settings.APP_URL.startswith("https://")

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_https,
        samesite="lax",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_https,
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",  # Must be "/" so Android PWA / mobile browsers always send it
    )


def create_invite_token() -> str:
    """Generate a secure random token for invitations."""
    return str(uuid.uuid4()) + "-" + str(uuid.uuid4())
