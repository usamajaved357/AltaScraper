# Dr PPC™ Console — Current State Page — Build Specification

## What This Is

Second page of the Dr PPC Console. Shows the full mirrored Amazon Ads account structure: all campaigns, ad groups, product ads, keywords, targets, and negatives. Each campaign is expandable to reveal its complete internal structure.

Route: `/w/<account_id>/dr-ppc/current-state`

---

## Page Header

- **Title**: "Current state" — 22px bold
- **Description**: "Full Amazon Ads setup, mirrored 100% into the experimental schema. Refreshed nightly, after every change Orbit writes to Amazon, and on demand." — 13px muted
- **Sync line**: "Last synced September 5th, 2026, 11:30 PM PDT (nightly)" — 13px muted
- **"Resync now"** button: ghost button, 🔄 icon, 13px font-weight 600

---

## Section 1 — Entity Count Cards

8 stat cards in a SINGLE bordered row (flat-joined, NOT separate cards with gaps):

```
┌────────┬──────────┬────────────┬──────────┬─────────┬──────────────┬──────────────┬────────────┐
│ 5,253  │    51    │    519     │   252    │   55    │     809      │      30      │     52     │
│CAMPAIGNS│AD GROUPS │PRODUCT ADS │ KEYWORDS │ TARGETS │NEG. KEYWORDS │ NEG. TARGETS │ PORTFOLIOS │
└────────┴──────────┴────────────┴──────────┴─────────┴──────────────┴──────────────┴────────────┘
```

- Container: 1px border, 8px border-radius, overflow hidden
- Each cell: flex 1, padding 14px 16px, separated by 1px right border
- Numbers: 24px bold, **cyan** (#39d2c0)
- Labels: 10px muted, bold 700, uppercase, letter-spacing 0.5

---

## Section 2 — Search + Filters

```
[Search campaigns by name...     ]    [All types ▾]    [All states ▾]    500 of 5253 campaigns
```

- Search: flex 1, surface bg, 1px border, 4px radius
- Type dropdown: All types / SP / SB / SD
- State dropdown: All states / Enabled / Paused / Archived
  - Dropdown panel: surface bg, 1px border, 4px radius, items highlight cyan on active
- Count: "X of Y campaigns" — 12px muted, right-aligned

When "Enabled" is selected, the table filters to show only enabled campaigns and the count updates to "51 of 51 campaigns". An additional **CREATED** column appears showing creation dates.

---

## Section 3 — Campaign Table

### Columns

```
CAMPAIGN | TYPE | STATE | DAILY BUDGET | AD GROUPS | KEYWORDS | TARGETS | PRODUCT ADS | NEGATIVES
```

When filtered to Enabled: adds CREATED column (right-most)

- Headers: 11px muted, bold 700, uppercase
- CAMPAIGN: left-aligned, 13px, truncated with ellipsis (max ~400px)
- TYPE: **shaded badge** — SP = gold tint + gold text, SB = blue tint + blue text
- STATE: **shaded badge** — ENABLED = green tint + green text, PAUSED = orange tint, ARCHIVED = gray tint
- DAILY BUDGET: right-aligned, 14px (e.g. "200.00", "35.00")
- Counts (AD GROUPS through NEGATIVES): right-aligned numbers
- CREATED: right-aligned date (e.g. "06/03/2026")

Rows are clickable — clicking expands the campaign detail below.

---

## Section 4 — Expanded Campaign Detail

When a campaign row is clicked, a detail section expands below it. This shows the COMPLETE internal structure of the campaign.

### 4a — BIDDING

```
BIDDING
[Strategy MANUAL]  [Rest of search +40%]  [Product pages +50%]  [Top of search +130%]
```

- Title: "BIDDING" — 14px bold
- Chips: surface2 bg, 1px border, 4px radius, 12px text. Each contains a label + value pair
- Different campaigns have different strategies: MANUAL, LEGACY_FOR_SALES, etc.
- Placements shown as separate chips

### 4b — Ad Group Card

Each ad group is inside a bordered panel (surface bg, 1px border, 8px radius, padding 16px 20px):

```
Broad    ENABLED    default bid 0.30
```

- Name: 14px bold
- State: shaded badge
- Bid: 12px muted

### 4c — PRODUCT ADS

```
PRODUCT ADS (80)
[B089757THZ ENABLED] [B08QYYX1PW ENABLED] [B09LD9THFT ENABLED] [B09LDFB2F5 PAUSED] ...
```

- Title: "PRODUCT ADS (count)" — 13px bold
- Each ad is a **chip**: ASIN code + state badge
- Chips wrap in a flow layout (flex-wrap)
- ENABLED badge: green text
- PAUSED badge: orange text
- ARCHIVED badge: gray/muted text
- Chip style: surface2 bg, 1px border, 4px radius, 12px text, 4px 10px padding, 6px margin-right, 6px margin-bottom

### 4d — KEYWORDS

```
KEYWORDS (1)
[+promixx  BROAD  0.15  ENABLED]
```

- Title: "KEYWORDS (count)" — 13px bold
- Each keyword is a chip: keyword text + match type + bid amount + state badge
- Keyword text in white, match type and bid in regular, state badge colored

### 4e — NEGATIVES

```
NEGATIVES (35)
[12oz promixx shaker bottle  NEGATIVE_EXACT] [electric protein shaker promixx  NEGATIVE_EXACT] ...
```

- Title: "NEGATIVES (count)" — 13px bold
- Each negative keyword is a chip: keyword text + "NEGATIVE_EXACT" badge in muted gray
- Wrapping flow layout, same chip styling

---

## Data Sources

- **Entity counts**: from the mirrored Amazon Ads data
- **Campaign list**: all campaigns from the mirror, with their type, state, budget, and child entity counts
- **Expanded detail**: ad groups, product ads (ASINs), keywords (with match type + bid), negative keywords from the campaign's mirrored data
- **Bidding**: campaign bidding strategy and placement adjustments
- **Sync status**: timestamp of the last successful mirror run

---

## Navigation

Second item in the Dr PPC Console sidebar. Same sidebar layout as Setup + readiness page.

---

## Summary Checklist

- [ ] Route `/w/<account_id>/dr-ppc/current-state`
- [ ] Page header with sync timestamp + "Resync now" button
- [ ] 8 flat-joined stat cards (cyan numbers, muted labels)
- [ ] Search + Type/State dropdowns with campaign count
- [ ] State dropdown: All states / Enabled / Paused / Archived with cyan highlight
- [ ] Campaign table: CAMPAIGN / TYPE / STATE / DAILY BUDGET / AD GROUPS / KEYWORDS / TARGETS / PRODUCT ADS / NEGATIVES
- [ ] Type badges: SP gold, SB blue (shaded transparent)
- [ ] State badges: ENABLED green, PAUSED orange, ARCHIVED gray (shaded transparent)
- [ ] Expandable campaign rows showing:
  - [ ] BIDDING: strategy + placement adjustment chips
  - [ ] Ad group cards with name, state badge, default bid
  - [ ] PRODUCT ADS: wrapping chip grid of ASINs with ENABLED/PAUSED/ARCHIVED badges
  - [ ] KEYWORDS: chips with keyword + match type + bid + state
  - [ ] NEGATIVES: chips with keyword + NEGATIVE_EXACT badge
- [ ] All chips: surface2 bg, 1px border, 4px radius, wrapping flow layout
