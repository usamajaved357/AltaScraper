"""A spreadsheet into the product queue, and the Google sheet out of it.

    "Replace Google Sheet import with CSV/Excel file upload. After this, the app
     has exactly TWO ways to add products to the input queue — and Google Sheets
     is not one of them."

WHAT THIS GUARDS, and why each part earns its place:

ONE RULE FOR "CAN THIS ROW BE GENERATED FROM". The form (/input/add) and the
uploader must agree, or a row the form accepts is dropped by an upload with no
message anywhere saying the two disagree. Both call
data/input_row.is_generatable, and the test below asserts the CALL, not a
matching pair of copies -- two identical copies pass a value test and still
drift the first time either is relaxed (CLAUDE.md Rule 12).

THE PARSERS ARE TESTED ON REAL BYTES. Every check here builds an actual file --
an Excel-exported CSV with a byte-order mark and semicolon delimiters, a real
.xlsx and .xlsm through openpyxl -- because the bugs in this shape of code are
all in the decoding: a BOM welded to the first header, a European delimiter, a
handling time of 3 arriving as the float 3.0 and reaching a listing as "3.0".

REMOVAL IS ASSERTED BY LOOKING FOR A LIVE DECORATOR. The Google-sheet import is
commented out rather than deleted, so the string "import_for_workspace(" is
still in both route files. A test searching for that string passes just as
happily on commented-out code as on running code -- it would go green over
exactly the behaviour it exists to watch. What separates them is whether the
line is commented, so that is what is checked.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def read(*p):
    return open(os.path.join(*p), encoding="utf-8").read()


from data import input_row as ir                        # noqa: E402
from routes import input_upload_routes as up            # noqa: E402


print("=== a header is matched however it is spelled ===")
# Case, spaces, underscores and hyphens are all noise; the same name underneath.
for spelling in ("eBay Link", "EBAY_LINK", "ebay-link", "ebay link", " eBay  Link "):
    check("  %-16s -> ebay_url" % spelling, ir.column_for(spelling), "ebay_url")
# Every variant amazon_listing_generator.read_input_sheet accepts. If that
# reader and this one disagree, a file imports differently depending on which
# door it came through.
for name, col in (("ebay_link", "ebay_url"), ("ebay_price", "source_cost"),
                  ("amazon_link", "amazon_url"), ("amazon_price", "selling_price"),
                  ("delivery_time", "handling_time"), ("ean", "upc"),
                  ("item_name", "item_name")):
    check("  the generator's own %-14s" % name, ir.column_for(name), col)
# What people actually type.
for name, col in (("Buy Price", "source_cost"), ("Sell Price", "selling_price"),
                  ("RRP", "selling_price"), ("Barcode", "upc"),
                  ("ASIN", "competitor_asin"), ("Dispatch", "handling_time"),
                  ("Title", "item_name"), ("Product", "item_name")):
    check("  %-14s" % name, ir.column_for(name), col)
check("a column that means nothing is refused",
      ir.column_for("Warehouse Bin"), "")

# A BARE "price" IS AMBIGUOUS AND IS READ AS THE COST.
#
# Nothing in a file says whether "price" is what you pay or what you charge, so
# this has to choose, and the two ways of being wrong are not equal. Read as a
# cost, a sale price only inflates the computed price. Read as a sale price, a
# cost prices the listing AT what was paid for it and every sale loses the fees.
check("a bare 'price' is read as the cost -- the safe way to be wrong",
      ir.column_for("price"), "source_cost")


print("\n=== one rule for whether a row can be generated from ===")
check("a source link alone is enough",
      ir.is_generatable({"ebay_url": "https://www.ebay.co.uk/itm/1"}), True)
check("  an Amazon link alone is enough",
      ir.is_generatable({"amazon_url": "https://www.amazon.co.uk/dp/B0EXAMPLE1"}), True)
check("  an ASIN alone is enough",
      ir.is_generatable({"competitor_asin": "B0EXAMPLE1"}), True)
check("  a name alone is enough",
      ir.is_generatable({"item_name": "Wire Whisk"}), True)
check("a price and a barcode are NOT",
      ir.is_generatable({"source_cost": "4.20", "upc": "5012345678900"}), False)
check("  nor is nothing at all", ir.is_generatable({}), False)

# THE FORM AND THE UPLOAD ASK THE SAME FUNCTION. Asserted as a call, because two
# copies that agree today are still two copies.
_routes = read("routes", "input_routes.py")
_upload = read("routes", "input_upload_routes.py")
truthy("the hand-add form asks input_row", "_ir.is_generatable(p)" in _routes)
truthy("  and uses its wording for the refusal", "_ir.WHY_NOT" in _routes)
truthy("the upload asks the same function", "_ir.is_generatable(product)" in _upload)
check("  and neither re-implements the test",
      _routes.count('p["ebay_url"] or p["amazon_url"]'), 0)


print("\n=== a real CSV, as Excel exports one ===")
# Byte-order mark, semicolons, CRLF, a totals row and a trailing blank -- all of
# it normal, and all of it has broken a naive reader at some point.
csv_bytes = (
    "﻿eBay Link;Buy Price;Product Name;EAN;Warehouse Bin\r\n"
    "https://www.ebay.co.uk/itm/111;4.20;Garlic Press;5012345678900;A1\r\n"
    "https://www.ebay.co.uk/itm/222;9.99;Wire Whisk;;B2\r\n"
    ";;TOTAL;;\r\n"
    ";;;;\r\n"
).encode("utf-8")
rows, err = up.rows_of(csv_bytes, "supplier.csv")
check("it reads without error", err, "")
check("  every line, header included", len(rows), 5)
mapping, matched, ignored = ir.map_headers(rows[0])
check("the byte-order mark did not eat the first header",
      mapping.get(0), "ebay_url")
check("  the semicolon delimiter was found", len(mapping), 4)
check("  the columns it understood", sorted(matched),
      ["ebay_url", "item_name", "source_cost", "upc"])
check("  and it says what it ignored", ignored, ["Warehouse Bin"])

products = [ir.row_to_product(r, mapping) for r in rows[1:]]
usable = [p for p in products if ir.is_generatable(p)]
check("four data rows", len(products), 4)
# THREE, NOT TWO. A totals row carrying the word TOTAL in the name column has a
# name, and a name makes a row generatable. The app cannot tell it from a
# product called TOTAL, and a heuristic that guessed would drop real
# single-word products. It is queued, and shown in the upload preview, for a
# person to delete.
check("  three are usable: two products and the TOTAL line", len(usable), 3)
check("  the fully blank row is dropped", len(products) - len(usable), 1)
check("values land in the right columns", usable[0]["source_cost"], "4.20")
check("  including the barcode", usable[0]["upc"], "5012345678900")
check("  and the empty cell stays empty", usable[1]["upc"], "")


print("\n=== a real .xlsx, and a real .xlsm ===")
try:
    import openpyxl

    def _book(rows_in):
        wb = openpyxl.Workbook()
        for r in rows_in:
            wb.active.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    data = _book([["Amazon Link", "Cost", "Sell At", "Handling Days"],
                  ["https://www.amazon.co.uk/dp/B0EXAMPLE1", 4.2, 12.99, 3],
                  [None, None, None, None]])
    xrows, xerr = up.rows_of(data, "list.xlsx")
    check("an .xlsx reads without error", xerr, "")
    xm, xmatched, _ = ir.map_headers(xrows[0])
    check("  its columns are understood", sorted(xmatched),
          ["amazon_url", "handling_time", "selling_price", "source_cost"])
    p = ir.row_to_product(xrows[1], xm)
    # EXCEL HANDS BACK NUMBERS, NOT TEXT. A handling time of 3 arriving as the
    # float 3.0 would reach a listing as "3.0" days.
    check("  an integer does not become 3.0", p["handling_time"], "3")
    check("  and a decimal keeps its value", p["source_cost"], "4.2")
    truthy("  the row is usable", ir.is_generatable(p))

    # .xlsm is an xlsx with a macro part. openpyxl opens it and nothing here
    # runs the workbook, so there is nothing for a macro to do.
    mrows, merr = up.rows_of(
        _book([["ebay link", "cost"], ["https://www.ebay.co.uk/itm/999", 7.5]]),
        "supplier.xlsm")
    check("an .xlsm reads too", merr, "")
    check("  and yields its rows", len(mrows), 2)
except ImportError:
    print("  SKIP  openpyxl is not installed")


print("\n=== a file it cannot read is a refusal, never a crash ===")
_, e_pdf = up.rows_of(b"%PDF-1.4 not a spreadsheet", "notes.pdf")
truthy("a .pdf is refused, naming what it wanted", "csv" in e_pdf.lower())
# openpyxl genuinely cannot read the pre-2007 BIFF format, so the refusal has to
# say what to do rather than pretend or crash.
_, e_xls = up.rows_of(b"\xd0\xcf\x11\xe0", "old.xls")
truthy("an .xls is refused with instructions",
       "xlsx" in e_xls.lower() and "save as" in e_xls.lower())
_, e_bad = up.rows_of(b"\xff\xfe\x00garbage", "broken.xlsx")
truthy("a corrupt .xlsx is an error, not an exception", bool(e_bad))
check("  and it does not leak a stack trace", "Traceback" in e_bad, False)


print("\n=== a repeated column keeps the first ===")
# "cost" and "unit_cost" in one file is ambiguous. Letting the later one win
# silently would mean the number shown in the preview is not the number stored.
m, mt, ig = ir.map_headers(["cost", "unit_cost", "name"])
check("only one cost column is mapped", sorted(mt), ["item_name", "source_cost"])
check("  the first one", m.get(0), "source_cost")
check("  and the second is reported as ignored", ig, ["unit_cost"])


print("\n=== the Google sheet is no longer an input ===")
_listing = read("routes", "listing_routes.py")
# Live code, not the commented copy kept for restoring -- see the note at the
# top of this file.
check("the /input/import route is not live",
      bool(re.search(r'^[ \t]*@app\.route\("/input/import"', _routes, re.M)), False)
truthy("  but it is kept, commented, so it can be restored",
       re.search(r'#\s*@app\.route\("/input/import"', _routes))
check("Generate no longer reads a sheet when the queue is empty",
      bool(re.search(r'^[ \t]*_a, _u, _t, _err = _ii\.import_for_workspace\(',
                     _listing, re.M)), False)
truthy("  that block is kept, commented, too",
       re.search(r'#\s*_a, _u, _t, _err = _ii\.import_for_workspace\(', _listing))

# THE QUEUE ITSELF IS UNTOUCHED. It is the same table, written through the same
# function, whichever of the two ways in put the row there.
truthy("the upload writes through the queue's own add_row",
       "_ii.add_row(" in _upload)
truthy("  marking where the row came from", 'source="upload"' in _upload)
truthy("the hand-add route is still live",
       re.search(r'^[ \t]*@app\.route\("/input/add", methods=\["POST"\]\)',
                 _routes, re.M))
truthy("  as are status and rows",
       re.search(r'^[ \t]*@app\.route\("/input/status"\)', _routes, re.M)
       and re.search(r'^[ \t]*@app\.route\("/input/rows"\)', _routes, re.M))

# The button and its handler went with the route; a live handler calling a
# commented-out endpoint would just be a 404 waiting to be pressed.
_html = read("templates", "dashboard.html")
_queue_js = read("static", "js", "inputqueue.js")
check("the Import from sheet button is gone", "inputQueueImport(this)" in _html, False)
check("  and so is its handler",
      bool(re.search(r'^async function inputQueueImport\(', _queue_js, re.M)), False)
truthy("the upload panel has a place to render",
       'id="inputupload"' in _html)
truthy("  and something renders it", "inputUploadPanel()" in read("static", "js", "shell.js"))


print("\n=== the blank template names the columns it accepts ===")
_tpl = _upload
truthy("there is a template route", '"/input/upload/template"' in _tpl)
# Every header it offers must be one the matcher accepts, or the app ships a
# template its own uploader would ignore.
for col in ("ebay_url", "amazon_url", "item_name", "source_cost",
            "selling_price", "upc", "handling_time"):
    truthy("  the template's %-14s is understood" % col,
           ir.column_for(col) != "")
truthy("it tells you to delete the example rows", "DELETE BOTH EXAMPLE ROWS" in _tpl)


print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
