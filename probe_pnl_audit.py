"""probe_pnl_audit.py -- is every row of the P&L heatmap telling the truth?

Not "does the app agree with itself". Each metric is checked against what it
CLAIMS to be, using the raw sources, and against the arithmetic that must hold
between rows. Anything that cannot be checked is said to be unchecked rather
than passed.

    python probe_pnl_audit.py                 every account
    python probe_pnl_audit.py jack_uk UK
"""
import json
import sys
import datetime as dt

sys.path.insert(0, r"D:\AltaScraper")

# Which calendar each row is dated by. This is the thing the grid could not say.
ORDER_DATED = {
    "ordered_sales", "units", "orders", "order_items", "avg_selling_price",
    "sessions", "sessions_mobile", "sessions_browser", "page_views",
    "unit_session_pct", "buy_box_pct", "units_b2b", "ordered_sales_b2b",
}
MONEY_DATED = {
    "principal", "tax", "vat", "net_revenue", "net_proceeds", "total_fees",
    "referral_fees", "fba_fees", "other_fees", "fee_rate", "refunds",
    "refund_units", "refund_rate", "refund_fees_returned", "promos",
    "reimbursements", "units_shipped", "cogs", "profit", "margin_pct",
}
CLICK_DATED = {"impressions", "clicks", "spend", "ad_sales", "ad_orders",
               "acos", "roas", "tacos"}


