# PPC build status — the four pages, against the spec

Recorded 7 Sep 2026, at the owner's request: *"record the list of tasks from the
last 12 hours and get them completed which are not already."*

`PPC_ANALYTICS_BUILD_SPEC` arrived in append-only versions — `(1).md` → `4` →
`445` → `757` → `fdsdgg`. Nothing was ever edited; each version adds sections.
The four pages it describes are §1–16 PPC Analytics, §17 Search Terms, §18
Campaign Analytics, §19 Live Tracker, with §20 giving exact formulas for all of
them.

---

## What was asked of Amazon first

Two of the four pages rested on data this app did not hold, and nobody had
established that Amazon would supply it. CLAUDE.md Rule 4 says ask rather than
guess, so `probe_ads_targeting.py` asked and `probe_ads_targeting_columns.py`
read the real columns of what came back.

| Report | timeUnit | Verdict |
|---|---|---|
| `spTargeting`, `groupBy:["targeting"]` | DAILY | **ACCEPTED** — 8,505 rows over 7 days, carrying `match_type` **and** `date` |
| `spSearchTerm`, one day and seven days | DAILY | **ACCEPTED** — carries a `date` column |
| `spKeywords`, `groupBy:["keyword"]` | DAILY | **REFUSED** — *"invalid groupBy values: (keyword). Allowed values: (adGroup)"* |

Both blockers cleared, and both are recorded in the code so nobody asks again.

---

## Done

### Page 1 — PPC Analytics (§1–16, §20)

- [x] **Trailing 2-day attribution immaturity** (§1 rule 4) — was not implemented
      at all. Money columns keep the full window; cohort and opportunity score are
      judged on days that have finished being attributed.
- [x] **Opportunity score to §20's exact arithmetic** — three separate faults, see
      below.
- [x] **Marginal cohort measured against spend**, not break-even ACOS (§5, §18).
- [x] **Comparison suppression thresholds** (§20) — spend <£10, sales <£25, orders
      <3, ratios off a base <2%. Each blank arrow carries its reason.
- [x] **Wasted spend, both definitions** (§20) — full universe for audit, qualified
      (≥10 clicks) for action.
- [x] Ratio changes in points, money in per cent — already built.
- [x] Efficiency score, 0.50/0.30/0.20, refusing rather than guessing — already built.
- [x] Four-grain same-money rule — already built, and now holds at **five** grains.

### Page 2 — Search Terms (§17)

- [x] **Daily grain.** `ppc_search_terms` gained a `date` column; the sync asks for
      `timeUnit: DAILY`. 976 dated rows landed.
- [x] **The date picker moves the figures** — £274.49 over the month, £75.44 over
      five days, £14.40 over a week.
- [x] Rows stored before the change keep a **NULL** date and are counted in every
      window; the page says which case it is in.
- [x] Dual KPI rows — top fixed, bottom recalculating under filters — already built,
      with ratios from summed totals rather than averaged per row.

### Page 3 — Campaign Analytics (§18)

- [x] **`ads_targeting_daily`** — a fifth grain. 23,634 rows, summing to £274.49,
      the account total to the penny.
- [x] **Match-type donut and daily stacked area from the targeting report**, not the
      search term report (which is privacy-thresholded and had no dates).
- [x] Match-type table — clicks, CTR, CPC, CPA, spend, % spend, sales, ACOS, profit,
      % profit, with ⓘ on every column.
- [x] **% profit is a share of the profit pool**, not a margin on spend (§18).
- [x] **Click gap measured**, not explained away — £0.00 on this account, which runs
      no Sponsored Brands.
- [x] Opportunity absolute, never re-scaled on filter (§18).
- [x] CPA blank when orders = 0 — undefined, not £0.
- [x] Bubble map with seven ACOS bands, dashed break-even at y=0, outliers hidden
      and counted — already built.

### Page 4 — Live Tracker (§19)

- [x] **Deferred by the spec itself**, and correctly not built. It needs more than
      an SQS queue: SP-API ORDER_CHANGE notifications, Redis, a reconciliation
      cron, hot/cold partitioning.
- [x] It and PPC Analytics now answer "is hourly data available?" from **one**
      module, `domain/ams.py`, which follows stored rows rather than an environment
      variable.

### Phase 4 (AMS/AWS) — deliberately not built

By instruction. No `ads_hourly`, no `hourly_baseline_cache`, no
`workers/ams_consumer.py`, no boto3. `test_ams_fallback.py` asserts all of it.

---

## The five formulas that were wrong, and which way they were wrong

Four of the five erred in the **same direction**: recent advertising looked worse
than it was, and trivial campaigns looked urgent. That is bias, not noise — and
acting on it means cutting bids on campaigns that were fine.

1. **A single test click scored 35 points of 100.** Zero sales gives an undefined
   ACOS, and undefined was read as the worst case there is. Now scaled by spend
   against break-even CPA: an 18p campaign scores 4, a £25 one scores the full 35.
2. **Money at stake was absolute.** `sqrt(spend)/20` saturates near £400, so on an
   account whose biggest campaign spends £34 the whole column bunched under 12 out
   of 40. Now relative to the largest spender in the set: the column spans 3–87.
3. **Unconverted clicks were a rate**, so 5 clicks and no orders scored the same as
   1,000. Now by volume, against a threshold of 30.
4. **Marginal was measured against an account-wide ACOS**, so a fatter-margin
   product was called marginal against a threshold that did not apply to it.
5. **The last two days were judged as if finished.** They are not.

---

## Not done, and why

### Needs the owner, not the code

- **Re-authorise `jack_uk`, `sheelady_us`, `selvora_limited`** in Seller Central.
  The Finance role is on the app but reaches an account only when that seller
  re-authorises. All three still answer 403; `nestwell_goods` works.
- **Type a cost for `AltaboltaVoo Ceiling Fan`** (31 units, hand-named SKU with no
  number to read). It is the whole of nestwell's remaining COGS gap — 15 of its 16
  selling SKUs are costed.
- **Advertising credentials for the other five accounts.** Only `nestwell_goods`
  has an Advertising login, so every figure on these four pages is that account's.

### Blocked by data that does not exist on this account

- **Sponsored Brands and Sponsored Display.** `ads_campaign_daily` holds only
  `SPONSORED_PRODUCTS`. §18's three-way spend reconciliation (SP+SB+SD vs SP+SB vs
  search terms) describes an account that runs all three; here all three totals are
  the same number. The SB/SD report configurations exist in `api/amazon_ads.py` but
  are marked UNVERIFIED and have never been run.
- **§10 ASIN Performance table** needs `asin_unit_economics` — SP-API Sales &
  Traffic joined with Finances per ASIN. The Finances half now works on
  nestwell_goods; the Sales & Traffic half is not yet ingested per ASIN.
- **§13 Status signals** (60-day sigma) — Phase 5, not started.

---

## Verification

- 315 files, 315 passed, 0 failed.
- Smoke-tested through the real Flask routes against live data: all four pages
  answer HTTP 200 carrying the new fields.
- Five grains of the same money reconcile to £274.49: account, per-ASIN,
  per-campaign, per-placement, per-targeting. **Nothing may ever add two of them
  together.**
