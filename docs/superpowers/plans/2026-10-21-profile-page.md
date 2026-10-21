# User Profile Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/profile` page with three tabs: Account (details and password), Notifications, and API Keys. Make the header and sidebar avatars link to it, turn Settings into an admin-only page, and sign out a user's other logins when their password changes.

**Architecture:**
- **Backend:** add a `users.token_version` counter and stamp it into every JWT as a `tv` claim. A JWT whose `tv` differs from the user's counter is rejected. A missing claim counts as 0. A password change bumps the counter and re-issues cookies for the caller.
- **Frontend:** the dashboard layout exposes the current user through a React context, so the profile page can update the header and sidebar name. Notifications and API Keys move out of the Settings page into components that the profile page renders as tabs.

**Tech Stack:**
- **Backend:** FastAPI, SQLAlchemy 2 async, Alembic, pytest-asyncio and httpx (`ASGITransport`).
- **Frontend:** Next.js 16 App Router, React 19, lucide-react and global CSS (no Tailwind).

**Spec:** `docs/superpowers/specs/2026-10-21-profile-page-design.md`

## Global Constraints

- Everything runs in Docker. There is no Node on the host.
  - Backend tests: `docker compose -f docker-compose.dev.yml exec backend pytest`.
  - Frontend checks: `docker compose -f docker-compose.dev.yml exec frontend npx tsc --noEmit` and `docker compose -f docker-compose.dev.yml exec frontend npm run lint`.
- Before writing frontend code, read the relevant guide in the container's `/app/node_modules/next/dist/docs/` (see `frontend/AGENTS.md`). This includes `useSearchParams`, which needs a `<Suspense>` boundary.
- Style with the existing global classes and CSS variables only (`.card`, `.input`, `.label`, `.form-group`, `.btn`, `.btn-primary`, `.btn-secondary`, `.tabs`, `.tab`, `.user-avatar`). No hex literals. Both themes must work.
- Password rules: 8–128 characters (existing `PasswordUpdate`). The new password must differ from the current one.
- API tokens (`mgb_…`, the Bearer auth in `_get_user_from_bearer`) are **not** affected by a password change.
- A JWT without a `tv` claim is treated as `tv == 0`, so users who are logged in when this deploys stay logged in.
- Copy, verbatim from the spec:
  - Page subtitle: "Manage your personal details, password, notifications and API keys."
  - Details hint: "Your name appears on issues, comments and team pages."
  - Password hint: "Use at least 8 characters. Changing it signs you out everywhere else. API keys keep working."
  - Mismatch error: "Passwords don't match"
  - Wrong-password error: "Current password is incorrect"
  - Tab labels: "Account", "Notifications", "API Keys"
  - Header avatar `aria-label` and `title`: "Your profile"
- The profile tab param is `?tab=account|notifications|apikeys`, defaulting to `account`.

## Review Focus

