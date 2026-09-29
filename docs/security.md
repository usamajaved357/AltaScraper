# Security

The security model as it is, and its known gaps. Never put a secret value in
this file. Claude updates it after a `security-review`; the owner reviews changes.

---

## 1. Secrets: what exists and where it lives

| Secret | Where | Committed? |
|---|---|---|
| SP-API client id/secret, refresh tokens, Anthropic / OpenRouter keys, eBay keys, 17TRACK key (Slack webhooks: `notify.json` in the same folder, domain/notify.py) | `config.json` beside the database (`$CONFIG_PATH`; Render: `/data/config.json`, seeded from a Render Secret File) | never (gitignored `config.json*`) |
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
- Claude never opens secret-bearing files and never looks for tokens in
  credential stores. Enforced two ways:
  - deny rules in `.claude/settings.json` stop the Read/Edit tools (and simple
    cmdlets such as Get-Content) on config.json*, service_account.json, .env*,
    users.json, app_state.json, miles_bundles*.json, image_url_key, *.db*,
    *.pem, *.p12, *.pfx and secret/credential data files;
  - the `guard_secrets` hook denies any tool call — including shell, .NET and
    Python routes — whose command or path NAMES one of those files. It checks
    names only and never opens the files. A name assembled at run time is not
    caught (docs/known-issues.md "Claude Code environment").
- The commit guard (`.claude/hooks/guard_commit.ps1`) blocks staging or
  committing secret-bearing files: the list is in CLAUDE.md Rule 2.
- The `guard_rules` hook makes every edit to CLAUDE.md and `.claude/`
  (settings, hooks, agents, skills) an owner confirmation, so the rules above
  cannot be relaxed silently.

## 2. Authentication

- `routes/dash_auth_routes.py` `/login`: email + password for real users
  (`auth/users.authenticate`); the shared `APP_PASSWORD` only while no admin
  user exists (bootstrap). No users and no password = no login -- locally
  only. On a hosting platform (config/hosting.py) the same blanks now FAIL
  CLOSED with a 503 until APP_PASSWORD is set, unless ALTASCRAPER_ALLOW_OPEN=1
  says otherwise on purpose (Milestone 2, 28 Sep 2026).
- Sessions are permanent for 30 days, signed with `APP_SECRET_KEY`. Without that
  env var every restart logs everyone out.
- `next=` is checked against open redirects, including the backslash and
  tab/newline forms browsers rewrite into `//other.site` (Milestone 2).
- Cross-site requests (CSRF): the session cookie is `SameSite=Lax`,
  `HttpOnly`, and `Secure` when hosted; any write whose Origin/Referer names
  another site is refused before anything else (`guard.cross_site_refusal`).
  No per-form token -- a request with neither header is left to the sign-in
  check (Milestone 2).
- Multi-tenant Amazon OAuth: single-use nonce, 15-minute expiry, constant-time
  compare (`routes/auth_oauth_routes.py`).

## 3. Authorisation

- One table: `auth/guard.py` `RULES`, first prefix match wins. Unlisted GET =
  any signed-in user; unlisted write = "edit".
- Roles: owner (all), manager (edit, upload_images, approve_delete, publish,
  ppc, view_activity), lister (edit, upload_images), viewer (none). Feature
  areas per page with none/view/edit levels. `view_activity` (PERMS_VERSION 3)
  gates `/activity/*` (Employee Performance); rows are limited to the reader's
  accounts, and rows naming no account only to someone who may open every one.
- Publishing paths needing `publish`: `/submit` (precheck), `/optimize/push`,
  `/sync/push`, `/listing/push_image`, `/listing/image_push`,
  `/handling/bulk_update`, `/stock/bulk_update`, `/listing/price/apply`,
  `/listing/price/percent_apply`, `/variations/apply`, `/sourcing`,
  `/orders/ship/confirm` (dispatch to Amazon; also refused while the owner's
  switch `ship_confirm_enabled` is off, and once per order -- a claim is
  recorded before the send). Removing a tracking number that records such a
  send (`/tracking/set` with `remove`) also needs `publish`: it is what allows
  another send.
- Orders writes needing `edit` (explicit RULES entries): `/orders/purchase`,
  `/orders/purchase/remove`, `/orders/ship/preview` (reads Amazon, sends
  nothing). They and `/tracking/*` act only for the account the request NAMES
  (domain/order_scope.py), never the server's open one.
