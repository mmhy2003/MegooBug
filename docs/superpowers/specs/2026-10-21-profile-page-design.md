# User profile page

**Date:** 2026-10-21
**Status:** Draft, awaiting approval
**Mockup:** https://claude.ai/artifact/WUruPFqkP7tUBSusnkwCqT. The approved layout is board **"C · B with tabs"**, which is clickable in Play mode. The link is private to the repo owner.

## Why

Today a user's own things are spread across Settings tabs: Profile (name and
email), Notifications and API Keys. Those tabs sit next to the admin-only
instance settings. Nothing in the UI uses the existing change-password
endpoint.

The avatar in the header and the avatar and name in the sidebar look
clickable: the header avatar has `cursor: pointer` and a hover glow. Clicking
them does nothing.

The user wants one obvious place for everything personal: a Profile page,
reached by clicking their avatar. The personal tabs move there, and Settings is
left for instance-wide admin settings. They also want a password change to
sign out the user's other logins.

## Goals

- A new `/profile` page inside the dashboard shell. Every role (admin,
  developer, viewer) can:
  - see an account summary,
  - edit their full name and email,
  - change their password,
  - manage notification preferences,
  - manage API keys (admin and developer only, as today).
- The header avatar and the sidebar avatar+name block link to `/profile`.
- The Profile, Notifications and API Keys tabs move out of Settings. Settings
  keeps only General and Email/SMTP, and becomes admin-only.
- After saving a new name or email, the header and sidebar show the new value
  straight away, with no reload.
- Changing the password signs out every other login for that user. The browser
  that made the change stays logged in.

## Non-goals

- Avatar image upload. The avatar stays as the first letter of the name on the
  existing gradient (`.user-avatar`). `avatar_url` stays unused.
- Email re-verification, or asking for the password when the email changes.
  Email editing behaves as it does today.
- A "Profile" entry in the sidebar nav list. The only ways in are the two
  avatar links, plus the URL.
- A dropdown menu on the header avatar. A click goes straight to `/profile`.
- Revoking API tokens (`mgb_…`) on password change. **The user decided:** API
  keys keep working after a password change. The Password card says so.
- Any change to how notification preferences or API tokens behave. They move
  as they are.
- Password strength rules beyond the backend's existing 8–128 characters.

## Anti-goals (would count as failure even if it "works")

- Changing the password logs out the user who made the change.
- Deploying this logs out every user who is already signed in.
- The name in the header or sidebar stays stale after a successful save.
- Admins lose General or Email/SMTP, or those tabs change behaviour.
- Notification preferences or API key create/copy/revoke work differently
  after the move.

## The page (layout C)

Path: `frontend/src/app/(dashboard)/profile/page.tsx`. It gets the dashboard
layout, sidebar, header and auth guard automatically.

The page is one centred column, about 820px wide, that stacks naturally on
phones. From top to bottom:

1. **Page header.**
   - Title "Profile", in the existing `.page-title` style.
   - Muted subtitle "Manage your personal details, password, notifications
     and API keys."
2. **Summary banner card.**
   - Large avatar initial (about 72px) on the existing gradient.
   - Name, with a role pill beside it (Admin / Developer / Viewer).
   - Email below the name, in muted text.
   - "Member since" and the date, aligned right, from `created_at`.
