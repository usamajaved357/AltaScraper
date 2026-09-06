# PPC Analytics — what every section is, where its numbers come from, and what is still blocked

Written 6 Sep 2026. Every figure quoted was measured on **nestwell_goods / UK**
over the 30 days ending 6 Sep 2026 — the only account with an Amazon Advertising
login. Nothing here is illustrative.

---

## The short answer

**Most of the page is real.** Of the eleven sections, **eight are fully measured
from Amazon's own data**, one is partly limited by what Amazon publishes, and
**two are genuinely empty and waiting on something only you can supply.**

| # | Section | State | What is blocking it |
|---|---|---|---|
| 1 | Today banner | ✅ real | — |
| 2 | Day trail (7 cards) | ✅ real | — |
| 3 | KPI row (Spend/Sales/ACOS/ROAS/…) | ✅ real | the *change* arrows need a prior period with spend |
| 4 | Branded vs non-branded | ❌ **empty** | **you must supply your brand words** |
| 5 | Profitability analysis | ⚠️ real, one caveat | **only 31 of 52 orders have a cost** |
| 6 | Wasted spend | ✅ real | cannot follow the date picker — explained below |
| 7 | Profit-per-click / efficiency trends | ✅ real | — |
| 8 | ACOS heatmap + TACOS over time | ✅ real | — |
| 9 | Budget & pricing | ✅ real | — |
| 10 | ASIN performance | ✅ real | 31 of 49 have a picture |
| 11 | Campaign table | ✅ real | — |

The two empty ones are §4 and part of §5. **Both are waiting on you, not on
code.** The questions are at the end.

---

## Where the numbers come from

Four stores, filled by the nightly advertising sync. It matters which one a
figure comes from, because they cover different things.

| Store | What it holds | Grain |
|---|---|---|
| `ads_daily` (`asin='*'`) | the day's account-wide advertising | one row per day |
| `ads_daily` (per ASIN) | the same money split by product | one row per day per ASIN |
| `ads_campaign_daily` | the same money split by campaign | one row per day per campaign |
| `ads_placement_daily` | the same money split by placement | one row per day per placement |
| `ppc_search_terms` | the Search Term Report | **one fixed window, no daily split** |
| `sales_daily` (`asin='*'`) | total sales, advertised or not | one row per day |

**These are four cuts of the SAME money, not four pots.** All four come to
**£274.49** for the last 30 days. Adding any two together doubles it — a mistake
this app has made before and now has tests against.

**The last row is the important one.** The Search Term Report is a single fixed
window. Anything built on it — branded/non-branded, wasted spend, match types —
**cannot move with the date picker**, because the report has no day-by-day
breakdown to slice.

---

## Section by section

### 1. Today banner — REAL

Reads the **latest complete advertising day**, not today. Amazon does not report
advertising for the current day; measured on 6 Sep, the newest stored day was
**5 Sep** (a 1-day lag; it is usually 2).

Measured: 5 Sep — spend £14.10, ad sales £54.98, ACOS 25.6%, 56 clicks, 2 orders.

The banner says which day it is showing and how far behind that is. It is not
"today" and does not claim to be.

### 2. Day trail — REAL, and interactive

Seven cards, one per day, each showing that day's spend, its orders, and a small
curve of **cumulative spend from the start of the window to that day**.

Measured: 31 Aug £14.63 → 1 Sep £28.89 → 2 Sep £42.32 (cumulative).

**It is interactive**: hovering a card gives the date, that day's spend, its
orders and the running total; clicking one narrows the whole page to that single
day. The curve itself is a 120×50 sparkline — deliberately not the full chart
engine, because a hover card would be larger than the thing it describes.

> If the cards look static to you, the likely cause is a cached older build —
> the hover and click were added in the "real charts, real thumbnails" commit.

### 3. KPI row — REAL numbers, honest blank arrows

All eight figures are Amazon's, summed over the window from the account-grain
rows:

| Figure | Formula | Measured (30 days) |
|---|---|---|
| SPEND | Σ daily spend | £274.49 |
| SALES | Σ daily **ad** sales (attributed) | £859.00 |
| ACOS | spend ÷ ad sales | 32.0% |
| ROAS | ad sales ÷ spend | 3.13× |
| IMPRESSIONS | Σ daily impressions | 174,790 |
| CLICKS | Σ daily clicks | 1,057 |
| CTR | clicks ÷ impressions | 0.60% |
| PURCHASES | Σ daily ad orders | 36 |

