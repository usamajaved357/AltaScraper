# Architecture

How AltaScraper actually works. Maintained by Claude; corrected whenever code
and this file disagree (the code wins). Line numbers drift: search for the
named function rather than trusting a number.

Sources: the 27 Sep 2026 codebase analysis (`active/CODEBASE_ANALYSIS_REPORT.md`
in the main checkout) and the project-fact memory notes migrated on 27 Sep 2026
(each section names the note it came from).

---

## 1. Shape of the system

```
Browser: one page (templates/dashboard.html) + ~118 classic <script> files
   |  fetch() / EventSource (streamed run output)
   v
Flask (dashboard.py build_app)
   |- before_request: auth/guard.py "doorman"
   |- ~80 routes/*_routes.py, each register(app, *, injected helpers)
   |- _state: per-user workspace in the session cookie (shared fallback)
   |- /run/<mode>, /preview/enqueue --spawn--> amazon_listing_generator.py
   |- SQLite altascraper.db + JSON files beside config.json
   \- background: APScheduler jobs, live_refresher, ASIN monitor, backup
```

- **Language / framework:** Python 3.11, Flask 3, served by Flask's own threaded
  server (`app.run(threaded=True)`), not gunicorn. Plain browser JS, no bundler,
  no modules, no framework. Node is used only to run `test_*.js`.
- **Entry point:** `dashboard.py`. `build_app()` picks the data backend, then
  calls about 77 `<module>.register(app, ...)` functions plus
  `dashboard_brand_patch.register` (8 `/brand/*` routes, root file).
  Three routes are still defined in dashboard.py itself: `/img/<token>/...`,
  `/diag`, `/live/refresher`.
- **Unused parallel skeleton:** `main.py` + `routes/__init__.register_blueprints`
  + the `routes/auth_routes.py` blueprint. Docker runs `dashboard.py`, so the
  blueprint is never live. `dashboard_beta.py` is a port-5001 variant.

## 2. Route wiring (register injection)

Each `routes/<x>_routes.py` exposes `def register(app, *, deps)` and declares
`@app.route` inside it, closing over helpers injected from dashboard.py
(`_cfg`, `_state`, `_ws`, `_records`, `_active_account`, `CONFIG_PATH`,
`SCRIPT`, ...). Why injection and not `import dashboard`: dashboard.py runs as
`__main__`, so importing it would load a second copy with separate state.
(memory: phase3-route-extraction)

Page URLs `/`, `/w/<ws>`, `/w/<ws>/<section>`, `/w/<ws>/listing/<sku>` all
render `dashboard.html` (`routes/ui_routes.py`). A section is valid only if it
appears as a `data-sec` value in the template (scraped and cached on mtime).
There is deliberately no catch-all route.

## 3. The listing generator (subprocess)

`amazon_listing_generator.py` (about 9,200 lines) runs as a **separate process**
for generate, retry, export, regen, api (preview), api submit and api verify.
- Launched by `/run/<mode>` (routes/listing_routes.py `run`), streamed to the
  browser as server-sent events through `routes/stream_pump.py`.
- Also launched by `listing/preview_jobs` (worker thread, for `/preview/enqueue`),
  routes/miles_routes.py, routes/misc_routes.py and dashboard_brand_patch.py.
- Arguments are parsed by hand from `sys.argv` (no argparse): positional mode,
  then `--account-id --sheet --tab --marketplace --skus --input-json ...`.
- Generate reads the queued products from a temp JSON written by
  `listing/queued_input.write_temp_input()`.
- Submit/preview path: `run_api()` -> `build_api_attributes()` ->
  `put_listings_item(requirements="LISTING")`. `merchant_suggested_asin` is
  popped last. The GTIN exemption is sent only when the tick column is set.
- `build_api_attributes`, `check_compliance` and `_shape_list_price` stay in the
  engine on purpose: they read the mutable `MARKETPLACE_ID`, which is
  reassigned at runtime. Moving them needs marketplace injection, a behaviour
  change. (memory: phase5-listing-extraction, phase6-config-layer)
- The engine is also imported for a few functions (e.g.
  `fetch_ebay_supplement`, `get_competitor_asin_data`), so it is dual-use.
- Root shims (`accounts.py`, `ai_providers.py`, ... about 12 files) forward
  old import names to `domain.<name>` via `sys.modules`. Temporary; no logic
  may be added to them. (memory: restructuring-shims)

