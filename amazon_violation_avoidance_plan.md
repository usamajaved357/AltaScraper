# Amazon Account Health — Violation Avoidance Plan
## For AltaScraper + Seller Operations

---

## HOW THIS BUSINESS ACTUALLY WORKS — READ FIRST

**We create NEW ASINs under our own brands.** Jack Reacherd, Selvora, Green Haven,
Sheelady, Nestwell, AltaboltaVoo. Every listing the app generates is a new product
under a brand we own.

**Competitor data is used for research and sourcing only.** The ASIN in the SKU
(`price_days_ASIN`, e.g. `8.00_3Days_B0G1K5B7QS`) is a *reference* the generator
reads to pull product data — title, specs, images, price, fees, category, schema.
It is never the listing target. We do not piggyback, we do not create offers on
another seller's ASIN, and we never send `merchant_suggested_asin`.

This distinction changes the risk picture completely, so the whole document is
written for it:

- We are **not** exposed to the classic hijacker risks (listing on a Brand
  Registry ASIN, shipping a different product than the ASIN depicts).
- We **are** exposed to **data leakage** — competitor brand names, copyrighted
  phrasing, or unsupported claims travelling from the scraped source into our own
  copy. That is the live IP risk, and it is where the app's defences are aimed.
- We are fully exposed to **restricted/prohibited product types** and
  **regulatory documentation**, because a new ASIN under our own brand makes us
  the responsible party, not a reseller of someone else's compliant product.

> **Decision on record (10 Aug 2026): using the competitor's product images is
> accepted for now.** It is a known, deliberate trade-off, not an oversight. Do
> not re-raise it as a defect. Revisit only if Amazon or a rights-holder acts.

---

## 1. SUSPECTED INTELLECTUAL PROPERTY VIOLATIONS
**What triggers it:** Amazon's automated scan finds trademarked brand names or
copyrighted content in your listing that you don't own.

**Your real risk:** MEDIUM, and it is entirely about **leakage**. The scraper
pulls the competitor's title, specs and description; the generator can carry a
brand name straight into our copy if nothing stops it.

### App features — STATUS

**A. Competitor brand blocker — ✅ DONE**
The competitor's brand (from SP-API Catalog and the eBay source) is passed into
the IP scan and blocked across title, bullets, description and search terms.
A hit is proof, not a guess, so it flags on its own.

**B. Capitalised-word heuristic — ✅ DONE (de-noised)**
Previously reported ordinary words as suspected brands (`Father's`, `Day`,
`Christmas`, `Dad`). Contractions and possessives now reduce to their base word
and the allowlist covers normal product-copy vocabulary (923 words). Words that
are also real trademarks are deliberately excluded from the allowlist.

**C. Forbidden-phrase scan — ✅ DONE**
`ip_rules.json` comparative phrases ("compatible with", "OEM approved") scanned
across all fields including the title.

### SOP
- Never let a competitor brand name appear in any field, including backend search terms.
- If an IP complaint arrives, delete the ASIN immediately — do not edit and re-list.
- Because the ASIN is ours, an IP complaint is about our **content**, so fix the
  content and understand which field leaked.

---

## 2. RECEIVED INTELLECTUAL PROPERTY COMPLAINTS
**What triggers it:** A brand owner files a takedown.

**Your real risk:** LOW-MEDIUM. We are not on their ASIN, so the usual trigger
(hijacking a Brand Registry listing) does not apply. What remains is a rights
holder objecting to our copy, images or a design that resembles theirs.

### App features
**A. Known-complainant list — NOT BUILT**
`ip_complainants.json` — brands that have filed against us or are known
aggressive enforcers. Check the competitor ASIN's brand against it at sourcing
time and warn.

### SOP
- Maintain a "do not source from" brand list; every complaint adds that brand permanently.
- Assume a brand that files once will file again.
- Respond within 24 hours. Do not appeal without genuine authorisation documents.

---

## 3. PRODUCT AUTHENTICITY CUSTOMER COMPLAINTS
**What triggers it:** A buyer says the item is counterfeit or not genuine.

