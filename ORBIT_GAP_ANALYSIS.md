# Orbit vs AltaScraper — every Inventory and PPC feature, compared

    "please check all the features of the orbit related to ppc, and inventory,
     i want them added to my app. compare and add"

Built from the two captures: `orbit_inventory_complete.md` and
`orbit_ppc_complete.md`. Every row is one Orbit feature.

**Status** is one of:

| | |
| --- | --- |
| **done** | built and working on real data |
| **added** | built in response to this comparison |
| **adapted** | built, but answering the version of the question that applies here |
| **blocked** | cannot be built until something is connected — says what |
| **n/a** | genuinely does not apply to this business, with the reason |

---

## Inventory

| # | Orbit feature | Status | Notes |
| --- | --- | --- | --- |
| 1 | Cockpit banner: "N critical ASINs need action" | **done** | Names the product and the date, not just a count. |
| 2 | Next projected stockout | **done** | Leads with what is ALREADY out, which Orbit does not distinguish. |
| 3 | Inbound within 7 days | **n/a** | No inbound exists: merchant-fulfilled, stock is bought per order. |
| 4 | Revenue at Risk card | **done** | Formula inferred and stated; Orbit does not publish its own. |
| 5 | Inventory at Cost card | **done** | Orbit's rule, quoted: units x resolved cost per unit. |
| 6 | Avg Cover card | **done** | Over SKUs that HAVE cover, never averaging in the unsold. |
| 7 | Network Units / Amazon FBA cards | **adapted** | Zero FBA units on all six accounts. Shows LISTED quantity, named as the promise it is. |
| 8 | COGS Value card | **done** | |
| 9 | Review Queue card | **done** | Orbit's phrase; our gaps (no cost / quantity / sales / supplier). |
| 10 | Product table: PRODUCT / TOTAL / VEL / VALUE / DOS / STATUS | **done** | Plus RESTOCK, which Orbit has no data for. |
| 11 | F/A/3 stock split column | **n/a** | No AWD, no 3PL, no FBA. |
| 12 | Column sorting | **done** | Missing values sort last in both directions. |
| 13 | Search by ASIN / SKU / title | **done** | |
| 14 | Status legend, 5 states | **done** | Orbit's names in Orbit's order. |
| 15 | Row click -> ASIN detail | **added** | See below. |
| 16 | Pagination | **n/a** | 57 rows at most here; a filter row does the job. |
| 17 | **Forecasting tab** — projected burn over 3/6/9/12 months | **added** | See below. |
| 18 | **Actions tab** — approval queue | **added** | See below, as "What to order". |
| 19 | Shipments tab | **n/a** | Nothing is shipped to a warehouse. |
| 20 | Comms tab — supplier messaging | **blocked** | Deliberate: it sends messages to suppliers. Not built without an explicit instruction. |
| 21 | AutoPilot — automatic reordering | **blocked** | Would place purchase orders. Rule 8 territory; needs an explicit decision. |
| 22 | Steven, the inventory agent | **blocked** | Needs an LLM call per question; the app has Anthropic wired for copy, so it is possible — but it is a feature request, not a gap. |
| 23 | Reimbursements | **blocked** | Files claims with Amazon. Not built without an explicit instruction. |
| 24 | Settings at /cogs | **done** | The Costs sheet on the Listings screen. |

---

## PPC

| # | Orbit feature | Status | Notes |
| --- | --- | --- | --- |
| 1 | AD SPEND / AD SALES / TOTAL SALES headline | **done** | |
| 2 | ACOS / TACOS / ROAS | **done** | Formulas checked against Orbit's own rendered figures. |
| 3 | Period-over-period change on each | **added** | See below. |
| 4 | Day trail — cumulative spend by hour | **blocked** | The Search Term Report is not dated per row. Needs the Advertising API. |
| 5 | 7 / 14 / 30 day toggle | **blocked** | Same reason: one report is one window. |
| 6 | Branded vs non-branded, with "Add brand term" | **done** | The most transferable idea on Orbit's page. |
| 7 | Per-ASIN table with Sessions / Page Views / Buy Box | **blocked** | The Search Term Report has no ASIN column. Sessions and Buy Box come from the Business Report, which is a different upload. |
| 8 | Search Terms table with an Opportunity column | **done** | Ours says what the term DID, never what to do. |
| 9 | WASTED SPEND | **done** | Orbit's best metric; our definition stated. |
| 10 | Match type filters | **done** | |
| 11 | Min/Max range filters | **added** | See below. |
| 12 | **Export** | **added** | See below. |
| 13 | **Campaign Analytics — campaign-level table** | **added** | The report carries campaign and ad group. See below. |
| 14 | SP / SB / SD split | **blocked** | The Search Term Report is Sponsored Products only. Match type is the split that exists. |
| 15 | Enabled / Paused filter | **blocked** | Campaign status is not in the report. |
| 16 | % of spend vs % of profit | **done** | Orbit's own idea and the best pair of columns on its page. |
| 17 | Live Tracker — hourly | **blocked** | Needs the Advertising API. |
| 18 | Dr PPC console — read-only analyst | **done** | The PPC agent already on the page. |
| 19 | Managed PPC — approval gates, audit trail | **n/a** | It is Orbit's paid upsell. The repricer in this app already has that shape. |

---

## What "blocked" actually needs

**The Amazon Advertising API.** A separate OAuth from SP-API: its own client id,
client secret, refresh token and profile id, applied for in the Advertising
console. It unlocks items 4, 5, 15 and 17 above, plus campaign budgets and
statuses. `ads_daily` and `ppc_campaigns` already have the schema waiting.

**The Business Report** (Seller Central > Reports > Business Reports > Detail
Page Sales and Traffic). A second upload would unlock item 7 — sessions, page
views, buy-box percentage per ASIN. `domain/ppc_module.py` can already detect
report families, so it is a small job when wanted.

**A decision from you**, not a technical block: AutoPilot, Comms and
Reimbursements all WRITE — purchase orders, supplier messages, claims to Amazon.
Nothing in this app does that without being asked, and each needs its own
conversation about approval gates first.
