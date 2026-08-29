"""routes/input_upload_routes.py -- put a CSV or Excel file into the product queue.

    POST /input/upload            a file in, queued products out
    GET  /input/upload/template   a blank CSV with the right headers

THE THIRD WAY IN, and the first that does not need Google or typing. The queue
could already be filled from a Google input sheet (/input/import) or a row at a
time by hand (/input/add). Both fill the SAME table, so this one does too: it
calls input_import.add_row, exactly as the hand-add route does, and the
generator neither knows nor cares which of the three put a row there.

WHAT IT WILL NOT DO
  * Replace the queue. Every upload ADDS. A second file adds to the first, and
    nothing here can empty the queue -- /input/clear is still the only way work
    leaves it. That is the same promise the sheet import makes, for the same
    reason: silently dropping work because a file changed is not a behaviour
    worth having.
  * Stop at the first bad row. A file is usually mostly fine, and one unparsable
    line is not a reason to refuse the other two hundred. Each row is caught on
    its own and reported.
  * Reach Amazon, eBay or Google. This writes rows to the local queue. Nothing
    is generated and nothing is sent.

WHICH HEADERS IT UNDERSTANDS is not decided here -- see data/input_row.py, which
holds the one alias table, shared with the reader the generator itself uses.
"""
import csv
import io

from flask import request, jsonify, Response


# A file bigger than this is not a product list, and reading it into memory to
# find that out is how a local app stops responding. 8 MB is roughly 40,000
# rows of the shape this queue takes.
MAX_BYTES = 8 * 1024 * 1024

# Stop describing failures after this many. A file whose columns are wrong
# produces one error per row, and ten identical complaints say everything two
# hundred would.
MAX_ERRORS = 10

PREVIEW_ROWS = 5


# ---- reading the file -------------------------------------------------------
#
# MODULE LEVEL, not closures inside register(). They need no app, no config and
# no request -- they turn bytes into rows -- and as closures the only way to
# exercise them was to stand up Flask and post a file, which is why parsing bugs
# in this shape of code are usually found by a user rather than a test.


