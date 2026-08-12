# AltaScraper UI redesign — design rules

Companion to the three HTML mockups (`1_dashboard.html`, `2_queue.html`, `3_detail.html`).
The HTML shows the **look and layout**; this file explains the **logic** so you match intent, not just pixels.

## How to use these files
- The mockups are a **layout + behaviour reference**. Match the structure, hierarchy, spacing feel, and interaction.
- **Use the app's OWN existing theme / CSS variables / component styles.** The `_tokens.css` values are illustrative stand-ins so the mockups render standalone — do NOT import them into the app or copy the hex values. Map each concept to the app's real styles.
- Every number/label in the mockups is placeholder. Wire real data; never ship fabricated counts.

## The one principle
**Show the judgment signals, hide the plumbing.** The user's job is to judge whether a generated listing is good and safe, then act. Surface what helps them judge (status, compliance, price, image count); tuck what they use rarely (delete, push-image, preview-raw, source, hold) into a `⋯` menu.

## Structure: three connected views
1. **Dashboard** — "what's the state of everything, what needs me today." The home screen.
2. **Queue** — compact rows, fast scanning, one action per row. Replaces the current listing grid.
3. **Detail** — clean, one primary button, plumbing under `⋯`. Replaces the current cluttered panel.
Connect them by click: dashboard metric/item → filtered queue → listing detail → back.

## Status = colour, always the same mapping
- **Needs review** → amber/warning
- **Blocked** (prohibited) → red/danger
- **Ready** → green/success
- **Live** → neutral/grey
Use ONE status pill per item. The pill IS the information — don't add redundant labels.

## The primary button changes with state (never show them all)
| State | Primary button |
|---|---|
| Needs review | Review |
| Blocked | See why (NEVER "Submit") |
| Ready | Submit |
| Live | View |
Auto-fix is the one common secondary in the detail view. Everything else lives in `⋯`.

## Warnings appear ONLY when real (the doormat lesson)
- Clean listing → a green "compliance clear" strip in detail; NOTHING on the row beyond a small green "clear".
- Flagged listing → a RED strip naming the SPECIFIC reason (e.g. "UK prohibited — Ofcom") + what's needed.
- **Never show an empty compliance panel on a clean listing.** No panel is the correct state when there's nothing to say. (This was a real bug — a coir/rubber doormat showed a compliance panel because of over-eager keyword matching. Clean = silent.)

## Compliance behaviour in detail view
- **PROHIBITED** → primary action is "See why", NOT Submit. Normal submit blocked. A separate, quiet, **logged** "Force list" exists (deliberate, not accidental).
- **GATED (needs docs)** → warn + show the required docs, but Submit is allowed (it's sellable with docs).
- Resolve status **per marketplace** (a 600mW FPV is UK-prohibited but US-legal). Never global.

## Voice / polish
- Sentence case everywhere. No Title Case, no ALL CAPS.
- Verb-first buttons: "Create listing", not "Submit"/"OK".
- Flat, calm, generous whitespace. No gradients/shadows beyond subtle card borders.
- Don't remove ANY existing capability — relocate it into `⋯`. Every current button still exists.

## Dashboard tiles (Stage 1) — use real data or omit
- Metric cards (need review / blocked / ready / live) — clickable → filtered queue.
- "Needs you first" — merged across ALL accounts, worst-first.
- "Compliance watch" — flagged this week, prohibited vs gated, + the "check a product before sourcing" (manual Shape-1 box).
- "Sync + account health" — per-account dot + last-sync; Sheelady = deactivated/red.
- "From your hunters" — ONLY if the data exists; otherwise omit and say so. Never fabricate.
