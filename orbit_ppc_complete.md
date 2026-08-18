# Orbit — the PPC / Advertising system, in full

**Captured** 18 Aug 2026 from `fullcircleorbit.com`, brand `flux-footwear`,
marketplace `ATVPDKIKX0DER` (Amazon US), by attaching to the signed-in Chrome
over the DevTools protocol. Raw fragments in `orbit_ppc/`; screenshots in
`orbit_ppc/shots/`.

Every section is marked **measured** (read off the rendered page), **quoted**
(Orbit's own words) or **inferred** (worked out, and said so). Nothing guessed is
presented as fact — the same rule the inventory capture followed, and for the
same reason: this document is being built from.

**Nothing was clicked that could write.** CLAUDE.md Rule 8 — never change a bid
or budget without an explicit instruction naming the value — and on an
advertising screen every "apply", "harvest", "negate" and "optimise" writes to
live campaigns spending real money on a client account. The extractor's `clicks`
part is hard-disabled for this section and must be armed by name.

---

## 1. The shape of it — five routes

| Route | Sidebar label | What it is |
| --- | --- | --- |
| `/ppc` | Advertising → PPC Analytics | the headline dashboard |
| `/ppc/search-terms` | Search Terms | per-search-term performance, 200 rows |
| `/ppc/campaigns` | Campaign Analytics | SP/SB/SD and match-type breakdown |
| `/ppc/live` | Live Tracker | today, by the hour |
| `/agents/dr-ppc-grok` | Dr PPC™ Console | a read-only analyst chat + an upsell |

**measured.** All five load real data on this account.

---

## 2. PPC Analytics — `/ppc`

**measured.** Subtitle, quoted: *"Advertising spend, sales, efficiency, and
campaign performance"*.

### The headline row

Six figures, each with a period-over-period change beneath it:

| Metric | Value seen | Change |
| --- | --- | --- |
| AD SPEND | $1,639 | −21.5% |
| AD SALES | $8,569 | −37.4% |
| TOTAL SALES | $18,150 | −30.3% |
| ACOS | 19.1% | +25.5% |
| TACOS | 9.0% | +12.7% |
| ROAS | 5.23 | −20.3% |

Stamped `TODAY · PDT · 9:05 PM` — the account's own timezone, not the viewer's.

**inferred**, and standard across the industry, so Orbit does not define them:

```
ACOS  = ad spend / ad sales
TACOS = ad spend / TOTAL sales          <- the one that matters
ROAS  = ad sales / ad spend             = 1 / ACOS
```

ACOS and TACOS together are the point: ACOS says whether the advertising pays
for itself, TACOS says what advertising costs the business. A brand can have a
healthy ACOS and a TACOS that is eating it, and only the second is visible here
because Orbit holds total sales as well as ad sales. **Checked:** 1,639 / 8,569
= 19.1% ✓ and 1,639 / 18,150 = 9.03% ✓. Both formulas confirmed against the
rendered figures.

### "Day trail"

**quoted:** *"Cumulative ad spend by hour · PDT"*. A 7 / 14 / 30-day toggle, and
a row per day carrying the date, the day's spend and its unit count:

```
TUE AUG 11  $2,004  77 units
WED AUG 12  $2,046  71 units
THU AUG 13  $2,018  78 units
FRI AUG 14  $1,969  107 units
SAT AUG 15  $1,837  ...
```

### Branded vs non-branded

A table with columns `METRIC | BRANDED | NON-BRANDED`, and an input reading
**"Add brand term…"**.

**This is the most transferable idea on the page.** The split is not something
Amazon reports — the seller types their own brand terms and Orbit partitions
every search term by whether it contains one. Branded spend is largely
defensive; non-branded spend is what actually grows the business, and mixing
them makes a healthy-looking ACOS out of paying to appear on your own name.

### The per-ASIN table

`ASIN | Profit | Sessions | Page Views | CVR | Buy Box | Impr | Clicks | Spend |
Orders`

**measured.** 50 products, selectable. Note it carries **Profit**, **Sessions**,
**Page Views** and **Buy Box** — traffic and profitability beside the ad
metrics, so a bad ACOS can be read as "the ads are wrong" or "the listing
converts badly" or "you lost the buy box" without leaving the screen.

---

## 3. Search Terms — `/ppc/search-terms`

**quoted:** *"Search term performance across all campaigns and keywords"*.

### Headline

| SPEND | SALES | ACOS | **WASTED SPEND** | ROAS | CTR | CVR | AVG CPC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| $54,364 | $364,009 | 14.9% | **$2,891** | 6.70x | 1.7% | 5.4% | $1.15 |

**WASTED SPEND is Orbit's own metric and the best thing on this page.**
**inferred:** spend on search terms that produced no sales in the window. At
$2,891 against $54,364 it is 5.3% of spend, which is a plausible zero-order
tail. It turns "your ACOS is 14.9%" into "here is £2,891 you could stop
spending", which is an action rather than a score.

### The table — 200 rows

`Opp | Search Term | Match Type | Profit | Clicks | CTR | CPC | CPA | Spend |
Sales | ACoS | RoAS`

**`Opp` is an opportunity flag** and is Orbit's own — **inferred**, it marks a
term worth acting on (harvest into exact, or negate). The column is first, ahead
even of the term itself, which says how the screen expects to be read: sort by
opportunity, work down the list.

Note **CPA** beside CPC: cost per *acquisition*, not per click. A term with a
cheap CPC and a terrible CPA is the expensive kind of cheap.

### Filters

Match type: `All | Exact | Phrase | Broad | Product Targeting`
Attribution: `Branded | Non-Branded` — with *"Add brand name to enable
filtering…"*, so the brand terms drive this page too.
Plus a free-text filter, Min/Max range sliders, and **Export**.

---

## 4. Campaign Analytics — `/ppc/campaigns`

**quoted:** *"Campaign type breakdown, match type performance, and top
campaigns"*.

**Table 1 — by type:**
`TYPE | CLICKS | CTR | CPC | CPA | SPEND | % SPEND | SALES | ACOS | PROFIT |
% PROFIT`

The two share-of-total columns are the point: **% SPEND against % PROFIT**. A
campaign type taking 40% of spend and returning 12% of profit is visible in one
glance without arithmetic.

**Table 2 — by campaign:**
`Opportunity | Campaign | Type | Status | Profit | Clicks | CTR | CPC | …`

Filters: `All | SP | SB | SD` and `Enabled | Paused`. Chart: "Campaign & Match
Type Breakdown — SP / SB / SD spend + match type performance", total spend
$54,202 over a 30-day daily series.

---

## 5. Live Tracker — `/ppc/live`

**quoted:** *"Advertising Dashboard - USA (ATVPDKIKX0DER)"*, *"All times in
PDT"*.

Views: `Last 24 Hours | Last 7 Days | Day by Day | Cumulative`.

| TOTAL AD SPEND | TOTAL SALES | TACOS | ACOS | TOTAL UNITS | TOTAL ORDERS |
| --- | --- | --- | --- | --- | --- |
| $1,645.85 | $17,990.00 | 9.15% | 19.21% | 126 | 120 |

Hourly buckets (`Aug 16, 10 PM`, `Aug 17, 12 AM`, …) and a "Show More ASINs
(5/178)" expander. This is the intraday view: the same metrics as `/ppc` but
answering "what is happening right now" rather than "what happened".

---

## 6. Dr PPC™ Console — `/agents/dr-ppc-grok`

Two things in one screen, and they are not the same product.

### The free part — a read-only analyst

**quoted:** *"Read campaigns, performance, search terms, and evidence for this
brand. Managed setup and changes stay locked."* and *"Base chat remains
read-only"*.

Five preset questions, numbered:

1. How is PPC performing over the last 30 days?
2. Which campaigns are spending the most right now?
3. Where are search terms wasting spend?
4. What changed versus the prior period?
5. Which evidence is missing or stale?

**Q5 is the interesting one.** An analyst that reports what it does NOT know is
worth more than one that always answers, and it is the same principle this app
applies to a missing cost or an unknown velocity.

### The paid part — "Managed PPC"

**quoted, in full**, because it is a description of how automated ad management
should be gated:

> **Current state** — A continuously refreshed mirror of campaigns, targeting,
> budgets, and readiness.
>
> **Goals and strategy** — Persistent business context that keeps every analysis
> aligned with the brand.
>
> **Analysis and recommendations** — Scheduled evidence-backed reviews with
> concrete proposals you can inspect.
>
> **Controlled execution** — Approval gates, reversible actions, and an audit
> trail before changes reach Amazon.
>
> *"Nothing changes without the configured controls."*

That last line is CLAUDE.md Rule 8 written by someone else. Propose, show the
evidence, gate the approval, keep the audit trail, make it reversible — and it
is exactly the shape the repricer in this app already has (dry run by default,
arm per SKU, a master switch, and every decision written down whether or not it
was applied).

---

## 7. What this app can and cannot copy

**measured, in AltaScraper, 18 Aug 2026:**

| | |
| --- | --- |
| `ads_daily` | **0 rows** (schema exists: impressions, clicks, spend, ad_orders, ad_sales) |
| `ppc_campaigns` | **0 rows** |
| Advertising API credentials | **none on any of the six accounts** |

So none of the above can be shown from live data today. That is not a gap in the
screens — it is that Amazon's Advertising API is a separate OAuth from SP-API
(its own client id, secret, refresh token and profile id) and it has never been
connected.

**But the data is obtainable without it.** `domain/ppc_module.py` already
ingests an **SP Search Term Report** downloaded from Seller Central, along with
Helium 10, DataDive and bulk exports, and normalises them to a canonical schema.
What it does not do is KEEP them: `/ppc/harvest` turns an upload into three CSVs
and throws the rows away.

**So the build is:** persist what is already ingested, and put Orbit's analytics
on top of it. Every metric above — spend, sales, ACOS, ROAS, CTR, CVR, CPC, CPA,
wasted spend, branded/non-branded, the per-term table with an opportunity flag,
the match-type breakdown — is computable from a Search Term Report alone.

TACOS needs total sales, which this app already has in `sales_daily` and
`order_lines`, so it can be shown honestly rather than left out.

What genuinely cannot be built without the Advertising API: the Live Tracker's
hourly view (the report is daily at best), campaign status/budgets, and anything
that writes. The first two should say why they are empty rather than showing
zero; the third is not wanted — Rule 8.
