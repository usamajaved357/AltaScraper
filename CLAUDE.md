# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Standing rules for every session. Rules 1-12 keep their numbers: about 80 tests
and code comments cite them ("CLAUDE.md Rule 4"), and test_barcode_and_exemption.py
reads Rule 1's wording. Never renumber them, and never reword Rule 1's protected
sentences (listed in Rule 17).

**Where things live** (read the one you need, not all of them):

| Need | File |
|---|---|
| How the app works (request path, storage, background jobs, gotchas) | docs/architecture.md |
| UI conventions, palettes, helpers, layers, load order | docs/design-system.md |
| The business, accounts, entities, who uses the app | docs/product-context.md |
| Why something is the way it is (owner decisions) | docs/decisions.md |
| Open bugs, blockers outside the code, baseline test failures | docs/known-issues.md |
| What changed in production | docs/changelog.md |
| Auth model, public endpoints, secrets | docs/security.md |
| Build prompts and Orbit specs (reference, never edited) | docs/specs/ |
| What is in flight across all worktrees | `<main checkout>/current-work.md` (untracked) |
| Temporary output: traces, plans, baselines, reports | `<main checkout>/active/` (untracked) |

`<main checkout>` is `D:\AltaScraper`. From any worktree it is the parent of
`git rev-parse --path-format=absolute --git-common-dir`. The session-start hook
prints both paths.

---

## 1. BUSINESS MODEL — NEVER CHANGE THIS

This app creates BRAND NEW Amazon listings under the owner's own brand names
(Jack Reacherd, Selvora, Green Haven, Sheelady, AltaboltaVoo etc).

It is NEVER doing "me too" / piggyback / offer-only listings on other sellers'
ASINs. The ASIN in the SKU format (price_days_ASIN e.g. 8.00_3Days_B0G1K5B7QS)
is a COMPETITOR REFERENCE used only during generation to pull product data
(title, specs, images). It is not the target listing. The listing is a new
product under the owner's own brand.

### NEVER — under any circumstances, in any branch, for any reason:
- Send merchant_suggested_asin
- Use requirements: "LISTING_OFFER_ONLY"
- Remove brand, title, or description from the listing payload to avoid
  catalogue conflicts
- Infer a listing mode change from an Amazon error message

### ALWAYS:
- Use requirements: "LISTING" (create new product)
- Never send fake, placeholder, or AI-generated UPC/EAN barcodes to Amazon
- THE GTIN EXEMPTION IS THE OWNER'S DECISION, NEVER THE APP'S.
  Changed by the owner on 26 Aug 2026, in writing:
      "i dont want to use the gtin exemption until the user wants to, he can
       check the button under the box apply for gtin exemption as we have in
       amazon backend, dont apply for exemption automatically"
  Claiming the exemption is a DECLARATION TO AMAZON that the product has no
  barcode. The app must never make that declaration on his behalf.
    * exemption ticked on the listing -> send
      supplier_declared_has_product_identifier_exemption: true
    * not ticked and no usable barcode -> send NEITHER, and say so before the
      submit. Amazon refusing for want of an identifier is the correct outcome.
  The tick is the "GTIN Exemption" column, shown under the barcode box on the
  drawer, off by default.
  REAFFIRMED AND TIGHTENED by the owner on 7 Sep 2026, in writing:
      "REMOVE THE GTIN EXEMPTION OPTION ENTIRELY I ALWAYS HAVE A BARCODE SO
       DONOT AUTOMATICALLY EXEMPT AUTOMATICALLY, ONLY EXEMPT WHEN USER SELECTS
       MULTIPLE DRAFTS AND CLICK ON APPLY FOR GTIN EXEMPTION OR DO IT INSIDE
       THE PDP ONE BY ONE."
  So there are EXACTLY TWO ways the exemption can ever be claimed, and both are
  a deliberate click by the owner:
    1. the tick box on one listing (the PDP / drawer identifier panel)
    2. "Apply for GTIN exemption" on the selection toolbar, for several drafts
  There is no third way, and an empty barcode box is not one. Anything that
  claims it from a CONDITION rather than a click is a bug, however sensible the
  condition looks. Both routes go through static/js/gtin.js, which is the one
  place in the browser that writes the column (Rule 12).
  An "empty the barcode box and it will use the exemption" instruction — in a
  help string, an error explanation, or a comment — is WRONG and must be
  corrected wherever it is found: emptying the box sends Amazon no identifier.
- A BARCODE ALREADY ON ANOTHER LISTING MUST BE REPORTED, not sent and hoped for.
  Amazon matches the code to the ASIN that already owns it and refuses to create
  a second product — measured on his own data, where one EAN was on a live
  jack_uk listing and on the nestwell_goods one he had just submitted, and
  sixteen barcodes were on more than one listing. domain/barcode_clash.py is the
  one place that answers this.

