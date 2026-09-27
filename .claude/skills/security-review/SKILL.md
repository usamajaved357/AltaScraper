---
name: security-review
description: AltaScraper-specific security review - secrets and .env handling, API credentials, dependencies, Flask routes vs auth/guard.py RULES and PUBLIC_ENDPOINTS, authorisation (user vs workspace publish), account isolation, output escaping, external APIs, deployment config and database access. Use before merging changes to routes, auth, config, accounts or OAuth, and periodically.
---

# security-review

**Problem it solves:** under-protected new routes (unlisted writes need only
"edit"), cross-account actions, secrets leaking into git/logs, XSS through
inline handlers.

**Modifies files:** no. Findings go to docs/known-issues.md and
docs/security.md after the owner has seen them.

## Scope
A diff (default: `git diff origin/main...HEAD`) or the whole repo (periodic).

## Procedure
1. **Secrets**
   - `git status`, `git diff --cached --name-only`, and `git ls-files` against
     the never-commit list (CLAUDE.md Rule 2). Any match is critical.
   - New code does not print, log, stream (SSE) or return credentials or
     refresh tokens; error text does not echo config values.
   - Never open config.json, service_account.json, .env or users.json to
     "check" them.
2. **Code checks** (hand to `change-reviewer` in security mode):
   - every new `@app.route`: which RULES entry applies (first prefix match)?
     Publish / spend / delete / credential routes need an explicit entry above
     the broader prefix; a GET that changes state is a finding.
   - `PUBLIC_ENDPOINTS` unchanged, or the change is approved.
   - SQL built with f-strings / `%` / `+` on values (use `?` placeholders).
   - subprocess arguments built from request input (the generator's argv).
   - direct `json.dump(..., open(config...,"w"))` (should use config/settings.write_raw).
   - inline handlers with `'${esc(x)}'` (use `jsArg`), raw `o.html` into dialogs.
3. **Authorisation:** user permission vs workspace capability — e.g.
   `_require_publish()` checks the workspace; is the user's `publish` checked on
   every path that reaches Amazon? (known-issues #1).
4. **Account isolation:** run the `account-scope-reviewer` agent.
5. **External APIs:** timeouts set; Ads client still has no write calls
   (test_ads_connect.py); Slack URLs restricted to hooks.slack.com; OAuth nonce
   single-use with expiry; `DRAFT_VERSION_PARAM` still correct for the app's
   publication state.
6. **Deployment:** render.yaml / railway.json env vars (APP_SECRET_KEY set so
   sessions survive restarts; APP_PASSWORD); `.dockerignore` keeps secrets,
   docs/, active/, .claude/ out of the image; debug mode off.
7. **Dependencies:** requirements.txt has lower bounds only; note any
   dependency added by the diff and whether it is maintained. Do not upgrade
   without approval.
8. **Database:** new tables/columns through `data/db.py` SCHEMA/_migrate; no
   destructive SQL run against real data from the agent shell.

## Output
Findings ranked critical / high / medium / low, each with file:line, the
exploit in one sentence (class of problem only, never a working exploit), and
the suggested direction. Mark each CONFIRMED (test or reproduction) or READ.

## Persist afterwards
docs/known-issues.md (open findings); docs/security.md (model changes, owner
reviewed).