## 4. Auth and permissions

- `auth/guard.py make_doorman()` runs before every request:
  0. a write (or a GET that does work, `WORK_OVER_GET`) whose Origin / Referer /
     Sec-Fetch-Site says another site, or `Origin: null`, is refused
     (`cross_site_refusal`); session cookie SameSite=Lax (`harden_session`)
  1. public endpoints pass (`_login, _healthz, static, _pubimg, invite_*,
     oauth_*, privacy_page, terms_page`)
  2. not signed in: JSON 401 for API calls, redirect to `/login?next=` for
     pages. With no password and no users: open locally, 503 when hosted
     (`open_gate_allowed`, `config/hosting.py`)
  3. EVERY account named anywhere -- query, the body whatever its type
     (`request_body_for_check`), form fields, each row of each list -- must be
     one the user may access (`named_workspaces`). Only `id` is ever exempt, on
     the record-id paths in `ID_NOT_AN_ACCOUNT` / `_EXACT` / `_EXCEPT`
  4. feature area level (none / view / edit); a GET at view level passes
     without consulting RULES -- unless it is `WORK_OVER_GET` (the streamed
     `/run/*`), which is judged as a write
  5. `WRITE_RULES` (write-only rules), then `RULES` (first prefix match wins;
     unlisted GET needs nothing, unlisted write needs "edit"), then
     `BODY_RULES` (e.g. `/preview/enqueue` with `mode: api_submit` needs
     "publish")
- Roles (`auth/users.py`): owner (everything), manager (edit, upload_images,
  approve_delete, publish, ppc), lister (edit, upload_images), viewer (none).
- **A new route that publishes, spends money, deletes or exposes credentials
  must be added to RULES**, specific path above its broader prefix.
  (memory: permission-table)
- Users live in `users.json` beside config.json. Bootstrap: with no users, the
  `APP_PASSWORD` env var logs in as owner; with neither, there is no login.
- Multi-tenant Amazon OAuth: `/auth/login` -> `/auth/callback`
  (routes/auth_oauth_routes.py). OAuth sellers are ordinary accounts with
  `"auth": "oauth"`; `domain/accounts.account_creds()` is the single place that
  decrypts tokens (Fernet key `ALTA_TOKEN_KEY`). The Amazon app is in DRAFT, so
  the consent URL carries `&version=beta` (`DRAFT_VERSION_PARAM`), which must be
  removed when the app is published. (memory: oauth-multitenant)

## 5. Which account a request acts on

- `_state` (domain/workspace_state.WorkspaceState): the keys
  `active_account_id, active_marketplace, active_sheet_id, active_tab,
  active_tab_gid, active_view` are **per signed-in user**, stored in the
  session cookie. With no `session["uid"]` (shared-password owner) or no
  request (background threads) they fall back to one process-wide value,
  persisted to `app_state.json`.
- `POST /accounts/select` sets them. `_active_account()` never falls back to
  the first account.
- Per-request resolution: `domain/request_account.py` (`named()`,
  `for_read()`, `mismatch_for_write()`), `routes/scope.py`
  (`workspace_id()`, `marketplace()`, `resolve()`), and
  `data/backend.store_for(aid)` for the named workspace's store.
- `domain/account_scope.is_mismatch()` **always returns False** (disabled
  deliberately). So the seven `_wrong_account` wrappers in route files are
  no-ops, and named-account safety rests on guard step 3 plus `store_for`.
- Browser: `static/js/reqscope.js` `acctId() / acctBody() / acctUrl()` add
  `account=`; a BULK loop takes `acctId()` once before its question and uses
  `acctBodyFor(obj, pin)`, stopping if `acctId()` changes (the repricer screen's
  equivalent is `_srcScopeNow()` / `_srcStillIn()`); `static/js/scopeq.js scopeQs()` adds `account` + `marketplace`
  and drops `__all__`. With no account open they add nothing and the server
  uses `_state`.
- **SKUs are not unique across accounts.** The owner runs the same product on
  two of his own accounts and may reuse a SKU (34 live ASINs shared between
  jack_uk and nestwell_goods, measured 25 Aug 2026). Anything arguing "a wrong
  account would just 404" is void. To prove an account leak, use the reply's
  own `source.workspace` label or open `ListingStore("<account>")` directly.
  (memory: skus-are-not-unique-across-accounts)

## 6. Two ASINs on every row

