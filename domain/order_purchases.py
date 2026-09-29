"""domain/order_purchases.py -- "I bought this order from the supplier", recorded.

WHAT THIS IS, AND WHAT IT IS NOT.
A NOTE A PERSON MAKES after buying the item themselves, on the supplier's own
website. The app buys nothing, contacts no supplier and spends no money: the
"Buy from supplier" button only opens the supplier's page. This record is what
lets the Orders page tell "still to buy" apart from "bought, waiting to post" --
the "To buy" tab of the Orders plan, which could not be drawn while the app held
nothing to decide it with.

NO MONEY IS STORED HERE. What an order cost is the order line's cost
(order_lines.cogs, written by domain/order_cogs.set_for_order from the Cost box
on the same panel). A second "paid" figure here would be a second answer to
"what did this order cost", free to disagree with the profit on the same screen
(CLAUDE.md Rule 12).

ONE ORDER OF ONE ACCOUNT. Every read and write names the account and the
marketplace; SKUs are not unique across accounts (Rule 14).
"""
import datetime as _dt

from data import db as _db

MAX_TEXT = 300          # a supplier name, an order number or a note; not an essay


def _clip(v, n=MAX_TEXT):
    return str(v or "").strip()[:n]


def record(config_path, workspace_id, marketplace, order_id, supplier="",
           supplier_url="", supplier_ref="", note="", who=""):
    """Record that this order was bought. -> the new record's id (0 if refused).

    Several records per order are allowed: a two-item order is often bought
    from two suppliers, and one of them being recorded is not both.
    """
    ws = _clip(workspace_id, 120)
    mkt = _clip(marketplace, 8).upper()
    oid = _clip(order_id, 60)
    if not (ws and mkt and oid):
        return 0
    url = _clip(supplier_url, 1000)
    if url and not url.lower().startswith(("http://", "https://")):
        # Drawn later as a link. Anything but a web address (javascript:, data:)
        # is dropped rather than stored and made clickable.
        url = ""
    conn = _db.get_db(config_path)
    # WITH ITS TIME ZONE. A bare local time is read by the browser as the
    # reader's own clock, an hour out in British Summer Time on a UTC server.
    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO order_purchases (workspace_id, marketplace, order_id, "
        "supplier, supplier_url, supplier_ref, note, bought_at, bought_by) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (ws, mkt, oid, _clip(supplier), url, _clip(supplier_ref), _clip(note),
         now, _clip(who, 200)))
    conn.commit()
    return int(cur.lastrowid or 0)


def remove(config_path, workspace_id, marketplace, order_id, purchase_id):
    """Forget ONE record, named by its id AND its order and account.

    All four must match, so an id typed against the wrong order -- or another
    account's -- removes nothing.
    """
    try:
        pid = int(purchase_id)
    except (TypeError, ValueError):
        return 0
    conn = _db.get_db(config_path)
    cur = conn.execute(
        "DELETE FROM order_purchases WHERE id=? AND workspace_id=? "
        "AND marketplace=? AND order_id=?",
        (pid, _clip(workspace_id, 120), _clip(marketplace, 8).upper(),
         _clip(order_id, 60)))
    conn.commit()
    return cur.rowcount or 0


def for_orders(config_path, workspace_id, marketplace, order_ids):
    """{order_id: [records, newest first]} for the orders a screen is showing.

    An empty list of ids reads NOTHING (never "every order of the account").
    """
    ids = [str(o).strip() for o in (order_ids or []) if str(o).strip()]
    if not ids:
        return {}
    conn = _db.get_db(config_path)
    out = {}
    # SQLite allows ~999 parameters per statement; read in slices so a long
    # list is answered in full rather than silently cut off.
    for i in range(0, len(ids), 900):
        part = ids[i:i + 900]
        q = ("SELECT id, order_id, supplier, supplier_url, supplier_ref, note, "
             "bought_at, bought_by FROM order_purchases "
             "WHERE workspace_id=? AND marketplace=? AND order_id IN (%s) "
             "ORDER BY bought_at DESC, id DESC" % ",".join("?" * len(part)))
        for r in conn.execute(q, [workspace_id, str(marketplace or "").upper()] + part):
            d = dict(r)
            out.setdefault(d["order_id"], []).append(d)
    return out


def attach(config_path, rows, order_key="order_id", account_key="account_id",
           marketplace_key="marketplace"):
    """Put each order's purchase records on its row, in place. -> the rows.

    r["purchases"] is a list, or None when it could not be read -- the Orders
    board then leaves the order out of "To buy" rather than claiming it still
    needs buying (or that it was bought).
    """
    from domain import order_attach as _oa

    def _put(r, got):
        r["purchases"] = got

    return _oa.attach(rows, lambda a, m, ids: for_orders(config_path, a, m, ids),
                      _put, order_key, account_key, marketplace_key)
