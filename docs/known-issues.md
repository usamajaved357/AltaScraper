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

1. **READ — A lister (no publish permission) appears able to submit to Amazon.**
   `/run/api_submit` needs only "edit" (`auth/guard.py` RULES `/run`), and
   `POST /preview/enqueue` is not in RULES so it defaults to "edit".
   `_require_publish()` (dashboard.py) checks whether the *workspace* can
   publish, not whether the *user* has `publish`.
   Verify with: a Flask test-client request as a lister.
2. **READ — `_state_account` is never defined** (routes/listing_routes.py, in
   `run()`, the scope-capture line). If the session's selected account is no
   longer in config, `/run/<mode>` raises NameError and the browser shows an
   empty stream. Verify with: test client, `_state` pointing at a removed account.
3. **READ — The 4-hourly `asin_monitor` scheduler job ignores the monitor's own
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
5. **READ — Another account's data can show after switching accounts.**
   `LIVE_MIRROR` and `COGS_LOCAL` (browser) are keyed by SKU only and not reset in
   `enterAccount`; `SELECTED` and `LISTING_METRICS` are not reset either.
   SKUs are not unique across accounts.

## PDP (product page) — review of 27 Sep 2026 (read-only; no tests run)

Account switching (none of these is pinned by a test yet):
- **READ — the PDP stays open across an account switch.** `enterAccount` /
  `switchAccountMarket` (shell.js) never call `pdpClose` or reset `PDP_SKU`,
  `PDP_DIRTY`, `PDP_EDITED_FIELDS`, `PDPI`, `LIVE_ATTRS`. Reachable with the
  Ctrl+K palette (z 200, above the PDP) and Back/Forward between
  `/w/A/listing/X` and `/w/B/listing/X`. Edits then save with `acctBody()` =
  the NEW account, into its same-SKU row (or `adopt` creates one). Cross-account write.
- **READ — `LIVE_ATTRS` (drawer_attributes.js) is keyed by SKU only, cached
  forever (failures included) and never cleared**; with a shared SKU, account
  B's PDP shows and merges account A's Amazon copy (`pdpAmazonCopy`) and
  `lvPushChanges` diffs against A. Extends suspected bug #5.
- **READ — `PDPI` (pdp_images.js) is keyed by SKU only, never reset** on close
  or switch; reopening the same SKU shows stale slots/library.
- **READ — a late `/row` reply** (pdp.js `pdpRefreshChecks`) is checked by SKU
  only, not account, and merged into the new account's row.
- **READ — `/listing/live_attributes` ignores the named account** and uses
  `_active_account()` (listing_routes.py `listing_live_attributes`).
- **READ — PDP calls that name no account:** `/listing/image_slots`,
  `/media/list`, `/media/upload`, `/genimage/start_batch`.
- **NEEDS VERIFICATION — an image-generation job finishing after a switch**
  may place images into the new account's slots (`_pdpigPlace`).

Security:
- **READ — guard exemption prefix bug.** `auth/guard.py`
  `WORKSPACE_PARAM_EXEMPT` uses `p.startswith(ex)`, so `"/row"` also exempts
  `/rows` and `/rows_all`: a user restricted to one account is not stopped from
  naming another in `/rows_all?account=`. Verify with the Flask test client.

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

**Baseline on origin/main 0e5529e, clean worktree with no config.json or
database (27 Sep 2026): 355 files, 327 passed, 28 failed.** Before calling a
failure a regression, check it fails the same way without the change
(memory: tests-need-real-data).

Failing because they need the owner's real config.json / database (expected in
a clean worktree; re-run in the main checkout before calling them regressions):
test_account_isolation_ui.py, test_account_switch.py, test_agent_tools.py,
test_ai_attribution.py, test_ai_usage.py, test_asin_has_a_name.py,
test_autofix_apply.py, test_backup.py, test_barcode_and_exemption.py,
test_cogs_one_reader.py, test_genimage_buttons.py, test_handling_saved.py,
test_hold_price.py, test_library.py, test_listings_store.py,
test_listrow_data.py, test_miles_column_shift.py, test_product_type_fill.py,
test_real_amazon_fee.py, test_seller_draft_e2e.py, test_stop_scope.py,
test_store_merge.py.

**Watch out:** in a clean worktree test_barcode_and_exemption.py crashes
(IndexError) on its data checks BEFORE it reaches its CLAUDE.md wording checks,
so a clean-worktree run never tests CLAUDE.md. Check the wording separately
(the `verify-change` skill says how) whenever CLAUDE.md changes.

Needs an untracked local file: test_mockup_match.py reads
`altascraper-listings-mockup.html`, which exists only in the main checkout.

Failing for reasons that look like code/test drift, not data (**not yet
investigated**):
- test_weekly_says_what_it_shows.py — `ReferenceError: WK_TREND_N is not defined`
  when weekly.js runs in the sandbox.
- test_brand_consistency.js — 8 checks on the "generate" screen header (the
  Generate screen was retired on 26 Sep, 562b4d8).
- test_live_counts.js — "the drafts view keeps tiles of its own".
- test_orbit_layout.js — nav reachability (8 of 9 sections) and "no route or
  endpoint appears in the CSS".
- test_profit_follows_price.js — "but only when it has none of its own".

Which of the 28 are data-dependent vs drift was classified from their output
text; the data ones were not re-run with real data in this pass.
