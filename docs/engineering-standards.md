# Engineering standards

Rules for code in this app, each with the reason AltaScraper needs it and what
enforces it. CLAUDE.md is the governing file; this one is the working detail
under it and never overrides it. Written in Milestone 4 (28 Sep 2026) from the
master audit's section 16, keeping only rules that are now true of the code.

"Enforced" names the test that fails when the rule is broken. "Review" means
nothing automatic catches it yet -- the change-reviewer checks it.

---

## 1. Every account is named, checked and pinned

| Rule | Why | Enforced |
|---|---|---|
| A request that acts on an account NAMES it (`acctBody`, `acctUrl`, `scopeQs`, `ppcQS`) | the server's "open account" is shared state; unnamed requests acted on whichever was open (known-issues #4) | review |
| The guard checks every account a request names, in any field, any body type, every row | the audit walked past it five different ways | test_guard_every_account.py |
| A bulk loop takes the account ONCE, before its confirmation, and stops if it changes | a switch mid-loop sent the rest to the new account's same-SKU rows -- incl. a GTIN declaration and a delete on Amazon | test_bulk_account_pinned.js |
| A loader takes `screenScope()` before its fetch and checks `screenStillIn()` after every await | late replies painted account A on account B's screen | test_switch_drops_old_replies.js |
| A screen that holds data resets it in `screenstate._screenResetHeld`, and lists its panel in `SCREEN_BODIES` | reopening redrew the previous account | test_switch_drops_old_replies.js (per screen: review) |
| A SKU never identifies an account | the owner reuses SKUs across accounts | review (memory: skus-are-not-unique-across-accounts) |

## 2. Permissions live in one table

| Rule | Why | Enforced |
|---|---|---|
| A route that publishes, spends, deletes or exposes credentials is in `auth/guard.py` RULES (or WRITE_RULES / BODY_RULES) | unlisted writes need only "edit" | test_permission_coverage.py, test_guard_every_account.py |
| Work done over GET is listed in `WORK_OVER_GET` | a view-only user could start a submit by GET | test_guard_every_account.py |
| A route whose `id` is NOT an account is listed in `ID_NOT_AN_ACCOUNT` | otherwise users limited to some accounts are refused it | test_guard_every_account.py |

## 3. Output is escaped for where it goes

| Rule | Why | Enforced |
|---|---|---|
| Text in HTML: `esc()`. A value inside an inline handler: `jsArg()` -- given the RAW value, never an already-escaped one | `esc` turns `'` into `&#39;`, which the browser decodes back inside `onclick="fn('...')"`: stored XSS | test_no_esc_in_handlers.js (single-line handlers) |
| One escaper per purpose; private copies delegate | four copies had drifted, two unsafe | review |

## 4. Files that hold state are written atomically

| Rule | Why | Enforced |
|---|---|---|
| config.json only through `config/settings.write_raw` | it holds every credential and is git-ignored -- no copy to restore | test_profit_review_fixes.py section 14 |
| Any JSON the app keeps (costs, bundles, defaults, stores) through `domain/jsonstore.write_json_atomic` | `open(p,"w")` empties the file before writing; a corrupt file then read as `{}` is saved back over everything | review (cogs_overrides, miles bundle store, attribute defaults converted in Milestones 2-4) |

## 5. Outside the app

| Rule | Why | Enforced |
|---|---|---|
| A URL that came from a user is fetched only through `domain/url_policy.urlopen` | full-read SSRF into the server and its private network | test_security_basics.py (lists the callers) |
| A file sent to an outside service is checked to be what it claims (e.g. pictures only) | a template path could name config.json | test_security_basics.py |
| "Is this hosted?" is `config/hosting.py` | four drifting copies | test_security_basics.py |
| Nothing publishes, reprices, changes bids/budgets or claims the GTIN exemption without a person's deliberate click | CLAUDE.md Rules 1 and 8 | protected tests + listing-payload-guardian |

## 6. Tests tell the truth

| Rule | Why | Enforced |
|---|---|---|
| A test resolves paths from its own tree (`_REPO` / `__dirname`), never `D:\AltaScraper` | 141 tests silently tested the main checkout | review (grep for the literal path) |
| Tests run through `run_tests.py`: own empty DB and stand-in config per file | so no test can touch real data or credentials | run_tests._safe_env |
| A test that cannot run exits 125 and says why -- it never "passes" | red that is not a fault teaches everyone to skim red | run_tests.py |
| A new check is shown to fail on the old code before it is trusted | several passing tests turned out to test nothing | review |
| A test that draws HTML in a sandbox loads the page's own `jsArg` (`test_helpers.jsArg`) | a stand-in escaper tests nothing | review |
| No name is used that is defined nowhere (Python and JS) | two NameErrors shipped and broke Generate | test_no_undefined_names.py, test_no_undefined_js_calls.js |

## 7. One logic, one place (CLAUDE.md Rule 12)

Before adding logic, search for every place that handles the same concept.
Examples settled so far: profit (`order_finance` / `order_profit` / `unit_profit`),
account scope for a request (`routes/scope.for_request`, `domain/request_account`),
the account check (`guard.named_workspaces`), the fetch policy, hosting, the
handler escaper, the screen scope (`screenScope`), config writes.
