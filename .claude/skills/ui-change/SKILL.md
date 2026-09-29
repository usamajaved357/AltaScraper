---
name: ui-change
description: AltaScraper's UI/UX engineering workflow - the seven questions, reuse of the existing design system, the interaction states to verify, the ui-reviewer hand-off and visual verification. Use for any change to static/js, static/css, templates/dashboard.html, or text the UI shows, and for any "looks wrong / behaves wrong on screen" task.
---

# ui-change

**Problem it solves:** inconsistent buttons/colours/states, full-page redraws
that lose focus, unsafe inline handlers, and UI claimed to work without being
looked at.

**Modifies files:** yes (Main Claude implements). The reviewer agent does not.

## Inputs
The request, the screen (Listings table/detailed/card, PDP tab, drawer, PPC,
Sales, ...), the account and marketplace, a screenshot if given.

## Procedure
1. **Answer the seven questions** in `active/ui-<topic>.md` (worktree):
   1. What is the user trying to accomplish?
   2. What happens now? (reproduce; or `tracer` / `ui-reviewer` mode B)
   3. What should happen?
   4. Which kind of problem: visual / behavioural / state / routing / data /
      rendering?
   5. Which existing component or pattern is reused? (docs/design-system.md
      sections 5-7; name the helper)
   6. Which interaction states must be verified? (step 4)
   7. What could regress? (step 5)
2. **Read** docs/design-system.md and the relevant owner rules in
   DESIGN_RULES.md (root). Check docs/decisions.md for decided UI choices.
3. **Implement** with the existing pattern. Rules: `jsArg()` for data in inline
   handlers; `esc()` for text; tokens not hex (drawer files excepted); the
   button family already on that screen; `uiEmpty` for a new empty state; an
   error never drawn as an empty state; reset or account-key any new global in
   `enterAccount`; call the right redraw. A NEW convention is proposed to the
   owner, not implemented.
4. **States to verify** (tick each, or say why not applicable):
   - loading / empty / error / success
   - one account, then after switching account and marketplace
   - table, detailed and card views; drawer vs PDP where both show it
   - 390px wide (mobile.css) and desktop
   - a SKU / text containing an apostrophe and `<`
   - long text (title, bullets), zero and unknown numbers ("unknown", not 0)
   - read-only workspace (`WS_READONLY`)
   - Escape key and overlay stacking (drawer 75, PDP 78, modal 90, dialog 9600)
5. **Regression risks to check:** CSS load order (docs/design-system.md §3);
   layer order; source-text/pixel tests pinning the old markup
   (`relevant_tests.py`); the ~58 `render()` callers; focus/caret loss.
6. **Review, in this order** (CLAUDE.md Rule 16, UI tier):
   1. `ui-reviewer` agent (mode A) on the diff; add `account-scope-reviewer`
      only if state, requests or caches changed.
   2. `verify-change` (syntax, scope check, relevant tests).
   3. `qa-runner` agent (tests vs baseline).
   4. `change-reviewer` agent (independent bug/regression review).
   Fix what they find and repeat the affected steps.
7. **Visual verification (when possible):** Playwright is installed locally.
   Start the app in the worktree (`py -3.11 dashboard.py`) and capture the
   affected states at 1280px and 390px into `active/screens/` (worktree),
   then LOOK at them. If the local app needs a login or has no data for that
   account, say "not visually verified" and why — never claim a visual check
   that did not happen. The owner verifies on app.altascraper.com after deploy.
8. `update-context`.

## Output
The seven answers, the state checklist with results, screenshots or the reason
there are none, the reviewer's findings and how each was handled.

## Persist afterwards
Observed UI facts -> docs/design-system.md. A convention the owner approved ->
docs/decisions.md + docs/design-system.md marked [decided].
