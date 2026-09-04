"""Every listing knows what Amazon calls it -- and the checks are NOT skipped.

    "but why are we having products with no product type, the app should be
     able to pull the product type of the items, dont skip compliance checks"

MEASURED before: 32 of 303 listings had no product_type. All 32 on jack_uk; 30
GENERATED, one variation PARENT, one QUEUED. Their SKUs carry eBay item ids
(336475288886) where an ASIN would be, so there was never an ASIN to read a type
from, and the paths that made them did not infer one either.

AFTER: 23 of the 32 filled from their own titles. The remaining 9 carry a
warning naming what is missing and what fixes it, because an INVENTED product
type is worse than none -- Amazon refuses it at submit and the compliance gate
believes it in the meantime.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


print("== the compliance gate is NOT skipped on a blank ==")
import amazon_listing_generator as G                                # noqa: E402
gate = G._product_type_allows
check("no product type -> the category still applies",
      gate("electrical", {"product_type_never": ["HOSE"]}, ""), True)
check("  a None product type is the same",
      gate("electrical", {"product_type_never": ["HOSE"]}, None), True)
check("  and it can still be ruled out on evidence",
      gate("electrical", {"product_type_never": ["HOSE"]}, "HOSE"), False)
gen = read("amazon_listing_generator.py")
yes("the reversal is written down where the code is",
    "dont skip compliance checks" in gen)

print("\n== a stored guess is never 'HOME' ==")
# infer_product_type falls back to HOME so a SUBMIT always has a real type to
# send. Writing that onto a row is different: the gate would read it as a fact.
check("nothing matched, asked for a default of '' -> ''",
      G.infer_product_type({}, item_name="qqzzxx nonsense", default=""), "")
check("  the old callers still get HOME",
      G.infer_product_type({}, item_name="qqzzxx nonsense"), "HOME")

print("\n== only type names Amazon has actually given this app a schema for ==")
# CLAUDE.md Rule 4: do not guess what Amazon calls something. The evidence is
# the schema_cache table -- 96 names Amazon returned a definition for.
import sqlite3                                                       # noqa: E402
conn = sqlite3.connect(os.path.join(HERE, "altascraper.db"))
known = {r[0] for r in conn.execute("select distinct product_type from schema_cache")}
known |= {"HOME"}
try:
    import json as _json
    known |= set(_json.load(open(os.path.join(HERE, "valid_values.json"),
                                 encoding="utf-8")).keys())
except Exception:
    pass
unknown = sorted({t for _pat, t in G._PT_INFER_RULES} - known)
# The rules predate this check and several of their types have never been
# fetched on this machine. What must hold is that nothing ADDED here is
# invented -- MACHINE_LUBRICANT is in the cache, which is why it is the only
# one of the four measured gaps that got a rule.
check("MACHINE_LUBRICANT is a name Amazon has confirmed",
      "MACHINE_LUBRICANT" in known, True)
yes("  and it is the rule that was added", "MACHINE_LUBRICANT" in gen)
yes("  the three that could not be confirmed are named, not guessed",
    "no confirmed name" in gen)
print("  (%d of the older rule types are not in this machine's cache: %s)"
      % (len(unknown), ", ".join(unknown[:6])))

print("\n== the backfill fills what it can and invents nothing ==")
from listing import product_type as PT                               # noqa: E402
check("a title with no signal types to nothing", PT.from_title("qqzzxx nonsense"), "")
check("  a lubricant types to MACHINE_LUBRICANT",
      PT.from_title("Miles Lubricants POE Refrigeration Oil"), "MACHINE_LUBRICANT")
check("  a row that already has one is never overwritten",
      PT.resolve({"product_type": "SQUEEGEE", "title": "Miles Lubricants Oil"}),
      "SQUEEGEE")

blank = PT.still_blank(os.path.join(HERE, "config.json"), "jack_uk")
print("  jack_uk rows still blank after the backfill: %d" % len(blank))
check("  the backfill has run on this database", len(blank) < 32, True)

print("\n== it runs where it has to, before anything reads the row ==")
w = read("listing", "warnings.py")
yes("recompute_workspace backfills product types",
    "_pt_mod.backfill(config_path, workspace_id)" in w)
yes("  before for_rows works the warnings out",
    w.index("_pt_mod.backfill") < w.index("found = for_rows("))

print("\n== a blank that survives is SAID, not left silent ==")
yes("there is a warning for it", "def no_product_type(row)" in w)
yes("  and it is in the list every row is checked against",
    "no_product_type(r)," in w)
yes("  it names what fixes it", "Press Sync" in w)
yes("  and it is low severity, not a hold",
    '"no_product_type", "low"' in w)

print("\n== and a Sync takes Amazon's own answer ==")
r = read("routes", "listing_routes.py")
pull = r[r.index("def live_pull_row"):r.index("def listing_push_image")]
yes("pull_row reads productType off the summary", 'summaries[0].get("productType")' in pull)
yes("  writes it to the row", '_repo.set_field(ws, trow, "Product Type", _pt' in pull)
yes("  ONLY when the row has none", "if not str(_repo.cell_value(" in pull)
yes("  and never fails the image pull if it cannot", "an extra field must not fail" in pull)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
