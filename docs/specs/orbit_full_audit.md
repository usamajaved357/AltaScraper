# Orbit — Full Product Audit

**Target:** `https://fullcircleorbit.com`
**Captured:** 13 Aug 2026, authenticated session, account `talal@fullcircleagency.com`, brand context `Lure Essentials` / marketplace `ATVPDKIKX0DER` (Amazon US)
**Method:** headless crawl over CDP against a logged-in Chrome 151 profile — 45 routes, full DOM snapshots, computed-style inventory across ~55,000 elements, all 27 CSS bundles, 559 XHR calls logged.

---

## 0. What this audit does and does not cover

Read this first — it tells you how far to trust each section.

**Solid, directly measured:**

- The route table (Part 1) — every URL was actually visited and returned a rendered page.
- Design tokens (Part 5) — read from Orbit's own `:root` custom properties. These are not inferred; they are the literal values the app ships.
- Component CSS (Part 4) — extracted from the shipped CSS modules, including hover/active/disabled/focus states.
- API surface (Part 7) — observed network traffic, not guesswork.

**Partial:**

- Screenshots capture the **first viewport only**. Orbit uses an app-shell layout (`height:100%` + inner `overflow-y:auto`), so full-page screenshot capture doesn't extend past the fold. Anything below the fold on each page is undocumented visually.
- Feature inventory (Part 2) is derived from rendered DOM — table headers, button labels, form fields present at load. Controls that only appear after interaction are missing.

**Not covered at all:**

- **Modals, drawers, dropdowns, hover states, animations in motion.** A URL crawl can't open them. Part 4 gives their CSS specs, but no captured instance.
- **Every write flow** — create/edit/delete/submit. The crawl was deliberately read-only; nothing was submitted and no records were touched. So "what validation fires on save" is unanswered.
- **Permissions.** Everything here is what *this* account sees. Role gating is inferred from route naming, not tested against a second account.
- **Light mode.** The app rendered dark throughout; no theme toggle was found in the captured DOM. See Part 5.7.

A second interactive pass would close the modal/drawer/hover gaps. Flagged at the end.

---

## 1. Sitemap

### 1.1 URL grammar

Three families:

```
/<global>                                      app-level
/brand/<brand-slug>/<page>                     brand-level, marketplace-independent
/brand/<brand-slug>/<marketplace-id>/<page>    marketplace-scoped
```

`<marketplace-id>` is the **Amazon marketplace ID** (`ATVPDKIKX0DER` = amazon.com), not an internal key. That's a deliberate choice worth copying: the URL is portable across environments and self-documenting, and switching marketplace is a path swap rather than a query param or session state. Brand is a human-readable slug (`lure-essentials`), so URLs are shareable and legible.

Note the inconsistency: some pages are brand-level (`/brand/lure-essentials/subscription`, `/api-connections`, `/notifications`, `/compliance/scans`) while most are marketplace-scoped. The split is semantic — billing and integrations are per-brand, analytics are per-marketplace — but `compliance/scans` sitting at brand level while `alerts` is marketplace-scoped looks more like drift than design.

### 1.2 Sidebar hierarchy (as rendered)

```
Orbit                                    → /brand                       [logo, home]
[Brand switcher: "Lure Essentials"]      → dropdown, 228×36 trigger
Brand Overview                    BETA   → /brand/{brand}

SALES & ANALYTICS                                                       [section label]
  [Marketplace switcher: 🇺🇸 USA]        → dropdown
  Sales                          ▾       → /brand/{brand}/{mp}
    Dashboard                            → /brand/{brand}/{mp}
    Hourly Sales                         → /brand/{brand}/{mp}/internal/hourly-sales
  Advertising                    ▾       → /brand/{brand}/{mp}/ppc
    PPC Analytics                        → /brand/{brand}/{mp}/ppc
    Search Terms                         → /brand/{brand}/{mp}/ppc/search-terms
    Campaign Analytics                   → /brand/{brand}/{mp}/ppc/campaigns
    Live Tracker                         → /brand/{brand}/{mp}/ppc/live
    Dr PPC™ Console                      → /brand/{brand}/{mp}/agents/dr-ppc-grok
  Keywords                               → /brand/{brand}/{mp}/sqp/asin-level
  Traffic                                → /brand/{brand}/{mp}/traffic
  Inventory                              → /brand/{brand}/{mp}/inventory
  Finance                                → /brand/{brand}/{mp}/finance
  ASINs                                  → /brand/{brand}/{mp}/asins
  Settings                               → /brand/{brand}/{mp}/cogs

TOOLS
  Connect WhatsApp                       → /brand/{brand}/{mp}/whatsapp-ava
  Dr PPC™ Console                        → /brand/{brand}/{mp}/agents/dr-ppc-grok

TRACKERS
  All Trackers                           → /brand/{brand}/{mp}/trackers
  BSR Tracker                            → /brand/{brand}/{mp}/bsr-tracker
  BuyBox Tracker                         → /brand/{brand}/{mp}/buybox-tracker
  Price Tracker                          → /brand/{brand}/{mp}/price-tracker
  Fee Tracker                            → /brand/{brand}/{mp}/fee-tracker
  Alerts                                 → /brand/{brand}/{mp}/alerts

NOTIFICATIONS
  Notifications                    503   → /brand/{brand}/notifications      [badge = unread count]

INTERNAL BETA                                                           [gated section]
  Agency                                 → /agency
  Feedback/Tickets                       → /feedback
  Leading Indicators                     → /brand/{brand}/{mp}/leading-indicators
  Category Explorer                      → /brand/{brand}/{mp}/internal/category-explorer
  Scout                                  → /brand/{brand}/{mp}/scout
  Compliance checker                     → /brand/{brand}/compliance/scans
  Ameer inventory                        → /brand/{brand}/{mp}/inventory/inventory-overview
  Ken inventory                          → /brand/{brand}/{mp}/inventory/overview

[User menu: T / Talal / talal@fullcircleagency.com]  → 236×42 trigger, bottom
```

### 1.3 Permission-gated surfaces

No second account was tested, so this is inference from naming and structure — treat as a hypothesis to verify:

| Surface | Signal | Confidence |
|---|---|---|
| `INTERNAL BETA` section | Explicit section label; the CSS has a dedicated `._adminSection_qc1hv_108` distinct from `._agencySection_qc1hv_103` | High |
| `/internal/*` routes | Path segment reserved for internal (`hourly-sales`, `category-explorer`) | High |
| `/agency`, `/agency/clients` | Agency-tier: multi-brand client list + cross-client sales overview | High |
| "Ameer inventory" / "Ken inventory" | **Developer names in production nav labels** — two competing unreleased builds of the same Inventory Overview screen, shipped side by side | High |
| `Brand Overview` | `BETA` badge, feature-flagged rather than role-gated | Medium |

The two developer-named inventory pages are the most telling artifact in the whole app: `/inventory/inventory-overview` and `/inventory/overview` are parallel implementations, both live, both linked from the nav, distinguished only by whose name is on them. If you're benchmarking against Orbit, that's an area they haven't settled.

### 1.4 Complete route table

| # | URL | Scope |
|---|---|---|
| 1 | `/` → redirects to brand context | app |
| 2 | `/brand` | app |
| 3 | `/brand/{brand}` — Brand Overview (BETA) | brand |
| 4 | `/brand/{brand}/{mp}` — Sales Dashboard | mp |
| 5 | `/brand/{brand}/{mp}/internal/hourly-sales` | mp / internal |
| 6 | `/brand/{brand}/{mp}/ppc` — PPC Analytics | mp |
| 7 | `/brand/{brand}/{mp}/ppc/search-terms` | mp |
| 8 | `/brand/{brand}/{mp}/ppc/campaigns` — Campaign Analytics | mp |
| 9 | `/brand/{brand}/{mp}/ppc/live` — Live Tracker | mp |
| 10 | `/brand/{brand}/{mp}/sqp/asin-level` — Keywords | mp |
| 11 | `/brand/{brand}/{mp}/sqp/keyword-ranking` | mp |
| 12 | `/brand/{brand}/{mp}/sqp-setup` | mp |
| 13 | `/brand/{brand}/{mp}/traffic` | mp |
| 14 | `/brand/{brand}/{mp}/inventory` | mp |
| 15 | `/brand/{brand}/{mp}/inventory/overview` — "Ken" build | mp |
| 16 | `/brand/{brand}/{mp}/inventory/inventory-overview` — "Ameer" build | mp |
| 17 | `/brand/{brand}/{mp}/inventory/sales-forecast` | mp |
| 18 | `/brand/{brand}/{mp}/inventory/forecasting` | mp |
| 19 | `/brand/{brand}/{mp}/inventory/actions` | mp |
| 20 | `/brand/{brand}/{mp}/inventory/shipments` | mp |
| 21 | `/brand/{brand}/{mp}/inventory/comms` | mp |
| 22 | `/brand/{brand}/{mp}/finance` | mp |
| 23 | `/brand/{brand}/{mp}/reimbursements` | mp |
| 24 | `/brand/{brand}/{mp}/manual-expenses` | mp |
| 25 | `/brand/{brand}/{mp}/cogs` — Settings | mp |
| 26 | `/brand/{brand}/{mp}/asins` | mp |
| 27 | `/brand/{brand}/{mp}/trackers` | mp |
| 28 | `/brand/{brand}/{mp}/bsr-tracker` | mp |
| 29 | `/brand/{brand}/{mp}/buybox-tracker` | mp |
| 30 | `/brand/{brand}/{mp}/price-tracker` | mp |
| 31 | `/brand/{brand}/{mp}/fee-tracker` | mp |
| 32 | `/brand/{brand}/{mp}/alerts` | mp |
| 33 | `/brand/{brand}/{mp}/leading-indicators` | mp / internal |
| 34 | `/brand/{brand}/{mp}/scout` | mp / internal |
| 35 | `/brand/{brand}/{mp}/internal/category-explorer` | mp / internal |
| 36 | `/brand/{brand}/{mp}/whatsapp-ava` | mp |
| 37 | `/brand/{brand}/{mp}/agents/dr-ppc-grok` | mp |
| 38 | `/brand/{brand}/notifications` | brand |
| 39 | `/brand/{brand}/notifications/config` | brand |
| 40 | `/brand/{brand}/api-connections` | brand |
| 41 | `/brand/{brand}/subscription` | brand |
| 42 | `/brand/{brand}/compliance/scans` | brand |
| 43 | `/agency` | app / agency |
| 44 | `/feedback` | app |
| 45 | `/feedback/changelog` | app |

