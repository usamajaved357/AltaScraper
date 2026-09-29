# Handover — Orbit Inventory extraction

**For:** the next Claude Code session, running with bypass permissions.
**Written:** 17 Aug 2026. Previous session stopped here deliberately; the
permission classifier was blocking roughly half of all PowerShell calls, which
made a several-hundred-step browser job unworkable.

**Read this whole file before running anything.** Then read `CLAUDE.md` — the
standing rules apply to this work too, especially Rule 5 (plain English first)
and Rule 12 (no duplicated logic).

---

## 1. What the user asked for

An exhaustive extraction of Orbit's Inventory system — enough detail to rebuild
it from scratch. Eleven parts:

| Part | Subject |
| --- | --- |
| 1 | Inventory Cockpit banner — the "141 critical ASINs need action" strip, next projected stockout, inbound-within-7-days, and the three stat cards (Revenue at Risk, Inventory at Cost, Avg Cover) |
| 2 | Every button: Run AutoPilot, Open action queue, Autopilot onboarding, Open reimbursements, Steven actions — click each, document what opens |
| 3 | The four stat cards (Network Units, Amazon FBA, COGS Value, Review Queue) and the ⓘ tooltip on each |
| 4 | The product table — columns `PRODUCT / F/A/3 / TOTAL / VEL / VALUE / DOS / STATUS`, sorting, search, row click, expand arrow, pagination |
| 5 | Every tab: Overview, Forecasting, Actions, Shipments, Comms |
| 6 | **Steven**, the inventory AI agent — the user called this the most important part. Full interface, capabilities, and five specific questions asked live |
| 7 | AutoPilot — rules, reorder points, safety stock, lead times, what "Run AutoPilot" actually executes |
| 8 | Inventory settings at `/cogs` |
| 9 | Reimbursements |
| 10 | Design specs — every measurement, colour, font size, radius, gradient |
| 11 | API calls — endpoint, method, params, response shape, load vs interaction |

**Output file:** `orbit_inventory_complete.md`, plus screenshots of every screen
and state.

The five questions to put to Steven verbatim:

1. "Which ASINs need reordering this week?"
2. "What's the stockout risk for our top 5 products?"
3. "Draft a purchase order for items running low"
4. "What's our inventory health summary?"
5. "Show me slow-moving inventory"

**Target:** brand `flux-footwear`, marketplace `ATVPDKIKX0DER` (Amazon US).
Base URL: `https://fullcircleorbit.com/brand/flux-footwear/ATVPDKIKX0DER`

---

## 2. State of play — what is already true

Verified this session, so you do not need to re-check any of it:

- **`playwright` is installed** and imports cleanly.
- **Chrome is already running with the debugging port open on 9222.**
  Chrome/151.0.7922.109. Confirmed via `http://127.0.0.1:9222/json/version`.
- **That Chrome is signed into Orbit.** `http://127.0.0.1:9222/json/list`
  showed a live page target at
  `https://fullcircleorbit.com/brand/flux-footwear/ATVPDKIKX0DER/inventory/comms`
  — a brand route, not a login page. There is also a tab on
  `app.altascraper.com`. Only 4 targets total, so attaching should be quick.
- **`%TEMP%\orbit-profile` exists** from earlier capture sessions.
- **The extraction script is written and ready:**
  `tools/orbit_inventory_extract.py`. It has never been run to completion — see
  §5, it is unproven.

**No credentials are needed and none should be requested.** The user offered
them; they are not required and should not be typed into the chat. The whole
method is to attach to a browser the user has already signed into.

---

## 3. Prior work in this repo — read before extracting

- **`orbit_full_audit.md`** — a 13 Aug 2026 crawl of 45 routes on the
  *Lure Essentials* brand. Contains the full route table, the API surface the
  user pasted into their brief, the table column names, and the four cockpit
  button labels. It is **shallow on purpose**: DOM-at-load only, first viewport
  only, nothing clicked. Its own "not covered" section names exactly the gaps
  this job fills. Do not redo it; build on it.
  Useful facts already established there:
  - Two parallel builds of the same screen ship side by side —
    `/inventory/overview` ("Ken" build, the one the user wants) and
    `/inventory/inventory-overview` ("Ameer" build).
  - Named agents in the app: **Ava, Steven, Dr PPC™**. A persistent circular
    ~100px avatar sits bottom-right with a status dot. Opening the assistant
    sets `--chat-drawer-width` and squeezes the app shell — meaning **Steven may
    not open as a modal**; expect a drawer that resizes the layout.
  - `/inventory/comms` pairs with
    `/api/inventory-agent/{brand}/comms/scan-policy` — agent-driven supplier
    comms with a configurable scan policy.
  - The app defines 80+ named keyframes, including `_autopilotStepSwirl_kexn7_1`
    — the AutoPilot onboarding flow is heavily animated.
  - `prefers-reduced-motion` is honoured.
