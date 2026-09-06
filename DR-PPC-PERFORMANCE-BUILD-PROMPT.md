# Dr PPC™ Console — Performance Page — Build Specification

## What This Is

Fifth page of the Dr PPC Console. A performance dashboard showing how the account is doing vs baseline expectations: daily KPIs with status badges, 7-day trend comparison, change drivers, largest spenders, and plan-dependent sections (budget pacing, goal progress, rank evidence).

Route: `/w/<account_id>/dr-ppc/performance`

---

## Page Header

- **Title**: "Performance" — 22px bold
- **Right**: "Latest complete day: Sep 5" — 12px cyan, font-weight 600
- **Description**: "How the account is doing right now. The latest complete reporting day is the verdict; today is a partial pulse only." — 13px muted

---

## Section 1 — Latest Complete Day KPIs

Title: "Latest complete day · Sep 5" — 18px bold
Subtitle: "Scored against the 60-day baseline (Jul 7 to Sep 4)." — 12px muted

6 cards in `repeat(6,1fr)` grid, 8px gap. Each card has a **colored left border** (3px) — different color per metric:

| Metric | Value | Delta | Status | Left Border Color |
|--------|-------|-------|--------|-------------------|
| TOTAL SALES | $2,612 | -$249 vs expected | ✓ in line with baseline (green) | cyan |
| SPEND | $346 | -$42 vs expected | ✓ in line with baseline (green) | blue |
| TACOS | 13.3% | -0.5pts vs expected | ✓ in line with baseline (green) | green |
| AD SALES | $1,251 | -$314 vs expected | ⚠ drifting from baseline (orange) | orange |
| ACOS | 27.7% | +2.2pts vs expected | ✓ in line with baseline (green) | gold |
| PPC CVR | 8.1% | -5.6pts vs expected | ✗ off baseline (red) | red |

**Status badges** (shaded transparent, matching PPC page badge style):
- "✓ in line baseline" — green tint bg, green text
- "⚠ drifting baseline" — orange tint bg, orange text
- "✗ off baseline" — red tint bg, red text

---

## Section 2 — Today So Far

Dark surface panel, single row:
```
Today so far (Sep 6, partial)    spend $89 · ad sales $258 · 173 clicks · 0 ad orders
Today is incomplete and attribution will continue to mature.
```

---

## Section 3 — Strategy Lanes · 14 Complete Days

Title with "Review classification" orange link on the right.
Empty state: centered dim text in a bordered panel.

---

## Section 4 — 7-Day Trend

Table inside a bordered panel:

| WINDOW | SPEND | AD SALES | TOTAL SALES | AD ORDERS | ACOS | TACOS | PPC CVR |
|--------|-------|----------|-------------|-----------|------|-------|---------|
| Recent · Aug 30 to Sep 5 | $2,506 | $9,969 | $19,086 | 458 | 25.1% | 13.1% | 11.6% |
| Prior · Aug 23 to Aug 29 | $2,697 | $11,335 | $20,639 | 563 | 23.8% | 13.1% | 13.6% |
| Change | -7.1% | -12.1% | -7.5% | -18.6% | +1.4pts | +0.1pts | -2.0pts |

Change row: values colored green (improvement) or red (decline). Font-weight 600.

---

## Section 5 — Change Drivers

Campaigns ranked by spend movement. Table columns: CAMPAIGN | TYPE | SPEND Δ | MOVEMENT SHARE | SALES Δ | ORDERS Δ | RECENT SPEND

- SPEND Δ: green for negative (less spend), red for positive (more spend)
- SALES Δ: green for positive, red for negative
- ORDERS Δ: green for positive, red for negative

---

## Section 6 — Largest Spenders

Top spending campaigns by absolute spend. Columns: CAMPAIGN | TYPE | SPEND | SHARE | AD SALES | ACOS | ORDERS

- ACOS color-coded: >40% = red, 30-40% = orange, <30% = normal

---

## Section 7 — Bottom Status Cards

3 cards in `repeat(3,1fr)` grid with **colored top border** (3px):
- **Budget pacing** (cyan top): empty state with plan activation prompt
- **Goal progress** (gold top): empty state with plan activation prompt
- **Rank evidence** (purple top): empty state with plan activation prompt

---

## Section 8 — Evidence Gaps

Bordered panel with bulleted list in orange text: things the page can't determine yet.

---

## Navigation

Fifth item in Dr PPC sidebar: "Performance" with 📈 icon.

---

## Summary Checklist

- [ ] Route `/w/<account_id>/dr-ppc/performance`
- [ ] 6 KPI cards with colored left borders + status badges (in line/drifting/off)
- [ ] Today so far partial stats bar
- [ ] Strategy lanes empty state with "Review classification" link
- [ ] 7-day trend comparison table (Recent vs Prior vs Change)
- [ ] Change drivers table with colored spend/sales/orders deltas
- [ ] Largest spenders table with ACOS color coding
- [ ] 3 bottom status cards (Budget/Goal/Rank) with colored top borders
- [ ] Evidence gaps bulleted list in orange