**Public (unauthenticated):** `/login`, `/signup`, `/forgot-password`, `/support`, `/eula`, `/privacy`


---

## 2. Per-page feature inventory

Derived from rendered DOM at load. Table headers, button labels and form fields are what was actually present; controls that appear only after interaction are not listed. Screenshots cover the first viewport only.

### `/` — Root (redirects into brand context)

**Headings:** Lure Essentials - USA

**Table columns (1 table(s)):** `METRIC`, `8/11`, `8/10`, `8/9`, `8/8`, `8/7`, `8/6`, `8/5`, `8/4`, `8/3`, `8/2`, `8/1`, `7/31`, `7/30`, `7/29`, `7/28`, `7/27`, `7/26`, `7/25`, `7/24`, `7/23`, `7/22`, `7/21`, `7/20`, `7/19`, `7/18`, `7/17`, `7/16`, `7/15`, `7/14`, `7/13`

**Controls:** `7d`, `30d`, `90d`, `YTD`, `Aug`, `Jul`, `Jun`, `Export`, `?`, `All Products (42)`, `2026-07-12 to 2026-08-11`, `33/33 Metrics`, `Day`, `Week`, `Month`, `14d`, `60d`, `Custom`

**Inputs:** 1× select[select-one]

### `/brand` — Brand router

**Headings:** Lure Essentials - USA

**Table columns (1 table(s)):** `METRIC`, `8/11`, `8/10`, `8/9`, `8/8`, `8/7`, `8/6`, `8/5`, `8/4`, `8/3`, `8/2`, `8/1`, `7/31`, `7/30`, `7/29`, `7/28`, `7/27`, `7/26`, `7/25`, `7/24`, `7/23`, `7/22`, `7/21`, `7/20`, `7/19`, `7/18`, `7/17`, `7/16`, `7/15`, `7/14`, `7/13`

**Controls:** `7d`, `30d`, `90d`, `YTD`, `Aug`, `Jul`, `Jun`, `Export`, `?`, `All Products (42)`, `2026-07-12 to 2026-08-11`, `33/33 Metrics`, `Day`, `Week`, `Month`, `14d`, `60d`, `Custom`

**Inputs:** 1× select[select-one]

### `/brand/lure-essentials` — Brand Overview (BETA)

**Headings:** Lure Essentials

**Controls:** `USD`, `EUR`, `Refresh`, `Breakdown`, `Trends`, `View all 55 ASINs`, `View all 58 ASINs`, `View all 60 ASINs`, `View all 56 ASINs`, `View all 57 ASINs`, `Load 12 earlier months`

**State at capture:** empty / no-data

### `/brand/lure-essentials/ATVPDKIKX0DER` — Sales Dashboard

**Headings:** Lure Essentials - USA

**Table columns (1 table(s)):** `METRIC`, `8/11`, `8/10`, `8/9`, `8/8`, `8/7`, `8/6`, `8/5`, `8/4`, `8/3`, `8/2`, `8/1`, `7/31`, `7/30`, `7/29`, `7/28`, `7/27`, `7/26`, `7/25`, `7/24`, `7/23`, `7/22`, `7/21`, `7/20`, `7/19`, `7/18`, `7/17`, `7/16`, `7/15`, `7/14`, `7/13`

**Controls:** `7d`, `30d`, `90d`, `YTD`, `Aug`, `Jul`, `Jun`, `Export`, `?`, `All Products (42)`, `2026-07-12 to 2026-08-11`, `33/33 Metrics`, `Day`, `Week`, `Month`, `14d`, `60d`, `Custom`

**Inputs:** 1× select[select-one]

### `/brand/lure-essentials/ATVPDKIKX0DER/internal/hourly-sales`

### `/brand/lure-essentials/ATVPDKIKX0DER/ppc`

**Headings:** PPC Analytics · Profitability Analysis

**Table columns (1 table(s)):** `PROFIT`, `TRAFFIC`, `PAID`, `REVENUE`, `ASIN`, `Profit`, `Sessions`, `Page Views`, `CVR`, `Buy Box`, `Impr`, `Clicks`, `Spend`, `Orders`, `Sales`, `ACOS`, `ROAS`, `Total Orders`, `Total Rev`, `Organic Orders`, `Organic Rev`

**Controls:** `7 days`, `14 days`, `30 days`, `All Products (50)`, `2026-07-14 to 2026-08-12`

**Inputs:** 1× select[select-one], 1× input[text], 51× input[checkbox] — placeholders: 'Search by ASIN or title...'

### `/brand/lure-essentials/ATVPDKIKX0DER/sqp/asin-level`

**Headings:** Search Query Performance Breakdown

### `/brand/lure-essentials/ATVPDKIKX0DER/traffic`

**Headings:** Traffic & Conversions

**Table columns (1 table(s)):** `ASIN`, `Sessions`, `Page Views`, `Units`, `Revenue`, `CVR%`, `Buy Box%`

**Controls:** `2026-07-11 to 2026-08-10`

**Inputs:** 1× input[checkbox]

### `/brand/lure-essentials/ATVPDKIKX0DER/inventory`

**Headings:** Inventory · Inventory priorities

**Controls:** `30D`, `60D`, `90D`, `Export`

**Inputs:** 1× input[text], 1× input[checkbox] — placeholders: 'Search product, SKU, ASIN, FNSKU'

### `/brand/lure-essentials/ATVPDKIKX0DER/finance`

**Headings:** Finance · Product Contribution Margin

**Table columns (1 table(s)):** `Product`, `Units`, `Revenue ▾`, `Ad Spend`, `Amazon Fees`, `COGS`, `Refunds`, `Contribution`, `Margin`

**Controls:** `Order-based`, `Settlement`, `Account-level overhead
The gap bet`, `All`, `Active PPC`, `Profitable`, `Loss-Making`, `Group by parent`, `7 days`, `30 days`, `90 days`, `This month`, `This quarter`, `H1`, `Custom`

### `/brand/lure-essentials/ATVPDKIKX0DER/asins`

**Headings:** Product Catalog

**Table columns (1 table(s)):** `Image`, `ASIN`, `Title`, `Brand`, `Parent ASIN`, `Units Sold`, `Revenue ▾`, `COGS`, `Sales Period`, `Favourite`

**Controls:** `All`, `Last month`, `Last 3 months`, `Last year`, `«`, `‹`, `›`, `»`

**Inputs:** 1× input[text] — placeholders: 'Search all columns…'

### `/brand/lure-essentials/ATVPDKIKX0DER/cogs`

**Headings:** Lure Essentials

**Controls:** `COGS`, `Manual Expenses`, `Amazon Fees`, `Per-ASIN`, `% of Sales`

### `/brand/lure-essentials/ATVPDKIKX0DER/whatsapp-ava`

**Headings:** WhatsApp Ava

**Controls:** `Connect WhatsApp`

**Inputs:** 1× select[select-one], 1× input[tel], 1× input[checkbox] — placeholders: '202 555 0123'

### `/brand/lure-essentials/ATVPDKIKX0DER/agents/dr-ppc-grok`

**Headings:** Put Dr PPC to work beyond the chat · Current state · Goals and strategy · Analysis and recommendations · Controlled execution

**Controls:** `Ask Dr PPC about Console`, `01
How is PPC performing over the `, `02
Which campaigns are spending th`, `03
Where are search terms wasting `, `04
What changed versus the prior p`, `05
Which evidence is missing or st`

**Inputs:** 1× input[file], 1× textarea[textarea] — placeholders: 'Ask about PPC numbers, campaigns, or performance.'

### `/brand/lure-essentials/ATVPDKIKX0DER/trackers`

**Headings:** All trackers

**Table columns (1 table(s)):** `Status ▾`, `Product`, `60d Rev`, `BSR`, `BuyBox`, `Price`, `Fee`

**Controls:** `«`, `‹`, `›`, `»`

**Inputs:** 1× input[text], 3× input[checkbox] — placeholders: 'Search ASIN, title, brand'

### `/brand/lure-essentials/ATVPDKIKX0DER/bsr-tracker`

**Headings:** BSR Tracker

**Table columns (1 table(s)):** `Track`, `Image`, `ASIN`, `Title`, `See ranking`, `60d Rev ▾`, `Category`, `Subcategory`

**Inputs:** 1× input[checkbox], 1× input[text] — placeholders: 'Search…'

### `/brand/lure-essentials/ATVPDKIKX0DER/buybox-tracker`

**Headings:** BuyBox Tracker

**Table columns (1 table(s)):** `Track`, `Image`, `ASIN`, `Title`, `View`, `60d Rev ▾`, `BuyBox`, `BuyBox price`, `Our offer`, `Offers`, `Last fetched`

**Inputs:** 2× input[checkbox], 1× input[text] — placeholders: 'Search…'

### `/brand/lure-essentials/ATVPDKIKX0DER/price-tracker`

**Headings:** Price Tracker

**Table columns (1 table(s)):** `Image`, `ASIN`, `Title`, `60d Rev`, `Current price`, `Target`, `Drift`, `Last fetched`, `Track price`

**Controls:** `set target`

**Inputs:** 2× input[checkbox], 1× input[text] — placeholders: 'Search…'

**State at capture:** empty / no-data

### `/brand/lure-essentials/ATVPDKIKX0DER/fee-tracker`

**Headings:** Fee Tracker

**Table columns (1 table(s)):** `Image`, `ASIN`, `Title`, `60d Rev`, `Total fee`, `Amazon dims`, `Brand dims (L×W×H · wt)`, `Drift`, `Last fetched`, `Track fee`

**Controls:** `set dims`

**Inputs:** 2× input[checkbox], 1× input[text] — placeholders: 'Search…'

### `/brand/lure-essentials/ATVPDKIKX0DER/alerts`

**Headings:** Tracker alerts

