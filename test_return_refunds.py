"""domain/return_refunds.py -- was each return actually refunded?

Owner, 30 Sep 2026: "please show me ... if we have already paid the refunds and
what is the status of the returns or if the returns closed without resolution or
refund". Measured the same day on nestwell_goods UK: six approved/pending
returns with no refund in any money source, one the returns report called
"refunded 31.85" with no money moved, and two where the report showed the list
price while the buyer was refunded the (discounted) price they paid.

A fixture account per class, the discount case (= full, not a mismatch), the
overdue rule, a refund with no return behind it, and account isolation (the
same order id in another account never leaks in). Also: the returns report's
tracking/delivery columns are parsed and kept, a later file without them does
not blank them, the daily pull stores through the one fetch path, and the
route and the job exist.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db                     # noqa: E402
from domain import return_refunds as _rr       # noqa: E402
from domain import returns_store as _rs        # noqa: E402
from domain import returns_view as _rv         # noqa: E402
from domain import returns_sync as _rsync      # noqa: E402
from domain import pnl_ledger as _pl           # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


A, B, MKT = "__rrefund_a__", "__rrefund_b__", "UK"
TODAY, START, END = "2026-09-30", "2026-08-01", "2026-09-30"
conn = _db.get_db()


def wipe():
    for t in ("order_lines", "order_fees", "returns"):
        for ws in (A, B):
            conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (ws,))
    conn.commit()


def line(ws, oid, day, sku, rev, units=1):
    conn.execute("INSERT INTO order_lines (workspace_id, marketplace, order_id, "
                 "purchase_date, sku, asin, title, units, revenue, shipping, currency, "
                 "status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (ws, MKT, oid, day + "T10:00:00Z", sku, "B0" + sku, "T " + sku,
                  units, rev, 0.0, "GBP", "Shipped"))


def refund(ws, oid, posted, amount, tax=0.0):
    conn.execute("INSERT INTO order_fees (workspace_id, marketplace, order_id, "
                 "posted_date, refunds, refund_tax, refund_units, currency) "
                 "VALUES (?,?,?,?,?,?,1,'GBP')", (ws, MKT, oid, posted, amount, tax))


def ret(oid, date, status, sku, refunded=None, resolution="StandardRefund",
        delivered=None, amount=None, **extra):
    d = {"kind": "mfn", "date": date, "order_id": oid, "sku": sku, "asin": "B0" + sku,
         "name": "Product " + sku, "qty": 1, "reason": "NOT_AS_DESCRIBED",
         "status": status, "resolution": resolution, "refunded": refunded,
         "order_amount": amount, "delivered": delivered}
    d.update(extra)
    return d


wipe()
# ---- account A ----------------------------------------------------------------
line(A, "DISC", "2026-08-31", "S1", 33.24)        # list 34.99, buyer paid 33.24
refund(A, "DISC", "2026-09-21", 33.24)
line(A, "PART", "2026-09-01", "S2", 14.49)
refund(A, "PART", "2026-09-16", 8.69)
line(A, "VAT", "2026-09-01", "S9", 12.00)         # 10.00 + 2.00 VAT itemised = full
refund(A, "VAT", "2026-09-10", 10.00, 2.00)
line(A, "UNREF", "2026-08-28", "S3", 19.99)
line(A, "RECENT", "2026-09-20", "S4", 11.99)
line(A, "PEND", "2026-09-18", "S5", 31.71)
line(A, "RNM", "2026-09-23", "S6", 31.85)
line(A, "CLOSED", "2026-08-20", "S7", 9.99)
line(A, "REPL", "2026-08-20", "S8", 9.99)
line(A, "NORET", "2026-09-02", "S10", 20.00)
refund(A, "NORET", "2026-09-15", 5.00)            # a goodwill partial refund
line(A, "OLDRET", "2026-05-02", "S11", 7.00)      # its return is from May
refund(A, "OLDRET", "2026-09-05", 7.00)
line(A, "OLDNODATE", "2026-08-25", "S12", 15.00)
line(A, "NEWNODATE", "2026-09-22", "S13", 16.00)
conn.commit()
_rs.store(None, A, MKT, [
    ret("DISC", "2026-08-26", "Approved", "S1", refunded=34.99, amount=34.99),
    ret("PART", "2026-09-05", "Approved", "S2", refunded=8.69),
    ret("VAT", "2026-09-04", "Approved", "S9", refunded=12.00),
    ret("UNREF", "2026-09-03", "Approved", "S3", delivered="2026-09-10",
        tracking_id="TRK123", carrier="Royal Mail"),
    ret("RECENT", "2026-09-24", "Approved", "S4", delivered="2026-09-29"),
    ret("PEND", "2026-09-22", "PendingApproval", "S5"),
    ret("RNM", "2026-09-25", "PendingApproval", "S6", refunded=31.85),
    ret("CLOSED", "2026-08-22", "Closed", "S7"),
    ret("REPL", "2026-08-22", "Approved", "S8", resolution="Replacement"),
    ret("OLDRET", "2026-05-06", "Approved", "S11", refunded=7.00),
    ret("OLDNODATE", "2026-09-01", "Approved", "S12"),
    ret("NEWNODATE", "2026-09-25", "Approved", "S13", a_to_z="Y"),
])
# ---- account B: the SAME order id, different money and a different return ------
line(B, "DISC", "2026-08-31", "S1", 50.00)
refund(B, "DISC", "2026-09-01", 1.00)
line(B, "BONLY", "2026-09-02", "S1", 9.00)
refund(B, "BONLY", "2026-09-03", 9.00)
conn.commit()
_rs.store(None, B, MKT, [ret("DISC", "2026-08-27", "Closed", "S1")])

res = _rr.build(None, A, MKT, START, END, today=TODAY)
by = {r["order_id"]: r for r in res["rows"]}

print("=== each class ===")
check("discount case: refunded (full)", by["DISC"]["class"], "refunded_full")
check("  money back is what the buyer paid", by["DISC"]["money_back"], 33.24)
check("  NOT a mismatch (report shows the pre-discount price)", by["DISC"]["mismatch"], False)
check("  and says why the report differs", "before discount" in by["DISC"]["note"], True)
check("  days from return to refund", by["DISC"]["days"], 26)
check("partial refund", by["PART"]["class"], "refunded_partial")
check("  8.69 back", by["PART"]["money_back"], 8.69)
check("  says of what", "8.69 of 14.49" in by["PART"]["note"], True)
check("itemised VAT counts toward full", by["VAT"]["class"], "refunded_full")
check("approved, not refunded", by["UNREF"]["class"], "approved_unrefunded")
check("  overdue (delivered 10 Sep, >2 business days)", by["UNREF"]["overdue"], True)
check("  waiting since the return date", by["UNREF"]["days"], 27)
check("  tracking kept", (by["UNREF"]["carrier"], by["UNREF"]["tracking_id"]),
      ("Royal Mail", "TRK123"))
check("delivered yesterday: 1 business day, not overdue",
      (by["RECENT"]["class"], by["RECENT"]["overdue"]), ("approved_unrefunded", False))
check("no delivery date, 29 days since request: overdue (fallback)",
      by["OLDNODATE"]["overdue"], True)
check("no delivery date, 5 days: not overdue", by["NEWNODATE"]["overdue"], False)
check("  A-to-z claim noted", "A-to-z claim: Y" in by["NEWNODATE"]["note"], True)
check("pending", by["PEND"]["class"], "pending")
check("  pending is never flagged overdue", by["PEND"]["overdue"], False)
check("report says refunded, no money moved", by["RNM"]["class"], "report_no_money")
check("  is a mismatch", by["RNM"]["mismatch"], True)
check("closed without refund", by["CLOSED"]["class"], "closed_no_refund")
check("replacement: no refund due", by["REPL"]["class"], "no_refund_due")
check("refund with no return", by["NORET"]["class"], "refund_no_return")
check("  partial, 5.00", (by["NORET"]["full_or_partial"], by["NORET"]["money_back"]),
      ("partial", 5.0))
check("an order whose return is outside the window is NOT 'no return'",
      "OLDRET" in by, False)

print("=== totals ===")
t = res["totals"]
check("refunded total = every pound that went back", t["refunded"],
      round(33.24 + 8.69 + 12.00 + 5.00, 2))
check("awaiting = approved-unrefunded + pending + report-no-money", t["awaiting"], 6)
check("awaiting value (report figure, else price paid)", t["awaiting_value"],
      round(19.99 + 11.99 + 31.71 + 31.85 + 15.00 + 16.00, 2))
check("overdue count", t["overdue"], 2)
check("mismatches", t["mismatches"], 1)
check("the rule is stated", "not Amazon's verdict" in res["rule"], True)

print("=== account isolation ===")
check("A's DISC carries A's money, not B's", by["DISC"]["money_back"], 33.24)
check("B's refund-only order never appears in A", "BONLY" in by, False)
rb = {r["order_id"]: r for r in _rr.build(None, B, MKT, START, END, today=TODAY)["rows"]}
check("B's DISC is B's own (partial 1.00 of 50)",
      (rb["DISC"]["class"], rb["DISC"]["money_back"]), ("refunded_partial", 1.0))
check("B sees none of A's orders", sorted(rb), ["BONLY", "DISC"])

print("=== shared helpers ===")
check("is_full_refund: equal is full", _pl.is_full_refund(33.24, 33.24), True)
check("is_full_refund: short is partial", _pl.is_full_refund(8.69, 14.49), False)
check("classify: money beats the report", _rr.classify(5.0, 20.0, 20.0, "Pending", ""),
      "refunded_partial")
check("business days skip the weekend",
      _rr.business_days_after("2026-09-25", "2026-09-28"), 1)

print("=== CSV ===")
csv_text = _rr.to_csv(res)
check("header row", csv_text.splitlines()[0].split(",")[:3], ["order_id", "label", "sku"])
check("every row written", len(csv_text.strip().splitlines()), len(res["rows"]) + 1)

print("=== the report's tracking columns are parsed and kept ===")
HDR = ("Order ID\tOrder date\tReturn request date\tReturn request status\tAmazon RMA ID\t"
       "Merchant RMA ID\tLabel type\tLabel cost\tCurrency code\tReturn carrier\tTracking ID\t"
       "Label to be paid by\tA-to-Z Claim\tIs prime\tASIN\tMerchant SKU\tItem Name\t"
       "Return quantity\tReturn Reason\tIn policy\tReturn type\tResolution\tInvoice number\t"
       "Return delivery date\tOrder Amount\tOrder quantity\tSafeT Action reason\t"
       "SafeT claim id\tSafeT claim state\tSafeT claim creation time\t"
       "SafeT claim reimbursement amount\tRefunded Amount\tCategory\tVAT\tOrder Item ID")
ROW = ("TRK-1\t20-Sep-2026\t23-Sep-2026\tApproved\tRMA9\t\tAmazonUnPaidLabel\t3.10\tGBP\t"
       "Evri\tH01ABC\tCustomer\tN\tN\tB0TRK\tSKU-TRK\tThing\t1\tCR-DEFECTIVE\tY\tC-Returns\t"
       "StandardRefund\t\t26-Sep-2026\t69.98\t1\t\t\t\t\t\t\tHome\t\tX1")
h, rows, err = _rsync.split(HDR + "\n" + ROW)
parsed, kind, _sk = _rv.parse_rows(h, rows)
p = parsed[0]
check("kind is seller-fulfilled", kind, "mfn")
check("delivery date parsed to ISO", p["delivered"], "2026-09-26")
check("tracking, carrier, RMA", (p["tracking_id"], p["carrier"], p["rma_id"]),
      ("H01ABC", "Evri", "RMA9"))
check("order date and label cost", (p["order_date"], p["label_cost"]), ("2026-09-20", 3.1))


def fake_fetch(acc, mkt, days):
    return h, rows, ""


out = _rsync.pull_and_store(None, {}, A, MKT, fetcher=fake_fetch)
check("the daily pull stores through the one fetch path", (out["ok"], out["added"]), (True, 1))
kept = _rs.load(None, A, MKT, order_id="TRK-1")[0]
check("  and keeps the delivery date", kept["delivered"], "2026-09-26")
# A later copy of the same return WITHOUT those columns must not blank them.
blank = dict(p)
for k in ("delivered", "tracking_id", "carrier", "rma_id"):
    blank[k] = None
_rs.store(None, A, MKT, [blank])
kept = _rs.load(None, A, MKT, order_id="TRK-1")[0]
check("a later file without the columns does not blank them",
      (kept["delivered"], kept["tracking_id"]), ("2026-09-26", "H01ABC"))
check("an empty report stores nothing and is not an error",
      _rsync.pull_and_store(None, {}, A, MKT, fetcher=lambda a, m, d: ([], [], _rsync.EMPTY))["ok"],
      True)
check("a failed fetch is reported, never raised",
      _rsync.pull_and_store(None, {}, A, MKT, fetcher=lambda a, m, d: ([], [], "boom")),
      {"ok": False, "error": "boom"})

print("=== a refund is judged against the RETURNED items (change review) ===")
line(A, "TWO", "2026-09-01", "S20", 20.00)
line(A, "TWO", "2026-09-01", "S21", 15.00)
refund(A, "TWO", "2026-09-12", 15.00)
line(A, "UNITS", "2026-09-01", "S22", 30.00, units=2)
refund(A, "UNITS", "2026-09-12", 15.00)
line(A, "NR2", "2026-09-01", "S23", 12.00, units=2)
refund(A, "NR2", "2026-09-13", 6.00)                 # 1 unit of 2, no return
conn.commit()
_rs.store(None, A, MKT, [ret("TWO", "2026-09-08", "Approved", "S21", refunded=15.00),
                         ret("UNITS", "2026-09-08", "Approved", "S22", refunded=15.00)])
by2 = {r["order_id"]: r for r in _rr.build(None, A, MKT, START, END, today=TODAY)["rows"]}
check("two-SKU order, the 15.00 item returned and refunded 15.00: Refunded",
      (by2["TWO"]["class"], by2["TWO"]["price_paid"], by2["TWO"]["mismatch"]),
      ("refunded_full", 15.0, False))
check("  and says which part of the order it was", "15.00 of order 35.00" in by2["TWO"]["note"], True)
check("two units on one line, one returned and refunded: Refunded",
      (by2["UNITS"]["class"], by2["UNITS"]["price_paid"]), ("refunded_full", 15.0))
ev = {e["order_id"]: e for e in _pl.refund_events(None, A, MKT, START, END)}
check("refund_events: 1 unit of 2 refunded in full is full (refund_units)",
      (ev["NR2"]["full_or_partial"], ev["NR2"]["returned_price"]), ("full", 6.0))
check("refund_events: one item of two refunded in full is full",
      ev["TWO"]["full_or_partial"], "full")
check("refund with no return, 1 unit of 2: judged on that unit",
      (by2["NR2"]["full_or_partial"], by2["NR2"]["price_paid"]), ("full", 6.0))
check("returned_price: no matching SKU falls back to the whole order",
      _pl.returned_price([{"sku": "X", "units": 1, "gross": 10}], returned={"Y": 1}), 10.0)

print("=== the daily job ===")
from domain import accounts as _accm  # noqa: E402
_saved = (_accm.load_accounts, _accm.has_own_creds, _accm.seller_scope_allowed)
_accm.load_accounts = lambda conf, cp=None, persist=True: [
    {"id": "acc1", "marketplaces": ["UK"]}, {"id": "acc2", "marketplaces": [],
                                              "default_marketplace": "de"},
    {"id": "acc3", "marketplaces": []}, {"id": "borrow", "marketplaces": ["UK"]}]
_accm.has_own_creds = lambda a: a["id"] != "borrow"
_accm.seller_scope_allowed = lambda a: True
try:
    try:
        _rsync.sync_all(None, {}, fetcher=lambda a, m, d: ([], [], "Amazon said no"))
        check("every pull failing makes the job fail", "no raise", "raised")
    except RuntimeError as e:
        check("every pull failing makes the job fail", "Amazon said no" in str(e), True)
    seen = []
    res = _rsync.sync_all(None, {}, fetcher=lambda a, m, d: (seen.append((a["id"], m)) or ([], [], _rsync.EMPTY)))
    check("an empty marketplace list uses the default marketplace", ("acc2", "DE") in seen, True)
    check("skips are listed with the reason", sorted((s["workspace"], s["why"]) for s in res["skipped"]),
          [("acc3", "no marketplace set"), ("borrow", "no Amazon login of its own")])
finally:
    _accm.load_accounts, _accm.has_own_creds, _accm.seller_scope_allowed = _saved

try:
    import sp_api.api  # noqa: F401
    from api import returns_report as _api
    def _nomid():
        raise ValueError("no such marketplace")
    _t, _n2, _err = _api.fetch({"refresh_token": "x", "lwa_app_id": "x",
                                "lwa_client_secret": "x"}, "UK", _nomid, 1)
    check("a bad marketplace keeps the button's wording",
          _err.startswith("Amazon refused the report request"), True)
except ImportError:
    print("  (sp_api not installed: wording check not run)")

print("=== wiring ===")
check("the button uses the one fetch-parse-store path",
      "_rsync.pull_and_store(CONFIG_PATH, acc, wsid, mkt, days, fetcher=_fetch)" in
      open(os.path.join(HERE, "routes", "returns_routes.py"), encoding="utf-8").read(), True)
src = open(os.path.join(HERE, "routes", "returns_routes.py"), encoding="utf-8").read()
check("route /returns/refunds exists", '"/returns/refunds"' in src, True)
check("route /returns/refunds.csv exists", '"/returns/refunds.csv"' in src, True)
check("the button's fetch is the shared one", "_rsync.fetch(acc, mkt, days)" in src, True)
rr_src = open(os.path.join(HERE, "domain", "return_refunds.py"), encoding="utf-8").read()
check("return_refunds never reads order_fees itself (Rule 12)", "order_fees" in
      rr_src.split('"""', 2)[2].replace("never reads order_fees", ""), False)
from data import scheduler as _sch  # noqa: E402
check("a daily returns job is registered", (_sch._JOBS.get("returns_sync") or {}).get("hours"), 24)

wipe()
print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
