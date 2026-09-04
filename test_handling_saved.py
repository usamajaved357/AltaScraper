"""The handling time is recorded here, not only pushed to Amazon.

    "Pushed live to Amazon: 36 (this works)
     Saved: 0 (nowhere to record it) (this is broken)"

Amazon had the new handling time and the app kept showing the old one.

THE CAUSE was one missing attribute and one bare except. routes/handling_routes
walks every tab with `_ws().spreadsheet.worksheets()`; the database's
worksheet-shaped shim had no `.spreadsheet`, so that line raised AttributeError,
the `except Exception` around it returned "no column found", and the caller
reported that as a fact about the listings. The handling column was there the
whole time -- nothing ever got as far as looking for it.

Two things are checked: the attribute exists and resolves to THIS workspace, and
a failure is now carried out as a reason instead of being disguised as an answer.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


print("== the database's worksheet shim answers .spreadsheet ==")
from data.store import ListingStore, SheetLikeStore     # noqa: E402
from listing import repo as _repo                       # noqa: E402

s = SheetLikeStore(ListingStore("jack_uk", config_path=os.path.join(HERE, "config.json")))
check("SheetLikeStore has .spreadsheet", hasattr(s, "spreadsheet"), True)
book = s.spreadsheet
wss = book.worksheets()
check("  and it lists tabs", len(wss) >= 1, True)

# ONE WORKSPACE, NOT ALL OF THEM. A SKU is not unique across accounts -- he runs
# the same SKU on two of them -- so walking every workspace would write another
# account's listing.
titles = [getattr(w.store, "workspace_id", "") for w in wss]
check("  scoped to this workspace only", titles, ["jack_uk"])

print("\n== and the handling column is findable through it ==")
_HANDLING_COLS = ("Handling Days", "Handling Time", "Handling", "Lead Time", "Handling days")
h = _repo.read_headers(wss[0])
check("the tab has headers", len(h) > 10, True)
check("  a handling column is found", bool(_repo.find_col(h, _HANDLING_COLS)), True)
check("  and a SKU column", bool(_repo.find_col(h, ("SKU", "Sku", "sku"))), True)
check("  the SKU column has values", len(_repo.column_values(
    wss[0], _repo.find_col(wss[0].row_values(1), ("SKU",)))) > 1, True)

print("\n== a failure is reported as a failure ==")
src = read("routes", "handling_routes.py")
fn = src[src.index("def _sheet_write_handling"):src.index("@app.route(\"/stock/bulk_update\"")]
check("the walk no longer swallows its error", "except Exception as e:" in fn, True)
check("  it carries the reason out", "return updated, tabs_touched, had_col, str(e)[:200]" in fn, True)
check("  and so does a failed write", 'why.append("%s: %s"' in fn, True)

print("\n== the three reasons are told apart ==")
# "nowhere to record it" used to cover all of them, including a bug.
route = src[src.index("def handling_bulk_update"):]
check("an error says what went wrong", "Nothing could be recorded here: %s" in route, True)
check("  a missing column says that", "There is no handling-time column" in route, True)
check("  and a SKU with no row here says THAT",
      "have no listing row in this app" in route, True)
check("  the missing ones are listed, not just counted",
      'out["sheet_missing"] = missing' in route, True)

# NOTHING IS CREATED for a SKU this app does not have. A handling-time change is
# not a reason to invent a half-empty draft; Sync is what pulls a listing in.
check("  and none of them is invented",
      "upsert" not in route and "INSERT" not in route.upper(), True)

print("\n== the front end shows the server's reason ==")
js = read("static", "js", "handling.js")
js = re.sub(r"(?s:/\*.*?\*/)", "", js)
js = re.sub(r"(?m:^[ \t]*//[^\n]*)", "", js)
check("it prints sheet_note", "if(j.sheet_note) msg += ` — ${j.sheet_note}`;" in js, True)
check("  and no longer guesses from sheet_has_column",
      "nowhere to record it" not in js, True)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
