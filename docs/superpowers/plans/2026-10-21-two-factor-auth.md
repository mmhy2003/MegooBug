# Two-Factor Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optional, admin-requirable 2FA (TOTP and passkeys) as a second login step after the password, with Profile → Security management, admin require/reset, and a server-side reset command.

**Architecture:**
- **Login state:** a correct password for an enrolled or required user issues only a 5-minute `mfa_pending` JWT cookie. Full session cookies (`issue_auth_cookies`) are issued only after a TOTP code or passkey assertion is verified, or after forced setup completes.
- **Shared logic:** TOTP and WebAuthn live in two service modules, used by the login step, forced setup and the profile endpoints.
- **Attempt tracking:** per-credential and per-account attempt state lives on the `users` row.

**Tech Stack:**
- **Backend:** FastAPI, SQLAlchemy 2 async, Alembic, `pyotp`, `webauthn` (py_webauthn 2.x), and Fernet from `cryptography`, which is already installed via `python-jose[cryptography]`.
- **Frontend:** Next 16 / React 19, `@simplewebauthn/browser` and `qrcode`.

**Spec:** `docs/superpowers/specs/2026-10-21-two-factor-auth-design.md`

## Global Constraints

- **Everything runs in Docker; there is no Node on the host.**
  - Backend tests: `docker compose -f docker-compose.dev.yml exec -T backend pytest -q`.
  - Frontend checks: `... exec -T frontend npx tsc --noEmit` and `npx eslint <touched files>`.
  - After adding a dependency, rebuild the image: `docker compose -f docker-compose.dev.yml up --build -d backend frontend`.
- **Pin exact versions.**
  - `pyotp==2.9.0`.
  - `webauthn==<latest 2.x>`: check it with `pip index versions webauthn` in the backend container.
  - `@simplewebauthn/browser@<latest 13.x>` and `qrcode@1.5.4` + `@types/qrcode`: check them with `npm view`. Use `--save-exact`.
- **Migrations** chain after `a7b8c9d0e1f2`. The dev DB is at head; a fresh DB can't run the chain (an existing bug, out of scope).
- **Failure responses that must persist counters return `JSONResponse(status_code=…, content={"detail": …})`. They never `raise HTTPException`.** The reason: `get_db` (`app/database.py`) rolls back on any exception, which would discard the failure count.
- **2FA-step errors use 400 or 429, never 401.** On a 401, `frontend/src/lib/api.ts` tries a refresh and then redirects to `/login`.
- **TOTP settings:** RFC 6238, SHA-1, 6 digits, 30-second step, ±1 step window. A step at or below `users.totp_last_step` is rejected. The issuer is `MegooBug` and the label is the user's email.
- **WebAuthn settings:** `rp_id = urlparse(settings.APP_URL).hostname`, `expected_origin = settings.APP_URL.rstrip("/")`, `rp_name = "MegooBug"`. Use `resident_key=PREFERRED`, `user_verification=PREFERRED`, and `require_user_verification=False` when verifying. The user handle is `user.id.bytes`. Challenges are valid for 5 minutes.
- **Pending credential:**
  - Cookie `mfa_pending`: `httponly`, `samesite="lax"`, `secure` exactly as in `issue_auth_cookies`, `path="/api/v1/auth"`, `max_age=300`.
  - JWT payload `{"sub", "type": "mfa_pending", "tv", "jti", "exp"}`.
  - The cookie is valid only while `jti == users.mfa_pending_jti`.
- **Limits:**
  - **Per pending credential:** 5 failures invalidate it.
  - **Per account:** after 5 consecutive failures, wait `min(30 * 2**(streak-5), 900)` seconds before the next attempt.
  - **Reset:** both counters are cleared on success, admin reset and the CLI reset.
- **Copy, verbatim:**
  - "Verify it's you"
  - "Use a passkey"
  - "Use authenticator app"
  - "Lost access? Ask an admin to reset your 2FA."
  - "Set up two-factor authentication"
  - "An admin requires 2FA for your account. Set up one method to continue."
  - "Too many attempts, try again in {N} seconds" (or "{M} minutes" when ≥ 60)
  - "Incorrect code"
  - "Your sign-in expired. Enter your password again."
  - "Must set it up at next sign-in"
- **Password confirmation:** these actions require the current password, checked server-side:
  - begin TOTP setup (which also covers Replace),
  - remove TOTP,
  - begin passkey registration,
  - remove a passkey.

  Renaming a passkey and forced setup during login don't require it.
- **API tokens (`mgb_…`)** are untouched by everything here.

## Review Focus