**Controls:** `All
0`, `BuyBox
0`, `BSR
0`, `Price
0`, `Fee
0`

**Inputs:** 1× input[checkbox]

### `/brand/lure-essentials/notifications`

**Headings:** Notifications

**Controls:** `Alert guide`, `All severities`, `All types`, `INFO
FBM order resolved
US
closes `, `INFO
FBM order resolved
US
closes `, `INFO
FBM order resolved
US
closes `, `INFO
FBM order resolved
US
closes `, `INFO
FBM order resolved
US
closes `, `INFO
FBM order resolved
US
closes `, `INFO
FBM order resolved
US
closes `, `INFO
FBM order resolved
US
closes `, `INFO
Buy Box won
US
B01AB4B6YI

Bu`, `CRITICAL
Buy Box lost
US
B01AB4B6Y`, `CRITICAL
Pending FBM order
US
FBM `, `CRITICAL
Pending FBM order
US
FBM `, `CRITICAL
Pending FBM order
US
FBM `, `CRITICAL
Pending FBM order
US
FBM `, `CRITICAL
Pending FBM order
US
FBM `, `CRITICAL
Pending FBM order
US
FBM `, `CRITICAL
Pending FBM order
US
FBM `, `INFO
FBM order resolved
US
closes `, `INFO
FBM order resolved
US
closes `, `INFO
FBM order resolved
US
closes `, `Load more`

**Inputs:** 2× select[select-one], 1× input[text], 1× input[checkbox] — placeholders: 'ASIN'

### `/agency`

**Headings:** Clients

**Table columns (1 table(s)):** `BRAND`, `HEALTH`, `TAG`, `KAM`, `CSM`, `AUTH STATUS`, `JOINED DATE`, `ACTIONS`

**Controls:** `Manage`, `Edit`, `Add Brand`, `Load health data`, `Targets`

**Inputs:** 2× input[checkbox], 3× select[select-one]

### `/feedback`

**Headings:** Feedback / Tickets

**Table columns (1 table(s)):** `STATUS`, `TITLE`, `URGENCY`, `REPORTER`, `ASSIGNEE`, `ACTIVITY`, `UPDATED`

**Controls:** `New ticket`, `Help me report a bug`, `I want to request a new feature`, `Has anyone reported the dashboard `, `What happened to my tickets?`, `What's changed in Orbit recently?`

**Inputs:** 1× input[text], 2× select[select-one], 1× input[checkbox], 1× textarea[textarea] — placeholders: 'Search tickets...', 'Describe a problem or ask about a ticket...'

### `/brand/lure-essentials/ATVPDKIKX0DER/leading-indicators`

**Headings:** Leading Indicators · Daily Tracker · Segment Performance

**Table columns (2 table(s)):** `Name`, `Spend ▾`, `Spend %`, `Sales`, `Sales %`, `ACOS`, `Orders`, `Clicks`, `CTR`, `CVR`, `CPC`, `Name`, `Spend ▾`, `Spend %`, `Sales`, `Sales %`, `ACOS`, `Orders`, `Clicks`, `CTR`, `CVR`, `CPC`

**Controls:** `PPC`, `Supply chain`, `Yesterday`, `30d`, `60d`, `90d`, `7d`, `14d`

### `/brand/lure-essentials/ATVPDKIKX0DER/internal/category-explorer`

**Headings:** Category Explorer

**Controls:** `Your footprint`, `Explore full tree`, `Populate from Amazon`

### `/brand/lure-essentials/ATVPDKIKX0DER/scout`

### `/brand/lure-essentials/compliance/scans`

**Headings:** Compliance checker

**Controls:** `Buy credits`, `+ New scan`

**Inputs:** 1× input[text], 2× select[select-one] — placeholders: 'Search by ASIN, title, or brand...'

### `/brand/lure-essentials/ATVPDKIKX0DER/inventory/inventory-overview`

**Headings:** Inventory Overview

**Controls:** `30`, `60`, `90`, `Set All SKUs`

**Inputs:** 1× input[text], 1× input[checkbox], 1× select[select-one], 1× input[number] — placeholders: 'Search SKU, ASIN, FNSKU, parent'

### `/brand/lure-essentials/ATVPDKIKX0DER/inventory/overview`

**Headings:** 122 critical ASINs need action · Inventory by Product · Control tower, AutoPilot, and source setup

**Table columns (1 table(s)):** `PRODUCT ▽`, `F/A/3 ▽`, `TOTAL ▼`, `VEL ▽`, `VALUE ▽`, `DOS ▽`, `STATUS ▽`

**Controls:** `Run AutoPilot`, `Open action queue`, `Autopilot onboarding`, `Open reimbursements`, `B0DK66R6QC`, `B0D1KZ99M3`, `B0FHRSBMPZ`, `B0BQV35492`, `B0BQV1NTT4`, `B00P6UYGOU`, `B0FHRSM48R`, `B0CTGJCC7J`, `B0GR6KN386`, `B0GR6F8B8D`, `B0D1B4DJF1`, `B0GHB17WTL`, `B0GR6G34CJ`, `B0G2MWX81Q`, `B0G2KBJ4XR`, `B07DLH8Y3G`, `B0BD9BJMV8`, `B06XF31HR8`, `B00P82QFPY`, `B00UXW8IAY`, `B00P86S3IM`, `B01AB4B6YI`, `B01MRHLZH5`, `B0D27HL3GD`, `B01DC5VU5S`, `Prev`, `Next`

**Inputs:** 1× input[text], 10× input[checkbox], 1× input[number], 1× textarea[textarea], 1× input[file] — placeholders: 'Search by ASIN, SKU, or title...', 'Optional operator note for approval and run history.'

### `/brand/lure-essentials/ATVPDKIKX0DER/ppc/search-terms`

**Headings:** Search Terms

**Controls:** `All Products (0)`, `2026-07-13 to 2026-08-11`

### `/brand/lure-essentials/ATVPDKIKX0DER/ppc/campaigns`

**Headings:** Campaign Analytics · Campaign Profitability Map

**Table columns (1 table(s)):** `Opportunity`, `Campaign`, `Type`, `Status`, `Profit`, `Clicks`, `CTR`, `CPC`, `CPA`, `Spend`, `Sales`, `ACoS`, `RoAS`

**Controls:** `2026-07-13 to 2026-08-11`, `All`, `SP`, `SB`, `SD`, `Enabled`, `Paused`

**Inputs:** 1× input[text], 1× input[number], 2× input[range] — placeholders: 'Search campaigns...', '0'

### `/brand/lure-essentials/ATVPDKIKX0DER/ppc/live`

**Headings:** Lure Essentials

**Controls:** `Last 24 Hours`, `Last 7 Days`, `Day by Day`

**Inputs:** 1× input[checkbox]

### `/brand/lure-essentials/ATVPDKIKX0DER/sqp/keyword-ranking`

**Headings:** Keyword Ranking

**Table columns (1 table(s)):** `Keyword`, `Volume`, `Impr.`, `Clicks`, `Cart Adds`, `Purchases`, `Our CVR`, `Mkt CVR`, `Conv Δ`, `Aug 13`, `Aug 12`, `Aug 11`, `Aug 10`, `Aug 9`, `Aug 8`, `Aug 7`, `Aug 6`, `Aug 5`, `Aug 4`, `Aug 3`, `Aug 2`, `Aug 1`, `Jul 31`, `Jul 30`, `Jul 29`, `Jul 28`, `Jul 27`, `Jul 26`, `Jul 25`, `Jul 24`, `Jul 23`, `Jul 22`, `Jul 21`, `Jul 20` …

**Controls:** `Add Keyword`, `7d`, `14d`, `30d`, `60d`, `90d`, `Fetch Rankings`, `Add`, `B0D1KZ99M3
You`, `Show Opportunities`, `Columns`

**Inputs:** 3× input[text], 1× input[checkbox] — placeholders: 'Add keyword to track…', 'Add a keyword to track…', 'Add ASIN...'

### `/brand/lure-essentials/ATVPDKIKX0DER/reimbursements`

**Headings:** Reimbursements · By category · By ASIN

**Table columns (1 table(s)):** `ASIN`, `Paid (window) ▾`, `Est. claimable`, `Customer Returned`, `Damaged`, `Lost & Misplaced`, `Missing FBA`

**Inputs:** 2× input[date]

### `/brand/lure-essentials/ATVPDKIKX0DER/manual-expenses`

**Headings:** Lure Essentials

**Table columns (1 table(s)):** `Date ▾`, `Description`, `Amount`

**Controls:** `COGS`, `Manual Expenses`, `Amazon Fees`, `Add expense`

**Inputs:** 1× input[text] — placeholders: 'Search description...'

### `/brand/lure-essentials/ATVPDKIKX0DER/sqp-setup`

**Headings:** SQP Setup

**Table columns (1 table(s)):** `Image`, `ASIN`, `Title`, `60d Revenue ▾`, `Track SQP`, `Last SQP week`

**Controls:** `Child ASINs`, `Parent ASINs`, `«`, `‹`, `›`, `»`

**Inputs:** 1× input[text] — placeholders: 'Search ASIN or title…'

### `/brand/lure-essentials/api-connections`

**Headings:** API Connections · Complete Your Setup

**Controls:** `Finalise Setup`

### `/brand/lure-essentials/subscription`

**Headings:** Subscription · Current plan
PRO · Let Full Circle run PPC for this brand

**Controls:** `Contact us about Managed PPC`

### `/brand/lure-essentials/notifications/config`

**Headings:** Alert settings

**Table columns (1 table(s)):** `Foreign seller`, `On latest snapshot`, `Alert slots ▾`, `Buy-box share`, `ASINs (all-time)`, `Marketplaces`, `Days seen`, `Min price`, `Feedback`, `Ruling`

**Controls:** `Hijacker protection`, `Capacity limits`, `Enable…`

**Inputs:** 1× input[text] — placeholders: 'Search seller id / marketplace…'

**State at capture:** empty / no-data

### `/feedback/changelog`

**Headings:** Feedback / Tickets

**Controls:** `New ticket`, `Help me report a bug`, `I want to request a new feature`, `Has anyone reported the dashboard `, `What happened to my tickets?`, `What's changed in Orbit recently?`

