"""domain/activity.py -- the one record of who did what (Employee Performance).

    "As an owner/manager, show me what meaningful work each employee did today
     or during another selected period."
    "Do NOT create separate tracking systems for each feature."
    "Do not invent a performance score. Record objective work/activity evidence."
                                            (owner, roadmap 29 Sep 2026)

ONE SERVICE, ONE TABLE (activity_log, data/db.py). Every meaningful business
action -- a draft created, a listing edited, images generated, a file uploaded,
a price, stock or tracking change, a PPC or repricer action -- becomes one row:
who, when, which account and marketplace, what kind of work, on what, whether it
worked, and a short sentence. Reads and plain clicks are never recorded.

This module is the ONLY writer and reader. Feature code does not keep its own
"who did it" column for this purpose; it is recorded here (see catalogue.py
beside it for the request-level catalogue).

NEVER FATAL. Recording happens around real work; a database hiccup must never
turn a successful action into an error. record() returns None when it could not
record, and the action's own answer stands.

NEVER A SECRET. `detail` passes through redact(): any key that looks like a
password, key, token, secret, credential, cookie or session is dropped outright
(not masked -- a masked value still tells you its length), strings are cut
short, and lists become a count plus a few ids.

WHO. The signed-in user's id (domain/job_owner.current()) and their name or
email AT THE TIME, so a row still says who did it after that person is deleted.
In a request with no user id it is the shared-password owner; outside a request
(a background job) it is the system unless the caller passes the job's owner.
"""
import json
import re
import time

# The kinds of work, in the order the screen shows them. The key is stored.
CATEGORIES = {
    "listings":  "Listings and drafts",
    "images":    "Images",
    "files":     "Files uploaded",
    "amazon":    "Sent to Amazon",
    "pricing":   "Price, stock and handling",
    "repricer":  "Repricer and suppliers",
    "ppc":       "PPC",
    "orders":    "Orders and tracking",
    "costs":     "Costs (COGS, charges, expenses)",
    "inventory": "Inventory",
    "team":      "Team and accounts",
}

SHARED_OWNER_LABEL = "Owner (shared password)"
SYSTEM_LABEL = "System"
SYSTEM_ID = "@system"          # background work; never a real user id ("u_...")

# A key whose NAME says it may hold a secret is dropped with its value.
_SECRET_KEY = re.compile(
    # "key" only as a whole word or a suffix (api_key, secret_key): "keywords"
    # is PPC work, not a secret.
    r"pass(word|wd)?|secret|token|api[_-]?key|(^|_)key$|credential|cookie|"
    r"session|auth|refresh|bearer|signature|private|lwa|client_id", re.I)
MAX_STR = 200
MAX_LIST_IDS = 20
MAX_DEPTH = 3


def _is_secret_key(k):
    return bool(_SECRET_KEY.search(str(k or "")))


def redact(value, _depth=0):
    """A copy of `value` that is safe to store: no secret-named keys, short
    strings, lists cut to a count and a few items, nothing deeper than 3 levels."""
    if _depth > MAX_DEPTH:
        return "…"
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _is_secret_key(k):
                continue
            out[str(k)[:60]] = redact(v, _depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if len(items) <= MAX_LIST_IDS:
            return [redact(v, _depth + 1) for v in items]
        return {"count": len(items),
                "first": [redact(v, _depth + 1) for v in items[:MAX_LIST_IDS]]}
    if isinstance(value, (bytes, bytearray)):
        return "<%d bytes>" % len(value)
    if isinstance(value, str):
        # A data URL or a long blob is file content, not evidence.
        if value.startswith("data:"):
            return "<file>"
        return value if len(value) <= MAX_STR else value[:MAX_STR] + "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact(str(value), _depth)


def person(config_path, uid):
    """{"id", "label"} for a user id: their name, else email, else the id.
    Through job_owner.person, the one lookup every "who" label uses."""
    from domain import job_owner as _jo
    p = _jo.person(config_path, uid)
    if not p:
        return {"id": str(uid or ""), "label": ""}
    return {"id": p["id"], "label": p["name"] or p["email"] or p["id"]}


def actor(config_path, user_id=None):
    """(user_id, label) for the person doing the work now.

    user_id None -> the signed-in user (job_owner.current()). No id inside a
    request is the shared-password owner (id ""); outside any request it is the
    system (id SYSTEM_ID), so the two are never counted as one person."""
    try:
        from domain import job_owner as _jo
        uid = _jo.current() if user_id is None else str(user_id or "")
        if not uid:
            try:
                from flask import has_request_context
                in_request = has_request_context()
            except Exception:
                in_request = False
            if in_request and user_id is None:
                return "", SHARED_OWNER_LABEL
            return SYSTEM_ID, SYSTEM_LABEL
        return uid, person(config_path, uid)["label"] or uid
    except Exception:
        return SYSTEM_ID, SYSTEM_LABEL


def record(config_path, action, *, category, ok=True, workspace_id="", marketplace="",
           entity_type="", entity_id="", entity_count=None, summary="", detail=None,
           http_status=None, method="", path="", user_id=None, ts=None):
    """Keep one piece of work. -> the row id, or None if it could not be kept."""
    try:
        if category not in CATEGORIES:
            return None
        from data import db as _db
        uid, label = actor(config_path, user_id)
        safe = redact(detail) if detail else None
        conn = _db.get_db(config_path)
        cur = conn.execute(
            "INSERT INTO activity_log (ts, user_id, user_label, workspace_id, marketplace, "
            "category, action, entity_type, entity_id, entity_count, summary, ok, "
            "http_status, detail, method, path) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (float(ts if ts is not None else time.time()), uid, label,
             str(workspace_id or "")[:80], str(marketplace or "").upper()[:10],
             category, str(action or "")[:60], str(entity_type or "")[:30],
             str(entity_id or "")[:200],
             int(entity_count) if entity_count is not None else None,
             str(summary or "")[:400], 1 if ok else 0,
             int(http_status) if http_status is not None else None,
             json.dumps(safe, ensure_ascii=False, default=str) if safe else None,
             str(method or "")[:8], str(path or "")[:200]))
        rid = cur.lastrowid
        conn.commit()
        return rid
    except Exception:
        return None