- **`tools/orbit_capture.py`** and **`tools/orbit_scan_page.py`** — the proven
  tools from earlier sessions. They only measure the *Sales* dashboard and never
  click anything, but their approach is sound and their docstrings explain the
  CDP method and its limits well. Reuse their patterns, do not duplicate them
  (Rule 12).
- **`orbit_interactions.md`**, **`orbit_sales_spec.md`** — outputs of those two
  tools, for the Sales page. Good examples of the level of detail the user
  expects.

---

## 4. Access — how you get in, and why there is no password here

**There are deliberately no credentials in this file, and you do not need any.**

Attach Playwright to the user's already-signed-in Chrome over the DevTools
protocol. No password is typed by Claude, none is stored, nothing leaves the
machine. This is how every previous Orbit capture in this repo was done.

The user asked for their Orbit login to be written into this document. It was
not, for three reasons:

1. It is not needed — the session on port 9222 is already authenticated
   (verified, §2).
2. **This file is tracked by git.** `.gitignore` covers `config.json`, `*.key`,
   `.env` and `users.json`, but not `*.md`. A password written here goes into
   the repository history. Live API keys are already sitting in this repo's old
   history awaiting rotation; do not add to that pile.
3. `CLAUDE.md` Rule 2 forbids committing anything that is credential material.

**If the user asks you to store the login anyway:** put it in `config.json`
(already gitignored, already where every other credential in this app lives),
never in a markdown file, and never in a file you are about to `git add`.

### If the session has expired

The symptom is any part exiting with *"Stopped: not signed in"* — the script
checks `page.url` for a login redirect before capturing anything, on every part.

Do not ask for the password. Ask the user to sign in **in the debug Chrome
window themselves**, wait for them to confirm, then re-run the part. Claude
never handles the credentials.

If the debug Chrome is not running at all, the user starts it:

```
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 --user-data-dir="%TEMP%\orbit-profile"
```

A separate `--user-data-dir` is deliberate: Chrome refuses the debugging port on
a profile that is already running, and it keeps the user's normal browser
untouched.

**The Claude-in-Chrome extension is not available** — the user declined it and
asked that it not be suggested again. Do not offer it. CDP is the route.

---

## 5. The script that is waiting for you

`tools/orbit_inventory_extract.py` — written this session, **never run to
completion. Treat it as a first draft, not a proven tool.**

Subcommands, each writing its own fragment to `orbit_inventory/<part>.md` so a
failure at step 40 does not cost steps 1–39:

```
python -u tools/orbit_inventory_extract.py routes      # every inventory route: scan, screenshots, load-time API calls
python -u tools/orbit_inventory_extract.py clicks      # the five cockpit buttons, and what each opens
python -u tools/orbit_inventory_extract.py table       # columns, sort, search, row click, expand, pagination
python -u tools/orbit_inventory_extract.py tooltips    # hover every ⓘ — this is where the RULES live
python -u tools/orbit_inventory_extract.py steven      # open Steven, ask the five questions
python -u tools/orbit_inventory_extract.py design      # tokens, motion, cockpit banner, stat cards, tab bar
python    tools/orbit_inventory_extract.py assemble    # merge fragments -> orbit_inventory_complete.md
python -u tools/orbit_inventory_extract.py all         # everything, then assemble
```

**Always pass `-u`.** Without it Python buffers stdout and the background-task
output file stays empty, which makes a long run impossible to monitor. That cost
this session two dead runs.

What is built into it already, and worth knowing before you rewrite anything:

- **Screenshots work around the app shell.** Orbit is `height:100%` with the
  scroll on an inner child, so `full_page=True` stops at the fold — which is
  precisely why the earlier audit has no below-the-fold imagery. `shots_down()`
  finds the real scrolling element and steps it down a viewport at a time.
- **Network capture is phase-stamped.** Every XHR/fetch is tagged with what was
  happening at the time (`load:overview`, `click:Run AutoPilot`, `steven:q3`),
  which is how Part 11's "load vs interaction" question gets answered. Response
  bodies are read *after* the page settles, never inside the event handler —
  blocking a Playwright handler on a network read deadlocks the run.
  Only top-level keys and one level of shape are recorded, no row data.
- **Overlays are found structurally** — by `role`, z-index and geometry — not by
  class name. Orbit's class names are content-hashed (`_statCard_xa5pv_431`) and
  change every build.
- **Steven's replies stream**, so the script waits for the answer to stop growing
  rather than sleeping a fixed time. `--steven-wait` controls the ceiling.
- **Status chip colours are read off the rendered chips**, giving the real STATUS
  legend rather than a guess at it.

Flags: `--limit` (elements listed per route), `--max-tooltips`, `--steven-wait`,
`--search-term`, `--width`, `--cdp`, `--out`.