On an app row, `r.asin` is the **competitor reference** parsed from the SKU
(`price_days_ASIN`), never ours. On a catalogue item (`LIVE_ITEMS`,
`/live/catalog`), `it.asin` IS ours. Use `rowAsin(r)` / `ownLiveAsin(r)` for
"our ASIN" and `_matchableAsin(r)` for matching against our catalogue
(static/js/listings.js; pinned by test_listings_asin.py). (memory: two-asins-per-row)

## 7. Storage

- **SQLite** `altascraper.db` beside config.json (override `ALTASCRAPER_DB`).
  One connection per thread, WAL, busy_timeout 30 s. Schema + migrations in
  `data/db.py` (`SCHEMA`, `_migrate`). About 40 tables there plus
  `keyword_*`/`rank_*` (domain/keyword_store.py) and `listing_metrics_cache`.
  Drafts are in `listings`, `UNIQUE(workspace_id, sku)`.
- **Google Sheets is permanently unlinked**: `data/choice.py` `_SHEETS_UNLINKED
  = True`, so `decide()` always returns "db". The Sheets read path in
  dashboard.py (`_records` cache, read pacer) is unreachable but still present.
  Decision: docs/decisions.md (SQLite).
- **Sheet-shaped adapter:** `data/store.ListingStore` returns rows keyed by the
  old sheet header names; `SheetLikeStore` mimics a gspread worksheet so old
  code runs on the database. `data/column_map.py` maps 49 headers to columns.
- **JSON files beside config.json:** users.json, app_state.json,
  cogs_overrides.json, live_snapshots.json, notify.json, trackers.json,
  categories.json, compliance_scans.json, asin_monitor*.json, miles_bundles*.json,
  run_status.json, image_url_key and others. Some are written atomically
  (`domain/jsonstore.write_json_atomic`); several are truncated then rewritten.
- **config.json:** `config/settings.py` `read_raw` / `write_raw` (atomic) is the
  single writer (the last direct writers -- accounts, known sellers, brand
  connection, settings routes -- moved onto it in Milestone 1).
- **attribute_defaults.json** (shared by every account): never holds brand,
  title, identifiers, offer or pictures -- `listing/attribute_defaults.py`,
  applied on save and on load (CLAUDE.md Rule 1).
- **Media:** `<config dir>/media/_acct/<account>/<sku>/`.

## 8. Data facts that are easy to get wrong

- **Two grains in one table.** `ads_daily` and `sales_daily` hold the account
  total at `asin='*'` beside per-product rows. A SUM that does not name a grain
  returns exactly double. Account total: `domain/ads_sync.totals()`; per
  product: the literal clause `asin<>'*'`. test_ads_grain.py enforces it.
  One advertising profile is one marketplace (`ads_sync.marketplace_for()`).
  (memory: two-grain-tables)
- **One calendar.** Sales/P&L use the ORDER calendar by default, decided only in
  `routes/sales_routes._basis()`. `series()` reports the basis it actually used
  in `meta`. `listFinancialEvents` is account-wide: finance data is stored only
  under the account's default marketplace. (memory: pnl-one-calendar)
- **Coupons, two feeds.** Orders API `OrderTotal` is already net of coupons
  (`domain/orders_view.profit_for()` must not subtract them); the Finances feed
  is gross, so `domain/order_profit.py` subtracts promotions. test_orders_promo.py
  pins both. (memory: coupon-two-feeds)
- **Amazon's fee.** Only from `domain/amazon_fees.py`: settled figure per order,
  else the account's measured rate, 15% only with no history.
  `getMyFeesEstimate` returns the pre-VAT fee; accounts without a VAT number pay
  about 1.2x, measured per account by `multiplier_for()` into `fee_multipliers`.
  (memory: amazon-charges-vat-on-its-fees)
- **The snapshot is not what sells.** `live_snapshots` omits SKUs an account
  actually sells. "Every SKU that matters" = live_snapshots + order_lines +
  sourcing_enrolment. (memory: snapshot-is-not-what-sells)
- **Product name/picture lookup:** `domain/catalogue.py` (`index()`, `merged()`,
  `look()`), SKU before ASIN. Never read live_snapshots directly in a screen.
  (memory: catalogue-lookup)
- **Uploaded .xlsx:** read rows only through `domain/report_reader.workbook_grid()`;
  Amazon exports declare a false row count that `read_only=True` believes.
  Template readers are the exception (read in full). (memory: xlsx-declares-its-own-size)
