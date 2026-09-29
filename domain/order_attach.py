"""domain/order_attach.py -- put this app's own per-order records onto order rows.

The Orders list comes from Amazon; what the app itself holds about an order (the
tracking typed in, the "bought from the supplier" record) is joined on here.
Tracking did this alone until purchases needed the same join -- so the grouping
lives once, and each record type says only how to read and where to put it
(CLAUDE.md Rule 12).

ONE ACCOUNT AT A TIME. Records are read per (account, marketplace), because a
record belongs to one order of one account and SKUs -- and in principle order
ids -- are only unique inside one (Rule 14). A row missing its account or
marketplace is never matched: guessing would attach another account's record.
"""


def _key(r, order_key, account_key, marketplace_key):
    r = r or {}
    return (str(r.get(account_key) or "").strip(),
            str(r.get(marketplace_key) or "").strip().upper(),
            str(r.get(order_key) or "").strip())


def attach(rows, read, put, order_key="order_id", account_key="account_id",
           marketplace_key="marketplace"):
    """For each row, put(row, records) -- records is a list, or None if unknown.

    `read(account, marketplace, order_ids)` -> {order_id: [records]}.
    None means the read FAILED for that row's account (or the row cannot be
    matched), which is different from "there are none" -- a caller that draws
    "nothing recorded" from None would state something it does not know.
    One read per account and marketplace, not one per order.
    """
    groups = {}
    for r in rows or []:
        a, m, o = _key(r, order_key, account_key, marketplace_key)
        if a and m and o:
            groups.setdefault((a, m), []).append(o)

    found, failed = {}, set()
    for (a, m), ids in groups.items():
        try:
            got = read(a, m, ids) or {}
        except Exception:
            # A table that cannot be read must not empty the orders screen.
            failed.add((a, m))
            continue
        for oid, lst in got.items():
            found[(a, m, str(oid))] = lst

    for r in rows or []:
        a, m, o = _key(r, order_key, account_key, marketplace_key)
        if not (a and m and o) or (a, m) in failed:
            put(r, None)
        else:
            put(r, found.get((a, m, o)) or [])
    return rows
