# PATCH_brand_mode.py
# ============================================================================
# Wires the BRAND-LISTING feature into your existing amazon_listing_generator.py
# WITHOUT touching the arbitrage path. Same spirit as PATCH_apply_to_original_script.py:
# additive only. The arbitrage generate/retry/export/api modes keep working
# exactly as today; you gain a new "brand" mode.
#
# Put these new files in the SAME folder as amazon_listing_generator.py:
#   shopify_import.py
#   brand_profile.py
#   brand_listing.py
#   (a brands/ folder is auto-created on first save)
#
# Make FOUR small edits below.
# ============================================================================


# ───────────────────────────────────────────────────────────────────
# EDIT 1 -- add imports.
# Near the top of amazon_listing_generator.py, with the other imports, add:
# ───────────────────────────────────────────────────────────────────

import shopify_import
import brand_profile
import brand_listing


# ───────────────────────────────────────────────────────────────────
# EDIT 2 -- add this NEW runner function. Paste it ANYWHERE at top level
# (e.g. directly ABOVE `async def main():`). It does NOT replace process_row;
# it calls process_brand_row from brand_listing.py for each Shopify product.
#
# `host` is THIS module -- we pass the module object so brand_listing can reuse
# build_sheet_row, check_compliance, check_ip_violations, sheet_write_row,
# get_product_type_schema, _build_message_content, SYSTEM_PROMPT, and the
# autocomplete helpers, all unchanged.
# ───────────────────────────────────────────────────────────────────

def run_brand(config: dict, gc, creds: dict, ws_out=None,
              brand_name: str = "", csv_path: str = "",
              status_filter=("active", "")):
    """
    BRAND mode: read a Shopify export, load the brand profile + claim docs, then
    generate one Amazon listing per product into the SAME output sheet/contract.

    ws_out : the ALREADY-OPEN output worksheet from main()/init_sheets. Passed in
             so we do NOT re-authenticate Google Sheets (re-auth was a freeze risk).

    Args (all optional; fall back to config / profile):
      brand_name : which brands/<slug>/profile.json to use. If empty, uses
                   config['active_brand'] or config['brand_name'].
      csv_path   : Shopify export path. If empty, uses the profile's
                   shopify_export_path or config['shopify_export_path'].
    """
    import sys as _sys
    from pathlib import Path as _P
    base_dir = _P(__file__).parent

    # Safety net: if main() didn't hand us a worksheet, open once (not twice).
    if ws_out is None:
        _gc, _wsin, ws_out = init_sheets(config)

    console.print(f"\n[bold magenta]{'='*55}[/bold magenta]")
    console.print(f"[bold magenta]  BRAND LISTING MODE[/bold magenta]")
    console.print(f"[bold magenta]{'='*55}[/bold magenta]\n")

    brand_name = (brand_name or config.get("active_brand")
                  or config.get("brand_name", "")).strip()
    if not brand_name:
        console.print("[red]No brand specified.[/red] Pass a brand name or set "
                      "'active_brand' in config.json.")
        return

    profile = brand_profile.load_profile(config, base_dir, brand_name)
    console.print(f"  Brand profile: [bold]{profile.get('brand_name')}[/bold] "
                  f"| vendor_mode={profile.get('vendor_mode')} "
                  f"| voice={profile.get('voice_mode')} "
                  f"| marketplace={profile.get('marketplace')}")

    csv_path = (csv_path or profile.get("shopify_export_path")
                or config.get("shopify_export_path", "")).strip()
    if not csv_path:
        console.print("[red]No Shopify export path.[/red] Set it in the brand "
                      "profile or config['shopify_export_path'].")
        return
    if not _P(csv_path).is_absolute():
        csv_path = str(base_dir / csv_path)
    if not _P(csv_path).exists():
        console.print(f"[red]Shopify export not found:[/red] {csv_path}")
        return

    # --- parse the export ----------------------------------------------------
    console.print("[bold]Step 1:[/bold] Parsing Shopify export")
    sf_status = (None if str(profile.get("import_all_statuses")).lower() == "true"
                 else status_filter)
    products = shopify_import.load_shopify_products(csv_path, include_statuses=sf_status)
    catlang  = shopify_import.detect_catalogue_language(products)
    # persist detected source language into the profile (drives the tone dropdown)
    if profile.get("source_language") != catlang["code"]:
        profile["source_language"] = catlang["code"]
        brand_profile.save_profile(config, base_dir, profile)
    console.print(f"  {len(products)} product(s) | source language: "
                  f"{catlang['name']} ({catlang['code']})")
    if not products:
        console.print("[yellow]No products after status filter.[/yellow]")
        return

    # --- optional reseller filter: one vendor only ---------------------------
    only_vendor = (profile.get("only_vendor") or "").strip()
    if only_vendor:
        products = [p for p in products if p.get("vendor", "") == only_vendor]
        console.print(f"  Reseller filter: vendor='{only_vendor}' -> {len(products)} product(s)")

    # --- claim docs (Drive) --------------------------------------------------
    console.print("[bold]Step 2:[/bold] Loading claim-support documents")
    docpack = brand_profile.fetch_claim_documents(config, profile, base_dir)
    for w in docpack.get("warnings", []):
        console.print(f"  [yellow]{w}[/yellow]")
    claim_docs = docpack.get("docs", [])
    console.print(f"  {len(claim_docs)} readable claim doc(s) attached"
                  + (f"; {len(docpack['office_skipped'])} Office file(s) need PDF conversion"
                     if docpack.get("office_skipped") else ""))

    # --- optional competitor ASIN enrichment pool ----------------------------
    competitor_specs = ""
    pool = profile.get("competitor_asins") or []
    if pool:
        console.print(f"[bold]Step 3:[/bold] Competitor enrichment ({len(pool)} ASIN[s])")
        bits = []
        for asin in pool[:5]:
            try:
                cd = get_competitor_asin_data(asin, creds)
                if cd.get("title"):
                    specs = "; ".join(f"{k}: {v}" for k, v in
                                      list(cd.get("attributes", {}).items())[:20])
                    bits.append(f"[{asin}] {cd['title'][:80]} :: {specs[:400]}")
            except Exception:
                continue
        competitor_specs = "\n".join(bits)
        console.print(f"  enriched from {len(bits)} competitor(s)")

    # --- generate ------------------------------------------------------------
    console.print(f"[bold]Step 4:[/bold] Generating {len(products)} brand listing(s)")
    client           = anthropic.Anthropic(api_key=config["anthropic_api_key"])
    taken_skus, _    = load_existing_skus_and_asins(ws_out)
    compliance_rules = load_compliance_rules()
    ip_rules         = load_ip_rules()
    static_vv        = load_static_valid_values()

    ok_count = 0
    for i, product in enumerate(products, 1):
        try:
            ok = brand_listing.process_brand_row(
                product, profile,
                host=_sys.modules[__name__], client=client, ws_out=ws_out,
                creds=creds, config=config, idx=i, total=len(products),
                taken_skus=taken_skus, compliance_rules=compliance_rules,
                ip_rules=ip_rules, static_vv=static_vv, claim_docs=claim_docs,
                competitor_specs=competitor_specs)
            if ok:
                ok_count += 1
        except Exception as e:
            console.print(f"  [red]error on '{product.get('title','')[:40]}': {str(e)[:120]}[/red]")
        if i < len(products):
            import time as _t; _t.sleep(2)

    console.print(f"\n[bold green]Brand run complete:[/bold green] {ok_count}/{len(products)} written")
    console.print("  Review in the dashboard, set Status=APPROVED, then run export or api.")


