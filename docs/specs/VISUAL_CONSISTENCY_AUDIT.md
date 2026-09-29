# AltaScraper — Visual Consistency Audit & Fix

## The problem

Every page was built or modified in a different session, with different font sizes, paddings, colors, and heading styles. The result is visual inconsistency — the listings page, orders page, sourcing page, PDP overlay, and other screens all feel like different apps stitched together.

This task standardizes everything to ONE design system.

---

## Step 1 — Audit what exists

Before changing anything, scan every page and catalog what's currently used. Run this in the browser console on each page and record the output:

```js
// Paste this on each page to see what's actually rendered
document.querySelectorAll('*').forEach(el => {
  const s = getComputedStyle(el);
  const fs = s.fontSize;
  const ff = s.fontFamily.split(',')[0];
  if(el.textContent.trim().length > 0 && el.children.length === 0){
    console.log(fs, ff, el.tagName, el.textContent.trim().substring(0,40));
  }
});
```

Pages to check:
- `/w/{workspace}/listings` (all 3 views)
- `/w/{workspace}/orders`
- `/w/{workspace}/sourcing`
- `/w/{workspace}/listing/{sku}` (PDP overlay)
- The sidebar/drawer
- Generate & Submit page

---

## Step 2 — The standard (apply everywhere)

### Font stack
One font stack, everywhere. No page should override this:
```css
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
```

### Font sizes — ONLY these values

| Token | Size | Where used |
|-------|------|------------|
| `--fs-xs` | 9px | Badge labels, tertiary labels, info badges |
| `--fs-sm` | 10px | Column subtitles, metadata, secondary text, toolbar button labels |
| `--fs-base` | 12px | Body text, table cells, form inputs, descriptions |
| `--fs-md` | 13px | Page titles ("Listings", "Orders"), toolbar h2 |
| `--fs-lg` | 16-18px | Stat card numbers |
| `--fs-xl` | 20px | Hero numbers (if any) |

**If a font size doesn't appear in this table, it shouldn't exist in the app.** Search the CSS for font-size values and map each one to the nearest token. Common offenders:
- 11px → decide: is it metadata (10px) or body (12px)?
- 11.5px → pick 12px
- 13.5px → pick 13px
- 14px → pick 13px
- 9.5px → pick 10px or 9px

For this app, 11px is used extensively as a "between" size. Standardize it: **use 11px for table cell data and product titles, 10px for metadata/labels, 12px for form inputs and descriptions.** Add `--fs-data: 11px` to the token list if needed.

### Font weights — ONLY these

| Weight | Where |
|--------|-------|
| 400 | Body text, descriptions, metadata |
| 500 | Semi-bold labels (column sub-headers, "Brand **Nestwell Goods**") |
| 600 | Bold labels, badge text, stat card labels |
| 700 | Stat card numbers, page titles |

No 300, no 800, no 900.

### Colors — use ONLY CSS variables

Every color in the app must come from a CSS variable. No hardcoded hex values anywhere in JS-rendered HTML. Audit and replace:

```
Search across all .js files for:
  color: '#    →  should be  color: 'var(--
  color:"#     →  should be  color:"var(--
  background: '#  →  should be  background: 'var(--
  style="color:#  →  should be  style="color:var(--
```

The existing variable set is:
- `--ink` (primary text), `--ink2` (secondary), `--ink3` (tertiary/labels), `--ink4` (disabled)
- `--accent` (primary action/active), `--accent2` (hover), `--accent-bg` (tint)
- `--ok` (success/profit green), `--red` (error/danger), `--warn` (warning amber)
- `--link` (clickable text — currently same as `--accent` or blue)
- `--bg`, `--panel`, `--panel2`, `--panel3`, `--sidebar`
- `--line` (borders), `--line2` (stronger borders)

### Padding — standardize

| Context | Padding |
|---------|---------|
| Page-level side padding | 10px (set by `--wspad`) |
| Table cell | 6px 8px |
| Stat cards | 7px 9px inside, 5px gap between |
| Toolbar | 4px 10px |
| Appbar | 5px 10px |
| Buttons (toolbar) | 2px 5px (small) or 3px 7px (normal) |
| Form inputs | 2px 6px |
| Badges | 1px 5px |
| Sections (between groups) | 6px 10px |