1. **The changer stays signed in.** After `PATCH /me/password`, the response's new cookies must authenticate `/me`, and the frontend must not bounce to `/login`. Pinned in Task 2 (`test_password_change_keeps_caller_signed_in`).
2. **Refresh with an old refresh token after the change.** Another browser's 401 → `/auth/refresh` must fail, so it lands on login instead of silently getting fresh tokens. Pinned in Task 2 (`test_old_refresh_token_rejected_after_password_change`).
3. **A role-hidden tab via the URL.** A viewer opening `/profile?tab=apikeys` must see Account, never an empty pane. Pinned in Task 4, step 6 (manual check; there's no frontend test runner).
4. **Whitespace-only name.** `"   "` must be rejected by the API, not saved as a blank name that breaks the avatar initial. Pinned in Task 2 (`test_patch_me_rejects_blank_name`).
5. **Admin opens `/settings` before the user loads.** The redirect must wait for the user from context and never send an admin to `/profile`. Pinned in Task 4, step 6 (manual check as an admin, with a hard reload on `/settings`).

---

## File Structure

**Backend**
- Modify `backend/app/models/user.py`: add the `token_version` column.
- Create `backend/alembic/versions/a7b8c9d0e1f2_add_user_token_version.py`.
- Modify `backend/app/services/auth.py`:
  - tokens carry `tv`,
  - add `token_version_matches`,
  - add `issue_auth_cookies` (moved from `_set_auth_cookies` in `api/v1/auth.py`).
- Modify `backend/app/api/v1/auth.py`: use `issue_auth_cookies`, and check `tv` in `/refresh`.
- Modify `backend/app/dependencies.py`: check `tv` in `_get_user_from_cookie`.
- Modify `backend/app/api/websocket.py`: check `tv` in `_authenticate_ws`.
- Modify `backend/app/schemas/user.py`: trim and validate `name` in `UserUpdate`.
- Modify `backend/app/api/v1/users.py`: password change bumps the version, re-issues cookies and returns `MessageResponse`.
- Create `backend/tests/test_token_version.py`: unit tests and auth-flow HTTP tests.
- Create `backend/tests/test_users_me.py`: `PATCH /me` and `PATCH /me/password` HTTP tests.

**Frontend**
- Modify `frontend/src/lib/api.ts`: readable messages from an array `detail`.
- Create `frontend/src/components/current-user-provider.tsx`: the context and the hook.
- Modify `frontend/src/app/(dashboard)/layout.tsx`: provide the context.
- Modify `frontend/src/components/header.tsx` and `frontend/src/components/sidebar.tsx`: the profile links, their active states, and Settings marked `adminOnly`.
- Modify `frontend/src/app/globals.css`: active-state styles for the two links.
- Create `frontend/src/components/profile/notification-preferences.tsx`, moved from Settings.
- Create `frontend/src/components/profile/api-keys.tsx`, moved from Settings, including its Create Token modal.
- Create `frontend/src/components/profile/account-forms.tsx`: the Personal details and Password cards.
- Create `frontend/src/app/(dashboard)/profile/page.tsx`: the banner, the tabs and `?tab=`.
- Modify `frontend/src/app/(dashboard)/settings/page.tsx`: keep only General and SMTP, and redirect non-admins.
- Modify `docs/prd.md`.

---

### Task 1: Token version: column, claim and enforcement

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/alembic/versions/a7b8c9d0e1f2_add_user_token_version.py`
- Modify: `backend/app/services/auth.py`, `backend/app/api/v1/auth.py`, `backend/app/dependencies.py`, `backend/app/api/websocket.py`
- Test: `backend/tests/test_token_version.py`, `backend/tests/conftest.py` (shared HTTP fixtures)

**Interfaces:**
- Produces, in `app/services/auth.py`:
  - `create_access_token(user_id: uuid.UUID, role: str, token_version: int) -> str`. Adds `"tv": token_version` to the payload. `token_version` is a required parameter, so a missed call site fails loudly.
  - `create_refresh_token(user_id: uuid.UUID, token_version: int) -> str`. Adds the same `tv` claim.
  - `token_version_matches(payload: dict, user: User) -> bool`. Returns `payload.get("tv", 0) == user.token_version`.
  - `issue_auth_cookies(response: Response, user: User) -> None`. Creates both tokens from `user.id`, `user.role.value` and `user.token_version`, then sets them with the cookie settings currently in `_set_auth_cookies`: same names, flags, `max_age` and `path="/"`. Delete `_set_auth_cookies` from `api/v1/auth.py`.
- Produces: `User.token_version: Mapped[int]`, with `nullable=False, default=0, server_default="0"`.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_token_version.py`.

  **HTTP fixtures**, used here and in Task 2. Put them in `tests/conftest.py` so Task 2 can reuse them:
  - `user_client(db)` (named so it does not clash with the local `api_client` fixture in `test_ingest_pipeline.py`):
    - Set `app.dependency_overrides[get_db]` to an async generator that yields the test `db` session.
    - Yield an `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`.
    - Clear the override afterwards.
  - `make_user(db)`: a factory `async (password="correct-horse-1", role=UserRole.DEVELOPER) -> User`.
    - Adds a `User` with a unique `f"{uuid4().hex}@example.com"`, `name="Test User"` and `hash_password(password)`.
    - Flushes and returns it.
  - Helper `cookie_header(access: str | None = None, refresh: str | None = None) -> dict`. Returns `{"Cookie": "access_token=…; refresh_token=…"}` with only the cookies that were given.
  - **Cookie handling rule:** always send cookies through this explicit header, and call `client.cookies.clear()` after reading `resp.cookies`. The httpx cookie jar must never carry auth between simulated browsers.

  Unit tests:
  - `test_access_token_carries_tv`: `decode_token(create_access_token(uid, "developer", 3))["tv"] == 3`.
  - `test_refresh_token_carries_tv`: the same for `create_refresh_token(uid, 3)`.
  - `test_token_version_matches_missing_claim_is_zero`: with a user at `token_version=0`, `{"sub": "x"}` → True. With `token_version=1`, the same payload → False.
  - `test_token_version_matches_mismatch`: `{"tv": 1}` against a user at `token_version=2` → False.

  HTTP tests:
  - `test_login_sets_cookies_that_authenticate`: login via `POST /api/v1/auth/login`. `GET /api/v1/users/me` with those cookies → 200.
  - `test_legacy_access_token_without_tv_accepted`:
    - Encode a payload by hand with `jose.jwt.encode`, using `settings.SECRET_KEY` and `settings.JWT_ALGORITHM`: `{"sub": str(user.id), "role": "developer", "type": "access", "exp": now + 5 minutes}`, with no `tv`.
    - `GET /me` with that token → 200.
  - `test_stale_access_token_rejected`:
    - Issue an access token with `tv=0`.
    - Set `user.token_version = 1` and flush.
    - `GET /me` → 401.
  - `test_stale_refresh_token_rejected`: the same, with a refresh token sent to `POST /api/v1/auth/refresh` → 401.
  - `test_refresh_issues_tokens_with_current_tv`:
    - Set the user to `token_version=2`.
    - Refresh with a token issued at `tv=2` → 200.
    - Decoding the new `access_token` cookie gives `tv == 2`.

- [ ] **Step 2: Run the tests and confirm they fail**

  Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_token_version.py -v`
  Expected: FAIL. You'll see `TypeError` (extra positional argument), `ImportError` for `token_version_matches`, and `AttributeError` for `token_version`.

- [ ] **Step 3: Add the column and the migration**
  - Add `User.token_version` as described under Interfaces.
  - Write the migration file. It's `revision='a7b8c9d0e1f2'` with `down_revision='f6a7b8c9d0e1'` and follows the style of `b2c3d4e5f6g7_add_notification_preferences.py`.
    - `upgrade`: `op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))`.
    - `downgrade`: drop the column.

- [ ] **Step 4: Implement the service functions** in `app/services/auth.py`, as listed under Interfaces.

- [ ] **Step 5: Wire up enforcement**
  - `api/v1/auth.py`: login, signup and accept-invite call `issue_auth_cookies(response, user)`. In `/refresh`, after the user is loaded and found active, reject `not token_version_matches(payload, user)` with the existing 401 "Invalid refresh token". Then call `issue_auth_cookies`.
  - `dependencies.py:_get_user_from_cookie`: return `None` when the token doesn't match.
  - `websocket.py:_authenticate_ws`: return `None` when the token doesn't match.

- [ ] **Step 6: Run the new tests, then the whole suite, and confirm they pass**

  Run: `docker compose -f docker-compose.dev.yml exec backend pytest -v`
  Expected: all PASS, including the existing suites.

- [ ] **Step 7: Check that the migration applies**

  Run: `docker compose -f docker-compose.dev.yml exec backend alembic upgrade head`, then `alembic current`.
  Expected: `a7b8c9d0e1f2 (head)`.

- [ ] **Step 8: Commit**

  ```bash
  git add backend/app backend/alembic/versions/a7b8c9d0e1f2_add_user_token_version.py backend/tests
  git commit -m "feat(auth): stamp token_version into JWTs and reject stale tokens"
  ```

---

### Task 2: Password change signs out other sessions; name trimming

**Files:**
- Modify: `backend/app/api/v1/users.py` (`update_password`, at around lines 75–90)
- Modify: `backend/app/schemas/user.py` (`UserUpdate`)
- Test: `backend/tests/test_users_me.py`

**Interfaces:**
- Consumes, from Task 1: `issue_auth_cookies(response, user)`, `create_access_token(…, token_version)`, `create_refresh_token(…, token_version)`, and the `user_client`, `make_user` and `cookie_header` fixtures and helpers.
- Produces:
  - `PATCH /api/v1/users/me/password` with `response_model=MessageResponse`.
    - Body: `{"message": "Password updated"}`.
    - Sets new `access_token` and `refresh_token` cookies.
    - Errors are 400s with `detail` set to "Current password is incorrect" or "New password must be different from the current password".
  - `UserUpdate.name`: stripped, and `max_length=255` still applies. A value that is empty after stripping → 422. `None` still means "unchanged".

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_users_me.py`. Each one logs in via `/auth/login` to get cookies.

  - `test_patch_me_trims_name`: `PATCH /me {"name": "  Alex Morgan  "}` → 200, and `json()["name"] == "Alex Morgan"`.
  - `test_patch_me_rejects_blank_name`: `{"name": "   "}` → 422, and the user's name is unchanged in the DB.
  - `test_patch_me_duplicate_email_409`: use another user's email → 409, with `detail == "Email already in use"`.
  - `test_password_wrong_current_400`: → 400, with `detail == "Current password is incorrect"`.
  - `test_password_same_as_current_400`: `new_password == current_password` → 400, with `detail == "New password must be different from the current password"`.
  - `test_password_change_bumps_version_and_sets_cookies`:
    - → 200 and `json() == {"message": "Password updated"}`.
    - Both cookies are present on the response.
    - After `db.refresh(user)`, `user.token_version == 1`.
  - `test_password_change_keeps_caller_signed_in`: `GET /me` with the new cookies from the change response → 200.
  - `test_old_access_token_rejected_after_password_change`: `GET /me` with the pre-change access cookie → 401.
  - `test_old_refresh_token_rejected_after_password_change`: `POST /auth/refresh` with the pre-change refresh cookie → 401.
  - `test_login_with_new_password_after_change`: `/auth/login` with the new password → 200, and with the old one → 401.
  - `test_api_token_survives_password_change`:
    - Before the change, create an `ApiToken` for the user from `generate_api_token()` (`app/services/token.py`), then flush.
    - After the change, `GET /me` with `Authorization: Bearer <raw>` and no cookies → 200.