**Inputs:** 1× textarea[textarea] — placeholders: 'Describe a problem or ask about a ticket...'

### `/brand/lure-essentials/ATVPDKIKX0DER/inventory/sales-forecast`

### `/brand/lure-essentials/ATVPDKIKX0DER/inventory/forecasting`

**Headings:** Autonomous Replenishment Forecasting · Inventory Projections · Forecast scope and assumptions

**Controls:** `Ask Steven for forecast plan`, `Generate actions`, `Review queue`, `Overview`

**Inputs:** 2× input[range], 4× input[number]

### `/brand/lure-essentials/ATVPDKIKX0DER/inventory/actions`

**Headings:** Loading execution readiness · Approval Queue · Readiness and planner context · Secondary action detail

**Controls:** `Generate queue`, `Adjust forecast`, `Overview`

### `/brand/lure-essentials/ATVPDKIKX0DER/inventory/shipments`

### `/brand/lure-essentials/ATVPDKIKX0DER/inventory/comms`

**Headings:** Inventory Comms · Thread connection and sync setup · Chronological source timeline for Inventory updates · What the user or Steven should handle next · Messages Steven should be able to prepare · Draft previews, extraction map, and implementation detail

**Controls:** `Ask tracking`, `Parse reply`, `Build PO packet`, `Client update`

**Inputs:** 4× input[text], 1× select[select-one], 1× textarea[textarea] — placeholders: 'https://mail.google.com/mail/#all/... or thread/message ID', 'Walkize PO, shipment, invoice, tracking, carton evidence...', 'Ivy, Forest Shipping, PrepFBA...', 'Comma-separated PO, FBA, SKU, ASIN, tracking refs'


---

## 4. UI Component Library

Orbit is built with **CSS Modules** (class names hash to `_name_<modulehash>_<line>`) on top of a global custom-property token layer. 130 distinct style modules ship in the main bundle. That architecture matters for you: the tokens are global and consistent, but each feature area has its own module that frequently *overrides* them with hardcoded values. Where I flag "off-token", that's the app disagreeing with itself, not a measurement error.

All values below are read from shipped CSS or measured computed styles.

### 4.1 Sidebar — `_sidebar_qc1hv_14`

| Property | Value |
|---|---|
| Width | `260px` fixed (`flex-shrink:0`) |
| Background | `var(--color-bg-secondary)` = `#252937` |
| Border | `1px solid var(--color-border-primary)` (`#374151`) on right |
| Layout | `flex column`, `overflow-y:auto`, `overflow-x:hidden` |
| Header | `padding:12px 16px`, background `--color-bg-primary` (darker than sidebar body) |
| Logo | 18px tall icon + wordmark at `20px/600`, `letter-spacing:-0.5px`, `line-height:1` |
| Collapse | `._sidebarCollapsed_qc1hv_36` — header re-centers, padding drops to `12px 8px`; toggle is a 24×24 icon button |

**Nav item** (`._navItem_qc1hv_232`):

```css
display:flex; align-items:center; gap:8px;
padding:8px 16px;
color:var(--color-text-secondary);      /* #d1d5db */
font-size:14px; font-weight:500;
transition:all var(--transition-base);  /* .3s ease */
position:relative;
```

- **Hover:** `background:var(--color-bg-tertiary)` (`#2d3242`), `color:--color-text-primary`
- **Active** (`._navItemActive_qc1hv_259`): `background:#4f46e51a` (indigo 10%), `color:var(--color-primary)` (gold), plus a `::before` **3px gold left rail** spanning full height — this is the signature active treatment
- **Icon:** `min-width:24px`, `color:--color-text-tertiary`, transitions independently on `--transition-fast`

Note the active state mixes an **indigo background** with a **gold foreground**. `#4f46e5` appears nowhere in the token set — a leftover from a previous indigo brand. Copy the pattern, not that value.

**Section labels** (`SALES & ANALYTICS`, `TOOLS`, `TRACKERS`): uppercase, `--font-size-xs` (10px), letter-spaced, tertiary color. Sections separated by `border-top:1px solid var(--color-border-primary)` with `padding:8px 0`.

**Quick actions block** (`._quickActions_qc1hv_120`) — a distinct visual treatment worth noting: a grouped card inset in the sidebar, `background:#ffffff08`, `border:1px solid rgba(255,255,255,.06)`, `border-radius:10px`, `padding:3px`, items at `7px 10px` with `border-radius:7px`. Icons get a 24×24 tinted tile using `color-mix(in srgb, var(--color-primary) 10%, transparent)`.

**Footer:** user menu trigger, 236×42, `border-radius:6px`, avatar initial + name + email stacked.

**Badges in nav:** `BETA` pill (38×18, `background:rgba(255,193,7,.12)`, `padding:1px 6px`); notification count badge showing `503`.

### 4.2 App shell / content area

```css
._layout_qc1hv_1 {
  display:flex; flex:1; height:100%; overflow:hidden;
  padding-right:var(--chat-drawer-width, 0px);
  transition:padding-right .15s ease;
}
._content_qc1hv_843 { padding:32px; background:var(--color-bg-primary); }
```

Measured content area: **774×613** at a 1034px viewport (sidebar 260 + content 774).

The `--chat-drawer-width` custom property on the layout is the mechanism for the AI assistant drawer: opening it sets the variable, and the whole app shell **squeezes** rather than being overlaid. Elegant, and cheap to implement — one variable, one transition.

**There is no top bar on desktop.** `<header>` exists but measures 0×0 — it's `._mobileTopBar_qc1hv_968`, rendered only under the mobile breakpoint with a burger button. Page title, date range, and export controls live *inside* the content area per page, not in a global chrome bar.

### 4.3 Buttons — `_button_1osxa_2` (canonical component)

```css
._button_1osxa_2 {
  display:inline-flex; align-items:center; justify-content:center; gap:6px;
  font-family:var(--font-family-base);
  font-weight:var(--font-weight-medium);
  border-radius:var(--radius-md);        /* 6px */
  border:1px solid transparent;
  cursor:pointer; white-space:nowrap;
  transition:all var(--transition-fast);  /* .2s ease */
}
._button_1osxa_2:disabled     { opacity:var(--opacity-disabled); cursor:not-allowed; }  /* .6 */
._button_1osxa_2:focus-visible{ outline:none; box-shadow:var(--shadow-focus); }
```

**Sizes:**

| Size | Padding | Font size | Height |
|---|---|---|---|
| `sm` | `4px 12px` | `10px` | `28px` |
| `md` | `8px 16px` | `12px` | `36px` |
| `lg` | `12px 20px` | `14px` | `44px` |

**Variants:**

| Variant | Rest | Hover | Active/selected |
|---|---|---|---|
| `primary` | `background:var(--color-primary-gradient)` (135° `#fde047`→`#f59e0b`), `color:var(--color-bg-primary)`, no border, `box-shadow:var(--shadow-xl)` | gradient darkens to `#f59e0b`→`#d97706`, `transform:translateY(-1px)`, `box-shadow:0 6px 20px #fbbf2466` | gradient + `--shadow-xl` |
| `secondary` | transparent, `color:--color-text-primary`, `1px solid --color-border-primary` | `border-color`+`color` → gold, `background:#fbbf240d` | gold gradient fill, dark text, `font-weight:600` |
| `ghost` | transparent, `color:--color-text-secondary`, no border | `color:--color-text-primary`, `background:--color-bg-secondary` | `color:--color-primary`, `background:#fbbf241a`, `font-weight:600` |

`:active` on primary resets `translateY(0)` — a press-down effect against the hover lift. That's the entire click animation; **no ripple anywhere in the app**.

**No `danger` variant exists in the canonical component.** Destructive actions are styled ad hoc per module using `--color-error`. If you're building a system, that's a gap to fill rather than a pattern to copy.

Caveat: 112 distinct button class signatures were measured across the app. The canonical `_1osxa_` component accounts for a minority — most feature modules roll their own (`_refreshBtn_1npn8_211`, `_secondaryButton_and57_639`, `_targetsButton_and57_446`, …), typically at 26–29px height with 10–12px text. Orbit's real button system is less unified than the token layer suggests.

### 4.4 Tables — `_table_rfi82_1039`

```css
._tableWrapper_rfi82_1039 {
  background:#0f172a52;                       /* slate-900 @ 32% */
  border:1px solid rgba(148,163,184,.14);
  border-radius:10px;
  overflow-x:auto; overflow-y:hidden;
}
._table_rfi82_1039 {
  width:100%; min-width:min(960px,100%);
  table-layout:fixed;
  border-collapse:separate; border-spacing:0;
  font-size:12px;
}
```

| Element | Spec |
|---|---|
| Header row | `background:#333c52b8` |
| `th` | `11px / 800 weight`, `color:#b9c2d2`, `uppercase`, `letter-spacing:.06em`, `white-space:nowrap`, `user-select:none`, bottom border `rgba(148,163,184,.16)` |
| `th:hover` / sorted | `color:var(--color-text-primary)` — the only sort affordance besides the indicator |
| `td` | `padding:10px 9px`, `color:--color-text-secondary`, **`font-variant-numeric:tabular-nums`**, `white-space:nowrap`, `vertical-align:middle`, bottom border `rgba(148,163,184,.1)` |
| Row height | ~24–28px measured — dense by design |
| Row hover | `._tableRow:hover ._td { background:#ffffff08 }`, `transition:background .12s ease`, `cursor:pointer` (rows are clickable → drawer) |
| Last row | bottom border removed |
| Emphasis | `._tdMain` = primary color + `font-weight:700`; `._tdMuted` = tertiary color |

`tabular-nums` on every cell is the right call for financial tables and worth copying verbatim.

**Column widths are declared as a CSS custom property**, e.g.:

```css
--ppc-campaign-columns: minmax(0,460px) 104px 90px 90px 80px 80px 90px …
```

So column layout is a single token per table, not per-cell rules. Clean pattern. No evidence of user-resizable columns.

Largest measured table: **2240px wide × 1098px tall** (heatmap) inside a 774px viewport — heavy horizontal scroll is normal here.

