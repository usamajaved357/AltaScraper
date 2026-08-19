"""Auto-fix asked for values, got good ones, and threw every one of them away.

    "once it does that i have to click autofix but autofix do not solve my
     problem, i still have to write the boxes ... it stops on dimensions.
     sometimes size etc etc"

Run on three real Nestwell listings. The AI answered well -- 50 cm x 10 cm x 5 cm
for the package, "148cm" for size, batteries_contained_in_equipment for the
battery packaging. Every single suggestion was then discarded with:

    batch edit crashed: int() argument must be a string, a bytes-like object
                        or a real number, not 'NoneType'

_apply_edits_batch is the ONLY way auto-fix writes anything, and it addresses
the row by its SHEET ROW NUMBER, read from the record as "_row".
dashboard._records() stamps that key on every record; data/backend._records(),
its database counterpart, did not. So "_row" was None, update_cell did int(None),
and the whole round was lost -- on every field, every round, every SKU, since
the day the app moved to the database.

Nothing about dimensions was broken. Dimensions were simply the fields most
often missing, so they were what the user watched it fail on.

The second half of this file covers the bug that was waiting behind it: a
dimension is TWO levels deep in Amazon's schema, and the source lookup read the
leaf as "length.value" instead of "value".
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


# ---------------------------------------------------------------------------
print("=== the contract: a record carries the row number used to write it ===")
src_dash = open(os.path.join(HERE, "dashboard.py"), encoding="utf-8").read()
src_back = open(os.path.join(HERE, "data", "backend.py"), encoding="utf-8").read()
truthy("the sheet reader stamps _row", 'rec["_row"] = ridx' in src_dash)
truthy("the writer addresses the row by it", 'row.get("_row")' in src_dash)
truthy("and the DATABASE reader stamps it too", 'r["_row"] = i + _FIRST_DATA_ROW' in src_back)
# One definition of "the first listing is row 2", not one per file.
from data.store import FIRST_DATA_ROW
check("both sides share one first-row constant", FIRST_DATA_ROW, 2)
truthy("  and the store's own lookup uses it",
       "int(row_n) - FIRST_DATA_ROW" in open(
           os.path.join(HERE, "data", "store.py"), encoding="utf-8").read())

# ---------------------------------------------------------------------------
print("\n=== against the real database: every record can address itself ===")
from data import choice as _choice

cfg = None
try:
    cfg = json.load(open("config.json", encoding="utf-8"))
except Exception:
    pass
backend = _choice.resolve(cfg or {}, "config.json")
print("  store in use: %s" % backend)

if backend != "db":
    print("  (this install is on sheets -- _row was never missing there)")
else:
    from data import backend as _data_backend
    from data import db as _db

    conn = _db.get_db("config.json")
    counts = {r["workspace_id"]: r["n"] for r in conn.execute(
        "SELECT workspace_id, COUNT(*) n FROM listings "
        "GROUP BY workspace_id ORDER BY n DESC")}
    wid = next(iter(counts), None)
    truthy("there is a workspace with listings to check", bool(wid))

    if wid:
        state = {"active_account_id": wid}
        _ws, _records = _data_backend.make(state, config_path="config.json")
        ws = _ws()
        rows = _records(ws)
        check("  every stored listing came back", len(rows), counts[wid])
        truthy("  every record has a row number",
               all(isinstance(r.get("_row"), int) for r in rows))
        # THE ROUND TRIP THAT MATTERS. update_cell turns the row number back
        # into a SKU; if that does not return the row we started from, auto-fix
        # would write one listing's values onto another.
        bad = [r["SKU"] for r in rows
               if ws._sku_for_row(r["_row"]) != r["SKU"]]
        check("  and it resolves back to that same listing", bad[:3], [])
        check("  the first listing is row %d" % FIRST_DATA_ROW,
              rows[0]["_row"], FIRST_DATA_ROW)
        # _row must never reach the writer as a column.
        from data.column_map import header_dict_to_row
        truthy("  and _row is dropped before any SQL write",
               "_row" not in header_dict_to_row({"SKU": "X", "_row": 7}))

# ---------------------------------------------------------------------------
print("\n=== a dimension is two levels deep, and the leaf is the LAST part ===")
import dashboard as D

# Amazon's real shape for a package dimension, as the app caches it: three axes,
# each with its own value and unit.
_UNITS = ["centimeters", "feet", "inches", "meters", "millimeters"]
_SCHEMA = {
    "enums": {},
    "subfields": {
        "item_package_dimensions": [
            {"path": "length.value", "kind": "number", "label": "length value"},
            {"path": "length.unit", "kind": "text", "label": "length unit", "enum": _UNITS},
            {"path": "width.value", "kind": "number", "label": "width value"},
            {"path": "width.unit", "kind": "text", "label": "width unit", "enum": _UNITS},
            {"path": "height.value", "kind": "number", "label": "height value"},
            {"path": "height.unit", "kind": "text", "label": "height unit", "enum": _UNITS},
        ],
        # A one-level field, to prove the ordinary case still works.
        "item_weight": [
            {"path": "value", "kind": "number", "label": "value"},
            {"path": "unit", "kind": "text", "label": "unit",
             "enum": ["grams", "kilograms", "pounds"]},
        ],
    },
}
_real_schema = D._load_schema
D._load_schema = lambda pt, *a, **k: _SCHEMA
# No AI key -> _resolve_fields returns exactly what the SOURCES gave, which is
# the half this section is about.
NOKEY = {"anthropic_api_key": ""}


def resolve(fields, ebay):
    out = D._resolve_fields(NOKEY, list(fields), {}, {"ebay": ebay, "sp": {}},
                            "Adjustable Wrench 250mm", "WRENCH", "UK")
    return {s["field"]: s.get("value", "") for s in out}


got = resolve(["item_package_dimensions"], {"Length": "50 cm"})
check("a source that names the axis fills it",
      got.get("item_package_dimensions.length.value"), "50")
check("  and its unit is snapped to Amazon's spelling",
      got.get("item_package_dimensions.length.unit"), "centimeters")
check("  while an axis the source is silent about stays empty",
      got.get("item_package_dimensions.width.value"), "")

# THE BUG: one combined string cannot say which number is the length. It used
# to be handed whole to a NUMERIC sub-field -- and to all three axes alike.
combined = resolve(["item_package_dimensions"], {"Item Dimensions": "50 x 10 x 5 cm"})
for _axis in ("length", "width", "height"):
    check("'50 x 10 x 5 cm' is not read as the %s" % _axis,
          combined.get("item_package_dimensions.%s.value" % _axis), "")
truthy("  and nothing non-numeric reached a number field",
       not any(str(v).lower().count("x") for k, v in combined.items()
               if k.endswith(".value")))

# The ordinary one-level case is untouched.
w = resolve(["item_weight"], {"Item Weight": "1.2 kg"})
check("a one-level value still fills", w.get("item_weight.value"), "1.2")
check("  and its unit still snaps", w.get("item_weight.unit"), "kilograms")

D._load_schema = _real_schema

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
