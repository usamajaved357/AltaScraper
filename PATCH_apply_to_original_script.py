# PATCH: add unified-template export to your ORIGINAL working script
# ===================================================================
# This adds a NEW export path. It does NOT change generation, and does NOT
# change your existing run_export(). Your original script keeps working exactly
# as it does today; you just gain an export that targets the new unified template.
#
# You are editing YOUR ORIGINAL amazon_listing_generator.py (the one that produced
# the good v7.0 output). Put unified_export.py in the SAME folder as that script.
#
# Make THREE small edits:


# ───────────────────────────────────────────────────────────────────
# EDIT 1 — add the import.
# Near the top of the file, with the other imports, add this ONE line:
# ───────────────────────────────────────────────────────────────────

import unified_export


# ───────────────────────────────────────────────────────────────────
# EDIT 2 — add this NEW function.
# Paste the whole function ANYWHERE at top level (e.g. directly ABOVE the
# existing `def run_export(`). Do not delete run_export — just add this beside it.
# It reuses your existing detect_route(), build_flat_row(), load_static_valid_values(),
# and merge_static_into_runtime(). The ONLY change vs run_export is:
#   - columns come from unified_export.build_field_map(template)  (not FILE1_COLS/FILE2_COLS)
#   - output goes to a LOCAL .xlsm                                (not template Google Sheets)
# ───────────────────────────────────────────────────────────────────

def run_export_unified(config: dict, gc, status_filter: str = "APPROVED"):
    console.print(f"\n[bold cyan]{'='*55}[/bold cyan]")
    console.print(f"[bold cyan]  UNIFIED FLAT FILE EXPORT -- Status: {status_filter}[/bold cyan]")
    console.print(f"[bold cyan]{'='*55}[/bold cyan]\n")

    brand        = config.get("brand_name", "")
    manufacturer = config.get("manufacturer", brand)

    template_path = config.get("unified_template_path")
    output_path   = config.get("unified_output_path", "filled_unified_template.xlsm")

    if not template_path:
        console.print("[red]unified_template_path missing in config.json[/red]")
        console.print("[yellow]Set it to the blank template downloaded from the "
                      "CORRECT Seller Central account.[/yellow]")
        return

    from pathlib import Path as _P
    if not _P(template_path).exists():
        console.print(f"[red]Template not found: {template_path}[/red]")
        return

    # Step 1: build the dynamic column map from the template's field-ID row.
    console.print("[bold]Step 1:[/bold] Mapping template columns by field ID")
    cols_map = unified_export.build_field_map(template_path)
    console.print(f"  Template width: {cols_map['TOTAL_COLS']} columns; "
                  f"{len([k for k in cols_map if k != 'TOTAL_COLS'])} fields located")

    # Step 2: valid-values for dropdown snapping (reuse your static XLSM values).
    console.print("\n[bold]Step 2:[/bold] Loading valid values")
    static_vv = load_static_valid_values()
    valid_all = merge_static_into_runtime({}, static_vv) if static_vv else {}

    # Step 3: read APPROVED rows from the SAME output tab as always.
    console.print("\n[bold]Step 3:[/bold] Reading approved listings")
    sh       = gc.open_by_key(config["google_spreadsheet_id"])
    ws       = sh.worksheet(OUTPUT_TAB)
    all_rows = ws.get_all_records()
    rows     = [r for r in all_rows
                if str(r.get("Status", "")).upper().startswith(status_filter.upper())]
    console.print(f"  {len(all_rows)} total -> [bold]{len(rows)}[/bold] '{status_filter}'")
    if not rows:
        console.print(f"[yellow]No '{status_filter}' rows. Set Status=APPROVED in sheet.[/yellow]")
        return

    # Step 4: route + build each row's VALUES with your existing logic.
    console.print(f"\n[bold]Step 4:[/bold] Routing + building {len(rows)} product(s)")
    built = []
    for row in rows:
        title  = str(row.get("Title",          ""))
        cat    = str(row.get("Amazon Category", ""))
        pt_raw = str(row.get("Product Type",   ""))
        _file_id, prod_type, node = detect_route(title, cat, pt_raw)
        vv = valid_all.get(prod_type, {})
        built.append(
            build_flat_row(row, brand, manufacturer, cols_map, vv, prod_type, node)
        )
    console.print(f"  Built [bold]{len(built)}[/bold] row(s)")

    # Step 5: write the LOCAL filled .xlsm (row 1 signature + macros preserved).
    console.print("\n[bold]Step 5:[/bold] Writing local filled template")
    out = unified_export.write_local_template(template_path, output_path, built)

    console.print(f"\n[bold green]Export complete![/bold green]")
    console.print(f"  Filled file: [bold]{out}[/bold]")
    console.print("  Next: open it in Excel -> File -> Save As -> "
                  "Text (Tab delimited) (*.txt)")
    console.print("  Then Seller Central UK -> Inventory -> Add Products via Upload\n")


# ───────────────────────────────────────────────────────────────────
# EDIT 3 — point `export` mode at the new function.
# Find where the script dispatches modes (where it currently calls run_export
# for the "export" argument). It looks something like:
#
#       elif mode == "export":
#           run_export(config, gc)
#
# Change that ONE call to:
#
#       elif mode == "export":
#           run_export_unified(config, gc)
#
# (If you ever want the old two-template behaviour back, just switch it back
#  to run_export — both functions now exist side by side.)
# ───────────────────────────────────────────────────────────────────