- `/run/stack` (py-spy dump of a stuck run) needs `edit`, a named account, and
  dumps only a process the app started whose pid is that account's heartbeat.
- Submitting needs `publish` whichever way it is started: `/run/api_submit`
  (RULES) and `/preview/enqueue` with `mode: api_submit` (BODY_RULES). Closed in
  Milestone 2 (was known-issues #1).
- Work done over GET (`WORK_OVER_GET`, the streamed `/run/*`) is judged as a
  write: a view-only user cannot start one.
- `WRITE_RULES`: `/ai/settings` and `/admin/logic_settings` may be read by
  anyone signed in, changed only with `manage_accounts`; so may
  `/brand/connection` (the brand panel's app-wide Google settings, 29 Sep 2026).
  `/jobs/run/*` and `/media/recover/move` need `manage_accounts`.
- The brand run (`/brand/run/*`) and the Miles streams (`/miles/run`,
  `/miles/generate`, `/miles/optimize`) start paid AI work over GET, so they are
  `WORK_OVER_GET` (a view-only user and a link from another site are refused);
  the brand run needs `edit`.
- Preview jobs: `/preview/job` shows only jobs the caller may see and, by SKU,
  only the open account's; `/preview/stop` stops only the caller's own.

## 4. Public endpoints (no login)

`_login`, `_healthz`, `static`, `_pubimg` (`/img/<token>/...`, HMAC-signed
image URLs for Amazon), `invite_page`, `invite_accept`, `oauth_login`,
`oauth_callback`, `oauth_diagnose`, `privacy_page`, `terms_page`.
Any addition to `PUBLIC_ENDPOINTS` is a security change: owner approval.

## 5. Account isolation

- A user may only name workspaces they have access to. Since Milestone 2 the
  guard checks EVERY account a request names (`guard.named_workspaces`): all
  six fields, in the query, the body whatever its Content-Type (JSON sent as
  text/plain included), form fields, and every row of every list. Only the
  field `id` is ever exempt, and only on paths where it is a record id
  (`ID_NOT_AN_ACCOUNT`, `_EXACT`, `_EXCEPT` -- found by sweeping every caller).
  `/listing/` and `/trackers/watch` are no longer exempt.
- Browser bulk actions (GTIN exemption, arm/rule on the repricer, Delete,
  Approve) take the account ONCE before the loop, name it on every request
  (`acctBodyFor` in reqscope.js) and stop if the account changes part-way.
  Ticks are cleared on every account switch. `/approve` honours the named
  account like `/delete`.
- All-account lists (`/backup/verify`, `/migrate/status`, `/aiusage/*`) show
  only accounts the caller may open (`users.caller_may_see`,
  `caller_sees_every_account`).
- `_wrong_account` checks are disabled (`account_scope.is_mismatch` returns
  False). Requests that name no account act on the session's selection; the
  shared-password owner and background threads share one process-wide value.
- SKUs are not unique across accounts.
- Review with the `account-scope-reviewer` agent. Open items: known-issues #4, #5.

## 6. Output escaping (XSS)

HTML is built as strings. Text goes through `esc()`; data inside inline JS
handlers goes through `jsArg()` (users.js) -- the one escaper; the private
copies (`_sarg`, `_sarg2`, `_dsArg`, `_pdpiArg`) now call it. In Milestone 2
about 260 handler arguments were converted: `'${esc(x)}'`, the concatenated
`\'' + esc(x) + '\'`, and raw unescaped `'${x}'` / `\'' + x + '\'`.
test_no_esc_in_handlers.js fails on any of the three shapes coming back
(multi-line handlers are the one shape it cannot see).

## 7. External APIs

- Timeouts are set per client (eBay 15 s, 17TRACK 20 s, Slack 12 s).
- The Ads client can only read (no bid/budget calls; test_ads_connect.py).
- Slack webhooks are accepted only on hooks.slack.com.
- A URL that came from a user (an image link, a supplier page, a page to
  optimise from) is fetched through `domain/url_policy.urlopen`: http/https
  only, every resolved address public, re-checked on each redirect, and size
  capped. Not closed: DNS rebinding between the check and the connection.
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
