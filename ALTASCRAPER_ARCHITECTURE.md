# ALTASCRAPER — ARCHITECTURE PLAN (Rebuilt Clean Version)
# Flask + Google Sheets + Hosted for team
# Written after reading the actual codebase — not generic advice.

---

## WHAT YOU ACTUALLY HAVE RIGHT NOW

Good news first: this app is already BETTER than the old one.
Several modules already exist as separate files:

ALREADY SEPARATED (keep these, just move them to the right folder):
  accounts.py         151 lines  — account model
  ai_providers.py     731 lines  — OpenRouter/AI gateway
  brand_analytics.py  439 lines  — Amazon Brand Analytics via SP-API
  brand_listing.py   1021 lines  — brand-mode listing generation
  brand_profile.py    377 lines  — brand profile + Drive connections
  inventory_module.py 978 lines  — FBA replenishment engine
  ppc_module.py       957 lines  — PPC campaign builder
  ppc_deliverables.py 716 lines  — PPC output files (xlsx/docx/pptx)
  shopify_import.py   440 lines  — Shopify export adapter
  miles_import.py    1095 lines  — Miles Lubricants harvester
  image_gen.py        185 lines  — AI image generation (Gemini)
  unified_export.py   226 lines  — unified template exporter
  template_schema.py  147 lines  — schema helpers

STILL MONOLITHIC (need to be broken up):
  dashboard.py       15,261 lines — 98 routes + all HTML + all JS
  amazon_listing_generator.py 7,747 lines — listing engine

The job is:
1. Move the existing modules into the right folders
2. Break dashboard.py into routes/ + templates/ + static/
3. Break amazon_listing_generator.py into listing/ modules
4. Wire everything back together through main.py

---

## THE LANGUAGES — WHICH ONE DOES WHAT

### Python — server logic only
Every .py file runs on the server.
Handles: routing, business logic, API calls, data processing.
NEVER contains: HTML strings, CSS strings, JavaScript strings.

### HTML — screen structure only (templates/ folder)
Jinja2 templates. {{ variable }}, {% for %}, {% if %}.
NEVER contains: business logic, API calls, raw data.
One file per screen.

### CSS — appearance only (static/css/ folder)
All styling in .css files.
NEVER in <style> tags in HTML.
NEVER as Python strings.
Use CSS variables for the colour palette.