- [ ] **Step 2: Run the tests and confirm they fail**

  Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_users_me.py -v`
  Expected: FAIL. These fail: trim, blank name, same password, bump/cookies, keeps-caller-signed-in, old-access-token and old-refresh-token. These already pass: wrong password, 409, login with new password, API token.

- [ ] **Step 3: Implement**
  - `UserUpdate`: a `field_validator("name")` that strips the value and raises `ValueError("Name cannot be empty")` when the result is empty.
  - `update_password(data, response: Response, current_user, db)`:
    - Verify the current password (unchanged).
    - Reject a new password where `verify_password(data.new_password, current_user.password_hash)` is true.
    - Set the hash, then `current_user.token_version += 1` and `await db.flush()`.
    - Call `issue_auth_cookies(response, current_user)` and return `MessageResponse`.

- [ ] **Step 4: Run the whole backend suite and confirm it passes**

  Run: `docker compose -f docker-compose.dev.yml exec backend pytest -v`
  Expected: all PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add backend/app/api/v1/users.py backend/app/schemas/user.py backend/tests/test_users_me.py
  git commit -m "feat(users): password change signs out other sessions; trim profile name"
  ```

---

### Task 3: Current-user context, avatar links and readable API errors

**Files:**
- Create: `frontend/src/components/current-user-provider.tsx`
- Modify: `frontend/src/app/(dashboard)/layout.tsx`, `frontend/src/components/header.tsx`, `frontend/src/components/sidebar.tsx`, `frontend/src/lib/api.ts`, `frontend/src/app/globals.css`

