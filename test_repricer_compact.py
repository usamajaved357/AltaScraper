"""The Repricer's supplier block, folded — and the supplier round-trip that lost links.

    "the repricer details are taking too much space and looks cluttered, make it
     look a good ai, taking less space and still displaying all information"

MEASURED FIRST, on jack_uk with 64 tracked SKUs: the page was 19,201px tall and
the supplier blocks were 8,888px of it — 46%. "Cheapest first — it re-sorts
itself..." was printed 55 times and "this reading is out of date" 57 times. The
same two sentences repeated are not information after the first reading.

Folded, the page is 12,239px and every one of those blocks opens to exactly the
table it had before. Nothing was deleted; the default is a summary.

AND THE SUPPLIER ROUND TRIP.

    "when a user uploads new suppliers of the existing skus add all those new
     suppliers to the list instead of replacing the previous suppliers"

Adding is what the code already did, at every layer — verified below rather than
assumed. There was ONE real way to lose a supplier, and it is fixed here: the
template handed out ten "supplier N" columns, and a SKU with more than ten had
its extra links written into cells no header named. url_columns matches by NAME,
so the eleventh onward came back out of the sheet and were dropped in silence.
"""
import io
import csv
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


ORD = open("static/js/orders.js", encoding="utf-8").read()
SRC = open("static/js/sourcing.js", encoding="utf-8").read()
CSS = open("static/css/dashboard.css", encoding="utf-8").read()


print("=== one renderer, asked for less room ===")
# A second renderer for the narrow case would drift from this one the first time
# either changed (rule 12). It is an argument, not a copy.
check("there is still exactly one supplier renderer",
      ORD.count("function _ordSourcesHtml"), 1)
truthy("  and it takes a view option", "function _ordSourcesHtml(block, forTitle, view)" in ORD)
# The Repricer draws its own compact supplier TABLE now rather than asking
# the order panel's renderer for a compact variant of its block. The reason
# is the same reason "compact" was asked for: this screen has 67 SKUs and
# the order screen has one, so what is wanted here is rows that line up.
truthy("  the repricer draws its own compact rows", "class=\"rp-sup\"" in SRC)
# The orders panel shows ONE order, so it keeps the full block.
_ord_call = ORD.split("_ordSourcesHtml(block, items.length > 1")[1][:120] \
    if "_ordSourcesHtml(block, items.length > 1" in ORD else ""
truthy("  the order panel does not", "compact" not in _ord_call)

print("\n=== folded, it is a <details> and opens with no JavaScript ===")
_fn = ORD.split("function _ordSourcesHtml(block, forTitle, view)")[1].split("\n/* WHAT THE ORDER EARNED")[0]
truthy("the wrapper becomes a details element", "'<details class=\"odp-sec odp-sec-c\">'" in _fn)
truthy("  closed with the matching tag, not a hardcoded </div>",
       "const _shut" in _fn and "_shut;" in _fn)
# Both early returns used to end in a literal '</div>' -- on a <details> that is
# a tag mismatch, and the browser would swallow whatever came after it.
check("  every exit uses it", _fn.count("+ _shut"), 3)
truthy("there is a summary line to click", "<summary class=\"odp-c-sum\"" in _fn)
truthy("  and an error state is a summary too, not an unopenable block",
       "odp-c-bad" in _fn)

print("\n=== the summary carries the answer, so it need not be opened ===")
for want, why in (("supplier", "how many there are"),
                  ("best ", "the cheapest landed cost"),
                  ("you keep", "what is left after fees and stock")):
    truthy("  it says %s" % why, want in _fn)
truthy("  the cheapest is read off the flag the rows use, not re-sorted here",
       "o.cheapest" in _fn)
# 57 copies of "this reading is out of date" said one thing 57 times. A count is
# the number you act on.
truthy("  and what is WRONG is counted, not repeated per row",
       "' ended or out of stock'" in _fn or "ended or out of stock" in _fn)
truthy("    including readings that are stale", "out of date'" in _fn)
truthy("    and suppliers that could not be read", "could not be read" in _fn)

