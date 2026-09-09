"""A cleared barcode clash stops being reported.

    "i see that the app highlights this ean is already used in this sku, and i
     replaced the ean with the fresh one and when i open the pdp it says the ean
     can be used and it does not overlap with another asin, but when i come our
     of pdp it still highlights that the ean can not be used"

THE PDP WAS RIGHT AND THE LIST WAS QUOTING A STALE ANSWER. The badge on the list
reads listings.warnings -- a column listing/warnings.py computes and STORES.
Its only writer is recompute_workspace, and its only caller was the end of a
generate/retry run. So editing a barcode changed the barcode and left the
verdict about it exactly as it had been since the listing was generated.

MEASURED, on two planted drafts sharing EAN 5060541510005:

    before          A ['duplicate_barcode', ...]   B ['duplicate_barcode', ...]
    change A's EAN  A ['duplicate_barcode', ...]   B ['duplicate_barcode', ...]
    recompute       A [...]                        B [...]

-- and note the second row. Giving A a fresh barcode cleared the warning on B
too, because a duplicate is a fact about a PAIR. That is why this recomputes the
WORKSPACE and not the row that was edited.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(*p):
    with io.open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


LR = read("routes", "listing_routes.py")
AF = re.sub(r"(?m:^[ \t]*//[^\n]*)", "",
            re.sub(r"(?s:/\*.*?\*/)", "", read("static", "js", "autofix.js")))
W = read("listing", "warnings.py")

print("== the verdict is the server's, and it is stored ==")
yes("warnings are computed and written per row",
    "def recompute_workspace(config_path, workspace_id" in W)
yes("  onto the listings.warnings column",
    "UPDATE listings SET warnings=?" in W)
# A DUPLICATE IS A FACT ABOUT A PAIR. for_rows indexes the whole workspace by
# barcode, which is why one row's fix changes another row's answer.
yes("  and a duplicate is decided across the whole workspace",
    'by_upc = _index(rows, "upc")' in W and "def duplicate_barcode(row, by_upc)" in W)

print("\n== editing a barcode re-asks the question ==")
_ed = LR[LR.index("    def edit():"):]
_ed = _ed[:_ed.index("\n    def ")]
yes("the edit route recomputes after a barcode change",
    "recompute_workspace(CONFIG_PATH, _wsid2)" in _ed)
# ONLY THE BARCODE. Every other editable column is a property of its own row,
# and a workspace pass on each blur-save would cost real time for no answer.
yes("  only for the barcode", 'if target == "col" and key == "UPC":' in _ed)
check("  and not for every column", 'key in _EDITABLE_COLS and target == "col"' in _ed
      and "recompute_workspace" in _ed.split('key in _EDITABLE_COLS')[0], False)
# THE WHOLE WORKSPACE, not the edited row -- see the measurement above.
yes("  across the workspace, not just this row",
    "_ws_id_of(ws)" in _ed and "workspace_id=?" in _ed)
# ONLY WHAT MOVED comes back: a full map on a keystroke would be a large reply
# for a small fact, and rows that went EMPTY are the ones being cleared.
yes("it returns only the rows whose verdict changed",
    '!= _before.get(r["sku"], "")' in _ed)
yes("  including the ones that went empty", '_wchanged[r["sku"]] = []' in _ed
    or 'json.loads(r["warnings"] or "[]")' in _ed)
yes("  under a named key", '"warnings_changed": _wchanged' in _ed)
# NEVER FATAL. A verdict that could not be re-worked-out must not fail a save
# that already happened.
yes("  and a failure here does not fail the save", "_wchanged = {}" in _ed)

print("\n== and the list is told, without a reload ==")
yes("the saver applies what came back", "j.warnings_changed" in AF)
yes("  to every row named, not just the edited one",
    "Object.keys(_wc).forEach" in AF)
yes("  by replacing that row's warnings", "row.warnings = _wc[k]" in AF)

print("\n== the badge itself is unchanged, and still reads the server ==")
LRD = read("static", "js", "listrow_detailed.js")
yes("the row badge reads r.warnings", "function lrEanClash(r)" in LRD
    and "r.warnings" in LRD)
# NOTHING IS WORKED OUT IN THE BROWSER. Rule 1 says a clash must be reported,
# and Rule 12 says one place decides what a duplicate is -- so the fix was to
# re-ask the server, never to let the screen decide a barcode is now fine.
yes("  and decides nothing itself",
    'w.type' in LRD and "barcode_live_on_amazon" in LRD)
check("  the browser does not compute a clash",
      "barcode_clash" in LRD, False)

# MEASURED END TO END through the running app, two planted drafts:
#   before          A ['duplicate_barcode','no_product_type']  B the same
#   /edit A -> new  answered {"status":200,
#                             "changed":[A, B]}
#   after, NO reload  A ['no_product_type']   B ['no_product_type']
#   planted rows removed, the real rows' warnings recomputed, no page errors.

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