### 4.5 Detail drawer — `_drawer_rfi82_1407`

Row clicks open a **right-side drawer**, not a page navigation:

```css
._drawerBackdrop { position:fixed; inset:0; background:#00000073; z-index:200;
                   animation:_fadeIn .15s ease; }
._drawer { position:fixed; top:0; right:0; bottom:0;
           width:min(560px, calc(100vw - 12px));
           background:var(--color-bg-primary);
           border-left:1px solid var(--color-border-primary);
           box-shadow:-8px 0 32px #00000080;
           z-index:201;
           animation:_slideLeft .2s ease; }
._drawerHeader { padding:12px; border-bottom:1px solid var(--color-border-primary);
                 display:flex; justify-content:space-between; gap:8px; }
._drawerTitle  { font-size:18px; font-weight:600; font-family:monospace; }
._drawerSubtitle{ font-size:10px; color:var(--color-text-tertiary); }
._drawerBody   { flex:1; overflow-y:auto; padding:12px;
                 display:flex; flex-direction:column; gap:12px; }
```

Backdrop fades in 150ms; panel slides 200ms. Drawer title uses **monospace** — it holds ASINs/SKUs.

### 4.6 Modal — `_modal_19svp_523`

```css
._modal { position:fixed; inset:0; background:#00000080;
          display:flex; align-items:center; justify-content:center;
          z-index:1000; padding:16px;
          animation:_fadeIn .2s; }
._modalContent { background:var(--color-background-default);
                 border-radius:var(--radius-lg);   /* 8px */
                 max-width:900px; max-height:90vh; width:100%;
                 overflow:hidden; display:flex; flex-direction:column;
                 animation:_slideIn .3s; }
._modalHeader { display:flex; justify-content:space-between; align-items:center;
                padding:16px; border-bottom:1px solid var(--color-border-subtle); }
._modalHeader h2 { font-size:20px; word-break:break-all; }
._closeButton { background:none; border:none; font-size:20px;
                color:var(--color-text-secondary); transition:color .2s; }
._closeButton:hover { color:var(--color-text-primary); }
._modalBody { padding:16px; overflow-y:auto; flex:1; }
```

Overlay fades 200ms, content slides 300ms. Centered, capped at 900×90vh, header/body/footer flex column with only the body scrolling.

**Inconsistency to note:** the modal uses `--color-background-default` and `--color-border-subtle` — **neither token exists in `:root`**. Both silently resolve to nothing. Modals inherit whatever the parent background is. That's a live bug in Orbit; don't replicate it.

`z-index` is hardcoded `1000` here but `--z-modal` is defined as `100`. The token layer and the components disagree.

### 4.7 Tabs — `_tab_q4apm_1`

```css
._tabs { display:flex; gap:4px; }
._tab  { background:transparent;
         border:1px solid var(--color-border-secondary);   /* #4b5563 */
         border-radius:var(--radius-lg);                    /* 8px */
         color:var(--color-text-tertiary);
         font-weight:500; display:inline-flex; gap:8px;
         transition:color .2s, border-color .2s, background .2s; }
._tab:hover { color:var(--color-text-primary); border-color:var(--color-text-tertiary); }
._tab:focus-visible { outline:none; box-shadow:var(--shadow-focus); }
._active { color:var(--color-bg-primary); background:var(--color-primary);
           border-color:var(--color-primary); font-weight:600; }
._active:hover { background:var(--color-primary-dark); }
```

Sizes: `sm` = `4px 12px / 10px`, `md` = `8px 16px / 12px`.
Second variant `._variant_underline_q4apm_64` — `gap:2px`, `border-bottom` on the container, used where tabs sit flush against content (measured 163×44 with `border-radius:6px 6px 0 0`).

### 4.8 Forms — `_input_kysn7_74`

```css
._label { font-size:12px; font-weight:500; color:var(--color-text-primary); }
._input { padding:12px 16px;
          background:var(--color-bg-primary);
          border:1px solid var(--color-border-primary);
          border-radius:var(--radius-md);
          font-size:14px; color:var(--color-text-primary);
          transition:var(--transition-fast); }
._input:focus { outline:none;
                border-color:var(--color-primary);
                box-shadow:var(--shadow-focus); }  /* 0 0 0 3px rgba(251,191,36,.3) */
```

Focus ring is a **3px gold glow**, applied consistently across inputs, buttons and tabs via `--shadow-focus`. That consistency is the strongest part of Orbit's system — worth copying wholesale.

**Validation display:**

```css
._errorMessage { padding:16px; background:#fee; border:1px solid #fcc;
                 border-radius:6px; color:#c00; font-size:12px; }
```

`#fee` / `#fcc` / `#c00` are **light-theme values on a dark app** — near-white background, in a dark UI, off-token (`--color-error` is `#ef4444`). This is unmigrated legacy CSS. Definitely don't copy.

Selects measured at 150×38 with `padding:4px 8px`, `background:--color-bg-primary`. A custom dropdown trigger (`_trigger_nx1ue_6`) is used for the brand/marketplace switchers: 240×36, `background:#2d3242`, `border-radius:8px`, `padding:7px 12px`, `13px` text.

**Date range control:** a button (`_dateButton_bfwpe_160`, 175×24) displaying `2026-07-14 to 2026-08-12` with a calendar icon, opening a picker. Paired everywhere with **preset pills** — `7d / 30d / 90d / YTD` plus named months (`Aug / Jul / Jun`) — as a segmented control (`_option_wl90e_11`, 37×18, `border-radius:4px`, `10px/600`, active = solid gold `#fbbf24`).

### 4.9 Stat cards — `_statCard_xa5pv_431`

Measured **156×104**, `padding:12px`, `background:#2d3242` (`--color-bg-tertiary`), inside a grid at `--grid-gap-base:20px`.

Skeleton counterpart (`_metricSkeleton_1hnpl_29`) is more elaborate than the card: `min-height:154px`, `padding:16px`, and a two-layer background — `linear-gradient(180deg, color-mix(--color-bg-tertiary 38%, transparent), transparent 58%)` over `--color-bg-secondary`, `border-radius:8px`, `overflow:hidden` for the sweep.

### 4.10 Status indicators

Two shapes coexist:

- **Pills** — `border-radius:999px` (250 uses) or `9999px` (90 uses); both present, so pick one for your own system.
- **Dots** — 10×10, `border-radius:50%`, muted/active variants (`_laneDot_1jeez_27`, `_dotMuted_1jeez_63`).

Semantic tinting follows a consistent formula: `rgba(<semantic>, .10–.16)` background + `rgba(<semantic>, .26)` border + solid semantic text.

| Meaning | Color | Tint background |
|---|---|---|
| Success / good | `#22c55e`, `#10b981` | `rgba(34,197,94,.10 → .15)` |
| Error / bad | `#ef4444` | `rgba(239,68,68,.10 → .16)` |
| Warning | `#f59e0b` | `rgba(251,191,36,.18)` |
| Info | `#3b82f6` | `rgba(59,130,246,.08)` |

`--color-primary-alpha` (`rgba(251,191,36,.18)`) is the token for the gold tint.

### 4.11 Charts

Recharts-style SVG (axis/grid/tooltip DOM structure). Observed:

- **Line** — today vs yesterday overlay, gold `#fbbf24` for current, grey dashed for comparison
- **Area** — gradient fill under line, blue-tinted (Week to Date)
- **Scatter/bubble** — "Campaign Profitability Map"; bubble size = sales volume, color = ACOS band
- **Heatmap table** — metrics × dates grid, 2240px wide, cell tinting by value

Chart-specific keyframes exist: `_chartFadeIn_1f2qi_1`, `_chartSweep_5igmz_1`, `_chartSkeletonSweep_1thmk_1`.

Legends are **discrete banded pills** rather than continuous scales — e.g. ACOS: `<15% / 15–25% / 25–40% / 40–60% / 60–100% / >100% / N/A`, green→amber→red. Banding continuous metrics into named buckets with fixed colors is a genuinely good decision for operator dashboards; it makes tables and charts scannable at a glance.

Charts also carry **inline explanatory copy**: *"Each bubble represents a campaign. Size = sales volume. Color = ACOS efficiency. Click to highlight in table below."* Every non-obvious visualization gets a subtitle. Cheap, and it does a lot of work.

An `ⓘ` info tooltip button (`_infoTooltipBtn_2vd43_207`, 18×18, `border-radius:50%`) appears next to most metric labels.

### 4.12 Loading and empty states

**Skeletons, not spinners**, for content: dedicated skeleton components per surface (`_metricSkeleton_`, `_toolbarSkeleton_5igmz_5`, `_historySkeletonScroll_5igmz_21`, `_historySkeletonGrid_5igmz_30`, `_footerSkeleton_5igmz_109`, `_chartSkeletonSweep_1thmk_1`, plus a whole `TrackerLoadingSkeletons` bundle). Skeletons mirror the real layout including toolbar and footer — the page doesn't reflow when data lands.

Shimmer via `_backgroundShimmer_5igmz_1` / `_chartSweep_5igmz_1`.

Spinners (`--animation-spin: spin 1s linear infinite`) are reserved for button-level and inline loading.

Empty states: `._noData_`, `._empty_` classes across modules. Two captured routes rendered empty (`/price-tracker`, `/notifications/config`).

### 4.13 AI assistant surface

A persistent floating **circular avatar** (~100px, `border-radius:50%`, photographic) sits bottom-right with a status dot. Named agents: **Ava**, **Steven**, **Dr PPC™**. An agent filter (`All agents / Dr PPC / Steven / Ava`) appears on some pages, and buttons carry a `SUGGESTED` badge to nudge the contextually-relevant agent.

Supporting CSS: `_bubbleIn_12u2z_1` (chat bubble entry), `--bubble-accent:#818cf8`, `_dockPulse_1r7ut_1`, `_drPpcDotPulse_1e9xz_1`, `_drPpcInputSpin_az495_1`, `_presenceTileGold_1bb81_760` with `--tile-accent:251,191,36`, and `_capabilitySpin_zof0c_1`. Opening the assistant sets `--chat-drawer-width`, squeezing the app shell (§4.2).

