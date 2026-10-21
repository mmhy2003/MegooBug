"""Passkeys (WebAuthn) as a second factor.

The Relying Party is the host of APP_URL and the expected origin is APP_URL
itself. One outstanding challenge per user is kept on the users row and is
valid for five minutes; it is consumed by the matching finish_* call.
"""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import settings
from app.models.user import User
from app.models.webauthn_credential import WebAuthnCredential

RP_NAME = "MegooBug"
CHALLENGE_TTL = timedelta(minutes=5)


class PasskeyError(Exception):
    """Passkey registration or authentication could not be verified."""


def _rp_id() -> str:
    return urlparse(settings.APP_URL).hostname or "localhost"


def _origin() -> str:
    return settings.APP_URL.rstrip("/")


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _descriptors(user: User) -> list[PublicKeyCredentialDescriptor]:
    return [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
        for c in user.webauthn_credentials
    ]


def _store_challenge(user: User, challenge: bytes, now: datetime) -> None:
    user.webauthn_challenge = bytes_to_base64url(challenge)
    user.webauthn_challenge_expires_at = now + CHALLENGE_TTL


def _take_challenge(user: User, now: datetime) -> bytes:
    """Return and clear the outstanding challenge; raise if missing or expired."""
    challenge, expires = user.webauthn_challenge, user.webauthn_challenge_expires_at
    user.webauthn_challenge = None
    user.webauthn_challenge_expires_at = None
    if challenge is None or expires is None or now > expires:
        raise PasskeyError("No valid passkey challenge")
    return base64url_to_bytes(challenge)


def registration_options(user: User, now: datetime | None = None) -> dict:
    opts = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=RP_NAME,
        user_id=user.id.bytes,
        user_name=user.email,
        user_display_name=user.name,
        exclude_credentials=_descriptors(user),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    _store_challenge(user, opts.challenge, _now(now))
    return json.loads(options_to_json(opts))


def finish_registration(
    user: User, credential: dict, name: str, now: datetime | None = None
) -> WebAuthnCredential:
    challenge = _take_challenge(user, _now(now))
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
            require_user_verification=False,
        )
    except Exception as exc:  # library raises several error types
        raise PasskeyError("Passkey registration failed") from exc

    transports = (credential.get("response") or {}).get("transports")
    cred = WebAuthnCredential(
        credential_id=bytes_to_base64url(verified.credential_id),
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        transports=transports if isinstance(transports, list) else None,
        name=(name or "").strip()[:100] or "Passkey",
    )
    user.webauthn_credentials.append(cred)
    return cred


def authentication_options(user: User, now: datetime | None = None) -> dict:
    opts = generate_authentication_options(
        rp_id=_rp_id(),
        allow_credentials=_descriptors(user),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    _store_challenge(user, opts.challenge, _now(now))
    return json.loads(options_to_json(opts))


def finish_authentication(
    user: User, credential: dict, now: datetime | None = None
) -> WebAuthnCredential:
    current = _now(now)
    challenge = _take_challenge(user, current)
    # Only this user's own passkeys can satisfy their second step.
    cred = next(
        (c for c in user.webauthn_credentials if c.credential_id == credential.get("id")),
        None,
    )
    if cred is None:
        raise PasskeyError("Unknown passkey")
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
            credential_public_key=cred.public_key,
            credential_current_sign_count=cred.sign_count,
            require_user_verification=False,
        )
    except Exception as exc:
        raise PasskeyError("Passkey verification failed") from exc

    cred.sign_count = verified.new_sign_count
    cred.last_used_at = current
    return cred
