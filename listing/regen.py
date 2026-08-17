"""listing/regen.py -- batch copy REgeneration for existing Miles rows (step d).

run_regen() regenerates ONLY the copy fields for a set of SKUs and replaces each
row IN PLACE (no duplicate rows, no _2 SKUs), stamping a "Regenerated" column with
timestamp + reason. It runs the SAME pipeline as the Miles generate path
(brand_listing.process_brand_row) -- so the claims-grounding gate AND the
forbidden-brand scanner both apply -- and it writes to the SHEET ONLY, never to
Amazon.

Two HARD RULES:
  1) a SKU with no source documents is REFUSED (never generate with nothing to
     ground on -- the rule that would have prevented the whole fabrication incident);
  2) a row already carrying an uncleared "HOLD:" is REFUSED (never silently launder a
     held row back to clean -- a human must clear the HOLD first).

Thin wrapper lives in amazon_listing_generator's `mode == "regen"` block.
"""
import os
import json


def _load_store(base_dir):
    """SKU(item_number) -> harvested bundle, from the accumulated store + latest run."""
    store = {}
    try:
        store.update(json.load(open(os.path.join(base_dir, "miles_bundles_store.json"), encoding="utf-8")))
    except Exception:
        pass
    try:
        for b in json.load(open(os.path.join(base_dir, "miles_bundles.json"), encoding="utf-8")):
            store.setdefault(str(b.get("item_number", "")), b)
    except Exception:
        pass
    return store


def _miles_regen_profile(config, marketplace):
    # Sufficient Miles profile. The big safe_words_extra list is omitted on purpose:
    # it only feeds the caps-scan, which is disabled for Miles (max_unrecognised=9999),
    # so leaving it out changes nothing about grounding or brand safety.
    return {
        "brand_name": "Miles Lubricants", "marketplace": marketplace,
        "voice_mode": "regenerate", "country_of_origin": "US", "handling_time": "5",
        "lead_with_brand": True, "title_max_chars": 75, "keyword_boxes": 2,
        "description_spec": "up to 2000 characters including HTML tags",
        "miles_sheet_format": True, "replace_existing": True, "auto_image": False,
        "_config": config,
        "allowed_phrases_override": ["produced by", "made by", "manufactured by",
                                     "supplied by", "backed by", "developed by"],
    }


