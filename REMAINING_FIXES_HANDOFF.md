# AltaScraper — Remaining Fixes Handoff

## Reference files

- `altascraper-order-detail-v2.html` — the target layout for order detail panels
- `altascraper-pdp-mockup.html` — the target layout for the PDP overlay
- `altascraper-listings-mockup.html` — the target layout for the listings page

Open each in a browser alongside the live app and close every visual gap.

---

## 1. Orders page — match the mockup

The expanded order detail panel doesn't match the mockup. Fix these gaps:

### 1a. Breakdown bar colors must match the Sourcing/Repricer page

The Sourcing page uses:
- **Cost/Supplier** = blue/teal (`#5b8fa8`)
- **Referral/Fee** = coral/salmon (`#d4735a`)
- **Profit** = green (`var(--ok)` / `#7fd1a0`)

The orders page currently uses different colors. Change them to match sourcing exactly. These same three colors must be used everywhere a cost/fee/profit bar appears — orders, sourcing, revenue calculator. One palette, no drift.

### 1b. Supplier table — full table format, not collapsed

The mockup shows a proper table with columns:

```
#  |  Supplier  |  You pay  |  Dispatch  |  Stock  |  You keep
```

The live app currently collapses this to one line ("1 supplier · best GBP 22.99 · shopzonearena"). Show the full table.

Shipping details for each supplier should use clean tagged pills under the supplier name instead of a wall of text:

**Current (hard to read):**
```
Free Royal Mail Tracked 48 · arrives Mon 7 Sep to Wed 9 Sep to B11AA · 5 days handling · 10 left
```

**Target (tagged pills):**
```html
<span class="sup-ship-tag"><i class="ti ti-truck"></i> Free Royal Mail Tracked 48</span>
<span class="sup-ship-tag"><i class="ti ti-calendar"></i> Arrives Mon 7 Sep – Wed 9 Sep</span>
<span class="sup-ship-tag"><i class="ti ti-map-pin"></i> to B11AA</span>
<span class="sup-ship-tag"><i class="ti ti-clock"></i> 5d handling</span>
```

Each pill: `font-size: 9px; padding: 1px 5px; background: var(--panel2); border-radius: 3px; color: var(--ink2)` with a small icon. These sit in a flex row under the supplier name, wrapping if needed.

### 1c. Delivery line — add spacing between segments

The delivery line currently blends together. Add clear visual separation:

```html
<div class="delivery">
  <i class="ti ti-truck-delivery"></i>
  Post by <b>08 Sept 2026, 03:59</b>
  <span class="days-left">(4 days left)</span>
  <span class="delivery-sep">·</span>
  Must arrive by <b>11 Sept 2026</b>
  <span class="delivery-sep">·</span>
  Going to <b>Caterham, CR3 5UJ, GB</b>
</div>
```

CSS:
```css
.delivery {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 0; border-top: 1px solid var(--line);
  font-size: 10.5px; color: var(--ink2); flex-wrap: wrap;
}
.delivery b { color: var(--ink); font-weight: 500; }
.delivery-sep { color: var(--ink4); margin: 0 2px; }
.days-left { color: var(--warn); font-weight: 600; }
```

The `gap: 6px` and explicit `·` separators prevent blending. The days-left count is amber/warning color so urgency stands out.

### 1d. Badges row — clean format

Bottom of the expanded panel shows info badges:

```
[Fee estimated at 15%]  [Not settled yet]  [Best supplier: souqdeals GBP 19.90]  [Buyer charged GBP 31.70]
```

CSS:
```css
.ibadge {
  font-size: 9px; padding: 2px 6px; border-radius: 3px;
  border: 1px solid; white-space: nowrap; font-weight: 500;
}
.ibadge-warn { border-color: rgba(227,183,104,.3); color: var(--warn); background: rgba(227,183,104,.06); }
.ibadge-red { border-color: rgba(255,107,107,.3); color: var(--red); background: rgba(255,107,107,.08); }
.ibadge-ok { border-color: rgba(127,209,160,.3); color: var(--ok); background: rgba(127,209,160,.08); }
.ibadge-info { border-color: var(--line); color: var(--ink2); background: var(--panel2); }
```

### 1e. "No cost" state — clean presentation

When cost is missing, the current app shows a tooltip "There is not enough here to work the profit out." Replace:

- Breakdown bar: show the fee segment and a grey placeholder segment saying "Set cost to calculate profit"
- Summary cards: show "—" with "No cost set" in 9px muted text below the dash
- Remove the tooltip entirely
- Handling card should still show the actual handling time (e.g. "4d"), not "—" — handling has nothing to do with cost
- Don't change any cost calculation logic — just clean up the visual presentation

### 1f. Header — apply compact header globally

The orders page still uses the old full-width tab navigation header with Returns Intelligence, All orders, Variations, etc. spread across the bar. Apply the same compact header from the listings page density pass:

- Logo + account chip + breadcrumb + bookmarks + spacer + health badge + icon buttons + user name
- The page-specific tabs (Returns Intelligence, All orders, etc.) go in the bookmarks bar, not as primary nav

This should be consistent across ALL pages: listings, orders, sourcing, generate, etc.

---

## 2. Remove "N warnings" text line everywhere

The "⚠ 1 warning" / "⚠ 2 warnings" text still appears below warning icons on:
- Listing rows in detailed view (`static/js/listrow_detailed.js`)
- PDP overlay hero section (`static/js/pdp.js`)
- Card/tile view (`static/js/listings.js` or `static/js/miles_template.js`)

