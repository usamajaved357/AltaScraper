"""domain/expenses.py -- the costs Amazon knows nothing about.

The P&L is built from what Amazon reports. Amazon reports nothing about the
accountant, the software subscription, the packaging, the postage bought
elsewhere or the money paid to an agency -- so a P&L that stops at Amazon's
figures is not the business's profit, however carefully the fees are measured.

IT ALSO CATCHES THE ONE AMAZON CHARGE THE ORDER-JOINED QUERIES CANNOT SEE.
Measured on nestwell_goods: the per-order fees come to 1.28 of "other" while the
account was charged 61.28. The missing 60.00 is the monthly selling
subscription, which Amazon posts against the ACCOUNT rather than any sale. Every
order-joined fee query is blind to it by construction. domain/pnl.py has
reported it as an unattributed fixed cost since the fee work went in; this is
where it stops being a footnote and starts being subtracted -- and `suggest()`
below offers to create it, filled in, rather than making somebody read the note
and retype the number.

MONTHLY, APPORTIONED BY DAY. An expense is entered once as a monthly amount with
a start date, and appears in every window it overlaps. A P&L for twelve days of
a month carries twelve days of the rent, not a month of it -- because the
alternative is that a fortnightly report looks twice as profitable as the month
containing it, which is the sort of thing somebody makes a decision on.

NOTHING IS ASSUMED. An expense that has not been entered is not zero, it is
absent, and the P&L says how many are recorded so "no other costs" can be told
apart from "nobody has entered any yet".
"""
import calendar as _cal
import datetime as _dt

from data import db as _db


def _d(s):
    """A date, or None. Accepts what a form and a database both produce."""
    s = str(s or "")[:10]
    if not s:
        return None
    try:
        return _dt.date.fromisoformat(s)
    except ValueError:
        return None


def _now():
    return _dt.datetime.now().isoformat(timespec="seconds")


def _days_in_month(y, m):
    return _cal.monthrange(y, m)[1]


def overlap_days(start, end, e_start, e_end):
    """How many days of [start, end] this expense was actually running.

    Both ends inclusive. An expense with no end date runs for ever, which is the
    normal case for a subscription -- it is not the same as one that ended
    today, and treating it as ended is how a live cost silently drops out.
    """
    s, e = _d(start), _d(end)
    es, ee = _d(e_start), _d(e_end)
    if not s or not e or not es:
        return 0
    lo = max(s, es)
    hi = min(e, ee) if ee else e
    if hi < lo:
        return 0
    return (hi - lo).days + 1


def _month_share(day):
    """One day's share of a monthly amount.

    Divided by the length of the month that day is IN, not by a flat 30. A
    monthly cost apportioned at 1/30 over a 31-day month quietly loses a day of
    it every August, and gains one every February.
    """
    return 1.0 / _days_in_month(day.year, day.month)


def apportion(amount, start, end, e_start, e_end):
    """A monthly amount -> what belongs to this window. Never negative.

    Walks the days rather than doing it in one division, because a window can
    span months of different lengths and the whole point of _month_share is that
    the divisor changes.
    """
    try:
        amt = float(amount or 0)
    except (TypeError, ValueError):
        return 0.0
    s, e = _d(start), _d(end)
    es, ee = _d(e_start), _d(e_end)
    if not s or not e or not es or amt == 0:
        return 0.0
    lo = max(s, es)
    hi = min(e, ee) if ee else e
    if hi < lo:
        return 0.0
    total, day = 0.0, lo
    while day <= hi:
        total += amt * _month_share(day)
        day += _dt.timedelta(days=1)
    return round(total, 2)


# ---------------------------------------------------------------------------
# Storing
# ---------------------------------------------------------------------------