# ───────────────────────────────────────────────────────────────────
# EDIT 3 -- add "brand" to the dispatch in main().
# main() already builds (gc, ws_in, ws_out) via init_sheets. Reuse ws_out --
# do NOT re-open Sheets (re-auth can freeze the run). Find the dispatch block:
#
#       if mode == "export":
#           run_export_unified(config, gc)
#           return
#
#       if mode == "api":
#           submit = any(a.lower() == "submit" for a in sys.argv[2:])
#           run_api(config, gc, creds, submit=submit)
#           return
#
# Add this NEW block right after them (note ws_out is passed in):
#
#       if mode == "brand":
#           bname = sys.argv[2] if len(sys.argv) > 2 else ""
#           csvp  = sys.argv[3] if len(sys.argv) > 3 else ""
#           run_brand(config, gc, creds, ws_out=ws_out, brand_name=bname, csv_path=csvp)
#           return
#
# If, at the point of dispatch, ws_out isn't in scope yet, either move the
# init_sheets(...) call above the dispatch, or just call
# run_brand(config, gc, creds, brand_name=bname, csv_path=csvp) and the function
# will open the sheet ONCE itself (the built-in safety net).
# ───────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────
# EDIT 4 -- (DASHBOARD) allow the "brand" run mode through the dashboard.
# In dashboard.py, in the /run/<mode> route, change the allowed-modes line:
#
#   if mode not in ("generate", "retry", "export", "api", "api_submit"):
#
# to:
#
#   if mode not in ("generate", "retry", "export", "api", "api_submit", "brand"):
#
# and in the `extra = (...)` ladder, add a branch so "brand" passes the active
# brand through (the dashboard patch file dashboard_brand_patch.py does this for
# you, along with the Connections + Brand Settings tabs and the "i" provenance
# button).
# ───────────────────────────────────────────────────────────────────

# Run from CLI without the dashboard:
#   py -3.11 amazon_listing_generator.py brand "Leech" "products_export_all_products.csv"