- **Stored verdicts go stale.** Status, IP Risk and Compliance Risk are stored on
  each row; fixing a rule changes nothing until Re-scan. Measure with
  `GET /rescan/preview`; never run `/rescan/apply` yourself.
  (memory: flag-fixes-need-a-rescan)
- **Two COGS systems** answer different questions: System A (what a product
  costs: `domain/cogs.py`, `cogs_store.py`, `cogs_overrides.json`, keyed
  `account::SKU`) and System B (what one order cost: `order_lines.cogs`, frozen,
  `domain/order_cogs.py`). (memory: cogs-two-systems-followup)
- **"All marketplaces" (`__all__`)** is honoured only by Sales
  (`/brand/marketplaces`, brandview.js). Other screens answer for one
  marketplace. (memory: all-marketplaces-was-a-lie)
- **eBay postage** needs a destination postcode header
  (`X-EBAY-C-ENDUSERCTX`); `sourcing_postcode` in config, fallback in
  `domain/source_fetch.py`. (memory: ebay-needs-a-destination-postcode)
- **Tracking:** no SP-API endpoint returns tracking a seller uploaded; it comes
  from Amazon's own shipping-confirmation file (`domain/tracking_sheet.py`).
  Carrier status needs a 17TRACK key. (memory: amazon-hides-seller-tracking)
- **Stock velocity** is out-of-stock-adjusted once `stock_daily` has 7 days per
  SKU (`velocity_basis`). (memory: stock-daily-started-20-aug)

## 9. Background work (started from build_app)

| System | Mechanism | Schedule |
|---|---|---|
| `data/scheduler.register_jobs` -> `start()` | APScheduler, staggered | tracking_check 6h, sourcing_listings 24h, sourcing_check 4h, sourcing_fees 24h, sourcing_apply 4h, sales_sync 6h, catalog_sync 6h, asin_monitor 4h, inventory_sync 24h, ads_sync 6h |
| `monitor/checker.start_scheduler` | thread, 60 s tick | user-chosen interval in `monitor/schedule.py`, off by default |
| `domain/live_refresher.start` | a thread per account | catalogue refresh after 10 min, stalest first |
| `domain/backup.NIGHTLY` | thread, hourly wake | export if last success > 24 h |

The browser adds its own clocks: live auto-sync every 10 min, auto-verify 30 s,
health 60 s, notifications/monitor badge 120 s, job pollers 2-3 s.
In-memory job registries and caches (`_IMG_JOBS`, `_AF_JOBS`, preview jobs,
`_LIVE_CACHE`, ...) are lost on restart.

ASIN monitor design (memory: asin-monitor): uses `getItemOffers` by ASIN
(cross-account); Amazon returns no seller name, only SellerId, and only about
20 offers even when more exist. Slack alerts need the app's own incoming
webhook. Any future seller-name scraping must live in its own module behind a
narrow interface, never inside checker logic.

Source repricer (memory: source-repricer): FBM only; ships inert (master switch
`repricer_enabled`, per-SKU arming from `dry_run`, mandatory `min_price`).
Active live listings auto-enrol in dry run; drafts never. Floor price and
"unknown is not out of stock" are load-bearing. It PATCHes price/qty/lead time
only, never PUTs a listing.

## 10. External APIs

- A URL that came from a user is fetched only through
  `domain/url_policy.urlopen` (http/https, public addresses only, re-checked on
  redirect). "Is this hosted, and where?" is `config/hosting.py`.

| Service | Where | Notes |
|---|---|---|
| SP-API (python-amazon-sp-api) | api/amazon_listings.py, api/amazon_catalog.py, api/sp_reports.py, api/amazon_metrics.py, api/amazon_messaging.py, many routes and domain modules, the generator | Pacing is per module (report reuse 30 min, orders cache 90 s, monitor adaptive 2-30 s). Nothing paces calls app-wide. |
| Amazon Ads API | api/amazon_ads.py, domain/ads_sync.py | Separate login from SP-API. Read-only: one POST (login) plus report POSTs; no bid/budget writes (Rule 8, test_ads_connect.py). HOURLY reports refused; spTargeting/spSearchTerm DAILY accepted; spKeywords groupBy keyword refused. (memory: advertising-api-not-connected, ads-hourly-not-available) |
| eBay Browse | api/ebay.py | client-credentials token, one global token cache |
| OpenRouter | domain/ai_providers.py | text and image models |
| Anthropic SDK | generator, several routes | usage recorded by patching the SDK (domain/ai_usage.py) |
| 17TRACK | api/track17.py | inert without `track17_key` |
| Slack webhook | domain/notify.py | only hooks.slack.com URLs |

