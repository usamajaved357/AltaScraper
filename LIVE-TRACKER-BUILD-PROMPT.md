# Live Tracker Page — Build Specification

## What This Is

A real-time PPC monitoring page in AltaScraper's Advertising/PPC section called **"Live Tracker"**. Fourth item in sidebar after Campaign Analytics. Shows hourly ad performance data with multiple time views, cumulative mode, and per-ASIN drill-down charts with 6 metric views and placement breakdowns.

The attached `orbit-live-tracker-v2.jsx` is a **visual reference only** — implement using AltaScraper's existing template engine, chart library, CSS, and Flask patterns.

Route: `/w/<account_id>/ppc/live`

---

## Page Header

- **Brand name**: account name (e.g. "Promixx") — 28px bold
- **Subtitle**: "Advertising Dashboard - USA" + account ID in monospace dim gray: `(ATVPDKIKX0DER)` — 13px muted

### Time Controls (right-aligned)

```
                                          All times in PDT
[✓ Last 24 Hours]  [Last 7 Days]  [Day by Day]    Cumulative [●━━]
```

- "All times in PDT" — 11px dim gray, above the buttons
- **3 time range buttons** inside a dark container (#1a1f26, border-radius 4px):
  - Active: **orange/gold** (#e8b923) filled background, dark text, checkmark "✓" before text
  - Inactive: transparent, muted text
  - Font: 13px, font-weight 600
- **Cumulative toggle**: round switch 40×22px
  - OFF: gray track (#3a3f47), white handle left
  - ON: orange/gold track (#e8b923), white handle right
  - "Cumulative" label: 13px, white, font-weight 600, to the LEFT of the toggle

---

## Section 1 — KPI Summary Cards

6 cards in a grid `repeat(6, 1fr)` with **12px gap** (NOT flat-joined — use gap like other PPC pages).

Each card has:
- Gold/amber top border: `border-top: 2px solid #e8b923`
- Background: subtle gradient `linear-gradient(180deg, #1c2128, #161b22)`
- Bottom corners rounded: `border-radius: 0 0 6px 6px`
- Subtle radial glow in top-right corner: `radial-gradient(circle, rgba(232,185,35,0.08), transparent 70%)`

| TOTAL AD SPEND | TOTAL SALES | TACOS | ACOS | TOTAL UNITS | TOTAL ORDERS |
|----------------|-------------|-------|------|-------------|--------------|

- Labels: 11px, muted, **bold 700**, uppercase, letter-spacing 0.8
- Values: 26px, bold 700

**Values change based on selected time range:**
- Last 24 Hours: $306.94 / $1,736.15 / 17.68% / 29.64% / 85 / 76
- Last 7 Days: $2,470.70 / $18,860.51 / 13.10% / 25.34% / 967 / 867
- Day by Day: same as Last 7 Days

No change percentages on this page — it's live data.

---

## Section 2 — Main Chart

### Subtitle
"All times displayed in PDT" — 13px, **white** text (not cyan), with left padding matching chart

### Chart Background
The chart area sits inside a dark container: `background: #0a0e14` (darker than the page), `border-radius: 6px`, padding 16px 8px

### Chart Elements
- **Gold/olive bars** = Impressions → mapped to RIGHT Y-axis
  - Fill: `rgba(160,128,50,0.65)` — semi-transparent dark gold
  - Top corners rounded (3px)
  - Bar width varies by mode: thin for 7-day hourly (~14px), medium for 24h hourly (~36px), wide for daily (~100px)

- **Blue line with gradient fill** = Total Sales → mapped to LEFT Y-axis
  - Stroke: #3b82f6, 2.5px width, no dots
  - Gradient fill below: from rgba(59,130,246,0.35) to transparent

- **Red line with gradient fill** = Ad Spend → mapped to LEFT Y-axis
  - Stroke: #e74c3c, 2.5px width, no dots
  - Gradient fill below: from rgba(231,76,60,0.3) to transparent

- **Orange dots** = TACOS → near the x-axis baseline
  - Small dots at each data point

- **Grid**: very subtle dashed lines (#252b33), dashed pattern "3 3"

### 6 Chart Modes — Exact Y-Axis Ranges

| Mode | Left Y-axis ($$) | Right Y-axis (counts) |
|------|-------------------|----------------------|
| **Last 24 Hours** (cumulative OFF) | $0, $9, $18, $27, $36 | 0, 1.5k, 3.0k, 4.5k, 6.0k |
| **Last 7 Days** (cumulative OFF) | $0, $200, $400, $600, $800 | 0, 5.5k, 11.0k, 16.5k, 22.0k |
| **Day by Day** (cumulative OFF) | $0, $850, $1.7k, $2.55k, $3.4k | 0, 20k, 40k, 60k, 80k |
| **Last 24 Hours** (cumulative ON) | $0, $80, $160, $240, $320 | 0, 15k, 30k, 45k, 60k |
| **Last 7 Days** (cumulative ON) | $0, $5k, $10k, $15k, $20k | 0, 150k, 300k, 450k, 600k |
| **Day by Day** (cumulative ON) | $0, $5k, $10k, $15k, $20k | 0, 150k, 300k, 450k, 600k |

### X-Axis Labels Per Mode

- **Last 24 Hours**: `Sep 4, 4 PM`, `Sep 4, 6 PM`, ... `Sep 5, 2 PM` — every other hour labeled
- **Last 7 Days**: `Aug 29, 3 PM`, `Aug 30, 6 AM`, `Aug 30, 9 PM`, ... `Sep 5, 12 PM` — every 5th data point
- **Day by Day**: `Aug 29`, `Aug 30`, `Aug 31`, `Sep 1`, `Sep 2`, `Sep 3`, `Sep 4`, `Sep 5` — every day

### Cumulative Mode Behavior

When Cumulative is ON:
- Each data point = running sum of all previous points
- Bars grow progressively taller (staircase pattern)
- Lines curve upward continuously
- The chart shows how total spend/sales/impressions accumulated over the period

### Legend (centered below chart)

```
■ Total Sales    ● Ad Spend    ■ Impressions    ● TACOS
```

- Colored squares/circles: Total Sales (#3b82f6 blue), Ad Spend (#e74c3c red), Impressions (#e8b923 gold), TACOS (#e67e22 orange)
- Font: 13px, white text

---

## Section 3 — ASIN-Level Breakdown

### Header Row

```
ASIN-level breakdown                      ☐ Group by parent ASIN    [● LIVE DATA]
```

- Title: **"ASIN-level breakdown"** — 20px bold
- **"Group by parent ASIN"** checkbox: when checked (gold/orange accent color), shows parent ASINs; when unchecked, shows child ASINs. The checkbox is 16×16px.
- **"● LIVE DATA"** badge:
  - Background: #1f8a4c (dark green)
  - Text: white, 11px, bold 700, letter-spacing 0.5
  - Pulsing green dot (6px, #4ade80) with CSS animation: `@keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:0.4 } }` — 2s infinite

### Per-ASIN Cards

Each ASIN gets its own card. Cards are stacked vertically, full width, ~28px gap between them.

#### Card Header

```
[product_image]  PROMIXX Pro Electric Shaker Bottle 20oz, USB-C Rec...     METRIC:  [Overview ▾]
                 B0DNFYB1PB · SPONSORED PRODUCTS
```

- **Product image**: 48×48px, rounded 4px corners, 1px border, dark background placeholder
- **Product title**: 14px, font-weight 600, white — truncated
- **ASIN**: 12px, **cyan** (#39d2c0), font-weight 600
- **"· SPONSORED PRODUCTS"**: 12px, muted gray
- **METRIC dropdown**: right-aligned
  - Label "METRIC:" — 12px, muted, bold 700, letter-spacing 0.5
  - Select box: dark background (#1a1f26), 1px border, 4px radius, 13px font-weight 600, min-width 130px
  - Options: Overview, Impressions, Clicks, Ad Spend, Ad Sales, Units Ordered

#### Chart Container
- Background: `#0a0e14` (darkest shade), border-radius 6px, padding 12px 8px

---

### ASIN Chart: Overview Mode

When METRIC = "Overview", shows ALL metrics overlaid with **dual Y-axes**:

**Left Y-axis**: "Impressions" label (rotated), ticks: 0, 85, 170, 255, 340
**Right Y-axis**: "Spend ($) / Clicks / Sales ($)" label (rotated), ticks: 0, 2, 4, 6, 8

**5 lines** (each with small dots at every data point):
```
Impressions:  #e8b923 (gold), 2.5px stroke, dots r=2.5    → LEFT y-axis
Total Sales:  #3b82f6 (blue), 2.5px stroke, dots r=2.5    → RIGHT y-axis
Ad Spend:     #e74c3c (red), 2.5px stroke, dots r=2.5     → RIGHT y-axis
Clicks:       #2ecc71 (green), 2.5px stroke, dots r=2.5   → RIGHT y-axis
TACOS:        #e67e22 (orange), 2px stroke, no dots        → RIGHT y-axis
```

**Grid**: both vertical and horizontal lines at every tick mark, color #252b33

**Legend**:
```
■ Total Sales    ● Ad Spend    ■ Impressions    ● Clicks    ● TACOS
```

**Overview Tooltip** (on hover, with vertical crosshair cursor):
```
Sep 5, 1 AM
Total Sales:    $0.00      ← blue label
Ad Spend:       $0.00      ← red label
Impressions:    1          ← gold label
Clicks:         0          ← green label
TACOS:          0.00%      ← orange label
```

Dark background (#1a1f26), 1px border, 6px radius, drop shadow.

---

### ASIN Chart: Placement Mode (Impressions / Clicks / Ad Spend / Ad Sales / Units Ordered)

When METRIC is anything other than Overview, shows **placement breakdown** with a **single Y-axis**:

**4 lines** (each with small dots at every data point):
```
Other on-Amazon:              #8b949e (gray), 2.5px stroke      ← often the highest line
Product Page on-Amazon:       #8b5cf6 (purple), 2.5px stroke    ← second highest
Top of Search on-Amazon:      #2ecc71 (green), 2.5px stroke     ← smaller values
Off Amazon:                   #6e7681 (dim gray), 2px stroke    ← near zero
```

**Y-axis ranges per metric**:
```
Impressions:    max=220,  ticks=[0, 55, 110, 165, 220]     label="Impressions"
Clicks:         max=2,    ticks=[0, 0.5, 1, 1.5, 2]        label="Clicks"
Ad Spend:       max=1.2,  ticks=[0, 0.3, 0.6, 0.9, 1.2]   label="Ad Spend ($)"
Ad Sales:       max=36,   ticks=[0, 9, 18, 27, 36]         label="Ad Sales ($)"
Units Ordered:  max=1,    ticks=[0, 0.25, 0.5, 0.75, 1]    label="Units Ordered"
```

**Legend** (centered below chart):
```
■ Other on-Amazon    ■ Product Page on-Amazon    ■ Top of Search on-Amazon    ■ Off Amazon
```

**Placement Tooltip** (on hover):
```
Sep 4, 9 PM
Other on-Amazon:              114     ← gray label
Product Page on-Amazon:       58      ← purple label
Top of Search on-Amazon:      5       ← green label
Off Amazon:                   2       ← dim label
```

For dollar metrics (Ad Spend, Ad Sales), tooltip shows `$X.XX` format.
For count metrics (Impressions, Clicks, Units Ordered), tooltip shows integers.

---

### Show More Button

Below all ASIN cards:
```
        [      Show More ASINs (5/61)      ]
         Showing 5 of 61 ASINs • 10000 hourly records
```

- Button: full width, outlined (1px border, transparent bg), 6px radius, 14px font-weight 600
- Count text: 12px, muted, centered

---

## Data Sources

### Hourly Data (Primary)

This page requires **hourly granularity** PPC data from the Amazon Ads API:

- **Main chart**: Hourly aggregates of spend, sales, impressions, clicks across all campaigns
- **TACOS**: calculated as `ad_spend / total_sales * 100` per hour
- **ACOS**: calculated as `ad_spend / ad_sales * 100` for the period
- **KPI totals**: Sum of all metrics across the selected time range

### Per-ASIN Data

- **Overview mode**: Per-ASIN hourly impressions, clicks, spend, sales, TACOS
- **Placement mode**: Per-ASIN hourly data broken down by placement type:
  - Top of Search on-Amazon
  - Other on-Amazon
  - Product Page on-Amazon
  - Off Amazon
  
  This comes from the **SP Placement Report** in the Amazon Ads API.

### Group by Parent ASIN

When "Group by parent ASIN" is checked:
- Aggregate child ASIN data under their parent ASIN
- Show the parent ASIN code instead of individual child ASINs
- Product image and title come from the parent variation

### Cumulative Mode

When Cumulative toggle is ON:
- Each bar/line value = running sum of all values from the start of the period to that hour/day
- Apply this transformation client-side: `cumulative[i] = sum(data[0..i])`

---

## Critical Implementation Notes

1. **Each chart mode is a SEPARATE render** — when switching between Overview and any placement metric, the chart must fully remount (use a `key` prop or conditional render). Recharts does NOT handle dynamic yAxisId changes within the same chart instance.

2. **The placement data must be pre-computed** — scale the raw placement counts by the metric type before passing to the chart. E.g. if viewing "Ad Spend", multiply raw placement proportions by the actual dollar amounts.

3. **Disable chart animations** (`isAnimationActive={false}` or equivalent in your chart library) — this page shows live data and needs instant rendering.

4. **The chart background is DARKER than the page** — use your darkest shade for the chart container, not the panel surface color.

5. **All ASIN cards are independent** — each has its own METRIC dropdown that only affects that one card's chart. Changing one card's metric does not affect others.

---

## Navigation

Add "Live Tracker" to sidebar under Advertising, **fourth item** after Campaign Analytics.

Use a heartbeat/pulse icon (↝ or similar waveform icon).

---

## Summary Checklist

- [ ] Route `/w/<account_id>/ppc/live` + sidebar entry
- [ ] Header: brand name + subtitle + 3 time range buttons (orange active + checkmark) + Cumulative toggle
- [ ] 6 KPI cards with gold top border, gradient background, radial glow
- [ ] Main chart: gold bars (impressions) + blue/red gradient-filled lines (sales/spend) + orange dots (TACOS)
- [ ] 6 chart modes: 3 time ranges × cumulative on/off, each with exact Y-axis tick values
- [ ] Dark chart container background (#0a0e14)
- [ ] ASIN-level breakdown: title + "Group by parent ASIN" checkbox + "● LIVE DATA" pulsing badge
- [ ] Per-ASIN cards: product image + title + ASIN (cyan) + METRIC dropdown (6 options)
- [ ] Overview mode: 5 lines on dual axes (impressions left, spend/clicks/sales right) + dots at every point
- [ ] Placement mode: 4 lines (gray/purple/green/dim) + single Y-axis scaled per metric
- [ ] Tooltips: vertical crosshair + colored labels matching line colors
- [ ] "Show More ASINs (5/61)" button + count text
- [ ] Charts use AltaScraper's existing chart style
- [ ] Full-width layout
