"""Round the over-precise dimensions already stored on drafts.

    "some data is put in there which do not make any sense"

Amazon's catalogue returns a competitor's dimensions already converted, so the
numbers arrive carrying the whole error of that conversion:

    item_length  9.842519675 inches      (25 cm)
    item_width   13.779527545 inches     (35 cm)
    item_height  157.48 inches           (4 m)

Nine decimal places on the width of a squeegee is not precision, it is float
noise, and it is shown to whoever is checking the draft.

get_competitor_asin_data now rounds these at the one point they enter the app,
so nothing generated from here on has the problem. This tidies what is ALREADY
stored, which no amount of fixing the intake will reach.

WHAT IT WILL NOT DO
  It only rewrites a value that is a number followed by a unit, and only to
  round the number. The unit is untouched, the axis is untouched, and any value
  it cannot parse as a number is left exactly as it is. It never adds, removes
  or renames a key.

Preview (writes nothing):   python tools/tidy_dimensions.py
Apply:                      python tools/tidy_dimensions.py --apply
"""
import collections
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from amazon_listing_generator import _dim_number

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "altascraper.db")

# "9.842519675 inches" -> number, then the rest. Only ever a plain number and a
# unit; anything else is left alone.
_NUM_UNIT = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*([A-Za-z][A-Za-z_ ]*)?\s*$")

# Only the keys that describe a physical measurement. A price or a count that
# happens to look similar is none of this script's business.
_DIM_KEY = re.compile(
    r"^item_(package_)?(length|width|height|depth|weight)$"
    r"|^(package|shipping)_(length|width|height|weight)$")


def tidy_value(v):
    """The rounded form, or None when there is nothing to change."""
    if not isinstance(v, str):
        return None
    m = _NUM_UNIT.match(v)
    if not m:
        return None
    num, unit = m.group(1), (m.group(2) or "").strip()
    rounded = _dim_number(num)
    out = (rounded + (" " + unit if unit else "")).strip()
    return out if out != v.strip() else None


def main(apply_it):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = list(conn.execute(
        "SELECT id, workspace_id, sku, attributes_json FROM listings"))

    per = collections.Counter()
    changed_rows, samples = 0, []
    updates = []
    for r in rows:
        try:
            pa = json.loads(r["attributes_json"] or "{}")
        except Exception:
            continue
        if not isinstance(pa, dict):
            continue
        edits = {}
        for k, v in pa.items():
            if not _DIM_KEY.match(str(k)):
                continue
            nv = tidy_value(v)
            if nv is not None:
                edits[k] = (v, nv)
        if not edits:
            continue
        changed_rows += 1
        per[r["workspace_id"]] += 1
        if len(samples) < 10:
            samples.append((r["sku"], list(edits.items())[:3]))
        for k, (_old, new) in edits.items():
            pa[k] = new
        updates.append((json.dumps(pa, ensure_ascii=False), r["id"]))

    print("rows scanned              : %d" % len(rows))
    print("rows with a value to round: %d" % changed_rows)
    print("by account                : %s" % dict(per))
    print("\nsamples:")
    for sku, edits in samples:
        print("   %s" % sku[:34])
        for k, (old, new) in edits:
            print("       %-24s %-24s -> %s" % (k, old, new))

    if not apply_it:
        print("\nPREVIEW ONLY -- nothing written. Re-run with --apply to write.")
        return 0

    with conn:
        conn.executemany("UPDATE listings SET attributes_json=? WHERE id=?", updates)
    print("\nwritten: %d row(s)" % len(updates))
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