1. **The second step after the access token expires mid-login.** The pending flow must never depend on `access_token`. A stale `access_token` cookie in the browser must not let `/auth/2fa/*` succeed or fail differently. Pinned in Task 3 (`test_totp_verify_ignores_stale_access_cookie`).
2. **Two tabs logging in at once.** A second password login replaces `mfa_pending_jti`, so the first tab's pending cookie gets "Your sign-in expired…" and never a 500. Pinned in Task 3 (`test_new_login_invalidates_previous_pending`).
3. **TOTP code with spaces or a dash** ("482 913", "482-913"). It must be accepted after normalising. Pinned in Task 1 (`test_verify_totp_accepts_spaced_code`).
4. **A passkey assertion for a credential that belongs to another user.** It must be rejected, never accepted because the credential id is unique. Pinned in Task 2 (`test_finish_authentication_rejects_foreign_credential`).
5. **Admin turns off Require for a user who is mid forced-setup.** That user's next login must just log in, with no stuck setup screen. Pinned in Task 6 (`test_unrequire_then_login_is_plain`).

---

## File Structure

**Backend**
- `app/models/user.py`: modify. Adds the new columns, the `webauthn_credentials` relationship, and the `mfa_methods` / `mfa_enrolled` properties.
- `app/models/webauthn_credential.py`: create. The `WebAuthnCredential` model. Register it in `app/models/__init__.py`.
- `alembic/versions/b8c9d0e1f2a3_add_two_factor_auth.py`: create.
- `app/services/mfa.py`: create. Secret encryption, TOTP and backoff.
- `app/services/passkeys.py`: create. WebAuthn options and verification.
- `app/services/auth.py`: modify. The pending cookie helpers.
- `app/dependencies.py`: modify. Adds `get_mfa_pending_user` and `MfaPendingUser`.
- `app/schemas/auth.py` and `app/schemas/user.py`: modify. Login response union, 2FA request/response models, and the MFA fields on `UserResponse`.
- `app/api/v1/auth.py`: modify. Login branching.
- `app/api/v1/two_factor.py`: create. Login second step and forced setup, at `/api/v1/auth/2fa/*`.
- `app/api/v1/two_factor_settings.py`: create. Profile endpoints at `/api/v1/users/me/2fa/*` and admin endpoints at `/api/v1/users/{id}/2fa*`. Mount it in `app/api/v1/__init__.py` with prefix `/users`, **before** `users.router`.
- `app/scripts/reset_2fa.py`: create. Also add a `reset-2fa` target to `Makefile`.
- Tests: `tests/test_mfa_service.py`, `tests/test_passkeys_service.py`, `tests/test_login_2fa.py`, `tests/test_2fa_settings.py`, `tests/test_2fa_admin.py`.

**Frontend**
- `src/lib/two-factor.ts`: create. Typed API calls and the WebAuthn helpers.
- `src/components/two-factor/totp-setup-modal.tsx`: create. Used by the profile and by forced setup.
- `src/components/two-factor/confirm-password-dialog.tsx`: create.
- `src/components/auth/login-second-step.tsx`: create. The choose, TOTP, passkey and setup screens.
- `src/app/(auth)/login/page.tsx`: modify.
- `src/components/profile/security-settings.tsx`: create. Also modify `src/app/(dashboard)/profile/page.tsx` to add the tab.
- `src/app/(dashboard)/users/page.tsx`: modify.
- `src/components/current-user-provider.tsx`: modify (types).
- `docs/prd.md`: modify.

---

### Task 1: Schema, models and the TOTP service

**Files:**
- Modify: `backend/app/models/user.py`, `backend/app/models/__init__.py`, `backend/app/schemas/user.py`
- Create: `backend/app/models/webauthn_credential.py`, `backend/alembic/versions/b8c9d0e1f2a3_add_two_factor_auth.py`, `backend/app/services/mfa.py`
- Modify: `backend/requirements.txt` (add `pyotp==2.9.0`)
- Test: `backend/tests/test_mfa_service.py`

**Interfaces:**
- Produces, as new `User` columns:
  - `mfa_required: bool` (server_default false)
  - `totp_secret: str | None` (Text, encrypted)
  - `totp_pending_secret: str | None` (Text, encrypted)
  - `totp_enabled_at: datetime | None`
  - `totp_last_step: int | None` (BigInteger)
  - `webauthn_challenge: str | None` (base64url)
  - `webauthn_challenge_expires_at: datetime | None`
  - `mfa_pending_jti: str | None` (String 64)
  - `mfa_pending_failures: int` (default 0)
  - `mfa_failed_streak: int` (default 0)
  - `mfa_retry_after: datetime | None`
- Produces, on `User`:
  - `webauthn_credentials: list[WebAuthnCredential]`, with `lazy="selectin"`, `cascade="all, delete-orphan"`, ordered by `created_at`.
  - Property `mfa_methods -> list[str]`: `"passkey"` if any credentials, then `"totp"` if `totp_enabled_at` is set, in that order.
  - Property `mfa_enrolled -> bool`.
- Produces, the `WebAuthnCredential` model:
  - `id: UUID` pk
  - `user_id: UUID` (FK `users.id`, `ondelete="CASCADE"`, indexed)
  - `credential_id: str` (String 512, unique, base64url)
  - `public_key: bytes` (LargeBinary)
  - `sign_count: int` (BigInteger, default 0)
  - `transports: list | None` (JSONB)
  - `name: str` (String 100)
  - `created_at`
  - `last_used_at: datetime | None`
