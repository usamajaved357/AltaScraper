"""domain/asin_charges.py -- the costs that are not the supplier's price.

WHY THIS EXISTS
Asked for: "give me option to add the additional charges per asin, which can be
sometimes my shipping price, my prep charges, my ads costs which i write
manually".

The supplier's price already includes their postage -- "the source price is
actual source price including shipping" -- so that half is covered. What is not
covered is everything the seller pays afterwards: sending it on, prep and
labelling, an advertising figure allocated by hand while the Ads API is not
connected. Without these, profit is the supplier price subtracted from revenue
and nothing else, which reads better than the business is doing.

ONE ROW PER NAMED CHARGE
Not a column per kind. The list of things a seller pays for is not fixed and
never will be, and a `prep_cost` column forces the next one into a name that does
not fit. A named row also lets the screen show WHAT the costs were rather than
only their total, which is what makes a thin margin explainable instead of
merely disappointing.

PER UNIT
Profit is worked out per unit sold, so charges are per unit. A cost that is
really per shipment is entered as its per-unit share, and saying so plainly is
what stops it being guessed at later.

DATED, SO HISTORY DOES NOT MOVE
A charge carries the date it started applying. An order is costed with the newest
charge dated on or before it, so putting up today's prep fee does not silently
rewrite what last month earned. A charge with no date applies from the beginning,
which is what a first entry should mean.
"""
import datetime as _dt

from data import db as _db


def _now():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_for(config_path, workspace_id, marketplace, asin=None, sku=None):
    """Every charge for this workspace, or just one product's."""
    conn = _db.get_db(config_path)
    q = ("SELECT * FROM asin_charges WHERE workspace_id=? AND marketplace=?")
    args = [workspace_id, marketplace]
    if asin:
        q += " AND asin=?"
        args.append(asin)
    if sku:
        q += " AND sku=?"
        args.append(sku)
    q += " ORDER BY asin, sku, label, effective_from"
    return [dict(r) for r in conn.execute(q, args)]


def save(config_path, workspace_id, marketplace, asin, label, amount,
         sku="", effective_from="", note="", charge_id=None):
    """Add or update one charge. Returns its id.

    A blank or zero amount is kept rather than rejected: "prep is free on this
    one" is a real thing to record, and deleting is a separate, deliberate act.
    """
    conn = _db.get_db(config_path)
    label = str(label or "").strip()[:60]
    if not label:
        raise ValueError("a charge needs a name -- postage, prep, ads")
    try:
        amount = round(float(amount or 0), 4)
    except (TypeError, ValueError):
        raise ValueError("amount must be a number")
    eff = str(effective_from or "").strip()[:10]

    if charge_id:
        conn.execute(
            "UPDATE asin_charges SET asin=?, sku=?, label=?, amount=?, "
            "effective_from=?, note=?, updated_at=? "
            "WHERE id=? AND workspace_id=? AND marketplace=?",
            (str(asin or ""), str(sku or ""), label, amount, eff,
             str(note or "")[:300], _now(), int(charge_id),
             workspace_id, marketplace))
        conn.commit()
        return int(charge_id)

    cur = conn.execute(
        "INSERT INTO asin_charges (workspace_id, marketplace, asin, sku, label,"
        " amount, effective_from, note, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (workspace_id, marketplace, str(asin or ""), str(sku or ""), label,
         amount, eff, str(note or "")[:300], _now()))
    conn.commit()
    return int(cur.lastrowid)


def delete(config_path, workspace_id, marketplace, charge_id):
    conn = _db.get_db(config_path)
    conn.execute("DELETE FROM asin_charges WHERE id=? AND workspace_id=? "
                 "AND marketplace=?",
                 (int(charge_id), workspace_id, marketplace))
    conn.commit()
    return True


def per_unit(config_path, workspace_id, marketplace, asin, sku="", on_date=None):
    """(total_per_unit, [{label, amount}, ...]) applying on a given date.

    For each NAME, the newest charge dated on or before `on_date` wins -- so
    raising a prep fee today leaves every earlier order costed as it was. A
    charge dated later than the order does not apply to it at all.

    A charge recorded against the SKU beats one against the ASIN: the SKU is the
    more specific thing, and that is the only reason someone would enter one.
    """
    on_date = str(on_date or _dt.date.today().isoformat())[:10]
    conn = _db.get_db(config_path)
    # A charge entered against a SKU belongs to THAT SKU and must not leak onto
    # the ASIN as a whole: a postage figure typed for one variation was being
    # applied to every unit of the product, because the row carries the ASIN too.
    # So an ASIN-wide charge is one whose sku is blank; a SKU charge only ever
    # applies when that SKU is the one being asked about.
    rows = conn.execute(
        "SELECT label, amount, effective_from, sku FROM asin_charges "
        "WHERE workspace_id=? AND marketplace=? "
        "  AND ((sku='' AND asin=?) OR (sku<>'' AND sku=?)) "
        "  AND (effective_from='' OR effective_from<=?) "
        "ORDER BY effective_from",
        (workspace_id, marketplace, str(asin or ""), str(sku or ""),
         on_date)).fetchall()

    best = {}
    for r in rows:
        lab = r["label"]
        specific = bool(r["sku"])
        prev = best.get(lab)
        # Later date wins; at the same date the SKU-specific one wins.
        if prev is None:
            best[lab] = (r["effective_from"] or "", specific, float(r["amount"] or 0))
            continue
        p_eff, p_specific, _p_amt = prev
        eff = r["effective_from"] or ""
        if (eff, specific) >= (p_eff, p_specific):
            best[lab] = (eff, specific, float(r["amount"] or 0))

    parts = [{"label": lab, "amount": round(v[2], 4)}
             for lab, v in sorted(best.items())]
    return round(sum(p["amount"] for p in parts), 4), parts