The three warning symbols (eye, document, quote icons) already indicate warnings visually. The text is redundant.

**Fix:** Find every place the warning count text is rendered and remove it. Keep the warning icons/symbols — only remove the text label.

Search for: `warning`, `warnings`, `⚠` in the JS files above.

---

## 3. API error persistence — errors vanish after sync

**Bug:** A listing (Window Cleaning Kit, SKU 11.59_3Days_B0DNJH3CRX) previously showed API_ERROR status after a failed `putListingsItem` submission. After a Sync operation, the error disappeared and the status changed to APPROVED. The API error is now invisible — the user has no way to see what went wrong.

**Root cause:** API errors are likely stored as the listing status (API_ERROR), which gets overwritten by Sync when it reads the current Amazon status. Or the error details are stored nowhere.

**Fix:**
1. Store API errors in a **separate field** (`api_errors` JSON column) on the listing row, not as the status
2. The `api_errors` field should contain the full `issues` array from Amazon's `putListingsItem` response:
   ```json
   [
     {
       "code": "INVALID_ATTRIBUTE_VALUE",
       "message": "The value provided for attribute 'item_name' exceeds...",
       "severity": "ERROR",
       "attributeNames": ["item_name"]
     }
   ]
   ```
3. This field survives Sync operations — Sync updates status and catalogue data but never touches `api_errors`
4. `api_errors` is cleared only when the listing is successfully resubmitted (putListingsItem returns no ERROR-severity issues)
5. Display API errors as a red banner on the PDP (see section 6 in PDP_REDESIGN_TASK.md for the design)
6. On the listings page, show a red indicator on rows that have stored API errors (e.g. a red dot or a specific icon)

---

## 4. False compliance flags + duplicates (still unfixed)

**Bug A — Duplicates:** The same compliance warning appears twice in the warnings JSON array. The Window Cleaning Kit shows the identical COMPLIANCE [HIGH] message twice.

**Fix:** In `listing/warnings.py`, before appending any warning to the array, check if a warning with the same `type` AND `message` already exists. Skip duplicates.

```python
# Before appending:
if not any(w['type'] == new_warning['type'] and w['message'] == new_warning['message'] for w in warnings):
    warnings.append(new_warning)
```

**Bug B — False categories:** A squeegee/scrubber is getting flagged for:
- `health_beauty, knives_blades, tools_hardware` categories
- CPSR (Cosmetic Product Safety Report)
- EU/UK Cosmetic Regulation 1223/2009
- Full INCI ingredient list

These are cosmetics regulations. A cleaning tool should never trigger them.

**Fix:** The compliance checker must use the product's actual Amazon `product_type` (from SP-API catalogue data) to determine which compliance rules apply:

- Read the product type from the listing's cached catalogue data (e.g. `product_type: "CLEANING_TOOL"`)
- Only apply health/beauty/cosmetics rules if the product type is in a health/beauty/cosmetics category
- Only apply knives/blades rules if the product type is in a blades/cutlery/tools category
- If no product type is cached, skip category-specific compliance checks entirely (better to miss a flag than to false-flag every product)

Do NOT use broad keyword matching against the title or item specifics for category determination. Use the Amazon product type classification.

---

## 5. Trace the orders cost calculation (investigation — don't change yet)

Before making any changes to cost logic, trace and explain the full data flow:

1. Where does the "cost" value come from for each order line? Which function, which table/field?
2. Does it read from sourcing/supplier data? From COGS upload? From manual input?
3. What is the priority order if multiple sources exist?
4. Why does an order show "—" for cost when the sourcing page shows a supplier with a price?
5. Where is the "There is not enough here to work the profit out." string in the code?
6. How are profit, ROI, and margin calculated? What formulas?

Report the file names, function names, and exact logic flow. Don't fix anything in the cost logic — just explain it so we can decide what to change.

---

## Summary — what to do in order

| Priority | Task | Risk |
|----------|------|------|
| 1 | Remove "N warnings" text line (section 2) | Zero risk — cosmetic only |
| 2 | Fix duplicate warnings in warnings.py (section 4A) | Low risk — dedup check |
| 3 | Fix false compliance flags (section 4B) | Medium risk — need to test against multiple product types |
| 4 | Store API errors separately (section 3) | Medium risk — schema change + display |
| 5 | Orders page visual match (section 1) | Low risk — CSS/JS rendering |
| 6 | Compact header on all pages (section 1f) | Medium risk — touches global layout |
| 7 | Trace cost calculation logic (section 5) | Zero risk — investigation only |

## Files likely touched

| File | Changes |
|------|---------|
| `static/js/listrow_detailed.js` | Remove warning text, API error indicator |
| `static/js/pdp.js` | Remove warning text, show API error banner |
| `static/js/listings.js` / `miles_template.js` | Remove warning text from card view |
| `listing/warnings.py` | Dedup check, product_type-based category filtering |
| `data/store.py` | Add `api_errors` column |
| `routes/listing_routes.py` | Store API errors from putListingsItem, clear on success |
| Orders JS/CSS files | Bar colors, supplier table, delivery spacing, badges, no-cost state |
| `static/css/dashboard.css` | Compact header applied globally |
| `templates/dashboard.html` | Header markup consistency across pages |
