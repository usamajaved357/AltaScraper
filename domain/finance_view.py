"""domain/finance_view.py -- the Finance screen's two derived panels.

previous_window()  the same-length window just before, for the "vs prev" cards
overhead()         the gap between contribution and net profit, itemised

Moved word for word out of routes/finance_routes.py (architecture batch A8,
29 Sep 2026); the only change is that CONFIG_PATH and _cfg, which the route
had from its closure, are passed in. The route keeps same-named wrappers.
"""
from domain import contribution as _contrib


def previous_window(config_path, cfg, wsid, mkt, start, end, basis):
    """The same window, immediately before. Totals only.

    Every "vs prev 30d" on the cards is against this. Returns None rather
    than zeros when the earlier window has nothing -- a move from no data to
    a number is not a rise, and rendering it as one invites somebody to
    celebrate a sync finishing.
    """
    import datetime as _dt
    try:
        s = _dt.date.fromisoformat(start)
        e = _dt.date.fromisoformat(end)
    except ValueError:
        return None
    span = (e - s).days + 1
    pe = s - _dt.timedelta(days=1)
    ps = pe - _dt.timedelta(days=span - 1)
    from domain import sales_data as _sd
    try:
        fn = (_contrib.by_product if basis == "settlement"
              else _contrib.by_product_orders)
        _rows, tot = fn(config_path, wsid, mkt, ps.isoformat(),
                        pe.isoformat(), vat_rate=_sd.vat_rate_for(cfg, wsid))
    except Exception:
        return None
    if not _rows:
        return None
    tot["start"] = ps.isoformat()
    tot["end"] = pe.isoformat()
    return tot


def overhead(config_path, wsid, mkt, start, end, totals):
    """The gap between contribution and net profit, itemised as far as it can be.

    THE SPEC ASKS FOR EIGHT NAMED AMAZON FEE TYPES -- fba_inbound_transportation,
    fba_disposal, deal_participation and the rest. THOSE ARE NOT STORED.
    domain/finance_data buckets every charge into referral, FBA, promo or
    "other", and only the bucket survives; the fee TYPE Amazon sent is not
    kept. So the accordion shows the two lines that ARE knowable -- what
    Amazon charged the account outside any order, and the costs entered by
    hand -- and says plainly that the rest cannot be broken down yet rather
    than inventing eight rows of plausible names.

    That is a real limitation with a real fix (keep the fee type on the way
    in), and naming it is how it gets fixed rather than papered over.
    """
    out = {"items": [], "total": 0.0, "why": ""}

    # THE SAME STEP THE P&L TAKES, from the same place. Both the Amazon
    # charge that belongs to no order and the costs entered by hand come
    # from expenses.overhead_for, which also makes sure a subscription the
    # owner has recorded as a cost is not taken off a second time. This
    # screen used to take the Amazon charge off automatically while the
    # P&L did not, so their "net profit" differed by the subscription.
    try:
        from domain import expenses as _exp
        ov = _exp.overhead_for(config_path, wsid, mkt, start, end)
    except Exception:
        ov = {"amazon_account_charges": 0.0, "own_costs": 0.0,
              "own_costs_detail": {"total": 0.0, "items": [], "recorded": 0}}
    unatt = float(ov.get("amazon_account_charges") or 0.0)
    if unatt:
        out["items"].append({
            "label": "Amazon charges that belong to no order",
            "amount": round(unatt, 2),
            "note": ("The monthly selling subscription is the usual one. "
                     "Amazon posts these against the account rather than a "
                     "sale, so no per-product row can carry them."),
            "children": [],
        })
    man = ov["own_costs_detail"]
    out["items"].append({
        "label": "Your own costs",
        # RECORDED NONE AND SPENT NONE ARE DIFFERENT, and the accordion says
        # which: None reads "not recorded", 0.00 is a measurement.
        "amount": (round(float(man.get("total") or 0), 2)
                   if man.get("recorded") else None),
        "note": ("The accountant, the software, the packaging — Amazon "
                 "reports none of it." if man.get("recorded") else
                 "Nothing recorded, so nothing has been subtracted for it."),
        "children": [{"label": x["name"], "amount": x["in_window"]}
                     for x in (man.get("items") or [])],
    })

    out["total"] = round(unatt + float(man.get("total") or 0), 2)
    out["why"] = (
        "Amazon sends a type with every charge — storage, inbound "
        "transportation, disposal, deal participation — but this app keeps "
        "only the bucket it falls into, so those cannot be listed "
        "separately yet. The total above is right; the breakdown inside it "
        "is not available.")
    # FROM THE ACCOUNT'S FIGURE where there is one -- the Sales card's
    # profit, which also carries ad spend no product could be matched to --
    # so this screen's net profit is the P&L's net profit.
    c = (totals.get("account_contribution")
         if totals.get("basis") == "orders" else totals.get("contribution"))
    out["contribution"] = c
    out["net_profit"] = (round(c - out["total"], 2) if c is not None else None)
    return out
