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
        "currency, in_stock, dispatch_days, error, available_qty) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (source_id, check.get("checked_at") or _now(), check.get("status"),
         check.get("price"), check.get("shipping"), check.get("currency"),
         (None if ins is None else (1 if ins else 0)),
         check.get("dispatch_days"), (check.get("error") or "")[:400], qty))
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
              "target_margin_pct", "target_roi_pct")


def save_rule(config_path, workspace_id, marketplace, sku, values):
    """Upsert the account default (sku='') or one SKU's override."""
    conn = _db.get_db(config_path)
    cols = [c for c in _RULE_COLS if c in values]
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
