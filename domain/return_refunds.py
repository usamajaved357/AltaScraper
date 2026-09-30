"""domain/return_refunds.py -- was each return actually refunded?

Asked for (owner, 30 Sep 2026): "you said there are some 6 returns which have
not been paid the refund? please show me all that information in the app -- if
we have already paid the refunds and what is the status of the returns or if the
returns closed without resolution or refund and other things which you think
matter in our case".

WHAT THIS JOINS, and nothing else:
  * the returns this app has KEPT (domain/returns_store -- Amazon's seller-
    fulfilled returns report: status, resolution, the report's own "Refunded
    Amount", tracking, the day the parcel reached the seller);
  * the MONEY that actually went back, from THE refund-events reader
    domain/pnl_ledger.refund_events (Rule 12: this never reads order_fees);
  * what the buyer paid for the order, from order_finance.placed_orders (the
    same read the account statement uses; already net of any promotion).

WHY THE REPORT'S "REFUNDED AMOUNT" IS NOT BELIEVED ON ITS OWN. Measured on
nestwell_goods UK the same day: one return showed "refunded 31.85" with no money
having moved in any Amazon money source, and two showed the list price (34.99,
29.99) where the buyer had paid, and was refunded, the discounted price (33.24,
28.49). The money is the fact; the report is Amazon's paperwork about it.

THE OVERDUE FLAG IS OURS, NOT AMAZON'S VERDICT. Amazon asks a seller-fulfilled
seller to refund within two business days of the return reaching them. So a
return that is approved and unrefunded is flagged when more than
OVERDUE_BUSINESS_DAYS weekdays have passed since its delivery date -- or, when the
report gives no delivery date, more than FALLBACK_DAYS calendar days since the
return was requested. Bank holidays are not known here, so it can flag a day
early around one.

Reads only. Nothing here refunds, approves or contacts anyone.
"""
import csv
import datetime as _dt
import io

from data import db as _db

OVERDUE_BUSINESS_DAYS = 2
FALLBACK_DAYS = 14
# How far before a return's own date a refund may have been posted and still
# belong to it (a seller who refunds from a buyer's message before the return
# is logged), and how far back an order may have been placed.
MONEY_LEAD_DAYS = 60
ORDER_LOOKBACK_DAYS = 180

RULE = ("Flagged when approved and not refunded more than %d business days after "
        "the parcel reached you (Amazon's seller-fulfilled refund window), or %d "
        "days after the return request when the report has no delivery date. "
        "A flag from this app, not Amazon's verdict." % (OVERDUE_BUSINESS_DAYS,
                                                         FALLBACK_DAYS))

# class key -> short label. The screen shows the label; the key never changes.
CLASSES = (
    ("refunded_full", "Refunded"),
    ("refunded_partial", "Partly refunded"),
    ("approved_unrefunded", "Approved, not refunded"),
    ("pending", "Pending"),
    ("report_no_money", "Report says refunded, no money"),
    ("closed_no_refund", "Closed, no refund"),
    ("no_refund_due", "Replacement, no refund due"),
    ("refund_no_return", "Refund, no return"),
)
LABEL = dict(CLASSES)
# The classes that are still waiting for money.
AWAITING = ("approved_unrefunded", "pending", "report_no_money")