**These are not placeholders.** They reconcile to the penny against the stored
rows — there is a test that fails if they stop doing so.

**Why the change arrows are blank on a 30-day view.** The comparison period is
9 Jul – 7 Aug, and this account had **no advertising at all** before 8 Aug. There
is nothing to compare against, so the arrow is a dash rather than "0%" — a nil
change would be a claim nobody measured.

Switch to **14 days** and 17 of the 18 arrows fill in: spend +75.2%, sales
+60.4%, orders +57.1%, ACOS +9.3pts. Measured.

### 4. Branded vs non-branded — EMPTY, and waiting on you

**This is the biggest genuinely blocked section.**

Amazon does not tell you which search terms are your brand. It cannot: only you
know your brand words. The split therefore needs a list from you — and this
account has none set, so the panel reports that rather than guessing.

**Why it matters more than it looks.** Paying to appear on your own name is
*defensive* spend — those customers were largely coming anyway. Mixed in with
everything else it makes a healthy-looking ACOS out of money that never won a new
customer. On 785 clicked terms, that is not a rounding error.

**What is needed:** your brand words — "Selvora", "Green Haven", "AltaboltaVoo",
"Jack Reacherd", plus common misspellings. Added on the PPC screen's brand box,
or tell me and I will add them.

### 5. Profitability analysis — REAL, with one honest caveat

This is the section you asked about specifically. **Here is exactly how profit is
worked out.**

Amazon attributes **sales** to a campaign. It does **not** attribute the referral
fee or the cost of the stock, and neither can be known per campaign. So profit
here applies **this account's own measured rates** to the sales Amazon
attributed:

```
profit = ad_sales − spend − (ad_sales × fee_rate) − (ad_sales × cogs_rate)
```

**fee_rate = 18.01%** — not a guess and not the usual 15%. Measured from what
Amazon actually charged this account: referral and FBA fees on £344.90 of settled
sales since 9 May. It is 18% rather than 15% because **Amazon charges VAT on its
own fees**. A further £61.28 of fixed charges (the monthly subscription) is *not*
a per-sale fee and is deliberately excluded from the rate.

**cogs_rate = 28.7%** — from the orders that actually have a cost recorded.

**break-even ACOS = 53.3%**, derived:

```
break_even_acos = (1 − fee_rate − cogs_rate) × 100
                = (1 − 0.1801 − 0.287) × 100 = 53.3%
```

Below 53.3% a campaign makes money; above it, it does not.

> **⚠️ THE CAVEAT, AND IT IS ON SCREEN TOO.** The cost rate is measured on
> **31 of 52 order lines** in this window. The other 21 have no cost recorded, so
> the 28.7% — and the 53.3% break-even built on it — describe a *minority* of the
> orders. If the uncosted 21 have a different margin, both figures move. **This
> is the single biggest thing you could fix to make this page more accurate.**

**Campaign cohorts** (254 campaigns, measured):

| Cohort | Rule | Count | Spend |
|---|---|---|---|
| Profitable | profit > 0 | 21 | £129.69 |
| Marginal | profitable by < 10% of spend | 1 | £34.16 |
| Unprofitable | profit < 0 | 1 | £22.34 |
| No sales | spent, sold nothing | **85** | **£88.30** |
| No activity | spent nothing | 146 | £0.00 |

**85 campaigns spent £88.30 and returned nothing.** That is a third of your spend
and the most actionable number on the page.

### 6. Wasted spend — REAL, but it does not follow the date picker

**£251.56 across 785 terms** that took at least one click and produced no order.
That is our definition, stated on the card — not "ACOS above target", which is a
judgement about price.

**A bug fixed today:** it used to show a change arrow against "the previous
period". Both readings came from the same fixed Search Term Report, so they were
**identical for every window** — 7, 14, 30 and 90 days all returned £251.56 and
the arrow always read zero. A comparison that cannot vary is not a comparison, so
the arrow is gone and the card now prints the window the figure actually covers.

### 7. Profit-per-click and efficiency trends — REAL

Two daily series, both derived from the same rates as §5.

- **Profit per click**: `(ad_sales − spend − fees − cogs) ÷ clicks`, per day.
  25 of 30 days carry a figure; the other 5 had no clicks.
