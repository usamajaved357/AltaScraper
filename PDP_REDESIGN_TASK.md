# AltaScraper — PDP Overlay Redesign

## Goal

Redesign the Product Detail Page (PDP) overlay to match Amazon Seller Central's "Edit Listing" page layout and functionality. The current overlay is too wide, inputs are inconsistently sized, API errors are invisible, multi-value fields can't add/remove entries, and attribute help text is missing.

**Reference mockup:** Open `altascraper-pdp-mockup.html` (provided alongside this file) in a browser and match it exactly.

---

## 1. Narrow the overlay — 680px max, centered

The PDP overlay currently stretches full-width across the screen. It should be a centered panel with dark backdrop visible on both sides.

**Files:** `static/css/pdp.css`

```css
.pdp-overlay {
  position: fixed; inset: 0; z-index: 78;
  background: rgba(0,0,0,.6);
  display: flex; justify-content: center;
  padding: 40px 60px;
  overflow-y: auto;
}
.pdp-panel {
  background: var(--panel);
  border-radius: 10px;
  width: 100%;
  max-width: 680px;
  box-shadow: 0 8px 40px rgba(0,0,0,.5);
  display: flex; flex-direction: column;
  align-self: flex-start;
}
```

Internal padding:
- Hero section: `12px 16px`
- Tabs: `0 16px`
- Main content area: `12px 16px`
- Sidebar: `12px 10px`, width `130px`
- Attribute labels: `110px` wide

## 2. Show Amazon's live catalogue value above every input

The small grey text above each input field shows **what Amazon is currently displaying on the product detail page** to shoppers. This is the "contributed value" — Amazon merges submissions from multiple sellers and picks the best. When this differs from the input value, the seller knows Amazon overrode their contribution.

**Data source:** SP-API `getListingsItem` with `includedData=summaries,attributes`. The `summaries` object contains the live catalogue values. The `attributes` object contains what the seller submitted.

**Implementation:**
- For every editable field, show the `summaries` value (or catalogue value) in small grey text above the input: `font-size: 10px; color: var(--ink4)`
- The input itself shows the `attributes` value (what the seller submitted or wants to submit)
- If summaries and attributes match, the grey text still shows (confirms Amazon accepted the value)
- If no summaries value exists (new listing, not yet live), don't show the grey line

```html
<div class="pdp-live">PROMIXX FORM Water Bottle - Premium Large...</div>  <!-- from summaries -->
<input class="pdp-input" value="PROMIXX FORM Sports Water Bottle 26oz">   <!-- from attributes -->
```

## 3. Question mark tooltips on every attribute field

Amazon shows a `(?)` circle next to every field label. Hovering it shows help text explaining what the field means and its requirements.

**Data source:** SP-API `getDefinitionsProductType` — the product type definition schema. Each attribute in the schema has:
- `title` — the display name (use this as the label)
- `description` — the help text (use this in the tooltip)
- Required fields are marked in the schema's `required` array

**Do NOT hardcode tooltip text.** Read it from the cached product type schema. If no schema is cached for this product type, fetch it on PDP open.

**Implementation:**
```html
<span class="pdp-help">?
  <span class="tip">{description from schema}</span>
</span>
```

CSS for the tooltip:
```css
.pdp-help {
  display: inline-flex; align-items: center; justify-content: center;
  width: 14px; height: 14px; border-radius: 50%;
  border: 1px solid var(--ink4); font-size: 9px; color: var(--ink4);
  cursor: help; margin-left: 4px; position: relative;
}
.pdp-help:hover { border-color: var(--accent); color: var(--accent); }
.pdp-help .tip {
  display: none; position: absolute; bottom: calc(100% + 6px);
  left: 50%; transform: translateX(-50%);
  background: var(--panel3); border: 1px solid var(--line);
  border-radius: 5px; padding: 6px 10px; font-size: 10px;
  color: var(--ink); width: 220px; z-index: 10;
  box-shadow: 0 4px 12px rgba(0,0,0,.4); line-height: 1.4;
}
.pdp-help:hover .tip { display: block; }
```

## 4. All input fields same full width

Every text input, textarea, and dropdown must stretch to fill the full width of its column. No short inputs for colour, weight, or other fields. The only exception is numeric+unit pairs where the schema defines them as two separate attributes (e.g. Item Weight + Item Weight Unit) — in that case, each is a separate full-width row.

