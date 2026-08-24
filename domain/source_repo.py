"""domain/source_repo.py -- rows in and out of the five sourcing tables.

Nothing here decides anything. It reads and writes, converts SQLite's integers
back into the True/False/None that domain/sourcing.py expects, and merges the
account-level rule with any per-SKU override. Keeping that in one place means
the sweep, the dry run and (later) the screen all see identical rows.

ONE CONVERSION WORTH SPELLING OUT
in_stock is stored as 1 / 0 / NULL and read back as True / False / None. That
NULL is load-bearing: it means "we could not tell", which is a different answer
from "no", and the whole out-of-stock rule turns on the difference. Reading it
with a plain bool() would turn every unknown into a False and start taking
listings out of stock on missing data.
"""
import time

from data import db as _db
# The ONE check vocabulary, same import source_fetch.py uses. Spelling "gone"
# as a literal here would be a second definition of it in a second file.
from domain.sourcing import GONE as _GONE


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _tri(v):
    """SQLite 1/0/NULL -> True/False/None, without flattening the NULL."""
    return None if v is None else bool(v)


# ---- enrolment -------------------------------------------------------------

def enrol(config_path, workspace_id, marketplace, sku, mode="dry_run"):
    """Opt one SKU in. Re-enrolling just updates the mode."""
    conn = _db.get_db(config_path)
    conn.execute(
        "INSERT INTO sourcing_enrolment (workspace_id, marketplace, sku, enrolled, mode, added_at) "
        "VALUES (?,?,?,1,?,?) "
        "ON CONFLICT(workspace_id, marketplace, sku) DO UPDATE SET enrolled=1, mode=excluded.mode",
        (workspace_id, marketplace, sku, mode, _now()))
    conn.commit()


def unenrol(config_path, workspace_id, marketplace, sku):
    """Opt out. The row is kept so the history and its sources survive."""
    conn = _db.get_db(config_path)
    conn.execute("UPDATE sourcing_enrolment SET enrolled=0 "
                 "WHERE workspace_id=? AND marketplace=? AND sku=?",
                 (workspace_id, marketplace, sku))
    conn.commit()


GONE = "gone"
LIVE_OK = "ok"


def set_listing_state(config_path, workspace_id, marketplace, sku, state):
    """Record whether Amazon still has this SKU, and DISARM it if it does not.

    "the template and the repricer is saving the skus which i have deleted
     already, turn off the auto repricing for that sku and give warning to tell
     that this offer is deleted"

    Disarming happens HERE, in the same statement, rather than being left to the
    caller: a SKU marked gone while still armed is a SKU the pricer will go on
    trying to push, and the whole point of the mark is that it cannot be sold.

    The enrolment row is KEPT. Its sources, its history and its rule are worth
    more than the row costs, and deleting them would lose the audit trail for a
    listing that might be relisted tomorrow.
    """
    conn = _db.get_db(config_path)
    if str(state) == GONE:
        conn.execute(
            "UPDATE sourcing_enrolment SET listing_state=?, listing_checked=?, "
            "mode='dry_run' WHERE workspace_id=? AND marketplace=? AND sku=?",
            (GONE, _now(), workspace_id, marketplace, sku))
    else:
        conn.execute(
            "UPDATE sourcing_enrolment SET listing_state=?, listing_checked=? "
            "WHERE workspace_id=? AND marketplace=? AND sku=?",
            (LIVE_OK, _now(), workspace_id, marketplace, sku))
    conn.commit()


def enrolled(config_path, workspace_id=None, marketplace=None):
    """Every enrolled SKU, optionally narrowed to one account/marketplace."""
    conn = _db.get_db(config_path)
    q = "SELECT * FROM sourcing_enrolment WHERE enrolled=1"
    args = []
    if workspace_id:
        q += " AND workspace_id=?"
        args.append(workspace_id)
    if marketplace:
        q += " AND marketplace=?"
        args.append(marketplace)
    return [dict(r) for r in conn.execute(q + " ORDER BY sku", args)]


# ---- sources ---------------------------------------------------------------

