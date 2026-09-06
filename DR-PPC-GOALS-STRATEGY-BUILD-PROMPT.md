# Dr PPC™ Console — Goals + Strategy + Budget Page — Build Specification

## What This Is

Third page of the Dr PPC Console. A comprehensive plan editor for PPC strategy: plan identity, operating constraints, strategy document (markdown), measurable goals, budget plan, and budget allocations. All form sections use WHITE/LIGHT themed panels on the dark page background. Every save creates an immutable revision; only an activated revision becomes approved strategy.

Route: `/w/<account_id>/dr-ppc/plan`

---

## Page Header

- **Title**: "Goals + Strategy + Budget" — 22px bold
- **Subtitle**: "Workspace-owned intent shared with Analyst chat. Independent from the classic PPC engine." — 13px muted
- **Right side** (3 elements):
  - **Revision badge**: "R1 · DRAFT" — outlined badge, cyan border, 12px font-weight 600
  - **"Save new draft"** button: ghost button, 1px border, 13px font-weight 600, icon 📋
  - **"✓ Activate r1"** button: green (#3fb950) filled, dark text, font-weight 700, checkmark icon

---

## IMPORTANT: All Form Panels Use WHITE/LIGHT Theme

Every form section (Plan identity, Operating constraints, Strategy document, Goals, Budget plan, Allocations) sits inside a WHITE-background panel with LIGHT-themed form elements — exactly like the Workspace configuration panel on the Setup page.

### Light Panel Styling
- Background: **#ffffff**
- Border: 1px solid #d1d9e0
- Border-radius: 10px
- Padding: 22px 26px
- Text color: #1f2328 (dark)

### Light Form Input Styling
- Background: **#f0f2f5** (light gray, NOT white)
- Border: 1px solid #d1d9e0
- Border-radius: 6px
- Padding: 9px 12px
- Font: 14px, dark text (#1f2328)
- Labels: 11px, light muted (#656d76), bold 700, uppercase, letter-spacing 0.3
- Dropdowns: same bg + border + radius, with native select arrow
- Textareas: same styling, resizable vertically
- **Active/focused dropdown**: 2px solid gold/amber (#e8b923) border highlight (visible in screenshots)

---

## Section 1 — Plan Identity

White panel:

```
Plan identity
Every save creates an immutable revision. Only an activated revision is approved strategy.

PLAN TITLE                              PERIOD START         PERIOD END
[promixx PPC plan 2026-09 (complete d]  [09/01/2026  📅]     [09/30/2026  📅]
```

- 3-column layout: PLAN TITLE (wide, ~60%), PERIOD START, PERIOD END
- Date inputs have calendar icon (📅)

---

## Section 2 — Operating Constraints

White panel:

```
Operating constraints
Standing policy this brand's operators wrote when rejecting a card. The analyst reads every active row
on every run. Enforced rows also gate compilation, so a proposal that breaks one is never born.

[0 active]

┌──────────────────────────────────────────────────────────────────────────────┐
│ No standing constraints yet. Rejecting a card and choosing "standing rule   │
│ for future runs" records one here.                                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

- "0 active" badge: small outlined pill
- Empty state: centered text inside a bordered, slightly tinted panel

---

## Section 3 — Strategy Document

White panel:

```
Strategy document                                                    Preview
Narrative context belongs here. Measurable goals and spend allocations stay structured below.
```

- "Preview" link: right-aligned, cyan/orange colored
- Below: a **monospace code editor / textarea** with markdown content

### Strategy Document Content (Monospace Textarea)

The textarea contains markdown-formatted strategy text:

```markdown
# PPC Strategy

## Business context
promixx on marketplace ATVPDKIKX0DER, reported in USD...

## Product priorities
1. B0DNFX8MW3 — top-spend ASIN #1 over the trailing 30 days.
2. B0GGTPSSJN — top-spend ASIN #2 over the trailing 30 days.
...

## Market position
_Not stated..._

## Strategic approach
- Non-branded ACOS is held between 14.9% and 24.9%...

## Targeting principles
- non_branded carries the growth mandate...

## Constraints and exclusions
...

## Current hypotheses
_None recorded..._

## Questions still unresolved
...
```

- Textarea: monospace font ('SF Mono', Consolas, monospace), dark text on light bg
- Scrollable, resizable
- Full width of the panel

---

## Section 4 — Goals

White panel with "+ Add goal" button:

```
Goals                                                          + Add goal
Machine-evaluable outcomes that future Performance and scheduled reviews can measure.
```

### Each Goal is a numbered form card (Goal 1, Goal 2, etc.)

Each goal card has a delete button (🗑) in the top-right corner and contains:

**Row 1** (3 columns for Goal 1, varies by goal):
```
TITLE                                    SCOPE              SCOPE ID
[Non-branded ACOS inside the approved ]  [Strategic lane ▾]  [non_branded    ]
```

**Row 2** (4 columns):
```
METRIC          OPERATOR        TARGET          UPPER TARGET
[acos         ]  [Between   ▾]  [14.9         ]  [24.9         ]
```

**Row 3** (4 columns):
```
UNIT             WINDOW                    AGGREGATION              PRIORITY
[Percent    ▾]   [Trailing 14 complete ▾]  [Recomputed ratio  ▾]   [Critical  ▾]
```

**Row 4** (full width):
```
RATIONALE
[Band derived from 80% of the brand's 31.17% revenue-weighted break-even ACOS...]
```

### Dropdown Options

**SCOPE**: Brand | ASIN | Goal | Strategic lane | Portfolio | Campaign | Reserve
**OPERATOR**: Between | At most | At least | Exactly
**UNIT**: Currency | Percent | Number | Rank | ROAS
**WINDOW**: Not evaluable yet | Latest complete day | Trailing 7 complete days | Trailing 14 complete days | Plan to date | Latest fresh evidence
**AGGREGATION**: Not specified | Sum | Recomputed ratio | Latest value
**PRIORITY**: Critical | High | Normal | Low

Active/selected dropdown items are highlighted with light blue background in the dropdown panel.

### Goal Data (4 goals)

**Goal 1**: Non-branded ACOS inside the approved band
- Scope: Strategic lane / non_branded
- Metric: acos, Operator: Between, Target: 14.9, Upper Target: 24.9
- Unit: Percent, Window: Trailing 14 complete days, Aggregation: Recomputed ratio, Priority: Critical

**Goal 2**: Non-branded cost per ad order at or under the cap
- Scope: Strategic lane / non_branded
- Metric: cost_per_ad_order, Operator: At most, Target: 4.84
- Unit: Currency, Window: Trailing 14 complete days, Aggregation: Recomputed ratio, Priority: Critical

**Goal 3**: Brand TACOS at or under target
- Scope: Brand
- Metric: tacos, Operator: At most, Target: 12
- Unit: Percent, Window: Trailing 14 complete days, Aggregation: Recomputed ratio, Priority: High

**Goal 4**: Hold or improve category rank for B0DNFX8MW3
- Scope: ASIN / B0DNFX8MW3
- Metric: organic_rank, Operator: At most, Target: 58237
- Unit: Rank, Window: Trailing 14 complete days, Aggregation: Sum, Priority: Normal

---

## Section 5 — Budget Plan

White panel:

```
Budget plan                                                Allocated: 100.0% · USD 0
Intended spend—not the sum of Amazon campaign delivery ceilings.

CURRENCY        TOTAL PLANNED SPEND     BUDGET BEHAVIOR          EXPERIMENT RESERVE %
[USD          ]  [12025.02            ]  [Flexible target   ▾]   [10                ]
```

- "Allocated: 100.0% · USD 0" — right-aligned, muted text
- 4-column layout

---

## Section 6 — Allocations

```
Allocations                                                    + Add allocation
```

### Each Allocation is a numbered card (Allocation 1, 2, 3, 4)

Each has a delete button (🗑) and contains:

**Row 1** (3 columns):
```
LABEL                         SCOPE              SCOPE ID
[Non-branded               ]  [Strategic lane ▾]  [non_branded    ]
```

**Row 2** (3 columns):
```
AMOUNT          PERCENTAGE       PRIORITY
[             ]  [55            ]  [High      ▾]
```

**Row 3** (full width):
```
RATIONALE
[Template lane split from plans:draft, not a measured split...]
```

### Allocation Data (4 allocations)

**Allocation 1**: Non-branded / Strategic lane / non_branded / 55% / High
**Allocation 2**: Branded / Strategic lane / branded / 25% / Normal
**Allocation 3**: Unclassified / Strategic lane / unclassified / 10% / Normal
**Allocation 4**: Experiment reserve / Reserve / 10% / Low — "Held back for tests rather than committed to a lane."

---

## Data Sources

- **Plan data**: stored as JSON revisions in the database. Each save creates a new immutable revision
- **Goals**: configurable metrics that the analyst evaluates in scheduled runs
- **Budget**: total planned spend for the period, split across allocations
- **Strategy document**: free-form markdown written by the operator or drafted by the AI analyst
- **Operating constraints**: rules recorded when operators reject analysis proposals

---

## Navigation

Third item in the Dr PPC Console sidebar: "Goals + strategy" with a 🎯 icon (or target icon).

---

## Visual Style Notes

- ALL form sections use **WHITE panels** on the dark page — same as workspace config
- Form inputs: **light gray bg** (#f0f2f5), NOT white
- **Focused dropdowns** get a **gold/amber border** (#e8b923) — visible in screenshots when dropdown is open
- Dropdown panels: white bg, items with light blue highlight on hover/selected
- Delete buttons (🗑): dim gray, top-right of each Goal/Allocation card
- Goal/Allocation titles: "Goal 1", "Goal 2", etc. — 14px bold, dark text
- The strategy document textarea uses **monospace font**
- "+ Add goal" and "+ Add allocation" buttons: ghost style, right-aligned

---

## Summary Checklist

- [ ] Route `/w/<account_id>/dr-ppc/plan`
- [ ] Header: title + "R1 · DRAFT" badge + "Save new draft" button + "✓ Activate r1" green button
- [ ] Plan identity: white panel with PLAN TITLE + PERIOD START/END date pickers
- [ ] Operating constraints: white panel with "0 active" badge + empty state
- [ ] Strategy document: white panel with monospace markdown textarea + "Preview" link
- [ ] Goals: white panel with "+ Add goal", 4 goal forms each with TITLE/SCOPE/SCOPE ID/METRIC/OPERATOR/TARGET/UPPER TARGET/UNIT/WINDOW/AGGREGATION/PRIORITY/RATIONALE
- [ ] All dropdown options documented (SCOPE 7 options, PRIORITY 4, AGGREGATION 4, WINDOW 6, UNIT 5)
- [ ] Budget plan: white panel with CURRENCY/TOTAL PLANNED SPEND/BUDGET BEHAVIOR/EXPERIMENT RESERVE %
- [ ] Allocations: 4 allocation forms with LABEL/SCOPE/SCOPE ID/AMOUNT/PERCENTAGE/PRIORITY/RATIONALE
- [ ] All form panels: white bg, light gray inputs, gold focus border on dropdowns
- [ ] Delete buttons on each Goal and Allocation card
- [ ] Monospace font in strategy document textarea