- Produces: `UserResponse` gains `mfa_required: bool` and `mfa_methods: list[str]`.
- Produces, in `app/services/mfa.py`:
  - `encrypt_secret(plain: str) -> str` and `decrypt_secret(token: str) -> str`. Fernet; the key is `urlsafe_b64encode(sha256(b"megoobug-mfa:" + SECRET_KEY.encode()).digest())`.
  - `begin_totp_setup(user: User) -> tuple[str, str]`. Sets `user.totp_pending_secret` and returns `(secret_base32, otpauth_uri)`.
  - `confirm_totp_setup(user: User, code: str, now: datetime | None = None) -> bool`. Moves the pending secret into place and sets `totp_enabled_at` and `totp_last_step`.
  - `verify_totp(user: User, code: str, now: datetime | None = None) -> bool`. Enforces the ±1 window and replay protection; updates `totp_last_step`.
  - `remove_totp(user: User) -> None`.
  - `normalize_code(code: str) -> str | None`. Strips spaces and `-`; returns `None` unless the result is exactly 6 digits.
  - `mfa_backoff_remaining(user: User, now: datetime | None = None) -> int | None`. Returns the seconds left, or `None`.
  - `record_mfa_failure(user: User, now: datetime | None = None) -> None`.
  - `reset_mfa_counters(user: User) -> None`. Clears the streak, `retry_after`, the pending failures and the jti.
  - `clear_all_mfa(user: User) -> None`. Removes the TOTP and pending secrets, deletes all credentials (`user.webauthn_credentials.clear()`) and resets the counters.

- [ ] **Step 1: Write the failing tests** in `tests/test_mfa_service.py`. Use pyotp with an explicit `now` to make codes deterministic.

  Use the existing `make_user` fixture and `db` session.

  - `test_encrypt_roundtrip`: `decrypt_secret(encrypt_secret("ABC")) == "ABC"`, and `encrypt_secret("ABC") != "ABC"`.
  - `test_confirm_totp_setup_enables`:
    - `secret, uri = begin_totp_setup(user)`.
    - `uri.startswith("otpauth://totp/MegooBug:")` and `"issuer=MegooBug" in uri`.
    - Confirming with `pyotp.TOTP(secret).at(now)` returns True.
    - Afterwards `user.totp_enabled_at` is set, `user.totp_pending_secret is None`, and `decrypt_secret(user.totp_secret) == secret`.
  - `test_confirm_totp_setup_wrong_code_keeps_disabled`: returns False, `totp_enabled_at is None`, and `totp_secret is None`.
  - `test_verify_totp_window`: codes for `now - 30s`, `now` and `now + 30s` each verify, using fresh users so replay doesn't interfere. `now - 90s` fails.
  - `test_verify_totp_rejects_replay`: the same code twice at the same `now` gives True, then False.
  - `test_verify_totp_accepts_spaced_code`: `"482 913"`-style formatting of a valid code verifies, and so does `"482-913"`.
  - `test_mfa_methods_order`: with TOTP enabled plus one `WebAuthnCredential` appended, `user.mfa_methods == ["passkey", "totp"]` and `user.mfa_enrolled is True`. A fresh user gives `[]` and `False`.
  - `test_backoff_progression`:
    - After 4 `record_mfa_failure` calls, `mfa_backoff_remaining` is None.
    - After the 5th it's 30. After the 6th it's 60.
    - After the 10th the wait is capped at 900.
    - `reset_mfa_counters` brings it back to None.

- [ ] **Step 2: Run the tests and confirm they fail**

  Run: `docker compose -f docker-compose.dev.yml exec -T backend pytest tests/test_mfa_service.py -q`
  Expected: an ImportError for `app.services.mfa`. Add pyotp to requirements and rebuild first if the import of `pyotp` fails.

- [ ] **Step 3: Implement** the models, the migration and `services/mfa.py` as listed under Interfaces. In `UserResponse`, read `mfa_methods` from the model property; it works with `from_attributes`.

- [ ] **Step 4: Run the whole backend suite and confirm it passes**

  Expected: all pass. The existing user and auth tests still pass, because `UserResponse` only gained fields.

- [ ] **Step 5: Apply the migration and check it**

  Run: `... exec -T backend sh -c "alembic upgrade head && alembic downgrade -1 && alembic upgrade head && alembic current"`
  Expected: it ends at `b8c9d0e1f2a3 (head)`.

- [ ] **Step 6: Commit** with `feat(2fa): schema, models and TOTP service`.

---

### Task 2: Passkey service

**Files:**
- Create: `backend/app/services/passkeys.py`
- Modify: `backend/requirements.txt` (add the pinned `webauthn`)
- Test: `backend/tests/test_passkeys_service.py`

