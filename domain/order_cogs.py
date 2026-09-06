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

WHERE A COST COMES FROM -- TWO PLACES, AND BOTH ARE PLACES YOU TYPED IT
  1. a cost typed against THAT ONE ORDER -- always wins, and applies to that
     order alone: "my typed cogs win but it should be only for that order not
     all time frames and all orders"
  2. the cost set against the product, by bulk upload or one SKU at a time
  3. nothing -- and nothing is NOT zero

That is the whole list, by instruction: "lets remove the cogs from sku things
entirely, lets keep it simple". Two things used to sit in this chain and are
gone:

  the cost read out of the SKU -- the number before the first underscore of a
    generated SKU. A guess dressed as data, right only for SKUs this app
    generated itself and impossible for one named by hand, with nothing on any
    screen to tell the two apart. Every value it was supplying was written into
    the product store by migrate_sku_costs.py first, so no figure went blank
    when it went: 18 SKUs covering all 50 costed order lines.

  TRACKED mode -- the supplier price the repricer had recorded before the order
    arrived. A third cost nobody had set. `mode` is still accepted by the
    functions below so no caller breaks, and is ignored.

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

    # TWO SOURCES, IN ORDER, AND NOTHING ELSE.
    #
    #     "if the cogs of the sku are set by the user by bulk upload or one by
    #      one per sku, consider them for profit calculation, if those cogs are
    #      filled and also a person has put in the cogs per order in the all
    #      orders page, consider those cogs for profit calculation"
    #
    #   1. a cost typed against THIS ONE ORDER -- wins, and applies to that
    #      order alone
    #   2. the cost set against the product, by upload or one at a time
    #   3. nothing. Not a guess, not a zero.
    #
    # `mode` is still accepted so every caller keeps working, and is IGNORED.
    # Tracked mode used to sit between the two above, taking the supplier price
    # the repricer happened to have recorded before the order arrived. It was a
    # third cost nobody had set, on an account where all sixteen of its frozen
    # costs turned out to come from the SKU parse anyway.
    if order_override is not None:
        try:
            return round(float(order_override), 4), "manual-order"
        except (TypeError, ValueError):
            pass

    cost, src = _cogs.resolve(overrides or {}, workspace_id, sku)
    if cost is not None:
        return round(float(cost), 4), "manual"
    return None, ""


def frozen_costs(config_path, workspace_id, marketplace=None, order_ids=None):
    """{(order_id, folded SKU): (cost, source)} -- the costs already ON the lines.

    A per-order correction is not held anywhere separate: set_for_order writes it
    straight into order_lines.cogs with source 'manual-order'. So "the cost typed
    against this one order" and "the cost frozen onto this line when it was first
    seen" are the same column, and reading that column is how any screen honours
    the first without re-deriving the second.

    FOLDED, because Amazon spells one SKU two ways -- order_lines holds
    10.99_3Days_B0GGSNN4Q6 and the Finances feed says 10.99_3DAYS_B0GGSNN4Q6.
    Keyed literally, the finance path would miss every per-order cost on an
    account whose feed disagrees with its orders about capitals. Same fold, same
    reason, as cogs_store.norm() -- which is the function used, not a copy of it.

    MARKETPLACE IS OPTIONAL AND DEFAULTS TO ALL. An Amazon order id is unique
    across marketplaces, so leaving it out cannot collide -- and the finance
    path needs it left out, because finances are stored under the account's
    DEFAULT marketplace while an order line carries the one it actually sold in.
    Filtering there would silently find no cost at all.

    order_ids None means EVERY order, which is what a finance pull wants. An
    empty list means NONE, which is what a screen drawing an order it has no id
    for wants -- and the difference matters: read the other way round, asking
    about no orders would load the account's entire history to answer.
    """
    from domain import cogs_store as _cstore
    if order_ids is not None and not len(order_ids):
        return {}
    q = ("SELECT order_id, sku, cogs, cogs_source FROM order_lines "
         "WHERE workspace_id=? AND cogs IS NOT NULL")
    args = [str(workspace_id or "")]
    if marketplace:
        q += " AND marketplace=?"
        args.append(str(marketplace))
    ids = [str(o) for o in (order_ids or []) if str(o or "")]
    if ids:
        q += " AND order_id IN (%s)" % ",".join("?" * len(ids))
        args.extend(ids)
    out = {}
    try:
        for r in _db.get_db(config_path).execute(q, args).fetchall():
            out[(str(r["order_id"] or ""), _cstore.norm(r["sku"]))] = (
                r["cogs"], r["cogs_source"])
    except Exception:
        # Never lose a whole screen, or a whole finance pull, over this read.
        return {}
    return out


def line_cost_fn(config_path, workspace_id, marketplace=None, when=None,
                 mode=None, overrides=None, order_ids=None, frozen=None,
                 default_order_id=""):
    """(sku, order_id) -> (cost, source). THE trust order, for every screen.

    THIS WAS A CLOSURE INSIDE routes/orders_routes.py AND NOWHERE ELSE, so the
    Orders screen honoured a per-order cost and the finance path did not -- the
    same order reporting one profit on Orders and a different one in the Sales
    daily figures, with nothing on either screen to say which was right. Moved
    here so both call it (Rule 12); the route's behaviour is unchanged.

        "yes make the finance path honour per-order costs too same logic should
         exist as for sales bar we prioritize per order costs"

    In order, stopping at the first answer:

      1. THE COST ON THE ORDER LINE. A correction typed against that one order,
         or the cost frozen onto it when it was first seen. Frozen deliberately:
         looked up fresh instead, an order from July picks up August's supplier
         price and last month's profit moves every time a supplier does.
      2. THE COST SET AGAINST THE PRODUCT, by upload or one SKU at a time.
      3. Nothing -- and nothing is NOT zero.

    `when` and `mode` are accepted so callers need not change, and are unused:
    resolve() ignores mode, and `when` only ever fed tracked mode, which is gone.

    `default_order_id` is for a caller built for ONE order, which then asks by
    SKU alone -- the Orders screen does exactly that, a function per order while
    a list is drawn. Without it the returned function would look up the empty
    order id and find none of the frozen costs it had just loaded.
    """
    from domain import cogs as _cogs
    from domain import cogs_store as _cstore
    have = (frozen if frozen is not None
            else frozen_costs(config_path, workspace_id, marketplace, order_ids))

    def _f(sku, order_id=None):
        oid = str(order_id if order_id else default_order_id or "")
        hit = have.get((oid, _cstore.norm(sku)))
        if hit and hit[0] is not None:
            try:
                return round(float(hit[0]), 4), (hit[1] or "frozen")
            except (TypeError, ValueError):
                pass
        try:
            return resolve(config_path, workspace_id, marketplace, sku, when,
                           mode or DEFAULT_MODE, overrides=overrides,
                           order_override=None)
        except Exception:
            # Never lose the whole row over a cost lookup. Falling back keeps
            # the previous answer rather than reporting "no cost", which would
            # read as a product nobody has costed -- a different, wrong finding.
            return _cogs.resolve(overrides or {}, workspace_id, sku)
    return _f


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
