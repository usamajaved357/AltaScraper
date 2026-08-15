# Sales Dashboard — Match Orbit Exactly

## REFERENCE
- Orbit's sales dashboard: fullcircleorbit.com/brand/flux-footwear/ATVPDKIKX0DER
- Our app: 127.0.0.1:5000/w/nestwell_goods/sales
- orbit_full_audit.md sections 4.11 (Charts), 4.9 (Stat cards), 5 (Tokens)

## CRITICAL RULE
Do NOT change any existing feature or page. Only modify the Sales 
dashboard page (routes/sales_routes.py, static/js/sales.js, and 
related CSS). Nothing else in the app should be affected.

---

## 1. CHART LINES

CURRENT: Thin lines (~1.5px), sharp angular corners, no fill.
ORBIT: Thicker lines (~2.5px), smooth monotone curves, gradient 
area fill under the "this period" line.

FIX:
- Main line (this period): stroke-width 2.5px, blue (#3b82f6), 
  smooth curve interpolation (monotoneX if using d3/recharts)
- Comparison line (last period): stroke-width 1.5px, grey (#6b7280), 
  dashed (dasharray "6,4"), same smooth interpolation
- Area fill under main line: linear-gradient top to bottom, 
  rgba(59,130,246,.15) at top → rgba(59,130,246,0) at bottom
- No area fill under the comparison line

## 2. Y-AXIS

CURRENT: Raw decimals (0, 62.50, 125.00, 187.50, 250.00)
ORBIT: Currency formatted with abbreviation ($0, $35.0k, $70.0k)

FIX:
- Format values as currency with the workspace's currency symbol
- Abbreviate: 1000 → "1k", 10000 → "10k", 100000 → "100k"
- Example: 35000 → "$35.0k" or "£35.0k"
- Font: 11px, color #9ca3af, font-weight 400
- 5 grid lines evenly spaced, grid line color rgba(255,255,255,.06)
- 8px gap between y-axis labels and the chart area

## 3. X-AXIS

CURRENT: Date format (08-10, 08-11, 08-12), only 3 labels shown.
ORBIT: Day names (Sun, Mon, Tue, Wed, Thu, Fri, Sat), full week.

FIX for "Week to Date" chart:
- Show all 7 day names: Sun, Mon, Tue, Wed, Thu, Fri, Sat
- Center each label under its data point
- Font: 11px, color #9ca3af
- Even spacing between labels
- Days with no data yet: show the label but shade that region 
  (same grey shading you already have for "not yet in" days)

FIX for "Today so far" chart:
- Keep hourly format (6 AM, 9 AM, 12 PM, 3 PM, 6 PM, 9 PM)
- Same 11px, #9ca3af styling

## 4. DATA POINT DOTS

CURRENT: Small solid dots appear on hover.
ORBIT: Ring-style dots — colored circle with white center.

FIX:
- At rest: no dots visible on the line
- On hover: dot appears at the nearest data point
  - Main line dot: 8px outer circle (#3b82f6), 4px inner 
    circle (white #ffffff), giving a ring/bullseye effect
  - Comparison line dot: 8px outer (#6b7280), 4px inner (white)
- Transition: opacity .15s ease (fade in, don't pop)

## 5. TOOLTIP

CURRENT: 
  "2026-08-10"
  "This period: 64.98"  (green label, raw number)
  "Before: 34.99 (+86%)" (plain text)

ORBIT:
  "Tue"                             (bold, 14px, day name only)
  "This Week:  $55,796  (Aug 11)"   (blue label, currency, date)
  "Last Week:  $61,389  (Aug 4)"    (grey label, currency, date)

FIX:
- Date heading: show day name only ("Tue", "Wed"), bold, 14px, 
  color --color-text-primary (#f1f5f9)
- Row 1 label: "This Week:" (or "This period:" for non-week views), 
  color matches the main line (#3b82f6), font-weight 500, 12px
- Row 1 value: currency formatted with commas ($55,796), same line, 
  color --color-text-primary, font-weight 600
- Row 1 date: "(Aug 11)" after the value, color #9ca3af, 11px
- Row 2 label: "Last Week:" (or "Before:"), color #6b7280 (matches 
  dashed line), font-weight 500, 12px
- Row 2 value: same formatting as row 1
- Row 2 date: "(Aug 4)" after value
- DO NOT show delta (+86%) in tooltip — show it only as the badge 
  in the card header
- Tooltip background: #1e293b (or var(--panel))
- Tooltip border: 1px solid rgba(148,163,184,.14)
- Tooltip border-radius: 8px
- Tooltip shadow: 0 4px 12px rgba(0,0,0,.5)
- Tooltip padding: 10px 14px
- Tooltip width: auto but min-width 160px
- Tooltip position: follows cursor horizontally, snaps to nearest 
  data point vertically, flips to left side when near right edge

## 6. CROSSHAIR LINE

CURRENT: Thin dark vertical line from data point to x-axis.
ORBIT: Same concept, slightly more visible.

FIX:
- Vertical line from hovered data point down to x-axis
- Stroke: 1px, color rgba(148,163,184,.3)
- No horizontal crosshair line

## 7. CARD CONTAINER

CURRENT: ~16px padding, ~200px chart height, basic border.
ORBIT: ~20-24px padding, ~250px chart height, subtle shadow.

FIX:
- Card padding: 20px 24px
- Chart area height: 250px minimum (was ~200px)
- Card background: var(--panel) (#22262e or #1e293b)
- Card border: 1px solid rgba(148,163,184,.10) — more subtle 
  than a solid hex border
- Card border-radius: 12px
- Card box-shadow: 0 1px 3px rgba(0,0,0,.2) — very subtle

## 8. TITLE AND LEGEND

CURRENT: Title "Week to date" left-aligned, legend below as text.
ORBIT: Title "Week to Date" left, legend top-right as colored lines.

FIX:
- Title: 20px, font-weight 700, color #f1f5f9
- Subtitle: 13px, color #9ca3af, margin-top 4px
- Legend: position top-right of the card (flexbox, justify-content 
  space-between on the header row)
- Legend format: actual SVG line segments (not text dashes)
  - "— This Week" with a 20px blue solid line before the text
  - "- - Last Week" with a 20px grey dashed line before the text
- Legend text: 12px, color #d1d5db
- Delta badge: inline after legend, same line
  - Positive: "↑ 5.2%" in green (#22c55e)
  - Negative: "↓ 0.4%" in red (#ef4444)
  - Font: 13px, weight 600

## 9. "NOT CONNECTED" NOTICE

CURRENT: "AD SPEND TODAY not connected  TACOS not connected" in red.
ORBIT: Shows actual values when connected, nothing when not.

FIX:
- When Ads API is connected: show "AD SPEND THIS WEEK £X,XXX · TACOS X.X%" 
  in gold (#fbbf24 for the numbers, #9ca3af for the labels)
- When NOT connected: show "AD SPEND not connected · TACOS not connected" 
  in muted grey (#6b7280), NOT in red — red implies error, this is just 
  "not set up yet"
- Font: labels 11px uppercase #9ca3af, values 14px bold
- Position: below the chart, 12px margin-top

## 10. STAT CARDS ROW (below the chart)

CURRENT: Not present.
ORBIT: 4 cards in a row below the date presets.

ADD a row of 4 stat cards below the Week to Date chart:

Card 1: "Daily Average"
  - Number: £XX,XXX.XX (24px, weight 700, white)
  - Comparison: "LY: £XX,XXX.XX  +X.X%" (11px, grey label, 
    green/red delta)
  
Card 2: "Total Orders"
  - Number: X,XXX (same styling)
  - Comparison: "LY: X,XXX  +X.X%"

Card 3: "Total Units"
  - Number: X,XXX
  - Comparison: "LY: X,XXX  +X.X%"

Card 4: "Profit"
  - Number: £XX,XXX (green #22c55e if positive, red if negative)
  - No comparison (COGS not always available)

Card styling:
- Use the .stat-card class from the layout pass
- Grid: 4 columns, equal width, gap 16px
- Card padding: 16px 20px
- Label: 12px, color #9ca3af, weight 500
- Number: 24px, weight 700, color #f1f5f9, 
  font-variant-numeric: tabular-nums
- Comparison line: 11px, "LY:" in #6b7280, delta percentage 
  in green (#22c55e) for positive, red (#ef4444) for negative

If the data isn't available yet (no SP-API data), show skeleton 
placeholders instead of £0 or empty cards.

## 11. DATE PRESETS BAR

CURRENT: Not present.
ORBIT: Pill buttons + date picker + compare dropdown + export.

ADD a date presets bar between the charts and stat cards:

Preset pills: 7d | 14d | 30d | 60d | 90d | YTD
Plus named months: Aug | Jul | Jun

Active pill: gold background (#fbbf24), dark text (#0f172a), 
  font-weight 600
Inactive pill: transparent bg, border 1px solid #4b5563, 
  color #9ca3af, hover → border brightens

Date range display: calendar icon + "2026-07-15 to 2026-08-13", 
  12px, border 1px solid #4b5563, border-radius 6px, padding 6px 12px

"COMPARE TO" dropdown: select with options "Prior Year", 
  "Prior Period", "None"

Export button: download icon + "Export", border style, 
  right-aligned

Layout: flexbox, centered, gap 6px between pills, 16px between 
groups (pills | months | date range | compare | export)

## 12. CHART SIZE SPECIFICATIONS

Today so far chart:
- Container: 50% width (left half of the two-panel layout)
- Chart area: fill container minus padding, height 250px
- Left padding for y-axis labels: 50px

Week to Date chart:
- Container: 50% width (right half)
- Chart area: fill container minus padding, height 250px
- Left padding for y-axis labels: 60px (larger numbers)

Both charts in a 2-column grid with 20px gap between them.

## 13. SHADED "NO DATA YET" REGION

For days in the current week that haven't happened yet:
- Shade the chart area for those days with rgba(255,255,255,.03)
- The line should stop at the last day with data
- The shaded region should have a subtle left border at the 
  cutoff point: 1px dashed rgba(255,255,255,.1)

Both your app and Orbit do this — keep your current approach 
but make sure the shade color matches: rgba(255,255,255,.03), 
NOT a heavy grey block.

---

## ORDER OF IMPLEMENTATION

1. Chart lines (thickness, smoothing, area fill)
2. Y-axis formatting (currency, abbreviation)
3. X-axis labels (day names for week view)
4. Tooltip redesign
5. Data point dots (ring style)
6. Card container (padding, height, shadow)
7. Title and legend repositioning
8. Stat cards row
9. Date presets bar
10. "Not connected" styling
11. Chart animations (fadeIn, sweep — see motion prompt)

After each change, verify the chart still renders correctly 
with real data. If a change breaks the chart, revert that 
specific change and move on.

Nothing pushed, model unchanged.