## 11. Front end

- **Account/marketplace switch (Milestone 3):** `screenstate.screenForgetAll()`
  bumps `SCREEN_GEN`, resets every screen's held data and busy flags and the
  SKU-keyed caches (`_screenResetHeld`), and empties the panels listed in
  `SCREEN_BODIES`. A loader takes `screenScope()` before its fetch and returns
  if `!screenStillIn(sc)` after each await (guarded with `typeof`, so a file
  loaded alone in a test still runs). A new screen that holds data must be
  added to both lists.

- One page: `templates/dashboard.html` loads about 20 CSS files and about 118 JS
  files as classic scripts in a fixed order; they share one global scope. Load
  order is execution order: the files began as one script split at top-level
  boundaries, so moving a `<script>` tag can break a later file.
  (memory: phase4-html-extraction)
- State is plain globals (`ROWS`, `LIVE_ITEMS`, `LIVE_STORE`, `LIVE_MIRROR`,
  `CUR_ACCOUNT`, `WS_MARKET`, `PDP_SKU`, `SELECTED`, `COGS_LOCAL`, ...). No
  store, no reactivity: each writer calls `render()`, `summary()`,
  `pdpRender()` or `openDrawer()` itself.
- Functions do not live where their file name suggests:
  `render()`, `loadLiveCatalog()`, `syncLive()` -> static/js/miles_template.js;
  `runMode()` -> inventory.js; `loadRows()`, `submitOne()` -> submit.js;
  `toast()`, `esc()`, `summary()` -> listings.js; `jsArg()` -> users.js.
- Navigation: `shell.js` `altaRouteFromUrl()` (boot and popstate), `navGo` ->
  `navTo(sec)` (permission check, show/hide, lazy loader, `altaSyncUrl()`),
  `enterAccount(id)` (clears account data, `POST /accounts/select`,
  `loadRows()`, `loadLiveCatalog()`). PDP URL from `pdpPath()`.
- Requests: raw `fetch` with `{ok, error}` replies; `_fetchJSON` (shell.js)
  adds a timeout and one retry. One global `ES` EventSource doubles as a run
  lock.
- UI conventions: docs/design-system.md.

## 12. Traced user actions (27 Sep 2026)

- **Open Listings:** `enterAccount` -> `POST /accounts/select` -> `navTo("listings")`
  -> `loadRows()` (`/rows_all?account=`, drops late replies for another
  account) -> `render()`; in parallel `loadLiveCatalog(false)` (`/live/catalog`,
  cache or stored snapshot, no Amazon call).
- **Edit a title in the PDP:** `dwBlurSave` -> `saveEdit` -> `editField` ->
  `POST /edit` (account in body) -> `listing/repo.set_field` -> store
  `update_cell` -> ROWS patched -> "Saved".
- **Generate:** `genflowGenerate` -> `runMode("generate")` ->
  `EventSource /run/generate?account_id=&marketplace=` -> guard ->
  `mismatch_for_write` -> run lock -> temp JSON -> spawn generator -> streamed
  lines -> `event: end` -> `loadRows()`.
- **Submit one listing:** `submitOne` -> `/submit/precheck`, `/submit/target`,
  `/dup_check` -> confirm -> `rqEnqueue` -> `POST /preview/enqueue` ->
  `_require_publish` -> `listing/preview_jobs` worker -> generator `api submit`
  -> `run_api` -> `put_listings_item` -> `/preview/job` polled.
- **Sync on Live:** `syncLive` -> `/run/api_verify` -> `/live/catalog` (forced:
  Listings API, else Reports API) -> `/live/full_pull` (mirror) -> `loadRows`
  -> `/live/reconcile`.

### The product page (PDP), as traced 27 Sep 2026
- Every row, tile and live view calls `openListing` -> `pdpOpen(sku)`
  (static/js/pdp.js); `openDrawer` also forwards to it. No draft row -> a
  read-only catalogue row from `LIVE_ITEMS` (`pdpCatalogueRow`).
