# AltaScraper — PDP Overlay: Match the Mockup EXACTLY

## THE PROBLEM

The PDP overlay was supposed to match `altascraper-pdp-mockup.html` but it doesn't. Almost nothing matches — the width, the tabs, the field layout, the input sizes, the sidebar width, the attribute arrangement. This task is: open the mockup in a browser, open the live app beside it, and make them identical. Not similar. Identical.

---

## STEP 1: Open the mockup and read every pixel

Open `altascraper-pdp-mockup.html` in Chrome. This is the target. Every CSS value, every spacing, every element order in this file is intentional and must be reproduced in the live app. Do not interpret, do not improve, do not deviate.

---

## STEP 2: Fix the overlay container

The PDP is currently full-width. The mockup is a centered panel.

```css
/* The overlay backdrop */
.pdp-overlay, #pdp-overlay, [whatever the overlay container is] {
  position: fixed; inset: 0; z-index: 78;
  background: rgba(0,0,0,.6);
  display: flex; justify-content: center;
  padding: 40px 60px;
  overflow-y: auto;
}

/* The panel itself */
.pdp-panel, #pdp-panel, [whatever the panel element is] {
  background: var(--panel);
  border-radius: 10px;
  width: 100%;
  max-width: 680px;
  box-shadow: 0 8px 40px rgba(0,0,0,.5);
  display: flex; flex-direction: column;
  align-self: flex-start;
}
```

If the current PDP uses a different structure (e.g. a full-page overlay instead of a centered card), restructure it to match the mockup. The dark backdrop MUST be visible on both sides of the panel.

---

## STEP 3: Fix the tabs

The current app has 5 tabs: `Product details | Images | Attributes | Offer | Compliance`

This is WRONG. Match Amazon exactly:

**Normal listing (no variations):** 4 tabs
```
Product Details | Images | Offer | Safety & Compliance
```

**Listing with variations:** 5 tabs
```
Product Details | Images | Variations | Offer | Safety & Compliance
```

There is NO "Attributes" tab. All attributes (brand, EAN, material, colour, weight, included components, special features, generic keywords, etc.) are displayed on the **Product Details** tab, below the title/highlights/bullets/description fields. The mockup shows this — scroll down on Product Details and you see all the attribute rows.

Rename "Compliance" to "Safety & Compliance" to match Amazon.

Remove the Attributes tab entirely. Move everything it currently shows into Product Details, below the description.

---

## STEP 4: Product Details tab — match the mockup field by field

The Product Details tab in the mockup shows these sections IN THIS ORDER, top to bottom. Every field uses the full width of the content area. Every field has:
- A label with question mark tooltip (from Amazon's schema `description`)
- Grey text above showing what Amazon currently has live (from `summaries`)
- The input box (full width)
- Character counter where applicable

### Section 1: Item name
```
* Item name (?)                    67 / 200 · fully indexed · highest weight
[grey: current Amazon live value]
[full-width textarea, auto-height]
```

### Section 2: Item Highlight
```
Item Highlight (?)                 108 / 125 · indexed · own weight
[grey: current Amazon live value]
[full-width input]
```

### Section 3: Bullet Points
```
* Bullet Point (?)                 ⚠ 1971 / 1000 bytes indexed
[grey: bullet 1 live value]
[full-width textarea, auto-height, no scroll]
[grey: bullet 2 live value]
[full-width textarea, auto-height, no scroll]
[grey: bullet 3 live value]
[full-width textarea, auto-height, no scroll]
... up to 5
Add More | Remove Last
```

Each bullet is a SEPARATE textarea that auto-grows to fit content. No scrollbar. Use `field-sizing: content; resize: none; overflow: hidden;` with JS fallback.

### Section 4: Product Description
```
* Product Description (?)          324 / 2000
[full-width textarea, min-height 80px, scrollable for long content]
```

### Section 5: Attributes
Below the description, all remaining Amazon attributes display as rows:

```
     Label (?) | [full-width input]
```

Label is right-aligned in a 110px column on the left. Input fills the rest. Every attribute from the schema shows here. Required fields have red asterisk. Locked fields are greyed with lock icon.

Specific attribute rendering rules:
- **Text fields**: full-width input
- **Dropdowns** (schema has `enum`): full-width `<select>`
- **Multi-value** (schema `maxItems > 1`): stacked inputs with "Add More | Remove Last"
- **Compound fields** (e.g. Item Weight = value + unit): two separate full-width rows
- **Read-only fields**: grey background + lock icon + `readonly`

The grey live value appears above each input showing what Amazon currently has.

---

## STEP 5: Sidebar — 130px, matches mockup exactly

```
QUICK ACTIONS
  📷 Image studio
  💬 Ask Claude
  </> Raw data
───────────────
CHECKS
  🟢 Restricted
  🟡 Compliance — 1
  🔴 1 claim risk
  💬 Amazon feedback
```

Width: 130px. Font sizes: title 9px uppercase, items 11px, checks 10px. Padding: 12px 10px. The mockup has all these values — copy them.

---

## STEP 6: Hero section — compact, matches mockup

```
[100x100 image] | Title (15px bold)
                | ASIN:    B0DNJH3CRX (competitor reference)
                | SKU:     11.59_3Days_B0DNJH3CRX
                | Barcode: 4545644574860
                | Brand:   Nestwell Goods
                | [GENERATED] [Profit £3.2] [Cost £11.59] [⚠ 2 warnings]
```

Image: 100×100px. Gap between image and info: 14px. Padding: 12px 16px. Meta labels: 60px wide. Badges: 9px font, 2px 6px padding, 3px radius.

Do NOT show the "⚠ 2 warnings" TEXT. Only show warning badges with counts. The warning text line was removed in a previous task.

---

## STEP 7: API error banner — red, at top of content

When `api_errors` JSON field has entries, show:

```
🔴 Submission failed — Amazon rejected this listing
   The value provided for attribute "item_name" exceeds...
   Error code: INVALID_ATTRIBUTE_VALUE · Attribute: item_name
```

Show ONCE at the top of the content area. Do NOT duplicate the full error message next to the field — the field only gets a red border + short one-line summary.

---

## STEP 8: Footer — Cancel / Save and finish

Sticky at the bottom of the panel:

```css
.pdp-footer {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 10px 16px; border-top: 1px solid var(--line);
  background: var(--sidebar);
}
```

Two buttons: `Cancel` (ghost) and `Save and finish` (accent color).

"Edits save as you leave each box. Nothing reaches Amazon until Submit." text at the left side of the footer, matching what the app already shows.

---

## STEP 9: Remove the drawer

The right-side product detail drawer must not appear anywhere. Every path that shows product details opens this PDP overlay. After submission, show a toast notification, not a drawer. Find every call that opens the drawer and replace it.

---

## WHAT NOT TO CHANGE

- The top bar buttons (Back to listings, Preview, Auto-fix, Submit, ···) — keep as they are
- The data fetching logic — keep
- The save/edit endpoints — keep
- Python backend — don't touch unless needed for api_errors storage

## HOW TO VERIFY

1. Open `altascraper-pdp-mockup.html` in one browser tab
2. Open a listing PDP in the live app in another tab
3. Put them side by side
4. Every section — hero, tabs, sidebar, fields, footer — must be visually identical
5. Tabs are: Product Details | Images | Offer | Safety & Compliance (no Attributes tab)
6. All attributes display under Product Details, below the description
7. Panel is centered at 680px with dark backdrop on both sides
8. No right-side drawer appears anywhere
9. All inputs are full width
10. Bullet textareas auto-grow, no scrollbar
11. Grey live values appear above each input
12. Question mark tooltips on every field label