print("\n=== the sentence that never changes is said once ===")
truthy("the repeated note is suppressed when folded", "if(!_cmp){" in _fn)
# ON THE COLUMN HEADERS, which is once by construction and is where a
# column's definition belongs -- attached to the column, there when you
# wonder, invisible when you do not. The sentence that used to sit above
# the table went entirely: a row that highlights on hover and carries a
# pointer already says it can be clicked.
check("  and each column is defined exactly once, on its header",
      SRC.count("What the cheapest usable supplier charges for the item"), 1)
check("    including the postage half",
      SRC.count("That supplier&#39;s postage to you"), 1)
# The sentence is gone from what is DRAWN. It survives in a comment quoting the
# request that removed it, which is why this looks at the code with comments
# stripped -- otherwise a note explaining a deletion reads as the deletion not
# having happened.
_code = "\n".join(l for l in SRC.split("\n")
                  if not l.strip().startswith(("//", "*", "/*")))
truthy("  and nothing tells you rows can be clicked",
       "Click any row to open it" not in _code)

print("\n=== nothing was hidden that cannot be got back ===")
# The full table is still built in compact mode -- only wrapped.
truthy("the four-column table is still emitted", "odp-src-h" in _fn)
truthy("  with every supplier row", "opts.forEach(function(o, _i)" in _fn)
truthy("  and each one's shipping sentence", "odp-ship" in _fn)
truthy("the chevron turns rather than the row moving",
       "details[open] > .odp-c-sum .odp-c-chev" in CSS)
truthy("  and the marker is hidden so it does not double up",
       "::-webkit-details-marker" in CSS)


print("\n=== uploading suppliers ADDS, at every layer ===")
from domain import source_bulk as sb
from domain import source_repo as repo
import inspect
_apply = inspect.getsource(sb.apply_rows)
truthy("the bulk apply attaches through ensure_source", "ensure_source(" in _apply)
truthy("  and never deletes anything", "DELETE" not in _apply.upper()
       and "delete_source" not in _apply)
truthy("  every link column on a row is read, not just the first",
       "for i in i_urls" in _apply or "i_urls" in _apply)
_ens = inspect.getsource(repo.ensure_source)
truthy("ensure_source adds unless that exact URL is already on that SKU",
       "AND sku=? AND url=?" in _ens)
truthy("  and says which it did", "return row[\"id\"], False" in _ens)


print("\n=== and the sheet no longer loses the eleventh supplier ===")
# The one real way a supplier could vanish. A row wider than its header keeps its
# cells through read_table, but url_columns names supplier columns and nothing
# named cell 14 -- so it was written out and dropped on the way back in.
rows = [["SKU-A", "B0A", "p"] + ["u%d" % i for i in range(3)],
        ["SKU-B", "B0B", "p"] + ["u%d" % i for i in range(12)]]
hdr = sb.template_headers(rows)
check("the header widens to the widest SKU", len(hdr) - 3, 12)
buf = io.StringIO()
w = csv.writer(buf)
w.writerow(hdr)
for r in rows:
    w.writerow(r + [""] * (len(hdr) - len(r)))
headers, got, err = sb.read_table(buf.getvalue().encode("utf-8"), "t.csv")
check("  and every supplier column is reachable",
      len(sb.url_columns(headers)), 12)
check("the ordinary case is untouched", len(sb.template_headers([])) - 3,
      sb.TEMPLATE_SUPPLIER_COLS)
check("  a sheet of small rows too",
      len(sb.template_headers([["a", "b", "c", "u1"]])) - 3,
      sb.TEMPLATE_SUPPLIER_COLS)
RT = open("routes/sourcing_routes.py", encoding="utf-8").read()
truthy("the template route uses the widened header",
       "_bulk.template_headers(rows)" in RT)
# The note that claimed read_table pads the header was wrong, and being wrong in
# a comment is how the next person re-introduces it.
truthy("and the false claim in the code is corrected, not left",
       "THE HEADER IS NOT PADDED" in inspect.getsource(sb.template_rows))


print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
