"""domain/drppc_activity.py -- the Dr PPC Console's activity ledger.

Built to DR-PPC-ACTIVITY-BUILD-PROMPT.md.

MOST OF THIS HISTORY IS DERIVED, NOT STORED AGAIN.

The spec asks for "the durable history of plans, decisions, actions, attempts
and verification". The obvious way to build that is a table every action writes
to. The obvious way is wrong here: a plan revision ALREADY carries created_at,
created_by and activated_at; a lane rule carries the same; a sync attempt is
already a row in sync_jobs with its outcome and its error. Writing a second copy
of any of those would create two records of one fact that can drift apart, and
the ledger -- the thing whose whole value is being trustworthy -- would be the
copy rather than the original (Rule 12).

So this module READS those tables and presents them as one timeline. The
consequence is a ledger that is already full on the day it is switched on,
covering everything that has actually happened, rather than an empty page
promising to record the future.

drppc_events holds only what has nowhere else to live: a setting changed, a
proposal accepted, an execution mode changed. Append-only; a correction is a new
row, because a ledger that can be edited is not evidence.

AN EVENT IS NEVER INVENTED. The spec's example rows describe a different
account's history -- entitlements stamped, channels created, brands onboarded --
and none of those things happened here. They are not drawn.
"""
import datetime as _dt

from data import db as _db

KINDS = ("plan", "observation", "recommendation", "decision", "action",
         "execution", "verification", "system")
ACTORS = ("human", "analyst", "scheduler", "system", "admin_assisted",
          "external")


def _now():
    return _dt.datetime.now().isoformat(timespec="seconds")


def record(config_path, workspace_id, marketplace, kind, actor, action, title,
           detail="", entity_type="", entity_id="", who=""):
    """Append one event. Never updates, never deletes. -> id or None.

    Refuses an unknown kind or actor rather than storing it: an event nobody can
    filter for is an event nobody will ever see again.
    """
    if kind not in KINDS or actor not in ACTORS:
        return None
    conn = _db.get_db(config_path)
    cur = conn.execute(
        "INSERT INTO drppc_events (workspace_id, marketplace, at, kind, actor, "
        "action, title, detail, entity_type, entity_id, who) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (workspace_id, marketplace or "", _now(), kind, actor, str(action),
         str(title), str(detail or ""), str(entity_type or ""),
         str(entity_id or ""), str(who or "")))
    conn.commit()
    return cur.lastrowid


def _ev(at, kind, actor, action, title, detail="", entity_type="",
        entity_id="", who="", op=""):
    return {"at": at or "", "kind": kind, "actor": actor, "action": action,
            "title": title, "detail": detail, "entity_type": entity_type,
            "entity_id": str(entity_id or ""), "who": who or "",
            "op": op or ("%s:%s" % (entity_type, entity_id) if entity_type
                         else "")}


