# Deployment manifest (authoritative) — 29 Sep 2026

Everything AltaScraper needs to run on a server, classified. Code facts are cited
(file:line) from the development branch `claude-environment-setup`; where
production (origin/main) differs, it says so. **No secret value appears here or
in git** — secrets are set on the server (Render dashboard / secret files).

Classes: **REQUIRED** (will not start or will not work without it) ·
**OPTIONAL** (a feature is off without it) · **SECRET** (never in git; server
env or secret file) · **PERSISTENT** (must survive a redeploy — lives on the
data disk) · **GENERATED** (the app creates it; lost = recreated or rebuilt).

## 1. Runtime and build

| Item | Value | Class | Evidence |
|---|---|---|---|
| Python | 3.11 (`python:3.11-slim`) | REQUIRED | Dockerfile:1 |
| Packages | `requirements.txt` (pip, unpinned `>=`) | REQUIRED | Dockerfile:11-12 |
| Chromium (Playwright) | `playwright install --with-deps chromium` (crawl4ai scraping in the generator) | REQUIRED for generation | Dockerfile:13 |
| build-essential | wheels that need a compiler | REQUIRED at build | Dockerfile:7-9 |
| `cryptography` | used by auth/token_crypto.py (OAuth token encryption); **not listed** in requirements.txt, arrives transitively (pdfplumber → pdfminer.six) — NOT VERIFIED | REQUIRED for OAuth accounts | auth/token_crypto.py:63 |
| Plan | Render `standard` (Chromium needs the RAM) | REQUIRED | render.yaml:6 |

## 2. Start, port, process

- Entrypoint `docker-entrypoint.sh` seeds `/data/config.json` and
  `service_account.json` from secret files / env, creates data folders, then
  `exec python dashboard.py` (docker-entrypoint.sh:122).
- Server: Flask's own threaded server, ONE process (`app.run(threaded=True)`,
  dashboard.py:3737). No gunicorn in the image (only `requirements-beta.txt`).
  In-memory state (run slots, image jobs, preview jobs, activity hook) assumes
  one process — **do not run more than one worker/instance against the same
  data disk**.
- Port: `PORT` set → binds `0.0.0.0:$PORT`; unset → 127.0.0.1, free port from
  5000 (dashboard.py:93-95). Image exposes 10000.
- Hosting detection: `RENDER*`, `RAILWAY_*`, `WEBSITE_INSTANCE_ID`, `DYNO`
  (config/hosting.py:17-22). Hosted ⇒ sign-in fails CLOSED without a password
  (503) unless `ALTASCRAPER_ALLOW_OPEN=1`; session cookie Secure; no template
  auto-reload. **origin/main does not have config/hosting.py or the fail-closed
  gate yet** (they are on the development branch).

## 3. Environment variables

| Name | Class | Default / effect |
|---|---|---|
| `CONFIG_PATH` | REQUIRED | `/data/config.json` on the server; its folder IS the data folder (render.yaml:13-14) |
| `PORT` | REQUIRED on server | set by the platform |
| `APP_SECRET_KEY` | SECRET, REQUIRED | signs sessions; random per boot if unset (everyone signed out on each deploy). render.yaml `generateValue: true`; a code comment (dashboard.py:141) says it is not set on the live service — **owner to confirm in the Render dashboard** |
| `APP_PASSWORD` | SECRET, REQUIRED until an owner account exists | shared bootstrap sign-in |
| `ALTA_TOKEN_KEY` | SECRET, REQUIRED for OAuth sellers | Fernet key for stored refresh tokens. **Losing it makes every stored OAuth token unreadable.** Back it up outside the server. |
| `ALTA_LWA_CLIENT_ID`, `ALTA_LWA_CLIENT_SECRET` | SECRET, OPTIONAL | multi-tenant Amazon OAuth (/auth/login refuses 503 without) |
| `ALTA_OAUTH_REDIRECT_URI` | OPTIONAL | default `https://app.altascraper.com/auth/callback` — **a parallel instance on another address needs its own value and an Amazon-registered redirect** |
| `PUBLIC_BASE_URL` | OPTIONAL | base of image URLs given to Amazon (else config `public_base_url`, else request host) |
| `APP_BASE_URL` | OPTIONAL | base of invite links (else forwarded host) |
| `ALTASCRAPER_DB` | OPTIONAL | database path; default beside config.json |
| `ALTASCRAPER_ALLOW_OPEN` | OPTIONAL, dangerous | `1` = run hosted with no sign-in |
| `ALTASCRAPER_BACKGROUND` | OPTIONAL (added 29 Sep 2026) | `off` stops every background starter (job timers incl. repricer apply, ASIN monitor, live refresher, nightly Google backup) — for a parallel/test instance. Unset = unchanged |
| `MONITOR_INTERVAL_S` | OPTIONAL | forces an ASIN-monitor interval |
| `ALTA_RUNS_PER_ACCOUNT` / `ALTA_RUNS_TOTAL` | OPTIONAL | generator concurrency, 2 / 6 |
| `ALTA_IMG_WORKERS` / `ALTA_IMG_BATCH` | OPTIONAL | 3 / 40 |
| `RESEED_CONFIG`, `CONFIG_JSON`, `SERVICE_ACCOUNT_JSON` | SECRET (the JSON ones), entrypoint only | seeding |
| `AWS_*` | SECRET, OPTIONAL | diagnostic only; nothing calls AWS |
| `ALTA_DATA_BACKEND`, `ALTA_READ_SHEETS` | ignored | the database is forced (data/choice.py) |

