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


def account_level_charge(config_path, workspace_id, marketplace, start, end):
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
    charged = conn.execute(
        "SELECT ROUND(SUM(COALESCE(other_fees,0)),2) o FROM finance_daily "
        "WHERE workspace_id=? AND marketplace=? AND asin='*' "
        "AND date>=? AND date<=?",
        (workspace_id, marketplace, start, end)).fetchone()
    attributed = conn.execute(
        "SELECT ROUND(SUM(COALESCE(f.other_fees,0)),2) o FROM order_lines o2 "
        "JOIN order_fees f ON f.workspace_id=o2.workspace_id "
        "  AND f.marketplace=o2.marketplace AND f.order_id=o2.order_id "
        "WHERE o2.workspace_id=? AND o2.marketplace=? "
        "AND substr(o2.purchase_date,1,10)>=? AND substr(o2.purchase_date,1,10)<=?",
        (workspace_id, marketplace, start, end)).fetchone()
    gap = round(float((charged["o"] if charged else 0) or 0)
                - float((attributed["o"] if attributed else 0) or 0), 2)
    return max(0.0, gap)


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
    for r in all_for(config_path, workspace_id, marketplace):
        n = str(r.get("name") or "").lower()
        if "subscription" in n or "seller account" in n or "monthly fee" in n:
            return None

    return {
        "name": "Amazon selling subscription",
        "category": "Amazon",
        "amount": gap,
        "starts": str(start)[:10],
        "why": ("Amazon charged this account %.2f in this window that belongs to "
                "no order — the monthly selling subscription is the usual one. "
                "It cannot be attached to a sale, so no per-order query can find "
                "it and it is not in the profit above. Add it as a monthly cost "
                "and it will be." % gap),
    }
