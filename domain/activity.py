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
        conn = _db.get_db(config_path)
        rid = _insert(conn, config_path, action, category=category, ok=ok,
                      workspace_id=workspace_id, marketplace=marketplace,
                      entity_type=entity_type, entity_id=entity_id,
                      entity_count=entity_count, summary=summary, detail=detail,
                      http_status=http_status, method=method, path=path,
                      user_id=user_id, ts=ts)
        conn.commit()
        return rid
    except Exception:
        return None


def record_many(config_path, items, **common):
    """Keep several pieces of work at once (a batch: one row per product), in
    one commit. `items` are record()'s keyword arguments with "action";
    `common` (method, path, ...) applies to each. -> how many were kept."""
    try:
        from data import db as _db
        conn = _db.get_db(config_path)
        n, who = 0, {}
        for it in items:
            it = dict(common, **it)
            if it.get("category") not in CATEGORIES:
                continue
            u = it.get("user_id")
            if u not in who:
                who[u] = actor(config_path, u)
            _insert(conn, config_path, it.pop("action"), who=who[u], **it)
            n += 1
        conn.commit()
        return n
    except Exception:
        return 0


def _insert(conn, config_path, action, *, category, ok=True, workspace_id="", marketplace="",
            entity_type="", entity_id="", entity_count=None, summary="", detail=None,
            http_status=None, method="", path="", user_id=None, ts=None, who=None):
    """One INSERT of record()'s row (no commit). -> the row id. `who` is
    actor()'s answer when the caller already has it (a batch asks once)."""
    uid, label = who or actor(config_path, user_id)
    safe = redact(detail) if detail else None
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
    return cur.lastrowid


# ---- reading --------------------------------------------------------------

def _where(since, until, *, user_id=None, workspaces=None, marketplace=None,
           category=None, ok=None, t=""):
    """SQL WHERE for the filters. `workspaces` None = every account (a viewer
    with "*"); a list = only those accounts, and never a row without one.
    `t` is a table alias with its dot ("a.") for a query that joins the log."""
    w, a = [t + "ts >= ?", t + "ts < ?"], [float(since), float(until)]
    if user_id is not None:
        w.append("COALESCE(" + t + "user_id,'') = ?")
        a.append(str(user_id))
    if workspaces is not None:
        ids = [str(x) for x in workspaces if str(x or "").strip()]
        if not ids:
            w.append("0")
        else:
            w.append(t + "workspace_id IN (%s)" % ",".join("?" * len(ids)))
            a.extend(ids)
    if marketplace:
        w.append(t + "marketplace = ?")
        a.append(str(marketplace).upper())
    if category:
        w.append(t + "category = ?")
        a.append(str(category))
    if ok is not None:
        w.append(t + "ok = ?")
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


# Work that CHANGED A LISTING after it had been sent to Amazon: an edit, a
# price/stock change or a re-push on a SKU the same account had already
# submitted. A fact from the record, not a judgement -- a price change after
# launch is normal work; the count is shown, never scored.
_SENT = ("amazon.submit",)
_CHANGED_AFTER = ("listing.edit", "amazon.push", "amazon.push_optimized")


def _action_label(action):
    """The catalogue's own words for an action ("Edited a listing"), never the
    code. Imported here: domain/activity_catalog imports this module."""
    try:
        from domain import activity_catalog as _cat
        for e in _cat.CATALOG:
            if e[4] == action:
                return e[5]
        for modes in _cat._BODY_MODES.values():
            for code, phrase in modes.values():
                if code == action:
                    return phrase
    except Exception:
        pass
    return action


