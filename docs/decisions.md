# Decisions

Why things are the way they are. One entry per decision the owner made, newest
first within each area. Append-only: a reversed decision gets a new entry that
names the one it replaces; the old entry is marked **SUPERSEDED**, never deleted.

Claude records a decision when the owner states it (quoting him where possible).
Claude never records its own recommendation here as if it were his decision.

Format: **date — decision.** Owner's words. What it rules out. Source.

---

## Listings and Amazon

- **7 Sep 2026 — The GTIN exemption is claimed only by a click.** "ONLY EXEMPT
  WHEN USER SELECTS MULTIPLE DRAFTS AND CLICK ON APPLY FOR GTIN EXEMPTION OR DO
  IT INSIDE THE PDP ONE BY ONE." Rules out any condition-based exemption.
  Source: CLAUDE.md Rule 1 (which also records the 26 Aug decision).
- **10 Aug 2026 — Competitor product images are accepted for now.** Knowingly
  departs from `amazon_violation_avoidance_plan.md` §1C. Do not raise it as a
  defect unprompted. That plan is written as an arbitrage playbook, which
  conflicts with Rule 1; its risk ratings are inflated for this app. The real
  residual IP risk is competitor brand names leaking into generated copy.
  Source: memory amazon-violation-plan-decisions.

## Money and profit

- **28 Sep 2026 — Every profit figure takes VAT out at the account's own
  setting.** Asked "should every profit figure for a VAT-registered account
  exclude VAT", he answered "D1 yes use the account VAT setting". SUPERSEDES the
  P&L's earlier "VAT is shown both ways and never subtracted" design. Source:
  chat, 28 Sep 2026; active/plan-profit-accuracy.md.
- **28 Sep 2026 (reaffirmed) — Refunds count on the day the money went back,
  on every screen.** Asked refund date or order date, he chose "Refund date
  (your rule)". The original words, quoted in domain/pnl.py: "REFUNDS stay on
  the refund event date -- NOT re-dated to the original order. July's profit
  stays locked. September's refund hits September's P&L." Rules out re-dating
  refunds anywhere (the Sales screen used to). Source: chat, 28 Sep 2026.
- **Missing cost prices: show the profit, say it is too high.** "if no cogs
  are added show profit as wrong i agree do not subtract cogs this is the
  standard way, the user should know he needs to add cogs otherwise the profit
  numbers wont be accurate." Applied to Finance on 28 Sep 2026 (it hid the
  figure); the Sales grid's daily cells still withhold, having nowhere to put
  the warning. Source: domain/order_profit.py docstring.