def _n(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _day(s):
    try:
        return _dt.date.fromisoformat(str(s or "")[:10])
    except ValueError:
        return None


def business_days_after(start, today):
    """Weekdays in (start, today]. 0 when either is unknown or today<=start."""
    a, b = _day(start), _day(today)
    if not a or not b or b <= a:
        return 0
    n, d = 0, a
    while d < b:
        d += _dt.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def _state(status, resolution):
    """Amazon's words -> "closed" | "pending" | "replacement" | "approved"."""
    s = str(status or "").lower()
    r = str(resolution or "").lower()
    if "replac" in r or "exchange" in r:
        return "replacement"
    if any(w in s for w in ("closed", "reject", "cancel", "denied")):
        return "closed"
    if "pending" in s or "request" in s:
        return "pending"
    return "approved"


def classify(back, price, report_refunded, status, resolution):
    """One order's class. `back` is the money that went back (incl. itemised
    VAT), `price` what the buyer paid, `report_refunded` the returns report's
    figure (None when it gave none)."""
    from domain import pnl_ledger as _pl
    if back > 0.005:
        if price and not _pl.is_full_refund(back, price):
            return "refunded_partial"
        return "refunded_full"
    if report_refunded and report_refunded > 0.005:
        return "report_no_money"
    st = _state(status, resolution)
    if st == "replacement":
        return "no_refund_due"
    if st == "closed":
        return "closed_no_refund"
    if st == "pending":
        return "pending"
    return "approved_unrefunded"


def _prices(config_path, workspace_id, marketplace, start, end):
    """{order_id: {"price", "date", "lines"}} from the statement's own order
    read. `price` is the whole order; a refund is judged against the RETURNED
    lines (pnl_ledger.returned_price), never simply against this."""
    from domain import order_finance as _of
    conn = _db.get_db(config_path)
    out = {}
    for oid, o in _of.placed_orders(conn, workspace_id, marketplace,
                                    start, end).items():
        out[oid] = {"price": round(sum(_n(L["gross"]) for L in o["lines"]), 2),
                    "date": o["d"],
                    "lines": [{"sku": L["sku"], "units": L["units"],
                               "gross": L["gross"]} for L in o["lines"]]}
    return out


def _join(vals):
    return ", ".join(sorted({str(v) for v in vals if v}))


def build(config_path, workspace_id, marketplace, start, end, today=None):
    """Every return in [start, end] (by return date), and every refund posted in
    [start, end] with no return behind it, each with its refund status.
    -> {ok, rows, totals, rule, classes, start, end}."""
    from domain import returns_store as _rs
    from domain import pnl_ledger as _pl
    today = str(today or _dt.date.today().isoformat())[:10]
    s, e = _day(start), _day(end)
    money_from = (s - _dt.timedelta(days=MONEY_LEAD_DAYS)).isoformat()
    orders_from = (s - _dt.timedelta(days=ORDER_LOOKBACK_DAYS)).isoformat()

    returns = _rs.load(config_path, workspace_id, marketplace, start, end)
    # EVERY return ever kept for this account, to tell a refund with no return
    # from one whose return falls outside the window.
    ever = {str(r.get("order_id") or "")
            for r in _rs.load(config_path, workspace_id, marketplace)}
    events = _pl.refund_events(config_path, workspace_id, marketplace,
                               money_from, max(today, str(end)))
    prices = _prices(config_path, workspace_id, marketplace, orders_from,
                     max(today, str(end)))

    money = {}
    for ev in events:
        m = money.setdefault(ev["order_id"], {"events": [], "price": None,
                                              "basis": None})
        m["events"].append({"date": ev["date"], "units": int(ev.get("refund_units") or 0),
                            "amount": round(_n(ev["amount"]) + _n(ev["refund_tax"]), 2)})
        if ev.get("order_price"):
            m["price"] = ev["order_price"]
        if ev.get("returned_price"):
            m["basis"] = ev["returned_price"]
        m["sku"] = ev.get("sku") or m.get("sku") or ""

    groups = {}
    for r in returns:
        key = str(r.get("order_id") or "") or ("__noorder__" + str(r.get("identity")))
        groups.setdefault(key, []).append(r)

    rows = []
    for key, rs in groups.items():
        oid = str(rs[0].get("order_id") or "")
        rs.sort(key=lambda x: str(x.get("date") or ""))
        first = rs[0]
        m = money.get(oid) or {"events": [], "price": None, "basis": None}
        back = round(sum(x["amount"] for x in m["events"]), 2)
        p = prices.get(oid) or {}
        whole = p.get("price") or m.get("price")
        # THE RETURNED ITEMS' price, quantity-aware (change review 30 Sep 2026):
        # one item of two, or one unit of two, refunded in full is "Refunded".
        returned = {}
        for x in rs:
            k = str(x.get("sku") or "").upper()
            if k:
                returned[k] = returned.get(k, 0) + int(x.get("qty") or 1)
        price = (_pl.returned_price(p.get("lines"), returned=returned) if p.get("lines")
                 else (m.get("basis") or whole))
        rep = [x.get("refunded") for x in rs if x.get("refunded") is not None]
        report_refunded = round(sum(_n(x) for x in rep), 2) if rep else None
        report_amount = (round(sum(_n(x.get("order_amount")) for x in rs), 2)
                         if any(x.get("order_amount") is not None for x in rs)
                         else None)
        status = " / ".join(sorted({str(x.get("status") or "") for x in rs} - {""}))
        resolution = " / ".join(sorted({str(x.get("resolution") or "")
                                        for x in rs} - {""}))
        cls = classify(back, price, report_refunded, status, resolution)
        delivered = max((str(x.get("delivered") or "") for x in rs), default="") or None
        row = _row(oid, cls, first, rs, m, back, price, report_refunded,
                   report_amount, status, resolution, delivered, today)
        row["order_price"] = whole
        if price and whole and price < whole - 0.005:
            row["note"] = (row["note"] + " Returned part %.2f of order %.2f."
                           % (price, whole)).strip()
        rows.append(row)

    for oid, m in money.items():
        if oid in ever:
            continue
        inwin = [x for x in m["events"] if str(start) <= x["date"] <= str(end)]
        if not inwin:
            continue
        p = prices.get(oid) or {}
        back = round(sum(x["amount"] for x in inwin), 2)
        # No return names the items, so the refunded UNIT count decides which
        # part of the order this was (pnl_ledger.returned_price).
        price = (_pl.returned_price(p.get("lines"),
                                    refund_units=sum(x["units"] for x in inwin), back=back)
                 if p.get("lines") else (m.get("basis") or m.get("price")))
        fp = ("full" if price and _pl.is_full_refund(back, price) else
              "partial" if price else "unknown")
        rows.append({
            "order_id": oid, "class": "refund_no_return",
            "label": LABEL["refund_no_return"],
            "sku": m.get("sku") or "", "asin": "", "name": "",
            "return_date": None, "order_date": p.get("date"), "delivered": None,
            "status": "", "resolution": "", "reason": "",
            "report_refunded": None, "report_amount": None,
            "price_paid": price, "order_price": p.get("price") or m.get("price"),
            "money": inwin, "money_back": back,
            "money_date": inwin[-1]["date"], "full_or_partial": fp,
            "days": None, "overdue": False, "mismatch": False,
            "tracking_id": None, "carrier": None, "rma_id": None,
            "a_to_z": None, "in_policy": None, "safet_state": None,
            # e.g. a goodwill partial refund, issued without a return.
            "note": "No return on record." + ("" if price else " Order not held here."),
        })

    rows.sort(key=lambda r: (str(r.get("return_date") or r.get("money_date") or "")),
              reverse=True)
    return {"ok": True, "workspace": workspace_id, "marketplace": marketplace,
            "start": str(start), "end": str(end), "today": today,
            "rows": rows, "totals": totals(rows), "rule": RULE,
            "awaiting_classes": list(AWAITING),
            "classes": [{"key": k, "label": l} for k, l in CLASSES]}


def _row(oid, cls, first, rs, m, back, price, report_refunded, report_amount,
         status, resolution, delivered, today):
    ret_date = str(first.get("date") or "") or None
    notes, overdue = [], False
    days = None
    if cls in ("refunded_full", "refunded_partial") and m["events"]:
        paid_on = m["events"][-1]["date"]
        a, b = _day(ret_date), _day(paid_on)
        days = (b - a).days if (a and b) else None
    elif ret_date:
        a, b = _day(ret_date), _day(today)
        days = (b - a).days if (a and b) else None

    if cls in ("approved_unrefunded", "report_no_money"):
        if delivered:
            bd = business_days_after(delivered, today)
            overdue = bd > OVERDUE_BUSINESS_DAYS
            notes.append("Reached you %s (%d business day%s)."
                         % (delivered, bd, "" if bd == 1 else "s"))
        else:
            overdue = (days or 0) > FALLBACK_DAYS
            notes.append("No delivery date.")

    mismatch = False
    if cls == "report_no_money":
        mismatch = True
        notes.append("Report: %.2f refunded. No money posted." % report_refunded)
    elif back > 0.005 and report_refunded is not None \
            and abs(report_refunded - back) > 0.01:
        if cls == "refunded_full" and report_refunded > back:
            notes.append("Report shows %.2f (before discount); buyer paid %.2f, "
                         "all back." % (report_refunded, back))
        else:
            mismatch = True
            notes.append("Report %.2f, money %.2f." % (report_refunded, back))
    if cls == "refunded_partial" and price:
        notes.append("%.2f of %.2f back." % (back, price))
    if len(m["events"]) > 1:
        notes.append("%d refund postings." % len(m["events"]))
    a2z = _join(x.get("a_to_z") for x in rs)
    if a2z and a2z.upper() not in ("N", "NO", "FALSE"):
        notes.append("A-to-z claim: %s." % a2z)
    pol = _join(x.get("in_policy") for x in rs)
    if pol and pol.upper() in ("N", "NO", "FALSE"):
        notes.append("Outside return policy.")
    sft = _join(x.get("safet_state") for x in rs)
    if sft:
        notes.append("SAFE-T claim: %s." % sft)
    if price is None:
        notes.append("Order not held here: full/partial unknown.")

    fp = None
    if back > 0.005:
        fp = ("unknown" if price is None else
              "full" if cls == "refunded_full" else "partial")
    return {
        "order_id": oid, "class": cls, "label": LABEL[cls],
        "sku": _join(x.get("sku") for x in rs),
        "asin": _join(x.get("asin") for x in rs),
        "name": str(first.get("name") or ""),
        "qty": sum(int(x.get("qty") or 1) for x in rs),
        "return_date": ret_date,
        "order_date": first.get("order_date"),
        "delivered": delivered,
        "status": status, "resolution": resolution,
        "reason": _join(x.get("reason") for x in rs),
        "report_refunded": report_refunded, "report_amount": report_amount,
        "price_paid": price, "money": m["events"], "money_back": back,
        "money_date": (m["events"][-1]["date"] if m["events"] else None),
        "full_or_partial": fp,
        "days": days, "overdue": overdue, "mismatch": mismatch,
        "tracking_id": _join(x.get("tracking_id") for x in rs) or None,
        "carrier": _join(x.get("carrier") for x in rs) or None,
        "rma_id": _join(x.get("rma_id") for x in rs) or None,
        "a_to_z": a2z or None, "in_policy": pol or None,
        "safet_state": sft or None,
        "note": " ".join(notes),
    }


def _expected(r):
    """What a waiting return should bring back: the report's figure, else the
    price paid, else the report's order amount."""
    for k in ("report_refunded", "price_paid", "report_amount"):
        if r.get(k):
            return _n(r[k])
    return 0.0


def totals(rows):
    """The stat cards: money back, returns still waiting, overdue, mismatches."""
    by = {k: 0 for k, _l in CLASSES}
    for r in rows:
        by[r["class"]] = by.get(r["class"], 0) + 1
    waiting = [r for r in rows if r["class"] in AWAITING]
    return {
        "refunded": round(sum(_n(r.get("money_back")) for r in rows), 2),
        "refunded_orders": sum(1 for r in rows if _n(r.get("money_back")) > 0.005),
        "awaiting": len(waiting),
        "awaiting_value": round(sum(_expected(r) for r in waiting), 2),
        "overdue": sum(1 for r in rows if r.get("overdue")),
        "mismatches": sum(1 for r in rows if r.get("mismatch")),
        "by_class": by,
        "returns": sum(1 for r in rows if r["class"] != "refund_no_return"),
    }


CSV_COLS = ("order_id", "label", "sku", "name", "return_date", "status",
            "resolution", "reason", "report_refunded", "price_paid",
            "money_back", "money_date", "full_or_partial", "days", "overdue",
            "mismatch", "delivered", "tracking_id", "carrier", "rma_id", "note")


def to_csv(result):
    """The table as CSV text, every row, amounts unrounded beyond the penny."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLS)
    for r in (result or {}).get("rows") or []:
        vals = []
        for c in CSV_COLS:
            v = r.get(c)
            if isinstance(v, bool):
                v = "yes" if v else ""
            s = "" if v is None else str(v)
            # Text a spreadsheet would run as a formula stays text.
            if isinstance(v, str) and s[:1] in ("=", "+", "-", "@"):
                s = "'" + s
            vals.append(s)
        w.writerow(vals)
    return buf.getvalue()