**Interfaces:**
- Produces, in `current-user-provider.tsx` (a `"use client"` file):
  - `export interface CurrentUser { id: string; name: string; email: string; role: "admin" | "developer" | "viewer"; created_at: string; }`
  - `export function CurrentUserProvider({ user, onUserChange, children }: { user: CurrentUser; onUserChange: (u: CurrentUser) => void; children: React.ReactNode })`
  - `export function useCurrentUser(): { user: CurrentUser; setUser: (u: CurrentUser) => void }`. It throws outside the provider.
- Produces, in `api.ts`: `ApiError.message` is always a string. When `detail` is an array, use the first entry's `msg`, with Pydantic's "Value error, " prefix stripped. When it's a string, use it. Otherwise use `response.statusText`. Apply the same rule on the retry path, which currently passes raw text.

- [ ] **Step 1: Implement the provider** and wrap the layout's content in it. The layout keeps owning `useState<CurrentUser>`; drop its local interface and import the type. Header and Sidebar keep their props, now read from the same state, so a `setUser` re-renders them.

- [ ] **Step 2: Update the header** (`header.tsx`):
  - Replace the avatar `div` with `<Link href="/profile" className="user-avatar" aria-label="Your profile" title="Your profile">`.
  - Use `usePathname()`. When the path starts with `/profile`, add `aria-current="page"` and the class `active`.

