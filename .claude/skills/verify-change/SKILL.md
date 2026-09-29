---
name: verify-change
description: AltaScraper's mandatory check after edits and before any commit or push - compile, node --check, deleted-function check across changed files, relevant tests vs the baseline, full suite before a push, CLAUDE.md wording check. Use after every batch of edits (CLAUDE.md Rule 3) and whenever about to say something is fixed.
---

# verify-change

**Problem it solves:** "fixed" being claimed without evidence, regressions
hidden among ~28 known baseline failures, and a scope check that only covered
two files.

**Modifies files:** no (reads and runs checks only). Delegate the running to
the `qa-runner` agent when the output would be long.

## Inputs
- worktree path (repo root; normally `D:\AltaScraper-wt\claude-environment`)
- the **task base**: the commit recorded by `start-task` (HEAD when the task
  began). On the long-running branch, never diff against origin/main for "what
  this task changed" — that would include every earlier task.
- what changed: `git status --short` and `git diff --name-only <task-base>`
- the baseline file: `active/test-baseline-<short-base-sha>.txt` (worktree)
  (made by `start-task`; if missing, say so and make one before judging
  failures — never by resetting or stashing the work)

## Procedure
Run from the repo root. `$g` = the git.exe from CLAUDE.md Rule 2.

1. **Syntax** (the hook already did each saved file; repeat for the set):
   - each changed .py: `py -3.11 -m py_compile <file>`
   - each changed .js: `node --check <file>` (parse only)
2. **Deleted functions:** `py -3.11 .claude/skills/verify-change/scope_check.py --base <task-base>`
   REMOVED must be empty, or each removal explained (a faithful move with the
   new location, confirmed by the owner if not already agreed).
3. **Re-read the diff:** `& $g diff <task-base>` — does it change exactly what was intended?
   Anything touching Rule 1 (payload), Rule 8 (bids), Rule 14 (account scope)?
   If so, the matching agent must review it.
4. **Relevant tests:** `py -3.11 .claude/skills/verify-change/relevant_tests.py --changed --base <task-base>`
   then run each (`py -3.11 <test>.py` / `node <test>.js`) or
   `py -3.11 run_tests.py <filter>`.
5. **Full suite** before any push, or when CLAUDE.md, run_tests.py,
   dashboard.py, data/db.py, templates/dashboard.html or more than about 40
   tests are involved: `py -3.11 run_tests.py`.
6. **Compare with the baseline.** For every failing file: REGRESSION (passed in
   baseline), BASELINE (same failure before), DATA (needs real config/DB — see
   docs/known-issues.md "Tests"), SOURCE-TEXT PIN (a literal the diff moved),
   ENV (startup-speed timing, parallel run). In a clean worktree, a DATA
   failure is re-run in the main checkout only if the owner's data is needed
   to judge it — never modify the main checkout to do so.
7. **CLAUDE.md changed?** `py -3.11 .claude/skills/verify-change/claude_md_check.py`
   (the real test cannot reach its wording checks without data).
8. **UI changed?** Follow the `ui-change` skill's verification states too.
9. **Next, by review tier** (CLAUDE.md Rule 16): trivial harmless edits stop
   at step 1. Every meaningful change continues with the `qa-runner` agent
   (steps 4-6 with the full output kept out of the conversation) and then the
   `change-reviewer` agent. High-risk changes also get their specialist
   (listing-payload-guardian / account-scope-reviewer / security-review)
   BEFORE this skill. Do not run specialists the change does not need.

## Output (report to the owner, CLAUDE.md Rule 3/5)
- plain English: what was checked and whether it is safe
- compile: pass/fail per file; scope: REMOVED / ADDED per file
- tests: files run, passed, failed; regressions listed; baseline/data failures
  named as such
- what was NOT verified and why

## Persist afterwards
- a new baseline after merging to main is taken by the next `start-task`
- a newly discovered data-dependent or drifted test -> docs/known-issues.md "Tests"
