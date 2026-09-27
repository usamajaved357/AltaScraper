# Changelog

What changed **in production** (origin/main, deployed by Render), in plain
English, newest first. One line per deploy: date, commit, what the owner will
notice. Work that never reached origin/main does not belong here; git history
holds the full detail.

Claude adds a line after every deploy it performs or confirms.

---

## September 2026

- **27 Sep** · 0e5529e · Listings: the "Click to filter" hint under the stat
  cards is gone; an empty product queue shows nothing at all.
- **27 Sep** · 5e78d3e · Listings: the detailed row and the card view are back
  as they were before the redesign (keeping Amazon's real condition); the "Add
  a product" form is removed; the upload zone is one line.
- **26 Sep** · 94a2306 (with c7359a0, df9daf1, 1c56857) · New product page
  (PDP) tabs: Product Details (one-line barcode/compliance notes, 75-character
  title limit, byte-counted bullets), Images (slots, one competitor strip, four
  AI preset buttons), Offer (real default quantity, live profit), Safety &
  Compliance (badges, saved "Actual on Amazon").
- **26 Sep** · 65fd9ab · Listings page redesign merged: generation flow on the
  listings page, toolbar with Costs and ⋯ menus, "Submit selected", badges that
  describe the situation.
- **26 Sep** · 243e92d and earlier · PDP fixes: status badge matches the list;
  no "Edit listing" on the listing's own page; Amazon feedback light; image
  library refresh after generation; named image slots; redraw after Preview /
  Submit / Auto-fix / Pull; barcode panel stays after the GTIN tick; Cost badge
  uses the one cost reader; Amazon's copy shown on live listings; "Ask Claude"
  above the page.
- **26 Sep** · 34d7aad, c185b54 · "GENERATED" now reads "Draft" everywhere,
  including the tile and the drawer.
- **26 Sep** · 562b4d8 · The separate Generate & submit screen retired.
- **26 Sep** · 28a06a5 · A permission added after a user record was written no
  longer reads as "denied".
- **26 Sep** · d8900e4 · Images pushed to live listings now reach Amazon (the
  marketplace was missing from the request).

Earlier history: `git log origin/main`. Before 19 Sep 2026 work reached main as
GitHub pull requests from the `koibhe` branch (PR #138-#174).