- **28 Sep 2026 — He delegated the remaining profit rules to Claude** ("i want
  you to chose the logics you think is accurate ... report me all at the end").
  Those choices are listed in known-issues "Fixed on the development branch" as
  awaiting his review; they are not recorded here as his decisions.

- **18 Aug 2026 — Profit is measured, never padded.** "do not add 3 pounds
  postage and 2 pounds ad cost and 1 pound profit space on your own, if i added
  this rule earlier, remove it. i want to be shown the profit as the truth."
  `listing/pricing.py` `PRICING_RULE_SHIPPING_LABEL`, `_ADS_MARGIN`,
  `_MIN_PROFIT` are 0.00 and stay 0.00; real per-unit costs he enters go in
  `domain/asin_charges.py`. Amazon's fee comes only from `domain/amazon_fees.py`.
  Coupons are measured from settled orders, never assumed.
  SUPERSEDES the 14 Aug 2026 repricer pricing rule
  (`cost + fee + 3.00 + 2.00 + 1.00`). Source: memory profit-is-measured-not-padded,
  source-repricer.
- **17 Aug 2026 — selvora_limited and nestwell_goods are not VAT-registered.**
  `vat_rate: 0` is correct for both; jack_uk stays 0.2. Do not "fix" them.
  Source: memory vat-rate-per-account.
- **Sales/P&L use the order calendar by default**, decided in one place
  (`routes/sales_routes._basis()`); finance data is stored per account, not per
  marketplace. Source: memory pnl-one-calendar.

## Data and architecture

- **13 Aug 2026 — SQLite is the primary datastore; Google Sheets stops being a
  main dependency.** Sheets may remain an import/export/backup path only. Rule 12
  governs the migration: never a DB path beside a sheet path. Current state: the
  app is permanently on the database (`data/choice._SHEETS_UNLINKED`).
  Source: memory database-migration-decision.
- **4 Jul 2026 — Root shims bridge old import names** to `domain/` instead of
  rewriting about 62 import sites; delete them when nothing imports the bare
  names. Source: memory restructuring-shims.
- **5 Jul 2026 — Restructuring stopped at the orchestrator.** `build_api_attributes`,
  `check_compliance` and `_shape_list_price` stay in the engine; marketplace
  injection (to move them) is a behaviour change, declined. The services layer
  and CONFIG_PATH anchor dedup were also declined. gunicorn was declined (the
  Flask dev server stays). Source: memory phase5-listing-extraction,
  phase6-config-layer.
- **Route registration by injection, not blueprints** (Phase 3). Source: memory
  phase3-route-extraction.

## UI

- **28 Sep 2026 — The product page (PDP) is not to be redesigned.** "i love my
  current pdp page i will not change it". Rules out PDP changes in any design
  option.
- **28 Sep 2026 — Redesign builds on the pages he likes, not on new
  directions.** "nah i like my current app, look at the sales page and traffic
  page, hourly sales page, all listings page 3 views i like to have all 3. and
  then repricer page i like it and campaign analytics page, search terms page
  ... you can take inspiration as a base from these and then design some
  options". Supersedes the three directions in
  docs/proposals/design-exploration.md as the basis for Milestones 8-9; the
  three listing views stay.
- **29 Aug 2026 — The listing drawer keeps the design file's literal hex
  colours, not Orbit tokens.** He was offered tokens and chose the mock's hex.
  **Every panel the design omitted was kept and folded closed**, not removed.
  A blocking banner (identifier / compliance) is never folded. Free-text fields
  are `contenteditable` saved through `saveEdit()`; enum fields stay `<select>`.
  There is no quality "score" (the app computes none). Source: memory
  drawer-redesign-decisions.
- **27 Sep 2026 — Listings page:** detailed row and card view restored as they
  were before the 26 Sep redesign (keeping Amazon's real condition); three view
  toggles, Table default; the "Add a product" form removed; one-line upload
  zone; stat-card hint text removed; an empty queue shows nothing. Source:
  commits 5e78d3e, 0e5529e; test_listings_restore.js.

- **27 Sep 2026 — An account or marketplace change is a change of product
  context.** "When the account or marketplace changes: close the open PDP;
  clear its account/marketplace-specific state and caches; prevent stale
  replies from updating the new context; allow the product to be reopened
  explicitly for the new context. Do not try to preserve the open PDP across an
  account or marketplace boundary." The `/listing/live_attributes` account
  handling is a separate follow-up (D2). Source: read.txt, 27 Sep 2026.

## PPC and advertising

- **7 Sep 2026 — Skip Phase 4 (AMS/AWS) entirely.** "Skip Phase 4 entirely
  (AMS/AWS). Owner doesn't have an AWS account. Build the graceful degradation
  fallbacks instead ... Do NOT create ads_hourly table, hourly_baseline_cache
  table, or workers/ams_consumer.py ... Keep the env var check (AWS_SQS_QUEUE_URL)
  in code". Screens branch on `domain/ams.available()` (stored rows), never on
  the env var. test_ams_fallback.py pins it. Source: memory phase4-ams-deferred.
- **PPC formulas follow the spec exactly** (`PPC_ANALYTICS_BUILD_SPEC` §18/§20;
  only the "(1)" version is in docs/specs — the later appended versions "4",
  "445", "757", "fdsdgg" are untracked files in the main checkout). Recorded here
  so they are not lost (memory: ppc-spec-arithmetic):
  - **Attribution maturity:** money columns keep the full window; cohort and
    opportunity score use matured days only, stepping back from the last day
    WITH DATA (`ppc_analytics.maturity()`).
  - **Opportunity score** = `min(100, S_spend + S_breakeven + S_unconverted)`;
    `S_spend = 40 × sqrt(spend / max_spend)` (max over the UNFILTERED set);
    `S_breakeven = 35 × min(1, (acos − be) / be)` when sales > 0, else
    `35 × min(1, spend / max_cost_per_order)` with `max_cost_per_order = AOV ×
    break-even ACOS`; `S_unconverted = 25 × min(1, (clicks − orders) / 30)`.
    Absolute: never re-scaled on filter.
  - **Marginal cohort:** profitable by ≤10% of SPEND (not against break-even ACOS).
  - **Comparison suppression:** prior spend < £10, sales < £25, orders < 3, or a
    ratio off a base < 2% → show `--` with the reason.
  - **Wasted spend, two definitions:** full universe (`spend > 0 AND orders = 0`)
    for audit; qualified (`clicks ≥ 10 AND orders = 0`) for action; nothing
    qualifying is a measured 0.0, not a dash.
- **Rule 8** — never change bids or budgets without an exact value from the
  owner; the Ads client has no write calls. Source: CLAUDE.md Rule 8.

## Monitoring and repricing

- **18 Aug 2026 — The ASIN monitor does not run on a fixed timer.** "i dont want
  the asin monitor to be working always". Only "Check now" and a user-chosen
  interval (1-168 h), OFF by default, decided in `monitor/schedule.py`.
  Source: memory asin-monitor. (A scheduler job used to bypass this; fixed in
  Milestone 3, 28 Sep 2026 -- known-issues Suspected #3, test_scheduler_jobs.py.)
- **31 Jul 2026 — Any seller-name scraping lives in its own module** behind a
  narrow interface, never inside checker logic. Source: memory asin-monitor.
- **15 Sep 2026 — Repricer enrolment is automatic on go-live, in dry run.**
  Arming (not enrolment) is the blast-radius control; drafts are never enrolled.
  FBM only; eBay via its API, anything else via an isolated scraper; floor
  price and "unknown is not out of stock" are load-bearing; PATCH only.
  Source: memory source-repricer.

## Security

- **Jul 2026 — Old keys found in local history were not rotated, by the owner's
  choice**: GitHub push protection blocked the push, so they were never
  published; the local history was scrubbed. Do not nag about rotation.
  Source: memory secrets-in-git-history. (27 Sep 2026: no `backup/*` or
  `refs/original` refs remain in the local repo.)

## Team and Employee Performance

- **29 Sep 2026 — Team manages people; Employee Performance shows their work.**
  "Team = manage employees. Employee Performance = see what work they did."
  "Do NOT create a second user or permission system." "Do not invent a
  performance score. Record objective work/activity evidence." "Only
  appropriate owner/admin/manager roles should see employee-wide performance."
  Implemented as the `view_activity` permission in the owner and manager
  presets; the one activity log is described in docs/architecture.md §4.
  Defaults Claude took where the rule is not yet stated (active/owner-review.md):
  automatic Amazon checks are not counted as a person's work; refusals are
  recorded as "refused"; edits keep the field name and the new value only;
  records are kept for ever. Per-person marketplace limits: not built (no rule).
  Source: roadmap, read.txt 29 Sep 2026 (active/roadmap-2026-09-29.md).

## Working agreements

- **27 Sep 2026 — One long-running development branch.** `D:\AltaScraper-wt\claude-environment`
  on `claude-environment-setup` is the primary development environment for the
  whole app. Ordinary tasks do not create worktrees or branches, switch, reset,
  rebase or cherry-pick; a new worktree only for isolated experimental work he
  asks for. No push / merge / deploy without his explicit word;
  `phase6-config-layer` not used unless he asks. Source: read.txt, 27 Sep 2026.

- **Ask before changing existing behaviour.** For any plan, separate: already
  does / needs your input / would change behaviour / pure addition. Source:
  memory ask-before-changing-existing-behaviour.
- **27 Sep 2026 — Claude Code environment** (this docs/ structure, skills,
  agents, hooks) approved, with: CLAUDE.md replaced by the shorter design;
  never-commit rule narrowed from blanket "key"/"token" to secret-bearing file
  types; memory project facts migrated into docs/ (originals kept); shared
  untracked `current-work.md` and `active/` in the main checkout.
  Source: read.txt, 27 Sep 2026. SUPERSEDED for notes by the entry below.
- **29 Sep 2026 — The old checkout is fully read-only.** "DO NOT modify
  D:\AltaScraper at all, including current-work.md ... all working notes,
  current-work tracking, plans, baselines, screenshots, investigations and other
  development artifacts must stay inside: D:\AltaScraper-wt\claude-environment".
  So `current-work.md` and `active/` live at the worktree root (both already in
  .gitignore); `D:\AltaScraper\read.txt` is only read. The old
  `D:\AltaScraper\current-work.md` is frozen as it stood at 07:04, 29 Sep.
  Source: read.txt, 29 Sep 2026.

## Orders

- **29 Sep 2026 — Orders: build the full design layout first, with no real
  actions.** After seeing the side-panel version the owner said "this orders page
  is not according to our plan"; asked which version to build, he chose "Layout
  first": status tabs with counts, supplier/cost columns, the dispatch countdown,
  row selection, a card list on phones -- and the "Next step" and bulk buttons
  only OPEN the right screen or order. Rules out, for now: any Orders button that
  marks dispatched, uploads tracking, buys from a supplier or otherwise writes to
  Amazon or spends money; each is wired later, one at a time, with his OK.
  Source: owner answer to the Orders question, 29 Sep 2026.

## Code structure

- **28 Sep 2026 — Milestone 4 approved: split the big files by feature, batches
  0–9 in the planned order.** "Approved for Milestone 4. Proceed with all batches
  0–9 in the proposed order." Explicit OK to move functions out of dashboard.py
  and the listing engine (batches 7–9, CLAUDE.md Rule 3). Duplicate CSS rules may
  be merged "only where you can prove the rendered result remains identical".
  Batch 8 may "pass the required shared app state explicitly to the
  background-job modules". Rules out: rewriting build_api_attributes in this
  milestone ("Leave it where it is; plan that separately later"); patching
  around a regression ("revert that batch rather than patching around the
  regression"); push, merge or deploy. Working style: "Continue autonomously
  through all approved batches. Do not stop between batches for routine
  questions; defer non-blocking issues to the final report."
  Source: owner message, plan doc "AltaScraper — Milestone 4: splitting the big
  files by feature".
