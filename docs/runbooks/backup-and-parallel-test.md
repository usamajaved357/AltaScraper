# Runbook: preserve old production, then test the new build beside it

Prepared 29 Sep 2026 (roadmap phases 5-6). Companion to
docs/deployment-manifest.md. **Every step marked OWNER is a push, a deploy, or
an action on the live server or its data: Claude does not do it without the
owner's explicit instruction in the conversation (CLAUDE.md Rule 2; autonomy
Level 4).** Steps marked CLAUDE are local and reversible.

## 0. What is being preserved

| Thing | Value (measured 29 Sep 2026) |
|---|---|
| Production code | `origin/main` = **0e5529e953fd5e4d9b421b0f9f1c5b4fb0a8afc3** (27 Sep 2026 04:12 +0500, "Listings: remove the stat-card hint text and the empty-queue line"), read with `git ls-remote origin refs/heads/main` |
| New build | branch `claude-environment-setup` (local only, not pushed) |
| Production service | Render web service `amazon-listing-tool`, Docker, disk `app-data` at `/data` (render.yaml) |

## 1. Code backup (git protects code only)

OWNER — creates refs on GitHub (a push):
```
git tag -a pre-modernization-production-2026-09-29 0e5529e953fd5e4d9b421b0f9f1c5b4fb0a8afc3 -m "Production before the modernization branch"
git push origin pre-modernization-production-2026-09-29
git push origin 0e5529e953fd5e4d9b421b0f9f1c5b4fb0a8afc3:refs/heads/legacy-main-backup-2026-09-29
```
Check: `git ls-remote origin "refs/tags/pre-modernization*" "refs/heads/legacy-*"`
shows both at 0e5529e. A tag is immutable by convention; GitHub branch
protection on `legacy-main-backup-2026-09-29` makes the branch so too.

## 2. Data backup (what git does not hold) — OWNER, on the live server

Take it with the app idle (no generation running), ideally in a quiet hour.
Everything is under `/data` (manifest §5). Never print or paste these files.

1. Database, consistently (a plain copy can miss what is still in -wal):
   `mkdir -p /data/backup-2026-09-29` then
   `python -c "import sqlite3;s=sqlite3.connect('/data/altascraper.db');d=sqlite3.connect('/data/backup-2026-09-29/altascraper.db');s.backup(d);d.close();s.close()"`
   (Render shell) — or stop the service and copy `altascraper.db*` together.
2. Files → `/data/backup-2026-09-29/`: simplest and complete is EVERY file and
   folder in `/data` except the backup folder itself and the GENERATED ones of
   manifest §5. At minimum: `config.json`, `service_account.json`,
   `notify.json`, `users.json`, `image_url_key`, `app_state.json`,
   `sheets_archive_*.json` (the one-time copy of the old Google Sheets — cannot
   be recreated), `attribute_defaults.json`, `_image_instructions.json`,
   `live_snapshots.json`, `cogs_overrides.json`, `model_number_counter.json`,
   the other `*.json` of manifest §5, and the folders `media/`, `uploads/`,
   `brands/`, `miles_templates/`.
3. Take a copy OFF the server (download, or the platform's disk snapshot):
   a backup on the same disk does not survive losing the disk.
4. Server settings: record (not their values in git — in the owner's password
   manager) `APP_SECRET_KEY`, `APP_PASSWORD`, `ALTA_TOKEN_KEY`,
   `ALTA_LWA_CLIENT_ID/SECRET`, and the service's plan, disk and domain settings.
   `ALTA_TOKEN_KEY` and `image_url_key` are the two whose loss cannot be undone.
5. Check the backup: the copied database opens
   (`sqlite3 ... "PRAGMA integrity_check"` → `ok`) and its row counts match.

## 3. Parallel server test

Goal: the new build runs beside the old one, on a COPY of the data, and proves
itself before anything replaces production.

OWNER — create a second Render service (e.g. `altascraper-next`):
- same Dockerfile, deploying the new branch (it must be pushed to GitHub first —
  a push of a non-main branch; it does NOT deploy production);
- its OWN disk at `/data`, filled from the §2 backup (never the production disk);
- env as production, plus **`ALTASCRAPER_BACKGROUND=off`** (no job timers, no
  repricer pushes, no monitor loop, no refresher, no Google backup — manifest §6);
- **the test copy's config.json must not reach production's outside services**
  — required, because the switch exists only in the NEW build and §4 runs the
  OLD build on this service:
  - `repricer_enabled` false, `asin_monitor_enabled` false;
  - Google blanked: `google_spreadsheet_id`, `input_spreadsheet_id`, the
    template ids, `google_service_account_json` (otherwise the nightly backup
    of an old build overwrites production's `backup_` tabs, and deleting an
    image deletes production's Drive file — `_drive_map.json` inside `media/`
    carries production's Drive ids);
  - Slack: `notify.json` removed or pointed at a test channel;
  - `track17_key` blanked (metered quota); supplier/eBay keys blanked unless a
    supplier READ test is planned;
- `ALTA_OAUTH_REDIRECT_URI` / `PUBLIC_BASE_URL` / `APP_BASE_URL` set to the test
  address (or leave OAuth unconnected on the test copy);
- NO custom domain: production keeps app.altascraper.com.

Then CLAUDE can run the READ checks through the browser once the owner shares
the test address and a sign-in (every screen, both accounts, two tabs):

| READ TEST (safe) | REAL WRITE TEST (owner approval each time) |
|---|---|
| startup, `/healthz`, `/diag` all green | Amazon submit / price / stock / handling push |
| login, Team, Employee Performance | tracking upload to Amazon, dispatch |
| account + marketplace switching, two tabs | repricer apply, PPC changes |
| Listings, Orders, Sales, Finance, Repricer, PPC, Inventory screens load | supplier purchase, any money |
| images/AI on a test draft (costs a little AI spend — say so first; never delete an image) | Google backup, Slack sends, image deletes |
| static files, console clean, server logs clean | |
| restart the service: data still there, health back | |

The same Amazon credentials are read by both copies during the test: reads are
safe (quota is shared — keep the test short); writes are not done.

## 4. Rollback proof, before any cutover

1. On the TEST service, deploy 0e5529e (the old code) against the test disk
   that the new build has been running on. **The old build ignores
   ALTASCRAPER_BACKGROUND**: it starts every timer, the refresher and (about
   two minutes after boot) the nightly Google backup. Only the §3 config
   blanking keeps it off production's Sheets, Drive, Slack and quota — check
   the blanking is still in place before this step, and keep the step short.
   Open every screen: the old build must work on the newer database (this
   branch only ADDS tables/columns). Not yet verified: that the old build reads
   the newer `users.json` (permissions version 3) correctly.
2. Redeploy the new build; it must pick up exactly where it was.
3. Only then plan cutover: pointing production at the new build is a
   merge/push to origin/main — OWNER instruction, with Rule 2's waiting period
   stated if he waives it.

## 5. Rolling back production after a cutover (if ever needed)

- Render → the service → Deploys → "Rollback" to the last 0e5529e deploy, or
  push `pre-modernization-production-2026-09-29` to main (OWNER).
- Data: if the new build wrote data the old one mishandles, stop the service,
  restore `/data` from the §2 backup, start it. Work done since the backup is
  lost — which is why the backup is taken immediately before cutover, again.