- `pdpOpen` resets tab/dirty state only when the SKU changes, then
  `pdpRender` (whole `innerHTML`), then `pdpRefreshChecks` (`/row`),
  `loadSchemas`, `lvEnsure` (`/listing/live_attributes`, cached per SKU in
  `LIVE_ATTRS`), `altaSyncUrl` (`pdpPath()` = `/w/<ws>/listing/<sku>`).
- Tabs: details, images (pdp_images.js), variations (only when it has one),
  offer, compliance (`pdpSafetyTab`). Partial redraws: `pdpHeroRefresh`,
  `pdpFieldEdited`, `_pdpiPaint`, `pdpMarkDirty`.
- Saving is per field, on blur/change: `dwBlurSave` / `editCell` -> `saveEdit`
  -> `editField` -> `POST /edit` with `acctBody()`; the server writes the named
  account's store (`_store_for`) via `listing/repo.set_field`. "Save & finish"
  only blurs the focused box and closes. `pdpClose` redraws the grid only if
  `PDP_DIRTY`.
- **Product context** (27 Sep 2026): `pdpContext()` (pdp.js) =
  `account::workspace::marketplace`. An account, marketplace or workspace
  change calls `pdpLeaveContext()` BEFORE `CUR_ACCOUNT` / `WS_MARKET` move
  (shell.js `enterAccount`, `switchAccountMarket`, `enterWorkspace`,
  `buildAccountMktSwitch`, and `altaRouteFromUrl` when Back/Forward goes to
  another workspace): it blurs a focused PDP field (so its save names the old
  account), cancels a pending barcode check, closes the page without touching
  the URL, and forgets `LIVE_ATTRS` (`lvForgetAll`) and `PDPI`
  (`pdpImagesForget`). Late replies are dropped by comparing the context (or,
  for caches, the identity of the entry/object they started with). The listing
  is reopened explicitly for the new context.
- Open problems: docs/known-issues.md "PDP".

## 13. Deployment

- Docker (`Dockerfile`: python:3.11-slim + Playwright Chromium for crawl4ai).
  `docker-entrypoint.sh` seeds `/data/config.json` and `service_account.json`
  from Render secret files (or env on Railway), then `exec python dashboard.py`.
- `render.yaml`: web service, `/healthz`, 5 GB disk at `/data`.
  `railway.json` also exists; the OAuth note records Railway env vars, the
  deploy note records Render. Both may be true. (memory: oauth-multitenant,
  deploy-and-branch-flow)
- Render deploys **origin/main**. A push to origin/main is the deploy; a new
  build is live within about a minute. `/healthz` returns a bare `ok` and cannot
  show which build is live: confirm by polling a changed or new static file.
- Environment variables: CONFIG_PATH, PORT, APP_SECRET_KEY, APP_PASSWORD,
  ALTASCRAPER_DB, ALTA_DATA_BACKEND, ALTA_READ_SHEETS, ALTA_LWA_CLIENT_ID,
  ALTA_LWA_CLIENT_SECRET, ALTA_TOKEN_KEY, ALTA_OAUTH_REDIRECT_URI,
  ALTA_RUNS_PER_ACCOUNT, ALTA_RUNS_TOTAL, ALTA_IMG_WORKERS, ALTA_IMG_BATCH,
  MONITOR_INTERVAL_S, AWS_SQS_QUEUE_URL, PUBLIC_BASE_URL, APP_BASE_URL.

### Running locally for a visual check (no credentials)
- The app needs only a `config.json` at `$CONFIG_PATH` (`build_app()` reads
  it at boot); the SQLite database is created beside it. No `APP_PASSWORD` =
  no login; no `PORT` = binds 127.0.0.1 and picks a free port from 5000.
