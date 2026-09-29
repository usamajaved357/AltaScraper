---
name: build-feature
description: Autonomous feature development for AltaScraper - the owner states an outcome in plain English ("add an employee performance screen") and Claude carries it through understand, investigate, acceptance criteria, plan, baseline, sliced implementation, tests, browser verification, independent review, fixes, documentation and local commits, inside the owner's bounded-autonomy levels (docs/product-operating-model.md). Orchestrates the existing skills and agents; it is not a second process. Use when the owner asks for a feature or a product outcome rather than a single fix.
---

# build-feature

**Problem it solves:** a feature request used to need the owner to restate the
process, approve every multi-file plan, and chase each step. The owner delegated
this on 29 Sep 2026 (read.txt, "Full Autonomous Feature Development") within
four levels of autonomy. This skill is the procedure; the operating model is
`docs/product-operating-model.md`.

**Modifies files:** application code, tests and docs in the worktree; plans,
baselines and reports in `active/`; `current-work.md`. Never `D:\AltaScraper`
otherwise, never origin/main, never pushes.

## 0. Autonomy level — decide first, per slice
- **L1** engineering/UI/reports/refactors, **L2** business/data logic under
  ESTABLISHED rules: proceed without waiting. The plan gate of `start-task`
  step 9 is satisfied by writing the plan to `active/` (the owner delegated it).
- **L3** real external writes, money, Amazon actions, supplier purchase,
  dispatch, price changes, permission changes: build it, mock it, test it, and
  leave the real action switched off / unwired until the owner approves THAT
  action. Say so in the report.
- **L4** push, merge, deploy, destructive migration, anything irreversible:
  stop and ask. Always.
- A rule is ESTABLISHED only if CLAUDE.md, docs/decisions.md, a test or the
  owner's written words say it. Otherwise it is a decision needed: take the
  conservative, reversible option or defer the slice, record it, continue.

## 1. Understand and investigate
1. `start-task` steps 1-7 (where am I, task base sha, classify, tier, baseline,
   Rule 12 audit). Read `docs/product-operating-model.md`,
   `docs/architecture-audit-2026-09-29.md` (target shape), `docs/decisions.md`
   and the relevant `docs/known-issues.md` entries.
2. Find what ALREADY exists (code, tables, routes, screens, permissions). Use
   `tracer` for any flow that crosses UI -> route -> domain -> data. Never
   rebuild what exists; extend it.

## 2. Acceptance criteria and plan -> `active/feature-<name>.md`
- Acceptance criteria as observable checks (what a user sees / what a request
  returns), including: account isolation (two tabs, two accounts), permission
  (who may and may not), loading / empty / error / after-account-switch states,
  phone width, keyboard.
- Data model: new tables through `data/db.py` SCHEMA + `_migrate`, additive
  only (a destructive migration is L4). Nothing sensitive stored (no passwords,
  keys, tokens, credentials, secret config).
- Architecture: routes -> domain -> data/api (the audit's target). No new
  logic in `dashboard.py` or the listing engine (Rule 7). New routes get an
  `auth/guard.py` RULES entry when they are sensitive (Rule 14).
- Slices: smallest shippable pieces, each independently testable and committable.
- Decisions needed: listed, each with the conservative default chosen.

## 3. Per slice
1. Implement (reuse existing helpers: `routes/scope.py`,
   `domain/request_account.py`, `reqscope.js`, `docs/design-system.md`).
2. Tests: a test for each acceptance criterion the slice covers; for changed
   behaviour, prove the test FAILS on the old code (stash the source file, run,
   restore). Tests never touch real credentials or data, never call Amazon.
3. `verify-change` (syntax, Rule 3 scope check, relevant tests).
4. Browser: `py -3.11 tools/browser_smoke.py` (two tabs, a11y, horizontal
   scroll, console errors). For a new screen add its checks to the harness.
   Visual claims only with a screenshot actually looked at.
5. Full suite `py -3.11 run_tests.py`: no new failure against the baseline.
6. Independent review: `change-reviewer`, plus ONLY the specialists the slice
   touches (`account-scope-reviewer`, `ui-reviewer`,
   `listing-payload-guardian`, `security-review`) — CLAUDE.md Rule 16.
7. Fix every real finding; retest; record anything deferred with evidence.
8. `update-context`; local commit (`ship` stage A), one slice per commit.

## 4. Bugs met on the way (read.txt bug policy)
Introduced by this work -> fix before commit. Security / account / data
corruption -> urgent. Existing bug blocking this feature -> reproduce, test,
fix, separate commit. Unrelated -> record in docs/known-issues.md with
evidence; do not derail.

## 5. Validate the workflow itself
If a step needed a manual engineering instruction from the owner, or a check
missed a real defect, improve this skill (or the agent/tool involved) and say
so in the report. Never weaken a safety rule to make autonomy look successful.

## Output
The operating model's report (§6): completed, tested, review findings, bugs
fixed/deferred, decisions needed, L3/L4 items waiting, commits, and what was
NOT pushed, merged or deployed.