No Anthropic / OpenRouter / eBay / Google / Ads / 17TRACK / Slack key is read
from the environment — they live in `config.json` / `notify.json` (below).

## 4. Secrets inside config.json (names only)

`config.json` is SECRET + PERSISTENT + REQUIRED (the app will not boot without
it: dashboard.py:411-424).
- AI: `anthropic_api_key`, `openrouter_api_key`, `chat_model`, `image_provider`
- Amazon SP-API (global and per account in `accounts[]`): `sp_api_client_id`,
  `sp_api_client_secret`, `sp_api_refresh_token`, `lwa_client_id`/`lwa_app_id`,
  `lwa_client_secret`, `refresh_token`, `seller_id`, `marketplaces`,
  `default_marketplace`, `brands`
- Amazon Ads: `ads_client_id`, `ads_client_secret`, `ads_refresh_token`,
  `ads_profile_id`, `ads_currency`
- eBay: `ebay_app_id`, `ebay_cert_id`
- Google: `google_spreadsheet_id`, `google_service_account_json` (→ the file
  `service_account.json`, SECRET), `drive_impersonate_email`, template ids
- Tracking: `tracking_provider`, `track17_key`
- Switches: `repricer_enabled`, `asin_monitor_enabled`
- Other: `app_password`, `app_secret_key`, `public_base_url`, `brands_dir`
- Slack webhooks: in `notify.json` (SECRET, PERSISTENT), not config.json.

## 5. Persistent data (the `/data` disk, 5 GB)

| Path (beside config.json) | Class | Note |
|---|---|---|
| `config.json`, `service_account.json`, `notify.json` | SECRET, PERSISTENT | |
| `altascraper.db` (+ `-wal`, `-shm`) | PERSISTENT | everything the app knows: drafts, orders, sales, costs, activity log. **Copy with SQLite's backup API or with the app stopped** — never copy the .db alone while -wal holds unmerged pages |
| `users.json` | SECRET, PERSISTENT | people, password hashes, invite hashes |
| `image_url_key` | SECRET, PERSISTENT | **if lost, every image URL already given to Amazon stops working** |
| `app_state.json` | PERSISTENT | open account per user |
| `sheets_archive_*.json` | PERSISTENT | the one-time copy of everything the Google Sheets held (archive_sheets.py) — cannot be recreated |
| `attribute_defaults.json` | PERSISTENT | the owner's "Save as default" attribute choices (routes/ui_routes.py, generator) |
| `_image_instructions.json` | PERSISTENT | saved image instructions (domain/image_jobs.py) |
| `.supplier_columns_repair_*.done` | GENERATED | marker; if lost the repair runs again, harmlessly |
| `media/`, `uploads/`, `brands/*/profile.json`, `miles_templates/` | PERSISTENT | images, original uploaded files (kept for ever), brand profiles |
| `live_snapshots.json`, `cogs_overrides.json`, `trackers.json`, `categories.json`, `compliance_scans.json`, `asin_monitor*.json`, `sync_*.json`, `model_number_counter.json`, `image_recipes.json`, `miles_*.json`, `marketplace_health.json` | PERSISTENT (some rebuildable) | model_number_counter must not go backwards |
| `ppc_out/`, `inventory_out/cache`, `autofix_logs/`, `brand_analytics_cache/`, `.disk_history.json`, `config.json.bak-*` | GENERATED | safe to lose |
| `run_status.<account>.json` (`run_status.json` for a run with no account) | GENERATED, beside config.json since 29 Sep 2026 | the run heartbeat; safe to lose |
| rule files (`compliance_rules.json`, `ip_rules.json`, `valid_values.json`, `forbidden_*.txt`, `miles_fonts/`) | GENERATED / in the image | code folder, recreated by each deploy |