def add(config_path, workspace_id, name, amount, starts, marketplace=None,
        category="", currency="", ends=None, note=""):
    """Record one recurring cost. -> its id, or (None, why).

    marketplace None means the whole account: an accountant's fee is not a UK
    cost or a German one, and forcing it to be either would make every
    single-marketplace P&L wrong in the same direction.
    """
    name = str(name or "").strip()
    if not name:
        return None, "give the cost a name"
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        return None, "the amount must be a number"
    if amt < 0:
        # A NEGATIVE COST IS INCOME, and calling it a cost would subtract it
        # twice over -- once by sign and once by the P&L's own minus.
        return None, ("a cost cannot be negative. If money comes IN, it belongs "
                      "in the sales or reimbursements lines, not here")
    if not _d(starts):
        return None, "the start date must be a real date, as YYYY-MM-DD"
    if ends and not _d(ends):
        return None, "the end date must be a real date, as YYYY-MM-DD"
    if ends and _d(ends) < _d(starts):
        return None, "the end date is before the start date"

    conn = _db.get_db(config_path)
    cur = conn.execute(
        "INSERT INTO manual_expenses (workspace_id, marketplace, name, category, "
        "amount, currency, starts, ends, note, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (workspace_id, (marketplace or None), name, str(category or ""),
         round(amt, 2), str(currency or ""), str(starts)[:10],
         (str(ends)[:10] if ends else None), str(note or ""), _now(), _now()))
    conn.commit()
    return cur.lastrowid, ""


def update(config_path, workspace_id, expense_id, **fields):
    """Change one expense. Only the fields given; the account is checked.

    THE WORKSPACE IS IN THE WHERE CLAUSE, not just read from the row: an id from
    another account must not be editable by guessing the number.
    """
    allowed = ("name", "category", "amount", "currency", "starts", "ends",
               "note", "marketplace")
    sets, args = [], []
    for k in allowed:
        if k not in fields:
            continue
        v = fields[k]
        if k == "amount":
            try:
                v = round(float(v), 2)
            except (TypeError, ValueError):
                return 0, "the amount must be a number"
            if v < 0:
                return 0, "a cost cannot be negative"
        if k in ("starts", "ends"):
            v = (str(v)[:10] or None) if v else None
            if k == "starts" and not _d(v):
                return 0, "the start date must be a real date"
            if k == "ends" and v and not _d(v):
                return 0, "the end date must be a real date"
        sets.append("%s=?" % k)
        args.append(v)
    if not sets:
        return 0, "nothing to change"
    sets.append("updated_at=?")
    args.append(_now())
    args += [workspace_id, int(expense_id)]
    conn = _db.get_db(config_path)
    cur = conn.execute("UPDATE manual_expenses SET %s WHERE workspace_id=? "
                       "AND id=?" % ", ".join(sets), args)
    conn.commit()
    return cur.rowcount or 0, ""


def remove(config_path, workspace_id, expense_id):
    """Delete one. The workspace is in the WHERE clause for the same reason."""
    conn = _db.get_db(config_path)
    cur = conn.execute("DELETE FROM manual_expenses WHERE workspace_id=? AND id=?",
                       (workspace_id, int(expense_id)))
    conn.commit()
    return cur.rowcount or 0


def all_for(config_path, workspace_id, marketplace=None):
    """Every recorded cost for this account, newest first.

    Includes the account-wide ones (marketplace NULL) whatever marketplace is
    asked for, because that is what account-wide means.
    """
    conn = _db.get_db(config_path)
    if marketplace:
        rows = conn.execute(
            "SELECT * FROM manual_expenses WHERE workspace_id=? "
            "AND (marketplace IS NULL OR marketplace='' OR marketplace=?) "
            "ORDER BY starts DESC, id DESC", (workspace_id, marketplace))
    else:
        rows = conn.execute(
            "SELECT * FROM manual_expenses WHERE workspace_id=? "
            "ORDER BY starts DESC, id DESC", (workspace_id,))
    return [dict(r) for r in rows]


def for_window(config_path, workspace_id, marketplace, start, end):
    """What these costs come to for one window. -> a dict the P&L can use.

    Every expense is listed with the share that landed in this window AND its
    full monthly amount, so a reader can see that a 60.00 subscription
    contributed 23.23 to a twelve-day period rather than wondering where the
    number came from.
    """
    rows = all_for(config_path, workspace_id, marketplace)
    out, total = [], 0.0
    for r in rows:
        share = apportion(r["amount"], start, end, r["starts"], r.get("ends"))
        days = overlap_days(start, end, r["starts"], r.get("ends"))
        if not days:
            continue
        total += share
        out.append({
            "id": r["id"], "name": r["name"], "category": r.get("category") or "",
            "monthly": round(float(r["amount"]), 2),
            "in_window": share, "days": days,
            "currency": r.get("currency") or "",
            "marketplace": r.get("marketplace") or "",
            "starts": r["starts"], "ends": r.get("ends") or "",
            "note": r.get("note") or "",
        })
    out.sort(key=lambda x: -x["in_window"])
    return {
        "total": round(total, 2),
        "count": len(out),
        # HOW MANY EXIST AT ALL, not just how many landed here. "You have
        # recorded none" and "none of the four fell in this window" are
        # different facts and the screen should be able to say which.
        "recorded": len(rows),
        "items": out,
    }