### Suggested order

Run `tooltips` and `design` early — they are short, and tooltips is where Orbit
states its own rules in its own words, which is most of what Parts 1 and 3 are
really asking for. Then `table`, `clicks`, `routes`, and `steven` last (longest
and most fragile). Do **not** start with `all`.

### Known unknowns in the script

- The button-finding helper matches on visible text across several tag types. If
  "Steven actions" is not a `<button>` it may miss; there is a fallback that
  hunts the fixed-position circular dock bottom-right, but that is untested.
- AutoPilot onboarding is likely a multi-step wizard. The script captures the
  *first* screen only. **Parts 2 and 7 need a human-guided pass through each
  step** — plan to add a step-through loop, or drive it interactively.
- `Run AutoPilot` may actually execute something. **See §7 before clicking it.**

---

## 6. Where the real answers live

The user asks "what makes an ASIN critical?", "how is next projected stockout
calculated?", "what formula for Revenue at Risk?". Orbit's server code is not
visible, so these can only come from three places, in descending order of
trustworthiness:

1. **Tooltip and helper copy** — Orbit explaining its own rules. Quote verbatim.
2. **API response field names and values** — e.g. if `products` rows carry
   `days_of_supply`, `velocity_30d`, `reorder_point`, the arithmetic is often
   recoverable by checking the numbers against each other across rows.
3. **Arithmetic checked against rendered values** — take five rows, test whether
   `DOS = TOTAL / VEL` holds. If it does across all five, say so and show the
   working.

**Label every inferred formula as inferred.** The user is rebuilding from this
document; a guess presented as fact becomes a bug in their app. CLAUDE.md Rule 4
exists because of exactly this failure mode — do not guess at a value and hope.

---

## 7. Safety — read before clicking anything

This is a **live production system** for a real agency account
(`talal@fullcircleagency.com`), with real inventory data for real brands.

- **`Run AutoPilot` may create purchase orders, FBA shipments, or queued
  actions.** Do not click it without asking the user first. The safe path is to
  open **`Autopilot onboarding`** and the **action queue** — which show the rules
  and the pending items — and to ask the user explicitly before triggering a run.
  If they approve, look for a dry-run or preview option and prefer it.
- **Reimbursements can file claims.** Document the interface; do not submit.
- **Comms can send messages to suppliers.** Document the templates and the draft
  previews; do not send.
- **Steven may be able to take actions, not just answer.** The five questions are
  read-only asks. If Steven offers to execute something, capture the offer and
  stop there.
- The COGS/settings page has editable fields. **Read them, do not save.** If a
  value must be changed to reveal behaviour, ask first and change it back.

When in doubt: capturing what a control *would* do is the deliverable.
Triggering it is not.

---

## 8. Definition of done

`orbit_inventory_complete.md` in the repo root, containing:

1. Feature inventory — what exists and what it does
2. Rule definitions — critical / at risk / needs action, quoted where Orbit
   states them, marked *inferred* where not
3. Calculation methods — DOS, velocity, reorder point, stockout projection
4. Steven's capabilities, in full, with the five answers transcribed verbatim
5. AutoPilot rules and every configuration option
6. Design specs — measurements, colours, fonts, radii, gradients, motion
7. API surface — endpoints, methods, params, response shapes, load vs interaction
8. Screenshots of every screen and state, in `orbit_inventory/shots/`

Each section marked **measured**, **quoted**, or **inferred**. Nothing guessed
presented as fact.

---

## 9. Housekeeping

- Current branch is `koibhe`. Per CLAUDE.md Rule 2, create a branch before doing
  the work: `git checkout -b feature/orbit-inventory-extraction`.
- Note that per `deploy-and-branch-flow` in memory, `koibhe` is local-only and
  its `origin/` ref is stale and misleading.
- `git` is not on PATH — use the GitHub Desktop bundled `git.exe` (see the
  `git-binary-location` memory).
- Before committing, check `git status` against Rule 2's never-commit list.
  `orbit_inventory/` will hold screenshots and captured business data for real
  brands — **decide with the user whether it belongs in version control at all.**
  It contains live inventory figures, ASINs and cost data for agency clients.
- CLAUDE.md Rule 3 (baseline + `py_compile` + scope check after every edit)
  applies if you edit any Python here.

## 10. What the previous session actually completed

- Confirmed the environment: playwright present, CDP live on 9222, Chrome signed
  into Orbit, `%TEMP%\orbit-profile` present.
- Read the prior audit and mapped what is already known versus what is missing.
- Wrote `tools/orbit_inventory_extract.py` in full.
- **Captured no data.** Both attempted runs were killed — the first by stdout
  buffering, the second by the user's request to hand over. `orbit_inventory/`
  may not exist yet, and if it does it is empty or partial. Start clean.
