"""listing/sheet_input.py -- reading the input sheet and choosing the rows to generate.

Moved word for word out of amazon_listing_generator.py (Milestone 4, owner-approved 28 Sep 2026).
amazon_listing_generator.py still imports every name below, so dashboard.<name> and every
route that is handed one keep working exactly as before. Nothing here may
import dashboard (it would load a second copy of the app).
"""

import re


def _data_backend(config: dict) -> str:
    """Where THIS run writes its listings: "sheets" (default) or "db".

    Delegates to data/choice.py, which is the ONE place this is decided. It used
    to read ALTA_DATA_BACKEND here directly, while dashboard.py decided from a
    function argument that the deployed app never set -- so the generator could
    be writing to SQLite while the dashboard read the Google Sheet, and listings
    generated here would never appear there.
    """
    from data import choice as _choice
    return _choice.resolve(config, config.get("_config_path"))


def read_input_sheet(ws_in) -> list:
    # Still a Google Sheet -- this is the INPUT, where products come from, and
    # nothing replaces it yet. Reading it through the repo anyway means the day
    # something does (a paste screen, an upload), this call site does not change.
    from listing import repo as _repo
    from listing import suppliers as _suppliers
    rows = _repo.read_grid(ws_in)
    if not rows:
        return []
    headers  = [h.strip().lower().replace(" ", "_") for h in rows[0]]
    products = []
    for row in rows[1:]:
        if not any(row):
            continue
        row  = row + [""] * max(0, len(headers) - len(row))
        item = dict(zip(headers, row))
        norm = {
            "ebay_url":      item.get("ebay_link",     item.get("ebay_url",      "")),
            # EVERY SUPPLIER ON THE ROW, in the owner's priority order.
            #
            # The sheet has always had one link column. Several sellers list the
            # same product and each fills in a different amount, so the second
            # and third carry specifics the first left blank. listing/suppliers
            # finds whatever supplier columns the sheet has -- Supplier 2,
            # Source URL 3, and so on -- so adding a sixth is a new column and
            # no code change. `ebay_url` stays as it was, and is the first of
            # these, so nothing that reads it needs to know about the rest.
            "supplier_urls": _suppliers.urls_from(item, headers),
            "source_cost":   item.get("ebay_price",    item.get("ebay_cost",     "")),
            "amazon_url":    item.get("amazon_link",   item.get("amazon_url",    "")),
            "selling_price": item.get("amazon_price",  item.get("selling_price", "")),
            "item_name":     item.get("item_name",     ""),
            "handling_time": item.get("delivery_time", item.get("handling_time", "")),
            "upc":           item.get("ean",           item.get("upc",            "")),
            # THE BRAND THE SHEET NAMED. Blank means "use the account's own",
            # which is what process_row then does -- see the brand selection
            # there. Without this the column was read by nothing on the way in,
            # so a sheet that named a brand generated under the account's
            # instead, silently (the upload path had the same gap: see
            # listing/queued_input.row_to_product).
            "brand":         item.get("brand",         ""),
        }
        # A ROW NEEDS A SOURCE, NOT NECESSARILY A COMPETITOR.
        #
        # This required amazon_url and dropped everything else without a word. On
        # a spreadsheet that was invisible -- a row with only an eBay link simply
        # never generated and nobody knew why. Once products can be typed into
        # the app it becomes a trap: you paste the eBay link you buy from, the
        # row appears in the queue, and generation silently ignores it.
        #
        # Per CLAUDE.md Rule 1 the Amazon ASIN is a COMPETITOR REFERENCE used to
        # pull product data, not the thing being listed. The eBay link is a
        # source of that same data -- fetch_ebay_supplement already reads title,
        # specifics and images from it, and the eBay seller import creates drafts
        # with no competitor ASIN at all. So either link is enough to start from.
        #
        # A ROW WHOSE ONLY LINK IS IN A SUPPLIER COLUMN still has a source.
        #
        # `ebay_url` reads the primary column, so a row filled in only under
        # "Supplier 2" would have had an empty ebay_url and been dropped by the
        # gate below -- silently, which is the exact failure the note above
        # describes and the reason it was written. The first supplier found IS
        # the primary link when the primary column is blank.
        if not str(norm["ebay_url"]).strip() and norm["supplier_urls"]:
            norm["ebay_url"] = norm["supplier_urls"][0][1]

        # A row with NEITHER is still dropped: there is nothing to generate from.
        if norm["amazon_url"].strip() or norm["ebay_url"].strip():
            products.append(norm)
    return products


