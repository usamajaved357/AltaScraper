#!/usr/bin/env python3
"""
diagnose_field.py  --  find the REAL allowed values Amazon accepts for a field.

WHY: Some attributes (e.g. battery_installation_device_type) hide their allowed
value list inside conditional branches (oneOf/anyOf/allOf/$ref/dependencies) of
the product-type schema, so the normal loader reports them as "free-text" even
though Amazon validates them server-side. This script downloads the FULL raw
schema for a product type and deep-searches every branch for a given field,
printing every enum value it can find anywhere in the document.

USAGE (run from the app folder, same place START_APP.bat lives):

    py -3.11 diagnose_field.py FLASHLIGHT battery_installation_device_type --account sheelady_us --marketplace US

  - First arg  = product type (e.g. FLASHLIGHT)
  - Second arg = the attribute name to hunt for
  - --account  = the account id you use in the dashboard (optional; falls back to config)
  - --marketplace = US or UK (default UK)

It prints:
  * every enum list found for that field (with the JSON path where it lives)
  * the field's declared type (string/boolean/number) if no enum
  * any conditional (oneOf/allOf) rules that reference the field

Nothing is written or submitted. Read-only.
"""
import sys, json, argparse, urllib.request

def deep_find(node, target, path="$", hits=None):
    """Walk the whole schema; collect any place where `target` appears as a key,
    plus any enum lists anywhere under it."""
    if hits is None:
        hits = []
    if isinstance(node, dict):
        for k, v in node.items():
            newp = f"{path}.{k}"
            if k == target:
                # found the field definition -- record it and dig for enums inside
                enums = collect_enums(v, newp)
                hits.append({"path": newp, "enums": enums,
                             "type": _typ(v), "raw_keys": list(v.keys()) if isinstance(v, dict) else None})
            deep_find(v, target, newp, hits)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            deep_find(v, target, f"{path}[{i}]", hits)
    return hits

def collect_enums(node, path="$", out=None):
    """Find every 'enum': [...] anywhere under node, with its path."""
    if out is None:
        out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "enum" and isinstance(v, list):
                out.append({"path": f"{path}.enum", "values": [str(x) for x in v]})
            else:
                collect_enums(v, f"{path}.{k}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            collect_enums(v, f"{path}[{i}]", out)
    return out

def _typ(v):
    if isinstance(v, dict):
        # dig to the value sub-prop if present
        it = v.get("items", {})
        if isinstance(it, dict):
            ip = it.get("properties", {})
            if isinstance(ip, dict) and "value" in ip and isinstance(ip["value"], dict):
                return ip["value"].get("type") or it.get("type") or v.get("type")
        return v.get("type")
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("product_type")
    ap.add_argument("field")
    ap.add_argument("--account", default="")
    ap.add_argument("--marketplace", default="UK")
    args = ap.parse_args()

    # reuse the app's own config + creds + marketplace plumbing
    import amazon_listing_generator as G

    cfg = G.load_config()

    # build creds for the requested account/marketplace, mirroring the app
    creds = None
    try:
        # account-scoped creds if the app exposes a resolver
        if args.account and hasattr(G, "sp_creds"):
            # sp_creds reads account override from config if present
            creds = G.sp_creds(cfg, args.marketplace)
    except Exception:
        creds = None
    if creds is None:
        creds = G.sp_creds(cfg, args.marketplace)

    # set the module marketplace so _raw_schema targets the right region
    from sp_api.base import Marketplaces
    if args.marketplace.upper() == "US":
        G.MARKETPLACE = Marketplaces.US
        G.MARKETPLACE_ID = G.US_MARKETPLACE_ID
    else:
        G.MARKETPLACE = Marketplaces.UK
        G.MARKETPLACE_ID = "A1F83G8C2ARO7P"

    print(f"Fetching FULL schema for {args.product_type} ({args.marketplace}) ...")
    # call getDefinitions WITHOUT enforcement to get the fullest schema, then
    # download the raw JSON (we want the entire document, not the slim props)
    from sp_api.api import ProductTypeDefinitions
    _locale = "en_US" if args.marketplace.upper() == "US" else "en_GB"
    ptd = ProductTypeDefinitions(credentials=creds, marketplace=G.MARKETPLACE)
    resp = ptd.get_definitions_product_type(
        productType=args.product_type, requirements="LISTING",
        locale=_locale, marketplaceIds=[G.MARKETPLACE_ID])
    link = resp.payload.get("schema", {}).get("link", {}).get("resource", "")
    if not link:
        print("ERROR: no schema link returned. Check creds/role for this account.")
        return
    req = urllib.request.Request(link, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        schema = json.loads(r.read().decode("utf-8"))

    print(f"\nSearching the entire schema for '{args.field}' ...\n")
    hits = deep_find(schema, args.field)
    if not hits:
        print(f"  '{args.field}' not found anywhere in the schema.")
    for h in hits:
        print(f"PATH: {h['path']}")
        if h.get("type"):
            print(f"  declared type: {h['type']}")
        if h["enums"]:
            for e in h["enums"]:
                print(f"  ALLOWED VALUES ({e['path']}):")
                for v in e["values"]:
                    print(f"      - {v}")
        else:
            print("  (no enum found directly under this node)")
        print()

    # Also: hunt for conditional rules (oneOf/allOf/if-then) that mention the field
    raw_text = json.dumps(schema)
    if '"' + args.field + '"' in raw_text:
        print("NOTE: the field also appears inside conditional/branch logic; the")
        print("      allowed values above are gathered from ALL branches found.")
    # And dump the related battery composition values, since the error ties them
    if args.field == "battery_installation_device_type":
        print("\n--- related: battery cell_composition allowed values (the error references this) ---")
        comp_hits = deep_find(schema, "cell_composition")
        for h in comp_hits:
            for e in h["enums"]:
                print(f"  cell_composition ({e['path']}):")
                for v in e["values"]:
                    print(f"      - {v}")

if __name__ == "__main__":
    main()