# The three fee kinds an account can be charged outside an order (30 Sep 2026).
_FEES_SQL = ("SUM(COALESCE(other_fees,0)+COALESCE(fba_fees,0)"
             "+COALESCE(promo_fees,0))")


def _attributed_fees(conn, workspace_id, marketplace, start, end, by):
    """The fees in the window that a row of the screen already carries -> float,
    or None when there is nothing to compare with.

    by="orders"    the postings attached to an order (order_fees) -- the order
                   calendar, the P&L, the Sales screen;
    by="products"  the per-product rows of finance_daily -- the Finance screen's
                   settlement tab, whose product rows carry a SKU's removal
                   fees too, which no order does."""
    if by == "products":
        r = conn.execute(
            "SELECT %s o, COUNT(*) n FROM finance_daily WHERE workspace_id=? AND "
            "marketplace=? AND asin<>'*' AND date>=? AND date<=?" % _FEES_SQL,
            (workspace_id, marketplace, start, end)).fetchone()
    else:
        r = conn.execute(
            "SELECT %s o, COUNT(*) n FROM order_fees WHERE workspace_id=? AND "
            "marketplace=? AND substr(posted_date,1,10)>=? AND "
            "substr(posted_date,1,10)<=?" % _FEES_SQL,
            (workspace_id, marketplace, start, end)).fetchone()
    if not r or not r["n"]:
        return None
    return float(r["o"] or 0)


def account_level_charge(config_path, workspace_id, marketplace, start, end,
                         attributed_by="orders"):
    """What Amazon charged the ACCOUNT that belongs to no order. -> float.

    The monthly selling subscription is the usual one. Amazon posts it against
    the account rather than a sale, so every order-joined fee query in the app
    is blind to it by construction -- measured at 60.00 on nestwell_goods
    against 1.28 of "other" the per-order query could see.

    THE SAME NUMBER WHICHEVER CALENDAR THE SCREEN IS ON. It is what Amazon
    charged in the window, less what the orders account for; neither half
    depends on whether the caller is thinking in orders or in settlements. The
    Finance screen derived it from a totals field that only held in settlement
    mode, so the overhead line read 65.51 on one tab and 0.00 on the other for
    the same month and the same charge.

    Never negative: when the orders account for MORE than Amazon charged, there
    is no account-level charge to find, and a negative here would be subtracted
    from profit as though it were income.
    """
    conn = _db.get_db(config_path)
    # ALL THREE FEE KINDS, not only "other" (owner, 30 Sep 2026: every
    # transaction in the account). Storage and inbound fees are FBA fees posted
    # against no order, and a coupon's participation fee arrives as an account
    # service fee -- both were charged, and neither reached any profit.
    charged = conn.execute(
        "SELECT ROUND(%s,2) o, ROUND(SUM(COALESCE(other_fees,0)),2) oth, "
        "SUM(COALESCE(principal,0)) p FROM finance_daily "
        "WHERE workspace_id=? AND marketplace=? AND asin='*' "
        "AND date>=? AND date<=?" % _FEES_SQL,
        (workspace_id, marketplace, start, end)).fetchone()
    # BOTH SIDES ON THE SAME CALENDAR: the day Amazon POSTED the money.
    #
    # This compared what Amazon posted in the window (finance_daily) with the
    # fees on orders PLACED in the window -- two calendars. A July order's 2.00
    # charge settled on 5 Aug was then in July's fees AND in August's
    # "account charge", counted twice; and orders placed late in a window but
    # settled after it inflated the other side and could hide the subscription
    # altogether. Found by the review of the profit-accuracy work, 28 Sep 2026.
    #
    # Every order-level posting carries its order id and posted_date in
    # order_fees, so "posted in the window and attached to an order" is exact,
    # and what finance_daily holds beyond it belongs to no order. It also
    # counts each posting once however many products the order had -- the
    # join to order_lines this replaces counted a three-product order three
    # times.
    attributed = _attributed_fees(conn, workspace_id, marketplace, start, end,
                                  attributed_by)
    if not charged:
        return 0.0
    if attributed is None and float(charged["p"] or 0) > 0:
        # SALES SETTLED BUT NO PER-ORDER POSTINGS KEPT (a window synced before
        # order_fees existed, or its write failed). The shipments' FBA fees are
        # then inside the '*' total with nothing to set them against, so only
        # the "other" fees -- which no shipment carries -- are sure to belong to
        # no order. The rule before 30 Sep 2026, kept for that case.
        return max(0.0, round(float(charged["oth"] or 0), 2))
    gap = round(float(charged["o"] or 0) - float(attributed or 0), 2)
    return max(0.0, gap)