**Interfaces:**
- Consumes, from Task 1: `User` and `WebAuthnCredential`, plus the `webauthn_challenge*` columns.
- Produces:
  - `class PasskeyError(Exception)`.
  - `registration_options(user: User, now: datetime | None = None) -> dict`.
    - Calls `generate_registration_options(...)`, excluding the user's existing credentials.
    - Stores the challenge as base64url, with an expiry of now + 5 min.
    - Returns `json.loads(options_to_json(opts))`.
  - `finish_registration(user: User, credential: dict, name: str, now: datetime | None = None) -> WebAuthnCredential`.
    - Verifies against the stored, unexpired challenge, then clears the challenge.
    - Appends the credential to `user.webauthn_credentials`. `name` is stripped and cut to 100 characters, defaulting to `"Passkey"`.
    - Raises `PasskeyError` on any failure.
  - `authentication_options(user: User, now: datetime | None = None) -> dict`. Its `allow_credentials` lists the user's credentials.
  - `finish_authentication(user: User, credential: dict, now: datetime | None = None) -> WebAuthnCredential`.
    - Finds the credential by `credential["id"]` **among `user.webauthn_credentials` only**.
    - Verifies it, then updates `sign_count` and `last_used_at` and clears the challenge.
    - Raises `PasskeyError` on failure.

- [ ] **Step 1: Write the failing tests.** Mock only at the library boundary: monkeypatch `app.services.passkeys.verify_registration_response` / `verify_authentication_response` to return simple objects with the needed attributes, or to raise.

  - `test_registration_options_stores_challenge`:
    - The returned `opts["rp"]["id"] == urlparse(settings.APP_URL).hostname`.
    - `opts["challenge"] == user.webauthn_challenge`.
    - The expiry is about 5 minutes after `now`.
  - `test_finish_registration_saves_credential`: the fake verified result has `credential_id=b"cid"`, `credential_public_key=b"pk"` and `sign_count=0`.
    - The credential is saved with `credential_id == "Y2lk"` (base64url of `b"cid"`).
    - Its name is the stripped one, and the challenge is cleared.
  - `test_finish_registration_expired_challenge_raises`: with `now` 6 minutes later → `PasskeyError`, and nothing is saved.
  - `test_finish_authentication_updates_sign_count`: `new_sign_count=5` → `sign_count == 5` and `last_used_at` is set.
  - `test_finish_authentication_rejects_foreign_credential`: the credential belongs to user B, and user A sends its id → `PasskeyError`.
  - `test_finish_authentication_verify_error_raises`: the patched verify raises → `PasskeyError`.

- [ ] **Step 2: Run the tests and confirm they fail.** Expected: an ImportError for `app.services.passkeys`.

- [ ] **Step 3: Implement** `services/passkeys.py` with the WebAuthn settings from Global Constraints.

- [ ] **Step 4: Run the whole backend suite and confirm it passes.**

- [ ] **Step 5: Commit** with `feat(2fa): passkey (WebAuthn) service`.

---

### Task 3: Login second step

**Files:**
- Modify: `backend/app/services/auth.py`, `backend/app/dependencies.py`, `backend/app/schemas/auth.py`, `backend/app/api/v1/auth.py`, `backend/app/api/v1/__init__.py`
- Create: `backend/app/api/v1/two_factor.py`
- Test: `backend/tests/test_login_2fa.py`

**Interfaces:**
- Consumes: `verify_totp`, `normalize_code`, `mfa_backoff_remaining`, `record_mfa_failure` and `reset_mfa_counters` (Task 1); `authentication_options`, `finish_authentication` and `PasskeyError` (Task 2); `issue_auth_cookies`.
- Produces, in `services/auth.py`:
  - `issue_mfa_pending_cookie(response: Response, user: User) -> None`. Sets a new `mfa_pending_jti`, resets `mfa_pending_failures` and sets the cookie.
  - `clear_mfa_pending(response: Response, user: User) -> None`. Clears the jti and deletes the cookie with `path="/api/v1/auth"`.
- Produces, in `dependencies.py`: `get_mfa_pending_user(request, db) -> User` and `MfaPendingUser = Annotated[User, Depends(get_mfa_pending_user)]`. An invalid, expired, wrong-type, wrong-`tv` or wrong-jti cookie, or an inactive user, raises `HTTPException(400, "Your sign-in expired. Enter your password again.")`. Raising is fine here, because nothing needs to persist.
- Produces, in `schemas/auth.py`:
  - `MfaChallengeResponse(mfa_required: Literal["verify", "setup"], methods: list[str], email: str)`.
  - `TotpCodeRequest(code: str)`.
  - `PasskeyAssertionRequest(credential: dict)`.
