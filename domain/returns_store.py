"""domain/returns_store.py -- keep the returns, instead of forgetting them.

WHAT THIS FIXES
routes/returns_routes.py parses a returns report and holds the rows in a
per-workspace dict in MEMORY. That was a deliberate, reasonable choice at the
time -- it stopped the export re-pulling a report and breaching Amazon's
roughly-one-report-a-minute quota. But it means a restart loses everything, the
export answers "load the file again", and there is no way to look at a return
that arrived last month.

Amazon caps the seller-fulfilled returns report at 60 DAYS. Year-to-date is four
or five downloads whose windows overlap. So history is not something the report
can be asked for; it is something that has to be accumulated. That is what this
module is for.

IT DOES NOT PARSE, AND IT DOES NOT DE-DUPLICATE
domain/returns_view.py already does both, and its identity() rule was measured
against a real 11,509-row file -- keying on Amazon's licence plate alone silently
deleted 467 genuine returns, because Amazon recycles them. That rule is asked
for here rather than restated, so the table and the merge cannot drift apart
(CLAUDE.md Rule 12).

THE FIRST VERSION OF A ROW WINS, which is the same rule returns_view.merge()
applies: re-pulling an overlapping window must not silently rewrite history. What
CAN move is Amazon's own state -- a return request that was pending last week and
is closed now -- so status, resolution and the money fields are refreshed while
everything identifying the return is left alone.

READS ONLY FROM AMAZON'S REPORT. Nothing here contacts a buyer, refunds anything
or changes a return. Phase 1 stores and shows; the actions are a separate
decision with their own confirmation.
"""
import datetime as _dt

from data import db as _db
from domain import returns_view as _rv

# Written by the report pull, and by a file the owner uploads. Kept apart so a
# figure can always be traced back to where it came from.
SOURCE_REPORT = "report"
SOURCE_UPLOAD = "upload"

# What Amazon may change about a return after we first saw it. Everything else
# identifies the return and is never overwritten.
_MUTABLE = ("status", "resolution", "refunded", "order_amount",
            "disposition", "comment", "name", "category")


def identity_key(r):
    """The identity tuple, flattened to one string for the unique index."""
    return "|".join(str(x) for x in _rv.identity(r))


def store(config_path, workspace_id, marketplace, returns, source=SOURCE_REPORT):
    """Keep these returns. -> {"stored": n, "added": n, "updated": n}.

    Idempotent: storing the same report twice adds nothing the second time.
    """
    conn = _db.get_db(config_path)
    now = _dt.datetime.now().isoformat(timespec="seconds")
    added = updated = 0
    for r in returns or []:
        key = identity_key(r)
        row = conn.execute(
            "SELECT id FROM returns WHERE workspace_id=? AND marketplace=? "
            "AND identity=?", (workspace_id, marketplace, key)).fetchone()
        if row:
            # Amazon's own state may have moved on. The identifying fields are
            # deliberately not in this list.
            conn.execute(
                "UPDATE returns SET status=?, resolution=?, refunded=?, "
                "order_amount=?, disposition=?, comment=?, name=?, category=?, "
                "fetched_at=? WHERE id=?",
                (r.get("status"), r.get("resolution"), r.get("refunded"),
                 r.get("order_amount"), r.get("disposition"), r.get("comment"),
                 r.get("name"), r.get("category"), now, row["id"]))
            updated += 1
            continue
        conn.execute(
            "INSERT INTO returns (workspace_id, marketplace, identity, kind, "
            "date, order_id, license_plate, asin, sku, name, qty, reason, "
            "reason_raw, nature, status, resolution, refunded, order_amount, "
            "category, disposition, comment, source, first_seen, fetched_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (workspace_id, marketplace, key, r.get("kind"), r.get("date"),
             r.get("order_id"), r.get("license_plate"), r.get("asin"),
             r.get("sku"), r.get("name"), r.get("qty"), r.get("reason"),
             r.get("reason_raw"), r.get("nature"), r.get("status"),
             r.get("resolution"), r.get("refunded"), r.get("order_amount"),
             r.get("category"), r.get("disposition"), r.get("comment"),
             source, now, now))
        added += 1
    conn.commit()
    return {"stored": added + updated, "added": added, "updated": updated}


def _row(r):
    """One stored return, in the SAME shape returns_view.parse_rows produces.

    So everything already written against those rows -- returns_view.summarise,
    returns_intel.build, the workbook -- reads a stored return without knowing
    it came from a table.

    `identity` IS KEPT, and is the only field here that is not the parser's.
    It is how a screen names one return back to the server: a return has no id
    of its own that Amazon guarantees (the licence plate is recycled -- see
    returns_view.identity), so the identity string is the handle. The row's
    database id is dropped because it means nothing outside this machine.
    """
    d = dict(r)
    d.pop("id", None)
    d.pop("workspace_id", None)
    d.pop("marketplace", None)
    return d


def load(config_path, workspace_id, marketplace, start=None, end=None,
         order_id=None, limit=None):
    """Stored returns, newest first. Every filter is optional."""
    conn = _db.get_db(config_path)
    sql = ("SELECT * FROM returns WHERE workspace_id=? AND marketplace=?")
    args = [workspace_id, marketplace]
    if start:
        sql += " AND date>=?"
        args.append(start)
    if end:
        sql += " AND date<=?"
        args.append(end)
    if order_id:
        sql += " AND order_id=?"
        args.append(order_id)
    sql += " ORDER BY date DESC, id DESC"
    if limit:
        sql += " LIMIT %d" % int(limit)
    return [_row(r) for r in conn.execute(sql, args)]


def one(config_path, workspace_id, marketplace, identity):
    """A single stored return by its identity, or None."""
    conn = _db.get_db(config_path)
    r = conn.execute(
        "SELECT * FROM returns WHERE workspace_id=? AND marketplace=? "
        "AND identity=?", (workspace_id, marketplace, identity)).fetchone()
    return _row(r) if r else None


def coverage(config_path, workspace_id, marketplace):
    """What is actually held -- so a screen can say so rather than imply.

    A returns screen showing 40 returns over a period the report only covered
    half of is not wrong, but it is misleading unless it says which half.
    """
    conn = _db.get_db(config_path)
    r = conn.execute(
        "SELECT COUNT(*) n, MIN(date) first_date, MAX(date) last_date, "
        "COUNT(DISTINCT order_id) orders, MAX(fetched_at) fetched_at, "
        "SUM(CASE WHEN kind='fba' THEN 1 ELSE 0 END) fba, "
        "SUM(CASE WHEN kind='mfn' THEN 1 ELSE 0 END) mfn "
        "FROM returns WHERE workspace_id=? AND marketplace=?",
        (workspace_id, marketplace)).fetchone()
    d = dict(r) if r else {}
    d["held"] = bool(d.get("n"))
    return d
