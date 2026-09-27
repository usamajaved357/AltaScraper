---
name: amazon-schema-first
description: CLAUDE.md Rule 4 workflow for any Amazon rejection or uncertain Amazon API behaviour (SP-API, Listings, Product Type Definitions, Ads, Reports) - capture the raw schema or reply with a temporary read-only probe, show it, build the fix from what it literally says, then remove the probe. Use when Amazon says a value is invalid / does not match / a field is required, or before relying on any Amazon field name or shape.
---

# amazon-schema-first

**Problem it solves:** hours lost guessing Amazon's field names, value shapes
and units from memory or docs (the leg/cable/decimal_value bugs), and field
names invented from Amazon's prose (the "The"/"Your" phantom fields).

**Modifies files:** only a temporary probe script in
`<main checkout>/active/probes/` (never in the repo), deleted at the end.
The fix itself is made afterwards through the normal flow.

## Inputs
Account id, marketplace, SKU, product type, the exact Amazon message/code, and
the payload that was sent (the PDP's "exact payload" view or the payload column).

## Procedure
1. **Blocked first?** Check docs/known-issues.md "Blocked outside the code": most
   APIs 403 on jack_uk (roles), Finance works only on nestwell_goods, Ads only
   on nestwell_goods. A 403 [ROLE] is not a code bug. `POST /sp_diagnose` or
   "Diagnose SP-API" tells which layer fails.
2. **Existing probe?** The repo has about 57 `probe_*.py` scripts (probe_schema.py,
   probe_enum*.py, probe_barcode_sent.py, ...). Reuse one if it asks the same
   question. They call live APIs: run only read calls, never a PUT/PATCH/POST
   that changes a listing, price, stock, bid or budget.
3. **Capture raw:** write a small read-only probe to `active/probes/` that
   prints Amazon's RAW JSON for the failing field (Product Type Definitions
   schema for `<pt>` in `<marketplace>`, or the listing's `issues`, or the
   report columns) before any of our code touches it. Run it once. Save the
   output to `active/probes/<topic>-raw.json`.
4. **Read the schema:** the exact property name (`value` vs `decimal_value`),
   array vs object, required members, the enum list (allowed units/values),
   `marketplace_id`/`language_tag` requirements.
5. **Compare**, in this exact format for the owner:
   - "Here is what Amazon's schema actually says" (the raw excerpt)
   - "Here is what we were sending" (the payload excerpt)
   - "Here is the difference"
   - "Here is the fix" (plain English)
6. Structured fields only: attribute names come from the schema /
   `attributeNames`, never from message text.
7. Hand the comparison to the `listing-payload-guardian` agent with the fix diff.
8. **Remove the probe** once the fix is confirmed (keep the raw capture in
   active/ until the task closes).

## Output
The four-part comparison, the raw capture path, and whether the fix is
confirmed by a second capture / preview.

## Persist afterwards
The durable fact (field shape, what Amazon accepts/refuses, per-account API
availability) -> docs/architecture.md or docs/known-issues.md; a decision the
owner made about it -> docs/decisions.md.