There's also a dedicated full console at `/agents/dr-ppc-grok` and `/ppc-agent/{brand}/experimental-chat/capabilities` in the API — the assistant is a first-class product area, not a bolted-on widget.


---

## 5. Design Tokens

Read directly from Orbit's `:root`. **114 custom properties.** This is the complete, verbatim system — copy-paste ready.

### 5.1 Color

```css
/* Brand — gold */
--color-primary:          #fbbf24;
--color-primary-dark:     #f59e0b;
--color-primary-light:    #fde047;
--color-primary-gradient: linear-gradient(135deg, #fde047 0%, #f59e0b 100%);
--color-primary-alpha:    rgba(251,191,36,.18);
--color-primary-alpha-20: rgba(251,191,36,.2);
--color-gold-muted:       #d97706;
--color-gold-bright:      #fef3c7;
--color-managed-gold:     #c9a227;

/* Semantic */
--color-success:        #10b981;   --color-success-dark:  #059669;
--color-success-light:  #34d399;   --color-success-alpha: rgba(16,185,129,.18);
--color-error:          #ef4444;   --color-error-dark:    #dc2626;
--color-error-light:    #f87171;   --color-error-alpha:   rgba(239,68,68,.18);
--color-warning:        #f59e0b;

/* Text */
--color-text-primary:   #f3f4f6;   /* gray-100 */
--color-text-secondary: #d1d5db;   /* gray-300 */
--color-text-tertiary:  #9ca3af;   /* gray-400 */
--color-text-light:     #ffffff;

/* Surfaces */
--color-bg-primary:     #1a1d29;   /* deepest — page background */
--color-bg-secondary:   #252937;   /* sidebar, cards */
--color-bg-tertiary:    #2d3242;   /* raised surfaces, stat cards */
--color-bg-gradient:    linear-gradient(135deg, #1a1d29 0%, #2d3242 100%);

/* Borders */
--color-border-primary:   #374151;  /* gray-700 */
--color-border-secondary: #4b5563;  /* gray-600 */
--color-border-light:     #374151;  /* alias — same as primary */
--color-border-lighter:   #4b5563;  /* alias — same as secondary */
```

The greys are **Tailwind's gray scale** verbatim; semantic colors are Tailwind's emerald/red/amber. The custom part is the three-step surface ramp (`#1a1d29` → `#252937` → `#2d3242`) — a blue-leaning near-black, not Tailwind's slate.

`--color-border-light`/`--color-border-lighter` are pure aliases of primary/secondary. Four names, two values.

**Actual usage frequency** (measured across all 45 routes — this is where the real hierarchy shows):

| Color | Uses | Role |
|---|---|---|
| `#f3f4f6` | 26,904 | default text |
| `#9ca3af` | 11,113 | secondary/muted |
| `#d1d5db` | 6,838 | tertiary |
| `#fbbf24` | 1,583 | brand accent |
| `#ffffff` | 948 | emphasis |
| `#22c55e` | 555 | positive |
| `#10b981` | 422 | positive (second green) |
| `#ef4444` | 357 | negative |

Note **two greens in production** — `#22c55e` (green-500, 555 uses) alongside the tokenised `#10b981` (emerald-500, 422 uses). Only emerald is in `:root`. Pick one.

Backgrounds by frequency: `#2d3242` (836), `#252937` (627), `#1a1d29` (255) — inverse of the ramp's depth, as you'd expect: most surfaces are raised cards.

### 5.2 Typography

```css
--font-family-base: Inter, system-ui, Avenir, Helvetica, Arial, sans-serif;
--font-family-mono: "Courier New", Courier, monospace;

/* Display faces (marketing/brand surfaces) */
--font-family-bradley-display: "Bradley DJR Display", serif;
--font-family-bradley-regular: "Bradley DJR Regular", serif;
--font-family-bradley-small:   "Bradley DJR Small", serif;
--font-family-bradley-micro:   "Bradley DJR Micro", serif;
--font-family-jersey:          "Jersey 10", sans-serif;
```

```css
--font-size-xs:      10px;   --font-size-sm:      12px;
--font-size-sm-plus: 13px;   --font-size-base:    14px;
--font-size-md:      16px;   --font-size-lg:      18px;
--font-size-xl:      20px;   --font-size-2xl:     24px;
--font-size-3xl:     28px;   --font-size-4xl:     32px;
--font-size-heading: 3.2em;

--font-weight-normal:400;  --font-weight-medium:500;  --font-weight-semibold:600;
--font-weight-bold:  700;  --font-weight-extrabold:800;

--line-height-base:1.5;  --line-height-tight:1.1;  --line-height-relaxed:1.6;
```

**Measured usage** — the real scale in practice:

| Size | Uses | | Weight | Uses |
|---|---|---|---|---|
| 16px | 11,721 | | 400 | 33,446 |
| 14px | 10,271 | | 500 | 12,136 |
| 13px | 8,723 | | 600 | 3,758 |
| 12px | 7,371 | | 700 | 803 |
| 10px | 6,122 | | 850 | 575 |
| 11px | 2,681 | | 800 | 278 |
| 9px | 797 | | 750 | 268 |
| 18px | 642 | | 650 | 100 |

Base is 16px but the **working range is 10–14px** — this is a dense analytics tool and the type reflects it. `11px` and `9px` are heavily used but have no token (`--font-size-xs` is 10px). Variable-font weights (`650/750/850`) appear in ~950 places with no tokens at all — Inter variable being used off-system.

Line heights compute to `24px / 21px / 19.5px / 18px / 15px` (i.e. `1.5×` of 16/14/13/12/10).

`letter-spacing` is chaotic: `0.5px`, `0.6px`, `0.54px`, `0.2px`, `0.72px`, `0.3px`, `0.55px`, `0.4px`, `0.06px`, `0.33px`, `-0.5px`, `0.22px`, `0.44px`, `0.8px` — 14+ values, no tokens. Uppercase labels (1,462 uses) drive most of it.

### 5.3 Spacing

```css
--spacing-xs:  2px;    --spacing-sm:  4px;    --spacing-md:  8px;
--spacing-lg: 12px;    --spacing-xl: 16px;    --spacing-2xl:20px;
--spacing-3xl:24px;    --spacing-4xl:32px;    --spacing-5xl:48px;
--spacing-6xl:60px;    --spacing-7xl:80px;

--grid-gap-base: 20px;
```

A 4px base grid with a 2px half-step. Note `60px` breaks the doubling pattern (48 → 60 → 80).

### 5.4 Radius

```css
--radius-sm:   3px;   --radius-base: 4px;   --radius-md:  6px;
--radius-lg:   8px;   --radius-xl:  12px;   --radius-2xl:20px;
--radius-full: 50%;
```

Measured: `4px` (1,620), `3px` (1,088), `50%` (655), `6px` (538), `8px` (406), `10px` (342), `999px` (250), `9999px` (90), `12px` (81).

`10px` is the 6th most common radius and **has no token** — it's the sidebar quick-actions block and table wrapper. `999px`/`9999px` pills also aren't tokenised (`--radius-full` is `50%`, which is for circles, not pills). Two gaps worth filling in your own system.

### 5.5 Shadow

```css
--shadow-xs:  0 1px 2px  rgba(0,0,0,.25);
--shadow-sm:  0 2px 4px  rgba(0,0,0,.3);
--shadow-md:  0 2px 8px  rgba(0,0,0,.4);
--shadow-lg:  0 4px 16px rgba(0,0,0,.5);
--shadow-xl:  0 4px 6px  rgba(251,191,36,.3);   /* gold glow, not elevation */
--shadow-2xl: 0 25px 50px rgba(0,0,0,.6);
--shadow-focus: 0 0 0 3px rgba(251,191,36,.3);  /* gold focus ring */
```

`--shadow-xl` is a **gold glow**, not a bigger drop shadow — it sits out of sequence in an otherwise linear elevation scale. It's the primary-button glow. Name it something else in your system.

Most-used measured shadow is `0 6px 18px rgba(0,0,0,.4)` (142 uses) — **not in the token set**. Also common: `0 14px 36px rgba(0,0,0,.4), 0 2px 8px rgba(0,0,0,.2)` (40) and `0 18px 50px rgba(0,0,0,.18)` (35). Selection/focus rings appear as `0 0 0 1.5px` in teal `#40c5bf`, purple `#a782f5` and gold `#f8c049` — a per-feature accent set that isn't in `:root` either.

### 5.6 Motion

```css
--transition-fast: .2s ease;
--transition-base: .3s ease;
--transition-slow: .5s ease;
--animation-spin:    spin 1s linear infinite;
--animation-fade-in: fadeIn .5s ease;
```

**Measured durations:** `0.15s` (3,394), `0.2s` (2,026), `0.3s` (1,460), `0.1s` (168), `0.12s`, `0.16s`, `0.24s`, `0.26s`.

`0.15s` is the single most-used duration and **has no token**. Easing is overwhelmingly plain `ease` (50,343). Notable custom curves:

- `cubic-bezier(.34, 1.56, .64, 1)` — overshoot/spring, used on drawer and card entrances
- `cubic-bezier(.4, 0, .2, 1)` — Material standard easing

Both used sparingly and untokenised.

The app defines **80+ named keyframes**. Beyond the standard `fadeIn`/`slideIn`/`spin`: `_borderRotate_`, `_buttonGradientShift_`, `_cardFloat_`, `_float1/2/3_`, `_badgePulse_`, `_dockPulse_`, `_cinematicRouteFlow_rfi82_349`, `_autopilotStepSwirl_kexn7_1`. Significant ambient/decorative motion, concentrated in the AI-agent and onboarding surfaces.

`@media (prefers-reduced-motion: reduce)` **is** handled — one of the few accessibility affordances present.

### 5.7 Layout, z-index, opacity, breakpoints

```css
--z-base:1;  --z-dropdown:50;  --z-modal:100;  --z-notification:1000;
--opacity-disabled:.6;  --opacity-muted:.7;  --opacity-subtle:.8;
--max-width-content:1200px;  --min-width-mobile:320px;  --breakpoint-mobile:768px;
```

z-index tokens are **not honoured** — modals hardcode `1000`, drawers use `200`/`201`.

