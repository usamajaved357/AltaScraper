---
name: ship
description: Commit, push and deploy for AltaScraper in three gated stages - (A) commit in the house style after the never-commit check, (B) push the branch only on the owner's instruction, (C) deploy to production (fast-forward origin/main, which Render builds) only on an explicit merge/deploy instruction, then confirm the new build is live. Use at the end of a task and whenever the owner says push, merge or deploy.
---

# ship

**Problem it solves:** secrets or junk committed, pushes nobody asked for,
deploys that were never confirmed live, and commit messages that lose the
owner's reason.

**Modifies files:** git state only (commits, pushes). Updates
docs/changelog.md after a deploy and current-work.md.

## Inputs
The task branch and worktree, the `verify-change` result, and the owner's exact
words if he asked to push, merge or deploy.

## Procedure (three gated stages)

### Stage A — Commit (normal end of a task)
1. The review tier for the change is complete (CLAUDE.md Rule 16): for any
   meaningful change `verify-change`, `qa-runner` and `change-reviewer` have
   run and their findings are fixed or stated; failures are stated, not hidden.
2. `& $g status --short`: nothing from the never-commit list (CLAUDE.md Rule 2);
   the guard_commit hook enforces it, but look anyway. Stage files by name, not
   `git add .`, unless status shows only intended files.
3. Message, house style (write it to a file and use `git commit -F <file>`;
   double quotes inside a PowerShell here-string break native arguments):
   - subject: the outcome in plain English, often the symptom fixed
     ("A handling-time change was recorded against the wrong account")
   - body: the owner's words quoted verbatim when the task came from him; the
     root cause(s), numbered; what changed and where; the Rule 1 / 4 / 12 notes
     (the Rule 12 audit); tests added or re-pinned and why; anything not verified.
   - no secrets, no customer personal data.
4. Commit locally on the current development branch (`claude-environment-setup`).
   Never on main. Committing is routine; it needs no extra approval.

### Stage B — Push the branch (only when the owner says to push)
`& $g push -u origin <branch>` (set `$env:GIT_TERMINAL_PROMPT=0`). The
guard_push hook asks for confirmation. Pushing a branch does not deploy.
No `gh` CLI: hand the owner the PR link git prints if he wants one.

### Stage C — Deploy (only on an explicit "merge" / "deploy" in this conversation)
1. Say out loud: CLAUDE.md Rule 2 asks for production confirmation before a
   merge; it is being waived on the owner's instruction.
2. `& $g fetch origin`; the branch must contain origin/main
   (`& $g merge-base --is-ancestor origin/main <branch>`). If it does not,
   STOP and tell the owner: bringing origin/main in (merge or rebase) is his
   decision. Only after his explicit instruction, do it and re-run
   `verify-change` on the resulting tree. Also tell him exactly which commits
   the push would put on main (`git log --oneline origin/main..<branch>`) —
   on the long-running branch that includes every earlier task and the
   Claude Code environment commits.
3. Fast-forward: `& $g push origin <branch>:main` (the hook asks; it says
   PRODUCTION DEPLOY).
4. **Confirm the swap from outside**: `/healthz` only says "ok". Poll a static
   file the push added or changed on https://app.altascraper.com (a new file
   404 -> 200; a changed file: compare a distinctive string), every 30 s, for
   up to about 3 minutes. If nothing static changed, say the swap is
   unverified and give the owner a signed-in check.
5. Report: commit(s), deploy confirmed or not, what he should see.

## Persist afterwards
docs/changelog.md: one line per deploy (date, commit, what he will notice).
current-work.md: branch status (committed / pushed / deployed).
docs/known-issues.md: remove entries the deploy fixed.