def add_source(config_path, workspace_id, marketplace, sku, url,
               kind="ebay", label="", priority=100, shipping_override=None):
    conn = _db.get_db(config_path)
    cur = conn.execute(
        "INSERT INTO sourcing_sources (workspace_id, marketplace, sku, url, kind, "
        "label, priority, enabled, shipping_override, added_at) VALUES (?,?,?,?,?,?,?,1,?,?)",
        (workspace_id, marketplace, sku, url, kind, label or url, priority,
         shipping_override, _now()))
    conn.commit()
    return cur.lastrowid


def ensure_source(config_path, workspace_id, marketplace, sku, url, **kw):
    """add_source, but only if that SKU does not already have that URL.

    -> (source_id, created). add_source INSERTs unconditionally, which is right
    when a person clicks "add a supplier" -- two links to the same shop are their
    business. It is wrong for anything automatic: importing the same eBay seller
    twice would give every SKU a second identical source, then a third, and the
    repricer would fetch each of them on every sweep, paying for the same answer
    over and over and weighting that supplier more heavily each time it ran.

    Matched on the URL exactly. A URL differing only by its ?var= is a DIFFERENT
    variation of the same eBay listing and a genuinely different supplier row --
    see api/ebay.variation_id_from_url.
    """
    u = str(url or "").strip()
    if not u:
        return None, False
    conn = _db.get_db(config_path)
    row = conn.execute(
        "SELECT id FROM sourcing_sources WHERE workspace_id=? AND marketplace=? "
        "AND sku=? AND url=?", (workspace_id, marketplace, sku, u)).fetchone()
    if row:
        return row["id"], False
    return add_source(config_path, workspace_id, marketplace, sku, u, **kw), True


def set_shipping_override(config_path, source_id, cost):
    """The postage this supplier charges, when they do not publish it."""
    conn = _db.get_db(config_path)
    conn.execute("UPDATE sourcing_sources SET shipping_override=? WHERE id=?",
                 (cost, source_id))
    conn.commit()


def set_source_enabled(config_path, source_id, enabled):
    conn = _db.get_db(config_path)
    conn.execute("UPDATE sourcing_sources SET enabled=? WHERE id=?",
                 (1 if enabled else 0, source_id))
    conn.commit()


def remove_source(config_path, source_id):
    conn = _db.get_db(config_path)
    conn.execute("DELETE FROM sourcing_sources WHERE id=?", (source_id,))
    conn.execute("DELETE FROM sourcing_checks WHERE source_id=?", (source_id,))
    conn.commit()


def count_sources(config_path, workspace_id, marketplace):
    """(suppliers, SKUs they are attached to, price readings held).

    All three, because the warning has to say what actually goes. "Delete 55
    suppliers" understates it: 153 price readings go with them, and those cannot
    be re-fetched -- a supplier's price on a day nobody was watching is gone for
    good.

    Separate from clear_sources on purpose: the confirmation names a real number
    BEFORE anything is deleted, and a count produced by the same reader that
    will do the deleting cannot disagree with it.
    """
    conn = _db.get_db(config_path)
    wsid, mkt = str(workspace_id or ""), str(marketplace or "").upper()
    try:
        row = conn.execute(
            "SELECT COUNT(*) n, COUNT(DISTINCT sku) skus FROM sourcing_sources "
            "WHERE workspace_id=? AND marketplace=?", (wsid, mkt)).fetchone()
        checks = conn.execute(
            "SELECT COUNT(*) FROM sourcing_checks WHERE source_id IN ("
            "  SELECT id FROM sourcing_sources WHERE workspace_id=? AND marketplace=?)",
            (wsid, mkt)).fetchone()[0]
        return {"sources": int(row["n"]), "skus": int(row["skus"]),
                "checks": int(checks)}
    except Exception:
        return {"sources": 0, "skus": 0, "checks": 0}


