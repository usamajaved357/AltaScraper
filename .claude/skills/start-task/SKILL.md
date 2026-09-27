---
name: start-task
description: How every AltaScraper task begins - in the PRIMARY development worktree D:\AltaScraper-wt\claude-environment on branch claude-environment-setup (no new worktree, no branch switch). Read the task (usually read.txt in the main checkout), check git state and in-flight work, record the task base commit, classify the task and its review tier, take the test baseline, do the Rule 12 audit, and stop for approval when the plan touches more than 2 files or changes behaviour. Use at the start of any new task, including "read read.txt".
---

# start-task

**Problem it solves:** tasks started on the wrong branch or in the wrong
folder, without a baseline to tell regressions from old failures, or with no
record of where the task began.

**Where work happens (owner's decision, 27 Sep 2026):**
`D:\AltaScraper-wt\claude-environment`, branch `claude-environment-setup`, is
the primary long-running development branch. Ordinary tasks stay there:
- do NOT create a new worktree or branch
- do NOT switch branches
- do NOT reset, rebase, cherry-pick, stash-and-drop or otherwise discard work
- do NOT modify `D:\AltaScraper` (except the shared untracked
  `current-work.md` and `active/`) or origin/main
A new worktree/branch is created ONLY when the owner explicitly asks for
isolated experimental work.

**Modifies files:** writes the baseline and a plan into
`<main checkout>/active/` and an entry in `<main checkout>/current-work.md`.
Never edits application code itself.

## Inputs
The owner's message, and usually `<main checkout>/read.txt` (the task inbox).

## Procedure
1. **Read the task in full.** If it is unclear in a way that changes what gets
   built, ask ONE specific question and stop (CLAUDE.md Rule 11).
2. **Where am I?** `git rev-parse --show-toplevel`, `git branch --show-current`,
   `git status --short`. The answer must be `D:/AltaScraper-wt/claude-environment`
   on `claude-environment-setup`. If not, STOP and tell the owner — do not switch.
   If the tree has uncommitted changes from earlier work, say so and ask before
   mixing them into this task. Read `current-work.md` and the relevant parts of
   `docs/known-issues.md`, `docs/architecture.md`, `docs/decisions.md`.
   (To compare with production without touching the shared .git, use
   `git ls-remote origin refs/heads/main`; no `git fetch` unless asked.)
3. **Record the task base:** `git rev-parse HEAD` at this moment. Every later
   check of "what this task changed" diffs against it (verify-change,
   qa-runner, change-reviewer), not against origin/main — the branch carries
   earlier tasks' commits.
4. **Classify:** UI / backend / Amazon API / account scope / new feature /
   refactor / deployment / maintenance / question-only. A question-only task
   needs no baseline: answer and stop. Also pick the **review tier** (CLAUDE.md
   Rule 16: trivial / meaningful / UI / high risk) and name the specialists it
   needs, and only those.
5. **Separate** (memory: ask-before-changing-existing-behaviour):
   ALREADY DOES (cite file/function) / NEEDS YOUR INPUT / WOULD CHANGE
   BEHAVIOUR / PURE ADDITION.
6. **Baseline** (meaningful, UI and high-risk tiers), before any edit, in this
   worktree: `py -3.11 run_tests.py > <main checkout>\active\test-baseline-<short-base-sha>.txt`
   (about 5-10 minutes; run it in the background while reading code). If a
   baseline for the same base commit already exists, reuse it. Expected here:
   about 28 failures (docs/known-issues.md "Tests").
7. **Rule 12 audit:** search the whole repo for every place handling the
   concept(s) involved; list them.
8. **Route:** bug -> `investigate`; UI -> `ui-change`; Amazon rejection ->
   `amazon-schema-first`; refactor -> `refactor-move`; maintenance ->
   `project-maintenance`; security -> `security-review`.
9. **Plan gate:** if the change touches more than 2 files or changes existing
   behaviour, write the plan to `<main checkout>/active/plan-<topic>.md`,
   show it in plain English, and wait for the owner's approval (CLAUDE.md Rule 7).
10. **Record** in `current-work.md` under the claude-environment-setup block:
    the task (one line), task base sha, status "in progress", waiting-on.

After implementation the task continues with the review tier, `update-context`,
and `ship` stage A (a local commit on this branch).

## Output
Confirmation of worktree/branch, the task base sha, classification and tier,
the ALREADY/INPUT/CHANGE/ADDITION split, the baseline file path, and either
"proceeding" or the plan awaiting approval.

## Persist afterwards
current-work.md entry; baseline and plan in active/.