**Your real risk:** LOW-MEDIUM, and different from a reseller's. We are not
shipping an unbranded item against a branded ASIN — our ASIN is our own brand.
The risk is a **mismatch between our listing and what actually arrives**: copy or
images sourced from a competitor's better product, with a cheaper item in the box.

### App features
**A. Listing-vs-source mismatch warning — NOT BUILT**
Where the source is a branded competitor product and our supplied item is
generic, warn at sourcing: the copy may promise specifications the shipped item
does not meet.

**B. Own-brand enforcement — PARTIAL**
Brand comes from the account's brand profile (`listing/brand_validator.py`), and
the AI is instructed never to put a brand name in the title.

### SOP
- Describe what you actually ship, not what the competitor ships.
- Do not carry over specifications (materials, capacities, certifications) that
  your supplier has not confirmed in writing.
- Since the ASIN is ours, its reviews and complaints follow *us* permanently —
  a mismatch is not recoverable by switching ASINs.

---

## 4. PRODUCT CONDITION CUSTOMER COMPLAINTS
**What triggers it:** Item arrives damaged, used, or not "New".

**Your real risk:** MEDIUM for dropship/MFN — you don't inspect before shipping.

### App features
**A. Handling-time buffer — ✅ ALREADY BUILT** (handling days in the SKU format).

**B. Supplier quality tracker — NOT BUILT** (spreadsheet/Airtable, not app).
Track return and condition-complaint rate per supplier; flag above 3%.

### SOP
- Tracked shipping on every order (Evri, Royal Mail — already standard).
- Require adequate packaging; rigid mailers for fragile items.
- For eBay-sourced items, check the source seller's feedback for "not as described" before sourcing.

---

## 5. FOOD AND PRODUCT SAFETY ISSUES
**What triggers it:** Product causes injury, is unsafe, or lacks required markings.

**Your real risk:** MEDIUM-HIGH — and higher than a reseller's, because a new ASIN
under our own brand makes us the **manufacturer/responsible person** in the eyes
of UK/EU law, not a distributor.

### App features
**A. Restricted-product safety flags — ✅ DONE**
44-category restricted reference runs at generation (Shape 2). Prohibited and
conditional product types hold the row; gated and restricted types leave a note
with the documents required for the active marketplace.

**B. UK Responsible Person — NOT BUILT**
Flag at generation that a UK Responsible Person must be named on packaging.

### SOP
- No electrical products without a Declaration of Conformity from the manufacturer.
- Children's products: CPC (US) or UKCA + EN 71 (UK) **before** listing.
- Keep a compliance file per ASIN — have it ready before Amazon asks.
- Check recalls (CPSC.gov / gov.uk) and delete recalled ASINs immediately.

---

## 6. LISTING POLICY VIOLATIONS
**What triggers it:** Listing content breaks Amazon's formatting or content rules.

**Your real risk:** LOW — well covered.

### App features
- **Copy scrubber — ✅ DONE** (`scrub_listing_copy`): promotional language, contact info.
- **Title cap — ✅ DONE** (75 chars, enforced).
- **Backend search terms — ✅ DONE** (249-byte cap, no brand names, no ASINs).
- **Claims screeners — ✅ DONE**: unsupported claims, numeric grounding,
  category-aware claims, regulated claims (FDA/NSF/food-grade/21 CFR — holds the
  row), restricted phrasing (pesticide/medical wording — warns).

### SOP
- Never include competitor ASINs, URLs or brand names in any field.
- Never use promotional language (sale, discount, free shipping, limited time).
- Never include external contact information.

---

## 7. RESTRICTED PRODUCT POLICY VIOLATIONS
**What triggers it:** Product type or language triggers Amazon's restricted classification.

**Your real risk:** HIGH — historically your most common violation type.

### App features — ✅ DONE
- 44-category restricted reference (patch merged into master).
- **Shape 1** — manual pre-source check: sidebar "Check a product" → paste a
  title → per-marketplace verdict with the documents required.
