# CLAUDE.md — Standing Rules for Every Session
# This file is version-controlled. Every branch inherits these rules.
# Read this entire file before touching any code, any session, no exceptions.

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
- When no real GS1-registered barcode is available, use the GTIN exemption:
  supplier_declared_has_product_identifier_exemption: true
- Never send fake, placeholder, or AI-generated UPC/EAN barcodes to Amazon

### To change any of the above:
The user must write explicitly: "I want to change the listing mode to X."
An Amazon error message is never sufficient justification to change this.

---

## 2. GIT WORKFLOW — EVERY PIECE OF WORK IS A BRANCH

Before starting any work in a session, check which branch is active:
  git branch

If on main, create a branch before touching anything:
  git checkout -b short-description-of-work
  (examples: fix/barcode-validation, feature/miles-drive-scan, refactor/phase-1-templates)

After completing and verifying work in a branch:
  git add .
  git commit -m "clear description of what changed and why"

### What NEVER goes into a commit — verify with git status before every commit:
- config.json (SP-API keys, Anthropic key, seller IDs)
- service_account.json (Google credentials)
- miles_bundles_store.json (local data cache)
- miles_bundles.json
- *.pyc files and __pycache__/ folders
- .env files
- Any file whose name contains: secret, credential, key, token

If any of the above appear in git status as untracked or modified,
STOP and check .gitignore before committing anything.

### If something breaks during a session and cannot be quickly fixed:
  git checkout main
Tell the user what happened, what was attempted, and why the rollback was needed.
Never leave a broken branch without telling the user.

### Merging back to main:
Only merge a branch to main after the user has confirmed it works in production
for at least a short period. Never auto-merge.

---

## 3. BUG CHECK — MANDATORY AFTER EVERY CODE EDIT

This is non-negotiable. After every single edit to any Python file,
run this full sequence before saying anything else or moving to the next step.

### Step 1 — Baseline (once per session, before first edit)
  cp amazon_listing_generator.py amazon_listing_generator.baseline.py
  cp dashboard.py dashboard.baseline.py
Keep these for the entire session. Never overwrite them.

### Step 2 — Compile check (after every edit)
  python -m py_compile amazon_listing_generator.py
  python -m py_compile dashboard.py
If this fails: STOP. Fix the syntax error. Do not proceed.
Never deliver a file that fails py_compile.

### Step 3 — Scope check (after every edit)
Run this to confirm no functions were accidentally deleted or renamed:

  python - << 'EOF'
  import ast
  b = ast.parse(open('amazon_listing_generator.baseline.py').read())
  n = ast.parse(open('amazon_listing_generator.py').read())
  def fns(t): return {x.name for x in ast.walk(t) if isinstance(x, ast.FunctionDef)}
  removed = sorted(fns(b) - fns(n))
  added   = sorted(fns(n) - fns(b))
  print("REMOVED:", removed)
  print("ADDED:  ", added)
  EOF

If REMOVED is not empty: STOP. A function was accidentally deleted.
Do not continue until the missing function is restored or the deletion
is explicitly confirmed intentional by the user.

### Step 4 — Re-read the diff
After every edit, re-read the exact changed lines and ask:
- Does this change exactly what was intended and nothing else?
- Could this affect any other part of the app that was not considered?
- Is any assumption baked into this change that could be wrong?
- Does this change touch business logic that is protected by Rule 1?

### Step 5 — Report to user
After every edit, tell the user:
- PLAIN ENGLISH: what was wrong, what was changed, what will be different now
- TECHNICAL: which file, which function, which lines changed
- BUG CHECK RESULTS: compile pass/fail, scope check (removed/added functions)
- BASELINE: confirm the baseline copy exists and where it is

---

## 4. WHEN AMAZON REJECTS A VALUE — NEVER GUESS

When Amazon returns an error like "value is invalid" or "does not match":

### Do NOT:
- Guess what Amazon wants based on documentation
- Guess based on training data or similar fields seen before
- Try a different value and hope it works
- Assume the schema shape from memory

### DO:
1. Add a temporary diagnostic that prints the RAW schema Amazon returns
   for the failing field — the exact JSON Amazon sends back, before any
   of our code processes it
2. Run one preview to capture that raw schema
3. Read the schema to find: the exact field name for the number
   (is it "value" or "decimal_value"?), whether the container is an
   array or an object, what units are allowed (the enum list)
4. Build the fix from what the schema literally says
5. Remove the diagnostic once the fix is confirmed working

### When explaining the fix to the user, always say:
- "Here is what Amazon's schema actually says" (show the raw schema)
- "Here is what we were sending" (show the actual payload)
- "Here is the difference" (point at the exact mismatch)
- "Here is the fix" (explain in plain English what changes)

This is how the leg/cable/decimal_value bugs were eventually solved.
Every hour spent guessing is wasted. The schema is always available — use it.

---

## 5. PLAIN ENGLISH FIRST — EVERY TIME

Every time code is changed, an error is explained, or the user is asked
to approve a change, structure the response like this:

### PLAIN ENGLISH (always first):
One paragraph maximum. Explain:
- What was going wrong (as if explaining to someone who has never coded)
- What the fix does (same level)
- What the user will see change in the app

### TECHNICAL DETAIL (always second):
- Which file and which lines changed
- What the code did before vs what it does now
- Why this approach was chosen over alternatives
- Any risks or side effects