### JavaScript — browser interactivity only (static/js/ folder)
One .js file per feature domain.
Communicates with Python via fetch() to /api/* routes only.
NEVER contains: business logic, credentials, hardcoded data.
NEVER written as Python strings inside Flask routes.
(This is the biggest single improvement over the current codebase —
 the current dashboard.py has thousands of lines of JS as strings.)

### JSON — configuration and data exchange
config.json — credentials (never committed)
compliance_rules.json, ip_rules.json, valid_values.json — rules (committed)
All external API responses arrive as JSON.

---

## THE COMPLETE TARGET FOLDER STRUCTURE

```
altascraper/
│
├── main.py                        # starts Flask, registers all blueprints
│                                  # < 40 lines, nothing else
├── CLAUDE.md                      # standing rules (already written)
├── README.md                      # setup guide for new team members
├── requirements.txt               # pinned dependencies
├── .gitignore                     # excludes all credentials + caches
├── .env.example                   # key names only, no values
│
│   (root-level credentials — NEVER committed)
│   config.json
│   service_account.json
│
├── config/
│   ├── settings.py                # loads config.json, validates required keys
│   │                              # raises clear error if a key is missing
│   └── constants.py               # PORT, timeouts, max rounds, etc.
│
├── routes/                        # HTTP ROUTING ONLY
│   ├── __init__.py                # registers all blueprints with Flask
│   ├── auth_routes.py             # /login  /logout  /healthz
│   ├── listing_routes.py          # /run /row /rows /approve /edit
│   │                              # /delete /clear_empty /suggest /ask
│   │                              # /schema /input_sheet /view
│   ├── genimage_routes.py         # /genimage/*  (14 routes)
│   ├── miles_routes.py            # /miles/*  (9 routes)
│   ├── ppc_routes.py              # /ppc/*  (5 routes)
│   ├── inventory_routes.py        # /inventory/*  (4 routes)
│   ├── accounts_routes.py         # /accounts/*  (8 routes)
│   ├── media_routes.py            # /media/*  (4 routes)
│   ├── optimize_routes.py         # /optimize/*  (4 routes)
│   ├── drive_routes.py            # /drive/*  (3 routes)
│   ├── aplus_routes.py            # /aplus/*  (2 routes)
│   ├── settings_routes.py         # /settings/*  /ai/*  /admin/*
│   └── ui_routes.py               # /  /ui  /stop  /save_default
│
│   RULE: Every route function is maximum 15 lines.
│   Receives request → validates input → calls one service → returns response.
│   Zero business logic. Zero HTML generation. Zero API calls.
│
├── services/                      # BUSINESS LOGIC — decisions and orchestration
│   ├── __init__.py
│   ├── listing_service.py         # orchestrates: source → generate → validate
│   ├── autofix_service.py         # the suggest/apply/preview loop (8 rounds max)
│   ├── brand_service.py           # brand-mode listing (wraps brand_listing.py)
│   ├── image_service.py           # image generation orchestration
│   ├── miles_service.py           # Miles Lubricants: harvest + generate
│   ├── ppc_service.py             # campaign building + audit + deliverables
│   ├── inventory_service.py       # FBA replenishment + forecasting
│   ├── optimize_service.py        # live listing optimisation (SQP-driven)
│   ├── aplus_service.py           # A+ content generation
│   └── account_service.py         # account management, brand detection
│
│   RULE: Services never import from routes/ or templates/.
│   Services call domain modules, api/, and repositories/.
│   Services contain ALL business rules from CLAUDE.md.
│
├── listing/                       # LISTING ENGINE — the core of the app
│   ├── __init__.py
│   ├── shaper.py                  # shape_by_schema — reads live Amazon schema,
│   │                              # folds values into exact required shape.
│   │                              # NEVER guesses. Always reads the schema.
│   ├── builder.py                 # build_api_attributes — assembles full payload
│   ├── compliance.py              # IP rules, compliance_rules.json checking
│   ├── hazmat.py                  # battery/chemical detection, hazmat fields
│   ├── brand_validator.py         # validates brand ≠ product description,
│   │                              # falls back to account default brand
│   └── schema_cache.py            # caches Amazon schemas locally to reduce
│                                  # SP-API calls (schema rarely changes)
│
├── domain/                        # DOMAIN MODULES — already exist, just moved
│   ├── __init__.py
│   ├── accounts.py                # ← move from root (already good)
│   ├── ai_providers.py            # ← move from root (already good)
│   ├── brand_analytics.py         # ← move from root (already good)
│   ├── brand_listing.py           # ← move from root (already good)
│   ├── brand_profile.py           # ← move from root (already good)
│   ├── inventory_module.py        # ← move from root (already good)
│   ├── ppc_module.py              # ← move from root (already good)
│   ├── ppc_deliverables.py        # ← move from root (already good)
│   ├── shopify_import.py          # ← move from root (already good)
│   ├── miles_import.py            # ← move from root (already good)
│   ├── image_gen.py               # ← move from root (already good)
│   ├── unified_export.py          # ← move from root (already good)
│   └── template_schema.py         # ← move from root (already good)
│
├── api/                           # EXTERNAL SERVICES — one file per service
│   ├── __init__.py
│   ├── amazon_sp.py               # ALL SP-API calls:
│   │                              #   fetch_schema(product_type, marketplace)
│   │                              #   preview_listing(payload, account)
│   │                              #   submit_listing(payload, account)
│   │                              #   get_asin_data(asin, marketplace)
│   │                              #   get_fba_inventory(account)
│   │                              #   get_orders(account, days)
│   ├── google_sheets.py           # ALL Sheets operations
│   ├── google_drive.py            # ALL Drive operations
│   ├── ebay_api.py                # eBay Browse + Sell APIs
│   └── openrouter.py              # wraps ai_providers.py cleanly
│
├── repositories/                  # DATA ACCESS — read/write only, no logic
│   ├── __init__.py
│   ├── listing_repo.py            # read/write listing rows
│   ├── input_repo.py              # read source SKUs from input sheet
│   ├── config_repo.py             # account config, tab mappings
│   └── cache_repo.py              # local JSON caches
│                                  # (miles_bundles_store.json etc)
│
├── templates/                     # HTML — one file per screen
│   ├── base.html                  # layout: navbar, sidebar, account selector
│   ├── dashboard.html             # main screen (currently rendered at /)
│   ├── listing_row.html           # single listing detail view
│   ├── miles.html                 # Miles Lubricants panel
│   ├── ppc.html                   # PPC campaigns and agent
│   ├── inventory.html             # FBA replenishment + forecast
│   ├── genimage.html              # image generation studio
│   ├── aplus.html                 # A+ content generator
│   ├── accounts.html              # account management
│   ├── settings.html              # AI settings, logic settings, eBay settings
│   └── login.html                 # login screen (already exists)
│
├── static/
│   ├── css/
│   │   ├── app.css                # global styles, nav, sidebar, CSS variables
│   │   ├── listings.css           # listing cards, status chips, filters
│   │   ├── genimage.css           # image studio styles
│   │   └── ppc.css                # PPC table and chart styles
│   │
│   └── js/
│       ├── app.js                 # global: account switcher, nav, sidebar,
│       │                          # SSE streaming handler (shared by all features)
│       ├── listings.js            # run/retry/approve/edit/delete listing actions
│       ├── autofix.js             # auto-fix progress, round trace display
│       ├── genimage.js            # image generation studio interactions
│       ├── miles.js               # Miles harvest/generate/results
│       ├── ppc.js                 # campaign builder, agent chat
│       ├── inventory.js           # replenishment table, forecast chart (Chart.js)
│       ├── optimize.js            # live listing optimisation
│       ├── aplus.js               # A+ content generation
│       └── settings.js            # AI settings, account management
│
└── tests/
    ├── __init__.py
    ├── conftest.py                 # mock SP-API, mock Sheets, mock Claude
    ├── test_shaper.py              # shape_by_schema vs real Amazon schemas
    ├── test_compliance.py          # IP and compliance rule checking
    ├── test_autofix.py             # auto-fix loop: rounds, stall detection
    ├── test_brand_validator.py     # brand name validation
    └── test_ppc_module.py          # campaign building output
```

---

## THE FEATURES — EACH ONE COMPLETELY SEPARATE

### Feature 1 — Dropshipping Listing Generation
Source: eBay competitor ASIN scrape → Claude writes copy → SP-API validates

Files that OWN this feature:
  services/listing_service.py
  listing/shaper.py
  listing/builder.py
  listing/compliance.py
  listing/brand_validator.py
  api/amazon_sp.py
  repositories/listing_repo.py
  templates/dashboard.html
  static/js/listings.js

Does NOT touch: PPC, inventory, image gen, Miles, brand mode.

Business rules hardcoded here:
  - Always requirements: "LISTING" (create new product)
  - Never merchant_suggested_asin
  - Never fake UPCs — use GTIN exemption
  - Brand fallback: if detected brand looks like a description, use
    account default brand from config.json

---

### Feature 2 — Brand-Mode Listing Generation
Source: Shopify export → Claude writes brand-aware copy (keeps brand name,
uses brand's own identifiers, gates claims to evidence)

Files that OWN this feature:
  domain/brand_listing.py       (already separated — just move to domain/)
  domain/brand_profile.py       (already separated)
  domain/brand_analytics.py     (already separated)
  domain/shopify_import.py      (already separated)
  services/brand_service.py     (new — thin orchestration wrapper)

Does NOT touch: dropshipping path, Miles, PPC, inventory.

Key distinction from dropshipping:
  Brand mode KEEPS the brand name, uses the brand's own identifiers,
  does NOT de-brand the product. These are two completely separate
  generation paths that must never be mixed.

---

### Feature 3 — Auto-Fix Loop
Runs after any listing generation. Up to 8 rounds of:
preview → read errors → AI suggests values → apply to sheet → repeat.

Files that OWN this feature:
  services/autofix_service.py
  api/amazon_sp.py (preview calls)
  api/openrouter.py (suggestion calls)
  repositories/listing_repo.py
  static/js/autofix.js (real-time progress via SSE)

Key rules:
  - Non-enforced Amazon messages (enforcements.actions = empty) are
    WARNINGS not errors. Label [W], do not count, do not fix.
  - Deterministic fields (rebuilt from fixed data every round) are
    flagged "manual fix needed" after round 1, not retried 8 times.
  - Never change listing mode (requirements) to resolve an API error.
  - Business model is not negotiable via API error messages.

---

### Feature 4 — Image Generation
AI-generated main images using Google Gemini (via image_gen.py).
Strategise → generate concept → refine → save to media library.

Files that OWN this feature:
  domain/image_gen.py           (already separated — just move)
  services/image_service.py     (new orchestration wrapper)
  routes/genimage_routes.py     (14 routes extracted from dashboard.py)
  templates/genimage.html
  static/js/genimage.js

Completely separate from: listing generation, PPC, Miles.
image_gen.py is already well-written as a standalone swappable module.
To switch from Gemini to OpenAI, only image_gen.py changes.

---

### Feature 5 — PPC Campaign Management
DataDive/Helium10/SQP ingestion → keyword bucketing → bulk upload CSV.
Also: PPC agent (conversational), deliverables (xlsx/docx/pptx).

Files that OWN this feature:
  domain/ppc_module.py          (already separated — just move)
  domain/ppc_deliverables.py    (already separated — just move)
  services/ppc_service.py       (new thin wrapper)
  routes/ppc_routes.py          (5 routes extracted)
  templates/ppc.html
  static/js/ppc.js

STANDING RULE: Never set or change bids or budgets without explicit
user instruction specifying the exact new value.

---

### Feature 6 — Inventory + Forecasting
FBA replenishment engine. SP-API pulls FBA stock + orders data.
Calculates reorder points, days of cover, seasonal uplift.
Forecast chart: actual sales vs projected, user-selectable period.

Files that OWN this feature:
  domain/inventory_module.py    (already separated — just move)
  services/inventory_service.py (new thin wrapper)
  routes/inventory_routes.py    (4 routes extracted)
  templates/inventory.html
  static/js/inventory.js        (includes Chart.js forecast graph)

Chart.js loaded from cdnjs CDN. Two lines: actual (solid navy) +
forecast (dashed). Period selector: 7d / 30d / 90d / 6mo / 1yr.

---

### Feature 7 — Miles Lubricants
Harvests product data from mileslubricants.com (SDS/TDS PDFs from Drive),
generates industrial lubricant listings (hazmat-aware, SDS-driven).

Files that OWN this feature:
  domain/miles_import.py        (already separated — just move)
  services/miles_service.py     (new — includes Drive scanning fix)
  routes/miles_routes.py        (9 routes extracted)
  templates/miles.html
  static/js/miles.js

THE DRIVE SCANNING FIX MUST STAY:
When Generate is clicked, scan Google Drive directly for harvested
item folders. Do NOT rely only on miles_bundles_store.json.
If a SKU folder exists in Drive but is missing from the local store,
read it from Drive and generate. Cross-tab dedup across ALL tabs.

---

### Feature 8 — Live Listing Optimisation
Pulls a live Amazon listing's current content via SP-API catalog API.
Compares it to what's in the sheet. Fills gaps, suggests improvements
based on SQP data, pushes updates.

Files that OWN this feature:
  services/optimize_service.py
  routes/optimize_routes.py     (4 routes extracted)
  static/js/optimize.js

---

### Feature 9 — A+ Content Generation
Generates Amazon A+ content modules from product data and brand assets.

Files that OWN this feature:
  services/aplus_service.py
  routes/aplus_routes.py        (2 routes extracted)
  templates/aplus.html
  static/js/aplus.js

---

### Feature 10 — Account Management
Multiple Amazon seller accounts, each with own SP-API creds,
marketplaces, brands, Sheets. Account switcher in the UI sidebar.

Files that OWN this feature:
  domain/accounts.py            (already separated — just move)
  services/account_service.py   (new thin wrapper)
  routes/accounts_routes.py     (8 routes extracted)
  templates/accounts.html
  static/js/settings.js (shared with settings feature)

---

### Feature 11 — Authentication
Simple team password login. Flask-Login session management.
All routes redirect to /login if not authenticated.
Session expires after 8 hours.

Files that OWN this feature:
  routes/auth_routes.py
  templates/login.html
  config/settings.py (reads team credentials from config.json)

---

## THE DATA FLOW — LISTING GENERATION END TO END

```
USER clicks Run in browser
  ↓
JavaScript (listings.js)
  fetch('/run/generate', {method: 'POST', body: {skus: [...]}})
  ↓
Route (routes/listing_routes.py)   ← max 15 lines
  listing_service.run(skus, account, mode)
  ↓
Service (services/listing_service.py)
  For each SKU:
  1. input_repo.get_row(sku)             → source data from input sheet
  2. amazon_sp.fetch_schema(product_type) → live Amazon schema
  3. openrouter.generate_copy(data)      → AI writes title/bullets/etc
  4. listing/builder.build(copy, schema) → assembles payload
  5. listing/compliance.check(payload)   → flags IP/compliance issues
  6. listing_repo.save(sku, payload)     → writes to output sheet
  ↓
autofix_service.run(sku) [automatic after generate]
  Round 1-8:
  1. amazon_sp.preview(payload) → Amazon validates, returns errors
  2. openrouter.suggest_fix(errors, schema) → AI suggests values
  3. listing_repo.apply(sku, suggestions)   → writes to sheet
  4. Repeat until API_READY or 8 rounds done
  ↓
Route returns JSON result
  ↓
JavaScript updates listing card: green badge, status chip, trace visible
```

---

## THE PHASED BUILD ORDER

### Phase 1 — Foundation (2-3 days)
Create folder structure. Set up Git. Create main.py (< 40 lines).
Set up config/settings.py. Set up auth. Confirm app starts.
COMMIT: "Phase 1 — foundation, auth, config loading"

### Phase 2 — Move existing modules to domain/ (1 day)
Move all 13 already-separated modules from root to domain/.
Update imports everywhere. Confirm app still starts.
No logic changes — pure file moves.
COMMIT: "Phase 2 — existing modules moved to domain/"

### Phase 3 — Extract routes from dashboard.py (3-4 days)
Extract all 98 routes from dashboard.py into routes/ files.
Each route file is one domain (genimage, miles, ppc etc).
Dashboard.py routes are deleted as they move.
After each route file is complete, confirm those endpoints still work.
COMMIT per route file: "Phase 3 — extracted [domain] routes"

### Phase 4 — Extract HTML and JS from dashboard.py (3-4 days)
Pull all HTML out of Python strings into templates/*.html.
Pull all JavaScript out of Python strings into static/js/*.js.
Use render_template() in routes.
After each template, confirm the screen still renders correctly.
COMMIT per template: "Phase 4 — extracted [screen] template"

### Phase 5 — Extract listing engine (3-4 days)
Break amazon_listing_generator.py into listing/ modules.
Start with listing/shaper.py (most tested, most isolated).
Then listing/builder.py, listing/compliance.py, listing/hazmat.py.
Write tests in tests/test_shaper.py as you go.
COMMIT per module: "Phase 5 — extracted [module]"

### Phase 6 — Services layer (2-3 days)
Create services/*.py as thin orchestration wrappers.
Routes call services. Services call domain modules and api/.
Routes become max 15 lines each.
COMMIT: "Phase 6 — services layer complete"

### Phase 7 — Hosting (1-2 days)
VPS (Hetzner CX22 €4.35/mo or DigitalOcean $6/mo).
gunicorn + nginx + systemd + Let's Encrypt HTTPS.
Team accesses at https://listings.yourdomain.com.
COMMIT: "Phase 7 — deployed to production"

---

## THE FIRST PROMPT TO GIVE CLAUDE CODE

Paste this exactly on day one of the rebuild:

```
Read CLAUDE.md and ARCHITECTURE_PLAN.md completely before doing anything.

We are rebuilding AltaScraper with proper architecture.
The existing code in the AltaScraper folder is the reference.
We are building a new clean version alongside it — do not modify
the existing files yet.

Today: Phase 1 only.

1. Create this exact folder structure (empty __init__.py files,
   placeholder comments in each .py file explaining its job):
   config/ routes/ services/ listing/ domain/ api/ repositories/
   templates/ static/css/ static/js/ tests/

2. Create main.py — starts Flask, registers blueprints, < 40 lines.

3. Create config/settings.py — loads config.json from the root,
   raises a clear readable error if any required key is missing.
   Required keys: anthropic_api_key, accounts (list), google_sheets.

4. Create routes/auth_routes.py — /login GET+POST, /logout, /healthz.
   Copy the login logic from dashboard.py lines 106-119.

5. Create templates/login.html — clean professional login screen
   matching the navy/corporate design from the UI spec.

6. Confirm the app starts: python main.py
   Confirm login screen loads at http://127.0.0.1:5000

7. Set up Git:
   git init
   git add .gitignore (create it first excluding config.json,
   service_account.json, __pycache__, *.pyc, miles_bundles_store.json)
   git commit -m "Phase 1 — foundation, auth, config loading"

Rules from the very first file:
- No HTML in Python strings
- No JavaScript in Python strings
- No business logic in routes
- No credentials in any committed file
- py_compile check after every file
- Explain in plain English what each file does as you create it
```

---

## WHAT THE OLD CODE HAD WRONG — NEVER REPEAT

Looking at dashboard.py specifically:

1. 98 routes in one file — unnavigable.
   FIX: 12 route files, max 10 routes each.

2. HTML as Python f-strings (thousands of lines).
   FIX: templates/*.html with Jinja2.

3. JavaScript as Python strings inside route functions.
   FIX: static/js/*.js files, loaded by templates.

4. Business logic inside route functions.
   (The /miles/run route is 376 lines — a route should be 15.)
   FIX: services layer. Routes call services.

5. No separation between dropshipping mode and brand mode.
   FIX: listing_service.py for dropshipping,
        brand_service.py for brand mode. Never mixed.

6. Guessing Amazon schema shape when a value is rejected.
   FIX: listing/shaper.py always reads the live schema.
        tests/test_shaper.py tests against real captured schemas.

7. No tests.
   FIX: tests/ folder with a test for every critical function.
        Run pytest before every commit.