- **Spend efficiency score**: how far that day's ACOS sits under break-even.
  18 of 30 days carry a figure — a day with no attributed sales has no ACOS, so
  it has no score either.

Days with no figure are **gaps, not zeros**. A line drawn to the floor would read
as "we stopped", which is a different fact from "Amazon reported nothing".

### 8. ACOS heatmap + TACOS over time — REAL

The heatmap is day × ACOS band, coloured in four bands (<26%, <35%, <43%, >43%).
An unmeasurable day is left blank rather than coloured green.

**TACOS** = spend ÷ **all** sales, advertised and organic together. Measured
20.7%.

> A second bug fixed today: TACOS used to divide by the whole window's sales
> while the spend covered only the days Amazon had reported. The ad feed runs
> ~2 days behind the sales feed, so the divisor included days the dividend could
> not — **TACOS came out too low, every day, always flattering.** It now divides
> over the days that have both, and says so when they differ.

### 9. Budget and pricing — REAL

Daily budgets and status per campaign, straight from `ads_campaign_daily`.

### 10. ASIN performance — REAL

49 products. Per product: spend, clicks, impressions, orders, ad sales, ACOS,
CVR, estimated profit, plus sessions, page views and buy-box % from the sales
report.

**31 of 49 carry a product picture**; the other 18 have no catalogue snapshot
stored, so the cell is empty rather than showing a broken image.

### 11. Campaign table — REAL

254 campaigns with spend, sales, ACOS, estimated profit, cohort and an
**Opportunity** score. That score is **ours, not Amazon's**, and the hover now
publishes the whole formula: up to 40 points for money at stake (square-root
scaled), up to 35 for distance past break-even (35 outright for spend that sold
nothing), up to 25 for clicks that bought no order.

---

## The chart style

Every chart on this page goes through **`salesCombo`** — the same engine the
Sales page uses. That means the same hover card, the same drag-across-to-zoom,
and the same clickable key, and it means these charts keep matching the Sales
page as that page changes.

The one exception is the day-trail sparkline (§2), which is 120px wide and gets a
hover tooltip instead, and the branded donut, which has no axes to hover along.

A second, non-interactive chart builder used to sit beside `salesCombo` in
`ppccharts.js` — four bespoke SVG functions that drew flat pictures. **Nine of
its ten functions had no caller at all**; it has been deleted, leaving only the
donut. That file went from 17,213 bytes to 3,777.

---

## Questions I need answered to finish this page

**These are the things I cannot determine from the data.**

### 1. Your brand words — unblocks §4 entirely
What words identify your brands in a search term? I would start with *Selvora,
Green Haven, AltaboltaVoo, Jack Reacherd, Nestwell*, plus misspellings, but I
should not guess at your brand list.

### 2. The 21 uncosted orders — improves §5 and every profit figure
21 of 52 order lines have no unit cost. Would you rather:
- **(a)** enter the missing costs (the Orders page takes a bulk file), or
- **(b)** I apply the measured 28.7% to the uncosted ones and label them as
  estimated, or
- **(c)** leave them out, which is what happens now?

I recommend **(a)**. Option (b) makes the page look more complete while being
less true.

### 3. What is your target ACOS?
Break-even is 53.3%, but break-even is not a target — it is where you stop losing
money. Most sellers run a target well below it. Without one, the page can say
"profitable" but not "good".

### 4. Should Sponsored Brands and Sponsored Display be pulled?
Only Sponsored Products is synced. If you run SB or SD, those figures are missing
entirely and the page does not currently say so loudly enough.

### 5. Do you want a wasted-spend threshold?
"Clicked and never ordered" is £251.56 across 785 terms. Most are 1–2 clicks and
pennies. Should terms below a spend floor be excluded so the list shows only
what is worth acting on?

---

## Two things Amazon simply will not give

Recorded so they are not asked for again.

**Hourly advertising data does not exist.** Asked directly on 6 Sep 2026:
`spCampaigns`, `spAdvertisedProduct` and the placement report all refuse
`timeUnit: HOURLY` with *"configuration timeUnit is not supported for this report
type"*. Every advertising row Amazon sends is one whole day. Any hourly chart
would be twenty-four invented points per day.

**Placement cannot be split per ASIN.** The placement report groups by campaign
and carries no advertised-ASIN column. A campaign usually advertises several
products, so dividing its placement spend between them would be an assumption
presented as a measurement.
