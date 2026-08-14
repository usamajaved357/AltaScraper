"""probe_variation.py -- what a REAL variation family on your account shares.

CLAUDE.md Rule 4: the rules in listing/variations.py say a family must share its
product type, brand and item type keyword, and must differ on the theme's axes.
Those are written from Amazon's documented behaviour, and documented is not the
same as observed. This reads a family that ALREADY EXISTS on the account and
prints what its parent and children actually have in common and where they
differ, so the rule set can be confirmed against reality rather than trusted.

If it shows a field that matches across every child which the checker does NOT
require, that is a candidate rule we are missing. If it shows a field the checker
requires that genuinely differs, that rule is wrong and should come out.

    python probe_variation.py jack_uk UK B0PARENTASIN
    python probe_variation.py jack_uk UK PARENT-SKU --sku
    python probe_variation.py jack_uk UK PARENT-SKU --sku --raw

Read-only. Nothing is written and nothing is submitted.
"""
import json
import sys

sys.path.insert(0, r"D:\AltaScraper")

# Fields worth comparing across a family. Everything the app can see on a
# listing, not only the ones the checker currently uses -- the point is to find
# out whether there are more.
COMPARE = ["productType", "brand", "item_type_keyword", "variation_theme",
           "parentage_level", "recommended_browse_nodes", "manufacturer",
           "material", "department", "age_range_description", "country_of_origin",
           "supplier_declared_dg_hz_regulation", "batteries_required"]


def _flat(attrs, key):
    """An attribute's value, whatever shape Amazon wrapped it in."""
    v = (attrs or {}).get(key)
    if v is None:
        return ""
    if isinstance(v, list):
        if not v:
            return ""
        first = v[0]
        if isinstance(first, dict):
            for k in ("value", "name", "value_with_tax"):
                if k in first:
                    return str(first[k])
            return json.dumps(first, sort_keys=True)[:80]
        return str(first)
    if isinstance(v, dict):
        for k in ("value", "name"):
            if k in v:
                return str(v[k])
    return str(v)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) < 3:
        print(__doc__)
        return 2
    account_id, marketplace, ident = args[0], args[1].upper(), args[2]
    by_sku = "--sku" in argv

    cfg = json.load(open("config.json", encoding="utf-8"))
    acc = next((a for a in (cfg.get("accounts") or [])
                if str(a.get("id")) == account_id), None)
    if not acc:
        print("no account called %r" % account_id)
        return 1

    from domain import accounts as _acc
    from api import amazon_listings as _al

    creds = _acc.account_creds(acc)
    mkt_id = _acc.marketplace_id(marketplace)
    seller = str(acc.get("seller_id") or "")

    if not by_sku:
        print("This needs the parent's SKU, not its ASIN — the Listings API is")
        print("keyed by SKU. Find it on the listing and pass --sku.")
        return 2

    print("account : %s (%s)\nparent  : %s\n" % (account_id, marketplace, ident))
    got = _al.get_item(creds, marketplace, seller, ident, mkt_id,
                       included=("attributes", "summaries", "relationships"))
    if got["status"] != _al.OK:
        print("could not read it: %s" % (got["error"] or got["status"]))
        return 1

    raw = got.get("raw") or {}
    rels = raw.get("relationships") or []
    children = []
    for block in rels:
        for r in (block.get("relationships") or []):
            if str(r.get("type") or "").upper() != "VARIATION":
                continue
            theme = (r.get("variationTheme") or {})
            print("variation theme Amazon reports: %s" % (theme.get("theme") or "?"))
            print("  its attributes            : %s"
                  % ", ".join(theme.get("attributes") or []) or "(none listed)")
            children.extend(r.get("childSkus") or [])
    if not children:
        print("\nNo child SKUs on this listing — is it actually a parent?")
        return 0

    print("\nchildren: %s\n" % ", ".join(children))
    rows = {ident: got}
    for s in children[:12]:
        rows[s] = _al.get_item(creds, marketplace, seller, s, mkt_id,
                               included=("attributes", "summaries"))

    print("%-34s %-22s %s" % ("field", "parent", "children"))
    print("-" * 92)
    for f in COMPARE:
        vals = {}
        for sku, r in rows.items():
            if r["status"] != _al.OK:
                continue
            a = r.get("attributes") or {}
            v = _flat(a, f) or (r.get("product_type") if f == "productType" else "")
            vals[sku] = v
        parent_v = vals.get(ident, "")
        kid_vals = [v for s, v in vals.items() if s != ident]
        uniq = sorted(set(kid_vals))
        same = len(uniq) <= 1
        mark = "SAME" if same else "DIFFER"
        shown = (uniq[0] if uniq else "")[:36] if same else \
            ("; ".join(u[:16] for u in uniq))[:44]
        print("%-34s %-22s %-6s %s" % (f, (parent_v or "-")[:22], mark, shown or "-"))

    print("\n--- read this as ---")
    print("  SAME across children  -> a candidate rule. If listing/variations.py")
    print("                           does not require it, we may be missing one.")
    print("  DIFFER across children-> must NOT be required. If the checker demands")
    print("                           it, that rule is wrong and should come out.")
    print("  The theme's own attributes (printed above) are the ones that SHOULD")
    print("  differ -- that is what the family varies by.")

    if "--raw" in argv:
        print("\n--- the parent, verbatim ---")
        print(json.dumps(raw, indent=2)[:120000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