def account_adjustments(config_path, workspace_id, marketplace, start, end):
    """Every other Amazon posting in the window, SIGNED: + money to you, - a
    cost. -> float. Postage labels bought through Amazon, Vine enrolment, tax
    retrocharges, removal revenue, anything Amazon adds tomorrow (finance_data
    reads them into `adjustments`; owner, 30 Sep 2026)."""
    r = _db.get_db(config_path).execute(
        "SELECT ROUND(SUM(COALESCE(adjustments,0)),2) a FROM finance_daily "
        "WHERE workspace_id=? AND marketplace=? AND asin='*' AND date>=? AND date<=?",
        (workspace_id, marketplace, start, end)).fetchone()
    return round(float((r["a"] if r else 0) or 0), 2)


def apply_account_money(est, totals):
    """Take the account's own money off a trading profit -> the same dict,
    with `profit` now NET (the P&L's "Net profit"; owner, 30 Sep 2026: the
    same profit on every screen). The trading figure is kept as
    `profit_before_account`; the three parts are named so the working can be
    shown. `totals` carries account_charges / other_amazon / own_costs for the
    same window (sales_data.totals sums them from the rows the grid draws)."""
    if not isinstance(est, dict) or est.get("profit") is None:
        return est
    ac = float((totals or {}).get("account_charges") or 0.0)
    oa = float((totals or {}).get("other_amazon") or 0.0)
    oc = float((totals or {}).get("own_costs") or 0.0)
    est["profit_before_account"] = est["profit"]
    est["account_charges"] = round(ac, 2)
    est["other_amazon"] = round(oa, 2)
    est["own_costs"] = round(oc, 2)
    est["profit"] = round(float(est["profit"]) - ac + oa - oc, 2)
    nr = est.get("net_revenue")
    if nr:
        est["margin_pct"] = round(est["profit"] / float(nr) * 100, 1)
    return est


def account_money_totals(config_path, workspace_id, marketplace, start, end):
    """The three account-level lines for a window, from overhead_for (the
    P&L's step) -> {account_charges, other_amazon, own_costs}, the shape
    apply_account_money reads."""
    ov = overhead_for(config_path, workspace_id, marketplace, start, end)
    return {"account_charges": ov.get("amazon_account_charges") or 0.0,
            "other_amazon": ov.get("amazon_other_transactions") or 0.0,
            "own_costs": ov.get("own_costs") or 0.0,
            "errors": ov.get("errors") or []}


def amazon_charge_given_back(ov):
    """How much of Amazon's measured account charge the owner's own entries
    already cover in the window (overhead_for's dict) -> float >= 0."""
    seen = float(ov.get("amazon_charge_seen") or 0.0)
    return max(0.0, seen - float(ov.get("amazon_account_charges") or 0.0))


