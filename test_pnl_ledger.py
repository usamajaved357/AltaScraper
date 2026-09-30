"""domain/pnl_ledger.py -- every statement line's items add up to the line.

Owner, 30 Sep 2026: "i want every detailed breakdown of how these profit
numbers are calculated and also references so i can verify them". A breakdown
that does not add up to the figure it explains is worse than none, so for a
fixture account this checks EVERY itemised line of domain/pnl.build, over
several windows and VAT settings, to the penny -- with settled and estimated
orders, a partial and a full refund, a refund posting with no order held,
missing costs, an order-level cost over a product cost, per-product charges,
account-level charges, other Amazon postings, own costs, and ads from both the
Ads API (with VAT added) and ad invoices. And that one account's ledger never
carries another account's orders.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db                 # noqa: E402
from domain import pnl as _pnl             # noqa: E402
from domain import pnl_ledger as _pl       # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


A, B, MKT = "__ledger_a__", "__ledger_b__", "UK"
TABLES = ("order_lines", "order_fees", "finance_daily", "ads_daily",
          "asin_charges", "manual_expenses", "finance_undated")
conn = _db.get_db()


def wipe():
    for t in TABLES:
        for ws in (A, B):
            conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (ws,))
    conn.commit()


def line(ws, oid, day, sku, units, rev, ship=0.0, cogs=None, src="", status="Shipped",
         asin=""):
    conn.execute("INSERT INTO order_lines (workspace_id, marketplace, order_id, "
                 "purchase_date, sku, asin, title, units, revenue, shipping, cogs, "
                 "cogs_source, currency, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (ws, MKT, oid, day + "T10:00:00Z", sku, asin, "Title " + sku, units,
                  rev, ship, cogs, src, "GBP", status))


def fee(ws, oid, posted, **k):
    cols = ["referral_fees", "fba_fees", "other_fees", "promo_fees", "principal", "tax",
            "refunds", "refund_tax", "refund_units", "refund_fees_returned", "promos"]
    conn.execute("INSERT INTO order_fees (workspace_id, marketplace, order_id, posted_date, "
                 "%s, currency) VALUES (?,?,?,?,%s,'GBP')"
                 % (",".join(cols), ",".join("?" * len(cols))),
                 [ws, MKT, oid, posted] + [k.get(c, 0) for c in cols])


def fin(ws, day, **k):
    cols = sorted(k)
    conn.execute("INSERT INTO finance_daily (workspace_id, marketplace, date, asin, currency, %s) "
                 "VALUES (?,?,?,'*','GBP',%s)" % (",".join(cols), ",".join("?" * len(cols))),
                 [ws, MKT, day] + [k[c] for c in cols])


wipe()
# ---- account A ---------------------------------------------------------------
# Settled history in June/July, so a fee rate is MEASURED (not the default).
fin(A, "2026-06-15", principal=400.0, referral_fees=69.04, fba_fees=0.0)
# Settled single-line order with every kind of Amazon money.
line(A, "S-1", "2026-08-03", "SKU-A", 2, 40.0, 3.99, 10.0, "manual", asin="B0A")
fee(A, "S-1", "2026-08-12", principal=36.66, tax=7.33, referral_fees=6.61, fba_fees=2.10,
    other_fees=0.33, promo_fees=0.60, promos=2.50)
# Settled two-line order: one line with its own order cost, one on the product cost.
line(A, "M-1", "2026-08-05", "SKU-B", 1, 19.99, 0.0, 8.0, "manual-order", asin="B0B")
line(A, "M-1", "2026-08-05", "SKU-C", 3, 30.00, 2.0, 4.25, "manual", asin="B0C")
fee(A, "M-1", "2026-08-15", principal=51.99, tax=0.0, referral_fees=8.97)
# Not settled: one with no cost (missing), one costed.
line(A, "U-1", "2026-08-20", "SKU-D", 2, 25.0, 0.0, None, "", asin="B0D")
line(A, "U-2", "2026-08-28", "SKU-A", 1, 21.0, 0.0, 10.0, "manual", asin="B0A")
line(A, "U-3", "2026-08-29", "SKU-D", 1, 12.5, 0.0, None, "", asin="B0D")
# Cancelled: never a sale.
line(A, "C-1", "2026-08-21", "SKU-A", 1, 99.0, 0.0, 10.0, "manual", status="Canceled")
# A July order refunded in full in August, and S-1 refunded in part.
line(A, "P-0", "2026-07-20", "SKU-C", 1, 15.0, 0.0, 4.25, "manual", asin="B0C")
fee(A, "P-0", "2026-08-18", refunds=15.0, refund_units=1, refund_fees_returned=1.80)
fee(A, "S-1", "2026-08-25", refunds=10.0, refund_units=1, refund_fees_returned=0.50)
# An order posting Amazon's day totals do not carry (no finance_daily row).
fee(A, "M-1", "2026-08-27", refunds=5.0, refund_units=1)
# Amazon's day totals: the refund day carries 4.00 more than any order we hold.
fin(A, "2026-08-18", refunds=19.0, refund_units=2, refund_fees_returned=1.80,
    reimbursements=4.20)
fin(A, "2026-08-25", refunds=10.0, refund_units=1, refund_fees_returned=0.50)
# Account-level: the subscription (other_fees on no order), storage (fba), a
# posting with no order (adjustments), plus the order-level fees of S-1/M-1.
fin(A, "2026-08-12", other_fees=0.33 + 25.0, fba_fees=2.10 + 1.15, promo_fees=0.60,
    adjustments=-3.49)
fin(A, "2026-08-15", other_fees=0.0, adjustments=1.25)
conn.execute("INSERT INTO finance_undated (workspace_id, marketplace, field, amount, placed_on) "
             "VALUES (?,?,?,?,?)", (A, MKT, "other_fees", 25.0, "2026-08-12"))
# Ads: invoices before the Ads API connected on 20 Aug, then the API.
fin(A, "2026-08-08", ads_charged=30.0, ads_charged_tax=6.0)
for d, s in (("2026-08-20", 4.13), ("2026-08-21", 5.07), ("2026-08-30", 2.2)):
    conn.execute("INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend) "
                 "VALUES (?,?,?,'*',?)", (A, MKT, d, s))
# Your per-product charge and your own cost.
conn.execute("INSERT INTO asin_charges (workspace_id, marketplace, asin, sku, label, amount, "
             "effective_from) VALUES (?,?,?,?,?,?,?)", (A, MKT, "B0A", "", "postage", 1.335, ""))
conn.commit()
from domain import expenses as _exp  # noqa: E402
_exp.add(None, A, "Accountant", 90.0, "2026-08-01")
# Part of Amazon's account charge ALSO recorded as your own cost: not twice.
_exp.add(None, A, "Amazon selling subscription", 10.0, "2026-08-01", category="Amazon")
# A fee posted to an order on a day Amazon's account total does not carry: the
# account charge would go below zero, and "never below zero" applies.
fee(A, "P-0", "2026-08-29", fba_fees=1.0)
conn.commit()

# ---- account B: same order ids and SKUs, different money ------------------
line(B, "S-1", "2026-08-03", "SKU-A", 5, 500.0, 0.0, None, "")
line(B, "B-ONLY", "2026-08-09", "SKU-A", 1, 77.0, 0.0, None, "")
fee(B, "S-1", "2026-08-12", principal=500.0, referral_fees=75.0)
fin(B, "2026-08-18", refunds=333.0)
conn.commit()

WINDOWS = (("2026-08-01", "2026-08-31"), ("2026-08-01", "2026-08-15"),
           ("2026-08-16", "2026-08-31"), ("2026-08-12", "2026-08-12"),
           ("2026-07-01", "2026-09-30"), ("2026-08-29", "2026-08-29"))
try:
    for vat in (None, 0, 0.2):
        for s, e in WINDOWS:
            st = _pnl.build(None, A, MKT, s, e, vat)
            print("\n== %s..%s, VAT %r: profit %s ==" % (s, e, vat, st["profit"]))
            for key in _pl.LEDGER_LINES:
                want = st.get(key)
                led = _pl.ledger(None, A, MKT, s, e, key, vat_rate=vat)
                if want is None:
                    check("%s is 'not known' on the statement; ledger still answers" % key,
                          led["ok"], True)
                    continue
                check("%-22s items %s = line" % (key, led["total"]),
                      round(led["total"], 2), round(float(want), 2))
            led = _pl.ledger(None, A, MKT, s, e, "cogs", vat_rate=vat)
            check("missing-cost units = the statement's uncosted units",
                  led["missing_units"], st["uncosted_units"])

    print("\n== what the items say ==")
    S, E = "2026-08-01", "2026-08-31"
    c = _pl.ledger(None, A, MKT, S, E, "cogs")
    miss = {m["sku"]: m for m in c["missing"]}
    check("SKU-D is the SKU with no cost", sorted(miss), ["SKU-D"])
    check("  its orders are listed", sorted(o["order_id"] for o in miss["SKU-D"]["orders"]),
          ["U-1", "U-3"])
    check("  with units and sale value", (miss["SKU-D"]["units"], miss["SKU-D"]["value"]),
          (3, 37.5))
    check("  and the product title", miss["SKU-D"]["title"], "Title SKU-D")
    srcs = {(i["order_id"], i["sku"]): i["source"] for i in c["items"]}
    check("the order's own cost is named as such", srcs[("M-1", "SKU-B")],
          "your cost (this order)")
    check("the product cost is named as such", srcs[("M-1", "SKU-C")], "your cost (product)")
    check("cancelled orders carry no cost", any(i["order_id"] == "C-1" for i in c["items"]),
          False)
    r = _pl.ledger(None, A, MKT, S, E, "refunds")
    by = {(i["date"], i["order_id"]): i for i in r["items"]}
    check("a refund sits on the day the money went back", by[("2026-08-18", "P-0")]["amount"], 15.0)
    check("  a full refund is called full", by[("2026-08-18", "P-0")]["ref"], "full refund of 15.00")
    check("  a partial one says of what", by[("2026-08-25", "S-1")]["ref"],
          "partial: 10.00 of 43.99")
    check("  Amazon's day total with no order held is its own item",
          by[("2026-08-18", "")]["amount"], 4.0)
    check("  an order posting missing from the day total is shown, and set against",
          (by[("2026-08-27", "M-1")]["amount"], by[("2026-08-27", "")]["amount"]), (5.0, -5.0))
    ev = {(e["order_id"], e["date"]): e for e in _pl.refund_events(None, A, MKT, S, E)}
    check("refund_events: one per order per posting day", sorted(ev),
          [("M-1", "2026-08-27"), ("P-0", "2026-08-18"), ("S-1", "2026-08-25")])
    check("  full / partial against what the buyer paid",
          (ev[("P-0", "2026-08-18")]["full_or_partial"], ev[("S-1", "2026-08-25")]["full_or_partial"],
           ev[("S-1", "2026-08-25")]["order_price"]), ("full", "partial", 43.99))
    check("  another account's refunds are not in it",
          _pl.refund_events(None, B, MKT, S, E), [])
    est = _pl.ledger(None, A, MKT, S, E, "fees_estimated")
    check("estimated fees list only the unsettled orders",
          sorted(i["order_id"] for i in est["items"]), ["U-1", "U-2", "U-3"])
    check("  and say the rate", est["items"][0]["source"].startswith("estimated at "), True)
    ads = _pl.ledger(None, A, MKT, S, E, "ad_spend", vat_rate=0)
    inv = [i for i in ads["items"] if i["source"] == "ad invoice"]
    api = [i for i in ads["items"] if i["source"] == "Ads API"]
    check("ads: the invoice day, VAT included for an unregistered account",
          (len(inv), inv[0]["amount"]), (1, 36.0))
    check("ads: API days with VAT shown apart", (len(api), api[0]["vat"] > 0), (3, True))
    ac = _pl.ledger(None, A, MKT, S, E, "account_charges")
    check("account charges name the undated subscription",
          any("monthly subscription" in i["ref"] for i in ac["items"]), True)
    check("  the part already in your own costs is its own item",
          [i["amount"] for i in ac["items"] if i["source"] == "already in your own costs"], [-10.0])
    ac1 = _pl.ledger(None, A, MKT, "2026-08-29", "2026-08-29", "account_charges")
    check("  'never below zero' is shown as the rule it is",
          sorted((i["source"], i["amount"]) for i in ac1["items"]),
          [("account charge (posted 2026-08-29)", -1.0), ("rule: never below zero", 1.0)])

    print("\n== one account never shows another's orders ==")
    for key in _pl.LEDGER_LINES:
        led = _pl.ledger(None, A, MKT, S, E, key, vat_rate=0)
        check("A's %s has no B-only order" % key,
              any(i["order_id"] == "B-ONLY" for i in led["items"]), False)
    ra = _pl.ledger(None, A, MKT, S, E, "ordered_sales")
    check("A's S-1 is A's money, not B's",
          [i["amount"] for i in ra["items"] if i["order_id"] == "S-1"], [43.99])
    rb = _pl.ledger(None, B, MKT, S, E, "refunds")
    check("B's refunds are B's", rb["total"], 333.0)
    check("an unknown line is refused", _pl.ledger(None, A, MKT, S, E, "nope")["ok"], False)
finally:
    wipe()

print("\n%d failed" % len(fails))
sys.exit(1 if fails else 0)