## 6. Background work started at boot

| Starter | What | Reaches outside |
|---|---|---|
| `data/scheduler.register_jobs` | tracking 6h, sourcing_listings 24h, sourcing_check 4h, sourcing_fees 24h, **sourcing_apply 4h (pushes prices only if `repricer_enabled` and armed SKUs)**, sales 6h, catalog 6h, asin_monitor 4h, inventory 24h, ads 6h; plus a one-time supplier-columns repair thread (database only) | Amazon reads; **Amazon price writes** (sourcing_apply); **Slack posts** (sourcing_listings, data/scheduler.py); 17TRACK metered quota (tracking); supplier / eBay calls (sourcing_check) |
| `monitor/checker.start_scheduler` | ASIN monitor loop (off by default in its UI) | Amazon reads |
| `domain/live_refresher.start` | per-account live catalogue refresh | Amazon reads |
| `domain/backup.NIGHTLY` | nightly listings export to Google Sheets | **writes Google** |
All of them honour `ALTASCRAPER_BACKGROUND=off` — **in this build only**; an
older build (production 0e5529e) ignores it, so a test copy running old code
needs its config blanked (runbook §3). Browser timers still read Amazon on any
open page (miles_template.js every 10 min, autoverify.js `/run/api_verify`).

## 7. Health, diagnostics, logs

- `/healthz` — public, returns `ok` without checking anything (liveness only).
- `/diag` — signed in: data folder writable, disk survives deploys, secret env
  set, files present, data store, duplicate sellers, recent faults.
- `/run/health`, `/live/refresher`, `/auth/diagnose` — feature health.
- Logs: stdout only (`print`) → the platform's log viewer. Boot prints a
  deploy-check banner (domain/deploy_check.py) naming every missing required
  item: data folder, persistent disk, APP_SECRET_KEY, APP_PASSWORD,
  ALTA_TOKEN_KEY when OAuth accounts exist, the AI key, and whether background
  work is on or off -- names only, never a value (test_deploy_check_required.py).
- Startup safety of a test copy is proven automatically:
  test_startup_side_effects.py (ALTASCRAPER_BACKGROUND=off -> no outbound
  connection, no background thread; negative control reaches api.amazon.com).

## 8. Startup procedure (new server or new service)

1. Create the service from the Dockerfile; plan with ≥ standard RAM.
2. Attach a persistent disk at `/data` (≥ 5 GB).
3. Set env: `CONFIG_PATH=/data/config.json`, `APP_SECRET_KEY` (generate, keep),
   `APP_PASSWORD` (until an owner account exists), `ALTA_TOKEN_KEY` (the SAME key
   as production if production's OAuth tokens are copied), OAuth vars if used.
4. Put `config.json` (+ `service_account.json`) on the disk (secret files /
   `CONFIG_JSON` seeding), then restore the data files of §5 if migrating.
5. Deploy; check `/healthz`, then sign in and open `/diag` — every line green.
6. Open each screen once (the browser harness list) before handing it over.

## 9. Rollback

- Code: the production commit before any change is recorded and tagged (see
  docs/runbooks/backup-and-parallel-test.md). Rolling back = redeploy that commit
  (Render "Rollback" to the previous deploy, or push the tag's commit to the
  deploy branch — a push, so the owner's explicit instruction).
- Data: restore the §5 files from the pre-change backup with the app stopped.
  The database schema changes on this branch are ADDITIVE only (new tables /
  columns), so an older build runs on a newer database; a newer build's new
  tables are simply unused by the older one.
- Prove it before cutover: on the parallel service, deploy the old commit on a
  copy of the new data and open every screen — with that copy's config blanked
  of Google / Slack / 17TRACK first, because the old build starts all its
  background work regardless (runbook §3-§4).

## 10. Known gaps (not fixed here)

- `/healthz` checks nothing — a broken data disk still reports `ok`.
- `requirements.txt` is unpinned; builds are not reproducible. A lock file
  (`pip freeze` from a known-good image) would make rollback exact.
- One process only (§2); no horizontal scaling.
- `APP_SECRET_KEY` on the live service: unknown (§3).