```css
.pdp-input, .pdp-input-sm {
  width: 100%;
  background: var(--sidebar); border: 1px solid var(--line);
  border-radius: 4px; padding: 5px 8px; color: var(--ink);
  font-size: 12px; font-family: inherit; outline: none;
}
```

**Weight, dimensions, etc.** — if Amazon's schema defines `item_weight` as one attribute with a nested `value` and `unit`, render them as two separate full-width rows: one for the number, one for the unit dropdown. Check the actual schema structure — don't guess.

## 5. Multi-value fields — "Add More" / "Remove Last"

Some Amazon attributes accept multiple values (e.g. Included Components, Specific Uses, Bullet Points, Special Features). Each value gets its own separate input box, stacked vertically, with an "Add More" link at the bottom.

**Data source:** The product type schema's `maxItems` property on each attribute:
- `maxItems: 1` or no maxItems → single input, no Add More
- `maxItems > 1` or `type: array` → show Add More / Remove Last

**Do NOT assume which fields allow multiple values.** Read it from the schema. Amazon's schema explicitly defines this per product type — a field that allows "Add More" for a shaker bottle may not allow it for a power tool.

**Implementation:**
```html
<!-- Multi-value field with 3 entries -->
<input class="pdp-input-sm" value="Squeegee">
<input class="pdp-input-sm" value="Microfibre Scrubber" style="margin-top:4px">
<input class="pdp-input-sm" value="Telescopic Pole" style="margin-top:4px">
<div class="pdp-addmore">
  <a onclick="addFieldEntry(...)">Add More</a>
  <span>|</span>
  <a class="remove" onclick="removeLastEntry(...)">Remove Last</a>
</div>
```

"Remove Last" only shows when there are 2+ entries. "Add More" disappears when `maxItems` is reached.

## 6. Bullet points — auto-height textareas

Each bullet point is a separate textarea that automatically grows to fit its content — no scrollbars.

```css
.pdp-bullet textarea {
  width: 100%; resize: none; overflow: hidden;
  field-sizing: content; min-height: 38px;
  /* fallback for browsers without field-sizing: */
}
```

The grey live value above the first bullet shows what Amazon has live. "Add More | Remove Last" below the last bullet, controlled by schema `maxItems`.

**JS fallback** for browsers without `field-sizing: content`:
```js
textarea.addEventListener('input', function(){
  this.style.height = 'auto';
  this.style.height = this.scrollHeight + 'px';
});
```

## 7. API error banner — show submission errors

When `putListingsItem` returns errors, they must be visible on the PDP. Currently API errors are invisible — the user submits a listing, it fails, and there's no way to see why.

**Data source:** SP-API `putListingsItem` response contains an `issues` array:
```json
{
  "issues": [
    {
      "code": "INVALID_ATTRIBUTE_VALUE",
      "message": "The value provided for attribute 'item_name' exceeds the maximum...",
      "severity": "ERROR",
      "attributeNames": ["item_name"]
    }
  ]
}
```

**Store these issues** in the listing's database row (alongside warnings). When the PDP opens a listing that has stored API errors, show a red banner at the top of the content area:

```html
<div class="pdp-error">
  <i class="ti ti-alert-circle"></i>
  <div class="pdp-error-text">
    <b>Submission failed — Amazon rejected this listing</b><br>
    {issue.message}
    <div class="pdp-error-code">Error code: {issue.code} · Attribute: {issue.attributeNames[0]} · Severity: {issue.severity}</div>
  </div>
</div>
```

If there are multiple issues, show them all stacked. The banner should be dismissible after the user fixes and resubmits.

## 8. Cancel / Save and finish footer

A sticky footer at the bottom of the PDP panel with two buttons:

```html
<div class="pdp-footer">
  <button class="pdp-footer-cancel">Cancel</button>
  <button class="pdp-footer-save">Save and finish</button>
</div>
```

- **Cancel** — discards all unsaved changes and closes the PDP overlay (or reverts to the saved state)
- **Save and finish** — saves all attribute changes via SP-API `putListingsItem`, then closes

The footer is always visible at the bottom of the panel (not scrolled away).

## 9. Attribute labels — right-aligned, from schema

Every attribute label comes from the schema's `title` field. Display them right-aligned in a 110px column on the left side, with the input on the right.

Required fields show a red asterisk: `<span style="color:var(--red)">*</span>`

The schema's `required` array tells you which fields are required. Don't hardcode which ones.

