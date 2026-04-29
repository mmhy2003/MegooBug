import secrets
from datetime import datetime, timezone

import bcrypt

from app.logging import get_logger

logger = get_logger("services.token")

TOKEN_PREFIX = "mgb_"


def generate_api_token() -> tuple[str, str, str]:
    """Generate a new API token.

    Returns:
        (raw_token, token_prefix, token_hash) tuple.
        raw_token is shown to the user once, token_hash is stored.
    """
    random_part = secrets.token_hex(32)  # 64 hex chars
    raw_token = f"{TOKEN_PREFIX}{random_part}"
    prefix = raw_token[:12]  # "mgb_" + first 8 hex chars
    token_hash = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode()
    return raw_token, prefix, token_hash


def verify_api_token(raw_token: str, token_hash: str) -> bool:
    """Verify a raw API token against a stored hash."""
    try:
        return bcrypt.checkpw(raw_token.encode(), token_hash.encode())
    except Exception:
        return False


def is_token_expired(expires_at: datetime | None) -> bool:
    """Check if a token has expired."""
    if expires_at is None:
        return False
    return datetime.now(timezone.utc) > expires_at