- Produces, the routes:
  - `POST /api/v1/auth/login`, with `response_model=UserResponse | MfaChallengeResponse`:
    - if `user.mfa_enrolled`: pending cookie + `{"mfa_required": "verify", "methods": user.mfa_methods, "email"}`, and **no** `issue_auth_cookies`;
    - elif `user.mfa_required`: the same with `"setup"` and `methods: []`;
    - else: unchanged.
  - `POST /api/v1/auth/2fa/totp`: `TotpCodeRequest` → `UserResponse`, plus session cookies and the pending cookie cleared.
  - `POST /api/v1/auth/2fa/passkey/options` → the WebAuthn request options dict.
  - `POST /api/v1/auth/2fa/passkey`: `PasskeyAssertionRequest` → `UserResponse`, plus cookies.
  - **Shared failure handling for both verify routes**, in a private helper in `two_factor.py`:
    1. If the backoff is active → `JSONResponse(429, "Too many attempts, try again in …")`.
    2. On a failure → `record_mfa_failure`, `user.mfa_pending_failures += 1`.
    3. If that reaches 5 → clear the jti and return `JSONResponse(400, "Your sign-in expired. Enter your password again.")`.
    4. Otherwise → `JSONResponse(400, "Incorrect code")`. For passkeys use "Passkey verification failed".
    5. On success → `reset_mfa_counters`, `clear_mfa_pending` and `issue_auth_cookies`.

- [ ] **Step 1: Write the failing tests** in `tests/test_login_2fa.py`, using `user_client`, `make_user` and `cookie_header`. Enroll TOTP in setup via `begin_totp_setup` + `confirm_totp_setup` at a fixed `now`. Use `monkeypatch` on `app.services.mfa`'s clock, or pass codes for the real `now` (`pyotp.TOTP(secret).now()`).

  - `test_login_without_2fa_unchanged`: 200, the body has `"id"`, and the `access_token` cookie is set.
  - `test_login_enrolled_returns_challenge_without_session`:
    - `json()["mfa_required"] == "verify"` and `methods == ["totp"]`.
    - `"access_token" not in resp.cookies` and `"mfa_pending" in resp.cookies`.
  - `test_pending_cookie_cannot_access_me`: `GET /users/me` with only `Cookie: mfa_pending=…` → 401.
  - `test_totp_verify_completes_login`: → 200; `access_token` and `refresh_token` are set; `GET /me` with them → 200.
  - `test_totp_wrong_code_400_and_counts`: → 400 with `detail == "Incorrect code"`. After `db.refresh(user)`, `mfa_pending_failures == 1` and `mfa_failed_streak == 1`. This proves the JSONResponse path committed.
  - `test_totp_five_failures_invalidate_pending`:
    - The 5th wrong code → 400 with "Your sign-in expired. Enter your password again."
    - A 6th with the correct code → 400 with the same message.
  - `test_backoff_across_logins_returns_429`:
    - Log in and fail twice, five times in total across fresh logins.
    - The next attempt, even with a correct code → 429, and the detail starts with "Too many attempts, try again in".
  - `test_success_resets_streak`: 3 failures, then success → `mfa_failed_streak == 0`.
  - `test_totp_replay_rejected`: log in and verify with code X; log in again; verify with X → 400.
  - `test_new_login_invalidates_previous_pending`: login A, login B; verify with A's pending cookie → 400 "Your sign-in expired…".
  - `test_totp_verify_ignores_stale_access_cookie`: send the pending cookie plus a garbage `access_token` → still 200 with a correct code.
  - `test_required_unenrolled_login_returns_setup`: `mfa_required=True` → `{"mfa_required": "setup", "methods": []}` and no `access_token`.
  - `test_passkey_login_flow`:
    - Monkeypatch `app.api.v1.two_factor.finish_authentication`, or `app.services.passkeys.verify_authentication_response`, to succeed.
    - `/2fa/passkey/options` → 200 and contains `"challenge"`.
    - `/2fa/passkey` → 200 with cookies.

- [ ] **Step 2: Run the tests and confirm they fail.** Expected: the challenge tests fail, because login returns a user, and the `/2fa/*` routes return 404.

- [ ] **Step 3: Implement** as described under Interfaces. Mount `two_factor.router` in `app/api/v1/__init__.py` with `prefix="/auth/2fa"`.

- [ ] **Step 4: Run the whole backend suite and confirm it passes.**

- [ ] **Step 5: Commit** with `feat(2fa): password-then-second-step login with attempt limits`.

---

### Task 4: Forced setup during login

**Files:**
- Modify: `backend/app/api/v1/two_factor.py`, `backend/app/schemas/auth.py`
- Test: append to `backend/tests/test_login_2fa.py`

**Interfaces:**
- Consumes: `MfaPendingUser`, `begin_totp_setup` and `confirm_totp_setup` (Task 1), `registration_options` and `finish_registration` (Task 2).
- Produces:
  - `TotpSetupResponse(secret: str, otpauth_uri: str)` and `PasskeyRegistrationRequest(credential: dict, name: str = "")`, in `schemas/auth.py`. These are reused by Task 5.
  - The routes, all authorised by `MfaPendingUser` and all returning **409** "Two-factor authentication is already set up" if `user.mfa_enrolled`:
    - `POST /api/v1/auth/2fa/setup/totp` → `TotpSetupResponse`;
    - `POST /api/v1/auth/2fa/setup/totp/confirm` with `TotpCodeRequest` → `UserResponse` plus session cookies, or a `JSONResponse(400, "Incorrect code")` (subject to the same per-pending failure counting);
    - `POST /api/v1/auth/2fa/setup/passkey/options` → creation options;
    - `POST /api/v1/auth/2fa/setup/passkey` with `PasskeyRegistrationRequest` → `UserResponse` plus cookies, or 400 "Passkey setup failed".