def account_money_by_day(config_path, workspace_id, marketplace, start, end,
                         fees_in_rows=False):
    """The account's own money, per day -> {date: {account_charges,
    other_amazon, own_costs}} -- for the Sales grid, so a week or a month there
    is the P&L's NET profit (owner, 30 Sep 2026: accurate profit on every screen).

    THE SAME TOTALS overhead_for gives the P&L, per calendar month of the
    window, then placed on days:
      account_charges  on the days Amazon posted them (each day's share of the
                       month's positive gaps), so the subscription lands on its day;
      other_amazon     exactly as posted, signed;
      own_costs        spread evenly over the month's days in the window (they
                       are monthly amounts; for_window apportions them by day).
    So summing the days of any month gives that month's P&L lines to the penny.

    fees_in_rows: the grid is on the MONEY calendar, where each day's row is
    the account's '*' finance row and its fees already include every account
    charge (sales_data.net_proceeds_for). Taking them off again counted the
    subscription twice (review, 30 Sep 2026). Then account_charges is only the
    part of Amazon's charge the owner ALSO entered as his own cost, given back
    (<= 0) -- overhead_for's same "not twice" rule.
    """
    import datetime as _dtm
    conn = _db.get_db(config_path)
    d0 = _dtm.date.fromisoformat(str(start)[:10])
    d1 = _dtm.date.fromisoformat(str(end)[:10])
    out = {}
    m0 = d0
    while m0 <= d1:
        nxt = (m0.replace(day=28) + _dtm.timedelta(days=4)).replace(day=1)
        m1 = min(d1, nxt - _dtm.timedelta(days=1))
        s, e = m0.isoformat(), m1.isoformat()
        ov = overhead_for(config_path, workspace_id, marketplace, s, e)
        days = [(m0 + _dtm.timedelta(days=i)).isoformat() for i in range((m1 - m0).days + 1)]
        for d in days:
            out[d] = {"account_charges": 0.0, "other_amazon": 0.0, "own_costs": 0.0}
        # Where the month's account charge fell: each day's own gap.
        gaps = {}
        for r in conn.execute(
                "SELECT date, %s c, "
                "SUM(COALESCE(adjustments,0)) a FROM finance_daily WHERE workspace_id=? AND "
                "marketplace=? AND asin='*' AND date>=? AND date<=? GROUP BY date" % _FEES_SQL,
                (workspace_id, marketplace, s, e)):
            gaps[r["date"]] = float(r["c"] or 0)
            if r["date"] in out:
                out[r["date"]]["other_amazon"] = round(float(r["a"] or 0), 4)
        for r in conn.execute(
                "SELECT substr(posted_date,1,10) d, %s c FROM order_fees WHERE workspace_id=? "
                "AND marketplace=? AND substr(posted_date,1,10)>=? AND "
                "substr(posted_date,1,10)<=? GROUP BY d" % _FEES_SQL,
                (workspace_id, marketplace, s, e)):
            gaps[r["d"]] = gaps.get(r["d"], 0.0) - float(r["c"] or 0)
        pos = {d: g for d, g in gaps.items() if g > 0 and d in out}
        amazon = float(ov.get("amazon_account_charges") or 0.0)
        if fees_in_rows:
            amazon = 0.0
            back = round(amazon_charge_given_back(ov), 4)
            if back and days:
                out[days[-1]]["account_charges"] = -back
        tot = sum(pos.values())
        if amazon and tot:
            for d, g in pos.items():
                out[d]["account_charges"] = round(amazon * g / tot, 4)
        elif amazon and days:
            out[days[-1]]["account_charges"] = round(amazon, 4)
        own = float(ov.get("own_costs") or 0.0)
        if own and days:
            per = own / len(days)
            for d in days:
                out[d]["own_costs"] = round(per, 4)
        m0 = nxt
    return out


def _is_amazon_charge(expense):
    """Is this recorded cost the owner's own entry for an AMAZON account charge?

    It has to say Amazon -- by its category (suggest() files it under "Amazon")
    or its name. The earlier test was any name containing "subscription",
    which made a "Helium 10 subscription" stand in for Amazon's own charge and
    quietly stop that being subtracted. Found by the review, 28 Sep 2026.
    """
    # AND IT HAS TO BE THE ACCOUNT CHARGE, not any Amazon cost. Matching every
    # name containing "amazon" let an "Amazon PPC (manual)" entry cancel the
    # measured subscription -- found by the second review, 28 Sep 2026. So: the
    # category suggest() files it under, or a name that says Amazon AND says
    # what kind of charge it is.
    e = expense or {}
    name = str(e.get("name") or "").lower()
    if str(e.get("category") or "").strip().lower() == "amazon":
        return True
    return "amazon" in name and any(
        w in name for w in ("subscription", "seller account", "selling plan",
                            "professional plan", "monthly fee"))


def _subscription_recorded(config_path, workspace_id, marketplace):
    """Has the owner recorded Amazon's account charge as a cost of their own?

    Only decides whether suggest() should OFFER to add it. How much of it to
    stop subtracting is overhead_for's job, and it works that out for the
    window, not from whether an entry exists at all.
    """
    return any(_is_amazon_charge(r)
               for r in all_for(config_path, workspace_id, marketplace))