- [ ] **Step 3: Update the sidebar** (`sidebar.tsx`):
  - Set `{ label: "Settings", …, adminOnly: true }`.
  - Wrap the footer's avatar, name and role in one `<Link href="/profile" className="sidebar-user-link">`. When the path starts with `/profile`, add `active` and `aria-current="page"`.
  - On click, call `onMobileClose()`, as the nav links do.
  - The collapsed state still renders the avatar inside the link.
  - The logout button stays outside the link.

- [ ] **Step 4: Add the active-state CSS** in `globals.css`, next to `.user-avatar` (around line 787):
  - `.user-avatar.active`: a 2px ring in `var(--accent-primary)` with a gap in `var(--bg-primary)`.
  - `.sidebar-user-link`: inherits colour, no underline. `.active` uses the same background and colour treatment as the sidebar's active nav item (copy that rule's variables).

- [ ] **Step 5: Update `api.ts` error messages** as described under Interfaces.

- [ ] **Step 6: Check types and lint**

  Run: `docker compose -f docker-compose.dev.yml exec frontend npx tsc --noEmit && docker compose -f docker-compose.dev.yml exec frontend npm run lint`
  Expected: no errors.

- [ ] **Step 7: Check manually** at http://localhost:3000 (dev stack running):
  - Clicking the header avatar and the sidebar user block both navigate to `/profile`. A 404 is fine until Task 4.
  - Settings is hidden for a developer and visible for an admin.

- [ ] **Step 8: Commit**

  ```bash
  git add frontend/src
  git commit -m "feat(ui): current-user context, avatar links to profile, readable API errors"
  ```

---

### Task 4: Profile page with tabs; move Notifications and API Keys; admin-only Settings

**Files:**
- Create: `frontend/src/app/(dashboard)/profile/page.tsx`
- Create: `frontend/src/components/profile/notification-preferences.tsx`, `frontend/src/components/profile/api-keys.tsx`
- Modify: `frontend/src/app/(dashboard)/settings/page.tsx`

**Interfaces:**
- Consumes: `useCurrentUser()` from Task 3.
- Produces:
  - `export function NotificationPreferences()`. It's self-contained, loads on mount, and is the current settings code at lines 64–83, 186–224 and 551–765, moved unchanged.
  - `export function ApiKeys()`. It's self-contained, with the token table, empty state and Create Token modal, and is the current code at lines 55–63, 112–120, 243–281 and the API Keys JSX, moved unchanged.
  - `profile/page.tsx` renders `<AccountForms />` from Task 5. Until then, render a placeholder `<div className="card">` so this task stands alone, and replace it in Task 5.

- [ ] **Step 1: Move the code.** Cut the Notifications and API Keys code into the two components, keeping their behaviour exactly: auto-save on toggle with revert on failure, the "Preferences saved" message, the show-once token and the copy button.

- [ ] **Step 2: Build the profile page.**
  - A `"use client"` page whose tab-reading part is wrapped in `<Suspense>` (see the Next docs).
  - Page header: title "Profile", with the subtitle from Global Constraints.
  - **Summary banner** `.card`:
    - A 72px `.user-avatar`, with its size set on the element.
    - Name, with a role pill (`Admin`, `Developer` or `Viewer`).
    - Email in muted text.
    - "Member since" and `new Date(user.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })`.
  - **Tabs:** `.tabs` with Account, Notifications, and API Keys (only when the role is `admin` or `developer`).
    - The active tab comes from `useSearchParams().get("tab")`, resolved against the visible tabs. An unknown or hidden tab, or no param, gives `account`.
    - Clicking a tab calls `router.replace(\`/profile?tab=${key}\`, { scroll: false })`.