def _extract_asin(url: str) -> str:
    # The one ASIN-from-a-link regex lives in data/input_import._asin_of; this
    # used to be a second copy of it (CLAUDE.md Rule 12).
    from data.input_import import _asin_of
    return _asin_of(url)


def _extract_ebay_item(url: str) -> str:
    """eBay item number = the digits after /itm/ in an eBay URL."""
    m = re.search(r"/itm/(?:[^/]*?/)?(\d{6,})", str(url))
    if m:
        return m.group(1)
    # some eBay URLs carry it as ?item=12345 or /itm/12345?...
    m = re.search(r"[?&]item=(\d{6,})", str(url))
    return m.group(1) if m else ""


def select_rows(products: list, raw: str, sel_type: str = "auto"):
    """Filter input-sheet products down to the user's selection.

    Returns (filtered_list, error_message). On success error_message is "".
    On a problem (duplicate / no match / bad input) returns ([], message) so the
    caller can print it and stop -- never silently generate the wrong rows.

    sel_type: 'row' | 'asin' | 'ebay_item' | 'auto'
      - A pasted URL always auto-detects (ignores sel_type): amazon.* -> ASIN,
        ebay.* -> item number.
      - 'row'       -> comma-separated 1-based positions in the queue. STILL
                       WORKS, but no longer offered in the app: it is a Google
                       Sheets idea (the product on line 5 of the spreadsheet)
                       and the queue is a database table that displays no row
                       number anywhere, so the box was asking for a figure that
                       appears on no screen. Reachable from the command line via
                       --select-type row, where the position is at least
                       countable.
      - 'asin'      -> match each row's ASIN (its competitor_asin, else the
                       one in its amazon_url -- data/input_row.resolved_asin).
      - 'ebay_item' -> match item number parsed from each row's ebay_url.
    """
    from data.input_row import resolved_asin
    raw = (raw or "").strip()
    if not raw:
        return products, ""   # empty -> generate all (unchanged)

    # --- URL pasted: auto-detect platform regardless of sel_type --------------
    low = raw.lower()
    if "http://" in low or "https://" in low or "amazon." in low or "ebay." in low:
        if "amazon." in low:
            asin = _extract_asin(raw)
            if not asin:
                return [], f"Couldn't read an ASIN from that Amazon URL: {raw[:60]}"
            hits = [(i, p) for i, p in enumerate(products, 1)
                    if resolved_asin(p) == asin]
            return _finish_match(hits, f"ASIN {asin}")
        if "ebay." in low:
            item = _extract_ebay_item(raw)
            if not item:
                return [], f"Couldn't read an item number from that eBay URL: {raw[:60]}"
            hits = [(i, p) for i, p in enumerate(products, 1)
                    if _extract_ebay_item(p.get("ebay_url", "")) == item]
            return _finish_match(hits, f"eBay item {item}")
        if "docs.google." in low or "/spreadsheets/" in low or "drive.google." in low:
            return [], ("That's your Google Sheet link, not a product to select. "
                        "Leave the Generate box EMPTY to make every input-sheet row, "
                        "or type a row number (e.g. 1), or paste a single Amazon/eBay "
                        "product URL.")
        return [], f"Couldn't tell if that URL is Amazon or eBay: {raw[:60]}"

    # --- Row numbers ----------------------------------------------------------
    if sel_type == "row":
        nums = []
        for tok in re.split(r"[,\s]+", raw):
            tok = tok.strip()
            if not tok:
                continue
            if not tok.isdigit():
                return [], (f"'{tok}' is not a row number. For rows, enter digits "
                            f"like 2, 5, 7.")
            nums.append(int(tok))
        picked, bad = [], []
        for n in nums:
            if 1 <= n <= len(products):
                picked.append(products[n - 1])
            else:
                bad.append(n)
        if bad:
            return [], (f"Row(s) {', '.join(map(str, bad))} are out of range "
                        f"(sheet has {len(products)} data rows).")
        if not picked:
            return [], "No valid rows in that selection."
        return picked, ""

    # --- Bare ASIN ------------------------------------------------------------
    if sel_type == "asin":
        asin = raw.upper()
        hits = [(i, p) for i, p in enumerate(products, 1)
                if resolved_asin(p) == asin]
        return _finish_match(hits, f"ASIN {asin}")

    # --- Bare eBay item number ------------------------------------------------
    if sel_type == "ebay_item":
        item = re.sub(r"\D", "", raw)
        hits = [(i, p) for i, p in enumerate(products, 1)
                if _extract_ebay_item(p.get("ebay_url", "")) == item]
        return _finish_match(hits, f"eBay item {item}")

    return [], f"Unknown selection type '{sel_type}'."


