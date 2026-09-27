---
name: start-task
description: How every AltaScraper task begins - read the task (usually read.txt in the main checkout), check git state and in-flight work, classify the task, create an isolated worktree from origin/main, take the test baseline, do the Rule 12 audit, and stop for approval when the plan touches more than 2 files or changes behaviour. Use at the start of any new task, including "read read.txt".
---

# start-task

**Problem it solves:** tasks starting on a stale branch, on main, in the wrong
worktree, or without a baseline to tell regressions from old failures.

**Modifies files:** creates a branch/worktree, writes the baseline and a plan
into `<main checkout>/active/`, and an entry in `<main checkout>/current-work.md`.
Never edits application code.

## Inputs
The owner's message, and usually `<main checkout>/read.txt` (the task inbox).

## Procedure
1. **Read the task in full.** If it is unclear, ask ONE specific question and
   stop (CLAUDE.md Rule 11).
2. **Where am I?** `git branch --show-current`, `git status --short`,
   `git worktree list`, `git fetch origin`, then
   `git rev-list --left-right --count origin/main...HEAD`.
   Read `current-work.md` and the relevant part of `docs/known-issues.md`.
3. **Classify:** UI / backend / Amazon API / account scope / new feature /
   refactor / deployment / maintenance / question-only. A question-only task
   needs no branch: answer and stop.
4. **Separate** (memory: ask-before-changing-existing-behaviour):
   ALREADY DOES (cite file/function) / NEEDS YOUR INPUT / WOULD CHANGE
   BEHAVIOUR / PURE ADDITION.
5. **Worktree from origin/main** (never local `main`, never the main checkout's
   branch): `& $g worktree add --no-track -b <type>/<short-name> D:\AltaScraper-wt\<short-name> origin/main`.
   Branch types: fix/, feature/, ui/, refactor/, docs/, chore/.
   All further work happens in that directory.
6. **Baseline:** in the new worktree, before any edit:
   `py -3.11 run_tests.py > <main checkout>\active\test-baseline-<branch>.txt`
   (about 5-10 minutes; run it in the background while reading code).
   Expected on a clean worktree: about 28 failures (docs/known-issues.md "Tests").
7. **Rule 12 audit:** search the whole repo for every place handling the
   concept(s) involved; list them.
8. **Route:** bug -> `investigate`; UI -> `ui-change`; Amazon rejection ->
   `amazon-schema-first`; refactor -> `refactor-move`; maintenance ->
   `project-maintenance`; security -> `security-review`.
9. **Plan gate:** if the change touches more than 2 files or changes existing
   behaviour, write the plan to `<main checkout>/active/plan-<branch>.md`,
   show it in plain English, and wait for the owner's approval (CLAUDE.md Rule 7).
10. **Record** in `current-work.md`: branch, worktree path, task (one line),
    status "in progress", waiting-on.

## Output
Classification, the ALREADY/INPUT/CHANGE/ADDITION split, the worktree path and
branch, the baseline file path, and either "proceeding" or the plan awaiting
approval.

## Persist afterwards
current-work.md entry; baseline and plan in active/.
