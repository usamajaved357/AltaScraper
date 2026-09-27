# Security

The security model as it is, and its known gaps. Never put a secret value in
this file. Claude updates it after a `security-review`; the owner reviews changes.

---

## 1. Secrets: what exists and where it lives

| Secret | Where | Committed? |
|---|---|---|
| SP-API client id/secret, refresh tokens, Anthropic / OpenRouter keys, eBay keys, 17TRACK key, Slack webhook | `config.json` beside the database (`$CONFIG_PATH`; Render: `/data/config.json`, seeded from a Render Secret File) | never (gitignored `config.json*`) |
| Google service account | `service_account.json` | never |
| Session signing key | env `APP_SECRET_KEY` (render.yaml `generateValue`); falls back to a random key per boot | env only |
| Shared bootstrap password | env `APP_PASSWORD` | env only |
| OAuth app credentials | env `ALTA_LWA_CLIENT_ID`, `ALTA_LWA_CLIENT_SECRET` | env only |
| Refresh-token encryption key | env `ALTA_TOKEN_KEY` (Fernet, `auth/token_crypto.py`) | env only |
| Public-image URL signing key | `image_url_key` beside config.json | never (gitignored) |
| User password hashes, invites | `users.json` | never (gitignored) |

- OAuth refresh tokens are encrypted at rest; older accounts still hold plain
  tokens and encrypt on next save. `domain/accounts.account_creds()` is the one
  place that decrypts. A refresh token can delete listings: treat it like a
  password.
- **History:** a config backup with live keys was committed locally in July 2026;
  GitHub push protection blocked it and the history was scrubbed before any
  push. The owner chose not to rotate (docs/decisions.md). No local backup refs
  holding it remain (checked 27 Sep 2026).
- Claude never opens config.json, service_account.json, .env files or users.json
  (deny rules in `.claude/settings.json`), and never looks for tokens in
  credential stores.
- The commit guard (`.claude/hooks/guard_commit.ps1`) blocks staging or
  committing secret-bearing files: the list is in CLAUDE.md Rule 2.

## 2. Authentication

- `routes/dash_auth_routes.py` `/login`: email + password for real users
  (`auth/users.authenticate`); the shared `APP_PASSWORD` only while no admin
  user exists (bootstrap). No users and no password = no login (local dev).
- Sessions are permanent for 30 days, signed with `APP_SECRET_KEY`. Without that
  env var every restart logs everyone out.
- `next=` is checked against open redirects.
- Multi-tenant Amazon OAuth: single-use nonce, 15-minute expiry, constant-time
  compare (`routes/auth_oauth_routes.py`).

## 3. Authorisation

- One table: `auth/guard.py` `RULES`, first prefix match wins. Unlisted GET =
  any signed-in user; unlisted write = "edit".
- Roles: owner (all), manager (edit, upload_images, approve_delete, publish,
  ppc), lister (edit, upload_images), viewer (none). Feature areas per page with
  none/view/edit levels.
- Publishing paths needing `publish`: `/submit` (precheck), `/optimize/push`,
  `/sync/push`, `/listing/push_image`, `/listing/image_push`,
  `/handling/bulk_update`, `/stock/bulk_update`, `/listing/price/apply`,
  `/listing/price/percent_apply`, `/variations/apply`, `/sourcing`.
- **Known gap (unverified):** the real submit paths `/run/api_submit` and
  `/preview/enqueue` need only "edit"; `_require_publish()` checks the
  workspace, not the user (docs/known-issues.md #1).

## 4. Public endpoints (no login)

`_login`, `_healthz`, `static`, `_pubimg` (`/img/<token>/...`, HMAC-signed
image URLs for Amazon), `invite_page`, `invite_accept`, `oauth_login`,
`oauth_callback`, `oauth_diagnose`, `privacy_page`, `terms_page`.
Any addition to `PUBLIC_ENDPOINTS` is a security change: owner approval.

## 5. Account isolation

- A user may only name workspaces they have access to (guard step: named
  workspace), except under exempt prefixes (`/users`, `/media`, `/input/`,
  `/listing/`, `/row`, `/genimage`, `/aplus`, `/drive`, ...).
- `_wrong_account` checks are disabled (`account_scope.is_mismatch` returns
  False). Requests that name no account act on the session's selection; the
  shared-password owner and background threads share one process-wide value.
- SKUs are not unique across accounts.
- Review with the `account-scope-reviewer` agent. Open items: known-issues #4, #5.

## 6. Output escaping (XSS)

HTML is built as strings. Text goes through `esc()`; data inside inline JS
handlers must go through `jsArg()`. The `'${esc(x)}'` pattern in several core
files is unsafe (known-issues).

## 7. External APIs

- Timeouts are set per client (eBay 15 s, 17TRACK 20 s, Slack 12 s).
- The Ads client can only read (no bid/budget calls; test_ads_connect.py).
- Slack webhooks are accepted only on hooks.slack.com.
- Credentials must not appear in logs or in the streamed run output.

## 8. Deployment

- Docker image built from the repo (`COPY . .`); `.dockerignore` excludes
  secrets, runtime folders, root `*.md`, `docs/`, `active/`, `.claude/`.
- Flask's built-in server serves production (gunicorn declined, docs/decisions.md).
- Render health check `/healthz`; persistent disk at `/data`.

## 9. Database

SQLite, one connection per thread. Reviews check for SQL built with f-strings
or `%` formatting of values (placeholders `?` only). Never run destructive SQL
against the owner's real database from the agent shell.

## 10. Dependencies

`requirements.txt` has lower bounds only (no pins, no lockfile). Flag, don't
change, without the owner's approval.
