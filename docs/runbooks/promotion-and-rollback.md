# Runbook: promote claude-environment-setup to main, and roll it back

Written 29 Sep 2026 on the owner's instruction: preserve production as an
immutable tag and a permanent legacy branch, keep the development branch
separate, and promote only with **normal, history-preserving git** after he
explicitly approves. Companion to backup-and-parallel-test.md (data backup §2,
parallel test §3) and docs/deployment-manifest.md.

**Every step marked OWNER is a push, a merge, a deploy or an action on the live
server. Claude does none of them without the owner's explicit instruction in
the conversation (CLAUDE.md Rule 2).** Nothing in this file rewrites history:
no `reset --hard` on main, no force-push, no rebase.

## 0. The preserved production

| Ref | Points at | Where |
|---|---|---|
| tag `prod-backup-2026-09-29` (annotated) | **0e5529e953fd5e4d9b421b0f9f1c5b4fb0a8afc3** | local; GitHub after §1 |
| branch `legacy/production-2026-09-29` | 0e5529e953fd5e4d9b421b0f9f1c5b4fb0a8afc3 | local; GitHub after §1 |
| `origin/main` today | 0e5529e953fd5e4d9b421b0f9f1c5b4fb0a8afc3 | GitHub (Render deploys it) |
| sealed copy `production-0e5529e.bundle` (SHA-256 7F2861A221BAFC6E191CB1AF7918B2BECCAE9BF6F9DB5C3991F89020A1FD3204) | tag + branch, full history | `D:\AltaScraper-wt\claude-environment-devdata\release-backup-2026-09-29\` (outside git) |

Never move, delete or re-point these two refs. Check at any time:
`git rev-parse "prod-backup-2026-09-29^{commit}" legacy/production-2026-09-29`
must both print 0e5529e953fd5e4d9b421b0f9f1c5b4fb0a8afc3.

Git itself does not stop someone deleting a local tag. "Immutable" is made real
in three layers: the bundle file (an independent copy, verified with
`git bundle verify`), the refs on GitHub (§1), and GitHub protection on them
(§1 step 3).

## 1. Put the backup on GitHub — OWNER authorises (a push; production unaffected)

Adds two refs; does not change main and does not deploy.
```
git push origin refs/tags/prod-backup-2026-09-29
git push origin legacy/production-2026-09-29
git ls-remote origin refs/tags/prod-backup-2026-09-29 refs/heads/legacy/production-2026-09-29
```
3. OWNER on GitHub → Settings → Rules → Rulesets: a tag ruleset for
   `prod-backup-*` and a branch ruleset for `legacy/*`, both blocking
   deletion, update and force-push.

## 2. Before promotion (all must be true)

1. Owner has tested locally and says so.
2. Automated verification is green at the commit being promoted: full suite,
   browser smoke desktop + phone, dispatch check (release report
   active/release-report-2026-09-29.md, re-run if the branch moved).
3. A fresh live `/data` backup taken **immediately before** the merge
   (backup-and-parallel-test.md §2), copied off the server, integrity `ok`.
4. `ship_confirm_enabled` is NOT true in live config (Dispatch to Amazon stays
   off until the owner approves a live send).
5. Record the old deploy: Render → service → Deploys shows 0e5529e live.
6. The owner writes, in the conversation, that the promotion is approved. If
   he orders it before the branch has run in production, Claude says aloud that
   Rule 2's waiting period is being waived on his instruction.

## 3. Promotion — OWNER authorises (a merge and a push = the production deploy)

A merge commit, even though main could fast-forward, so the promotion is ONE
commit that can be reverted as a unit and history shows where it happened.
```
git fetch origin
git ls-remote origin refs/heads/main          # must still be 0e5529e...; if not, STOP and re-plan
git checkout -b promote-2026-XX-XX origin/main   # in a clean clone or new worktree, not this one
git merge --no-ff claude-environment-setup -m "Promote claude-environment-setup to production"
git rev-parse "HEAD^{tree}" claude-environment-setup^{tree}   # the two must be equal
git push origin HEAD:main
```
Record the merge commit's hash (called **M** below) in docs/changelog.md.
Render then builds main. Watch: deploy log green, `/healthz` 200, sign-in,
one read on each screen, no errors in the server log for ten minutes.
claude-environment-setup stays as it is; development continues on it.

Rehearsed 29 Sep 2026 in a throwaway clone: merge tree == branch tree; parents
are 0e5529e and 5e24b36.

## 4. Rollback — pick the lightest that works

### 4a. Instant, no git change (first minutes, code problem only)
Render → service → Deploys → the previous 0e5529e deploy → "Rollback".
Production is back on the old code in the time of one restart. Render may
switch off auto-deploy; main still holds M, so the NEXT push redeploys the new
code — follow with 4b before any other push.

### 4b. Normal rollback, history preserved — OWNER authorises (a push)
```
git fetch origin
git checkout -b rollback-2026-XX-XX origin/main
git revert -m 1 <M> --no-edit             # -m 1 = keep production's side
git diff --stat 0e5529e953fd5e4d9b421b0f9f1c5b4fb0a8afc3 HEAD   # must print nothing
git push origin HEAD:main
```
Main's files are then exactly production's 0e5529e; the merge stays in
history. If commits landed on main after M, revert those first (newest first),
or revert M alone and accept they stay.
Rehearsed 29 Sep 2026: after the revert, tree == 0e5529e's tree exactly, and
M is still in history.

### 4c. Data
The new build only ADDS tables and columns. Rehearsed locally 29 Sep 2026:
the 0e5529e code, started on data the new build had written to (new tables,
a purchase record, a tracking record), boots, integrity `ok`, and 15 main
routes answer exactly as under the new build. So a code rollback normally
needs NO data restore. Not verified: the old build reading a `users.json`
the new build has rewritten (Team permissions version 3); check sign-in and
Team right after a rollback.
Restore `/data` from the §2 pre-promotion backup ONLY if the old build
mishandles something: stop the service, replace `/data` with the backup, start
it. Everything recorded since the backup (orders marked bought, tracking,
settings, team changes) is lost — say so to the owner first.

### 4d. Last resort, rewrites history — OWNER must order this exact step
`git push --force-with-lease origin prod-backup-2026-09-29^{commit}:main`
Only if 4a and 4b are impossible. It removes M from main's history; every clone
must re-sync.

## 5. Promoting again after a 4b rollback
Git regards M as already merged; merging the branch again brings only
commits made after M. Restore the rest by reverting the revert:
`git revert <revert commit> --no-edit`, then merge the newer branch commits
as in §3. Rehearsed 29 Sep 2026: the tree then equals the branch's tree.
