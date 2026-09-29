# The pages the owner likes — how they are built (design research, parked)

Status: **research only, parked 28 Sep 2026.** The owner said the redesign should
build on his current app, naming these pages (docs/decisions.md, 28 Sep): Sales,
Traffic, Hourly sales, All listings (keep all 3 views), Repricer, Campaign
analytics, Search terms — and that the PDP stays as it is. The design work was
then put on hold ("Skip the design decision and design-system/UI migration
milestones for now. Preserve all existing design research for later").

Also parked: `prototypes/design-review/` (three earlier directions A/B/C, fake
data, open `index.html`) and `docs/proposals/design-exploration.md`.

---

## Shared foundation

- CSS order (templates/dashboard.html:42-115): tabler-icons, dashboard.css,
  dialog.css, datatable.css, genui.css, repricer.css, … listrow_detailed.css,
  listrow_edit.css, … ppc.css, drppc.css, mobile.css.
- Tokens (dashboard.css:32-165): surfaces `--bg #1a1d23 --panel #1e2128
  --panel2 #252930 --panel3 #2c3038`, lines `#2a2e36/#363b45`; ink tiers;
  accent teal `#2dd4a8`; money gold `#f0b429`; AI violet `#c8b6ff`; status
  ok/warn/red with -bg/-line; radius 6/10/14; money bars cost/fee/profit.
- **Sales, Traffic and Hourly use literal "Orbit" colours**, not tokens
  (dashboard.css:3091-3106): page `rgb(26,29,41)`, panel `rgb(37,41,55)` +
  `rgb(55,65,81)` border r12, stat card `rgb(45,50,66)` r8, active gold `#fbbf24`.
- **PPC screens have their own palette** (ppc.css:21-61, GitHub-dark).
- Two stat-card designs: `.stat-card` (Sales/Traffic: label, number, comparison
  line) and `.ui-stat` / `.rp-mc` (Listings/Repricer: number, label, 2px share
  bar; clickable as a filter).
- Account/marketplace appear only in the top-bar chip and the sidebar, never in
  page headers.
- Two header styles: `.pagehead > .pagetitle` (Sales, Repricer) and
  `.wstoolbar.bleed` + h2 (Traffic, Hourly, Listings).

## Sales (sales.js, salescharts.js; dashboard.html:852-1035)
Top row: Live Sales + Week to Date panels (today strip, hourly/weekly line vs
dashed previous). Sales Report: gold segmented presets (7d…YTD, Custom), last 3
months, Day/Week/Month, product select, Compare to (Prior Year / Previous
Period), range text, Sync, Export. Five `.stat-card`s. `salesCombo` SVG: order
bars (right axis) + Sales/Profit/prior lines, gold crosshair hover card,
drag-to-zoom with a "Zoomed to … / Back to the full range" banner, toggleable
legend. Lower: Organic vs PPC, P&L, campaigns, P&L heatmap grid (sticky
header/first column, green/red tint vs previous column).

## Traffic (traffic.js)
`.gtools` period pills 7-90d + group By ASIN / By parent; 8 stat cards; combo
charts (overview, performance, channel donut, top-ASIN trends), ASIN bars,
sortable top-ASIN table. Reload dims the old page instead of blanking it.

## Hourly (hourly.js)
Window 30/60/90d, Units/Revenue; a per-ASIN 24-hour heat strip (gold, scaled to
each row's own peak) with totals; a row expands to a Mon-Sun × 24h grid with
"Best hour".

## All listings — three views (listings.js, listrow_detailed.js, miles_template.js)
Header: source switch Drafts / Live / All / Removed, Sync, Costs; view toggle
`#viewtoggle` (table / detailed / grid, saved in localStorage). Selection bar
with bulk actions; `uiStats` tiles that filter.
- Table: `table.lt` — thumb, ASIN+SKU, title+brand, price, COGS (click to
  edit), handling, status badge, compliance, actions.
- Detailed ("Manage All Inventory"): `table.inv-table` with status + Amazon's
  words, product details and risks, 30-day performance, inventory, editable
  pricing with profit, fees; variation families; staged edits + save bar.
- Grid: 300px tiles, square image with status dot / checkbox / corner flags,
  title, price, facts, profit chip, ASIN, action icons.

## Repricer (sourcing.js, repricer.css)
Toolbar chips (Auto-pricing ON/OFF, Check now, Enroll, More menu); one-line
alert bar; four filter stat cards; sticky bulk bar; `table.rp-tbl` rows with
thumb, tags, was→now price, profit, ROI, sparkline (click → chart), status dot;
row expands to price-composition bar, metric tiles, actions, supplier table and
rule chips.

## Search terms / PPC analytics / Campaign analytics (ppcterms.js, ppcanalytics.js, ppccampaigns.js)
Shared window (PPCWIN), 2×4 KPI cards with change pills coloured by "better";
filter pills, brand words, spend/ACOS filters, summary grid, sortable table with
expandable rows (≤400). PPC Analytics: latest-day strip, 7-day trail, KPIs with
sparklines, branded donut, profitability cards, combo charts, ACoS heatmap,
TACoS, pacing, ASIN table. Campaign Analytics (ppccampaigns.js — the sidebar's
"Campaign Analytics"): breakdown donut + stacked area, profitability scatter,
cohorts, filterable campaign table expanding to stats and search terms.

## Small defects found while mapping (fixed or listed in known-issues)
1. Traffic sort arrows garbled (`" â–´"`) — traffic.js.
2. Sales combo-chart key swatch colour differs from the bar colour.
3. Traffic donut legend dots don't match the ring colours.
4. Repricer classes with no CSS rule: `.rp-was`, `.rp-pen`, `.rp-held`, `.rp-m2y`.
5. PPC Analytics help mentions reference lines the chart never draws.
