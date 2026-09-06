# Dr PPC™ Console — Setup + Readiness Page — Build Specification

## What This Is

The Dr PPC Console is a PPC management and automation engine inside AltaScraper. This is the first page: **"Setup + readiness"** — a configuration and diagnostic dashboard that shows workspace settings, proof readiness checks, plan status, runtime health, automation schedules, lane classification rules, and search-term evidence.

The attached `orbit-dr-ppc-setup.jsx` is a **visual reference only**.

Route: `/w/<account_id>/dr-ppc/setup`

---

## Layout: 3-Panel Structure

The Dr PPC Console has its own layout different from the main AltaScraper pages:

```
┌──────────────────────────────────────────────────────────────────┐
│  [Left Sidebar 200px]  │  [Main Content ~1060px]  │  [Analyst]  │
└──────────────────────────────────────────────────────────────────┘
```

- **Left Sidebar**: 200px fixed, dark (#161b22), sticky, full height
- **Main Content**: scrollable, dark bg (#0d1117), max-width ~1060px
- **Analyst Panel** (optional right sidebar): collapsible chat panel — build as a placeholder for now

---

## Left Sidebar

### Header (top section, border-bottom)
- **Avatar**: 36px circle, gradient background (dark green → teal), robot icon
- **Title**: "Dr PPC™ Console" — 14px bold
- **Account selector**: "promixx · US ▾" — 11px muted, clickable dropdown
- **Action button**: "Manual apply ▸" — green (#3fb950) filled pill, 11px bold 700, dark text
- **Info icon**: ⓘ next to the button, dim gray

### Navigation (7 items)
```
⚙  Setup + readiness     ← active (cyan left border, white text, subtle bg highlight)
📋 Current state
🎯 Goals + strategy
📦 Products
📈 Performance
🔬 Analysis + proposals
⚡ Activity + decisions
```

- Active item: `border-left: 2px solid #39d2c0`, white text, font-weight 600, `rgba(255,255,255,0.06)` background
- Inactive: no left border, muted text, font-weight 400
- Font: 13px, 9px vertical padding, 14px left padding
- Icons: 15px emoji or SVG

### Footer
- Green dot (8px) + "Synced 1h ago" — 11px muted, bottom of sidebar

---

## Main Content — Page Header

```
Setup + readiness                                    🔄 Refresh evidence
Make the Promixx proof legible before enabling analysis or Amazon execution.
```

- Title: 22px bold
- Description: 13px muted
- "Refresh evidence" button: ghost button, 1px border, muted text, 🔄 icon

---

## Section 1 — Workspace Configuration

**THIS SECTION USES A WHITE/LIGHT THEME** — it's a white panel sitting on the dark page background.

### Panel Container
- Background: **#ffffff** (pure white)
- Border: 1px solid #d1d9e0 (light gray)
- Border-radius: 10px
- Padding: 22px 26px
- All text inside uses DARK colors

### Header Row
- Title: "Workspace configuration" — 18px bold, dark text (#1f2328)
- **"Save configuration"** button: **GOLD/AMBER** (#e8b923) filled, dark text, border-radius 6px, font-weight 700 — NOT cyan, NOT green
- Description below: "These controls only determine eligibility. Saving them does not run analysis or touch Amazon." — 13px, light muted (#656d76)

### Form Fields (3 columns)

| Label | Type | Default Value |
|-------|------|---------------|
| DISPLAY NAME | text input | Promixx |
| WORKSPACE STATUS | dropdown | Active |
| ANALYSIS PROFILE | dropdown | Non-branded growth v1 |

Below: AMAZON ADS PROFILE dropdown (full width ~420px): "PROMiXX: The Original Vortex Mixer · seller · US — 2842..."

**Input styling** (light theme):
- Background: #f0f2f5 (light gray, NOT white)
- Border: 1px solid #d1d9e0
- Border-radius: 6px
- Padding: 9px 12px
- Font: 14px, dark text (#1f2328)
- Labels: 11px, light muted (#656d76), bold 700, uppercase, letter-spacing 0.3

### Toggle Switches (3 across, in a bordered row)

```
┌─────────────────────┬──────────────────────┬──────────────────────┐
│ Scheduled            │ Exclude legacy       │ Manual apply         │
│ observation    [●━━] │ automation     [●━━] │ eligible       [●━━] │
│ Makes the brand...   │ Keep this indep...   │ Eligibility only...  │
└─────────────────────┴──────────────────────┴──────────────────────┘
```

- Container: 1px border, 8px radius, overflow hidden, light surface bg (#f6f8fa)
- Separated by 1px vertical borders
- Each toggle: 14px padding
- **Toggle switch ON color**: **GOLD/AMBER** (#e8b923) — NOT green
- Toggle switch OFF: gray (#bbb)
- Toggle dimensions: 42×22px track, 18px handle with shadow
- Title: 13px bold 600, dark text
- Description: 12px, light muted, line-height 1.4

---

## Section 2 — Proof Readiness

Title: "Proof readiness" — 20px bold, on the DARK background
Description: "Green means the evidence or configuration exists. It never means execution is automatically enabled." — 13px muted

### Readiness Check Grid

All 10 checks sit INSIDE A SINGLE dark panel (surface bg #161b22, border 1px #30363d, border-radius 10px, padding 16px 18px).

**Layout**: 5 columns × 2 rows, 4px gap

Each check has:
- **Green check** (ok): 24px circle, 2px solid green border, green-tinted bg `rgba(63,185,80,0.12)`, white SVG checkmark inside
- **Empty check** (not ok): 24px circle, 2px solid gray border (#4a4f57), no fill
- Title: 14px, font-weight 600, white
- Sub-text: 12px, muted

**Row 1**: ✅ Ads profile (designated) | ✅ Standard lanes (3 active) | ○ Branded rules (0 active) | ○ Non-branded rules (0 active) | ○ Reviewed campaigns (0 exact)
**Row 2**: ○ Classification coverage (0.00%) | ○ Active plan (No active plan) | ○ Scheduled observation (Blocked) | ✅ Manual apply (Authorized, still gated) [**TEAL HIGHLIGHT BG**] | (empty)

The **Manual apply** check has a special teal highlight: `background: rgba(45,212,191,0.08)` with border-radius 6px

### Backend Next Steps

Separate panel below the checks (same dark surface styling):

```
Backend next steps
• Add reviewed branded search-term rules.
• Add reviewed non-branded search-term rules.
• Assign exact reviewed campaign ids to the non_branded lane.
• Approve and activate a current Goals + Strategy + Budget plan.
Tell Analyst your goals, strategy and budget to review...
Open the plan form instead     ← ORANGE color (#d29922), NOT cyan
```

---

## Section 3 — Plan Readiness

Title + description on dark background.

### "No active plan" card
- Surface bg, bordered, 8px radius
- Left: title "No active plan" (14px bold) + description (12px muted)
- Right: **red badge** `● Plan cannot be scored` — 1px red border, red text, red dot

### Error card
- Background: `rgba(248,81,73,0.06)` (subtle red tint)
- Border: 1px solid `rgba(248,81,73,0.25)`
- Red ⊗ icon (18px) on the left
- Title: "No active Goals + Strategy + Budget plan" (14px bold)
- Description text + monospace "Closed by Plan · activate a revision..."

### Link
- "Open the plan" — cyan (#39d2c0), 13px bold 600

---

## Section 4 — Runtime Checks

5 horizontal cards in a flex row, 8px gap:

Each card:
- Surface bg, 1px border, 8px radius, 14px padding
- **Status badge** centered at top: green outlined pill (1px green border, green text, 12px radius) with ✓ checkmark — e.g. "✓ Profile resolved", "✓ Mirror fresh", "✓ Configured", "✓ Version confirmed"
- Title: 13px bold 700
- Sub-text: 12px muted
- Secondary sub-text (optional): 11px dim

### Green status bar below
- Subtle green bg `rgba(63,185,80,0.06)`, 6px radius
- ✓ icon + "Global writes resumed · deployment mutations capable · brand mode Manual apply"

---

## Section 5 — Automation Schedule + Run Evidence

### Schedule Cards (2 cards connected by an arrow)

```
┌─────────────────────────┐         ┌─────────────────────────┐
│ DAILY CRON    ✓Scheduled│  ──→    │ CHAINED TRIGGER ✓Enrolled│
│ 06:30 UTC · Current-    │ ONLY    │ Strategy analysis · no   │
│ state mirror            │ AFTER   │ separate cron            │
│ 30 6 * * * Next: Sep 7  │ SUCCESS │ Immediately after...     │
│ Resolve this active...  │         │ Partial, failed...       │
└─────────────────────────┘         └─────────────────────────┘
```

- Left card: rounded left corners, straight right edge
- Right card: straight left edge, rounded right corners
- Arrow between them on the page bg: → + "ONLY AFTER SUCCESS" (9px dim uppercase)
- Both cards: surface bg, 1px border
- Labels: "DAILY CRON" / "CHAINED TRIGGER" — 11px muted, bold 700, letter-spacing 0.8
- Status badges: green outlined pills with ✓

### Recent Automated Runs

Header: "Recent automated runs" + "5 shown" + "Open Analysis + proposals" (cyan link) + "Run baseline research"

List of expandable MIRROR runs:
- Each: surface bg card, 8px radius, 6px margin-bottom
- Collapsed: "MIRROR" label (12px muted bold) + date (14px bold) + "Mirror #XXXX" (12px dim) + "✓ Success" (green, right)
- **Expanded** (first run by default): shows "Mirrored 7,021 entities with 0 warnings." + 2×2 grid of check results, each with ✓ icon + title + description on surface2 bg

---

## Section 6 — Lane Classification

### Classified Spend Meter
- Surface bg panel, 8px radius
- Big number: "0.00%" (26px bold) + "classified spend" (13px muted)
- Orange warning badge: "■ Below the 80% confidence bar"
- Progress bar: 6px height, gray track, with a **vertical marker at 80%** (2px wide, white/text color, extends above and below the bar)
- Stats below: "$0 classified  $5,135 unclassified  1953 search terms" (12px muted)

### Two-Column Layout: Add Rule + Reviewed Lanes

**Left — Add Reviewed Rule** (surface panel):
- Title: 16px bold, description: 12px muted
- Form: LANE dropdown (Branded), EVIDENCE TYPE dropdown (Search term), MATCH dropdown (Contains), PATTERN text input, PRIORITY number input (100), RATIONALE textarea
- Inputs: surface2 bg, 1px border, 4px radius
- Labels: 10px muted bold uppercase
- "Save reviewed rule" button: ghost button, right-aligned

**Right — Reviewed Campaign Lanes** (surface panel):
- Title: 16px bold, description: 12px muted
- Big number: "0" (26px bold)
- Progress indicator: "No reviewed lane 5253  of 5253 live campaigns"
- Empty state: "No exact campaign assignments yet." centered in a bordered box

---

## Section 7 — Priority-Ordered Rules Table

Header: "Priority-ordered rules" + "0 active" (orange text, right)
Description: "Every match remains visible with its source and rationale."

Table columns: PRIORITY | LANE | EVIDENCE | MATCH | PATTERN / ID | SOURCE | RATIONALE | ACTIVE

Empty state: "No rules configured yet." centered

---

## Section 8 — Search-Term Evidence Table

Header: "Search-term evidence" + "Unclassified first" sort dropdown (right)
Description: "Highest-spend terms from the trailing 14 complete days, with the exact rule that classified each term."

Table columns: SEARCH TERM | LANE | MATCHED RULE | SPEND | AD SALES | ORDERS

- Search terms in **monospace font** ('SF Mono', Consolas, monospace)
- Lane: "Unclassified" in muted
- Matched Rule: "No reviewed rule" in dim
- Numbers: right-aligned, 14px

Data:
| promixx shaker bottle | Unclassified | No reviewed rule | $716 | $4,386 | 213 |
| protein shaker bottle | Unclassified | No reviewed rule | $450 | $1,706 | 99 |
| shaker bottle | Unclassified | No reviewed rule | $325 | $886 | |
| shaker cups for protein shakes | Unclassified | No reviewed rule | $198 | $477 | |
| stainless steel shaker bottle | Unclassified | No reviewed rule | $164 | $321 | |
| protein shaker | Unclassified | No reviewed rule | $135 | $325 | 22 |

---

## Data Sources

- **Workspace configuration**: stored in the account config (display name, ads profile, analysis profile, toggles)
- **Proof readiness**: computed from the account's current state — does the ads profile exist, are lanes configured, are rules set, etc.
- **Plan readiness**: check if an active plan covers today's date
- **Runtime checks**: ping the ads profile API, check mirror freshness, verify worker versions
- **Recent runs**: log of automated mirror and analysis runs with timestamps and outcomes
- **Lane classification**: from the search-term rules engine — how much spend is classified by reviewed rules
- **Search-term evidence**: top-spend search terms from trailing 14 days with their classification status

If any data source isn't available, stub with placeholder data and `# TODO`.

---

## Navigation

The Dr PPC Console is a separate section in AltaScraper's sidebar under **Advertising**:

```
Advertising
  PPC Analytics
  Search Terms
  Campaign Analytics
  Live Tracker
  Dr PPC™ Console      ← this opens the Dr PPC layout with its own sub-sidebar
```

The Dr PPC Console has its own left sidebar with 7 sub-pages. This spec covers only the first one (Setup + readiness). The other 6 are future pages — add them as placeholder routes.

---

## Visual Style Notes

- **Workspace config panel**: WHITE background inside the dark page — this is the ONLY light-themed section
- **"Save configuration" button**: GOLD/AMBER (#e8b923), NOT cyan or green
- **Toggle switches**: GOLD/AMBER when ON
- **"Open the plan form instead" link**: ORANGE (#d29922), not cyan
- **Readiness checks**: inside a SINGLE dark panel, not individual cards
- **Manual apply check**: has a teal highlight background
- **Active sidebar item**: 2px cyan left border
- **All form inputs inside workspace config**: light gray bg (#f0f2f5), NOT white
- **Search terms**: monospace font
- **Runtime badges**: green outlined pills with ✓, NOT filled
- **All other sections**: standard dark theme

---

## Summary Checklist

- [ ] Route `/w/<account_id>/dr-ppc/setup` + sidebar entry under Advertising
- [ ] Dr PPC left sidebar: avatar, title, account selector, Manual apply button, 7 nav items, sync status
- [ ] Workspace config: WHITE panel, gold Save button, 3 dropdowns + ads profile, 3 gold toggles
- [ ] Proof readiness: single dark panel, 5×2 grid of checks, green/empty circles, teal highlight on Manual apply
- [ ] Backend next steps: bulleted list + orange "Open the plan form" link
- [ ] Plan readiness: "No active plan" with red "Plan cannot be scored" badge + red error box
- [ ] Runtime checks: 5 horizontal cards with green status badges + green status bar
- [ ] Automation schedule: Daily Cron → arrow → Chained Trigger (connected cards)
- [ ] Recent runs: expandable MIRROR entries with Success badges and 2×2 check grids
- [ ] Lane classification: 0.00% progress bar with 80% marker + Add Rule form + Reviewed Lanes panel
- [ ] Priority-ordered rules: empty table with 8 columns
- [ ] Search-term evidence: table with monospace terms, Unclassified lane, spend/sales/orders
- [ ] Analyst panel: placeholder for right-side chat (future)