- [ ] **Step 1: Write the failing tests:**
  - `test_forced_setup_totp_then_session`:
    - The required user logs in → setup.
    - `/2fa/setup/totp` → a secret.
    - Confirming with `pyotp.TOTP(secret).now()` → 200, cookies set, `totp_enabled_at` set.
  - `test_forced_setup_requires_pending_cookie`: `/2fa/setup/totp` with no cookie → 400 "Your sign-in expired…".
  - `test_forced_setup_refused_when_enrolled`: an enrolled user's pending cookie on `/2fa/setup/totp` → 409.
  - `test_forced_setup_passkey_then_session`: patch `verify_registration_response`; options → finish → 200, cookies set, and 1 credential.

- [ ] **Step 2: Run the tests and confirm they fail** with 404s.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the whole suite and confirm it passes.**
- [ ] **Step 5: Commit** with `feat(2fa): forced setup during login for required users`.

---

### Task 5: Profile 2FA endpoints

**Files:**
- Create: `backend/app/api/v1/two_factor_settings.py`
- Modify: `backend/app/api/v1/__init__.py`, `backend/app/schemas/user.py`
- Test: `backend/tests/test_2fa_settings.py`

**Interfaces:**
- Consumes: the Task 1 and Task 2 services, `TotpSetupResponse`, `PasskeyRegistrationRequest`, `verify_password` and `CurrentUser`.
- Produces, in `schemas/user.py`:
  - `PasswordConfirm(password: str)`
  - `PasskeyInfo(id, name, created_at, last_used_at)`
  - `TwoFactorStatus(enabled: bool, required: bool, methods: list[str], totp_enabled_at: datetime | None, passkeys: list[PasskeyInfo])`
  - `PasskeyRename(name: str)`, between 1 and 100 characters after stripping.
- Produces, the routes. All require `CurrentUser`. A wrong password gives **400** "Password is incorrect":
  - `GET /api/v1/users/me/2fa` → `TwoFactorStatus`;
  - `POST /me/2fa/totp` with `PasswordConfirm` → `TotpSetupResponse`. This begins setup or a replacement; the old secret stays active until confirmed.
  - `POST /me/2fa/totp/confirm` with `TotpCodeRequest` → `TwoFactorStatus`, or 400 "Incorrect code";
  - `POST /me/2fa/totp/remove` with `PasswordConfirm` → `TwoFactorStatus`;
  - `POST /me/2fa/passkeys/options` with `PasswordConfirm` → creation options;
  - `POST /me/2fa/passkeys` with `PasskeyRegistrationRequest` → `TwoFactorStatus`. A valid registration challenge from the options call is proof enough; no password is needed here.
  - `PATCH /me/2fa/passkeys/{passkey_id}` with `PasskeyRename` → `TwoFactorStatus`. It returns 404 if the passkey isn't the caller's.
  - `POST /me/2fa/passkeys/{passkey_id}/remove` with `PasswordConfirm` → `TwoFactorStatus`.
- **Last-method rule:** if `user.mfa_required` and the removal would leave `mfa_methods` empty → **400** "2FA is required for your account, so you must keep at least one method."
- Mount `two_factor_settings.router` with `prefix="/users"` **before** `users.router` in `app/api/v1/__init__.py`.

- [ ] **Step 1: Write the failing tests:**
  - `test_status_defaults`: `{"enabled": False, "required": False, "methods": [], "passkeys": []}`, ignoring `totp_enabled_at`.
  - `test_begin_totp_requires_password`: wrong → 400 "Password is incorrect"; right → 200 with a secret.
  - `test_confirm_totp_enables`: after confirming, `methods == ["totp"]` and `enabled` is true.
  - `test_replace_totp_keeps_old_until_confirmed`: begin a replacement; the old code still verifies through `verify_totp`; after confirming the new one, `decrypt_secret(user.totp_secret)` is the new secret.
  - `test_remove_totp_requires_password` and `test_remove_totp`.
  - `test_add_passkey` (patching `verify_registration_response`): options need the password; finishing gives `methods == ["passkey"]`.
  - `test_rename_passkey_no_password` → 200 with the new name. Renaming another user's passkey → 404.
  - `test_remove_passkey_requires_password`.
  - `test_cannot_remove_last_method_when_required`: TOTP only, `mfa_required=True`, remove → 400 with the exact message.
  - `test_can_remove_one_of_two_when_required`: TOTP + passkey, remove the passkey → 200.

- [ ] **Step 2: Run the tests and confirm they fail** with 404s.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the whole suite and confirm it passes.**
- [ ] **Step 5: Commit** with `feat(2fa): profile endpoints with password confirmation`.

---

### Task 6: Admin require/reset and the server reset command