def read_csv_rows(data, filename=""):
    """Rows out of a CSV or TSV file, as lists of strings.

    utf-8-sig, because a CSV exported from Excel begins with a byte-order mark
    and the first header would otherwise be "﻿sku", matching nothing. The
    delimiter is sniffed rather than assumed: a European Excel writes
    semicolons, and every row arriving as a single column is the usual sign that
    the separator was guessed wrong.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # A spreadsheet saved as "CSV (Windows)" is cp1252. Falling back beats
        # refusing a file over one curly apostrophe.
        text = data.decode("cp1252", errors="replace")
    name = (filename or "").lower()
    delim = "\t"
    if not name.endswith(".tsv"):
        try:
            delim = csv.Sniffer().sniff(text[:8000], delimiters=",;\t|").delimiter
        except Exception:
            delim = ","
    return [list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)]


def read_xlsx_rows(data):
    """Rows out of the first worksheet of an .xlsx.

    read_only and values_only: this is a product list, not a document, and
    loading formatting for thousands of rows is the difference between a moment
    and a minute. Dates and numbers arrive as their Python types and become text
    in row_to_product.
    """
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        return [list(r) for r in wb[wb.sheetnames[0]].iter_rows(values_only=True)]
    finally:
        try:
            wb.close()
        except Exception:
            pass


def rows_of(data, filename):
    """(rows, error). Never raises -- a broken file is an answer, not a 500."""
    name = (filename or "").lower()
    try:
        if name.endswith(".xlsx"):
            return read_xlsx_rows(data), ""
        if name.endswith((".csv", ".tsv", ".txt")):
            return read_csv_rows(data, name), ""
        if name.endswith(".xls"):
            return [], ("That is an old-format .xls file, which this cannot "
                        "read. Open it and save as .xlsx or .csv.")
        return [], ("Give a .csv, .tsv or .xlsx file — that one is "
                    "%s." % (name.rsplit(".", 1)[-1] if "." in name
                             else "of no recognisable type"))
    except Exception as e:
        return [], "That file could not be read: %s" % str(e)[:200]


def register(app, *, CONFIG_PATH, _state):
    """Attach /input/upload* to the app."""

    def _wsid():
        return str(_state.get("active_account_id", "") or "") or "_no_account"

    # ---- the upload ---------------------------------------------------------

    @app.route("/input/upload", methods=["POST"])
    def input_upload():
        from data import input_import as _ii
        from data import input_row as _ir

        f = request.files.get("file")
        if f is None or not (f.filename or "").strip():
            return jsonify({"ok": False, "error": "No file was sent."}), 400
        filename = str(f.filename)

        data = f.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return jsonify({"ok": False, "error": (
                "That file is over %d MB. A product list this large is usually "
                "an export of something else — split it, or clear the columns "
                "you do not need." % (MAX_BYTES // (1024 * 1024)))}), 400
        if not data:
            return jsonify({"ok": False, "error": "That file is empty."}), 400

        rows, err = rows_of(data, filename)
        if err:
            return jsonify({"ok": False, "error": err, "filename": filename}), 400
        # A header row on its own is a file with no products in it, which is a
        # different problem from a file that would not parse.
        if not rows:
            return jsonify({"ok": False, "filename": filename,
                            "error": "There are no rows in that file."}), 400

        headers = [("" if h is None else str(h)) for h in rows[0]]
        mapping, matched, ignored = _ir.map_headers(headers)
        if not mapping:
            # SAY WHAT WAS IN THE FILE. "No columns matched" with nothing else
            # leaves the reader guessing at spelling; the headers we DID find
            # are the whole diagnosis.
            return jsonify({"ok": False, "filename": filename,
                            "found_columns": [h for h in headers if h.strip()],
                            "error": (
                                "None of that file's columns were recognised. "
                                "It needs a header row naming at least one of: "
                                "a source link, an Amazon link or ASIN, or a "
                                "product name.")}), 400

        wsid = _wsid()
        added = skipped = 0
        errors, preview = [], []
        stopped = False

        for n, row in enumerate(rows[1:], start=2):     # 2 = first row after headers
            if len(errors) >= MAX_ERRORS:
                stopped = True
                break
            try:
                if not any(str(c).strip() for c in row if c is not None):
                    continue                            # a blank line, not a failure
                product = _ir.row_to_product(row, mapping)
                # NOT AN ERROR. A list with a heading row, a totals row or a
                # note in it is normal, and calling those failures buries the
                # rows that really did break.
                if not _ir.is_generatable(product):
                    skipped += 1
                    continue
                _ii.add_row(CONFIG_PATH, wsid, product, source="upload")
                added += 1
                if len(preview) < PREVIEW_ROWS:
                    preview.append(product)
            except Exception as e:
                errors.append("Row %d: %s" % (n, str(e)[:160]))

        if stopped:
            errors.append("(stopped after %d errors — the rest of the file was "
                          "not read)" % MAX_ERRORS)

        return jsonify({
            "ok": True,
            "filename": filename,
            "workspace": wsid,
            "added": added,
            "skipped": skipped,
            "errors": errors,
            "mapped_columns": matched,
            "ignored_columns": ignored,
            "preview": preview,
            **_ii.summary(CONFIG_PATH, wsid),
        })

    # ---- the blank file to fill in ------------------------------------------

    @app.route("/input/upload/template")
    def input_upload_template():
        """A CSV with the headers this understands and one example row.

        The note goes in a column rather than a comment line: a leading "#" row
        is a row to every spreadsheet program, and the file has to survive being
        opened in Excel, saved, and uploaded back.
        """
        from data.input_import import COLUMNS

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(list(COLUMNS) + ["notes"])
        w.writerow([
            "https://www.amazon.co.uk/dp/B0EXAMPLE1",   # amazon_url
            "",                                          # competitor_asin
            "https://www.ebay.co.uk/itm/1234567890",     # ebay_url
            "Stainless Steel Garlic Press",              # item_name
            "4.20",                                      # source_cost
            "12.99",                                     # selling_price
            "3",                                         # handling_time
            "",                                          # upc
            "EXAMPLE ROW — DELETE IT. Fill in a source link OR an Amazon "
            "link; you do not need both. This 'notes' column is ignored on "
            "upload, but the row itself is not: leave it in and you will queue "
            "a garlic press.",
        ])
        w.writerow([""] * (len(COLUMNS) + 1))
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition":
                     'attachment; filename="product-queue-template.csv"'})
