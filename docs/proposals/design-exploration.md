# Design exploration — three directions (for the owner to choose)

**PARKED 28 Sep 2026.** The owner prefers his current app and named the pages to
build on (see docs/proposals/liked-pages-anatomy.md and docs/decisions.md);
design work is on hold. Clickable prototypes of the three directions below are
in `prototypes/design-review/` (open `index.html`). Kept for later reference.

Status (original): **PROPOSAL, nothing built.** Milestone 7, 28 Sep 2026. Milestones 8
(final design system) and 9 (screen-by-screen migration) wait on the choice
below, because the design system follows from it and the owner's written rule
is that a new convention needs his approval (docs/design-system.md).

Grounded in: the master audit (sections 11-15), docs/design-system.md (what
exists), DESIGN_RULES.md (the owner's redesign rules), and the fixes of
Milestones 2-6.

---

## What any direction must keep

These already work and the owner has asked for them; every direction keeps them.

- **Unknown is never zero.** A figure Amazon has not given is "not known", not 0.00.
- **Status = one colour mapping** (review amber, blocked red, ready green, live
  neutral) and **one primary button per state** (DESIGN_RULES.md).
- **Anything that spends money or changes Amazon is a deliberate button**, and
  its confirmation names the account, seller and marketplace.
- **Amazon's reply is kept as the record** (field chips), and bulk results are
  split "On Amazon" vs "Recorded here".
- **The product page opens over the grid** and keeps the grid underneath.
- **The drawer's literal hex palette** stays (owner's decision, 29 Aug 2026).
- **Dark theme only; no section transitions** (matched to Orbit).

## The problems every direction has to solve

From the audit, measured in code:

| Problem | Evidence |
|---|---|
| Account and marketplace live in the user's head | marketplace only in an overlay sidebar; "All marketplaces" honoured by one screen |
| Too many look-alike destinations | ~43 nav items; screens rarely link to each other |
| Money is answered in several places | cost price entered in 4 places; P&L vs Finance vs Sales |
| Seven token sets, 432 distinct colours, 32 font sizes, 63 shadows | audit section 13 |
| Feedback is a 1.8 s toast | fixed in Milestone 6 (announced, styled, timed) but still the only channel |
| Accessibility | ~102 clickable non-buttons, 251 unlabeled controls, no focus trap |

---

## Direction 1 — Operations cockpit (dense, keyboard-first)

**Philosophy.** You know the business; the screen's job is throughput.

- One **context bar** at the top of every screen: account · marketplace · date
  window. Every screen obeys it; nothing has its own date picker.
- **Dense tables with inline actions**; the command palette (Ctrl+K, which
  exists) becomes the main navigation; the sidebar shrinks to 6 groups.
- **Queues instead of menus**: "Needs attention" is a view of every screen.
- Errors become **persistent inline states** on the row they are about.

*Listings + PDP:* grid by default, keyboard row navigation, PDP as a side
panel with the three blocking facts on top. *Orders:* one table, expand in
place. *Sales/P&L:* one reconciled figure per period on the context bar.

**Cost:** high (every screen reads the context bar). **Risk:** changes muscle
memory everywhere at once. **Best for:** the owner working alone, fast.

## Direction 2 — Task-led workflow (guided, fewer screens)

**Philosophy.** Most work is a handful of repeat journeys.

- Four journeys become the top level: **Create a listing** (research → draft →
  approve → submit → live), **Fulfil orders** (order → buy → ship → return),
  **Check money** (sales → profit → costs), **Advertising** (read-only, Rule 8).
- Each step shows only the decision it needs; the next action is always one
  obvious button; hand-offs are links, not "go and find the SKU".
- Staff with restricted permissions see only their journeys (the permission
  table already knows which).

*Listings + PDP:* the PDP gains Approve/Hold (it is the only editor now, and
every hint already says "Approve" — audit UX #5). *Orders:* supplier purchase
and tracking recorded in the row. *Money:* one "where do costs live" answer.

**Cost:** medium-high (navigation restructure; screens mostly reused).
**Risk:** power features must stay reachable. **Best for:** adding staff.

## Direction 3 — Decision dashboard (exception-first)

**Philosophy.** The app tells you what changed and what needs a decision.

- A **morning round** (Daily exists, 5th in Reports) becomes the home screen:
  every finding links to the exact row that fixes it, ranked by money at risk.
- Money screens lead with one reconciled figure and drill down.
- Everything else stays where it is, one click away.

*Listings + PDP:* reached from findings ("3 listings Amazon refused"), not
browsed. *Orders:* "late to ship", "unpaid supplier", "no tracking" as
findings. *Sales/P&L:* the reconciled figure plus what moved it.

**Cost:** lowest (a new home screen + links; existing screens kept).
**Risk:** needs the checks behind each finding to be trustworthy (six Daily
checks can never run today). **Best for:** checking the business quickly.

---

## Recommendation (Claude's, not a decision)

**Direction 3 first, built on the context bar from Direction 1.** Reasons:
it is the cheapest to reach, it keeps every screen the owner already knows,
and the context bar fixes the most dangerous class of problem found in this
run (account/marketplace confusion — Milestones 2-3 fixed the code; the screen
still does not *show* it consistently). Direction 2's PDP Approve/Hold can be
done on its own at any time.

## What the design system (Milestone 8) would then fix, whichever is chosen

Safe to do first, and visible only as consistency (proposal, not done):

1. **One token set** for the shell: fold `--muted/--ink2`, `--green/--ok` into
   one name each; define the four variables used but never defined (`--fg2`
   has no fallback, so bookmark chips inherit colour); keep PDP/PPC scoped sets
   but derive them from the shell tokens. Drawer hex stays (owner's decision).
2. **Type scale actually used**: `--fs-*` exists and is used twice; move the 32
   CSS sizes and the ~300 half-pixel inline sizes onto it.
3. **One button family per role** (primary / secondary / danger / chip), from
   the 7 primaries and 4 dangers in use.
4. **One overlay system** (`.modalwrap` + `dialog.js`) with a focus trap and
   Escape, replacing the ≥8 overlay kinds.
5. **One status/empty/error/loading component set** (pageui.js `uiEmpty`,
   `motion.js` skeletons exist).

## Decisions needed from the owner

1. Which direction (1, 2, 3, or the recommended 3 + context bar)?
2. May the PDP get Approve/Hold buttons (audit UX #5)?
3. Currency symbols for Canada/Mexico/Singapore/Australia: money.js says "C$",
   "MX$", "S$", "A$" (a documented choice); marketplaces.js and seven screens
   say a bare "$" -- or "£" for anything not US/EU (Sales, P&L, PPC, repricer).
   One answer needs choosing, then every screen moved onto money.js. Tried in
   Milestone 5 and REVERTED after the UI review: changing one table alone made
   the tiles disagree with Sales.
4. Should inline price/stock edits on live listings ask for confirmation (they
   change Amazon in one step today)? Deliberately NOT changed in this run.
