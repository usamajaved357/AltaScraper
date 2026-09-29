---
name: update-context
description: AltaScraper's context-maintenance protocol - at the end of every meaningful task, sort what was learned into the right place (architecture, design system, known issues, decisions, changelog, current work, active/) and propose - never silently make - changes to CLAUDE.md, skills, agents or hooks. Use at the end of every task that changed code, found a fact, or made a decision.
---

# update-context

**Problem it solves:** knowledge lost between sessions, the same fact kept in
three places, and docs that drift from the code.

**Modifies files:** docs/architecture.md, docs/known-issues.md,
docs/changelog.md, docs/design-system.md (observed facts), docs/decisions.md
(recording decisions the owner stated), `<main checkout>/current-work.md`,
`active/` (worktree, git-ignored). Proposes, but does not make, changes to CLAUDE.md,
skills, agents, hooks, .gitignore, .dockerignore.

## Procedure
Ask each question about the task just finished:

| Did I find... | Goes to | Automatic? |
|---|---|---|
| a durable fact about how the code works | docs/architecture.md | yes |
| a UI fact (pattern, class, layer, breakpoint) as it exists | docs/design-system.md | yes |
| a new UI convention to follow from now on | docs/decisions.md + design-system.md [decided] | owner approval |
| a decision the owner made (quote him) | docs/decisions.md | yes (records his words) |
| an unresolved bug / blocker / baseline test failure | docs/known-issues.md with CONFIRMED / READ / BLOCKED | yes |
| a fix that deployed | remove from known-issues; line in docs/changelog.md | yes |
| in-flight state (branch, waiting on whom) | current-work.md | yes |
| temporary output (traces, captures, screenshots, plans) | active/ | yes |
| a reusable procedure or a correction to one | a skill edit | propose |
| a durable project rule | CLAUDE.md | propose; owner approval |
| a doc that is wrong or obsolete | fix it now if it is a fact file; else flag | facts yes, rules propose |

Rules:
- One fact, one home. Link, don't copy. If the same fact is already elsewhere,
  update that place.
- Code wins: when a doc disagrees with the code, correct the doc in the same task.
- Never write a guess as a fact; mark READ vs CONFIRMED.
- Keep CLAUDE.md free of history; dated narratives go in decisions/changelog.
- Memory notes (the user's auto-memory) are not the project record: project
  facts go in docs/; memory is for personal preferences about how to work.
- Keep entries short: a few lines each, with a file or function name to search.
- Governance files (CLAUDE.md, .claude/settings*.json, hooks, agents, skills)
  are never edited as part of context upkeep. Write the proposal (exact text
  and reason) in the task report; only after the owner approves, make the
  edit — the `guard_rules` hook will then ask him to confirm it once more.

## Output
A short list for the owner: "Updated: ... / Proposed for your approval: ...".

## Persist afterwards
The edits themselves; commit docs changes with the task's branch (they are
tracked), except current-work.md and active/ (untracked, shared).
