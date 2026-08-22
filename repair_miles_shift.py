"""repair_miles_shift.py -- put the column-shifted Miles rows back where they belong.

WHAT WENT WRONG (plain English)
Miles Lubricants listings are written in Miles' own spreadsheet layout, which has
different columns in a different order from the app's standard one. When those
rows were saved to the database, nothing translated between the two layouts, so
every value landed one meaning to the left of where it belonged: the product's
title was filed as its source web address, its first bullet point was filed as
its SKU, and its description was filed as the "fee source".

That is why the compliance, IP, restricted-product and claims checks reported
nothing for these products. Those checks read the title and the bullet points.
Both were empty, so there was nothing to find, and a clean result looks exactly
like a product that passed.

The cause is fixed in data/store.py so it cannot happen again. This script fixes
the rows that were already written.

WHAT CAN AND CANNOT BE PUT BACK
Anything that landed in a TEXT column is still there, word for word, and is
moved back: SKU, title, item highlights, bullet points 1 and 2, description.

Anything that landed in a MONEY column is gone. Those columns store numbers, so
saving "ISO 220" into one kept 220.00 and discarded the words. That destroyed
bullet points 3, 4 and 5, the backend keywords, and the compliance report. They
cannot be recovered from the database and have to be generated again. Each
repaired row gets a note saying so, rather than being left looking complete.

USAGE
    python repair_miles_shift.py            # dry run -- shows every change
    python repair_miles_shift.py --apply    # write them
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from data import db as _db
from data.store import ORDERED_HEADERS
from domain.brand_listing import MILES_SHEET_HEADERS
from data.column_map import HEADER_TO_COL, HEADER_ALIASES

CONFIG = "config.json"

# Where each value ACTUALLY belongs. Position i of the standard layout was filled
# with position i of the Miles layout, so reading the two side by side gives the
# correction directly rather than by a hand-written table that could be wrong.
SHIFT = list(zip(ORDERED_HEADERS, MILES_SHEET_HEADERS))

# Standard columns that store a number. A value that passed through one of these
# has already lost its words and cannot be recovered.
LOSSY = {"Buy Box Price (GBP)", "Our Price (GBP)", "Amazon Fees (GBP)",
         "Profit (GBP)", "Margin %", "ROI %"}

# Miles columns that are layout scaffolding, not listing data.
DISCARD = {"Column 1", "Uploaded"}


def db_col(header):
    return HEADER_TO_COL.get(header) or HEADER_ALIASES.get(header)


def damaged_rows(conn):
    """The rows written under the shift.

    Identified by the SHAPE OF THE DAMAGE, not by a remembered list of ids: the
    SKU column holds prose rather than a SKU, and the title column is empty. A
    healthy row can match neither.
    """
    out = []
    for r in conn.execute("SELECT * FROM listings ORDER BY id"):
        sku = (r["sku"] or "").strip()
        title = (r["title"] or "").strip()
        if title or not sku:
            continue
        # A real SKU is one token. Anything with spaces in the SKU column and no
        # title at all is a shifted row's bullet point.
        if " " in sku:
            out.append(r)
    return out


def plan_for(row):
    """{db column -> new value} plus the list of fields that cannot be restored."""
    fields, lost = {}, []
    for std_header, miles_header in SHIFT:
        if miles_header in DISCARD:
            continue
        src = db_col(std_header)
        dst = db_col(miles_header)
        if not src or not dst:
            continue
        if std_header in LOSSY:
            # The words are already gone; record what is missing rather than
            # moving a number into a text field and calling it a bullet point.
            lost.append(miles_header)
            continue
        val = row[src]
        fields[dst] = "" if val is None else str(val)
    # The columns the values came OUT of must be cleared, or the title stays in
    # source_url as well as in title and the row reads as two products.
    for std_header, miles_header in SHIFT:
        src = db_col(std_header)
        if src and src not in fields:
            fields[src] = None
    return fields, lost


HEADER_ROW_MARK = "Bullet Point 1"


def main(apply_it):
    conn = _db.get_db(CONFIG)
    rows = damaged_rows(conn)
    print("Found %d damaged rows.\n" % len(rows))
    repaired = deleted = 0
    for r in rows:
        # The Miles HEADER row, stored as if it were a product. It is not a
        # listing and never was -- there is nothing in it to repair.
        if (r["sku"] or "").strip() == HEADER_ROW_MARK:
            print("  id=%-5s DELETE  the Miles header row stored as a listing" % r["id"])
            if apply_it:
                conn.execute("DELETE FROM listings WHERE id=?", (r["id"],))
            deleted += 1
            continue

        fields, lost = plan_for(r)
        note = ("Repaired from a column-shifted import. These were destroyed when "
                "they were written into number columns and must be generated "
                "again: " + ", ".join(lost) + ".") if lost else ""
        if note:
            existing = (r["notes"] or "").strip()
            fields["notes"] = (existing + " | " + note) if existing else note
        # A repaired row has never been checked -- its title and bullets were
        # empty when the checks last ran. Say so rather than leaving a blank,
        # which reads as "checked and clean".
        fields["status"] = "NEEDS_REVIEW"

        print("  id=%-5s REPAIR  sku=%-12s title=%s"
              % (r["id"], fields.get("sku", "")[:12], (fields.get("title") or "")[:44]))
        print("           lost: %s" % (", ".join(lost) or "nothing"))
        if apply_it:
            sets = ",".join("%s=?" % c for c in fields)
            conn.execute("UPDATE listings SET %s WHERE id=?" % sets,
                         list(fields.values()) + [r["id"]])
        repaired += 1

    if apply_it:
        conn.commit()
        print("\nAPPLIED: %d repaired, %d deleted." % (repaired, deleted))
    else:
        print("\nDRY RUN: %d would be repaired, %d deleted. "
              "Re-run with --apply to write." % (repaired, deleted))


if __name__ == "__main__":
    main("--apply" in sys.argv)