def run_regen(config, gc, creds, *, skus, marketplace="UK", output_tab=None,
              spreadsheet_id=None, reason=""):
    import amazon_listing_generator as G
    import brand_listing
    from listing.compliance import forbidden_names_block

    console  = G.console
    base_dir = str(G.CONFIG_PATH.parent)                       # data dir (store lives here)
    code_dir = os.path.dirname(os.path.abspath(G.__file__))    # code dir (rule files here)

    skus = [str(s).strip() for s in (skus or []) if str(s).strip()]
    if not skus:
        console.print("[regen] no SKUs given; nothing to do.")
        return {"regenerated": [], "refused_no_source": [], "refused_held": [], "not_found": []}

    # THE STORE THIS APP ACTUALLY USES.
    #
    # This opened a Google Sheet directly -- gc.open_by_key, then .worksheet() --
    # so on the database backend regeneration read and wrote a spreadsheet while
    # everything else read and wrote SQLite. Exactly the fault output_ws() was
    # written to end for Preview and Submit, in the one path that had not been
    # moved over: a regenerated listing would land somewhere the app never looks.
    #
    # output_ws picks by backend, so this cannot pick the wrong one (Rule 12).
    ws = G.output_ws(config, gc, spreadsheet_id, output_tab)
    console.print(f"[regen] store '{getattr(ws, 'title', '?')}' | {len(skus)} SKU(s) | "
                  f"marketplace {marketplace} | reason: {reason or '(none)'}")

    store = _load_store(base_dir)
    try:
        safe_alts = open(os.path.join(code_dir, "safe_alternatives.txt"), encoding="utf-8").read().strip()
    except Exception:
        safe_alts = ""
    guidance = forbidden_names_block(safe_alts)
    profile  = _miles_regen_profile(config, marketplace)

    compliance_rules = G.load_compliance_rules()
    ip_rules  = G.load_ip_rules()
    static_vv = G.load_static_valid_values()
    # G._claude(config), not G.anthropic.Anthropic(...).
    #
    # The generator stopped importing anthropic at module level -- it costs 2.1
    # seconds on every run, including the ones that never call Claude -- and
    # moved the import inside _claude(), the single place that builds the
    # client. This line was left reaching for the module attribute that used to
    # exist, so regen died on the spot with
    #
    #     AttributeError: module 'amazon_listing_generator' has no attribute
    #     'anthropic'
    #
    # every time it was asked to rebuild a listing. Found by regenerating one.
    client    = G._claude(config)

    # read the tab once (retry-wrapped)
    vals = G._read_retry(ws.get_all_values)
    hdr  = vals[0] if vals else []
    # Some older Miles tabs have no "Compliance Report" column -- then a HOLD would
    # have nowhere to land. Add it so HOLD status always has a home; existing rows
    # are untouched (new column is blank). The "Regenerated" column is added by the
    # in-place writer itself.
    if hdr and "Compliance Report" not in hdr:
        # Shared with brand_listing's "Regenerated" column, which did the same
        # three steps. ensure_column swallows a failure the same way this did --
        # a missing optional column must not abort a regeneration run.
        from listing import repo as _repo
        _col, hdr, _added = _repo.ensure_column(ws, "Compliance Report", hdr)
        if _added:
            vals = G._read_retry(ws.get_all_values)
            hdr  = vals[0] if vals else hdr
            console.print("[regen] added a 'Compliance Report' column (was missing on this tab).")
    def _ci(name):
        return hdr.index(name) if name in hdr else -1
    sku_c, comp_c = _ci("SKU"), _ci("Compliance Report")
    row_by_sku = {}
    for i, r in enumerate(vals[1:], start=2):
        if 0 <= sku_c < len(r):
            s = str(r[sku_c]).strip()
            if s:
                row_by_sku.setdefault(s, (i, r))

    regenerated, refused_nosrc, refused_held, notfound = [], [], [], []
    for sku in skus:
        hit = row_by_sku.get(sku)
        if not hit:
            notfound.append(sku)
            console.print(f"  [yellow][regen] {sku}: not found in tab[/yellow]")
            continue
        row_idx, rowvals = hit

        # HARD RULE 2 -- an uncleared HOLD must not be laundered back to clean.
        comp = (rowvals[comp_c] if 0 <= comp_c < len(rowvals) else "").strip()
        if comp.startswith("HOLD:"):
            refused_held.append(sku)
            console.print(f"  [yellow][regen] {sku}: carries an uncleared HOLD -- "
                          f"refusing (a human must clear it first)[/yellow]")
            continue

        # HARD RULE 1 -- no source documents -> refuse (never generate with nothing
        # to ground on).
        b = store.get(sku) or {}
        src = " ".join(str(b.get(f, "")) for f in ("sds_text", "spec_text", "other_pdf_text")).strip()
        if not src:
            refused_nosrc.append(sku)
            console.print(f"  [red][regen] {sku}: NO source documents -- refusing to "
                          f"regenerate (would fabricate). Re-harvest from Drive first.[/red]")
            continue

        source_docs = ""
        if b.get("sds_text"):
            source_docs += "SAFETY DATA SHEET (SDS):\n" + b["sds_text"][:4000] + "\n\n"
        if b.get("spec_text"):
            source_docs += "TECHNICAL DATA SHEET (TDS):\n" + b["spec_text"][:3000] + "\n\n"
        if b.get("other_pdf_text"):
            source_docs += "ADDITIONAL:\n" + b["other_pdf_text"][:1500]
        product = {
            "title": b.get("title", "") or sku, "description": b.get("description", ""),
            "vendor": "Miles Lubricants", "sku": sku, "model_number": sku, "barcode": "",
            "product_type": (b.get("product_type") or "").strip().upper() or "LUBRICANT",
            "attributes": b.get("attributes", {}), "images": b.get("images", []),
            "volume": b.get("volume", "") or b.get("pack", ""),
        }
        try:
            ok = brand_listing.process_brand_row(
                product, profile, host=G, client=client, ws_out=ws, creds=creds,
                config=config, idx=len(regenerated) + 1, total=len(skus),
                taken_skus=set(), compliance_rules=compliance_rules, ip_rules=ip_rules,
                static_vv=static_vv, claim_docs=[], competitor_specs="",
                source_docs=source_docs, guidance_block=guidance,
                replace_at_row=row_idx, regen_reason=reason)
            if ok:
                regenerated.append(sku)
        except Exception as e:
            console.print(f"  [red][regen] {sku}: {type(e).__name__}: {str(e)[:140]}[/red]")

    console.print(f"\n[regen] done. regenerated={len(regenerated)} | "
                  f"refused(no source)={len(refused_nosrc)} | refused(held)={len(refused_held)} | "
                  f"not found={len(notfound)}")
    if refused_nosrc:
        console.print(f"  no source (re-harvest first): {', '.join(refused_nosrc)}")
    if refused_held:
        console.print(f"  held (clear the HOLD first): {', '.join(refused_held)}")
    if notfound:
        console.print(f"  not found in tab: {', '.join(notfound)}")
    return {"regenerated": regenerated, "refused_no_source": refused_nosrc,
            "refused_held": refused_held, "not_found": notfound}