def clear_sources(config_path, workspace_id, marketplace):
    """Delete every supplier link for one account and marketplace.

        "I also want to delete all the suppliers from the repricer ... so i can
         add new suppliers"

    WHAT GOES: the supplier links, and the price readings recorded against them.
    Readings are deleted for the same reason remove_source deletes them for a
    single supplier -- a reading is keyed only by source_id, so once its
    supplier is gone there is no URL and no label to say whose price it was. An
    orphaned row is not history, it is a number nobody can attribute.

    WHAT STAYS, and this is the point of the request: the ENROLMENT and the
    pricing RULES. The SKUs remain tracked and their targets remain set, so a
    fresh supplier sheet works the moment it is uploaded rather than needing
    fifty-five SKUs re-enrolled first.

    SCOPED TO ACCOUNT AND MARKETPLACE. Every workspace's suppliers share this
    table, so a clear that ignored the scope would silently strip another
    account's repricer. A blank account or marketplace deletes NOTHING rather
    than everything -- the safe direction, enforced here rather than trusted to
    each caller.

    Returns what actually went.
    """
    wsid = str(workspace_id or "").strip()
    mkt = str(marketplace or "").strip().upper()
    if not wsid or not mkt:
        return {"sources": 0, "checks": 0}
    conn = _db.get_db(config_path)
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM sourcing_sources WHERE workspace_id=? AND marketplace=?",
        (wsid, mkt))]
    if not ids:
        return {"sources": 0, "checks": 0}
    marks = ",".join("?" for _ in ids)
    checks = conn.execute(
        "SELECT COUNT(*) FROM sourcing_checks WHERE source_id IN (%s)" % marks,
        ids).fetchone()[0]
    conn.execute("DELETE FROM sourcing_checks WHERE source_id IN (%s)" % marks, ids)
    conn.execute("DELETE FROM sourcing_sources WHERE id IN (%s)" % marks, ids)
    conn.commit()
    return {"sources": len(ids), "checks": int(checks)}


def sources_for(config_path, workspace_id, marketplace, sku):
    conn = _db.get_db(config_path)
    return [dict(r) for r in conn.execute(
        "SELECT * FROM sourcing_sources WHERE workspace_id=? AND marketplace=? AND sku=? "
        "ORDER BY priority, id", (workspace_id, marketplace, sku))]


# ---- checks ----------------------------------------------------------------

def record_check(config_path, source_id, check):
    """Store one reading. `check` is the shape domain/sourcing.py consumes."""
    conn = _db.get_db(config_path)
    ins = check.get("in_stock")
    qty = check.get("available_qty")
    try:
        qty = None if qty is None else int(qty)
    except (TypeError, ValueError):
        qty = None
    conn.execute(
        "INSERT INTO sourcing_checks (source_id, checked_at, status, price, shipping, "
        "currency, in_stock, dispatch_days, error, available_qty, "
        # HOW IT GETS HERE AND WHEN. Stored with the reading and not looked up
        # later: a delivery estimate is only true for the day it was made, so it
        # belongs to this check the same way the price does.
        "carrier, postage_text, delivery_min, delivery_max, delivery_postcode, "
        # WHO IS SELLING IT, so a screen can show a name instead of a 120
        # character URL. Stored with the reading like everything else here: a
        # listing can change hands, and the name we show should be the one that
        # was true when the price was read.
        "seller) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (source_id, check.get("checked_at") or _now(), check.get("status"),
         check.get("price"), check.get("shipping"), check.get("currency"),
         (None if ins is None else (1 if ins else 0)),
         check.get("dispatch_days"), (check.get("error") or "")[:400], qty,
         (check.get("carrier") or "")[:80],
         (check.get("postage_text") or "")[:120],
         (check.get("delivery_min") or "")[:10],
         (check.get("delivery_max") or "")[:10],
         (check.get("delivery_postcode") or "")[:12],
         (check.get("seller") or "")[:80]))
    conn.commit()


def _gone_streak(conn, source_id, cap=10):
    """How many of the most recent readings IN A ROW said the listing had ended.

    Capped because the answer is only ever compared against a small number
    (confirm_gone_checks, normally 2) while the check history for a source grows
    by one every sweep, forever.
    """
    n = 0
    for r in conn.execute("SELECT status FROM sourcing_checks WHERE source_id=? "
                          "ORDER BY id DESC LIMIT ?", (source_id, cap)):
        if r["status"] != _GONE:
            break
        n += 1
    return n