# ---- reading --------------------------------------------------------------

def _where(since, until, *, user_id=None, workspaces=None, marketplace=None,
           category=None, ok=None):
    """SQL WHERE for the filters. `workspaces` None = every account (a viewer
    with "*"); a list = only those accounts, and never a row without one."""
    w, a = ["ts >= ?", "ts < ?"], [float(since), float(until)]
    if user_id is not None:
        w.append("COALESCE(user_id,'') = ?")
        a.append(str(user_id))
    if workspaces is not None:
        ids = [str(x) for x in workspaces if str(x or "").strip()]
        if not ids:
            w.append("0")
        else:
            w.append("workspace_id IN (%s)" % ",".join("?" * len(ids)))
            a.extend(ids)
    if marketplace:
        w.append("marketplace = ?")
        a.append(str(marketplace).upper())
    if category:
        w.append("category = ?")
        a.append(str(category))
    if ok is not None:
        w.append("ok = ?")
        a.append(1 if ok else 0)
    return " AND ".join(w), a


def _row(r):
    d = dict(r)
    try:
        d["detail"] = json.loads(d.get("detail") or "null")
    except Exception:
        d["detail"] = None
    d["ok"] = bool(d.get("ok"))
    return d


def entries(config_path, since, until, *, limit=200, offset=0, **filters):
    """The rows in [since, until), newest first."""
    from data import db as _db
    where, args = _where(since, until, **filters)
    conn = _db.get_db(config_path)
    rows = conn.execute(
        "SELECT id, ts, user_id, user_label, workspace_id, marketplace, category, action, "
        "entity_type, entity_id, entity_count, summary, ok, http_status, detail "
        "FROM activity_log WHERE " + where + " ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?",
        args + [max(1, min(int(limit or 200), 1000)), max(0, int(offset or 0))]).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM activity_log WHERE " + where, args).fetchone()[0]
    return {"rows": [_row(r) for r in rows], "total": int(total)}


def summary(config_path, since, until, **filters):
    """Per person: how many actions of each kind, how many failed, first and last.

    Objective counts only -- there is no score, by the owner's instruction."""
    from data import db as _db
    where, args = _where(since, until, **filters)
    conn = _db.get_db(config_path)
    rows = conn.execute(
        "SELECT COALESCE(user_id,'') AS uid, category, "
        "COUNT(*) AS n, SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END) AS failed, "
        "SUM(COALESCE(entity_count, 1)) AS items, MIN(ts) AS first_ts, MAX(ts) AS last_ts, "
        "'' AS label "
        "FROM activity_log WHERE " + where + " GROUP BY uid, category", args).fetchall()
    people = {}
    for r in rows:
        p = people.setdefault(r["uid"], {
            "user_id": r["uid"], "label": r["label"] or "", "total": 0, "failed": 0,
            "items": 0, "by_category": {}, "first_ts": r["first_ts"], "last_ts": r["last_ts"]})
        p["total"] += int(r["n"] or 0)
        p["failed"] += int(r["failed"] or 0)
        p["items"] += int(r["items"] or 0)
        p["by_category"][r["category"]] = {"actions": int(r["n"] or 0),
                                           "failed": int(r["failed"] or 0),
                                           "items": int(r["items"] or 0)}
        p["first_ts"] = min(p["first_ts"], r["first_ts"])
        p["last_ts"] = max(p["last_ts"], r["last_ts"])
    # The name as of their LATEST action (after a rename), not MAX() of names.
    for uid, p in people.items():
        row = conn.execute("SELECT user_label FROM activity_log WHERE COALESCE(user_id,'') = ? "
                           "ORDER BY ts DESC, id DESC LIMIT 1", (uid,)).fetchone()
        if row and row[0]:
            p["label"] = row[0]
    return sorted(people.values(), key=lambda p: (-p["total"], p["label"]))
