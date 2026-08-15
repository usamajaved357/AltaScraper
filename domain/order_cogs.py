"""domain/order_cogs.py -- what each order's stock cost, frozen at the time.

WHY FREEZING MATTERS
Looked up later instead, an order from July picks up August's supplier price, and
last month's profit moves every time a supplier does. So the cost is worked out
once, when the order is first seen, and written onto that order line. A week you
have already looked at then never changes underneath you.

TWO MODES, BECAUSE THE OWNER HAS TWO WAYS OF WORKING
Asked for as a toggle on the page:

  TRACKED  the repricer checks each source every couple of hours and records the
           price with the time it was read. An order is costed at THE PRICE IN
           FORCE WHEN IT ARRIVED -- "the price of the item on 12th aug 12 am to
           2am was 7 gbp ... i received an order in between 12 to 2", so that
           order costs 7, whatever the price did afterwards.

  SKU      the cost written into the SKU by the generator
           (7.00_3Days_B0G1K5B7QS), overridden by a cost typed against the
           product, applying to every order past and future. Simple, and right
           for stock bought once at a known price.

WHERE A COST COMES FROM, IN ORDER OF TRUST
  1. a correction typed against THAT ONE ORDER -- always wins, and applies to
     that order alone: "my typed cogs win but it should be only for that order
     not all time frames and all orders"
  2. in TRACKED mode, the supplier price in force when the order arrived
  3. a cost typed against the product (domain/cogs.py overrides)
  4. the cost built into the SKU

THE SUPPLIER PRICE ALREADY INCLUDES THEIR POSTAGE -- "the source price is actual
source price including shipping" -- so nothing is added for inbound carriage.
What the seller pays AFTER that (postage out, prep, a hand-allocated ad figure)
is domain/asin_charges.py, and is added on top of this.

NO COST IS NOT A ZERO COST. A product nobody has costed returns None, never 0.
Zero would make it look infinitely profitable, and that is precisely the product
someone would then buy more of.
"""
import datetime as _dt

from data import db as _db

MODE_TRACKED = "tracked"
MODE_SKU = "sku"
MODES = (MODE_TRACKED, MODE_SKU)
DEFAULT_MODE = MODE_SKU


def mode_for(config, workspace_id):
    """Which costing mode this account is on. Per account, like VAT."""
    cfg = config() if callable(config) else (config or {})
    for a in (cfg.get("accounts") or []):
        if str(a.get("id")) == str(workspace_id):
            m = str(a.get("cogs_mode") or "").strip().lower()
            return m if m in MODES else DEFAULT_MODE
    return DEFAULT_MODE


def tracked_cost(config_path, workspace_id, marketplace, sku, when):
    """The supplier price in force at `when`, or None.

    THE PRICE IN FORCE, not the nearest reading. The newest check taken at or
    BEFORE the moment the order arrived is the price that was true then; a later
    check describes a price the order never paid. Asked for exactly this way.

    price + shipping, because a source whose postage is unknown is not a source
    whose postage is free -- sourcing_checks stores NULL for unknown, and a row
    with unknown postage is skipped rather than counted as cheaper than it is.
    """
    conn = _db.get_db(config_path)
    row = conn.execute(
        "SELECT c.price, c.shipping, s.shipping_override "
        "FROM sourcing_checks c "
        "JOIN sourcing_sources s ON s.id = c.source_id "
        "WHERE s.workspace_id=? AND s.marketplace=? AND s.sku=? "
        "  AND s.enabled=1 AND c.status='fetched' AND c.price IS NOT NULL "
        "  AND c.checked_at <= ? "
        "ORDER BY c.checked_at DESC, s.priority ASC LIMIT 1",
        (workspace_id, marketplace, str(sku or ""), str(when or ""))).fetchone()
    if not row:
        return None
    try:
        price = float(row["price"])
    except (TypeError, ValueError):
        return None
    ship = row["shipping"]
    if ship is None:
        ship = row["shipping_override"]
    if ship is None:
        # Unknown postage is not free postage. Better to have no cost -- which
        # is visible and fixable -- than a cost that is quietly too low.
        return None
    try:
        return round(price + float(ship), 4)
    except (TypeError, ValueError):
        return None


def resolve(config_path, workspace_id, marketplace, sku, when, mode,
            overrides=None, order_override=None):
    """(cost_per_unit, source) for one line. cost is None when unknown.

    `order_override` is a correction typed against this one order; it wins over
    everything and applies to nothing else.
    """
    from domain import cogs as _cogs

    if order_override is not None:
        try:
            return round(float(order_override), 4), "manual-order"
        except (TypeError, ValueError):
            pass

    if mode == MODE_TRACKED:
        c = tracked_cost(config_path, workspace_id, marketplace, sku, when)
        if c is not None:
            return c, "tracked"

    # Both modes fall back here: a typed cost, then the SKU's own. In TRACKED
    # mode this covers orders from before the repricer ever saw that product,
    # which would otherwise have no cost at all.
    cost, src = _cogs.resolve(overrides or {}, workspace_id, sku)
    if cost is not None:
        return round(float(cost), 4), ("manual" if src == "manual" else "sku")
    return None, ""


def freeze_range(config_path, workspace_id, marketplace, start, end, mode,
                 overrides=None, force=False):
    """Work out and store the cost of every order line in a window.

    Only lines with no cost yet are touched, unless `force` -- so a cost already
    frozen stays frozen, which is the whole point. Returns a short report.
    """
    conn = _db.get_db(config_path)
    q = ("SELECT id, sku, asin, purchase_date, cogs FROM order_lines "
         "WHERE workspace_id=? AND marketplace=? "
         "  AND substr(purchase_date,1,10) >= ? "
         "  AND substr(purchase_date,1,10) <= ?")
    rows = conn.execute(q, (workspace_id, marketplace, str(start), str(end))).fetchall()

    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    priced = unpriced = skipped = 0
    for r in rows:
        if r["cogs"] is not None and not force:
            skipped += 1
            continue
        cost, src = resolve(config_path, workspace_id, marketplace,
                            r["sku"], r["purchase_date"], mode, overrides)
        if cost is None:
            unpriced += 1
            continue
        conn.execute("UPDATE order_lines SET cogs=?, cogs_source=?, cogs_at=? "
                     "WHERE id=?", (cost, src, now, r["id"]))
        priced += 1
    conn.commit()
    return {"priced": priced, "unpriced": unpriced, "already_had_one": skipped,
            "mode": mode}


def set_for_order(config_path, workspace_id, marketplace, order_id, cost,
                  sku=None):
    """Correct one order's cost by hand. That order only, for ever.

    Marked 'manual-order' so nothing later overwrites it, and so the screen can
    show which figures a person stood behind.
    """
    conn = _db.get_db(config_path)
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    args = [None if cost is None else round(float(cost), 4), "manual-order", now,
            workspace_id, marketplace, str(order_id)]
    q = ("UPDATE order_lines SET cogs=?, cogs_source=?, cogs_at=? "
         "WHERE workspace_id=? AND marketplace=? AND order_id=?")
    if sku:
        q += " AND sku=?"
        args.append(str(sku))
    cur = conn.execute(q, args)
    conn.commit()
    return cur.rowcount
