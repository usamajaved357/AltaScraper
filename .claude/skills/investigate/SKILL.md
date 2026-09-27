---
name: investigate
description: AltaScraper's standard bug investigation - reproduce, find the entry point, trace UI -> JS -> fetch -> route -> guard -> domain -> external API -> response -> redraw, find the root cause, classify, propose. Use for any reported misbehaviour before changing code ("when I click Submit something goes wrong", wrong numbers, wrong account, stale screen).
---

# investigate

**Problem it solves:** speculative fixes made before the flow is understood,
and fixes that treat a symptom.

**Modifies files:** no application files. Writes a trace/notes file in
`<main checkout>/active/` and may add a FAILING test in the development worktree once
the cause is known (step 7).

## Inputs
The owner's report (often with a screenshot from app.altascraper.com), the
account and marketplace, the screen and view (table / detailed / card / PDP).

## Procedure
1. **Is it deployed?** The owner tests the live site. Check whether the
   relevant fix is on origin/main (`git merge-base --is-ancestor <sha> origin/main`)
   before re-reading code. Read the screenshot for which account, view and tab.
2. **Known already?** Search docs/known-issues.md and docs/decisions.md (a
   "bug" may be a decided behaviour, e.g. the drawer's hex colours, profit
   showing unknown rather than 0, an SP-API role 403).
3. **Reproduce**, cheapest first: a Flask test-client call; a JS vm-sandbox run
   of the renderer (as the existing tests do); the local app
   (`py -3.11 dashboard.py`); a read-only probe for Amazon (`amazon-schema-first`).
   If it cannot be reproduced, say so and say what would be needed.
4. **Trace** with the `tracer` agent (give it the action, account, and what
   goes wrong). Output: numbered hops with file:line.
5. **Root cause:** the first hop where behaviour departs from intent. Ask "why"
   until the answer is a code decision, a data fact, or an outside blocker.
6. **Classify:** UI / state / rendering / routing / backend logic / data /
   account scope / Amazon API / config / blocked outside code.
7. **Pin it:** write a test that fails because of the bug (in the development
   worktree), unless the bug is outside the code.
8. **Propose** in plain English (CLAUDE.md Rule 6 format): what happened, why,
   the fix, what else it touches (Rule 12 audit). More than 2 files or a
   behaviour change -> wait for approval.
9. After implementation, follow the review tier for the change (CLAUDE.md
   Rule 16): the specialist(s) if high risk, `verify-change`, `qa-runner`,
   `change-reviewer`; for UI, the `ui-change` order. Then `update-context`.

## Output
`<main checkout>/active/investigation-<topic>.md`: symptom, reproduction,
trace, root cause, classification, proposed fix, open questions. A summary to
the owner in plain English first.

## Persist afterwards
Unresolved cause -> docs/known-issues.md (with CONFIRMED/READ level).
New architecture fact -> docs/architecture.md. A pattern worth reusing ->
propose a skill change (owner approval).
