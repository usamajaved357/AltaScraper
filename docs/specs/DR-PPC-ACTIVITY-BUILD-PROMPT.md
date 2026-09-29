# Dr PPC™ Console — Activity + Decisions Page — Build Specification

## What This Is

Seventh (last) page of the Dr PPC Console. An append-only activity ledger showing the durable history of plans, decisions, actions, attempts, and verification. Includes a suggested changes review area and filterable timeline of all workspace events.

Route: `/w/<account_id>/dr-ppc/activity`

---

## Page Header

- **Title**: "Activity + decisions" — 22px bold
- **Right**: "6 events shown" — 12px muted
- **Description**: "The durable history of plans, decisions, actions, attempts, and verification." — 13px muted

---

## Section 1 — Ledger Notice

Green-tinted info bar:
- Background: `rgba(63,185,80,0.06)`, border: 1px solid `rgba(63,185,80,0.2)`, 8px radius
- ✓ icon in green + bold text "Append-only workspace ledger." + description in muted

---

## Section 2 — Suggested Changes

Title: "Suggested changes" + "Suggestions only" right-aligned muted text.
Description about reviewing proposals.

### Manual Apply Status Card
- Surface panel with ✓ green icon + "Manual apply" (15px bold)
- Status: "Deployment capable · global writes resumed · no active plan" (12px muted)
- Warning: "No Goals + Strategy + Budget plan active for today" (12px orange)
- Two ghost buttons right-aligned: "Use suggestions only" | "Pause global writes"

### Empty State Panel
- "No compiled bid, budget, placement, target-state, or search-term-negative cards are waiting for review."
- Link to "Analysis + proposals" in cyan

---

## Section 3 — Activity Timeline

### Filter Dropdowns (2)

**Activity type dropdown**: All activity | Plans | Observations | Recommendations | Decisions | Actions | Execution | Verification | System
- Active item highlighted cyan with tint background

**Actor dropdown**: All actors | Human | Analyst | Scheduler | System | Admin-assisted | External
- Same styling

### Timeline Structure

A vertical timeline with:
- **Vertical line**: 2px solid #30363d, running down the left side (position absolute)
- **Dot**: 10px circle at each event's top, surface2 bg with 2px border, sitting on the line
- **Event cards**: surface bg, 1px border, 8px radius, indented 12px from the dot

### Each Event Card Contains:

**Header row** (flex space-between):
- Left: **Type badge** (shaded transparent — Plan=gold, System=blue, Analyst=purple, Action=green) + **action text** (12px muted)
- Right: **timestamp** (12px dim) e.g. "Sep 2, 2026, 1:39 AM"

**Title**: 15px bold — the event headline

**Description** (optional): 13px muted, line-height 1.5

**Meta line**: 11px dim, monospace font — operation ID, actor, entity type, entity ID separated by " · "

### Event Data

| Type | Action | Title | Date |
|------|--------|-------|------|
| Plan | Plan revision created | Created plan revision r1: promixx PPC plan 2026-09 (complete draft) | Sep 2, 1:39 AM |
| System | Managed ppc entitlement scope stamped | Managed Dr PPC for promixx on ATVPDKIKX0DER now stands for the seller channel. | Aug 31, 8:56 PM |
| System | Managed ppc channel scope created | Managed Dr PPC seller channel created for promixx on ATVPDKIKX0DER in state active. | Aug 31, 8:56 PM |
| System | Execution mode changed | Workspace execution mode changed to manual_apply | Aug 31, 3:11 PM |
| System | Workspace brand onboarded | Promixx added to the Dr PPC workspace with status active. | Aug 31, 3:11 PM |
| System | Managed ppc entitlement changed | Managed PPC enabled for this brand and marketplace. | Aug 31, 3:11 PM |

---

## Navigation

Seventh item in Dr PPC sidebar: "Activity + decisions" with ⚡ icon (active, cyan left border).

---

## Summary Checklist

- [ ] Route `/w/<account_id>/dr-ppc/activity`
- [ ] Green ledger notice bar
- [ ] Suggested changes: Manual apply status card + empty state for pending cards
- [ ] Two filter dropdowns: activity type (9 options) + actor (7 options)
- [ ] Vertical timeline with dots and vertical line
- [ ] Event cards: type badge + action text + timestamp + title + optional description + monospace meta
- [ ] Type badges: Plan=gold, System=blue (shaded transparent style)
- [ ] Dropdown items: cyan highlight on active selection