- Dev runtime data lives OUTSIDE the repo in
  `D:\AltaScraper-wt\claude-environment-devdata\`, one folder per data set:
  - `sandbox\` — no keys; two fake credential-free accounts (`dev_test_a`,
    `dev_test_b`, read-only: no Amazon calls, no publishing) and TEST drafts,
    one SKU shared by both.
  - `local-copy\` — a COPY of the old checkout's data, made by the OWNER running
    `migrate_local_copy.py` (Claude does not open credential files or
    databases). The copy's config gets dev overrides: `repricer_enabled` and
    `asin_monitor_enabled` off, `google_service_account_json` blanked, paths
    into `D:\AltaScraper` re-pointed or blanked; Slack (`notify.json`),
    `service_account.json`, `users.json` are not copied. The database is a
    read-only-sourced SQLite backup copy.
- Start with `devdata\start_dev.ps1 -Data sandbox|local-copy`: sets
  CONFIG_PATH, clears PORT/APP_PASSWORD/ALTASCRAPER_DB (binds 127.0.0.1),
  refuses if the database would not be that data set's own, logs into the
  data set folder. `.app_port` is written in the worktree (gitignored).
- Never point CONFIG_PATH at `D:\AltaScraper\config.json` from a development session.

## 14. Tests

About 362 standalone scripts at the repo root (`test_*.py`, `test_*.js`), run
by `run_tests.py` (each file its own subprocess; `probe_*.py` live-API scripts
skipped; lock file against two runs; TMP redirected). No CI.

Since Milestone 1 (28 Sep 2026):
- **A test tests the tree it lives in.** Python tests resolve paths from
  `_REPO` (their own folder); JS tests from `__dirname`. No test may name
  `D:\AltaScraper` -- 141 did, and silently tested the main checkout.
- **Safe by default.** The runner gives every test file its own empty database
  (`ALTASCRAPER_DB`) and a config path that does not exist (`CONFIG_PATH`),
  under the run's scratch folder. A test that sets these itself still wins.
- A test that cannot start without a config.json is reported as "could not
  run", by name, not as a failure. Exit code 125 means "could not run".
- **No test needs the owner's data** (28 Sep 2026): the seven that did now
  build their own temporary config and database.

Browser check -- `py -3.11 tools/browser_smoke.py [--only a,b] [--shots DIR]`
(28 Sep 2026). Serves the real app in-process on a TEMPORARY copy of the
credential-free `sandbox` data set (refuses to start if the database would be
anywhere else), blocks every non-local request, and drives headless Chromium
(Playwright) through every screen in both fake accounts. It seeds each
account's copy with marker orders/sales/ads rows and a marker title on the SKU
both accounts share, then fails on: a script error, a console error, any 5xx,
one account's marker visible under the other (normal switch, switch while
loading, two tabs, the product page), a request from a tab that names no
account and is not on its reviewed app-wide list, or an unlabelled field. It
also reports the slowest server calls. ~10 minutes for all screens; not part
of `run_tests.py` because it starts a browser.

Page weight -- `py -3.11 tools/asset_report.py` (read-only): every script and
stylesheet the dashboard loads, raw and gzipped.
- Undefined-name guards: `test_no_undefined_names.py` (Python, pyflakes) and
  `test_no_undefined_js_calls.js` (browser calls to functions defined nowhere).

Many tests still assert source text rather than behaviour; about 11 need the
owner's real data. Details and the baseline: docs/known-issues.md "Tests".

## 15. Milestone 4 — where the big files went (28 Sep 2026)

Code MOVED word for word, never rewritten; every old name still resolves
(`dashboard.X is new_module.X`). Test support: tests_support/README.md.

- **Styles:** `static/css/dashboard.css` = base; the rest is
  `static/css/dashboard/01-shell.css` … `21-density.css`, linked right after it
  in number order (together they ARE the old file — do not reorder).
- **Page:** `templates/dashboard.html` = shell; each screen is
  `templates/screens/sec_<name>.html`, pulled in with `{% include %}`.
- **Browser helpers:** `static/js/core_util.js` (esc, toast, badges), loaded
  just before listings.js.
- **Sales:** `sales.js` + `sales_breakdown / _week / _campaigns / _live / _cards / _grid.js`.
- **Listings:** `listings.js` + `listings_selection / _search / _dups / _summary /
  _ppc / _grid / _drawer_build / _rows / _panels / _open.js`.
- **Repricer:** `sourcing.js` + `sourcing_actions / _dialogs / _chart / _detail /
  _menu / _bulk / _row / _row_actions.js`.
  Every split JS file loads right after its original; a one-line pointer marks
  each old spot.
- **dashboard.py helpers (batch 7):** `domain/report_parsers.py`,
  `api/google_drive.py`, `domain/image_bytes.py`, `listing/subfields.py`,
  `domain/cogs_estimate.py`, `listing/patches.py`. Only functions that need
  nothing of dashboard.py's changeable state moved; anything reading
  `CONFIG_PATH`, `_state` or `_cfg` stayed, because tests (and the app) replace
  `dashboard.CONFIG_PATH` at run time and a moved copy would not see it.
