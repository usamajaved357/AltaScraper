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
   STILL OPEN: S9 (navTo marks a screen fresh before its load finishes, so a
   failed load looks fresh for 10 minutes); S10 (the shared-password owner and
   background threads share one process-wide selection); an old request's
   `finally`/`catch` can still clear the new request's busy flag or paint its
   network error for a moment (low); and four older per-screen copies of the
   "still the same account?" check (submit.js stillMine, miles_template
   stillHere, sales _sFetch -- account only, orders loadId) are not yet on the
   shared screenScope (Rule 12, work when those screens are next touched).

## Fixed on the development branch, NOT yet in production

On `claude-environment-setup` (local, not merged or deployed — production still
has these until the owner merges):
- **Milestones 4-6 (28 Sep 2026).** Cost overrides (cogs_overrides.json) and
  the Miles bundle store are written atomically -- a crash mid-write could
  empty them, and a corrupt file was then saved back as `{}`. The live
  refresher and the A+ route no longer `import dashboard` (a second copy of the
  app with a config cache nobody cleared: accounts added later were invisible
  to live catch-up until a restart). Marketplace currency symbols come from
  money.js's one map (Canada/Mexico/Singapore/Australia were "$" on some screens
  and "C$"/"MX$"/"S$"/"A$" on others). UX: an untouched order-cost box no
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
  image-tab state, which narrows this to that reopen case. pdp_imagegen.js was
  outside the approved change.
- **LIKELY — a save reply that lands after a switch updates the new account's
  same-SKU row IN THE BROWSER** (`editField`, autofix.js, has no context check;
  `pdpBarcodeSave` likewise). The server write goes to the correct account;
  only the in-memory row/screen can show the old value until a reload. Needs a
  context check in autofix.js (outside the approved change).
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
- **READ — the image-generation poller has no end on error**, so
  `PDPIG.running` can stay true and block later runs.
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

- **READ — config.json is still written directly (non-atomic, truncate first)**
  by routes/settings_routes.py (AI settings, logic settings, eBay settings),
  domain/accounts.py (seed, save, delete) and monitor/known_sellers.py, bypassing
  `config/settings.write_raw`. A crash mid-write can empty config.json. The
  phase6 memory note claimed this was finished; it has regressed or was partial.
- **READ — Other truncate-then-write JSON files:** cogs_overrides.json,
  app_state.json, asin_monitor*.json, miles_bundles*.json.
- **READ — Unsafe inline handlers:** `onclick="fn('${esc(x)}')"` in listings.js
  (tile menu, drawerMore), autofix.js, drawer.js, pdp.js toolbar. An apostrophe
  in a SKU/key breaks the button or injects script. `jsArg()` is the fix.
- **READ — Image-generation pollers never stop on 404** (genimage.js,
  pdp_imagegen.js), e.g. after a restart loses `_IMG_JOBS`.
- **READ — `_srcBody` / `_srcUrl` (sourcing.js) do not drop `__all__`.**
- **READ — eBay token cache is one global**, not keyed by app id (api/ebay.py).
- **READ — Toast renders behind modals** (z-index 80 vs 90+).
- **READ — Some load errors look like empty states** (hourly.js draws "Could not
  load" in `.empty`).
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

## Carried over from REMAINING_FIXES_HANDOFF.md (status NOT re-checked)

That handoff (root file, undated, written before the 26 Sep PDP/listings
redesign) listed seven items. Whether each is still open was not verified on
27 Sep 2026; check before working on any of them.
1. Orders expanded panel vs `altascraper-order-detail-v2.html`: one cost/fee/
   profit bar palette everywhere (sourcing colours), full supplier table with
   shipping pills, spaced delivery line, badge row, clean "no cost" state
   (handling still shown), compact header on every page.
2. Remove the "N warnings" text under the warning icons (detailed row, PDP hero,
   card view); keep the icons.
3. Amazon API errors vanish after Sync because they live in the status: store the
   `issues` array separately, survive Sync, clear on a clean resubmit, show on
   the PDP and the row. (No `api_errors` field exists in the code today.)
4. Compliance warnings: duplicates in the warnings array (listing/warnings.py),
   and cosmetics/blades rules firing on cleaning tools — decide categories from
   Amazon's product type, not keywords.
5. Trace (don't change) the orders cost calculation: sources, priority, why an
   order shows "—" when sourcing has a supplier price, the profit/ROI/margin
   formulas.

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
- **The interactive approval path** (owner clicks "allow" on a guard prompt) was
  not testable in headless sessions; the ask was verified to stop the action.
- The syntax_check hook reports through JSON because PowerShell turns a child's
  exit code 2 into 1 (measured). Any future hook must also report via JSON.

## Tests

**Baseline after Milestones 1-2 (28 Sep 2026), `py -3.11 run_tests.py` in this
worktree: 367 files, 353 passed, 12 failed, 2 could not run.** Every test runs
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

**Failing because they need the owner's real data** (12; not app faults, not
re-run with real data): test_ai_attribution, test_asin_has_a_name,
test_autofix_apply, test_barcode_and_exemption, test_cogs_one_reader,
test_handling_saved, test_listings_store, test_listrow_data,
test_miles_column_shift, test_product_type_fill, test_real_amazon_fee (its code
pins were re-pinned in Milestone 1 and pass; only the data checks fail),
test_seller_draft_e2e. Next step (Testing milestone): give each a fixture.

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

Fixed in Milestone 1 (were failing): the two CRLF tests
(test_weekly_says_what_it_shows, test_profit_follows_price) now normalise line
endings; test_brand_consistency / test_live_counts / test_orbit_layout were
re-pinned to the deliberate 26 Sep changes (Generate screen retired 562b4d8,
"Generated" tile renamed "Drafts") and orbit_layout's CSS check no longer reads
CSS comments.