**Breakpoints actually in the CSS** (25 distinct media queries):

`480, 500, 560, 600, 640, 700, 720, 760, 767, 768, 900, 960, 980, 1000, 1024, 1050, 1100, 1180, 1200, 1250, 1280, 1400` (max-width) + `1380` (min-width) + both `prefers-reduced-motion` states.

Only `768px` is tokenised. Everything else is per-component ad hoc. There is no breakpoint system here — just 22 hand-picked values. Don't copy this; define 4–5 and hold the line.

**Dark mode:** the app is dark-only. No `[data-theme]`, no `.light` class, no `prefers-color-scheme` query anywhere in 1.2MB of CSS, no toggle in the captured DOM. The light-theme fragments in the form error styles (`#fee`/`#fcc`/`#c00`) are legacy, not a second theme. **Orbit ships one theme.**


---

## 3. Page flows

**Coverage warning:** the crawl was read-only. Nothing was submitted, created, or deleted. The flows below are reconstructed from route structure, rendered controls and API traffic — they are *inferred*, and the write-path details (validation rules, confirmation steps, error handling) are genuinely unknown. Each flow notes what would need an interactive pass to confirm.

### 3.1 Onboarding / first login

Public routes: `/login`, `/signup`, `/forgot-password`, plus `/eula` and `/privacy`. The auth module (`_1xvm8_`, 52 rules) contains classes `logo, link, step, form, input, brand` — **`step` implies a multi-step signup wizard**, not a single form. A separate module (`_1suhg_`, 62 rules) carries `step, hero, input, select, stepDot, content` — a stepper with dot indicators, plus `_blink_1suhg_1` for a caret animation.

`_createBrandSlideUp_1tppd_1` and `_createSpin_1tppd_601` indicate a **create-brand modal** that slides up, with a loading spinner during creation. So first-run is plausibly: signup → create brand → connect Amazon (`/api-connections`) → land on dashboard.

`/api-connections` is the SP-API/Ads-API integration screen — almost certainly a required onboarding step, since every data surface depends on it.

*Not verified:* actual step count, field validation, whether Amazon OAuth is inline or redirected.

### 3.2 Analytics review (the app's primary loop)

This is the flow the product is actually built around, and it's consistent across ~30 routes:

1. **Scope** — brand switcher (sidebar top) → marketplace switcher → both encoded in the URL
2. **Filter** — date-range presets (`7d / 30d / 90d / YTD` + named months) or explicit range picker; product filter (`All Products (42)`); metric selector (`33/33 Metrics`); granularity toggle (`Day / Week / Month`)
3. **Read** — stat card row → chart → dense table
4. **Drill** — click a table row → right-side drawer (§4.5) with detail for that ASIN/campaign/keyword
5. **Export** — `Export` button, present on the dashboard

Filter state appears to be **component-local, not URL-encoded** — the crawler navigated to bare URLs and got default ranges every time. So filter selections are probably not shareable or back-button-restorable. That's a real weakness and an easy place to beat them.

### 3.3 PPC management

Four sub-routes under Advertising:

- `/ppc` — **PPC Analytics**: profitability analysis joining organic and paid. Columns span `PROFIT / TRAFFIC / PAID / REVENUE` groups: `ASIN, Profit, Sessions, Page Views, CVR, Buy Box, Impr, Clicks, Spend, Orders, Sales, ACOS, ROAS, Total Orders, Total Rev, Organic Orders, Organic Rev`. Search by ASIN/title; per-row checkboxes (bulk selection).
- `/ppc/search-terms` — search-term report
- `/ppc/campaigns` — **Campaign Analytics**: "Campaign & Match Type Breakdown" + "Campaign Profitability Map" (bubble chart, click-to-highlight-in-table)
- `/ppc/live` — **Live Tracker**, real-time campaign monitoring
- `/agents/dr-ppc-grok` — **Dr PPC™ Console**, LLM agent for PPC

Critically: **this is read/analyse only.** No bid-change controls, no campaign creation, no budget editing, no negative-keyword actions were rendered. `--ppc-campaign-columns` and the API (`/api/ppc-analytics/*`, `/api/ams-engine/*`) are all GET. Orbit reports on PPC; it does not appear to manage it — the "management" is delegated to the AI console.

*Not verified:* whether Dr PPC can execute changes or only advise.

### 3.4 Inventory

Seven routes, and the section is visibly mid-refactor (two developer-named parallel builds, §1.3):

`/inventory` (index), `/inventory/overview` ("Ken"), `/inventory/inventory-overview` ("Ameer"), `/inventory/sales-forecast`, `/inventory/forecasting`, `/inventory/actions`, `/inventory/shipments`, `/inventory/comms`.

API surface is the richest in the app — `health`, `planning`, `planning-settings`, `valuation`, `storage-fees`, `sales-velocity`, `awd-summary` (Amazon Warehousing & Distribution), `products`, `overview`, `inventory-actions`, plus `/api/supply-chain/{mp}/shipments` and `/dashboard`.

`/inventory/comms` + `/api/inventory-agent/{brand}/comms/scan-policy` suggests **automated supplier/3PL communication driven by an agent** with a configurable scan policy. That's an unusual feature.

### 3.5 Finance

`/finance` (P&L), `/reimbursements`, `/manual-expenses`, `/cogs` (Settings — COGS entry).

APIs: `/api/profit/{brand}/pl`, `/pl-by-asin`, `/api/finance-api/{brand}/orders-pl-v2/{mp}`, `/api/cogs-api/{mp}/settings`, `/api/cogs-api/{brand}/inventory`, `/api/fx/rates`.

`/api/fx/rates` is called on **every page load** (45/45 routes) — multi-currency is baked in globally, and Brand Overview exposes a `USD / EUR` toggle.

`orders-pl-v2` implies a v1 still exists somewhere.

### 3.6 Trackers and alerts

Five tracker routes (`/trackers` index, `bsr-`, `buybox-`, `price-`, `fee-tracker`) plus `/alerts`. Two alert APIs run on nearly every page:

- `/api/v2/trackers/{brand}/alerts` — 55 calls
- `/api/brand-alerts/{brand}/alerts` — 45 calls

Notification config at `/brand/{brand}/notifications/config`; the sidebar badge showed **503 unread**.

A `TrackerHistoryTabs` CSS bundle and dedicated `TrackerLoadingSkeletons` bundle exist — trackers are a substantial, well-developed area.

### 3.7 Settings / account / users

- `/cogs` — labelled "Settings" in nav; COGS configuration
- `/api-connections` — Amazon SP-API / Ads API connections (brand-level)
- `/subscription` — billing (brand-level)
- `/notifications/config` — notification preferences (rendered empty at capture)
- `/agency`, `/api/agency/clients`, `/api/agency/tag-values` — multi-brand agency console with client tagging

**No user-management screen was found.** No `/users`, `/team`, `/members`, `/roles`, or `/invite` route, and no such nav item. `/api/authed-sellers` (44 calls) manages *Amazon seller account* connections, not app users. The sidebar CSS has `_addSellerButton_and57_601`.

So: either user management doesn't exist yet, lives behind the agency console, or sits on a route with no inbound link. Given Part 3 of your brief asks specifically about roles/permissions/invites — **this is the biggest thing Orbit appears not to have.** Worth confirming manually before you conclude that.

---

## 6. Interactions and effects

| Behaviour | Finding |
|---|---|
| **Button hover** | Primary: gradient darkens + `translateY(-1px)` + gold glow expands to `0 6px 20px`. Secondary: border and text → gold, faint gold wash. Ghost: text brightens, grey background appears. All `.2s ease`. |
| **Button press** | `translateY(0)` on `:active` for primary — a press-down against the hover lift. **No ripple effect anywhere.** |
| **Focus** | Consistent 3px gold ring (`--shadow-focus`) via `:focus-visible` on buttons, inputs and tabs. Genuinely well done. |
| **Nav hover** | Background → `--color-bg-tertiary`, text → primary, `.3s ease`. Active adds a 3px gold left rail. |
| **Table row hover** | `background:#ffffff08`, `.12s ease` — the fastest transition in the app, appropriate for high-frequency scanning. Rows are `cursor:pointer`. |
| **Sort** | `th:hover` and `._thSorted` both brighten to primary text. `user-select:none` on headers. |
| **Drawer open** | Backdrop `fadeIn .15s`; panel `slideLeft .2s ease` from right. Width `min(560px, 100vw-12px)`. |
| **Modal open** | Overlay `fadeIn .2s`; content `slideIn .3s`. |
| **AI drawer** | Sets `--chat-drawer-width`; app shell squeezes via `padding-right` transition `.15s ease`. Not an overlay. |
| **Page transitions** | None found. React Router swaps content instantly; perceived transition is the skeleton→content swap. |
| **Loading** | Skeletons with shimmer sweep for content; spinners only for buttons/inline. Skeletons mirror final layout including toolbar and footer. |
| **Tooltips** | `ⓘ` buttons (18×18, circular) next to metric labels. Custom `._tooltip_` classes, not native `title`. Delay/placement not measurable without interaction. |
| **Charts** | Banded discrete legends; inline explanatory subtitles; "click to highlight in table below" cross-filtering between chart and table. |
| **Reduced motion** | `@media (prefers-reduced-motion: reduce)` honoured. |
| **Ambient motion** | 80+ keyframes; `_cardFloat_`, `_float1/2/3_`, `_borderRotate_`, `_buttonGradientShift_`, `_badgePulse_`, `_dockPulse_` — decorative motion concentrated on AI/onboarding surfaces. |
| **Pagination vs infinite scroll** | Neither, mostly. Tables render full datasets with horizontal scroll (measured 2240px × 1098px). A `_loadMoreBtn_1npn8_250` (157×33) and `Load 12 earlier months` button indicate **explicit load-more**, not infinite scroll. |
| **Drag and drop** | No evidence in CSS or DOM. |
| **Right-click menus** | No custom `contextmenu` handling found. |
| **Keyboard shortcuts** | **None found.** No shortcut hints, no `kbd` elements, no visible key handlers. For a dense operator tool this is a notable omission — and an easy differentiator. |
| **Auto-save vs manual** | Not determinable read-only. |
| **Undo/redo** | No evidence. |