def latest_checks(config_path, source_ids):
    """{source_id: check} for the most recent reading of each source given.

    Each check also carries `gone_streak`. domain/sourcing.py refuses to zero a
    listing's quantity on a single 'gone' reading, and a check dict is the only
    thing it is given to decide from -- so the count has to travel WITH the
    reading rather than being looked up there. Only computed when the latest
    reading is 'gone'; for anything else the streak is 0 by definition and the
    query would be wasted.
    """
    if not source_ids:
        return {}
    conn = _db.get_db(config_path)
    marks = ",".join("?" * len(source_ids))
    rows = conn.execute(
        "SELECT * FROM sourcing_checks WHERE id IN ("
        "  SELECT MAX(id) FROM sourcing_checks WHERE source_id IN (%s) GROUP BY source_id"
        ")" % marks, list(source_ids)).fetchall()
    out = {}
    for r in rows:
        d = dict(r)
        d["in_stock"] = _tri(d.get("in_stock"))
        d["gone_streak"] = (_gone_streak(conn, d["source_id"])
                            if d.get("status") == _GONE else 0)
        out[d["source_id"]] = d
    return out


def history(config_path, source_id, limit=50):
    conn = _db.get_db(config_path)
    rows = conn.execute("SELECT * FROM sourcing_checks WHERE source_id=? "
                        "ORDER BY id DESC LIMIT ?", (source_id, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["in_stock"] = _tri(d.get("in_stock"))
        out.append(d)
    return out


def pairs_for(config_path, workspace_id, marketplace, sku):
    """[(source, latest_check_or_None)] -- exactly what sourcing.decide() takes."""
    srcs = sources_for(config_path, workspace_id, marketplace, sku)
    latest = latest_checks(config_path, [s["id"] for s in srcs])
    return [(s, latest.get(s["id"])) for s in srcs]


# ---- rules -----------------------------------------------------------------

_RULE_COLS = ("strategy", "require_in_stock", "max_dispatch_days",
              "handling_buffer_days", "referral_rate", "min_price", "max_price",
              "max_change_pct", "min_change", "stale_after_hours",
              "in_stock_quantity",
              # Read, so an account that set a target before there were two
              # boxes keeps it. Nothing writes these any more.
              "profit_target_kind", "profit_target_pct",
              # The two boxes. Independent, both applied.
              "target_margin_pct", "target_roi_pct",
              # The never-sell-at-break-even floor. Not a target -- see
              # min_roi_pct in domain/sourcing.DEFAULT_RULE.
              "min_roi_pct",
              # THE SELLER'S OWN PER-UNIT COSTS, storable at last.
              #
              # These were listed as deliberately-not-stored, on the reasoning
              # that they came from listing/pricing.py so there was one
              # definition. That held while they were 3.00 / 2.00 / 1.00 for
              # everybody. They are 0.00 now -- "do not add 3 pounds postage and
              # 2 pounds ad cost and 1 pound profit space on your own" -- which
              # leaves the owner with real postage to declare and nowhere to
              # declare it. A default in code and a per-SKU value in the
              # database are not two definitions; the code default is what the
              # database means by NULL.
              "shipping_label", "ads_margin", "min_profit",
              # The market price, held against a target that would lower it.
              "hold_price")

# SETTINGS THAT DELIBERATELY HAVE NO COLUMN, and why. Listed rather than left
# implicit so the check below can tell "not stored on purpose" apart from
# "somebody added a setting and forgot the column" -- which is exactly what
# happened with hold_price: it was accepted by the route, filtered out here, and
# saved as nothing, while the app answered "saved".
_RULE_NOT_STORED = frozenset({
    # Set from the marketplace on every run, never by hand.
    "currency",
    # A safety constant, not a per-SKU preference.
    "confirm_gone_checks",
})


def storable_rule_keys():
    """(storable, unaccounted) -- every DEFAULT_RULE key, sorted into two piles.

    A setting that is neither a column nor explicitly not-stored is a bug waiting
    to be found by a user rather than by a test, so it is reported by name.
    """
    from domain.sourcing import DEFAULT_RULE
    unaccounted = sorted(k for k in DEFAULT_RULE
                         if k not in _RULE_COLS and k not in _RULE_NOT_STORED)
    return sorted(_RULE_COLS), unaccounted


def save_rule(config_path, workspace_id, marketplace, sku, values):
    """Upsert the account default (sku='') or one SKU's override.

    A setting that cannot be stored is REFUSED rather than dropped. It used to be
    filtered out silently: hold_price was accepted by the route, discarded here,
    and the screen said "saved" while the price went on being cut to the target.
    """
    conn = _db.get_db(config_path)
    cols = [c for c in _RULE_COLS if c in values]
    # Only complain about real settings. A stray field from an old client is not
    # worth failing a save over; a known setting with nowhere to go is.
    from domain.sourcing import DEFAULT_RULE
    lost = [k for k in values
            if k in DEFAULT_RULE and k not in _RULE_COLS
            and k not in _RULE_NOT_STORED]
    if lost:
        raise ValueError(
            "these settings have no column in sourcing_rules, so saving them "
            "would silently do nothing: %s. Add them to _RULE_COLS in "
            "domain/source_repo.py and to _ADDED_COLUMNS in data/db.py."
            % ", ".join(sorted(lost)))
    if not cols:
        return
    conn.execute(
        "INSERT INTO sourcing_rules (workspace_id, marketplace, sku, %s) "
        "VALUES (?,?,?,%s) ON CONFLICT(workspace_id, marketplace, sku) DO UPDATE SET %s"
        % (", ".join(cols), ",".join("?" * len(cols)),
           ", ".join("%s=excluded.%s" % (c, c) for c in cols)),
        [workspace_id, marketplace, sku or ""] + [values[c] for c in cols])
    conn.commit()


def rule_for(config_path, workspace_id, marketplace, sku):
    """The account default with any per-SKU override laid over it.

    NULL columns are dropped rather than passed on, so an override row that only
    sets max_price does not silently blank every other setting back to a NULL --
    sourcing.rule_with_defaults would then fill them from DEFAULT_RULE and the
    account's own settings would be lost without anyone touching them.
    """
    conn = _db.get_db(config_path)
    out = {}
    for key in ("", sku):
        r = conn.execute("SELECT * FROM sourcing_rules WHERE workspace_id=? AND "
                         "marketplace=? AND sku=?",
                         (workspace_id, marketplace, key)).fetchone()
        if r:
            out.update({k: v for k, v in dict(r).items()
                        if k in _RULE_COLS and v is not None})
    return out


# ---- the audit log ---------------------------------------------------------

def record_action(config_path, workspace_id, marketplace, sku, decision,
                  current=None, applied=0, at=None):
    """Write one decision down, whether or not anything was pushed.

    `at` exists because the cooldown is measured against this timestamp. Stamping
    it from the wall clock while the decision was made against a supplied `now`
    means the two disagree, and the cooldown then depends on what time of day the
    code happens to run -- which is exactly the kind of thing that works all
    morning and fails after lunch.
    """
    conn = _db.get_db(config_path)
    cur = current or {}
    conn.execute(
        "INSERT INTO sourcing_actions (workspace_id, marketplace, sku, at, action, "
        "source_id, from_price, to_price, from_quantity, to_quantity, from_lead_days, "
        "to_lead_days, reason, blocked_by, applied, inputs_age_mins) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (workspace_id, marketplace, sku, (at or _now()), decision.get("action"),
         decision.get("source_id"), cur.get("price"), decision.get("price"),
         cur.get("quantity"), decision.get("quantity"), cur.get("lead_days"),
         decision.get("lead_days"), (decision.get("reason") or "")[:1000],
         (decision.get("blocked_by") or "")[:400], applied,
         decision.get("inputs_age_mins")))
    conn.commit()


def recent_actions(config_path, workspace_id=None, marketplace=None, sku=None, limit=200):
    conn = _db.get_db(config_path)
    q = "SELECT * FROM sourcing_actions WHERE 1=1"
    args = []
    for col, val in (("workspace_id", workspace_id), ("marketplace", marketplace),
                     ("sku", sku)):
        if val:
            q += " AND %s=?" % col
            args.append(val)
    return [dict(r) for r in conn.execute(q + " ORDER BY id DESC LIMIT ?",
                                          args + [limit])]
