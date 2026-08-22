"""Two layouts, one database -- and the checks that went quiet when they mixed.

    "the compliancechecks the ipchecks and restriction checks and gated checks
     are not working properly, check each asin in database"

Two independent faults, both of which make a check report NOTHING, which is the
one failure mode that looks exactly like success.

FAULT 1 -- THE COLUMN SHIFT.
Miles Lubricants listings are written in Miles' own 13-column sheet layout. The
database's positional writer assumed there was only ever one layout, the standard
49-column one, so every Miles value landed one meaning to the left: the title
was filed as the source URL, bullet point 1 as the SKU, the description as the
fee source. Title and bullets are exactly what the compliance, IP, restricted and
claims checks read -- so all four ran against an empty listing and passed it.
Twenty-one rows of jack_uk, a quarter of the account, silently unchecked.

FAULT 2 -- THE MISSING MARKETPLACE.
listing/restricted.py resolves its tier per marketplace and downgrades to a
generic RESTRICTED when it does not know one. The card never supplied one, so
PROHIBITED and GATED both collapsed to RESTRICTED on every row -- and the screen
reads the tier back to decide between a red flag and "gated: documents required".
A product Amazon forbids outright was shown as a paperwork errand.

Both are asserted here against the real rulebooks, not mocks.
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from data.column_map import _num, header_dict_to_row, col_for_header
from data.store import ORDERED_HEADERS, SheetLikeStore
from domain.brand_listing import MILES_SHEET_HEADERS


print("=== a money column does not read a number out of prose ===")
# Every one of these was a real stored value. "ISO 220" became a profit of
# GBP220.00 on a real row, because the old last-resort branch pulled the first
# run of digits out of any string at all.
for text in ("Miles NXT POE-LT 320", "ISO 220", "Bullet Point 3", "Description",
             "Backend Keywords", "Compliance Report", "Uploaded",
             "2000W Electric Patio Heater", "12V 5A DC UK Plug Power Supply"):
    check("  %-30r is not a number" % text, _num(text), None)

print("\n=== but a price still is one, however it is written ===")
# The sheet really does store "GBP16.00" with no space. A word-boundary strip
# cannot see that code (P runs into 1), so it has to be allowed deliberately --
# this exact format is what cost 53 of 55 prices on the first real import.
for text, want in (("GBP16.00", 16.0), ("£12.34", 12.34), ("$5", 5.0),
                   ("-26.60%", -26.6), ("1,234", 1234.0), ("16", 16.0),
                   ("approx 12.50", 12.5), ("12.50 each", 12.5),
                   ("from 9.99", 9.99), ("9.99 inc VAT", 9.99)):
    check("  %-16r reads as %s" % (text, want), _num(text), want)
check("  and nothing at all is still nothing", _num(""), None)


print("\n=== a header row is never stored as a product ===")


class _Fake:
    def __init__(self):
        self.rows = []

    def upsert_row(self, rec):
        self.rows.append(header_dict_to_row(rec))
        return "x"

    def get_all_rows(self):
        return []


ws = SheetLikeStore(_Fake())
# The Miles header begins SKU | Title | Item Highlights where the standard order
# begins Competitor ASIN | Source URL | UPC. The old test compared the first
# three cells against the standard order and nothing else, so this row failed it,
# was taken for data, and was stored as a listing whose SKU was the literal text
# "Bullet Point 1" -- sitting in jack_uk among real products.
truthy("the Miles header is recognised as a header",
       ws._looks_like_header(MILES_SHEET_HEADERS))
truthy("  so is the standard one", ws._looks_like_header(list(ORDERED_HEADERS)))
truthy("  a real product row is NOT",
       not ws._looks_like_header(["8.00_3Days_B0G1K5B7QS", "A Kitchen Colander",
                                  "Dishwasher safe", "Stainless steel"]))
check("  and appending the header stores nothing", ws.append_row(MILES_SHEET_HEADERS), 0)
check("  including via insert_row at any position",
      ws.insert_row(MILES_SHEET_HEADERS, index=7), 0)
check("  nothing reached the store", len(ws.store.rows), 0)


print("\n=== and the row after it lands in the columns it means ===")
# Announcing the header is what teaches the shim this layout; the row that
# follows is then read in it.
ws2 = SheetLikeStore(_Fake())
ws2.append_row(MILES_SHEET_HEADERS)
ws2.update([["MSF2047001",
             "Miles Lubricants POE Refrigeration Oil ISO 320",
             "Full synthetic ISO 320 polyol ester lubricant",
             "POE FULL SYNTHETIC FORMULA -- polyol ester base",
             "ISO 320 VISCOSITY GRADE -- 320 cSt at 40C",
             "BULLET THREE", "BULLET FOUR", "BULLET FIVE",
             "<p>Miles NXT POE-LT 320</p>",
             "compressor oil iso 320", "", "No batteries.", "No"]],
           range_name="A2:M2")
check("  exactly one listing was stored", len(ws2.store.rows), 1)
got = ws2.store.rows[0] if ws2.store.rows else {}
for col, want in (("sku", "MSF2047001"),
                  ("title", "Miles Lubricants POE Refrigeration Oil ISO 320"),
                  ("item_highlights", "Full synthetic ISO 320 polyol ester lubricant"),
                  ("bullet_1", "POE FULL SYNTHETIC FORMULA -- polyol ester base"),
                  ("bullet_5", "BULLET FIVE"),
                  ("description_html", "<p>Miles NXT POE-LT 320</p>"),
                  ("search_terms", "compressor oil iso 320"),
                  ("compliance_notes", "No batteries.")):
    check("  %-18s" % col, str(got.get(col) or ""), want)
# The shift's signature: the SKU in the competitor's column, the title in the
# source URL, and a viscosity grade filed as money.
for col in ("competitor_asin", "source_url", "profit", "buy_box_price"):
    check("  %-18s stays empty" % col, str(got.get(col) or ""), "")

# Without the announcement nothing has changed: the standard layout is still the
# default, so every existing caller reads exactly as it did before.
ws3 = SheetLikeStore(_Fake())
ws3.update([["B0G1K5B7QS", "http://src", "50000", "8.00_3Days_B0G1K5B7QS"]],
           range_name="A2:D2")
check("  a standard row is still read the standard way",
      str((ws3.store.rows[0] if ws3.store.rows else {}).get("competitor_asin") or ""),
      "B0G1K5B7QS")


print("\n=== the Miles compliance column has somewhere to land ===")
# dashboard._card already reads gm("Compliance Notes", "Compliance Report"), so
# the two were always meant to be one field -- but nothing mapped the second, so
# every Miles listing showed an empty compliance panel and no error.
check("  Compliance Report maps to the notes column",
      col_for_header("Compliance Report"), "compliance_notes")
check("  layout scaffolding still maps nowhere",
      [h for h in ("Column 1", "Uploaded") if col_for_header(h)], [])


print("\n=== the restricted check is told which country's rules apply ===")
from listing.restricted import check_restricted_type


def tiers(title, mkt):
    r = check_restricted_type(title, mkt, product_type="", category_path="")
    return sorted({m.get("tier") for m in (r.get("matches") or [])})


# THE COLLAPSE. Every one of these is a real distinction the screen depends on:
# listings.js paints red only for PROHIBITED and says "gated -- documents
# required to list" for anything else that matched.
check("  an unknown marketplace flattens a US prohibition",
      tiers("Disposable Vape Pen 600 Puffs Nicotine Free", ""), ["RESTRICTED"])
check("  named, it is prohibited",
      tiers("Disposable Vape Pen 600 Puffs Nicotine Free", "US"), ["PROHIBITED"])
check("  an unknown marketplace flattens a gate",
      tiers("Upholstered Fabric Armchair Living Room Accent Chair", ""), ["RESTRICTED"])
check("  named, it is gated",
      tiers("Upholstered Fabric Armchair Living Room Accent Chair", "UK"), ["GATED"])

import dashboard as D

# The resolver must go through routes/scope, which is the app's one marketplace
# resolver and carries the step the old chain was missing -- the ACCOUNT'S OWN
# default. _state["active_marketplace"] is written only when somebody chooses a
# marketplace, and Listings is not that screen, so it is "" on a normal load.
for aid, want in (("jack_uk", "UK"), ("nestwell_goods", "UK"), ("sheelady_us", "US")):
    D._state["active_account_id"] = aid
    D._state["cfg"] = None
    D._state["active_marketplace"] = ""
    check("  %-16s is judged by its own country" % aid, D._card_marketplace({}), want)

# NOT the row's own listing_marketplace column, however tempting. It is 'UK' on
# every row of every workspace -- sheelady_us included -- because it is the
# schema default and nothing has ever written it.
src = open("dashboard.py", encoding="utf-8").read()
i = src.find("def _card_marketplace")
body = src[i:i + 3000]
truthy("  and not from the column that is 'UK' for everyone",
       "listing_marketplace" not in body.split('"""')[2] if body.count('"""') > 2
       else True)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