def breakdown(config_path, since, until, *, tz_minutes=0, **filters):
    """The shapes the overview draws, from the same rows summary() counts.

    days    [{day, actions, failed, people}] -- `day` in the VIEWER's calendar
            (tz_minutes = JS getTimezoneOffset(), minutes WEST of UTC)
    by_day  {user_id: {day: actions}}
    places  [{workspace_id, marketplace, actions, failed}]
    actions [{category, action, actions, failed, last_error}]  -- busiest first
    after_sent {edits, skus} -- see _CHANGED_AFTER
    """
    from data import db as _db
    where, args = _where(since, until, **filters)
    shift = -float(tz_minutes or 0) * 60.0          # local = utc - offset
    conn = _db.get_db(config_path)
    day = "strftime('%Y-%m-%d', ts + ?, 'unixepoch')"
    days, by_day = {}, {}
    for r in conn.execute(
            "SELECT " + day + " AS d, COALESCE(user_id,'') AS uid, COUNT(*) AS n, "
            "SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END) AS failed "
            "FROM activity_log WHERE " + where + " GROUP BY d, uid", [shift] + args):
        d = days.setdefault(r["d"], {"day": r["d"], "actions": 0, "failed": 0, "people": 0})
        d["actions"] += int(r["n"] or 0)
        d["failed"] += int(r["failed"] or 0)
        d["people"] += 1
        by_day.setdefault(r["uid"], {})[r["d"]] = int(r["n"] or 0)
    places = [{"workspace_id": r["w"], "marketplace": r["m"], "actions": int(r["n"] or 0),
               "failed": int(r["f"] or 0)} for r in conn.execute(
        "SELECT COALESCE(workspace_id,'') AS w, COALESCE(marketplace,'') AS m, COUNT(*) AS n, "
        "SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END) AS f FROM activity_log WHERE " + where +
        " GROUP BY w, m ORDER BY n DESC", args)]
    actions = []
    for r in conn.execute(
            "SELECT category, action, COUNT(*) AS n, "
            "SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END) AS f FROM activity_log WHERE " + where +
            " GROUP BY category, action ORDER BY n DESC LIMIT 40", args):
        a = {"category": r["category"], "action": r["action"], "label": _action_label(r["action"]),
             "actions": int(r["n"] or 0), "failed": int(r["f"] or 0), "last_error": ""}
        if a["failed"]:
            e = conn.execute(
                "SELECT summary, detail FROM activity_log WHERE " + where +
                " AND action = ? AND ok = 0 ORDER BY ts DESC, id DESC LIMIT 1",
                args + [r["action"]]).fetchone()
            if e:
                try:
                    det = json.loads(e["detail"] or "null") or {}
                except Exception:
                    det = {}
                a["last_error"] = str(det.get("error") or ("refused" if det.get("refused") else "")
                                      or e["summary"] or "")[:200]
        actions.append(a)
    # Changed after it was sent: the change is in the period; the submit may be
    # any time before it, in the same account, on the same SKU.
    ph_c = ",".join("?" * len(_CHANGED_AFTER))
    ph_s = ",".join("?" * len(_SENT))
    wa, aa = _where(since, until, t="a.", **filters)
    ca = conn.execute(
        "SELECT COUNT(*) AS n, COUNT(DISTINCT a.workspace_id || '|' || a.entity_id) AS k "
        "FROM activity_log a WHERE " + wa +
        " AND a.action IN (" + ph_c + ") AND a.ok = 1 AND COALESCE(a.entity_id,'') <> '' "
        "AND EXISTS (SELECT 1 FROM activity_log s WHERE s.action IN (" + ph_s + ") AND s.ok = 1 "
        # A batch submit is one row PER SKU (activity_catalog.rows), so every
        # product it sent is found here by its own entity_id.
        "AND s.entity_id = a.entity_id AND s.workspace_id = a.workspace_id AND s.ts < a.ts)",
        aa + list(_CHANGED_AFTER) + list(_SENT)).fetchone()
    return {"days": sorted(days.values(), key=lambda d: d["day"]),
            "by_day": by_day, "places": places, "actions": actions,
            "after_sent": {"edits": int(ca["n"] or 0), "skus": int(ca["k"] or 0)}}
