# Architecture audit and modernization plan — 29 Sep 2026

Owner brief: read.txt #8 (deep architecture modernization after Milestone 4;
Direction A UI migration paused, still approved). Read-only audit of the code as
it is after Milestone 4, then a pragmatic target and small behaviour-preserving
batches. Nothing here changes a business rule.

Evidence: a scripted scan of every Python module (imports, route sizes, raw SQL,
HTTP calls, module state, context sources) plus four feature maps (Listings /
PDP / generation; Orders / Sales / Finance / Inventory; Repricer / PPC /
Images-AI; Accounts / Auth / Jobs / Integrations). File:line references were
taken on commit 593433a.

---

## 1. The architecture as it is

**Shape.** One Flask app built by `dashboard.build_app()` (3,228 lines after
Milestone 4). 80 route modules registered by injection (`register(app, *, deps)`);
123 `domain/`, 39 `listing/`, 12 `data/`, 10 `api/`, 9 `monitor/`, 4 `auth/`,
4 `config/` modules. The listing engine `amazon_listing_generator.py` runs as a
subprocess (`__main__`). Browser code is ~150 classic scripts sharing one
global scope.

**What is healthy (keep):**
- Route wiring by injection; no core module imports `routes/` (0 backwards imports).
- One global permission doorman (`auth/guard.py`), first-match rules, every
  named account checked.
- Config writes all go through `config/settings.write_raw` (atomic).
- The account-isolation layer from the earlier batches: `domain/request_account`,
  `routes/scope.py`, `reqscope.js`, `screenstate.js`, the browser smoke harness.
- Domain modules own their own SQL through `data.db.get_db` (246 statements in
  `domain/`) — there is no repository layer, and for this app a module per
  feature owning its tables works; the problem is the SQL that leaks into routes.

**Measured debt:**

| # | Problem (brief numbering) | Evidence | Concrete AltaScraper cost |
|---|---|---|---|
| P1 | Business logic in routes (1) | 381 handlers; 109 > 60 lines, 35 > 120. Largest: `live_catalog` 682, `rows_all` 427, `run` 383, `miles_run` 375, `ppc_deliverable` 272 | Rules (floor checks, VAT, week windows, date parsing) cannot be tested without Flask and are copied when a second screen needs them |
| P2 | Raw SQL in routes (3) | 22 statements: `finance_routes.py` 6, `sales_routes.py` 2, `orders_routes.py` 1, `listing_routes.py` 2, … | The same table is read with different filters in two places |
| P3 | External calls outside the integration layer (4) | Direct SP-API in routes (`orders_routes.py:577,696`, `listing_routes.py:542`, `live_routes.py:986`, …); ~23 client-construction sites; 9 credential builders; Anthropic built in ≥13 places (`aplus_routes.py:222`, `ppc_routes.py:509,605`, `listing_routes.py:1083`, …) | Two answers to "what was in this order" (UK vs US fallback differ); spend tracking relies on a global SDK patch |
| P4 | The engine used as a library (7, 8) | 7 core modules import `amazon_listing_generator` (`listing/flags.py`, `product_type.py`, `regen.py`, `sync.py`, `data/input_import.py`, `input_row.py`, `domain/generate_plan.py`) | Importing it loads the whole generator and its runtime-mutable globals into the web process; 4 of the 7 only want helpers that now live in `listing/` |
| P5 | A route importing `dashboard` for convenience (7) | `routes/weekly_routes.py:346` `import dashboard as _dash; _dash._client()` | Run as `python dashboard.py`, this loads a SECOND copy of the app module with its own `_state` |
| P6 | Account context from the server's open account (11) | Hand-rolled `b.get("id") or _state.get("active_account_id")` in `live_routes.py` ×6, `optimize_routes.py` ×4, `cogs_routes.py` ×3, `accounts_routes.py` ×2, `genimage_routes.py` ×2; routes reading `active_*` directly: `inventory_routes.py:236,405`, `revenue_routes.py:61`, `tracking_routes.py:38`, `expenses_routes.py:31`, `cogs_mode_routes.py:66`; three name-lists for "which param names an account" (`guard.WORKSPACE_PARAMS`, `request_account.ACCOUNT_KEYS`, `named_any`) | A second tab that omits the id acts on whichever account the other tab opened; the rule lives in ~20 copies |
| P7 | Shared mutable state borrowed across a request (5, 6) | `/schema/<pt>` sets `_state["active_marketplace"]` for the length of the request (`listing_routes.py:1998-2039`) | A concurrent request reads the borrowed marketplace (known S11, only the restore half was fixed) |
| P8 | State owned by the wrong module (6) | `_IMG_JOBS`/`_AF_JOBS` tables live in `dashboard.py` but are only used by `domain/image_jobs.py` / `autofix_jobs.py` (via `_app`); `_INV_ALERT_COUNTS`, `_INV2_CACHE` in `dashboard.py` used only by inventory | Owner of the state is not the feature that uses it |
| P9 | Duplicate / competing paths (9, 10) | Generator CLI args built twice (`routes/listing_routes.py` `/run` vs `listing/run_command.py`, already drifted); two image-push routes; five price-push paths, two bypassing `api/amazon_listings.patch`; three VAT formulas; two VAT-rate readers | Fixes land in one copy only (the dropship branch already differs) |
| P10 | Background jobs and the open account (12) | Timers loop accounts explicitly (good). Image jobs fall back to the open account when the stamp is empty (`image_jobs.py:391,425`); ASIN monitor hard-codes `jack_uk` when unset (`monitor/checker.py:30`) | A job can act for the account the last browser opened |
| P11 | Dead paths kept on purpose | `/inventory/build` returns 410 then unreachable code; `dashboard._fetch_fba_inventory_via_spapi` only reachable from it; `inventory_sync` job can never succeed | Owner rule: do not delete dead code for cleanup alone; do not switch on scheduled inventory sync |

