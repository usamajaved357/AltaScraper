# PPC Analytics Page — Full Build Specification for AltaScraper

> **Source:** Reverse-engineered from Orbit's Dr PPC Console (Promixx / ATVPDKIKX0DER / USA)
> across three interrogation rounds on 6 Sep 2026. Every formula, threshold, data source, and
> edge case documented below was confirmed by the system's own tool outputs.
>
> **Target:** AltaScraper — Flask app, Railway deployment, SP-API multi-tenant OAuth already
> connected, Amazon Advertising API already connected (EU endpoint, UK profile active, 30 days
> SP data stored). Orbit-style UI (charcoal #1a1d23, teal #2dd4a8, gold #f0b429).
>
> **Standing rule:** Never modify existing tools. All PPC analytics in separate routes/files.
>
> **AMS status:** REQUIRED for live Today banner, hourly day trail, and ACOS heatmap. Owner
> is setting up AWS SQS in parallel. Build Phases 1-3 first, then Phase 4 when AWS env vars
> land. Phase 4 code MUST degrade gracefully if AWS vars are absent (fall back to daily data).
>
> **Existing codebase references:** Read `CLAUDE.md`, `ALTASCRAPER_ARCHITECTURE.md`, and
> `NEW_APP_BLUEPRINT.md` in the repo root before writing any code. The existing `api/amazon_ad`
> module handles Ads API auth, campaigns, and report request/poll/download. The existing
> `config.json` stores Ads API + SP-API credentials per workspace. Reuse these — do not
> create parallel auth flows.

---

## Table of Contents

1. [Data Architecture](#1-data-architecture)
2. [Section 1 — Today Banner](#2-section-1--today-banner)
3. [Section 2 — Day Trail (7 cards)](#3-section-2--day-trail-7-cards)
4. [Section 3 — KPI Row (8 metrics)](#4-section-3--kpi-row-8-metrics)
5. [Section 4 — Branded vs Non-Branded](#5-section-4--branded-vs-non-branded)
6. [Section 5 — Profitability Analysis](#6-section-5--profitability-analysis)
7. [Section 6 — Wasted Spend](#7-section-6--wasted-spend)
8. [Section 7 — Profit per Click & Efficiency Trends](#8-section-7--profit-per-click--efficiency-trends)
9. [Section 8 — ACOS Heatmap + TACOS Over Time](#9-section-8--acos-heatmap--tacos-over-time)
10. [Section 9 — Budget & Pacing](#10-section-9--budget--pacing)
11. [Section 10 — ASIN Performance Table](#11-section-10--asin-performance-table)
12. [Section 11 — Campaign Table](#12-section-11--campaign-table)
13. [Status Signals System](#13-status-signals-system)
14. [Amazon API Hard Limits](#14-amazon-api-hard-limits)
15. [Database Schema](#15-database-schema)
16. [Build Order](#16-build-order)

---

## 1. Data Architecture

### Data Sources

| Source | API | What it provides | Grain | Update cadence |
|---|---|---|---|---|
| **Amazon Advertising API** (daily reports) | `spCampaigns`, `spAdvertisedProduct`, `spSearchTerm` | Spend, clicks, impressions, ad sales, ad orders per campaign/ASIN/search term | 1 row/day | Nightly sync, ~24-48h lag |
| **Amazon Marketing Stream (AMS)** | SQS/EventBridge push | Hourly spend, clicks, impressions (near real-time) | 1 row/hour/campaign | 60-90 min lag, late events upserted |
| **SP-API Sales & Traffic Report** | `GET_SALES_AND_TRAFFIC_REPORT` | Total sales (ad+organic), sessions, page views, buy box %, units sold per ASIN | 1 row/day/ASIN | Daily batch, 12-48h lag |
| **SP-API Finances API** | `ShipmentEventList` | Per-unit referral fee, FBA fulfillment fee, per ASIN | Per shipment event | Rolling daily sync, 24-72h behind shipment |
| **COGS** (user-supplied) | Manual entry / bulk upload | Unit cost per ASIN | Static until updated | User-driven |

### Critical Rules

1. **Same-money rule:** Daily ads data at account level, per-ASIN, per-campaign, and per-placement
   are four cuts of the SAME spend. Never add two together. Write a test that asserts all four sum
   to the same total.

2. **Search Term Report is a fixed window:** The `spSearchTerm` report has no day-by-day breakdown.
   Any section built on it (branded split, wasted spend) CANNOT follow a date picker. Display the
   actual window the data covers, not the user's selected range.

3. **Attribution ownership:** The day of the ad CLICK owns the sale, not the day of purchase.
   SP = 7-day attribution window, SB = 14-day, SD = 14-day.

4. **Trailing 2-day exclusion:** The last 2 complete days are attribution-immature. Exclude them
   from any optimization/analysis calculations. Display them on charts but mark as immature.

5. **TACOS never computed intraday:** Total sales from SP-API lag 12-48h. Computing
   `intraday_spend / 0_organic_sales` produces nonsense. TACOS only on complete days where both
   feeds have landed.

---

## 2. Section 1 — Today Banner

### What it shows
The current day's **partial** advertising data, updated via AMS hourly stream. NOT yesterday.

### Data source
- **Today's numbers:** AMS hourly stream → sum all hourly buckets for today
- **Comparison:** Hour-matched trailing 7-day baseline

### Fields displayed
| Field | Source |
|---|---|
| Ad Spend | Sum of today's AMS hourly spend buckets |
| Ad Sales | Sum of today's AMS hourly attributed sales (will mature) |
| Total Sales | NOT available intraday — show only after day completes |
| ACOS | spend ÷ ad_sales (partial, will change) |
| TACOS | **Do not show intraday** — denominator doesn't exist yet |
| ROAS | ad_sales ÷ spend (partial) |
| Impressions | Sum of today's AMS hourly impressions |
| Clicks | Sum of today's AMS hourly clicks |

### Comparison formula (the % change arrows)
```
change_pct = ((today_spend_to_hour_H) - (avg_7d_spend_to_hour_H)) / (avg_7d_spend_to_hour_H) × 100
```

**Critical:** This compares today's cumulative at hour H against the average of the last 7 days'
cumulative at the SAME hour H. NOT against yesterday's full day. Without hour-matching, every
morning looks -80% and catches up by evening, making the number useless until late afternoon.

### Hour-shaped baseline computation
For each hour H (0-23) in the current day:
1. Look back 7 complete days
2. For each of those 7 days, sum AMS spend from hour 0 through hour H
3. Average those 7 cumulative values = `baseline_spend_to_hour_H`

### Flip logic
- Resets at **midnight marketplace-local time** (PDT for US, GMT for UK)
- Yesterday becomes "latest complete day"
- Today starts accumulating from hour 0

### Display requirements
- Show timestamp of last data refresh
- Show `status: partial` warning
- Show text: "Today is incomplete and attribution will continue to mature"
- When comparison data unavailable, show dash (—) not 0%

### AMS implementation notes
- Subscribe to AMS datasets via SP-API `POST /streams/subscriptions`
- Delivery via AWS SQS or EventBridge
- Upsert key: `(campaign_id, time_window_start_utc)`
- Late/revised events overwrite — curve silently self-corrects
- Current measured lag: ~77 minutes (60-90 min range)

---

## 3. Section 2 — Day Trail (7 cards)

### What it shows
7 cards, one per day, each with:
- Day's total ad spend
- Day's total ad orders (labeled as "units" in Orbit)
- A 120×50px cumulative spend sparkline

### Data source
- `ads_daily` (account grain, `asin='*'`) — one row per day
- For today's card: AMS hourly stream cumulated

### Sparkline
- X-axis: hours 0-23 (from AMS) for recent days, or just a single point for days before AMS
- Y-axis: cumulative spend from hour 0 to hour H
- Each card is auto-scaled to its own Y range — they do NOT share a baseline

### Interactivity
- **Hover:** Shows date, that day's spend, orders, running total
- **Click:** Filters the entire page to that single day. The KPI row, campaign table,
  ASIN table all re-scope. Profit calculations still use the account-level fee_rate and cogs_rate
  (not recalculated per day).

### Edge case: today's card
- Labeled "Today" with a distinct visual treatment
- Uses AMS partial data
- May fall outside the selected date range — handle this explicitly

---

## 4. Section 3 — KPI Row (8 metrics)

### Metrics and formulas

| Metric | Formula | Source |
|---|---|---|
| SPEND | `Σ daily_spend` | `ads_daily` account grain |
| SALES | `Σ daily_ad_sales` (attributed) | `ads_daily` account grain |
| ACOS | `spend ÷ ad_sales` | Derived from summed totals |
| ROAS | `ad_sales ÷ spend` | Derived from summed totals |
| IMPRESSIONS | `Σ daily_impressions` | `ads_daily` account grain |
| CLICKS | `Σ daily_clicks` | `ads_daily` account grain |
| CTR | `clicks ÷ impressions` | From **summed totals**, NOT averaged daily CTR |
| PURCHASES | `Σ daily_ad_orders` | Ad-attributed only. Blends SP 7-day + SB 14-day windows |

### Sparklines under each KPI
- Daily values over the selected window
- **Each card auto-scaled to its own Y range** — do not share a baseline
- Visual comparison of sparkline shapes between cards is misleading — this is by design

### Comparison period
- Previous period of equal length immediately before the selected window
- 30-day view → compare against prior 30 days
- 14-day view → compare against prior 14 days
- If comparison period has no data → show dash (—) not 0%

### Impressions 0% edge case
When comparison baseline is incomplete or lacks exact mirror data at this grain, the delta
defaults to 0.0% rather than NaN or broken UI. Flag this explicitly: "0% may indicate missing
comparison data, not flat traffic."

### Change arrow format
- Spend, Sales, Impressions, Clicks, Purchases: **percentage change** (`(new - old) / old × 100`)
- ACOS, CTR: **percentage point change** (e.g., 24.3% → 28.4% = +4.1pts, NOT +16.9%)
- Clarify in tooltip which format is used

---

## 5. Section 4 — Branded vs Non-Branded

### What it shows
Donut chart + metrics table splitting spend, sales, ACOS, ROAS, CVR into branded vs non-branded.

### Data source
`ppc_search_terms` (Search Term Report) — **fixed window, does not follow date picker**

### Brand matching logic
- **Case-insensitive substring match** against search terms
- "promixx" matches "promixx pro electric shaker bottle" — no need for separate entries
- User supplies brand words via input field on the PPC page
- Store brand words per workspace in a `brand_terms` table

### Display rules
- Show top 200 search terms by spend (apply spend-floor truncation)
- Full search term universe may be 1,953+ terms — the widget caps the visual sample
- Show count: "35 branded terms · 165 non-branded terms"
- If no brand words configured → show empty state with CTA to add brand words

### Metrics per lane
| Metric | Formula |
|---|---|
| Spend | Σ spend for matched/unmatched terms |
| Sales | Σ ad_sales for matched/unmatched terms |
| ACOS | lane_spend ÷ lane_sales |
| ROAS | lane_sales ÷ lane_spend |
| CVR | lane_orders ÷ lane_clicks |

### Important: search-term level, not campaign level
If a non-branded broad-match campaign caught "promixx bottle", those clicks count as Branded
in this view. The split is by what the customer typed, not which campaign served.

### Date picker warning
Display the actual window the search term data covers. When user changes the date picker,
show a note: "Branded analysis uses the Search Term Report window [date range], which does
not change with the date picker."

---

## 6. Section 5 — Profitability Analysis

### Overview metrics

| Metric | Formula | Notes |
|---|---|---|
| COGS | Sales-weighted average: `Σ(unit_cogs × units_sold) / Σ(units_sold)` | Per-ASIN from user input. Coverage tracked (e.g., 93 of 144 ASINs). Show coverage %. |
| Amazon Fees | Per-ASIN actual from SP-API Finances API | NOT a flat 15%. Includes referral (~15%) + FBA fulfillment (~22-24%) + placement/storage (~1-2%). Includes VAT on fees where applicable. |
| Break-even ACOS | `(1 - fee_rate - cogs_rate) × 100` | Per-ASIN calculation preferred. Account-level blended shown as headline. |
| TACOS | `spend ÷ total_sales` (ad + organic) | Only on complete days. Show window dates. |
| Wasted Spend | From search term report (see §6) | Fixed window. |
| Net Profit | `total_sales - total_fees - total_cogs - ad_spend` | **Total account contribution margin (ad + organic), NOT PPC-only** |
| Profit/Click | `(ad_sales - spend - fees - cogs) / clicks` per day | See §7 |
| Efficiency Score | Composite 0-100 (see below) | See formula |

### Fee ingestion pipeline
1. Ingest via SP-API Finances API (`ShipmentEventList`), rolling daily sync
2. Each shipped order emits: `Commission` (referral fee) + `FBAPerUnitFulfillmentFee`
3. Store per-ASIN: `fulfillment_fee`, `commission_fee`, `total_fees`
4. Fees reflect on next batch of shipped orders (24-48h after shipment)
5. **No retroactive rewrite** — past days keep actual fees charged; new days use new rates
6. If ASIN has zero shipped units since reclassification, retain last observed fee until first
   unit under new rate clears fulfillment

### Efficiency Score formula
```
efficiency_score = (0.50 × acos_component) + (0.30 × cvr_component) + (0.20 × wasted_component)
```

Where:
- `acos_component = max(0, 1 - (acos / break_even_acos)) × 100`
- `cvr_component = max(0, 1 - abs(cvr - historical_cvr_mean) / (2 × historical_cvr_stddev)) × 100`
  (against 60-day baseline)
- `wasted_component = (1 - wasted_spend_share) × 100`

Bands:
- **< 50 = Poor**
- **50-75 = Average**
- **> 75 = Good**

Scale: 0-100.

### Net Profit waterfall
```
Net Profit = Total Ordered Revenue (SP-API Sales & Traffic, all ASINs)
           - Total Amazon Fees (SP-API Finances, all ASINs)
           - Total COGS (user-supplied × units sold, all ASINs)
           - Total Ad Spend (Ads API)
```

This includes organic revenue. The ASIN performance table shows per-ASIN contribution from
both paid and organic channels.

### Campaign cohorts
Group all campaigns into:

| Cohort | Rule |
|---|---|
| Profitable | profit > 0 |
| Marginal | profitable by < 10% of spend |
| Unprofitable | profit < 0 |
| No sales | spent > 0, ad_sales = 0 |
| No activity | spent = 0 |

### TACOS change % edge case
When prior period had near-zero spend, TACOS change can show +922% or similar. This is
mathematically correct but meaningless. Consider: if prior TACOS < 2%, suppress the % change
and show "N/A — prior period baseline too low" instead.

---

## 7. Section 6 — Wasted Spend

### Definition
Search terms with ≥1 click and 0 attributed orders in the reporting window.

### Data source
`ppc_search_terms` — fixed window, does NOT follow date picker.

### Display
- Total wasted spend: `Σ spend` for zero-order terms
- As % of total spend
- Show the actual window the data covers
- List top terms by spend (with clicks, impressions)

### No comparison arrow
Previous versions showed a change arrow comparing "current" vs "prior" period. Both readings
came from the same fixed report = always identical = always 0%. **Do not show a comparison.**

### Optional threshold
Consider a minimum filter (≥3 clicks OR ≥$1 spend) to surface actionable terms and hide
statistical dust. Show both filtered count and unfiltered total.

---

## 8. Section 7 — Profit per Click & Efficiency Trends

### Profit per Click (daily series)

```
profit_per_click = (ad_sales - spend - (ad_sales × fee_rate) - (ad_sales × cogs_rate)) / clicks
```

Per day. Uses the account-level blended fee_rate and cogs_rate.

**Gaps vs zeros:**
- Day with clicks but profit ≤ $0.00 → plot at $0.00 (real data point)
- Day with 0 clicks → **break the line** (gap). Do NOT draw to zero.

**Attribution immaturity:**
The last 2 complete days are structurally depressed (clicks booked, sales not yet attributed).
Plot them but consider a visual indicator (dashed line, lighter color, or tooltip warning).

### Spend Efficiency Score Trend (daily series)

```
daily_efficiency = (break_even_acos / actual_acos) × 100
```

**This is unbounded.** Values above 100 mean ACOS was better than break-even:
- Break-even 34.4%, actual ACOS 17.2% → efficiency = 200
- Break-even 34.4%, actual ACOS 50% → efficiency = 68.8

Dashed line at the break-even threshold (score = 100).

Days with no attributed sales have no ACOS → gap in line, not zero.

---

## 9. Section 8 — ACOS Heatmap + TACOS Over Time

### ACOS Heatmap (Day-of-week × Hour)

**Data source:** AMS hourly stream

**Cell value:** `hourly_spend / attributed_sales_for_clicks_at_that_hour`

**Color bands:**
| Band | Color | Range |
|---|---|---|
| Green (dark) | `#166534` | < 26% |
| Green (light) | `#15803d` | < 34% |
| Amber | `#ca8a04` | < 43% |
| Red | `#dc2626` | > 43% |
| Blank | `var(--surface-2)` | No data or < 10 clicks |

**Minimum threshold:** 10 clicks per cell before rendering color. Below 10 clicks → leave blank.
This prevents single-click noise from showing as red.

**Attribution timing:** Sales mapped back to click hour. Recent hours will look artificially
red until conversions mature (48-72h). Consider noting this.

**AMS backfill:** If AMS stream was recently enabled, historical weekdays may be empty.
Show blank cells, not zeros.

### TACOS Over Time (line chart)

```
tacos = ad_spend / total_sales  (per day)
```

- Uses each day's actual values (not rolling average)
- All days in window plotted, including immature last 2 days
- Total sales from SP-API Sales & Traffic Report
- Both feeds must have landed for a day to be valid
- If ad feed present but sales feed missing → skip that day (gap)

---

## 10. Section 9 — Budget & Pacing

### What it shows
- Total Spend (sum of window) with daily average
- Total Sales (sum of window) with daily average
- Daily bar chart: Ad Spend bars + Sales bars + average reference lines

### Critical: "Total Sales" here = ad-attributed sales ONLY
Confirmed: `$48,411 / $11,768 = 4.114x` matches the ROAS in KPI row exactly.
This is NOT total revenue (ad + organic). Label accordingly.

### Daily average calculation
Average over days with active ad delivery only (exclude days where `spend = 0`).

### Data source
`ads_daily` account grain + `ads_campaign_daily` for budget details.

---

## 11. Section 10 — ASIN Performance Table

### Columns

| Column | Source | Formula |
|---|---|---|
| ASIN | Catalog | — |
| Title + Thumbnail | SP-API Catalog API | Show empty cell if no image, not broken img tag |
| Profit | SP-API Sales & Traffic + Finances + COGS | **Total ASIN profit (ad + organic)**, NOT ad-only |
| Sessions | SP-API Sales & Traffic Report | Total detail page sessions |
| Page Views | SP-API Sales & Traffic Report | Total detail page views |
| CVR | SP-API Sales & Traffic | `total_units_sold / total_sessions` — **listing CVR, not ad CVR** |
| Buy Box % | SP-API Sales & Traffic Report | Session-weighted. 3-day reporting lag. |
| Impressions | Ads API per-ASIN | Ad impressions only |
| Clicks | Ads API per-ASIN | Ad clicks only |
| Spend | Ads API per-ASIN | Ad spend only |
| Orders | Ads API per-ASIN | Ad-attributed orders |
| Sales | Ads API per-ASIN | Ad-attributed sales |

### Profit formula (per ASIN)
```
profit = total_ordered_revenue - total_amazon_fees - (unit_cogs × units_sold) - direct_ad_spend
```

- `total_ordered_revenue` from SP-API Sales & Traffic (includes organic)
- `total_amazon_fees` from SP-API Finances API (per-ASIN actual, NOT account blended)
- `unit_cogs` from user-supplied COGS (per ASIN)
- `direct_ad_spend` from Ads API per-ASIN

If COGS missing for an ASIN → show `null` in profit column, not $0.

### CVR clarification
The CVR shown is `total_units_sold / total_sessions` (listing-level, all traffic).
It is NOT `ad_orders / ad_clicks` (that would be ad CVR).
Consider showing both in a tooltip.

### Buy Box + Ad suppression
Amazon suppresses Sponsored Products ads within 15-30 minutes of losing the buy box.
No charges while ineligible. On contested ASINs (buy box < 90%), campaign delivery starts/stops
erratically, fragmenting momentum.

Consider: flag ASINs with buy box < 80% and highlight their ACOS as potentially distorted.

### Data join
This table requires joining:
1. `ads_daily` per-ASIN (spend, clicks, impressions, orders, ad_sales)
2. SP-API Sales & Traffic per-ASIN (sessions, page_views, buy_box_pct, total_units, total_revenue)
3. SP-API Finances per-ASIN (fulfillment_fee, commission_fee)
4. COGS table per-ASIN (unit_cogs)

---

## 12. Section 11 — Campaign Table

### Columns
Campaign name, spend, ad sales, ACOS, estimated profit, cohort, opportunity score.

### Opportunity Score (custom, not Amazon's)
```
score = money_at_stake + distance_past_breakeven + unconverted_clicks
```

| Component | Max points | Calculation |
|---|---|---|
| Money at stake | 40 | Square-root scaled relative to max spend in table |
| Distance past break-even | 35 | 35 outright for campaigns with spend but $0 sales |
| Unconverted clicks | 25 | Clicks with no attributed order, scaled |

Show formula in hover tooltip so the number is auditable.

### Campaign cohort assignment
Same as §5: Profitable, Marginal, Unprofitable, No sales, No activity.

---

## 13. Status Signals System

### Method: Statistical (sigma / z-score), NOT fixed thresholds

### Baseline
Trailing 60 complete days (excluding today and yesterday).

### For each metric:
```python
historical_mean = mean(last_60_days)
historical_stddev = std(last_60_days)
sigma_distance = (today_value - historical_mean) / historical_stddev
```

### Classification thresholds

| Status | Condition |
|---|---|
| `on_track` | `abs(sigma) < 1.0` or favorable direction |
| `monitoring` | `1.0 ≤ abs(sigma) < 2.0` |
| `off_track` | `abs(sigma) ≥ 2.0` |

### Metrics tracked
total_sales, spend, tacos, impressions, clicks, cpc, ctr, cvr, total_orders,
units_sold, ad_orders, ad_sales, acos

### Outlier handling
60-day parametric rolling stats. Extreme shocks absorbed into σ over time rather than manually
purged. Peak retail events (Prime Day) normalized only when event model is explicitly configured.

---

## 14. Amazon API Hard Limits

Recorded so they are never asked for again.

1. **No hourly advertising data from Ads API.** `spCampaigns`, `spAdvertisedProduct`, and
   placement reports all reject `timeUnit: HOURLY`. Every row is one whole day. Hourly data
   requires AMS subscription (separate infrastructure).

2. **No placement split per ASIN.** Placement report groups by campaign with no ASIN column.
   Dividing placement spend between ASINs would be assumption, not measurement.

3. **SP-API Sales & Traffic lag.** Daily batch, 12-48h behind real-time. No intraday total sales.

4. **Finances API lag.** 24-72h behind physical shipment. Fee data for reclassified products
   only updates after first unit ships under new dimensions.

5. **Ad attribution windows are not configurable.** SP = 7 days, SB/SD = 14 days. Click day
   owns the sale. Data for trailing 2 days is always immature.

---

## 15. Database Schema

### New tables needed (in addition to existing `ads_daily`, `ads_campaign_daily`)

```sql
-- Hourly AMS data for day trail, heatmap, today banner
CREATE TABLE ads_hourly (
    workspace_id TEXT NOT NULL,
    marketplace_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    hour_start_utc TIMESTAMP NOT NULL,
    spend DECIMAL(10,2) DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    impressions INTEGER DEFAULT 0,
    ad_sales DECIMAL(10,2) DEFAULT 0,
    ad_orders INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, marketplace_id, campaign_id, hour_start_utc)
);
-- Upsert on (campaign_id, hour_start_utc) — AMS late events overwrite

-- Per-ASIN unit economics from SP-API
CREATE TABLE asin_unit_economics (
    workspace_id TEXT NOT NULL,
    marketplace_id TEXT NOT NULL,
    asin TEXT NOT NULL,
    date DATE NOT NULL,
    total_ordered_revenue DECIMAL(10,2),     -- SP-API Sales & Traffic
    total_units_sold INTEGER,
    sessions INTEGER,
    page_views INTEGER,
    buy_box_pct DECIMAL(5,2),
    realized_unit_price DECIMAL(10,2),       -- revenue / units
    fulfillment_fee DECIMAL(10,2),           -- SP-API Finances
    commission_fee DECIMAL(10,2),            -- SP-API Finances
    total_fees DECIMAL(10,2),
    fees_source TEXT DEFAULT 'finances_api',
    unit_cogs DECIMAL(10,2),                 -- user-supplied
    cogs_source TEXT,
    contribution_before_ads DECIMAL(10,2),   -- revenue - fees - cogs
    break_even_acos_pct DECIMAL(5,2),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, marketplace_id, asin, date)
);

-- Brand terms for branded/non-branded split
CREATE TABLE brand_terms (
    workspace_id TEXT NOT NULL,
    marketplace_id TEXT NOT NULL,
    term TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, marketplace_id, term)
);

-- Search term report (fixed window batches)
CREATE TABLE ppc_search_terms (
    workspace_id TEXT NOT NULL,
    marketplace_id TEXT NOT NULL,
    report_window_start DATE NOT NULL,
    report_window_end DATE NOT NULL,
    search_term TEXT NOT NULL,
    campaign_id TEXT,
    campaign_name TEXT,
    ad_group_id TEXT,
    keyword TEXT,
    match_type TEXT,
    spend DECIMAL(10,2) DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    impressions INTEGER DEFAULT 0,
    ad_sales DECIMAL(10,2) DEFAULT 0,
    ad_orders INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, marketplace_id, report_window_start, search_term, campaign_id)
);

-- Hour-shaped baseline cache for Today banner
CREATE TABLE hourly_baseline_cache (
    workspace_id TEXT NOT NULL,
    marketplace_id TEXT NOT NULL,
    hour_of_day INTEGER NOT NULL,  -- 0-23
    metric TEXT NOT NULL,          -- 'spend', 'clicks', 'impressions'
    trailing_7d_avg_cumulative DECIMAL(10,2),
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, marketplace_id, hour_of_day, metric)
);
-- Recompute hourly as AMS data lands
```

---

## 16. Build Order

### Phase 1 — Foundation (no AMS needed)
1. **KPI Row** — reads existing `ads_daily` account grain. Summed totals, sparklines, comparison.
2. **Campaign Table** — reads existing `ads_campaign_daily`. Cohorts + opportunity score.
3. **Budget & Pacing** — same data as KPI row, different presentation.

### Phase 2 — Per-ASIN economics
4. **ASIN Performance Table** — requires `asin_unit_economics` table. Build SP-API Sales &
   Traffic ingestion + Finances API ingestion. Join with existing ads per-ASIN data.
5. **Profitability Analysis** — requires ASIN economics. Build headline metrics, campaign cohorts,
   efficiency score.
6. **Profit per Click + Efficiency Trends** — daily series from Phase 2 data.

### Phase 3 — Search term features
7. **Brand Terms UI** — input field + `brand_terms` table.
8. **Branded vs Non-Branded** — requires search term report + brand terms.
9. **Wasted Spend** — requires search term report.

### Phase 4 — AMS Real-Time (REQUIRED — owner is setting up AWS in parallel)

**Owner will provide these Railway env vars before this phase starts:**
- `AWS_ACCESS_KEY_ID` — IAM user with `AmazonSQSFullAccess`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_SQS_QUEUE_URL` — full URL of the SQS queue (e.g. `https://sqs.us-east-1.amazonaws.com/123456789/alta-ams-queue`)
- `AWS_SQS_QUEUE_ARN` — ARN of the same queue (e.g. `arn:aws:sqs:us-east-1:123456789:alta-ams-queue`)
- `AWS_REGION` — `us-east-1` (or whichever region the queue lives in)

**Step 10 — AMS Subscription (code does this)**

Subscribe to AMS datasets using the existing Ads API credentials. Two subscriptions needed:

```python
# Using the existing amazon_ad module's auth
# Endpoint: Amazon Advertising API (same base URL already configured)

# Subscription 1: Traffic data (spend, clicks, impressions per hour)
POST /streams/subscriptions
{
    "dataSetId": "sp_traffic",
    "destinationArn": "{AWS_SQS_QUEUE_ARN}",
    "profileId": "{ads_profile_id}",         # from config.json
    "notes": "AltaScraper SP traffic stream"
}

# Subscription 2: Conversion data (attributed sales, orders per hour)
POST /streams/subscriptions
{
    "dataSetId": "sp_conversion",
    "destinationArn": "{AWS_SQS_QUEUE_ARN}",
    "profileId": "{ads_profile_id}",
    "notes": "AltaScraper SP conversion stream"
}
```

**Important:** The SQS queue needs a resource policy allowing Amazon Advertising to send messages.
Add this policy to the queue (Claude Code should provide owner with the exact JSON if needed,
or do it via boto3 if AWS creds have SQS policy permissions):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ads-stream.amazon.com"},
    "Action": "sqs:SendMessage",
    "Resource": "{AWS_SQS_QUEUE_ARN}"
  }]
}
```

**Step 11 — SQS Consumer Worker**

Build a worker process (new file: `workers/ams_consumer.py`) that:

1. Polls SQS queue using `boto3` (`pip install boto3`)
2. Parses each message — AMS sends JSON with fields:
   ```json
   {
     "campaignId": "123456",
     "timeWindowStart": "2026-09-06T14:00:00Z",
     "timeWindowEnd": "2026-09-06T15:00:00Z",
     "spend": 12.50,
     "clicks": 23,
     "impressions": 1450,
     "attributedSales7d": 45.99,
     "attributedOrders7d": 3
   }
   ```
3. Upserts into `ads_hourly` table keyed on `(workspace_id, marketplace_id, campaign_id, hour_start_utc)`
4. Deletes message from queue after successful processing
5. Handles late/revised events by overwriting (upsert) — Amazon sends corrections for earlier hours

**Worker deployment options (Railway):**
- Option A: Separate Railway service running the consumer as a long-polling loop
- Option B: Cron job that runs every 5 minutes, drains the queue, exits
- **Recommend Option A** for near-real-time. Use `while True` loop with `WaitTimeSeconds=20`
  (SQS long polling) to minimize API calls.

```python
# workers/ams_consumer.py — skeleton
import boto3, json, os, time
from app.database import db  # use existing DB connection

sqs = boto3.client('sqs',
    region_name=os.environ['AWS_REGION'],
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY']
)
QUEUE_URL = os.environ['AWS_SQS_QUEUE_URL']

def consume():
    while True:
        resp = sqs.receive_message(
            QueueUrl=QUEUE_URL,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20  # long poll
        )
        for msg in resp.get('Messages', []):
            body = json.loads(msg['Body'])
            # AMS wraps the payload — extract the inner detail
            detail = json.loads(body.get('Message', body))
            upsert_hourly(detail)
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=msg['ReceiptHandle'])

def upsert_hourly(record):
    # INSERT INTO ads_hourly ... ON CONFLICT (workspace_id, marketplace_id, campaign_id, hour_start_utc)
    # DO UPDATE SET spend=EXCLUDED.spend, clicks=EXCLUDED.clicks, ...
    pass

if __name__ == '__main__':
    consume()
```

**Step 12 — Hour-Shaped Baseline Cache**

After AMS data accumulates for 7+ days, build the baseline computation:

```python
def compute_hourly_baseline(workspace_id, marketplace_id):
    """
    For each hour 0-23, compute trailing-7-day average cumulative spend.
    Run this after each AMS batch lands (or on a 15-min cron).
    """
    for hour in range(24):
        # For each of the last 7 complete days:
        #   sum ads_hourly spend from hour 0 through this hour = cumulative_at_hour
        # Average those 7 cumulative values → store in hourly_baseline_cache
        pass
```

**Step 13 — Today Banner** — reads `ads_hourly` summed for today + `hourly_baseline_cache` for comparison.

**Step 14 — Day Trail sparklines** — reads `ads_hourly` per day, cumulative sum per hour for the curve.

**Step 15 — ACOS Heatmap** — reads `ads_hourly` aggregated by `(day_of_week, hour)`.
Only color cells with ≥10 clicks. Use click-hour for attributed sales mapping.

**Graceful degradation:** If AWS env vars are not set, the Today Banner should fall back to
showing yesterday's complete data from `ads_daily`. The day trail sparklines should show
daily totals as flat bars instead of hourly curves. The heatmap should show day-of-week only
(no hour axis). Never crash — check for `AWS_SQS_QUEUE_URL` in env before attempting AMS features.

### Phase 5 — Status signals
16. **Signals system** — 60-day rolling stats per metric, sigma classification.
    Can be computed nightly as a batch job.

---

## Appendix A: Owner Setup Checklist (Talal does these, Claude Code does NOT)

1. [ ] **SP-API: Enable Finance and Accounting role**
   - Seller Central → Apps & Services → Develop Apps → AltaScraper app → Edit → add role
   - Re-authorize any seller accounts that need Finances data

2. [ ] **AWS: Create account** — aws.amazon.com (or use existing)

3. [ ] **AWS: Create SQS queue**
   - Service: SQS → Create queue → Standard (not FIFO) → Name: `alta-ams-queue`
   - Region: `us-east-1`
   - Copy the Queue URL and Queue ARN

4. [ ] **AWS: Set queue access policy**
   - Queue → Access policy tab → Edit → add the `ads-stream.amazon.com` principal
     (Claude Code will output the exact JSON when it reaches Phase 4)

5. [ ] **AWS: Create IAM user**
   - IAM → Users → Create → Attach policy: `AmazonSQSFullAccess`
   - Create access key → copy Access Key ID + Secret

6. [ ] **Railway: Add env vars**
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_SQS_QUEUE_URL`
   - `AWS_SQS_QUEUE_ARN`
   - `AWS_REGION` = `us-east-1`

7. [ ] **Railway: Add worker service** (after Claude Code builds `workers/ams_consumer.py`)
   - New service in same Railway project → Start command: `python workers/ams_consumer.py`

---

## Appendix B: Key Numbers from Orbit (Promixx USA, 30-day window ending Sep 5 2026)

For validation / comparison if connecting the same account:

| Metric | Value |
|---|---|
| Spend | $11,768 |
| Ad Sales | $48,411 |
| ACOS | 24.3% |
| ROAS | 4.11x |
| Impressions | 1,850,119 |
| Clicks | 17,271 |
| CTR | 0.9% |
| Purchases (ad orders) | 2,323 |
| TACOS | 15.3% |
| Fee rate (actual) | 39.9% |
| COGS rate (sales-weighted) | 25.7% |
| Break-even ACOS | 34.4% |
| Net Profit | $10,762 |
| Wasted spend | $2,731 (23.2% of spend) |
| Efficiency score | 81.20 (Good) |
| Total search terms | 1,953 |
| COGS coverage | 93 of 144 ASINs (64.58%) |
| Campaigns (active + inactive) | 254+ |
| Products tracked | 50 |
