# Product context

What the business is and who the app serves. Owned by the owner; Claude
proposes changes. **Rule 1 (the listing business model) lives in CLAUDE.md,
not here**: a test reads it there.

Sources: the old CLAUDE.md §9, memory notes (skus-are-not-unique-across-accounts,
aplus-api-not-granted, advertising-api-not-connected, orbit-features-not-built,
vat-rate-per-account, oauth-multitenant, explain-shorter).

---

## The owner

- Talha, Sahiwal, Punjab, Pakistan. Not a programmer: wants the question
  answered first, in short plain sentences (CLAUDE.md Rule 5).
- Tests on the live site (app.altascraper.com), not on a local copy.
- Writes task instructions in `read.txt` in the main checkout.

## The operation

Multi-platform e-commerce: Amazon US/UK/EU, eBay UK/US/AU, TikTok Shop. This app
is the Amazon side: it creates new listings under his own brands, prices them,
tracks orders, profit, stock, PPC and competitors.

**UK entities**
- FLIPX LTD
- Green Haven Goods Ltd (CRN 16578100, director Nida Mustafa) — the
  `nestwell_goods` account; also the developer of record for the SP-API app
- Selvora Limited (CRN 16977772, director Rida Rasheed) — `selvora_limited`

**Brands:** Jack Reacherd, Selvora, Green Haven, Sheelady, AltaboltaVoo, and others.

**Amazon accounts (workspaces)**

| Account id | Seller / market | Notes |
|---|---|---|
| jack_uk | A34CMN3Q5Q4U3Z, UK (marketplace A1F83G8C2ARO7P) | VAT rate 0.2. SP-API roles missing for most APIs (see known-issues). |
| sheelady_us | A1W1VC2O2BR7M2, US | |
| nestwell_goods | UK/EU | The account most APIs work on; the usual measuring account. Only account with Advertising credentials (6 Sep 2026). Not VAT-registered. |
| selvora_limited | UK | Not VAT-registered. |
| headbanger_lures, miles_lubricants | | Borrow another account's SP-API app. Miles Lubricants has its own supplier-specific import/template logic (domain/miles_import.py, routes/miles_routes.py, routes/miles_template_routes.py, static/js/miles.js; `/miles/*`). |

**The owner runs the same product on two of his own accounts** and may reuse the
same SKU. That is his manual practice, not the app piggybacking; it does not
conflict with Rule 1. It does mean a SKU never identifies an account.

## Who uses the app

Signed-in users with roles: owner, manager, lister, viewer (docs/security.md).
Third-party sellers can connect through Amazon OAuth (the Amazon app is still in
draft).

## Related businesses and references

- **ALTAVOUR** — Amazon agency (brand recovery, $12K fixed 90-day engagement).
- **Full Circle Agency (Houston)** — the owner works there as a manager.
- **Orbit** (fullcircleorbit.com) — the reference product whose screens the app
  has been matching. Captures and specs are in docs/specs/ (orbit_*.md). Three
  Orbit screens are deliberately not built: Scout (needs a paid market-data
  source), Vendor B2B/B2C (Vendor Central, not applicable to 3P sellers), and Dr
  PPC was built ahead of its Advertising API credentials.

## What the app is not

- Not an arbitrage / offer-only lister (CLAUDE.md Rule 1).
  `amazon_violation_avoidance_plan.md` was written as an arbitrage playbook and
  over-rates some risks for how this app works (docs/decisions.md).
- Not a bid/budget manager: PPC is read-only (CLAUDE.md Rule 8).