### To change any of the above:
The user must write explicitly: "I want to change the listing mode to X."
An Amazon error message is never sufficient justification to change this.
Any diff touching the payload goes to the `listing-payload-guardian` agent.

## 2. GIT WORKFLOW — ONE LONG-RUNNING DEVELOPMENT BRANCH

- All ordinary work happens in `D:\AltaScraper-wt\claude-environment` on
  branch `claude-environment-setup` (local only, no upstream) — the primary
  development branch since 27 Sep 2026. Do not create another worktree or
  branch, switch branches, reset, rebase, cherry-pick or discard work unless
  the owner explicitly asks. A new worktree is only for isolated experimental
  work he requests, and then it is cut from **origin/main**, never local
  `main` (it goes stale silently).
- Never modify `D:\AltaScraper` (except the shared untracked
  `current-work.md` / `active/`) or origin/main. Commit locally on this branch
  after verification.
- git is not on PATH. Use the GitHub Desktop git (newest `app-*` folder):
  `$g=(Get-ChildItem "$env:LOCALAPPDATA\GitHubDesktop" -Directory -Filter "app-*" | Sort-Object Name -Descending | Select-Object -First 1).FullName + "\resources\app\git\cmd\git.exe"`
- **Pushing to origin/main IS the production deploy** (Render builds it).
  Push, merge and deploy ONLY on the owner's explicit instruction in this
  conversation. Rule 2 says merge only after the owner has confirmed a branch
  in production; when he orders a merge before that, say out loud that the
  waiting period is being waived on his instruction. Never auto-merge.
- **Never commit** (the guard_commit hook enforces this list):
  `config.json*`, `service_account.json`, `.env*`, `users.json`,
  `app_state.json`, `miles_bundles_store.json`, `miles_bundles.json`,
  `image_url_key`, `*.db` / `*.db-wal` / `*.db-shm`, `*.pem`, `*.key`,
  `*.p12`, `*.pfx`, `*.pyc`, `__pycache__/`, and any NON-SOURCE file (not
  .py/.js/.css/.html/.md/.jsx/.ts/.ps1/.bat/.command) whose name contains
  `secret`, `credential`, `key` or `token`. Source files such as
  auth/token_crypto.py, routes/keywords_routes.py and
  .claude/hooks/guard_secrets.ps1 are code, not secrets.
- If something breaks and cannot be quickly fixed: stop, leave the branch, and
  tell the owner what happened. Never leave a broken branch unreported.

## 3. BUG CHECK — MANDATORY AFTER EVERY CODE EDIT

After every edit: compile check, deleted-function check against the branch's
base commit (every changed .py file, `async def` included), re-read the diff,
report (compile result, removed/added functions). The `verify-change` skill
holds the exact commands; the syntax_check hook compiles each .py and
`node --check`s each .js on save. Never deliver a file that fails to compile. A function that disappears
must be explained (a faithful move) or restored.

## 4. WHEN AMAZON REJECTS A VALUE — NEVER GUESS

Read what Amazon actually sends (the raw schema or reply) before changing
anything: the `amazon-schema-first` skill. When explaining the fix, show:
what Amazon's schema says / what we were sending / the difference / the fix.
Never derive an attribute name from Amazon's human-readable message text — use
the structured field/schema, and validate any derived name against the schema
before rendering it as an input field (the "The"/"Your" phantom-field bug).

## 5. PLAIN ENGLISH FIRST — EVERY TIME

The owner is not a programmer. Answer the question asked in the first two or
three lines, in short sentences. Then the technical detail (files, lines,
before/after, why this approach, risks). Define any technical term the first
time it appears in a message (schema, payload, endpoint, API, enum, GTIN, EAN,
SP-API, merchant_suggested_asin, ...). Offer one next step, not three.

## 6. ERROR EXPLANATION FORMAT

What happened (plain English) / why it happened (root cause, file and line) /
why it will not happen again (say honestly if the fix only treats a symptom) /
what to do now.

## 7. ARCHITECTURE RULES

- No new logic in `dashboard.py` or `amazon_listing_generator.py`. New features
  get their own module in `routes/`, `domain/`, `listing/`, `api/`, `data/`,
  `static/js/`, `static/css/` or `templates/` (map: docs/architecture.md).
- `api/` = outside-API calls only. `routes/` = HTTP wiring. `domain/` and
  `listing/` = business logic. `templates/` = HTML only. Never embed JS or CSS
  in Python strings.
