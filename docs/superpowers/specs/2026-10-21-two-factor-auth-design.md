# Two-factor authentication (TOTP + passkeys)

**Date:** 2026-10-21
**Status:** Draft, awaiting approval
**Mockups:** https://claude.ai/artifact/MBK9Z8Voizp7xSpdzaePfY (private to the repo owner). The top row is the login flow, which is clickable in Play. The bottom row shows the Profile → Security tab, the authenticator setup and the admin Users page.

## Why

Today a password alone gets you into MegooBug. The user wants an optional
second step after the password. There are two kinds:

- **TOTP:** a 6-digit code from an authenticator app.
- **Passkeys:** WebAuthn, using a fingerprint, face or security key.

Each user decides whether to turn 2FA on. An admin can require it for a
specific user.

## Goals

- **Setup:** any user can set up 2FA from a new **Profile → Security** tab.
  They can add one authenticator app, add one or more passkeys, or both.
- **Login:** after a correct password, a user with 2FA must finish a second
  step before they get a session.
  - If they have both methods, they choose one.
  - If they have one method, they go straight to it.
- **Requiring 2FA:** an admin can require 2FA for a user. A required user
  with no method must set one up during login before they get into the app.
- **Reset:** an admin can reset another user's 2FA, which removes all their
  methods. The user then signs in with just their password and sets 2FA up
  again later (or immediately, if it's still required).
- **Last-resort reset:** whoever runs the server can reset any account's 2FA
  with a command. This is for when the only admin is locked out.

## Non-goals

- **Backup / recovery codes.** The user chose admin reset as the recovery
  path.
- **Passwordless login.** A passkey is a second factor only; the password
  still comes first.
- **A global "require 2FA for everyone" switch.** Requiring is per user.
- **"Remember this device" / skipping 2FA on trusted browsers.**
- **SMS or email codes.**
- **2FA on API tokens (`mgb_…`).** Bearer API tokens keep working as they do
  today. They're for scripts, which can't do a second step. *(Claude's
  call, consistent with API keys surviving a password change.)*

## Anti-goals (would count as failure even if it "works")

- A correct password alone yields a full session for a user who has 2FA,
  or who is required to have it.
- **Lockout with no way back:** there must always be a path, via another
  admin or the server command.
- Deploying this logs out existing users, or forces 2FA on anyone who
  hasn't opted in and isn't required.
- A user who is required to have 2FA can remove their last method.
- Admins can reset their **own** 2FA from the Users page, which would bypass
  their own second factor. They manage it on their profile like anyone else.
- A stolen session alone (without the password) is enough to remove a
  user's 2FA, or to add the attacker's own passkey.
- A user marked "Required" goes on using the app without 2FA because their
  session keeps renewing.

## The screens (see the mockups)

### Login: second step (top row)

1. **Choose a method:** shown only when the user has both. The heading is
   "Verify it's you", with "Signed in as <email>" underneath. There are two
   large choices:
   - "Use a passkey: Fingerprint, face, or security key",
   - "Use authenticator app: Enter the 6-digit code from your app".

   Passkey is listed first *(Claude's call: it's quicker)*. A "Back to sign
   in" link is at the bottom.
2. **Authenticator app code:**
   - One numeric input with `autocomplete="one-time-code"`, and a "Verify"
     button.
   - "Use a passkey instead" shows only if the user has a passkey.
   - The note "Lost access? Ask an admin to reset your 2FA."
3. **Passkey:**
   - "Waiting for your passkey…" while the browser's WebAuthn prompt is open.
   - "Try again" if it was cancelled or failed.
   - "Use authenticator app instead" if the user has the app.
   - The same "Lost access?" note.
4. **Required, not set up:**
   - "Set up two-factor authentication: An admin requires 2FA for your
     account. Set up one method to continue."
   - "Add a passkey", or "Use an authenticator app" (which opens the same
     setup as the profile).
   - "Sign out".
   - Once one method is set up, the login completes.

These replace the login card's content in place on the existing `(auth)`
layout, with the same card styles as the login page.

### Profile → Security tab

A new tab between Account and Notifications, visible to every role. It's
reachable at `?tab=security`, following the existing pattern in
`profile/page.tsx`. It has three cards:

- **Status card:** "Two-factor authentication", with an **On** or **Off**
  pill, plus a **Required by admin** pill when it applies. The explanation
  text changes with the state.
- **Passkeys card:**
  - A list of passkeys, each with a name, an added date and a last-used
    date, plus **Rename** and **Remove**.
  - An **Add passkey** button, which runs WebAuthn registration and then
    asks for a name. The name defaults to something sensible, such as the
    browser or OS.
- **Authenticator app card:**
  - Not set up: a **Set up** button, which opens the setup modal.
  - Set up: the date it was set up, plus **Replace** (the same modal; the
    new secret replaces the old one only once it's verified) and **Remove**.

Removing a user's last method while 2FA is required for them is refused,
with a clear message. In the UI the button is disabled with an explanation.

**Password confirmation (decided by the user):** these actions ask for the
user's **current password** first, and the backend checks it on each of
those endpoints:
- adding a passkey,
- removing a passkey,
- setting up, replacing or removing the authenticator app.

This matches how `PATCH /users/me/password` works. Renaming a passkey
doesn't need it.

Forced setup during login is the exception: the password was entered
moments earlier, and the pending credential proves it.

The mockups don't show this password field yet. Put it at the top of the
setup modal, and in a small confirm dialog for Add passkey and Remove.

### Authenticator setup modal

1. "Scan this QR code with your app". The QR encodes a standard
   `otpauth://totp/…` URI, with issuer `MegooBug` and the user's email as the
   label.
2. The same secret as text (Base32, grouped in fours) with a copy button,
   for anyone who can't scan.
3. "Enter the 6-digit code it shows". Then **Verify and turn on**.
   - The secret is only saved once a correct code has been entered.
   - Cancelling discards it.

### Admin → Users page

- A new **2FA** column, showing **On · Passkey**, **On · App**, **On · App +
  Passkey**, **Off**, or **Required · not set up**.
- A **2FA ▾** menu in each row's Actions, except the admin's own row:
  - **Require 2FA**, a toggle. The hint reads "Must set it up at next
    sign-in". **Decided by the user:**
    - When it's turned on for a user who has **no** 2FA method, bump their
      `token_version`. That signs them out everywhere, and their next login
      goes into forced setup.
    - When the user is already enrolled, nothing is interrupted.
    - This is needed because `/auth/refresh` renews sessions without limit,
      so a "next login" might otherwise never happen.
  - **Reset 2FA…**, with a confirmation step. It removes all of the user's
    passkeys and their app secret. It doesn't change whether 2FA is
    required.

## Behaviour and rules

- **Who goes through the second step:** a user is "2FA-enrolled" when they
  have at least one passkey or a verified authenticator app.
  - An enrolled user always goes through the second step.
  - A required user who isn't enrolled goes through forced setup.
  - Everyone else logs in exactly as today.
- **Between password and second step:**
  - The backend issues **no** access or refresh cookies. Instead it issues
    a short-lived, single-purpose "2FA pending" credential, for example a
    signed HTTP-only cookie with `type: "mfa_pending"`, about a 5-minute
    expiry and the user id.
  - That credential only works on the 2FA verify endpoints (and, for forced
    setup, the setup endpoints).
  - Full cookies are issued with the existing
    `services/auth.py:issue_auth_cookies` once the second step succeeds.
- **The login response** tells the frontend which state the user is in:
  - logged in (as today),
  - second step needed, with the methods the user has,
  - setup required.

  The exact shapes are the builder's call.
- **Signup and accept-invite** log in directly as today. A new user has no
  2FA and isn't required to have it.
- **TOTP:**
  - RFC 6238, SHA-1, 6 digits, 30-second step. Accept ±1 step of clock drift.
  - **Reject reuse of a code** that has already been accepted for the same
    step (store the last accepted time step).
  - The secret is stored **encrypted at rest** with a key derived from
    `SECRET_KEY` *(Claude's call; how it's derived is the builder's choice)*.
- **Passkeys (WebAuthn):**
  - The Relying Party ID is the host of `APP_URL`, and the expected origin
    is `APP_URL`.
  - When adding a passkey, ask the browser to remember it on the device
    (resident key "preferred") and to check the user's fingerprint, face or
    PIN (user verification "preferred").
  - Store the credential id, public key, sign count, transports, name,
    created and last-used dates.
  - Check that the sign count is going up, as WebAuthn requires.
  - Note: browsers only allow WebAuthn on HTTPS or `localhost`. That fits
    the dev setup (`http://localhost:3000`) and production behind TLS.
- **Brute force (decided by the user):**
  - **Per pending credential:** after 5 failed second-step attempts, the
    credential is invalidated and the user must re-enter their password.
  - **Per account:** count consecutive failed second-step attempts across
    logins, in Redis or on the user row (the builder's call). After 5 in a
    row, each further attempt must wait, with the wait growing: 30 s, then
    1 min, 2 min, 4 min… capped at 15 min.
    - While waiting, the API refuses with a clear "Too many attempts, try
      again in X" message.
    - The counter resets on a successful second step, and on an admin reset
      or the server-command reset.
  - **No hard lock.** Someone who knows the password must never be able to
    lock the real user out for good.
- **Admin rules:**
  - Require/reset is admin-only and can't target the caller.
  - Resetting another user's 2FA also signs that user out of their other
    sessions, by bumping `token_version`. That's the existing mechanism from
    the profile-page work. *(Claude's call: a reset usually means a lost or
    stolen device.)*
- **Server command:**
  - A `make reset-2fa email=<email>` target, which runs a backend CLI inside
    the backend container. It removes the user's passkeys and app secret and
    bumps `token_version`.
  - It prints what it did, and gives a clear error for an unknown email.
  - It works against the production compose stack as well as dev. Today
    every operational Makefile target only uses `docker-compose.dev.yml`, so
    add a variable or a second target; the builder decides how.
  - It doesn't change "required". The user will be asked to set 2FA up
    again at their next login if it's still required.
- **No change to existing sessions on enable:** turning 2FA on doesn't sign
  anyone out. It applies from the next login.

## Data

All schema changes go through Alembic migrations chained after
`a7b8c9d0e1f2`:

- `users`: add
  - `mfa_required` (bool, not null, default false),
  - `totp_secret` (encrypted text, nullable),
  - `totp_enabled_at` (timestamptz, nullable),
  - `totp_last_step` (bigint, nullable).
- A new `webauthn_credentials` table:
  - `id`,
  - `user_id` (foreign key with cascade delete),
  - `credential_id` (unique, bytes or base64url),
  - `public_key`,
  - `sign_count`,
  - `transports` (JSON),
  - `name`,
  - `created_at`,
  - `last_used_at`.

Since there are no backup codes, the database needs nothing else.

## Libraries

These are Claude's calls, based on the existing stack:
- **Backend:** `pyotp` for TOTP and `webauthn` (py_webauthn) for passkeys.
  `cryptography` (Fernet) for encrypting the secret, if it isn't already
  available through existing dependencies.
- **Frontend:** `@simplewebauthn/browser` for the WebAuthn browser calls, and
  a small QR library (e.g. `qrcode`) to render the `otpauth://` URI on the
  client. That way the secret never travels to a third-party service.

Pin exact versions.

## API surface (shape left to the builder)

The builder decides the endpoints, but these capabilities are needed:

- **Login second step:**
  - verify a TOTP code,
  - get passkey authentication options,
  - verify a passkey assertion.
- **Forced setup during login:** the same setup actions as the profile,
  authorised by the pending credential.
- **Profile (current user):**
  - read 2FA status,
  - begin and confirm TOTP setup,
  - remove TOTP,
  - begin and finish passkey registration,
  - rename and remove a passkey.
- **Admin:**
  - set or unset "required" for a user,
  - reset a user's 2FA.
- **`GET /users/me` and the admin user list** expose what the UI needs:
  - whether 2FA is enrolled,
  - which methods are set up,
  - whether it's required.

## Testing

The backend suite runs on real Postgres (`backend/tests/conftest.py` has the
`user_client`, `make_user` and `cookie_header` fixtures from the profile
work). Cover at least:

- **Login:**
  - Without 2FA, login is unchanged and cookies are issued.
  - With 2FA, login issues **no** session cookies, only the pending
    credential.
  - The pending credential can't reach `/users/me` or anything else.
  - A correct TOTP code completes the login and sets cookies. A wrong code
    fails. A reused code fails.
  - The attempt limit invalidates the pending credential.
  - Per-account backoff: after 5 consecutive failures across fresh logins,
    the next attempt is refused with a wait time. The wait grows and caps at
    15 minutes. A success resets the counter.
- **Forced setup:** a required user with no method gets "setup required",
  can set up TOTP with the pending credential, and then gets a session.
- **Profile methods:**
  - Removing the last method while required is refused.
  - Adding, replacing or removing a method without the correct current
    password is refused. Renaming a passkey doesn't need the password.
  - TOTP setup only saves the secret after a valid code.
- **Admin:**
  - Turning on Require for an un-enrolled user bumps `token_version`, so
    their old cookies are rejected. For an enrolled user it doesn't.
  - require/reset is admin-only,
  - it refuses to target the caller,
  - reset removes the methods and bumps `token_version`.
- **Server command:** the CLI reset works, and an unknown email gives a
  clear error.
- **Passkeys:** test registration and authentication through
  py_webauthn's verification, with deterministic fixtures. Use a test
  credential/assertion pair, or mock only at the library boundary if
  generating real ones is impractical.

The frontend has no test runner. Verify it with `tsc`, lint on the touched
files, `next build`, and a manual click-through: TOTP with a real
authenticator app, and a passkey on localhost using the browser's virtual
authenticator or a real device.

## Left to the builder

- Exact endpoint paths, payloads and the pending-credential format, as long
  as the rules above hold.
- How the login page holds its step state (one page with steps, or
  sub-routes).
- Default passkey names, QR size and styling details. Follow the existing
  `.auth-card`, `.card`, `.btn` and pill styles, and use CSS variables, not
  hex colours.
- How the encryption key is derived from `SECRET_KEY`.

## Notes for the builder

- `frontend/AGENTS.md`: read `node_modules/next/dist/docs/` before writing
  frontend code (Next 16).
- **Dev environment:**
  - Node runs only in Docker.
  - A fresh database can't run the Alembic chain (an existing bug), so the
    dev DB was bootstrapped with `create_all` and `alembic stamp`.
  - The seeded `admin@megoobug.local` can't log in, because `EmailStr`
    rejects `.local`.
  - New route folders need a frontend container restart.