Error handling (16) is mostly consistent (`uiError`, `_mh.explain`, `{ok:false,error}`) and not a batch.
Monkey-patching in tests (17): `D._load_schema`, `D.CONFIG_PATH`, `gen.seller_id_for` are
patched because those names have no injection point; noted per batch below.

---

## 2. Target architecture (pragmatic)

```
browser (static/js)  ->  routes/<feature>_routes.py  ->  domain/<feature>*.py  ->  data (data.db / data.store)
                                   |                            |
                                   +--> routes/scope.py         +--> api/<service>.py  (SP-API, Ads, eBay, Anthropic, Drive)
                         (who: account, marketplace)
```

- **Routes**: read the request, resolve WHO (`routes/scope.py`), call a domain
  function, shape JSON. No SQL, no SDK clients, no business rules longer than a guard.
- **Domain**: the rules, per feature; owns its tables' SQL; takes account and
  marketplace as ARGUMENTS, never reads the open account.
- **api/**: the only place that constructs an external client or builds credentials.
- **State**: a module that uses state owns it (job tables in the job module);
  process-wide caches are named and documented; the open account is a UI
  convenience, never a default for writes or jobs.
- **Engine**: `amazon_listing_generator.py` is a top-level runner; the web process
  imports `listing/` modules, never the engine.
- **Dependency direction**: routes -> domain/listing -> data/api; nothing below
  routes imports `routes/` or `dashboard`.

What is NOT forced: no repository layer for its own sake, no service classes, no
framework change, no rewrite of working screens.

---

## 3. Migration batches (lowest risk first; each: baseline -> characterization -> change -> tests -> browser smoke where relevant -> review -> commit; revert on unexplained change)

| Batch | Problem | Change | Risk | Proof / tests | Rollback |
|---|---|---|---|---|---|
| A1 | P4 | The 4 modules that import the engine only for helpers now in `listing/` import them from `listing/` directly (`infer_product_type`, `build_sku`, `read_input_sheet`, `resolve_account_brand`); `listing/sync.py` gets the data dir without loading the engine | Low | Same function objects (`listing.x.f is G.f`); suite | one commit |
| A2 | P5 | `weekly_routes` receives `_client` by injection instead of importing `dashboard` | Low | suite; weekly routes tests | one commit |
| A3 | P8 | Job tables and inventory caches move to the modules that use them (`image_jobs`, `autofix_jobs`, inventory); `dashboard` re-exports the same objects | Low | identity of objects; suite; harness | one commit |
| A4 | P7 | `_load_schema` (and the schema helpers) take an explicit `marketplace`; `/schema` passes it instead of borrowing `_state`; default keeps today's behaviour for every other caller | Medium | characterization of `/schema` payload for UK/US; concurrent-request test | one commit |
| A5 | P6 | ONE helper for "the account this request names, else the open one" with exactly today's semantics; the ~17 hand-rolled copies call it (no semantic change); the three param-name lists documented as one table | Low-medium | per-route characterization (same id resolved for id/no-id); two-tab harness | one commit |
| A6 | P2 | Raw SQL in routes moves, statement for statement, into the feature's domain/data module (finance, sales, orders, listing) | Low-medium | same SQL text; route tests with fixtures | one commit per feature |
| A7 | P3 | One factory for SP-API clients and one for Anthropic clients in `api/`; call sites construct through them (same arguments, same key source) | Medium | identical constructor args (mocked SDK); suite | one commit per service |
| A8 | P1 | The largest pure-rule blocks leave routes for domain functions: finance contribution rules, orders profit loop, sales windows, sourcing rules validation, PPC deliverable file-sorting/date parsing | Medium | characterization of each route's JSON on fixtures before/after | one commit per route |
| A9 | P9 | Generator CLI args built once (`listing/run_command.py` becomes the one builder; `/run` calls it) — ONLY after a characterization shows which of the two drifted behaviours is live, and keeping the live one | Medium | args equality for every mode on fixtures | one commit |
| A10 | P10 | Jobs: document and assert that every job names its account; image jobs refuse to fall back silently only if that is behaviour-identical today (else recorded for the owner) | Medium | job tests | one commit |

Not in these batches (recorded, owner decisions or disproportionate risk):
consolidating the 9 credential builders (touches every Amazon call), the five
price-push paths (write paths; each differs in validation), the VAT formula
copies (money rules — record, owner to confirm the single formula), deleting dead
inventory code (owner rule), fixing `inventory_sync` (owner rule: no scheduled
inventory sync), and `build_api_attributes` (separate plan:
`docs/plans/build-api-attributes.md`).

---

## 4. Bugs found, kept separate

1. `inventory_sync` scheduled job can never succeed (JSON `id` vs form
   `account_id`; reads keys the route never returns) — `data/scheduler.py:331-338`.
   Not fixed: the owner decided not to enable scheduled inventory sync.
2. `/schema/<pt>` borrows the server-wide marketplace for the request (race) —
   fixed structurally in batch A4 because it is an account/marketplace safety issue.
3. `orders_routes` fetches order items itself with a UK fallback while
   `orders_live.order_items` falls back to US — two answers for an account with no
   default marketplace. Recorded; consolidating it changes a fallback, owner to confirm.
4. `/run` and `listing/run_command.py` build different generator arguments (dropship branch).
   A9 (29 Sep) made both use the same `account_args` / `api_scope_args`; argv is
   identical for every account shape. The one remaining difference is
   `build_api_run_args`'s no-account "dropshipping" branch, which reads
   `dropshipping_*` config keys the code says were never set. Left as it was;
   removing it is the owner's call (Rule 1 retired that workspace).
5. Writes via `config/settings.write_raw` do not clear `dashboard._state["cfg"]`
   unless the route calls `_reload_cfg` — possible stale config after a save.
6. `sales_summary` (a GET) writes `order_lines` through `order_cogs.freeze_range`.
7. `/preview/enqueue` does not refuse when no account is open, where `/run`
   does ("No account is open"). A queued preview then reaches the generator with
   no `--account-id`, whose credential fallback is the global block. Found during
   A9; not fixed there (a behaviour change on a write-adjacent path; owner to
   confirm the refusal should match `/run`). NOW FIXED (owner decision 1,
   943fb60; test_preview_needs_account.py).
8. An image batch started with NO account open is stamped `_acct_id=""`, and
   the worker then falls back AT FINISH TIME to whatever account is open
   (`domain/image_jobs.py` ~399, and the Drive copy ~433) -- so an image can be
   filed under an account opened after it started. Found in A10; not changed
   (owner to confirm: refuse at enqueue, or file under the shared root). NOW
   FIXED (owner decision 2: refuses at start, deb7329;
   test_image_batch_needs_account.py).
9. The ASIN monitor defaults to `jack_uk` when no account is configured
   (`monitor/checker.py` `_MONITOR_ACCOUNT_DEFAULT`). Recorded (P10). NOW FIXED
   (owner decision 3, b0a9c6d; test_monitor_needs_account.py).

## 5. Batch notes

- **A4** (`/schema` marketplace). The `/schema` JSON is unchanged for every input
  (proven: the new test run against the pre-A4 code fails only on the race check).
  One hidden side effect is gone with the borrow: `_state` is a `WorkspaceState`,
  so for a signed-in user with a `uid` the old code wrote the per-user session's
  `active_marketplace` and then "restored" it from the process-wide value, which
  could leave that user pinned to a stale marketplace and added a Set-Cookie to
  the response. Nothing is written now.
- **A5** (account fallback). `id_or_open` is exactly the hand-written expression;
  only the 15 identical copies moved. The other reads of the open account differ
  (str(), strip(), None, ?account=) and stay with their routes; a guard caps them.
- **A6** (SQL out of routes). Finance, Sales, Orders and the listing edit's reads
  moved statement for statement; 19 calls in 11 smaller route files remain,
  capped per file by `test_routes_sql_ceiling.py`.
- **A7** (clients). One Anthropic constructor. No SP-API factory: see the commit;
  the credential builders are the real duplication and stay out of scope.
- **A9** (generator args). One builder for the account and Preview/Submit
  arguments; equivalence proven against the pre-A9 code over every mode and
  account shape.
- **A10** (jobs). Every job already stamps its account at start (image batch,
  auto-fix, preview queue, /run); `test_jobs_name_their_account.py` pins it.
  No code change; the two remaining fallbacks are bugs 8-9.
- **A8** (rules out of routes). Finance's previous-window and overhead panels
  moved word for word to `domain/finance_view.py` (full JSON snapshot identical
  before/after). Stopped there on purpose: the other large blocks
  (`dashboard_routes._build_summary`, `variant_routes._plan`, `live_catalog`,
  `rows_all`, `miles_run`, `ppc_deliverable`) read sheets, the database and
  closures through 5-15 free names -- moving them is a rewrite, not a move.
  Intentional debt, per route, for later.
