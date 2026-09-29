# Known issues

Open problems only. Each entry says how sure we are:

- **CONFIRMED** — reproduced, or pinned by a failing test
- **READ** — seen by reading the code, not run
- **BLOCKED** — the cause is outside the code (credentials, roles, accounts);
  only the owner can clear it

When an issue is fixed, delete its entry here and add a line to
docs/changelog.md when it deploys. Claude maintains this file automatically.

---

## Suspected bugs (from the 27 Sep 2026 analysis — all need verification)

1. **FIXED ON THE DEV BRANCH (Milestone 2, 28 Sep 2026) — a lister could submit
   to Amazon.** Proved by the master audit; now `/run/api_submit` needs
   `publish` (RULES) and so does `/preview/enqueue` with `mode: api_submit`
   (BODY_RULES). A streamed `/run/*` counts as a write, so a view-only user
   cannot start one either. test_guard_every_account.py section 7.
2. **FIXED ON THE DEV BRANCH (Milestone 1, 28 Sep 2026) — `_state_account` was
   never defined** (routes/listing_routes.py, `run()`). Any request with no
   account open raised NameError. Now: no fallback to the shared state (which the
   comment there forbids); an empty account runs as `_no_account`, nothing to
   act on. Guarded from returning by test_no_undefined_names.py. After the
   Milestone 1 review: with no account open the run is now REFUSED with a
   message, not run as `_no_account` (the generator's credential fallback is the
   global block, jack_uk's). test_profit_review_fixes.py section 16.
3. **FIXED ON THE DEV BRANCH (Milestone 3, 28 Sep 2026)** -- the job now returns
   "skipped" unless `monitor/schedule.is_on()`; test_scheduler_jobs.py. Original
   report: **the 4-hourly `asin_monitor` scheduler job ignores the monitor's own
   on/off schedule.** `data/scheduler.py` registers it and `register_jobs()`
   calls `start()` at boot; the job calls `checker.check_all()` directly, which
   honours only `asin_monitor_enabled`, not `monitor/schedule.py` (off by
   default, per the owner's 18 Aug decision). Verify with: scheduler status on a
   running app, or a unit test of the job function.
4. **READ — Some runs and submits name no account**, so they act on whatever the
   session last selected: single-listing Submit (`rqEnqueue`, runqueue.js),
   autofix.js `/run/api` and `/autofix/start`, Live-tab verify
   (miles_template.js `/run/api_verify`). `mismatch_for_write` only refuses when
   an account IS named.
5. **FIXED ON THE DEV BRANCH (Milestone 3, 28 Sep 2026) — another account's data
   could show after switching accounts.** Every screen's held data, busy flag
   and the SKU-keyed caches (LIVE_MIRROR, COGS_LOCAL, LISTING_METRICS/LR_*,
   SCHEMAS, PPC per ASIN) are reset on a switch (`screenstate._screenResetHeld`);
   loaders check `screenStillIn()` after each await; the Dr PPC draft cannot be
   saved into another account; returns/hourly/traffic name their account.
   test_switch_drops_old_replies.js (22 checks; the first 15 all fail on the
   old code). After the Milestone 3 review also: SQP, tracker alerts, Dr PPC
   campaign detail, repricer rules/families (which pre-filled B's dialogs with
   A's floor), schema requests in flight, and the two paths that moved the
   marketplace without the switch reset.
   S9 is fixed where a load draws its failure through `uiError` (Hourly,
   Traffic, Sales, Listings); screens that still draw failures their own way
   stay "fresh" for 10 minutes after one. The stale `finally`/`catch` is fixed
   for Hourly, Traffic, the PPC console and listing metrics (non-design batch 1).
   STILL OPEN: S10 (the shared-password owner and background threads share one
   process-wide selection). The four older "still the same account?" checks
   are LEFT AS THEY ARE ON PURPOSE (28 Sep 2026): submit.js stillMine and
   miles_template stillHere guard loaders that the switch itself calls again,
   so the shared check's generation would drop replies nothing re-requests;
   orders loadId is already reset by the switch (screenstate.js); sales
   _sFetch is account-only by design. Revisit only with a test per screen.

## Left open from the Milestone 6 UI review (28 Sep 2026)

- Bulk GTIN / Approve / Delete pin the ACCOUNT only; the repricer loops also
  stop on a MARKETPLACE change. Drafts are stored per account, so this is
  probably harmless -- not verified. One shared pin helper would settle it.
- The long (fallback) order-cost form pre-fills the saved cost and clears it
  without asking; the compact panel now asks. Emptying a pre-filled box is a
  deliberate act, so low risk.
- `jsArg` lives in users.js, loaded after its callers; it works because every
  call happens at render time. A core escaper belongs in an early file.
- `jsArg(j.data_url)` runs six regex passes over a multi-MB base64 image per
  card (genimage.js, howworks.js) -- a performance point, not a fault.
- Seven screens keep their own currency-symbol rule (see the design proposal,
  decision 3).
- Repricer rows use `.rp-was`, `.rp-pen`, `.rp-held`, `.rp-m2y` and no CSS
  styles them; the PPC charts compute reference lines that are never drawn
  (docs/proposals/liked-pages-anatomy.md). Recorded, NOT restyled -- design
  work is parked by the owner (28 Sep 2026).

## Left open from the Team slice 1 reviews (29 Sep 2026)

Fixed in the slice: Team gated by manage_users alone (users.js SECTION_PERMISSION /
sectionLevel, matching guard `/users`); unknown account ids shown, never dropped;
summary cleared on loading/error; "Invite expired" filter; one `_rolePreset`.
Left open (READ by the reviewers, not fixed):
- **Inherit + role (low, server, pre-existing).** `auth/users.py` feature_level
  checks ROLE_FEATURES[role][page] before the parent area, so a page set to
  "Inherit (sales)" resolves to the ROLE's level, not the parent's the editor
  shows. The new role picker makes this reachable on existing people.
- **A stored user with no role becomes "viewer" on the next save (low).**
  `public()` reports a missing role as viewer; feature_level treated it as
  lister. Only hand-edited/legacy records; not checked whether any exist.
- **Two editors for page access (owner decision).** Team's editor still has
  "What may they SEE?" and accounts; User permissions edits the same settings as
  a grid. Wording now says both do; trimming one is a behaviour change.
- **Team / User permissions nav icons nearly identical** (`ti-users` above
  `ti-users-group`); changing the permissions icon needs the owner's OK.
- **"Which workspaces?"** in the add form / editor vs "Accounts" on the rows.
- **`#usersmodal` markup is now unreachable** on the dashboard (the Users button
  opens Team); browser_smoke opens it by class to test dialog.js. Deleting it
  needs approval.
- Permission badges are `db-chip`, so mobile.css gives them a 34px min height on
  phones (older code; not visually verified).

## Wrong "who did it" — FIXED on the development branch (7458fa4), not in production
(found 29 Sep 2026 while designing the activity log; all three now use
`domain/job_owner.label`; test_who_labels.py)
- `routes/drppc_console_routes.py:63-69` `_who()` calls `auth.guard.current_user()`,
  which does not exist; the except swallows it, so Dr PPC settings/plans/rules/
  events store who = "". CONFIRMED by reading.
- `routes/sourcing_routes.py:963` reads `session.get("user")`, never set, so a
  manual repricer price records manual_by "". CONFIRMED by reading.
- `dashboard.py:237` reads `session.get("email")`, never set; the selfcheck error
  log falls back to the uid. CONFIRMED by reading.
The central activity log (Employee Performance) resolves the actor one way for all
(`domain/job_owner.person` / `label`).

## Deployment — found in the 29 Sep 2026 audit
- `run_status.json`: the generator writes it in the CODE folder
  (listing/run_status.py:48; amazon_listing_generator.py passes no app_dir) but
  routes/listing_routes.py reads it from the CONFIG folder. On the server (/app
  vs /data) the reader may never see what the writer wrote. READ, not traced.
- `/healthz` checks nothing; `requirements.txt` is unpinned (manifest §10).

## Open account — left open after the 4G fixes (29 Sep 2026)
Fixed: browser callers now name the account on /clear_empty, /rescan/*,
/approve, /edit, /brand/*, the Miles and brand streams; the brand routes read
the named account; /clear_empty and /rescan/apply refuse with none named; the
brand run and Miles streams count as work in the guard. Still open (READ):
- `/brand/run` never passes the account to the generator: output goes to the
  "dropshipping" store with the global credentials (jack_uk's) and brand
  settings. Owner decision (owner-review #24).
- Miles: `_MILES_STATE["items"]` (the uploaded item list) is process-wide, and a
  new stream re-attaches to whatever run is active -- tab B can see A's run log,
  and a list uploaded in B can be run into A's sheet.
- `howworks.js setStatus` and `autofix.js applySuggestion` read the account at
  send time (not pinned across `await ensureCardTab`).
- The rescan preview and apply are not pinned to the same account.
- `enterWorkspace` never clears CUR_ACCOUNT, nor /view/set the open account
  (view workspaces only).

## dashboard.py — remaining feature code (4D review, 29 Sep 2026): intentional debt
3,737 lines; build_app (839) is composition and stays. The largest feature
blocks -- _resolve_fields (416), _save_miles_templates (310), _load_schema (238),
the Google Drive group (_drive_service/_drive_upload_image/_drive_map_*,
~150), _variation_schema (131), _fetch_fba_inventory_via_spapi (121, dead by
owner rule) -- each read app state (_cfg, _state, SCOPES, the media-root helpers)
through 3-10 module globals (AST scan). Moving them is an injection redesign, not
a verbatim move (refactor-move step 2), with no behaviour gained; the master
brief says not to chase line count. Left in place; move one only when a feature
change needs it, via register injection.

## Money formulas — audited 29 Sep 2026 (active/map-4H-vat.md)
- The VAT-out formula `gross*r/(1+r)` is the same everywhere (rounding differs:
  per order vs per window -- pennies). Fixed: the account form saving an
  unanswered VAT rate as 0 (a0d07ba); a 100% rate refused.
- NOT duplicates: `sales_data.vat_rate_for` is the lookup, and
  `unit_profit.account_vat_status` reads the file and calls it -- one rule.
- Intentional debt: `order_profit.for_lines` works its fee on net revenue, but
  its money figures are overwritten by `period_money` in its only caller
  (for_period) -- no screen shows them; fix only if a new caller uses them.
  The margin-target save check re-derives the limit with the same `_kept` VAT
  factor as `floor_from_target` -- consistent, cost-independent sanity check.
- Owner decisions: generator profit/floor leave VAT in (owner-review #19);
  fee VAT on non-VAT accounts not invoice-verified (#20).

## Price writes — left open (29 Sep 2026 map: active/map-4F-price-writes.md)
- `/optimize/push` (listing/patches._build_patches) writes a price with an
  INVENTED offer shape (no marketplace/currency/audience), no read-before-write,
  no floor, no usable_price check, productType from the browser, VALID counted
  as success, and records nothing. Fix belongs with the shared price core and
  the listing-payload-guardian. READ.
- A new listing submitted to the US sends purchasable_offer currency "GBP"
  (listing/builder.py _offer) while list_price follows the marketplace. Payload
  change: needs the raw US schema/reply first (Rule 4). READ.
- Workspace publish gate differs by path (price editor: seller_scope_allowed,
  which ignores can_publish False; repricer box and job: none; optimize/submit:
  can_publish). READ; owner to confirm the intended gate.

## Activity log — left open (29 Sep 2026 reviews)
- Some callers post a catalogued write naming NO account (`autofix.js` /edit,
  `howworks.js` /approve; `_srcBody`'s `__all__`), so that work is filed under
  no account and only a viewer of every account sees it. Existing Rule 14 gaps
  in those callers, not in the log. READ.
- Auto-fix posts /edit in its own loop, so its automatic edits count as edits by
  whoever started it. READ, not traced further; owner may want them separate.
- An upload's activity row does not link to its upload_log entry (no upload id
  reaches the hook). READ.
- The hook parses a JSON body again (third parse for large base64 uploads);
  the insert happens before the reply is sent (busy_timeout 30s under a long
  write lock). READ, low.

## Orders "To buy" -- left open (29 Sep 2026 reviews)
- **"Mark as bought" is still offered when the records could not be read.**
  Deliberate: an unreadable table should not stop someone recording a purchase.
  The cost is a possible second record on an order already recorded; Remove
  undoes it.
- **"Which marketplace is this account's" still has copies.** The Orders
  WRITES share domain/order_scope.py (purchases, dispatch); it sits beside
  orders_routes._marketplace, tracking_routes._account_marketplace and
  routes/scope.marketplace. Its fallback equals orders_routes'; it adds "the
  asked marketplace must be one of the account's own". Folding the other three
  onto it is the remaining fix (tracking_routes also falls back to the open
  account, which order_scope never does).
- **Dispatch to Amazon (/orders/ship/confirm) is built and OFF.** Turning it on
  or off is the owner's: config `ship_confirm_enabled: true` (read fresh on
  every send; no restart). Never sent for real yet; every carrier goes as
  carrierCode "Other" + carrierName until a code is seen accepted
  (domain/ship_confirm.py). Whole unshipped orders only (a partly shipped one
  would need a second packageReferenceId, not yet seen); Transparency items are
  refused. Still to capture on the first real send: Amazon's reply, whether
  "Other" is accepted, and the UK carrier-code list.
- FIXED 29 Sep 2026 (not yet in production): **the Orders list on a phone
  squeezed to one letter per line** with an order open (the table stayed a
  table while its rows were cards; static/css/orders_panel.css), and **the top
  bar was 467px wide at 360-430px**, pushing the page sideways (account chip
  would not shrink, "Users" kept its word; static/css/dashboard/09-mobile-860.css).
  On a phone the account name is now cut with "..." (e.g. "DEV Test ...").
- **getOrderItems is read in four places** (domain/orders_live.order_items, two
  in routes/orders_routes, api/amazon_orders_ship.order_items). The last is the
  only one that follows NextToken pages and keeps OrderItemId; folding the
  others onto one reader is the fix.
- **Times from tracking are stored without a time zone** (domain/tracking.add),
  so the browser may show them an hour out in British Summer Time on a UTC
  server. Purchase records store UTC with its offset.
- test_order_sources_ui.js, like test_order_panel.js, fails when run on its
  own (`_srcDeliveryLine is not a function`) and passes under run_tests.py.

## Fixed on the development branch, NOT yet in production

On `claude-environment-setup` (local, not merged or deployed — production still
has these until the owner merges):
- **Non-design batch 2: two tabs (28 Sep 2026).** Found by the new browser
  check (tools/browser_smoke.py: tab 1 on account A while tab 2 switches the
  server to B). The server has ONE open account for every tab, and a class of
  routes used only that: the image library, uploads (and their Drive copy),
  image generation and its Stop, Variations (read with the open account's
  credentials, could publish to it), stock pushes, auto-fix, Amazon Ads keys,
  the input queue, Drive uploads, Miles runs, variant queueing, sync, and the
  rows on the database (a pull_row could write A's Amazon data into B's
  same-SKU row). Now: `_active_account()` and the database rows follow the
  account the request names (domain/request_account.current / named_now);
  the browser names its account (and marketplace) on those paths (reqscope.js);
  /media/delete refuses another account's folder; image jobs are labelled and
  filed under the requesting tab's account and use its instructions and brand;
  auto-fix refuses up front on a mismatch. Also: 25 form fields got accessible
  labels (no visual change).
  LEFT OPEN (low, from the reviews): the image worker records the Drive map
  under the open account, so deleting that image later can leave its Drive
  copy behind; /edit's "add a live SKU as a row" step takes the open account's
  marketplace when the account came via ?account= (only hand-built requests
  do that); a single write after a confirmation dialog reads the account when
  it is sent (a switch can only happen meanwhile via back/forward) -- the
  brand reference photo and the input-upload log's marketplace were fixed in
  batch 7; Miles runs (EventSource, not fetch) stay on the open account,
  as before; /submit/precheck always returns nothing (it calls _records()
  without a sheet -- pre-existing, not account-related).
- **Non-design batches 8-9 (28 Sep 2026).** The pre-submit warning about main
  images Amazon cannot use NEVER fired (/submit/precheck read rows without a
  sheet and for keys a row does not have). It now works, for the tab's account
  and only the listings being submitted, and says what the submit will actually
  do -- the rule is domain/image_urls (fetchable / is_ours / main_image_problem),
  which the generator's own helpers now call (verified to answer exactly as
  before for every input). Load failures on Finance, the ASIN monitor and Sync
  use the shared error box. Thirteen actions that write after a confirmation
  dialog (incl. the Repricer's push-now and minimum-price upload, stock bulk,
  pushing attribute changes to Amazon, deletes) note the account before the
  dialog and refuse if it changed; test_loops_pin_account.py guards both this
  and write loops.
  LEFT OPEN (low): an EMPTY main image gets no warning though the listing goes
  up without one (a new warning would be a behaviour change); the generator's
  "Skipping main image" console message is unreachable (it reads the value
  after popping it) -- pre-existing, in the protected generator, not changed.
- **Batches 11-12 (28 Sep 2026).** The Drive map (which Drive file backs which
  app image) now lives in the account named by the image's own URL -- the image
  worker filed entries under the open account, so deleting the image later left
  its Drive copy behind (entries misfiled before this stay orphaned; they were
  never findable). JSON files written truncate-then-write in the two-line form
  the first scan missed are now atomic: the generator's MODEL-NUMBER COUNTER
  (emptied by a crash it would restart and reuse numbers), app_state.json, the
  Drive map, image instructions, Miles run metadata and item list; the test now
  catches that form. ppc_brand_terms has one reader and one writer
  (domain/ppc_view; audit A11 in part) -- the weekly screen had a second copy
  of the read.
  VERIFIED, NOT CHANGED (owner: no cleanup-only deletions): same-named escape
  helpers defined in more than one file (_aiEsc, _sEsc twice in sales.js,
  _esc) all escape identically, so which copy wins at load time changes
  nothing.
- **Batch 10 (28 Sep 2026): audit A16 done.** The Brand panel's markup is
  templates/brand_panel.html and its script static/js/brand_panel.js (moved
  byte-for-byte, then its native alert/confirm, hard-coded colours and one
  unsafe inline handler fixed under the standing JS rules).
- **Non-design batch 5 (28 Sep 2026): multi-step work stays in one account.**
  The listing-row editor's Save-all (which pushes STOCK to Amazon), the bullet
  save and the product-type fix loop re-read the open account on every write:
  a switch part-way sent the rest to the new account's same-SKU listing. They
  now take the account once (before the stock confirmation) and stop on a
  switch. A switch also forgets unsaved row edits, the Image studio's product
  and results (and stops its poll), Sales' product filter, and empties the
  panels those screens had drawn (the seeded-marker browser check caught the
  Sales product picker and the Image library list still showing the other
  account). The auto-fix worker checks the account before EVERY step, not once
  per SKU. AI spend from background jobs is billed to the job's account. An
  image's Drive title comes from its own account; its Drive copy never falls
  back to the open account's folder. Re-picking the marketplace already open
  no longer discards in-flight work.
  LEFT FOR THE OWNER: (1) the scheduled `inventory_sync` job has never worked
  -- it sends the account as JSON and the route reads a form field -- so it
  always gets a 400. The fix is one line, but it would START scheduled Amazon
  inventory reads for every account, which is new external activity; not done
  without a yes. (2) A signed-in team member's auto-fix stops at the first
  SKU ("workspace changed"): worker threads see only the shared account, not
  a person's own. Safe (it refuses rather than mixes), but it means auto-fix
  only runs for the shared-password owner, or when the shared account matches.
- **Non-design batch 3 (28 Sep 2026).** The browser check now SEEDS its
  temporary copy with orders, sales and ad rows unique to each fake account
  and fails if one account's marker is ever visible under the other -- after a
  normal switch, a switch while loading, and with two tabs. It found: B's
  Image library and Image studio listed A's products (the shared product
  picker was fetched once and never forgotten). Fixed; test in
  test_switch_drops_old_replies.js.
  **OPEN, UNEXPLAINED:** twice in full runs the Sales screen showed the other
  account's marker (once A under B, once B under A in tab 1). Not reproduced in
  eight targeted runs (single-tab B->A at eight delays, two tabs x 8 rounds
  capturing every response, six Sales/Listings/Traffic runs); every Sales
  request goes through _sFetch, which drops a reply whose account changed, and
  no tab-1 response ever carried B's data. The harness now names the element
  a leaked marker is drawn in, so the next occurrence says where.
- **Non-design batch 1 (28 Sep 2026).** A failed load is now drawn as a
  failure (pageui.js `uiError`: red, `role="alert"`, a Try again button) on
  Hourly, Traffic, Sales and Generate instead of the grey "no data" box, and it
  marks the screen stale so coming back retries (audit S9).
  Traffic's sort arrows were mojibake ("â–´"); its legend dots now use the same
  colours as the donut. The Sales chart key showed the bars in a different
  colour from the bars. The Hourly, Traffic, PPC console and listing-metrics
  loaders no longer let an old account's reply clear the new account's
  "loading" flag after a switch.
  ACCOUNT ISOLATION: ten route files and the Repricer took the marketplace
  (and the Repricer the account) from the server's OPEN account instead of the
  one the page named -- two tabs could answer a US account on UK. All now use
  routes/scope. An account named in a GET body is ignored (the permission
  check never saw it). Stop acts for the tab's account and no longer ends
  another account's run through the legacy single-process fallback (audit A15).
  The seven tests that needed the owner's real data now build their own
  fixtures; the old test_real_amazon_fee changed the live fee_multipliers
  table when run in the main checkout.
  NOTE: with no marketplace sent, the resolution order is now "selected (if
  the account sells there), then default" -- the copies used default first.
  LEFT OPEN (low, from the review): (a) Repricer with "All marketplaces"
  selected: "__all__" used to match nothing; now it resolves to the account's
  default, or "" (= every marketplace) if it has none and several hold data --
  every other gate (master switch, arming, floor) still applies, and the timer
  already works that way. (b) Stop still ends another account's run whose
  slot never attached its process (the legacy fallback cannot tell whose it
  is). (c) pdp_imagegen.js polled forever after a 404 -- fixed in batch 4.
- **Milestones 4-6 (28 Sep 2026).** Cost overrides (cogs_overrides.json) and
  the Miles bundle store are written atomically -- a crash mid-write could
  empty them, and a corrupt file was then saved back as `{}`. The live
  refresher and the A+ route no longer `import dashboard` (a second copy of the
  app with a config cache nobody cleared: accounts added later were invisible
  to live catch-up until a restart). UX: an untouched order-cost box no
  longer wipes the saved cost on Save (it asks); the button after a template
  upload no longer opens the retired Generate screen; Generate no longer says
  "Nothing queued" when the queue panel simply has not been opened; toasts are
  above every overlay, announced (`role=status`), styled as errors when they
  are, and stay up in proportion to their length; a refused queue from the
  product page is now said (it vanished, and left RUN_STREAMING stuck on).
- **Milestone 2 — security and account isolation (28 Sep 2026).** From the
  master audit, each with a test: the guard now checks every account a request
  names (query, any body type, form fields, every batch row; only `id` exempt
  and only where it is a record id; `/listing/` and `/trackers/watch` no longer
  exempt) -- test_guard_every_account.py; submitting needs `publish`; streamed
  runs are writes; `/jobs/run`, `/media/recover/move`, writes to `/ai/settings`
  and `/admin/logic_settings` need `manage_accounts`; preview jobs are owned;
  bulk GTIN/arm/rule/Delete/Approve pin their account and stop on a switch, and
  ticks clear on a switch -- test_bulk_account_pinned.js; CSRF (SameSite=Lax +
  cross-site Origin refused), open redirect, sign-in fails closed when hosted,
  URL policy for user-supplied fetches, `kind` path traversal, all-account lists
  scoped to the caller -- test_security_basics.py; ~260 inline-handler XSS
  sinks (esc'd or raw values inside a quoted JS argument) converted to `jsArg`
  -- test_no_esc_in_handlers.js; shared attribute
  defaults can no longer carry a brand, name, identifier or offer into another
  account's drafts (Rule 1) -- test_defaults_carry_no_identity.py. Also fixed
  on the way: 14 routes whose `id` is a record id were refused for users limited
  to some accounts.
- **PDP account/marketplace switching** (27 Sep 2026). Proven by
  test_pdp_account_switch.js (runs the real browser code; 28 checks fail on the
  old code, all pass now): the page stayed open across an account switch and a
  save from it went to the NEW account; LIVE_ATTRS / PDPI leaked across the
  switch; late `/row` and live-attribute replies were painted over the new
  account; `detectMarketplaces` for another account silently made it the open
  one. Now an account, marketplace or workspace change closes the page and
  forgets its state (`pdpLeaveContext`, `pdpContext`).
- **Guard: `/row`, `/rows`, `/rows_all` did not check a named account** for a
  user restricted to some accounts (the `"/row"` exemption, matched with
  startswith). Proven by test_row_account_guard.py; fixed in auth/guard.py.
- **Profit screens disagreed (28 Sep 2026).** Measured on the local copy,
  jack_uk 29 Jul–27 Aug: Profit card 64.70, grid 64.43, P&L 80.76, Finance
  50.19. Now all four read 41.36 (20.0%), and P&L/Finance net profit both
  −9.36 after the 50.72 subscription. nestwell 1 Aug–14 Sep: card = P&L =
  Finance account figure = 415.10. Pinned by test_profit_agreement.py (23 of 32
  checks failed on the old code). One calculation now: order_profit.
  period_money / for_period, built on order_finance.complete_by_order_date and
  sales_data.net_proceeds_for; the step to net profit is expenses.overhead_for.
  Bugs removed on the way: the P&L's VAT line used one settled order's tax as
  the whole window's (5.83 of 41.31); Finance (order view) left VAT in, dropped
  postage, counted CANCELLED orders, and charged a multi-product order's whole
  fee to every product; P&L and expenses joined fees per order LINE (counted a
  multi-product order's fees several times); coupon/deal fees in `promo_fees`
  were missing from every figure except the P&L; reimbursements were missing
  on the order calendar; the P&L ignored coupons you funded.
  **Rules Claude chose (owner delegated, awaiting his review):** margin = profit
  ÷ sales after VAT everywhere; all measured ad spend comes off every headline
  (Finance shows unmatched spend as its own step); the grid's Profit row now
  subtracts ad spend too; the Amazon account-level charge (subscription) comes
  off NET profit automatically unless recorded as an own cost; a multi-product
  order's fee/VAT/coupon is split by each line's share of the price.
  **Stage 2 (28 Sep 2026), per-product figures.** One per-unit answer,
  domain/unit_profit.at_price (price editor, Live rows, cost editor), on
  listing/pricing.achieved (also the repricer, the Orders screen, order
  sources, supplier drift): VAT out at the account's setting, margin over the
  price after VAT. Measured: a jack_uk listing at 29.99 costing 15.10 now reads
  5.30 (21.2%); the Live row used to say 10.39 (34.6%) -- flat 15%, VAT left in.
  The account fee rate (order_profit.fee_rate) is now measured over what buyers
  PAID (VAT included), the same base as the per-product and quoted tiers:
  jack_uk 14.6%, not 17.5% of principal, which overcharged every listing priced
  on the fallback by a fifth. breakdown_for now starts at the "actual" tier
  (sku passed), so the price editor, listing row and repricer show one fee.
  **The repricer's break-even and targets now include VAT** (for jack_uk only;
  other accounts are vat_rate 0): prices it would set rise accordingly.
  PPC: one ad_profit() (was 6 copies), VAT share out, cost rate = unit cost x
  units over costed, non-cancelled lines only (it ignored units).
  Review fixes (test_profit_review_fixes.py, 6 fail on b834412): PPC net profit
  took ads off twice; any "...subscription" expense suppressed Amazon's charge;
  account charge compared two calendars; per-product charges missing from grid
  and Finance rows; Profit card ignored the product filter; settlement view
  dropped coupon fees.
  Second review fixes (28 Sep 2026, test_profit_review_fixes.py 7-11): fee
  base includes tax only on VAT-registered accounts (US sales tax excluded);
  product fee rate counts buyer-paid postage; settled history memoised
  (400 SKUs / 5000 orders: 15.4s -> 0.15s); cost editor on unit_profit;
  "Amazon PPC" expense no longer cancels the subscription charge; margin
  target save check is VAT-aware; Repricer tile/bar and PPC page JS take VAT.
  Known small gap: when the Sales grid falls back to the money calendar
  (fees older than the order history), per-product charges are not
  subtracted there (the Profit card still subtracts them).
  Milestone 1 fixes (28 Sep 2026): the repricer now refuses to price a run
  when the account's config cannot be READ (`rule["vat_unknown"]`), instead of
  pricing a VAT-registered account as if it had no VAT; the three routes that
  truncated config.json on write now write it atomically; the per-product fee
  history memo is thread-local (it could serve a stale answer when a finished
  thread's connection id was reused); Finance's estimated revenue again counts
  sales with no measured fee rate.
  **Still not changed:** the generator's stored listing profit
  (amazon_listing_generator.calculate_financials -- protected file; fee from
  the competitor ASIN or flat 15%, VAT in) and its price floor; a single
  order/unit with no cost stays blank (not shown as "too high").

## PDP (product page) — still open (27 Sep 2026)

Account scope, remaining after the fix above:
- **DEFERRED by owner (D2) — `/listing/live_attributes` ignores the named
  account** and uses `_active_account()`, and the `"/listing/"` guard exemption
  lets a restricted user name another account on `/listing/*`. Separate follow-up.
- **READ — PDP calls that name no account:** `/listing/image_slots`,
  `/media/list`, `/media/upload`, `/genimage/start_batch` (answered for the
  session's account; after the fix they only run for the open context).
- **READ — image generation finishing after a switch** (`_pdpigPlace`,
  pdp_imagegen.js, checks the SKU only): if the SAME SKU is reopened on the new
  account and its Images tab loaded before the job ends, the old job's pictures
  could be assigned into the new account's slots. The switch now resets the
  image-tab state, which narrows this to that reopen case. FIXED 28 Sep 2026:
  the batch is only placed if the account and marketplace are unchanged.
- **FIXED (28 Sep 2026) — a save reply after a switch updated the new
  account's same-SKU row in the browser** (`editField`, `pdpBarcodeSave`): the
  reply is now reported as saved-but-stale and the screen is left alone
  (test_pdp_late_replies.js). No visual change.
- **Rule 12 follow-up:** `pdpContext` (pdp.js) and `_liveKey` / inline
  `acct::mkt` keys in miles_template.js build similar account+marketplace keys.
- **UNVERIFIED — whether the browser fires blur when a focused field is
  removed.** The switch now blurs the focused PDP field itself before the
  account changes, so this matters only for paths that bypass pdpLeaveContext.

States and rendering:
- **READ — silent failures:** `/row` checks (so a barcode clash can go
  unreported), schema load, mirror load, profit recompute; the barcode check
  can stick on "checking…"; the image library and competitor-picture errors
  look like "nothing here".
- **FIXED (28 Sep 2026) — the PDP image poller** stops on 404 (PDPIG.running no
  longer sticks) and does not place a finished batch after the account or
  marketplace moved.
- **READ — Preview/Submit from the PDP:** the run panel exists only in the
  drawer, so a queue failure started from the PDP shows nothing.
- **LIKELY — full `pdpRender` from late data** (live attributes, schema,
  `/row`, mirror, image assign, sync) is not deferred while typing, so focus or
  unsaved typed text can be lost; only `pdpAfterAction` waits.
- **LIKELY — one Escape with a modal open over the PDP closes both.**
- **READ — the Variations tab always shows its fallback note**:
  `pdpVariationsTab` is referenced (pdp.js) but defined nowhere.
- **READ — a deep link cannot open a catalogue-only listing**
  (`pdpOpenFromUrl` requires a ROWS hit).
- **READ — two `/edit` writers bypass `editField`:** gtin.js `_gtinWrite` and
  pdp_images.js `pdpImgAssign` (Rule 12; the latter skips dirty/warnings updates).
- **READ — unsafe `'${esc(x)}'` inline handlers in the PDP** (pdp.js, pdp_images.js,
  `editCell`, `drawerMore`); pdp.js says `jsArg` "is not in scope", but it is a
  global (users.js).

## Other defects seen by reading

- **FIXED (28 Sep 2026) — truncate-then-write JSON.** config.json writers went
  through `config/settings.write_raw` in Milestone 1; the ASIN monitor store and
  history, image recipes and the Miles template index now do too
  (test_json_writes_are_atomic.py guards against new ones).
- **FIXED — unsafe inline handlers** were moved to `jsArg()` (Milestone 7;
  re-counted 28 Sep 2026: none left in listings/autofix/drawer/pdp/pdp_images).
- **Image-generation pollers:** genimage.js now stops on 404 and says so
  (28 Sep 2026); pdp_imagegen.js too (batch 4 -- a code fix, no visual change).
- **FIXED — `__all__` reaching the Repricer:** the server now drops it
  (routes/sourcing_routes `_where` on the shared resolver, 28 Sep 2026), and
  reads the account the page names -- it had read only `?id=`, so GETs sent
  with `?account=` were answered for the server's open account.
- **FIXED (28 Sep 2026) — eBay token cache** is tied to the app id that fetched
  it; a caller with other keys or none no longer gets it (test_ebay_auth_cache).
- **FIXED — toast behind modals** (it now sits above every overlay).
- **FIXED — load errors drawn as empty states** on Hourly/Traffic/Sales/Listings
  (`uiError`, 28 Sep 2026).
- **READ — "All marketplaces" is honoured only by Sales**; Traffic, Hourly,
  Orders, Stock, Weekly and PPC silently answer for one marketplace.
  (memory: all-marketplaces-was-a-lie)
- **READ — Stale Rule 1 wording:** amazon_listing_generator.py flat-file export
  comment says "needs GTIN exemption" for an empty barcode (wording only or
  behaviour: not verified). test_rule1_holds.py:13 docstring quotes the old
  GTIN rule.
- **READ — Duplicated helpers (Rule 12):** about 55 JS escape helpers (`_sEsc`
  defined twice in sales.js, `_aiEsc` in two files), about 17 Python `_num()`
  and 5 `_money` copies.

## Carried over from REMAINING_FIXES_HANDOFF.md (re-checked 28 Sep 2026)

That handoff (root file, undated, written before the 26 Sep PDP/listings
redesign) listed seven items; the five kept here were re-checked in the code:
1. OPEN, DESIGN (parked): Orders expanded panel vs
   `altascraper-order-detail-v2.html` -- a visual brief, waits for the design
   phase.
2. DONE: the "N warnings" text under the warning icons -- the row's count chip
   was removed and the card badge reworked (listrow_detailed.js, listings.js,
   the owner's "i dont want this" note). The PDP's "accepted with N warnings"
   line is Amazon's own summary, a different thing.
3. DONE: Amazon's issues are stored in their own field ("API Issues JSON",
   listing/api_issues.py pack/parse), which Sync does not touch, and are shown
   on the row and the PDP.
4. DONE: warnings are de-duplicated (listing/warnings.py `_dedupe`) and the
   compliance category comes from the product type (listing/compliance.py
   `lane_for_product_type`), not keywords.
5. OPEN, A TRACE (not a defect): document the orders cost calculation --
   sources, priority, why an order shows "—" with a supplier price, formulas.

## Carried over from PPC-BUILD-STATUS.md (7 Sep 2026)

- Sponsored Brands / Sponsored Display report configs in api/amazon_ads.py are
  UNVERIFIED and have never run (nestwell runs SP only).
- §10 ASIN Performance needs `asin_unit_economics` (Sales & Traffic per ASIN not
  yet ingested).
- §13 status signals (60-day sigma): not started.
- Owner actions listed there: re-authorise jack_uk / sheelady_us /
  selvora_limited (Finance role); type a cost for "AltaboltaVoo Ceiling Fan"
  (nestwell's remaining COGS gap); Advertising credentials for five accounts.

## Deferred by the owner (asked, not yet decided)

- **COGS, three items** (shown 18 Aug 2026, he asked to be asked again):
  1. Orders reads COGS System A (live), the Sales profit card reads System B
     (frozen per order): they agree only by coincidence. Recommended first.
  2. `/cogs/order` (correct one order's cost) has no UI.
  3. Two cost-sheet uploads with two parsers (`/cogs/upload_sheet` and
     `/cogs/upload`; the latter accepts a column named `price`, which on a
     listings export is the selling price).
  (memory: cogs-two-systems-followup)
- **Latent: `/row`, `/edit`, `/delete`, `/live/pull_row` locate a row by SKU in
  the session's workspace** unless the request names one; with shared SKUs this
  could edit another account's row. Fixing touches about 16 JS call sites, so it
  needs the owner's go-ahead (Rule 7). (memory: two-asins-per-row)

## Blocked outside the code

- **BLOCKED — SP-API roles.** jack_uk authenticates but most APIs return 403
  [ROLE] (catalog, pricing, definitions, listings, orders, A+). Finance works on
  nestwell_goods only; jack_uk, sheelady_us, selvora_limited 403. Roles reach an
  account only when that seller re-authorises the app. Check with
  `POST /sp_diagnose` or "Diagnose SP-API" before blaming code.
  (memory: aplus-api-not-granted)
- **BLOCKED — Amazon Advertising API** credentials exist only for nestwell_goods;
  the other five accounts have none, so "advertising is not connected" wording
  must stay conditional. Dr PPC's field `MAPPING` came from docs, not a real
  response: first job once connected is `GET /drppc/raw` against `MAPPING`.
  (memory: advertising-api-not-connected, orbit-features-not-built)
- **BLOCKED — Hourly ad data** needs Amazon Marketing Stream (AWS), deliberately
  not built. (memory: ads-hourly-not-available, phase4-ams-deferred)
- **BLOCKED — OAuth token exchange** has never run against a real consent.
  (memory: oauth-multitenant)
- **BLOCKED — Fee VAT confirmation**: the 18% effective fee on non-VAT accounts is
  measured from orders but not yet checked against a Seller Central fee invoice.
  (memory: amazon-charges-vat-on-its-fees)
- **BLOCKED — selvora's catalogue has never been fully pulled**, which breaks
  SKU-to-ASIN attribution for its finance rows. (memory: snapshot-is-not-what-sells)
- **Tracking carrier status** needs a paid 17TRACK key. (memory: amazon-hides-seller-tracking)

## Data from past incidents that may resurface

- Drafts generated 29 Aug - 14 Sep 2026 went out as HOME with no Amazon data
  (profit £0). Fixed at source (0d1d5c8); existing drafts are corrected by the
  owner pressing "Fix product types" on the live site. Only nestwell_goods may
  call catalogue / product-type search. (memory: home-product-type-drafts)
- Stray IT copies of UK ads reports are still stored;
  `ads_sync.stray_marketplaces()` reports them, `drop_marketplace()` removes
  (dry run by default). (memory: two-grain-tables)

## Claude Code environment (hooks, permissions) — limits as of 27 Sep 2026

Measured in live headless Claude Code 2.1.283 sessions on this machine. What
works is in CLAUDE.md Rule 19; these are the genuine remaining limits.

- **Hooks fail OPEN if they cannot even start.** The guards catch their own
  errors (deny / ask), but if PowerShell itself cannot start the script, the
  script has a syntax error, or Claude Code's 30 s hook timeout expires, Claude
  Code treats it as a non-blocking error and the action proceeds. The guards
  give up after 10 s internally to stay inside that window.
- **guard_secrets matches names, not intent.** A file name assembled at run
  time (`'con' + 'fig.json'`), a wildcard (`Get-Content conf*`), or a program
  that opens the file without its name in the command is not caught. The deny
  rules cover the Read/Edit tools and simple cmdlets regardless.
- **guard_rules recognises writes that NAME a governance file.** A shell
  command that changes CLAUDE.md or `.claude/` without naming it (e.g.
  `git checkout .`, `git stash`) is not caught; reviewing `git diff` before
  every commit remains the backstop.
- **In bypass mode governance edits and pushes cannot be approved from Claude**
  — they are denied, by design. The owner makes them himself or in a
  normal-mode session.
- **Agents are read-only by instruction only**: four have PowerShell.
- **Hooks use relative paths** (`.claude/hooks/...`); a session started in a
  subfolder of the worktree was not tested.
- **A session started in `D:\AltaScraper` runs with NO hooks at all** (measured
  29 Sep 2026). The hooks live in the worktree's `.claude/settings.json`; the
  old checkout has no `settings.json` and its `settings.local.json` defines no
  hooks. The whole 28-29 Sep run was such a session: guard_secrets did not stop
  a Python read of `D:\AltaScraper\config.json` (only one key's presence was
  printed, as a boolean), and governance edits (build-feature skill, start-task,
  CLAUDE.md Rules 7/19) raised no guard_rules prompt. The rules were followed
  by hand; the edits are in one commit for the owner to review. Fix: start
  Claude Code from `D:\AltaScraper-wt\claude-environment` (the old checkout is
  not to be modified, so the hooks cannot be added there without the owner).
- **The interactive approval path** (owner clicks "allow" on a guard prompt) was
  not testable in headless sessions; the ask was verified to stop the action.
- The syntax_check hook reports through JSON because PowerShell turns a child's
  exit code 2 into 1 (measured). Any future hook must also report via JSON.

## Tests

**Baseline at the end of the 28 Sep 2026 run (Milestones 1-12), `py -3.11
run_tests.py` in this worktree: 371 files, 362 passed, 7 failed, 2 could not
run.** (After Milestones 1-2 it was 367/353/12/2.) Every test runs
against the tree it lives in (141 used to hard-code `D:\AltaScraper` and so
tested the main checkout). The runner gives each test file its own empty
database and a STAND-IN config.json (`run_tests._safe_env` / `TEST_CONFIG`:
visible placeholder values, one test account with no SP-API details), so no test
can read or write the owner's real data or credentials, and tests that build the
whole app now run instead of stopping at "config.json not found". Earlier
baselines (355/327/28 on 27 Sep; 362/339/11/12 mid-Milestone 1) are NOT
comparable.

**Could not run** (exit 125, reported separately): test_library.py (needs the
real sheelady_us credentials -- a live Amazon call), test_mockup_match.py (its
`altascraper-listings-mockup.html` is not in git).

**Failing because they need the owner's real data** (7 after Milestone 10; not
app faults, not re-run with real data): test_ai_attribution,
test_autofix_apply, test_barcode_and_exemption, test_handling_saved,
test_listings_store, test_listrow_data, test_real_amazon_fee (its code pins
pass; only the data checks fail). These MEASURE the owner's data by design;
they are meant to be run in his checkout.

Converted in Milestone 10 (now run anywhere): test_seller_draft_e2e (a made-up
account instead of COPYING THE OWNER'S FIRST ACCOUNT AND ITS CREDENTIALS into a
temp file; two expectations were also stale -- drafts are never enrolled since
the owner's 7 Sep rule), test_miles_column_shift (fixture accounts),
test_cogs_one_reader (a throwaway config -- it WROTE and restored costs in the
owner's real cogs_overrides.json when run in the main checkout),
test_product_type_fill (the run's own database, not `<repo>/altascraper.db`),
test_asin_has_a_name (the real-config check says "not checked" when there is
no real config; its code checks run).

**Watch out:** test_barcode_and_exemption.py crashes on its data checks BEFORE
it reaches its CLAUDE.md wording checks, so a run never tests CLAUDE.md. Check
the wording separately (the `verify-change` skill says how) whenever CLAUDE.md
changes.

Checks added in Milestones 1-3:
- test_no_undefined_names.py -- pyflakes, "undefined name" only, over the app
  code (it found and closed known-issues #2 `_state_account`).
- test_no_undefined_js_calls.js -- a call in static/js or a template handler to
  a function declared in no file. Lexical, so limited to camelCase/_prefixed
  names and it treats `typeof f === "function"` guards as intentional. Proven to
  catch a planted undefined call. Cannot see load order or a name declared in
  another file (stated in the test).
- test_guard_every_account.py, test_security_basics.py,
  test_bulk_account_pinned.js, test_no_esc_in_handlers.js,
  test_defaults_carry_no_identity.py -- Milestone 2; each shown to fail on the
  old code where that could be run (bulk: acct_A,acct_B,acct_B; esc: 46 sites
  in the old listings.js).
- test_helpers.js now exports the page's own `jsArg` for sandboxed tests.

**test_order_panel.js fails when run on its own (`node test_order_panel.js`,
12 CSS checks) but passes under `run_tests.py`** (seen 29 Sep 2026). It reads
`static/css/dashboard.css`, while the `.odp*` rules now live in
`static/css/dashboard/19-order-panel.css`. Not investigated further; run it
through the runner.

Fixed in Milestone 1 (were failing): the two CRLF tests
(test_weekly_says_what_it_shows, test_profit_follows_price) now normalise line
endings; test_brand_consistency / test_live_counts / test_orbit_layout were
re-pinned to the deliberate 26 Sep changes (Generate screen retired 562b4d8,
"Generated" tile renamed "Drafts") and orbit_layout's CSS check no longer reads
CSS comments.