- **A change touching more than 2 files: explain the plan and get the owner's
  confirmation before editing.** Exception delegated by the owner (read.txt,
  29 Sep 2026): feature work under the `build-feature` skill at autonomy
  Level 1 or 2 (docs/product-operating-model.md §2) writes its plan to
  `active/` and proceeds. Level 3 real actions and Level 4 (push, merge,
  deploy, irreversible) still wait for the owner, every time.
- One function, one job. Split before adding to a function that does two.

## 8. PPC AND CAMPAIGNS

Never change bids or budgets unless the owner names the exact new value in his
message. Do not recommend bid/budget changes in the middle of other work.

## 9. WHAT THIS APP IS

Multi-account Amazon seller tool (UK/US/EU), run as a Flask app on Render at
app.altascraper.com; the owner tests there, not on 127.0.0.1. Accounts,
entities and brands: docs/product-context.md.

## 10. RESTRUCTURING

The structural phases are done: routes are out of dashboard.py, HTML/CSS/JS
are out of Python strings (one exception remains: dashboard_brand_patch.py still
carries the brand-setup panel's markup and script -- master audit A16), the
listing engine's movable parts are in listing/,
and config/settings.py exists. `build_api_attributes` and the functions that
read the mutable `MARKETPLACE_ID` stay in the engine on purpose. Any further
move: `refactor-move` skill — move code, do not rewrite it; behaviour must be
identical before and after.

## 11. HOW TO START EVERY TASK

Use the `start-task` skill: read the task (usually `<main checkout>/read.txt`),
confirm you are in the development worktree on `claude-environment-setup`,
read current-work.md and the relevant docs, record the task base commit,
classify it, take the test baseline, do the Rule 12 audit. If the request is
unclear in a way that changes what gets built, ask one specific question first.

## 12. NO DUPLICATED LOGIC

Before adding, fixing or touching any logic, search the whole codebase for
every place that handles the same concept (barcode, price, dimensions, status,
hazmat, account, ...). If it exists in 2+ places, extract ONE shared helper
first, then change it there. Never add a "second pass" that reimplements
existing logic. Every delivered fix includes the audit: each location that
touches the concept, and confirmation they all call the same helper.

---

## 13. COMMANDS (Windows, PowerShell 5.1)

- Run the app: `py -3.11 dashboard.py` (picks a free port from 5000; with no
  users and no APP_PASSWORD there is no login).
- All tests: `py -3.11 run_tests.py`. A subset: `py -3.11 run_tests.py pdp`.
  One file: `py -3.11 test_x.py` or `node test_x.js`. Every test is a plain
  script at the repo root that exits non-zero on failure; there is no pytest.
- Syntax: `py -3.11 -m py_compile <file>`; `node --check <file.js>` (parse only).
- PowerShell: no `&&` (use `; if ($?) {...}`); don't redirect native stderr
  with `2>&1`; .NET `[IO.File]` relative paths resolve against `D:\AltaScraper`,
  so always pass absolute paths.
- There is no lint, type-check, build step or CI.

## 14. ACCOUNT SCOPE — EVERY REQUEST NAMES ITS ACCOUNT

The app runs several companies' Amazon accounts, and **SKUs are not unique
across accounts**, so a SKU never identifies an account.
- Browser: every request that reads or writes one account's data names it,
  via `acctBody()` / `acctUrl()` (static/js/reqscope.js) or `scopeQs()`.
- Server: resolve the named account (`routes/scope.py`,
  `domain/request_account.py`, `data/backend.store_for`), never silently fall
  back to the session's `_state`. `_wrong_account` is currently a no-op.
- Guard: a new route that publishes, spends money, deletes or touches
  credentials needs an `auth/guard.py` RULES entry (unlisted writes need only
  "edit").
- Browser state that holds one account's data is keyed by account or reset in
  `enterAccount`.
Changes here go to the `account-scope-reviewer` agent.

## 15. UI RULES

Document and reuse the existing system (docs/design-system.md); never invent a
new one. Reuse an existing helper or pattern before adding one. Data inside an
inline `onclick` goes through `jsArg()`, never `'${esc(x)}'`. Tokens, not hex
(the drawer's literal hex is a recorded decision). Every UI change states its
loading, empty, error and after-account-switch behaviour. A new UI convention
needs the owner's approval. Procedure: `ui-change` skill.

## 16. TESTING AND VERIFICATION

- "Fixed" / "works" is said only with evidence: which checks ran and their
  results. Anything not run is reported as not verified.
- A failure is a regression only if it is not in the baseline taken before the
  change. About 20 tests read the owner's real config.json / database and fail
  in a clean worktree (docs/known-issues.md lists them).
- Many tests assert source text. When one breaks because wording moved,
  re-pin it with a stated reason — never change behaviour to satisfy a pin.
- Every fix adds or updates a test that fails without it.
- Never claim a visual check without having actually seen the result
  (a screenshot); say "not visually verified" instead.

**Review tiers — use the smallest one that fits; never run every specialist:**

| Change | Workflow |
|---|---|
| Trivial and harmless: comments, docstrings, docs/*.md, whitespace, a typo in text that is not shown to users or tested | syntax check only (the hook does it) |
| Meaningful code change | `verify-change` -> `qa-runner` -> `change-reviewer` |
| UI change (static/, templates/, text the UI shows) | `ui-change` -> `ui-reviewer` -> `verify-change` -> `qa-runner` -> `change-reviewer` -> visual verification when possible |
| High risk: listing payload / GTIN / submit (Rule 1), account scope / guard RULES / auth, Amazon writes, bids (Rule 8), DB schema, config/secrets, deploy config | the relevant specialist(s) -> `verify-change` -> `qa-runner` -> `change-reviewer` |

Specialists: `listing-payload-guardian` (Rule 1/4), `account-scope-reviewer`
(Rule 14), `ui-reviewer` (Rule 15), `security-review` skill (auth, secrets,
public endpoints). When unsure which tier applies, use the higher one.

## 17. PROTECTED WORDING (tested)

test_barcode_and_exemption.py requires this file to contain
"THE GTIN EXEMPTION IS THE OWNER'S DECISION", "dont apply for exemption
automatically" and "MUST BE REPORTED", and to NOT contain the old sentence that
told the app to use the exemption when no real barcode is available.
test_title_is_a_source.py requires `dashboard.py` to keep the words
"CLAUDE.md rule 1".

## 18. KEEPING PROJECT CONTEXT

At the end of every meaningful task run the `update-context` skill. It routes:
architecture fact -> docs/architecture.md; observed UI convention ->
docs/design-system.md; unresolved problem -> docs/known-issues.md; decision
the owner made -> docs/decisions.md; deployed change -> docs/changelog.md;
in-flight state -> current-work.md; temporary output -> active/.

Claude maintains those automatically. **Owner approval is required for:** any
change to this file; a new UI convention; new or changed skills, agents or
hooks; deleting or archiving files; `.gitignore` / `.dockerignore` edits;
any behaviour change. **Explicit instruction is required for:** push, merge,
deploy.

**Governance layer.** This file, `.claude/settings.json` (and
`settings.local.json`), `.claude/hooks/`, `.claude/agents/` and
`.claude/skills/` are the governance layer. Permanent governance changes need
the owner's approval: propose the exact change (what and why) and wait. The
`guard_rules` hook enforces this by turning every edit of those files into a
confirmation prompt; the owner approves it there, which keeps the system
maintainable. Never try to get around a guard (for example by writing a file
through a different tool); if a guard blocks something legitimate, say so and
let the owner decide.

## 19. CAPABILITIES

Skills (`.claude/skills/`): start-task, investigate, verify-change,
amazon-schema-first, ui-change, refactor-move, ship, update-context,
project-maintenance, security-review, build-feature (a feature outcome in
plain English, end to end; operating model: docs/product-operating-model.md).
Agents (`.claude/agents/`): tracer, listing-payload-guardian,
account-scope-reviewer, ui-reviewer, change-reviewer, qa-runner. They are
**read-only by instruction**: their definitions forbid edits, but four of them
can run PowerShell, so this is not technically enforced. qa-runner runs tests;
change-reviewer is the independent bug/regression reviewer.
Hooks (`.claude/hooks/`, enforced by Claude Code in every permission mode):
- `session_start` — prints branch, worktree and current-work.md at start
- `syntax_check` — compiles each edited .py / `node --check`s each .js and
  reports errors back to Claude
- `guard_secrets` — denies any tool call naming a secret-bearing file
  (config.json, service_account.json, .env*, users.json, app_state.json,
  miles_bundles*.json, image_url_key, *.db, *.pem, *.p12, *.pfx, non-source
  names containing secret/credential), including indirect shell/.NET/Python reads
- `guard_rules` — asks the owner before any governance-file edit
- `guard_commit` — denies staging or committing never-commit files
- `guard_push` — asks the owner before any push (louder for main)
The guards fail safe: if a check cannot complete, guard_secrets and
guard_commit deny, guard_push and guard_rules ask. Where no confirmation
prompt can be shown (bypass mode; accept-edits mode for file edits), an "ask"
becomes a deny, because Claude Code was measured ignoring a hook's ask there:
the owner then does the action himself or approves it in a normal-mode
session. Known limits: docs/known-issues.md "Claude Code environment".

## 20. UNCERTAINTY

Say "not verified" rather than guess. Never state an inference as a measured
fact. For Amazon behaviour, capture the raw reply (Rule 4). If code and a doc
disagree, the code wins, and the doc is corrected in the same task.