**Files:**
- Modify: `backend/app/api/v1/two_factor_settings.py`, `Makefile`
- Create: `backend/app/scripts/reset_2fa.py`
- Test: `backend/tests/test_2fa_admin.py`

**Interfaces:**
- Consumes: `clear_all_mfa` (Task 1), `require_admin`, and `token_version` (the existing mechanism).
- Produces:
  - `PATCH /api/v1/users/{user_id}/2fa-required` with `{"required": bool}` → `UserResponse`. It's admin-only.
    - Targeting yourself → 400 "You can't change your own 2FA requirement here."
    - An unknown user → 404.
    - Setting `required=True` for an **un-enrolled** user does `token_version += 1`.
  - `POST /api/v1/users/{user_id}/2fa/reset` → `UserResponse`. It's admin-only.
    - Targeting yourself → 400 "You can't reset your own 2FA here."
    - Otherwise it calls `clear_all_mfa` and then `token_version += 1`.
  - `python -m app.scripts.reset_2fa <email>`: prints `2FA reset for <email>`, or for an unknown email prints `No user with email <email>` to stderr and exits 1. Same effect as the admin reset.
    - Structure it as `async def reset_2fa(session: AsyncSession, email: str) -> bool` plus a `main()`, so it can be tested.
  - A `Makefile` target, with `COMPOSE_FILE ?= docker-compose.dev.yml`:

    ```make
    reset-2fa:
    	docker compose -f $(COMPOSE_FILE) exec backend python -m app.scripts.reset_2fa "$(email)"
    ```

    Add a help line: `make reset-2fa email=...  Reset a user's 2FA (COMPOSE_FILE=docker-compose.yml for prod)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_require_is_admin_only`: a developer → 403.
  - `test_require_self_400`.
  - `test_require_unenrolled_bumps_token_version`: the old access cookie → 401 on `/me`.
  - `test_require_enrolled_keeps_sessions`: `token_version` is unchanged.
  - `test_unrequire_then_login_is_plain`: require, then unrequire, then a password login returns a user with cookies, not a challenge.
  - `test_reset_clears_methods_and_bumps_version`: `mfa_methods == []`, the credentials are deleted, `token_version` is incremented and the counters are reset.
  - `test_reset_self_400`.
  - `test_reset_keeps_required_flag`.
  - `test_cli_reset_2fa`: `await reset_2fa(db, user.email) is True` and the methods are cleared. An unknown email → False.

- [ ] **Step 2: Run the tests and confirm they fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the whole suite and confirm it passes.** Then run `make reset-2fa email=smoke@example.com` against the dev stack. Expected: `2FA reset for smoke@example.com`.
- [ ] **Step 5: Commit** with `feat(2fa): admin require/reset and reset-2fa command`.

---

### Task 7: Frontend login flow and the shared setup modal

**Files:**
- Modify: `frontend/package.json` (add `@simplewebauthn/browser`, `qrcode` and `@types/qrcode`, all with `--save-exact`), `frontend/src/app/(auth)/login/page.tsx`, `frontend/src/components/current-user-provider.tsx`
- Create: `frontend/src/lib/two-factor.ts`, `frontend/src/components/two-factor/totp-setup-modal.tsx`, `frontend/src/components/auth/login-second-step.tsx`

**Interfaces:**
- Consumes: the Task 3–5 routes.
- Produces, in `current-user-provider.tsx`: `CurrentUser` gains `mfa_required: boolean` and `mfa_methods: ("passkey" | "totp")[]`.
- Produces, in `lib/two-factor.ts`:
  - `type MfaChallenge = { mfa_required: "verify" | "setup"; methods: ("passkey" | "totp")[]; email: string }`.
  - `isMfaChallenge(x: unknown): x is MfaChallenge`.
  - `verifyLoginTotp(code: string): Promise<CurrentUser>`.
  - `verifyLoginPasskey(): Promise<CurrentUser>`. It fetches the options, calls `startAuthentication({ optionsJSON })` and posts the result.
  - `registerPasskey(optionsPath: string, finishPath: string, name: string): Promise<unknown>`. Used by both forced setup and the profile.
- Produces, in `totp-setup-modal.tsx`: `TotpSetupModal({ mode, onDone, onClose })`, where `mode` is `"login" | "profile"`.
  - Profile mode shows a "Current password" field first, then calls `/users/me/2fa/totp`.
  - Login mode calls `/auth/2fa/setup/totp` with no password.
  - The QR is rendered client-side with `QRCode.toDataURL(uri)` into an `<img alt="QR code for your authenticator app">`.
  - The secret is shown in groups of four, with a copy button.
  - The submit button reads "Verify and turn on".
- Produces, in `login-second-step.tsx`: `LoginSecondStep({ challenge, onSuccess, onRestart })`. It has internal steps `"choose" | "totp" | "passkey" | "setup"`.
  - With one method, it starts on that method; with both, on `"choose"`; with `"setup"`, on `"setup"`.
  - Use the copy and layout of mockup boards 1, 2a, 2b and "Required", inside the existing `.auth-card`.
  - Any 400 whose detail is "Your sign-in expired. Enter your password again." calls `onRestart`, which shows the password form again with that message.