### Border radius

| Element | Radius |
|---------|--------|
| Buttons, inputs, badges | 3px |
| Cards, stat boxes | 5px |
| Pills (bookmarks, status) | 10px |
| Appbar mark | 5px |

No other radius values. No 6px, no 8px, no 4px on cards, no 12px on buttons.

### Line heights

Body: 1.45. Tight (badges, labels): 1.2. Headings: 1.1.

---

## Step 3 — Apply page by page

### 3a. Global (dashboard.css)

Add the CSS variables at the top of `:root`:
```css
:root {
  --fs-xs: 9px;
  --fs-sm: 10px;
  --fs-data: 11px;
  --fs-base: 12px;
  --fs-md: 13px;
  --fs-lg: 17px;
  --fs-xl: 20px;
  --wspad: 10px;
  --radius-sm: 3px;
  --radius-md: 5px;
  --radius-pill: 10px;
}
```

### 3b. Appbar — must be identical on EVERY page

The appbar currently renders differently on some pages (orders has the old full-width tab nav). Every page must use the same compact appbar:
- Logo + account chip + breadcrumb + bookmarks + spacer + health badge + icon buttons + user name
- `padding: 5px 10px`, `gap: 7px`, `min-height: 36px`
- If a page has its own header rendering, remove it and use the global one

### 3c. Stat cards — same style everywhere

The stat cards on Listings, Orders, and Sourcing should use identical styling:
- Same padding, font sizes, border radius, border color
- Same active state (border-color: var(--accent))
- Same label font size (--fs-sm)
- Same value font size (--fs-lg)

### 3d. Tables — same column header style everywhere

Every table in the app (listings detailed view, orders, sourcing) should have:
- Headers: `font-size: var(--fs-sm)`, `text-transform: none` (sentence case), `font-weight: 600`, `color: var(--ink3)`
- Subtitles: `font-size: var(--fs-xs)`, `font-weight: 400`, `opacity: 0.7`
- Cell text: `font-size: var(--fs-data)`, `color: var(--ink)`
- Cell padding: `6px 8px`
- Row border: `1px solid var(--line)` (not a mix of rgba values)

### 3e. Buttons — same across pages

Toolbar buttons, action buttons in expanded panels, card action buttons — all should use:
- `font-size: var(--fs-sm)` or `var(--fs-data)`
- `padding: 3px 7px`
- `border: 1px solid var(--line)`
- `border-radius: var(--radius-sm)`
- Active state: `background: var(--accent-bg)`, `border-color: var(--accent)`, `color: var(--accent)`

### 3f. Badges — same everywhere

Status badges (LIVE, ACTIVE, GENERATED, Shipped, Not shipped):
- `font-size: var(--fs-xs)`
- `padding: 1px 5px`
- `border-radius: var(--radius-sm)`
- `font-weight: 600`
- Green: `background: var(--ok-bg)`, `color: var(--ok)`
- Red: `background: rgba(var(--red-rgb), .12)`, `color: var(--red)`
- Amber: `background: rgba(var(--warn-rgb), .12)`, `color: var(--warn)`

---

## Step 4 — Verify

After applying, open each page and visually compare:

1. **Listings** (detailed view) → **Orders** → **Sourcing** — the headers, stat cards, table headers, badges, and buttons should look like they belong to the same app
2. **Sidebar** — fonts match the rest
3. **PDP overlay** — fonts match the rest
4. No hardcoded hex colors in any JS file (grep for `'#` and `"#` in `static/js/`)
5. No font-size values outside the token set (grep for `font-size:` in all CSS files)
6. Every page uses the same compact appbar

## Files touched

Every CSS and JS file that renders UI. The main ones:
- `static/css/dashboard.css` — global tokens and appbar
- `static/css/listrow_detailed.css` — listings table
- `static/css/pdp.css` — PDP overlay
- `static/js/listrow_detailed.js` — listings rendered HTML
- `static/js/listings.js` — card/table view
- `static/js/miles_template.js` — card renderer
- The orders JS/CSS files
- The sourcing JS/CSS files
- `static/css/mobile.css` — sidebar