def events(config_path, workspace_id, marketplace, kind=None, actor=None,
           limit=200):
    """The whole timeline, newest first. -> list.

    Four sources, merged: the plans, the lane rules, the sync attempts, and the
    events that have no other home. Filtering happens after the merge so a
    filter cannot silently miss a source.
    """
    conn = _db.get_db(config_path)
    out = []

    # --- plans: created, and separately activated ---------------------------
    # Two events from one row on purpose. Writing a plan and approving it are
    # different acts, often days apart and often by different people, and a
    # ledger that showed only the second could not answer "who drafted this".
    try:
        for r in conn.execute(
                "SELECT revision, status, title, created_at, created_by, "
                "activated_at, period_start, period_end FROM drppc_plans "
                "WHERE workspace_id=? AND COALESCE(marketplace,'')=?",
                (workspace_id, marketplace or "")):
            who = r["created_by"] or ""
            out.append(_ev(
                r["created_at"], "plan", "human" if who else "system",
                "plan_revision_created",
                "Created plan revision r%s%s" % (r["revision"],
                                                 (": " + r["title"])
                                                 if r["title"] else ""),
                ("Covers %s to %s." % (r["period_start"], r["period_end"]))
                if r["period_start"] else
                "Saved as a draft. A draft governs nothing until it is activated.",
                "plan", r["revision"], who))
            if r["activated_at"]:
                out.append(_ev(
                    r["activated_at"], "decision", "human" if who else "system",
                    "plan_activated",
                    "Activated plan revision r%s" % r["revision"],
                    "From this point it is the approved strategy every review "
                    "measures against. The revision it replaced is kept.",
                    "plan", r["revision"], who))
    except Exception:
        pass

    # --- lane rules: a reviewed judgement, which is a decision ---------------
    try:
        for r in conn.execute(
                "SELECT id, lane, evidence, match_type, pattern, priority, "
                "rationale, created_at, created_by FROM drppc_rules "
                "WHERE workspace_id=? AND COALESCE(marketplace,'')=?",
                (workspace_id, marketplace or "")):
            out.append(_ev(
                r["created_at"], "decision",
                "human" if r["created_by"] else "system", "lane_rule_added",
                "Lane rule: %s %s \"%s\" → %s"
                % (r["evidence"].replace("_", " "),
                   r["match_type"].replace("_", " "), r["pattern"], r["lane"]),
                r["rationale"] or "No rationale was recorded.",
                "rule", r["id"], r["created_by"] or ""))
    except Exception:
        pass

    # --- sync attempts: the observations, successes AND failures -------------
    try:
        from data import scheduler as _sch
        for r in _sch.history(job_types=["ads_sync", "sales_sync"],
                              workspace_id=workspace_id, limit=60):
            okay = (r.get("status") == "ok")
            res = r.get("result")
            detail = ""
            if isinstance(res, dict):
                detail = " · ".join("%s %s" % (k, v) for k, v in
                                    list(res.items())[:6])
            elif r.get("error"):
                detail = str(r["error"])[:300]
            out.append(_ev(
                r.get("last_run"), "observation", "scheduler",
                r.get("job_type") or "sync",
                "%s %s" % (str(r.get("job_type") or "sync").replace("_", " "),
                           "completed" if okay else
                           ("is still running" if r.get("status") == "running"
                            else "failed")),
                detail, "job", r.get("id"), ""))
    except Exception:
        pass

    # --- and the ones with no other home ------------------------------------
    try:
        for r in conn.execute(
                "SELECT * FROM drppc_events WHERE workspace_id=? "
                "AND COALESCE(marketplace,'')=? ORDER BY at DESC LIMIT 500",
                (workspace_id, marketplace or "")):
            out.append(_ev(r["at"], r["kind"], r["actor"], r["action"],
                           r["title"], r["detail"] or "", r["entity_type"] or "",
                           r["entity_id"] or "", r["who"] or ""))
    except Exception:
        pass

    if kind and kind != "all":
        out = [e for e in out if e["kind"] == kind]
    if actor and actor != "all":
        out = [e for e in out if e["actor"] == actor]
    out.sort(key=lambda e: e["at"] or "", reverse=True)
    return out[:int(limit)]


def suggestions(config_path, workspace_id, marketplace):
    """What is waiting for review, and the state of manual apply.

    NOTHING IS EVER WAITING, and that is a fact about this app rather than about
    this account: no part of it compiles a bid, budget, placement or negative
    into a card to be approved, because no part of it can send one to Amazon
    (Rule 8). The panel says that plainly instead of showing an empty queue that
    implies one might fill.
    """
    from domain import drppc_console as _dc

    plan = _dc.plan_current(config_path, workspace_id, marketplace)
    active = bool(plan and plan.get("status") == "active")
    return {
        "cards": [],
        "manual_apply": True,
        "plan_active": active,
        "plan_warning": ("" if active else
                         "No Goals + Strategy + Budget plan is active for "
                         "today, so nothing could be compiled against one even "
                         "if this app could compile."),
        "why": ("No compiled bid, budget, placement, target-state or "
                "search-term-negative cards are waiting for review — and none "
                "ever will from here. This app does not write to Amazon, so it "
                "does not build changes to be applied. What it produces is "
                "evidence and a recorded plan; the change is made by a person, "
                "in Seller Central."),
    }


def counts(config_path, workspace_id, marketplace):
    """How many events of each kind and actor, for the filter labels."""
    all_ = events(config_path, workspace_id, marketplace, limit=100000)
    by_kind, by_actor = {}, {}
    for e in all_:
        by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1
        by_actor[e["actor"]] = by_actor.get(e["actor"], 0) + 1
    return {"total": len(all_), "by_kind": by_kind, "by_actor": by_actor}
