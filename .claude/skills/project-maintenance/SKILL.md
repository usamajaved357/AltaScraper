---
name: project-maintenance
description: Repeatable AltaScraper housekeeping audit - stale or contradictory docs, duplicated information, broken references, obsolete files/skills/agents, root clutter, temporary files, outdated commands, stale handoff docs, and CLAUDE.md vs actual behaviour. Produces a report; acts only on items the owner approves. Use on request or about weekly.
---

# project-maintenance

**Problem it solves:** drift. Docs, rules, memory and code slowly disagree;
the root folder fills with one-off files.

**Modifies files:** only after the owner ticks items in the report. Deleting or
archiving anything always needs approval, with the reason stated.

## Procedure (write findings to `<main checkout>/active/maintenance-<date>.md`)
1. **Broken references:** every file path, function and route named in
   CLAUDE.md, docs/*.md, .claude/agents/*.md and .claude/skills/*/SKILL.md
   still exists (search for each).
2. **Contradictions:** CLAUDE.md vs code (e.g. the never-commit list vs tracked
   files; command lines that no longer run); CLAUDE.md vs tests (run
   `claude_md_check.py`); docs vs code; docs vs memory notes; decisions marked
   superseded but still followed.
3. **Duplication:** the same fact in two docs, or in a doc and a memory note;
   pick the one home, link from the other.
4. **Stale state:** current-work.md entries whose branch is merged or gone
   (`git branch -a`, `git worktree list`); known-issues entries already fixed
   on origin/main; active/ files older than 14 days (list, don't delete).
5. **Obsolete tooling:** skills or agents no task used for a month, or whose
   instructions no longer match the code; hooks that fail when run with a
   sample input; permission rules that no longer match anything.
6. **Root clutter** (list with a recommendation each: keep / move to docs/specs
   / archive / delete): probe_*.py, PATCH_*.py, one-off migration scripts,
   mockup HTML, .docx/.pdf, `_merge_*`, `_archive`, tracked files that
   .gitignore says should be ignored (e.g. orbit_shots/), root shims no longer
   imported, stale handoff docs (REMAINING_FIXES_HANDOFF.md, PPC-BUILD-STATUS.md).
7. **Worktrees and branches:** list stale worktrees and local branches already
   on origin/main (never delete without approval; never delete unmerged work).
8. **Image contents:** anything large or non-runtime that `.dockerignore` lets
   into the Docker image.
9. **Tests:** baseline failures that have become permanent (propose a fix or a
   documented skip); test helpers copied into many files.

## Output
A table: item | finding | evidence | recommendation | risk if left. Then the
list of actions awaiting approval. Nothing is changed in this step.

## Persist afterwards
Approved actions are done on a `chore/maintenance-<date>` worktree branch;
removed items are listed in docs/changelog.md when they deploy; decisions in
docs/decisions.md.