def overhead_for(config_path, workspace_id, marketplace, start, end,
                 attributed_by="orders"):
    """The step from the headline profit to NET profit. -> a dict.

        net profit = profit (the Sales card's figure)
                   - what Amazon charged the ACCOUNT and no order carries
                   - the costs you entered yourself

    THE ONE PLACE THAT STEP IS TAKEN. The P&L and the Finance screen each had
    their own, and they disagreed: Finance subtracted Amazon's account charge
    automatically, the P&L only once somebody had typed it in as a cost -- so
    the two "net profit" figures for the same month differed by the
    subscription (CLAUDE.md Rule 12).

    The account charge is MEASURED (Amazon took it), so it comes off. Where
    the owner has ALSO recorded it as a cost of their own, the part of it his
    entry already covers IN THIS WINDOW is not taken off a second time -- only
    the remainder. So an entry starting 1 Sep stops nothing in August, and an
    entry for less than Amazon charged still leaves the difference to come off.
    """
    # WHAT COULD NOT BE READ IS SAID (`errors`), never swallowed: a missing
    # part leaves net profit higher than it is (review, 30 Sep 2026). The
    # P&L, the Finance screen and the Sales card print it.
    errors = []
    try:
        charge = account_level_charge(config_path, workspace_id, marketplace,
                                      start, end, attributed_by=attributed_by)
    except Exception as e:
        charge = 0.0
        errors.append("Amazon's account charges could not be read (%s)" % e)
    man = for_window(config_path, workspace_id, marketplace, start, end)
    covered = round(sum(float(i.get("in_window") or 0.0)
                        for i in (man.get("items") or [])
                        if _is_amazon_charge(i)), 2)
    amazon = round(max(0.0, charge - covered), 2)
    recorded_already = charge > 0 and covered > 0
    own = round(float(man.get("total") or 0.0), 2)
    try:
        other = account_adjustments(config_path, workspace_id, marketplace, start, end)
    except Exception as e:
        other = 0.0
        errors.append("Amazon's other postings could not be read (%s)" % e)
    return {
        "errors": errors,
        "amazon_account_charges": amazon,
        # Signed: + money Amazon paid in, - a cost. Comes off (or goes on) net
        # profit beside the account charges.
        "amazon_other_transactions": other,
        "amazon_charge_seen": round(charge, 2),
        "amazon_charge_in_own_costs": bool(recorded_already),
        "amazon_charge_covered_by_own": covered,
        "own_costs": own,
        "own_costs_recorded": bool(man.get("recorded")),
        "own_costs_detail": man,
        "total": round(amazon + own - other, 2),
    }


def suggest(config_path, workspace_id, marketplace, start, end):
    """The fixed Amazon charge nobody has entered yet, offered ready to add.

    domain/pnl.py can already SEE the monthly subscription -- it is the gap
    between what Amazon charged the account and what the order-joined fees
    account for -- and until now all it could do was print a note asking
    somebody to treat it as a fixed cost. Reading a note and retyping a number
    is the step nobody takes, so this hands back the figure and the wording, and
    the screen offers a button.

    Returns None when there is nothing to suggest, or when something matching is
    already recorded -- offering to add a cost that is already subtracted is how
    it ends up subtracted twice.
    """
    # ONE READER OF THAT GAP, shared with the Finance screen's overhead line so
    # the two cannot report different figures for the same charge (Rule 12).
    gap = account_level_charge(config_path, workspace_id, marketplace, start, end)
    if gap <= 0:
        return None

    # Already recorded? Matched on name rather than amount, because the amount
    # is what somebody would correct.
    if _subscription_recorded(config_path, workspace_id, marketplace):
        return None

    return {
        "name": "Amazon selling subscription",
        "category": "Amazon",
        "amount": gap,
        "starts": str(start)[:10],
        "why": ("Amazon charged this account %.2f in this window that belongs to "
                "no order — the monthly selling subscription is the usual one. "
                "It is already taken off net profit as an Amazon account charge. "
                "Add it as a monthly cost of your own if you want it named and "
                "carried into months Amazon has not posted yet; it will not be "
                "counted twice." % gap),
    }