---

## 7. Data and API patterns

**559 XHR calls** observed across 45 routes. All same-origin (`fullcircleorbit.com/api/*`). **Zero WebSocket connections** — including on `/ppc/live` ("Live Tracker") and the hourly-sales page. "Live" means polling or on-load fetch, not push.

### 7.1 Service decomposition

The API is split into ~20 named services, which maps closely onto the nav:

| Service | Purpose |
|---|---|
| `/api/auth/me` | session (45 calls — every page) |
| `/api/authed-sellers` | connected Amazon seller accounts (44) |
| `/api/fx/rates` | currency conversion (45 — every page) |
| `/api/hybrid/{brand}/*` | `data-availability`, `asin-catalog`, `month-summary`, `asin-unit-economics`, `cogs-lookup` |
| `/api/sales/*` | `hourly/latest`, `daily/range` |
| `/api/sales-overview/{brand}/*` | dashboard aggregate |
| `/api/ppc-analytics/{brand}/*` | `data-availability`, `daily-trends`, `hourly-acos`, `unified-asins`, `available-profiles` |
| `/api/ams-engine/{brand}/*` | `efficiency-trend` |
| `/api/ppc-agent/{brand}/experimental-chat/capabilities` | AI console (35) |
| `/api/sp-api/{brand}/*` | `catalog-items`, `keyword-rankings`, `keyword-subscriptions`, `sqp-weekly-aggregates`, `sqp-breakdown-data` |
| `/api/seller-central-impressions/{brand}/*` | `summary`, `daily-trends`, `top-asins`, `data-availability` |
| `/api/inventory/{mp}/*` | `overview`, `health`, `planning`, `planning-settings`, `products`, `valuation`, `storage-fees`, `sales-velocity`, `awd-summary`, `inventory-actions` |
| `/api/inventory-agent/{brand}/comms/scan-policy` | agent-driven supplier comms |
| `/api/supply-chain/{mp}/*` | `shipments`, `dashboard` |
| `/api/profit/{brand}/*` | `pl`, `pl-by-asin` |
| `/api/finance-api/{brand}/orders-pl-v2/{mp}` | order-level P&L |
| `/api/cogs-api/{mp}/*` | `settings`, `settings/all`, `inventory` |
| `/api/trackers` + `/api/v2/trackers/{brand}/alerts` | trackers (v2 — v1 still mounted) |
| `/api/brand-alerts/{brand}/alerts` | brand alerts |
| `/api/agency/*` | `clients`, `clients/sales-overview`, `tag-values` |
| `/api/whatsapp/{brand}/{mp}/subscription` | WhatsApp integration |

### 7.2 Patterns worth stealing

**`data-availability` endpoints.** Three services expose one (`hybrid`, `ppc-analytics`, `seller-central-impressions`). The client asks *what date ranges actually have data* before requesting data. That's how you avoid rendering empty charts for periods Amazon hasn't delivered yet, and it's the single best idea in Orbit's API design.

**Path-scoped multi-tenancy.** Brand slug or marketplace ID in the path on essentially every call. Trivially cacheable, trivially auditable.

**Global calls on every route.** `auth/me`, `fx/rates`, `authed-sellers`, `hybrid/data-availability`, and both alert endpoints fire on all 45 routes — an app-shell provider layer. Note this is unbatched: ~6 requests before any page-specific data. There's an easy performance win against them here.

**Versioning is inconsistent.** `/api/v2/trackers/` (path-versioned) vs `orders-pl-v2` (name-versioned) vs everything else unversioned.

### 7.3 Refresh behaviour

- No WebSockets, no SSE observed.
- Dashboard states **"Sales data updated hourly"** — server-side batch, not live.
- Manual refresh controls exist (`Refresh` button on Brand Overview, `_refreshBtn_1npn8_211`).
- Hourly sales has its own `latest` endpoint, suggesting polling on that page specifically.

### 7.4 Import / export / bulk

- **Export:** an `Export` button on the Sales Dashboard. Format not determinable read-only; no export endpoint fired during the crawl (it's likely client-side CSV or a POST on click).
- **Import:** no file-upload input rendered on any of the 45 routes. COGS is presumably entered through the UI at `/cogs`; whether bulk upload exists is unconfirmed.
- **Bulk operations:** per-row checkboxes on the PPC Analytics table (8+ captured) imply multi-select, but **no bulk-action toolbar was rendered** — because nothing was selected. Whether a toolbar appears on selection is unverified.

### 7.5 Integrations

Amazon **SP-API** (catalog, SQP, keyword rankings), Amazon **Ads API** (via `ams-engine` / `ppc-analytics`, with `ad-profiles` and `available-profiles`), **Seller Central impressions**, **AWD**, **WhatsApp** (Ava agent), and an LLM backend for Dr PPC (route name `dr-ppc-grok` suggests xAI Grok).

---

## 8. Feature checklist for gap analysis

I don't have visibility into AltaScraper, so I can't produce a real gap table — that needs your app's feature inventory. What follows is Orbit's complete surface as a checklist: mark each ✅/❌ for your side and the gaps fall out.

**Scope & navigation**
- [ ] Multi-brand switching
- [ ] Multi-marketplace switching (marketplace ID in URL)
- [ ] Agency console — multiple clients, cross-client sales overview, client tagging
- [ ] Collapsible sidebar with grouped sections + quick actions
- [ ] Unread notification badge in nav

**Sales & analytics**
- [ ] Sales dashboard — live sales (today vs yesterday), week-to-date vs last week with % delta
- [ ] Hourly sales granularity
- [ ] Metrics × dates heatmap table (33 selectable metrics)
- [ ] Day / Week / Month granularity toggle
- [ ] Date presets (7d/30d/90d/YTD + named months) and custom range
- [ ] Product filter across all analytics
- [ ] Multi-currency (USD/EUR) with live FX
- [ ] Brand Overview roll-up across marketplaces

**Advertising**
- [ ] PPC analytics joining organic + paid per ASIN (profit, sessions, CVR, buy box, ACOS, ROAS, organic vs total split)
- [ ] Search-term report
- [ ] Campaign analytics + match-type breakdown
- [ ] Campaign profitability bubble map with chart↔table cross-filtering
- [ ] Live PPC tracker
- [ ] Hourly ACOS
- [ ] Ad-profile selection

**Keywords / SQP**
- [ ] ASIN-level SQP
- [ ] Keyword ranking tracking
- [ ] SQP setup / keyword subscriptions
- [ ] Weekly SQP aggregates + breakdown

**Inventory & supply chain**
- [ ] Inventory overview, health, valuation, storage fees
- [ ] Sales velocity, sales forecast, forecasting
- [ ] Restock planning + planning settings
- [ ] Recommended inventory actions
- [ ] Shipments / supply-chain dashboard
- [ ] AWD summary
- [ ] Agent-driven supplier comms with scan policy

**Finance**
- [ ] P&L (account-level and by ASIN)
- [ ] Order-level P&L
- [ ] COGS settings
- [ ] Reimbursements
- [ ] Manual expenses

**Trackers & alerts**
- [ ] BSR tracker
- [ ] BuyBox tracker
- [ ] Price tracker
- [ ] Fee tracker
- [ ] Combined tracker index with history tabs
- [ ] Brand alerts + tracker alerts
- [ ] Notification centre + per-notification config

**AI / automation**
- [ ] Named agents (Ava, Steven, Dr PPC™) with contextual "suggested" nudges
- [ ] Dedicated agent console page
- [ ] In-app chat drawer that squeezes the layout
- [ ] WhatsApp integration + subscription
- [ ] Agent-driven inventory comms

**Platform**
- [ ] Amazon SP-API + Ads API connection management
- [ ] Multiple seller accounts per brand
- [ ] Subscription/billing page
- [ ] Feedback/tickets + public changelog
- [ ] Compliance scanner
- [ ] Category explorer, Scout, Leading Indicators (internal beta)
- [ ] `data-availability` endpoints so UI never requests missing date ranges

### Where Orbit is weak — your openings

Not everything above is worth copying. These are the places a competitor can straightforwardly beat them:

1. **No user management.** No team, roles, invites, or permissions UI found anywhere. For an agency product this is a glaring hole.
2. **No keyboard shortcuts.** Zero. In a dense operator tool used daily, a command palette alone would be a visible advantage.
3. **Filter state isn't in the URL.** Views aren't shareable or bookmarkable, and the back button doesn't restore filters.
4. **"Live" isn't live.** No WebSockets; hourly batch data behind a "Live Tracker" label.
5. **PPC is read-only.** They report on campaigns but don't appear to let you act on them — no bid, budget, or negative-keyword controls.
6. **No visible bulk actions.** Checkboxes exist with no rendered bulk toolbar.
7. **No import.** No file upload found on any route.
8. **Dark mode only.** No light theme.
9. **Internal builds shipped to production.** Two competing inventory pages named after developers, in the live nav.
10. **Design system drift.** 112 button signatures, 22 ad-hoc breakpoints, untokenised `0.15s`/`10px`/`11px`/`999px`, two greens, dead token references in the modal, and light-theme error styling on a dark app. Their tokens are good; their adherence isn't.

---

## 9. What's still missing, and how to get it

This audit is complete for structure, tokens and components. Three gaps remain, all needing a second interactive pass:

1. **Below-the-fold content** — screenshots captured one viewport each because of the app-shell scroll container. Fix: scroll-and-stitch capture on the inner scroll element.
2. **Modals, drawers, dropdowns, hover states** — specs are documented from CSS, but no captured instance. Fix: a script that clicks each table row, each `ⓘ`, each dropdown trigger, and screenshots the result.
3. **Write flows** — create/edit/delete/submit, validation, bulk-action toolbars, export format. Requires deliberately triggering actions; needs your call on whether to do that in a live account.

Say the word and I'll write the second-pass script. It's a variation on the one you already have — same CDP attach, but driven by an explicit interaction list rather than link-following.

---

*Audit generated from a 45-route authenticated capture, 13 Aug 2026. Design tokens and component CSS are verbatim from shipped stylesheets. Flows, permissions and write behaviour are inferred and flagged as such.*