def _finish_match(hits: list, label: str):
    """hits = list of (row_number, product). Enforce the duplicate rule."""
    if not hits:
        return [], (f"No row found matching {label}. Check the value or the input "
                    f"sheet.")
    if len(hits) > 1:
        rows = ", ".join(str(i) for i, _ in hits)
        return [], (f"{label} appears in rows {rows} of the input sheet. Switch to "
                    f"Row number and enter the exact row you want.")
    return [hits[0][1]], ""


def _attrs_with_images(pa: dict, comp_data: dict) -> dict:
    """Stash the competitor's primary (+ additional) image URLs into the attribute
    dict so the dashboard can preview them and the API submit can use them as the
    product images. eBay images already take priority inside comp_data['images'].

    Also writes a `_provenance` map {attr_key: 'ebay'|'amazon'|'ai'} so the
    dashboard can tag each field with where its value came from. Source-supplied
    keys keep their eBay/Amazon tag; any attribute the AI produced (present in
    `pa` but not in the source map) is tagged 'ai'.
    """
    out = dict(pa or {})
    imgs = [u for u in (comp_data.get("images") or []) if u][:5]
    if imgs:
        out.setdefault("main_product_image_locator", imgs[0])
        for i, u in enumerate(imgs[1:5], start=1):
            out.setdefault(f"other_product_image_locator_{i}", u)
    # provenance: start from the eBay/Amazon source map, tag the rest as AI
    _src = dict((comp_data.get("_provenance") or {}))
    _prov = {}
    for _k in out.keys():
        if _k.startswith("main_product_image_locator") or _k.startswith("other_product_image_locator_"):
            continue  # images aren't attribute facts
        if _k in _src:
            _prov[_k] = _src[_k]
        else:
            _prov[_k] = "ai"   # the AI produced this value
    if _prov:
        out["_provenance"] = _prov
    return out


def _find_target_row(ws, comp_asin: str):
    """Decide where a generated row should go so listings refill the row you
    cleared (or the first blank gap) instead of always appending at the bottom.
    Priority:
      1) a row with this exact Competitor ASIN but no SKU  (the row you cleared);
      2) the first fully-blank data row (SKU, Title, Competitor ASIN, Product Type all empty);
      3) None  -> caller appends.
    Returns a 1-based sheet row number, or None.
    """
    # MOVED to listing/repo.py. This generator runs as its own process with its
    # own sheet client, so while this logic lived here nothing else could reach
    # it -- and a database backend could never replace it. Kept as a thin
    # delegate because domain/brand_listing.py calls these by name via `host`.
    from listing import repo as _repo
    return _repo.find_reusable_row(ws, comp_asin)