- [ ] **Step 3: Trim Settings to General and SMTP.**
  - Delete the `profile`, `notifications` and `apikeys` tabs, their state and handlers, the local `/me` fetch, and the unused imports.
  - Take `role` from `useCurrentUser().user.role`, and set the default `activeTab` to `"general"`.
  - When `role !== "admin"`, call `router.replace("/profile")` in an effect, and render nothing until it redirects.

- [ ] **Step 4: Check types and lint** (the same command as Task 3, step 6). Expected: no errors.

- [ ] **Step 5: Check the moved tabs** as a developer.
  - Toggling a notification switch persists across a reload.
  - Creating a token shows it once and copy works. Revoking removes it.

- [ ] **Step 6: Check the Review Focus cases manually:**
  - As a viewer, `/profile?tab=apikeys` shows Account, and the API Keys tab isn't shown.
  - As a viewer or developer, `/settings` lands on `/profile`.
  - As an admin, a hard reload on `/settings` stays on Settings with General and Email/SMTP.
  - `/profile?tab=notifications` opens on Notifications.
  - Do this in both themes.

- [ ] **Step 7: Commit**

  ```bash
  git add frontend/src
  git commit -m "feat(profile): profile page with tabs; move notifications and API keys out of settings"
  ```

---

### Task 5: Account tab (details and password) and PRD

**Files:**
- Create: `frontend/src/components/profile/account-forms.tsx`
- Modify: `frontend/src/app/(dashboard)/profile/page.tsx` (replace the placeholder)
- Modify: `docs/prd.md`

**Interfaces:**
- Consumes: `useCurrentUser()` from Task 3, which gives `{ user, setUser }`, and `api` and `ApiError`.
- Produces: `export function AccountForms()`.

- [ ] **Step 1: Build the Personal details card.**
  - lucide `User` icon heading and the details hint.
  - "Full name" and "Email" (`type="email"`, `required`) fields, seeded from `user`.
  - On submit:
    - Trim the name. If it's empty, show "Name is required" locally and don't send anything.
    - Otherwise `api.patch<CurrentUser>("/api/v1/users/me", { name, email })`, then `setUser(response)` and a green "Profile updated" message with a Check icon.
    - On failure, show the error in red with an AlertTriangle icon: `err.message` for an `ApiError`, otherwise "Something went wrong. Please try again."
  - The button reads "Save changes", or "Saving..." while the request is in flight.

- [ ] **Step 2: Build the Password card.**
  - lucide `Lock` icon heading and the password hint.
  - "Current password", "New password" and "Confirm new password" fields, all `type="password"`, with `autoComplete` set to `current-password`, `new-password` and `new-password`.
  - New password: `minLength={8}` and `maxLength={128}`.
  - Before sending, if the confirm box doesn't match the new password, show "Passwords don't match".
  - On success, clear all three fields and show "Password updated".
  - Errors are handled as in step 1.
  - The button uses `btn btn-secondary` and reads "Update password".

- [ ] **Step 3: Render `<AccountForms />`** for the Account tab, replacing the placeholder.

- [ ] **Step 4: Update `docs/prd.md`** following the spec's Docs section:
  - §6.5 Settings: admin-only, with General and Email/SMTP only.
  - A new Profile section.
  - The sidebar description (around line 313) and the nav list (around line 853).
  - "Settings → API Keys" becomes "Profile → API Keys" (around lines 516 and 604–606).

- [ ] **Step 5: Check types and lint**. Expected: no errors.

- [ ] **Step 6: Check manually:**
  - Saving `"  New Name  "` updates the header avatar initial and the sidebar name without a reload.
  - A blank name is blocked.
  - A duplicate email shows "Email already in use".
  - A wrong current password shows "Current password is incorrect".
  - Mismatched confirm shows "Passwords don't match".
  - A successful change keeps this browser on `/profile`. A second browser logged in as the same user is sent to `/login` on its next action.

- [ ] **Step 7: Commit**

  ```bash
  git add frontend/src docs/prd.md
  git commit -m "feat(profile): account tab with details and password forms; update PRD"
  ```