- **Shape 2** — automatic at generation: PROHIBITED/CONDITIONAL hold the row,
  GATED/RESTRICTED leave a note.
- Claims screener (`restricted_phrasing.txt`, `compliance_rules.json`).

### SOP
- Run Shape 1 on every new product **before committing to source**.
- AMBER → gather the listed documents before submitting.
- RED → do not list.
- Never use pesticide/medical trigger words even when the product is neither —
  Amazon's scanner cannot tell the difference.

---

## 8. CUSTOMER PRODUCT REVIEWS POLICY VIOLATIONS
**What triggers it:** Review manipulation.

**Your real risk:** LOW if the rules are followed. **No app feature can help** —
this is purely seller behaviour.

### SOP
- No review-solicitation inserts in packages.
- No incentives of any kind for reviews.
- Never ask a buyer to change or remove a review.
- Use only Amazon's "Request a Review" button.
- Dispatch messages are clean today — keep them that way.
- Never use review clubs or manipulation services.

---

## 9. OTHER POLICY VIOLATIONS
**What triggers it:** Multiple accounts, dropship policy, price gouging.

**Your real risk:** MEDIUM — the dropship packaging rule applies directly.

### App features
**A. Dropship compliance reminder — NOT BUILT**
Note on MFN listing cards: you must be the seller of record; remove all
third-party branding and packing slips.

### SOP
- You must be the seller of record. No supplier invoices or branding in the parcel.
- Never operate multiple seller accounts without explicit Amazon approval.
- No price rises on essentials during emergencies.
- Keep account details current and consistent across accounts.

---

## 10. REGULATORY COMPLIANCE
**What triggers it:** Amazon requests compliance documents you cannot produce.

**Your real risk:** HIGH — and this is the section most changed by owning the
ASIN. As the brand owner we cannot fall back on "ask the manufacturer"; we are
the party Amazon asks.

### App features
**A. Per-marketplace document lists — ✅ DONE**
Restricted matches return the documents required for the *active* marketplace
(US → EPA/FCC/TSCA; UK → HSE/UKCA/BS 1363), no longer a single mixed list.

**B. Compliance document tracker — NOT BUILT**
Per-ASIN checklist: doc name, status (obtained / pending / unavailable), file
link. Warn before submit when required documents are unconfirmed.

**C. SP-API `getListingsRestrictions` pre-check — NOT BUILT**
Programmatic gating check at sourcing time.

### SOP
- Request the Declaration of Conformity from the supplier **before ordering**, in
  a regulated category.
- Keep a compliance folder per ASIN in Google Drive.
- Respond to document requests within 24 hours.
- UK: every product needs a UK Responsible Person. No named RP, no legal sale.

---

## PRIORITY ORDER FOR APP FEATURES

| # | Feature | Covers | Status |
|---|---|---|---|
| 1 | Restricted products Shape 1 + Shape 2 | Restricted, Regulatory, Safety | ✅ **DONE** |
| 2 | Competitor brand auto-block in generated copy | Suspected IP, Listing Policy | ✅ **DONE** |
| 3 | Prohibited/regulated claims screeners | Listing Policy, Restricted | ✅ **DONE** |
| 4 | Per-marketplace document lists | Regulatory | ✅ **DONE** |
| 5 | SP-API `getListingsRestrictions` pre-check | Regulatory, Restricted | Medium — new SP-API call at sourcing |
| 6 | Compliance document tracker per ASIN | Regulatory | Medium — new UI element |
| 7 | UK Responsible Person flag | Safety, Regulatory | Small — flag at generation |
| 8 | Known complainant database | Received IP | Small — new JSON reference file |
| 9 | Listing-vs-source mismatch warning | Authenticity | Small — comparison at generation |
| 10 | Dropship compliance reminder | Other Policy | Tiny — static note on MFN cards |

Priorities 1–4 are complete. 5–7 are the next highest-impact, because they all
address the risk that grew when we moved to owning the ASIN: we are the
responsible party for compliance, and we currently have no structured way to
prove it on demand. 8–10 are small and can be done incrementally.