## 10. Locked fields

Some attributes are read-only (e.g. Brand Name once set, External Product ID once matched). Show these with:
- Grey background on the input: `background: var(--panel2); color: var(--ink3)`
- `readonly` attribute on the input
- Lock icon next to the input: `<i class="ti ti-lock"></i>`

Which fields are locked: if the schema property has `readOnly: true`, or if the listing is LIVE and the attribute is immutable on Amazon (brand, product type, external product ID on matched listings).

## 11. Dropdowns for enumerated fields

Some attributes have a fixed set of allowed values (Unit Count Type, Weight Unit, etc.). The schema defines these as `enum` arrays or `oneOf` arrays.

Render these as `<select>` dropdowns, not free-text inputs. Read the allowed values from the schema.

## 12. Grouped attributes

Amazon groups some attributes under a heading (e.g. "Item Weight" contains both the value and unit as sub-attributes, "Government Contract Name and Number" groups name + number).

If the schema defines a group (an object-type attribute with sub-properties), render a group heading with the sub-fields indented below it, matching Amazon's layout.

---

## Data flow summary

| What | Source | Where it shows |
|------|--------|---------------|
| Field labels | Schema `title` | Left column, right-aligned |
| Field help tooltips | Schema `description` | Question mark hover popup |
| Required marker (*) | Schema `required` array | Red asterisk on label |
| Multi-value (Add More) | Schema `maxItems` / `type: array` | Add More / Remove Last links |
| Allowed values (dropdown) | Schema `enum` / `oneOf` | `<select>` dropdown |
| Read-only fields | Schema `readOnly` or immutable attributes | Grey input + lock icon |
| Grey live value | SP-API `summaries` (Catalog Items) | Small grey text above input |
| Input value | SP-API `attributes` (Listings Items) | Input/textarea value |
| API errors | SP-API `putListingsItem` response `issues` | Red error banner |
| Grouped fields | Schema object-type attributes | Group heading + indented sub-fields |

**Nothing is assumed. Everything comes from Amazon's API.**

---

## What NOT to change

- The PDP top bar (Back to listings, Preview, Auto-fix, Submit, ···) — keep as is
- The PDP hero section (image, title, ASIN, SKU, barcode, brand, badges) — keep but tighten padding
- The PDP tab structure (Product details, Images, Attributes, Offer, Compliance) — keep
- The sidebar (Quick Actions + Checks) — keep but narrow to 130px
- The warning system — keep
- Any Python/backend code unless needed for:
  - Storing API errors from putListingsItem
  - Caching product type schemas
  - Serving summaries data to the frontend

## Files touched

| File | Changes |
|------|---------|
| `static/css/pdp.css` | Overlay centering, 680px max-width, all new field styles |
| `static/js/pdp.js` | Render attributes from schema, Add More/Remove Last, auto-height textareas, error banner, live values |
| `static/js/drawer_attributes.js` | May need updates if it renders the attribute editor |
| `routes/listing_routes.py` | Store API errors from putListingsItem in listing row |
| `data/store.py` | Add `api_errors` column or use existing `warnings` JSON |
| Backend schema cache | Cache `getDefinitionsProductType` responses, serve to frontend |

## How to verify

1. Open any listing's PDP at `/w/{workspace}/listing/{sku}`
2. **Overlay is 680px wide**, centered, with dark backdrop on both sides
3. **Every field has a question mark** — hover it to see help text from Amazon's schema
4. **Grey text above every input** shows what Amazon has live (for live listings)
5. **All inputs are full width** — no short inputs for colour, weight, etc.
6. **Weight** is two separate rows: Item Weight (input) + Item Weight Unit (dropdown)
7. **Multi-value fields** (Included Components, Specific Uses, etc.) show "Add More" — click to add a new input. "Remove Last" removes the last one
8. **Bullet points** are auto-height textareas — no scrollbar, they grow with content
9. **Submit a listing with an error** (e.g. title over 200 chars) → red error banner appears showing the exact Amazon error message, code, and affected attribute
10. **Cancel** button reverts all changes instantly
11. **Save and finish** submits to Amazon and closes
12. **Required fields** show a red asterisk — check against schema, don't hardcode
13. **Dropdowns** appear for fields with enumerated values (unit types, etc.)
14. **Locked fields** show grey background + lock icon for read-only attributes
15. Compare side-by-side with `altascraper-pdp-mockup.html` — should match
