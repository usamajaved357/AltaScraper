# How AltaScraper is developed — the operating model

The authoritative description of how the owner gives work and how Claude carries
it out. It gathers what the owner has already written — the master handoff
(`ALTASCRAPER_MASTER_HANDOFF.md`, 28 Sep 2026), the continuation instruction
(read.txt, 29 Sep 2026) and CLAUDE.md — into one place. It adds no business
rule of its own; where it and CLAUDE.md differ, CLAUDE.md wins and this file is
corrected.

## 1. What the owner does, what Claude does

The owner states an **outcome** in plain English ("Add an employee performance
screen", "Orders should show which supplier to buy from"). The owner decides
what AltaScraper should accomplish and reviews finished work and open decisions.

Claude turns the outcome into working, tested, reviewed, documented, locally
committed software, using the process in §3, without being told the
engineering, account-scope, Amazon, UX, testing or documentation rules again —
they live in CLAUDE.md, `docs/` and `.claude/`.

## 2. Bounded autonomy (owner, read.txt 29 Sep 2026)

| Level | What | Claude may |
|---|---|---|
| 1 | Normal engineering, UI, reports, refactors | do it autonomously |
| 2 | Business/data logic under rules already established (CLAUDE.md, docs/decisions.md, tests) | do it autonomously, with stronger tests (characterization first; a test that fails without the change) |
| 3 | Real external writes, money, Amazon actions, supplier purchase, dispatch, price changes, permission changes | build, mock and test it; **never execute** the real high-consequence action without the owner's approval for that action |
| 4 | Push, merge, deploy, destructive production migrations, irreversible actions | owner approval required, every time |

Always a hard stop, whatever the level: secret exposure; real spend or
purchase; destructive database migration; changing an undocumented business
rule; a blocking ambiguity that cannot be safely deferred.

**A missing, non-blocking owner decision does not stop the work**: take the
conservative, reversible option (or defer that slice), record it, continue
everything else, and list it under "Decisions needed" in the report.

**Never invent business rules.** A rule is established only if it is in
CLAUDE.md, docs/decisions.md, a test, or the owner's written words. Otherwise it
is a decision needed.

## 3. The feature workflow

`build-feature` (`.claude/skills/build-feature/SKILL.md`) is the procedure. It
reuses the existing skills and agents — there is no second process:

understand → investigate (`start-task`, `investigate`, `tracer`) → acceptance
criteria + plan (written to `active/`) → baseline (`run_tests.py`) → implement
in slices → test (a test per behaviour; `verify-change`) → browser verify
(`tools/browser_smoke.py`, screenshots where visual) → independent review
(`change-reviewer` + only the specialists the change needs, CLAUDE.md Rule 16)
→ fix findings → retest → document (`update-context`) → local commit (`ship`
stage A) → next slice.

## 4. Evidence

Labels: CONFIRMED BY TEST / CONFIRMED BY CODE READING / OBSERVED / LIKELY /
UNVERIFIED. "Works" only with the check that proved it. A behaviour change is
proven by running the new test against the old code too (it must fail there).
Visual claims need a screenshot that was actually looked at.

## 5. Where things live

| What | Where |
|---|---|
| Rules | `CLAUDE.md` |
| Architecture | `docs/architecture.md`, `docs/architecture-audit-2026-09-29.md` |
| Owner decisions | `docs/decisions.md` |
| Known problems | `docs/known-issues.md` |
| Engineering standards | `docs/engineering-standards.md` |
| UI system | `docs/design-system.md` |
| Product context | `docs/product-context.md` |
| In-flight work | `current-work.md` at the worktree root (untracked). The old checkout `D:\AltaScraper` is fully read-only — only its `read.txt` is read (docs/decisions.md, 29 Sep 2026) |
| Plans, baselines, reports | `active/` in the worktree (git-ignored) |

## 6. Reporting

Progress is not narrated between normal phases. At the end of a major piece of
work the report states: what was completed, what was tested, reviewer findings,
bugs fixed, bugs deferred, business decisions still needed, and what is safe to
do next — with commits listed and a plain statement of what was NOT pushed,
merged or deployed.