### Never use technical terms without defining them first in that same message.
Examples of terms that always need a plain English explanation before use:
schema, payload, endpoint, API, enum, array, object, regex, middleware,
merchant_suggested_asin, LISTING_OFFER_ONLY, sp-api, gtin, ean, upc,
build_api_attributes, shape_by_schema, taken_skus, ws_out, gc, mid

---

## 6. ERROR EXPLANATION FORMAT

When an error occurs, always structure the explanation like this:

### What happened (plain English):
One paragraph. What the user saw. What the app was trying to do.
What went wrong in terms anyone can understand.

### Why it happened (plain English + technical):
The root cause. Not the symptom — the underlying reason.
Include which file, which function, which line if relevant.

### Why it will not happen again:
Explain what the fix addresses at the root level.
If the fix only addresses the symptom, say so honestly and
describe what a root-level fix would require.

### What to do now:
Clear next steps for the user.

---

## 7. ARCHITECTURE RULES — DO NOT VIOLATE

The app is being progressively restructured. During this process:

### Never add new logic to these files:
- dashboard.py — being broken up into routes/ + templates/ + static/
- amazon_listing_generator.py — being broken up into listing/ modules

New features go in their own dedicated file from day one.
If it does not fit in an existing module, create a new one.

### File responsibilities (strictly enforced):
- api/amazon_sp.py — SP-API calls only. No UI, no business logic.
- api/google_sheets.py — Sheets read/write only. No listing logic.
- api/google_drive.py — Drive operations only. No business logic.
- listing/shaper.py — shape_by_schema and field shaping only.
- listing/builder.py — build_api_attributes only.
- listing/compliance.py — IP rules, hazmat, compliance_rules.json only.
- listing/auto_fix.py — the suggest/apply/preview loop only.
- listing/miles.py — Miles Lubricants specific logic only.
- templates/ — HTML files only. No Python logic inside templates.
- static/js/ — JavaScript files only. Never embed JS in Python strings.
- static/css/ — CSS files only. Never embed CSS in Python strings.

### If a change requires touching more than 2 files:
Stop. Explain the full plan to the user before making any edits.
Get confirmation before proceeding.

### One function, one job:
If a function does more than one thing (e.g. fetches data AND formats it
AND writes to a sheet), split it before adding to it.

---

## 8. STANDING RULES FOR PPC AND CAMPAIGNS

NEVER change bids or budgets on any campaign unless the user explicitly
specifies in their message the exact new value to set.

Do not recommend bid/budget changes proactively in the middle of other work.
If bid/budget changes are needed, flag them separately and wait for instruction.

---

## 9. WHAT THIS APP IS — CONTEXT FOR EVERY SESSION

**Owner:** Talha (Sahiwal, Punjab, Pakistan)
**Operation:** Multi-platform e-commerce (Amazon US/UK, eBay UK/US/AU, TikTok Shop)

**UK entities:**
- FLIPX LTD
- Green Haven Goods Ltd (CRN 16578100, director Nida Mustafa)
- Selvora Limited (CRN 16977772, director Rida Rasheed)

**Amazon accounts:**
- jack_uk — seller A34CMN3Q5Q4U3Z (UK, marketplace A1F83G8C2ARO7P)
- sheelady_us — seller A1W1VC2O2BR7M2 (US)

**Amazon agency:** ALTAVOUR (brand recovery, $12K fixed 90-day engagement)
**Agency role:** Manager at Full Circle Agency (Houston)

**Tech stack:**
- Local Flask app running at 127.0.0.1:5000 (auto-fallback port if taken)
- Python 3.11 on Windows
- Google Sheets as the primary data store (input + output)
- Google Drive for file/image storage
- SP-API for Amazon listing validation and submission
- Anthropic Claude API for listing copy generation

**Key config files:**
- config.json — all credentials (NEVER commit to Git)
- service_account.json — Google credentials (NEVER commit to Git)
- compliance_rules.json — 17 product categories
- ip_rules.json — IP violation rules
- valid_values.json — 21 product types

---

## 10. RESTRUCTURING PLAN — CURRENT STATUS

The app is being restructured in 6 phases. Do not skip phases or
combine phases. Each phase must be stable in production before the next begins.

- Phase 1: Architecture mapping — produce ARCHITECTURE.md (read-only, no code changes)
- Phase 2: Extract HTML/JS into templates/ and static/ folders
- Phase 3: Extract API layer into api/ folder
- Phase 4: Extract listing engine into listing/ folder
- Phase 5: Extract eBay, PPC, TikTok into domain folders
- Phase 6: Clean routing — dashboard.py becomes routes only

### Current phase: NOT STARTED (Git setup must come first)

### Rule during restructuring:
Move code, do not rewrite it. The app must behave identically
before and after every phase. If behaviour changes during a move,
stop and investigate — a move should never change what the app does.

---

## 11. HOW TO START EVERY SESSION

Read this file. Then:
1. Run: git branch (confirm which branch you are on)
2. If on main and doing real work: git checkout -b branch-name
3. Take baselines: cp the two main Python files to .baseline.py
4. Read ARCHITECTURE.md if it exists (it will after Phase 1)
5. Then and only then, start the work the user asked for

If the user's request is unclear, ask one specific clarifying question
before starting. Do not make assumptions about what they want.