3. **Tab bar**, using the existing `.tabs` / `.tab.active` styles:
   **Account | Notifications | API Keys**.
   - API Keys only shows for admin and developer, as today.
   - The active tab is in the URL as `?tab=account|notifications|apikeys`.
     Account is the default when the param is missing.
   - An unknown tab, or one the user's role can't see, falls back to Account.
     *(Claude's call: makes tabs linkable.)*
4. **Tab content:**
   - **Account:**
     - **Personal details card.**
       - Heading with a lucide `User` icon in the primary colour, and the
         hint "Your name appears on issues, comments and team pages."
       - Fields: "Full name", and "Email" (`type="email"`), stacked full width.
       - A primary "Save changes" button.
       - An inline status line beside the button: green with a check icon on
         success, red with an alert icon on error.
     - **Password card.**
       - Heading with a lucide `Lock` icon, and the hint "Use at least 8
         characters. Changing it signs you out everywhere else. API keys keep
         working."
       - Fields, stacked: "Current password", "New password", "Confirm new
         password". All are `type="password"` with matching `autocomplete`
         values.
       - An outlined (`.btn-secondary`) "Update password" button and an inline
         status line.
       - The fields clear after a successful change.
   - **Notifications:** the existing Notifications tab content from Settings,
     moved as is. That means the same three event types, the in-app and email
     toggles, auto-save on toggle, revert on failure, and the "Preferences
     saved" message.
   - **API Keys:** the existing API Keys tab content from Settings, moved as
     is. That means the token table, the empty state, the Create Token modal
     with show-once and copy, and revoke.

Build it from the existing global classes (`.card`, `.input`, `.label`,
`.form-group`, `.btn .btn-primary`, `.btn .btn-secondary`, `.tabs`, `.tab`,
`.user-avatar`) and the CSS variables, so light and dark themes both work.
Follow the richer card style already used on the Notifications tab: a header
icon in the accent colour, a muted subtitle, and status messages with Check /
AlertTriangle icons. The mockup's hex values stand in for the CSS variables;
don't copy them as literals.

## Entry points

- **Header** (`frontend/src/components/header.tsx`): the `.user-avatar` div
  becomes a Next `<Link href="/profile">`, with `aria-label="Your profile"` and
  `title="Your profile"`. On `/profile` it shows an active state: a ring in
  `--accent-primary`.
- **Sidebar** (`frontend/src/components/sidebar.tsx`): the footer's avatar,
  name and role become one `<Link href="/profile">`. On `/profile` it uses the
  same active styling as an active nav item. The logout button stays a
  separate button beside it.
  - When the sidebar is collapsed, only the avatar shows, and it is still the
    link.
  - On mobile, clicking it closes the drawer, as nav links already do.

## Settings becomes admin-only

In `frontend/src/app/(dashboard)/settings/page.tsx`:

- Remove the `profile`, `notifications` and `apikeys` tabs, with their state,
  loaders and handlers. Move the Notifications and API Keys code to the
  profile page. General and Email/SMTP stay untouched.
- The page's own `/me` fetch currently supplies the role used to filter the
  tabs (`const userRole = profile?.role || "viewer"`, around line 292). Take
  the role from the new user context instead (below). The default `activeTab`
  is currently `"profile"`; change it to `"general"`.
- A non-admin who opens `/settings` is redirected to `/profile`, with
  `router.replace` once the user is known. This is a frontend redirect only.
  The backend settings endpoints are already admin-gated; confirm that while
  building.

In `frontend/src/components/sidebar.tsx`, mark the Settings nav item
`adminOnly: true`. The `adminOnly` flag already exists and is used for Users.

## Keeping the header and sidebar in sync

Today `(dashboard)/layout.tsx` holds the current user in local `useState` and
passes `name` and `role` down as props, so other pages can't update it.

Expose the user through a small React context provided by that layout. It
should offer the current user and a way to replace it after a successful
`PATCH /me`. The profile page and the settings page read the user (and role)
from it instead of fetching `/me` again. The profile page writes the server's
response back into it, so the header and sidebar re-render with the new name.

Extend the layout's `CurrentUser` type with `email` and `created_at`, which the
banner needs. `GET /me` already returns both.

## Backend changes

### Profile update (`PATCH /api/v1/users/me`)

- Trim `name`. Reject an empty name after trimming with a 422. The admin-only
  `PATCH /{id}/name` already trims; match its behaviour.
- Everything else is unchanged: a duplicate email still returns 409 "Email
  already in use".

### Password change (`PATCH /api/v1/users/me/password`)

Existing behaviour stays: a wrong current password gives a 400 "Current
password is incorrect". Add:

- **New password must differ from the current one.** Return a 400 with a clear
  message.
- **Sign out other logins.** Today JWTs are stateless: access tokens last 30
  minutes, refresh tokens 7 days, and nothing on the user record can invalidate
  them. Add a version counter to the user and stamp it into every token:
  - New column `users.token_version` (int, not null, default 0), added with an
    Alembic migration. Follow the pattern in
    `alembic/versions/b2c3d4e5f6g7_add_notification_preferences.py`. Its
    `down_revision` is the current head, `f6a7b8c9d0e1`.
  - `create_access_token` and `create_refresh_token` include a `tv` claim set
    to the user's current `token_version`. Update every call site: login,
    signup, refresh, accept-invite.
  - Every place that accepts a JWT rejects it when the claim doesn't match
    the user's `token_version`:
    - the cookie dependency (`dependencies.py:_get_user_from_cookie`),
    - the refresh endpoint (`auth.py:/refresh`),
    - WebSocket auth (`api/websocket.py:_authenticate_ws`).
  - **A token without a `tv` claim counts as version 0.** Users who are
    already logged in when this deploys stay logged in.
  - On a successful password change: increment `token_version`, then issue new
    access and refresh cookies for the current response using
    `_set_auth_cookies`. The browser that made the change stays signed in, and
    every other session fails on its next request or refresh.
    `_set_auth_cookies` lives in `auth.py`; move or share it as you see fit.
  - API tokens (`_get_user_from_bearer`) are deliberately **not** affected.
- Return a proper response model (e.g. the existing `MessageResponse`) instead
  of a bare `dict`.

WebSocket connections that are already open are only checked on (re)connect,
so another session's live socket can keep running until it reconnects. That
is acceptable: its next HTTP call fails and the frontend sends it to login.

## Frontend error handling

`api.ts` passes `errorBody.detail` straight into `ApiError`. For a Pydantic 422
that's an array, which shows up as "[object Object]". Turn an array `detail`
into a readable message (e.g. the first entry's `msg`). Show a generic fallback
for non-`ApiError` failures in the new profile forms, instead of the silent
nothing that happens today.

Checks the Account tab does in the browser before sending anything:

- Name: required, trimmed.
- Email: required, `type="email"`.
- New password: at least 8 characters.
- Confirm password must match the new password, or show "Passwords don't
  match".

## Docs

Update `docs/prd.md` to match:

- §6.5 Settings: admin-only, with General and Email/SMTP only.
- Add a Profile section: Account, Notifications and API Keys.
- The sidebar description around line 313, and the nav list around line 853:
  Settings is admin-only, and the avatar links to the profile.
- Change "Settings → API Keys" to "Profile → API Keys" around lines 516 and
  604–606.

## Testing

The backend has a pytest suite against a real Postgres DB
(`backend/tests/conftest.py`), but nothing yet covers `/users/me` or the auth
routes. Add tests for:

- `PATCH /me`:
  - trims the name,
  - rejects a blank name,
  - returns 409 on a duplicate email.
- `PATCH /me/password`:
  - a wrong current password gives 400,
  - new password equal to the current one gives 400,
  - success bumps `token_version` and sets new cookies,
  - after success, an access token and a refresh token issued before the
    change are both rejected, and the new cookies work,
  - an API token for the same user still works afterwards.
- A token without a `tv` claim is still accepted while `token_version` is 0.

The frontend has no test runner; don't add one for this. Verify the UI by
running the app. Check:

- each role's tabs on `/profile`,
- the `?tab=` deep links,
- the `/settings` redirect for non-admins,
- the header and sidebar name updating after a save,
- both themes.

## Left to the builder

- The context's name and file location, and whether the header and sidebar
  read it directly or keep taking props.
- Exact CSS for the active state on the header avatar and sidebar footer link.
  It must work in both themes.
- Where `_set_auth_cookies` ends up.
- How to split the profile page into files. The moved Notifications and API
  Keys code are natural candidates for their own components. Settings
  currently keeps everything in one file.

## Note for the builder

`frontend/AGENTS.md` warns that this Next.js version (16.x) differs from older
versions. Read the relevant guide in `frontend/node_modules/next/dist/docs/`
before writing frontend code. This includes `useSearchParams` for the
`?tab=` param.