- [ ] **Step 1: Read** `node_modules/next/dist/docs` for client components in `(auth)`, and the `@simplewebauthn/browser` README (`startRegistration({ optionsJSON })` and `startAuthentication({ optionsJSON })`).
- [ ] **Step 2: Implement.** In `login/page.tsx`, the response from `api.post("/api/v1/auth/login")` is checked with `isMfaChallenge`:
  - if it's a challenge, render `<LoginSecondStep>` in place of the form;
  - otherwise `router.push(redirectTo)` (unchanged).

  `onSuccess` also does `router.push(redirectTo)`.
- [ ] **Step 3: Run `tsc` and eslint on the touched files.** Expected: no errors in touched files.
- [ ] **Step 4: Check by hand** at http://localhost:3000. Restart the frontend container after adding the dependencies.
  - Log in as a user with TOTP: the code screen, a wrong code, then a correct code lands on the dashboard.
  - A required user goes through forced TOTP setup with a real authenticator app.
  - Passkey: on localhost, Chrome DevTools → WebAuthn → virtual authenticator.
- [ ] **Step 5: Commit** with `feat(2fa): login second step and forced setup UI`.

---

### Task 8: Profile → Security tab

**Files:**
- Create: `frontend/src/components/profile/security-settings.tsx`, `frontend/src/components/two-factor/confirm-password-dialog.tsx`
- Modify: `frontend/src/app/(dashboard)/profile/page.tsx`

**Interfaces:**
- Consumes: `TotpSetupModal` (profile mode), `registerPasskey` and `useCurrentUser`.
- Produces:
  - `ConfirmPasswordDialog({ title, confirmLabel, danger?, onConfirm(password): Promise<void>, onClose })`. It shows server errors such as "Password is incorrect" inline.
  - `SecuritySettings()`. It loads `GET /users/me/2fa` and renders the three cards from mockup "Profile → Security":
    - **Status card:** On/Off and "Required by admin" pills.
    - **Passkeys card:** a list with Rename (inline, no password) and Remove (with `ConfirmPasswordDialog`), plus "Add passkey" (`ConfirmPasswordDialog`, then a name prompt defaulting to the browser and OS, then `registerPasskey`).
    - **Authenticator app card:** Set up / Replace (`TotpSetupModal`) and Remove (`ConfirmPasswordDialog`).
  - After each change, call `setUser({...user, mfa_methods, mfa_required})` from the status response.
  - A Remove that would leave a required user with no method is disabled, with the title text "2FA is required for your account, so you must keep at least one method."
- In `profile/page.tsx`: add `{ key: "security", label: "Security", roles: all }` to `TABS`, between Account and Notifications. Update the subtitle to "Manage your personal details, password, security, notifications and API keys."

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Run `tsc` and eslint on the touched files.**
- [ ] **Step 3: Check by hand:**
  - Set up TOTP, replace it and remove it.
  - Add a passkey with the virtual authenticator, rename it and remove it.
  - Check the password prompts.
  - Check that removing the last method is disabled when required.
  - Check `?tab=security` and both themes.
- [ ] **Step 4: Commit** with `feat(2fa): profile security tab`.

---

### Task 9: Admin Users page and PRD

**Files:**
- Modify: `frontend/src/app/(dashboard)/users/page.tsx`, `docs/prd.md`

**Interfaces:**
- Consumes: the Task 6 routes. The user items now carry `mfa_required` and `mfa_methods`.
- Produces:
  - **A 2FA column**, placed after Role. Its pill reads:
    - "On · Passkey", "On · App" or "On · App + Passkey" (success colour);
    - "Off" (muted);
    - "Required · not set up" (warning colour), when required and `mfa_methods` is empty.
  - **A "2FA ▾" menu button** in Actions for every row except the current user's. Use the outside-click dropdown pattern from `components/notification-bell.tsx`. It contains:
    - a "Require 2FA" switch, with the hint "Must set it up at next sign-in", calling `PATCH /users/{id}/2fa-required`;
    - "Reset 2FA…", with a confirm step ("This removes all of <name>'s passkeys and authenticator app and signs them out."), calling `POST /users/{id}/2fa/reset`.
  - Both update the row from the response.
- `docs/prd.md`:
  - a "Two-factor authentication" subsection under Profile (§6.5.1): methods, login flow and limits;
  - the admin 2FA controls under the Users section;
  - `make reset-2fa` in the operations and commands area.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Run `tsc` and eslint on the touched files**, plus a production build on a copy in the container. Copy `node_modules` (don't symlink it), and set `NODE_ENV=production`. Expected: `/users` and `/profile` build.
- [ ] **Step 3: Check by hand as an admin:**
  - require for an un-enrolled user, whose session ends and who lands in forced setup at login;
  - reset an enrolled user;
  - no menu on your own row.
- [ ] **Step 4: Commit** with `feat(2fa): admin 2FA controls on users page; update PRD`.