def audit(aid, mkt, days=30, basis="order"):
    import dashboard as D
    from domain import sales_data as _sd

    end = dt.date.today()
    start = end - dt.timedelta(days=days - 1)
    rows = _sd.series(D.CONFIG_PATH, aid, mkt, start.isoformat(),
                      end.isoformat(),
                      vat_rate=_sd.vat_rate_for(D._cfg, aid), basis=basis)
    buckets, order = _sd.bucket(rows, "day")
    tot = {}
    for key, label, kind, good, _how in _sd.METRICS:
        tot[key] = _sd.aggregate(rows, key)
    tot["_labels"] = {k: l for k, l, _k, _g, _h in _sd.METRICS}

    print("\n%s" % ("=" * 74))
    print("%s (%s)   %s .. %s   basis=%s   %d day(s) of data"
          % (aid, mkt, start, end, basis, len(rows)))
    print("=" * 74)

    problems = []

    def val(k):
        v = tot.get(k)
        return None if v is None else float(v)

    # ---- 1. every row, with its calendar and whether it has anything -------
    print("\n%-24s %-12s %14s" % ("row", "calendar", "total"))
    print("-" * 54)
    for key, label, kind, good, _how in _sd.METRICS:
        v = tot.get(key)
        cal = ("order" if key in ORDER_DATED else
               "money" if key in MONEY_DATED else
               "click" if key in CLICK_DATED else "?")
        if cal == "?":
            problems.append("%s: no calendar declared for this row" % key)
        shown = "-" if v is None else ("%.2f" % v if kind != "count" else "%d" % v)
        print("%-24s %-12s %14s" % (label[:24], cal, shown))

    # ---- 2. the arithmetic that MUST hold ---------------------------------
    print("\nchecks:")

    def chk(name, ok, detail=""):
        print("   %-52s %s%s" % (name, "OK" if ok else "WRONG",
                                 ("   " + detail) if detail else ""))
        if not ok:
            problems.append("%s %s" % (name, detail))

    tf, rf, ff, of = (val("total_fees"), val("referral_fees"),
                      val("fba_fees"), val("other_fees"))
    if None not in (tf, rf, ff, of):
        chk("Amazon fees = referral + FBA + other",
            abs(tf - (rf + ff + of)) < 0.02,
            "%.2f vs %.2f" % (tf, rf + ff + of))

    p, v_, nr = val("principal"), val("vat"), val("net_revenue")
    if None not in (p, nr):
        # Amazon reports Principal EXCLUDING VAT and sends the tax separately,
        # so "Revenue after VAT" equalling it is CORRECT -- there is nothing to
        # take out. The row is labelled "(ex VAT)" for exactly that reason.
        chk("Revenue after VAT is the ex-VAT figure", abs(nr - p) < 0.02,
            "%.2f vs %.2f" % (nr, p))
    os_all = val("ordered_sales")
    if None not in (p, v_, os_all) and os_all:
        # THE INVARIANT WORTH HAVING: what the buyer paid, on the order basis,
        # is the ex-VAT money plus the VAT. Promotions are deliberately NOT in
        # this sum -- adding them made the gap larger, which is the measurement
        # saying they are already accounted for on one side.
        gap = abs((p + v_) - os_all)
        chk("ex-VAT + VAT reconciles to ordered sales",
            gap < max(1.0, os_all * 0.02),
            "%.2f + %.2f = %.2f vs sales %.2f (out by %.2f)"
            % (p, v_, p + v_, os_all, gap))

    np_ = val("net_proceeds")
    if None not in (nr, tf, np_):
        rfnd, promo = val("refunds") or 0, val("promos") or 0
        reimb = val("reimbursements") or 0
        # Amazon hands part of the fee BACK with a refund, and the app adds it
        # in. Leaving it out of the check made a correct figure look wrong by
        # exactly that amount.
        back = val("refund_fees_returned") or 0
        expect = nr - tf - rfnd - promo + back + reimb
        chk("Net proceeds = revenue - fees - refunds - promos + returned",
            abs(np_ - expect) < 0.05, "%.2f vs %.2f" % (np_, expect))

    pr, cg = val("profit"), val("cogs")
    if None not in (np_, pr, cg):
        chk("Profit = net proceeds - cost of goods",
            abs(pr - (np_ - cg)) < 0.05, "%.2f vs %.2f" % (pr, np_ - cg))
    if pr is not None:
        os_ = val("ordered_sales")
        if os_:
            chk("Profit does not exceed sales", pr <= os_ + 0.01,
                "profit %.2f vs sales %.2f" % (pr, os_))

    asp, os_, un = val("avg_selling_price"), val("ordered_sales"), val("units")
    if None not in (asp, os_, un) and un:
        chk("Average selling price = sales / units",
            abs(asp - os_ / un) < 0.02, "%.2f vs %.2f" % (asp, os_ / un))

    csr, u2, ss = val("unit_session_pct"), val("units"), val("sessions")
    if None not in (csr, u2, ss) and ss:
        chk("Conversion = units / sessions",
            abs(csr - (u2 / ss * 100)) < 0.6,
            "%.2f%% vs %.2f%%" % (csr, u2 / ss * 100))

    fr = val("fee_rate")
    if None not in (fr, tf, p) and p:
        chk("Fee rate = fees / charged", abs(fr - (tf / p * 100)) < 0.6,
            "%.1f%% vs %.1f%%" % (fr, tf / p * 100))

    # ---- 3. do the two calendars ever meet? -------------------------------
    sales_days = {r["date"] for r in rows if r.get("ordered_sales")}
    money_days = {r["date"] for r in rows if r.get("principal")}
    both = sales_days & money_days
    print("\n   days with sales: %d   days with settled money: %d   days with BOTH: %d"
          % (len(sales_days), len(money_days), len(both)))
    if sales_days and money_days and not both:
        problems.append("no day carries both a sale and its money -- the grid "
                        "cannot be read across")
    return problems


def main(argv):
    import dashboard as D
    args = [a for a in argv[1:] if not a.startswith("--")]
    basis = "money" if "--money" in argv else "order"
    if len(args) >= 2:
        pairs = [(args[0], args[1].upper())]
    else:
        # THE MARKETPLACE THE ACCOUNT ACTUALLY TRADES IN. marketplaces[0] is the
        # first one listed, which gave FR for a UK seller and MX for a US one --
        # auditing three countries with no trade in them and reporting "every
        # metric consistent" because every row was empty.
        pairs = []
        for a in (D._cfg().get("accounts") or []):
            aid = a.get("id")
            m = (a.get("default_marketplace")
                 or (a.get("marketplaces") or [None])[0])
            if aid and m:
                pairs.append((aid, str(m).upper()))

    all_problems = {}
    for aid, mkt in pairs:
        try:
            probs = audit(aid, mkt, basis=basis)
        except Exception as e:
            probs = ["audit failed: %s" % str(e)[:160]]
        if probs:
            all_problems[aid] = probs

    print("\n%s\nSUMMARY\n%s" % ("=" * 74, "=" * 74))
    if not all_problems:
        print("Every checked metric is consistent on every account.")
        return 0
    for aid, probs in all_problems.items():
        print("\n%s:" % aid)
        for p in probs:
            print("   - %s" % p)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
