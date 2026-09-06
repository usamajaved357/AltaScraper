"""domain/drppc_console.py -- the Dr PPC Console's own state.

Three things live here that Amazon has no opinion about: the plan the operator
writes, the rules that decide which lane a search term belongs to, and whether
the account is ready for either to be acted on. All of it is this business's own
judgement, which is why none of it can be derived and all of it has to be kept.

A PLAN IS A CHAIN OF IMMUTABLE REVISIONS.

    "Every save creates an immutable revision. Only an activated revision is
     approved strategy."

Honoured exactly. A plan decides what may be proposed and what a scheduled run
measures against, so a plan that could be edited in place would make last week's
proposal unexplainable -- the thing it was made against would be gone. Saving
writes a NEW revision; activating is a separate act.

READINESS IS MEASURED, NEVER ASSUMED. Every check here asks the database or the
config and reports what it found. A green tick means the evidence exists; it
never means execution is enabled, and nothing in this module can write to
Amazon (CLAUDE.md Rule 8).
"""
import datetime as _dt
import json as _json
import re as _re

from data import db as _db

LANES = ("branded", "non_branded", "unclassified")
MATCHES = ("contains", "exact", "starts_with", "regex")
EVIDENCE = ("search_term", "campaign_id", "ad_group")

DRAFT, ACTIVE, SUPERSEDED = "draft", "active", "superseded"

# The bar the console holds itself to before it will call classification usable.
# Below this, a lane split is a sample rather than a picture -- and the number is
# on screen beside it so it is a stated threshold rather than a hidden one.
CONFIDENCE_BAR = 80.0


def _now():
    return _dt.datetime.now().isoformat(timespec="seconds")


def _term_report(config_path, workspace_id, marketplace):
    """The newest search-term report id, or "" -- and why anything reading
    ppc_search_terms has to know about it.

    That table keeps one row per term PER REPORT, and the API sync names each
    report after the window it covers, so a second sync leaves two overlapping
    reports sitting side by side. Every query here counted or summed across all
    of them: the readiness check reported 1,595 stored terms where 821 were
    real, and a campaign's keyword spend was the sum of the same keyword in two
    reports.

    domain/ppc_view owns the question of which report is current; this asks it
    rather than deciding again (Rule 12).
    """
    try:
        from domain import ppc_view as _pv
        m = _pv.report_meta(config_path, workspace_id, marketplace)
        return (m or {}).get("report_id") or ""
    except Exception:
        return ""


def _f(v, d=0.0):
    try:
        return float(v if v is not None else d)
    except (TypeError, ValueError):
        return d


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


def plan_history(config_path, workspace_id, marketplace, limit=25):
    """Every revision, newest first. The audit trail, not just the current one."""
    conn = _db.get_db(config_path)
    out = []
    for r in conn.execute(
            "SELECT id, revision, status, title, period_start, period_end, "
            "created_at, created_by, activated_at FROM drppc_plans "
            "WHERE workspace_id=? AND COALESCE(marketplace,'')=? "
            "ORDER BY revision DESC LIMIT ?",
            (workspace_id, marketplace or "", int(limit))):
        out.append(dict(r))
    return out


def plan_current(config_path, workspace_id, marketplace):
    """The ACTIVE revision, or the newest draft, or None. -> dict.

    Active wins over a newer draft on purpose: a draft is not strategy until
    somebody says it is, so a half-written revision must not start governing
    what the analyst may propose merely by being newer.
    """
    conn = _db.get_db(config_path)
    row = conn.execute(
        "SELECT * FROM drppc_plans WHERE workspace_id=? "
        "AND COALESCE(marketplace,'')=? AND status=? "
        "ORDER BY revision DESC LIMIT 1",
        (workspace_id, marketplace or "", ACTIVE)).fetchone()
    if not row:
        row = conn.execute(
            "SELECT * FROM drppc_plans WHERE workspace_id=? "
            "AND COALESCE(marketplace,'')=? ORDER BY revision DESC LIMIT 1",
            (workspace_id, marketplace or "")).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["body"] = _json.loads(d.get("body") or "{}")
    except ValueError:
        d["body"] = {}
    return d


def plan_save_draft(config_path, workspace_id, marketplace, body, who=""):
    """Write a NEW revision. Always a draft; never overwrites one. -> dict.

    The revision number is taken inside the write so two saves a second apart
    cannot land on the same number.
    """
    body = body if isinstance(body, dict) else {}
    conn = _db.get_db(config_path)
    row = conn.execute(
        "SELECT COALESCE(MAX(revision),0) r FROM drppc_plans "
        "WHERE workspace_id=? AND COALESCE(marketplace,'')=?",
        (workspace_id, marketplace or "")).fetchone()
    rev = int((row["r"] if row else 0) or 0) + 1
    ident = body.get("identity") or {}
    conn.execute(
        "INSERT INTO drppc_plans (workspace_id, marketplace, revision, status, "
        "title, period_start, period_end, body, created_at, created_by) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (workspace_id, marketplace or "", rev, DRAFT,
         str(ident.get("title") or ""), str(ident.get("period_start") or ""),
         str(ident.get("period_end") or ""), _json.dumps(body), _now(),
         str(who or "")))
    conn.commit()
    return {"revision": rev, "status": DRAFT}


def plan_activate(config_path, workspace_id, marketplace, revision, who=""):
    """Make one revision the approved strategy. -> (ok, why).

    The one that was active becomes SUPERSEDED rather than being deleted: the
    proposals made under it have to remain explainable afterwards, which is the
    entire reason revisions are immutable.
    """
    conn = _db.get_db(config_path)
    row = conn.execute(
        "SELECT id, status FROM drppc_plans WHERE workspace_id=? "
        "AND COALESCE(marketplace,'')=? AND revision=?",
        (workspace_id, marketplace or "", int(revision))).fetchone()
    if not row:
        return False, "there is no revision %s to activate" % revision
    if row["status"] == ACTIVE:
        return False, "revision %s is already the active plan" % revision
    conn.execute(
        "UPDATE drppc_plans SET status=? WHERE workspace_id=? "
        "AND COALESCE(marketplace,'')=? AND status=?",
        (SUPERSEDED, workspace_id, marketplace or "", ACTIVE))
    conn.execute(
        "UPDATE drppc_plans SET status=?, activated_at=? WHERE id=?",
        (ACTIVE, _now(), row["id"]))
    conn.commit()
    return True, ""


# ---------------------------------------------------------------------------
# Lane rules, and what they classify
# ---------------------------------------------------------------------------


def rules(config_path, workspace_id, marketplace, active_only=False):
    """Every rule, in the order they are applied. Priority first, then age."""
    conn = _db.get_db(config_path)
    sql = ("SELECT * FROM drppc_rules WHERE workspace_id=? "
           "AND COALESCE(marketplace,'')=?")
    args = [workspace_id, marketplace or ""]
    if active_only:
        sql += " AND active=1"
    sql += " ORDER BY priority ASC, id ASC"
    return [dict(r) for r in conn.execute(sql, args)]


def rule_add(config_path, workspace_id, marketplace, lane, evidence,
             match_type, pattern, priority=100, rationale="", who=""):
    """Record one reviewed rule. -> (id, why).

    EVERY FIELD IS CHECKED BEFORE IT IS STORED, because a rule with a lane
    nobody recognises would silently classify nothing and look like it was
    working -- the failure that is hardest to notice.
    """
    lane = str(lane or "").strip().lower()
    evidence = str(evidence or "").strip().lower()
    match_type = str(match_type or "").strip().lower()
    pattern = str(pattern or "").strip()
    if lane not in LANES:
        return None, "lane must be one of: %s" % ", ".join(LANES)
    if evidence not in EVIDENCE:
        return None, "evidence must be one of: %s" % ", ".join(EVIDENCE)
    if match_type not in MATCHES:
        return None, "match must be one of: %s" % ", ".join(MATCHES)
    if not pattern:
        return None, "give the rule a pattern to match on"
    if match_type == "regex":
        # A BAD PATTERN IS REFUSED HERE, not at classify time. Stored, it would
        # throw on every run and the run would report nothing classified.
        try:
            _re.compile(pattern)
        except _re.error as e:
            return None, "that is not a valid regular expression: %s" % str(e)[:80]
    try:
        priority = int(priority)
    except (TypeError, ValueError):
        return None, "priority must be a whole number"

    conn = _db.get_db(config_path)
    cur = conn.execute(
        "INSERT INTO drppc_rules (workspace_id, marketplace, lane, evidence, "
        "match_type, pattern, priority, rationale, source, active, created_at, "
        "created_by) VALUES (?,?,?,?,?,?,?,?,?,1,?,?)",
        (workspace_id, marketplace or "", lane, evidence, match_type, pattern,
         priority, str(rationale or ""), "reviewed", _now(), str(who or "")))
    conn.commit()
    return cur.lastrowid, ""


def rule_remove(config_path, workspace_id, marketplace, rule_id):
    conn = _db.get_db(config_path)
    cur = conn.execute(
        "DELETE FROM drppc_rules WHERE workspace_id=? "
        "AND COALESCE(marketplace,'')=? AND id=?",
        (workspace_id, marketplace or "", int(rule_id)))
    conn.commit()
    return cur.rowcount or 0


def _matches(rule, value):
    v = str(value or "").lower()
    p = str(rule.get("pattern") or "").lower()
    m = rule.get("match_type")
    if not v or not p:
        return False
    if m == "exact":
        return v == p
    if m == "starts_with":
        return v.startswith(p)
    if m == "regex":
        try:
            return bool(_re.search(rule.get("pattern") or "", str(value or ""),
                                   _re.I))
        except _re.error:
            return False
    return p in v


def classify(config_path, workspace_id, marketplace, terms=None):
    """Which lane each search term falls in, and by which rule. -> dict.

    EVERY MATCH STAYS VISIBLE. A term can be caught by more than one rule and
    hiding the losers makes a classification impossible to argue with; the
    winner is simply the lowest priority number, and the rest are listed.

    A term no rule matches is UNCLASSIFIED, which is a real answer and not a
    lane. Defaulting it to non-branded would quietly move somebody else's spend
    into the bucket that carries the growth mandate.
    """
    from domain import ppc_view as _pv

    rows = terms
    if rows is None:
        try:
            rows = [dict(r) for r in
                    _pv.load_rows(config_path, workspace_id, marketplace)]
        except Exception:
            rows = []

    rs = [r for r in rules(config_path, workspace_id, marketplace,
                           active_only=True)
          if r.get("evidence") == "search_term"]

    out, by_lane = [], {k: {"spend": 0.0, "terms": 0} for k in LANES}
    total_spend = 0.0
    for t in rows or []:
        term = t.get("search_term") or ""
        spend = _f(t.get("spend"))
        total_spend += spend
        hits = [r for r in rs if _matches(r, term)]
        winner = hits[0] if hits else None
        lane = winner["lane"] if winner else "unclassified"
        by_lane.setdefault(lane, {"spend": 0.0, "terms": 0})
        by_lane[lane]["spend"] += spend
        by_lane[lane]["terms"] += 1
        out.append({
            "search_term": term,
            "lane": lane,
            "matched_rule": (winner["id"] if winner else None),
            "matched_pattern": (winner["pattern"] if winner else ""),
            "other_matches": [r["id"] for r in hits[1:]],
            "spend": round(spend, 2),
            "sales": round(_f(t.get("sales")), 2),
            "orders": int(_f(t.get("orders"))),
            "clicks": int(_f(t.get("clicks"))),
        })

    for v in by_lane.values():
        v["spend"] = round(v["spend"], 2)
    classified = round(total_spend - by_lane["unclassified"]["spend"], 2)
    pct = (round(100.0 * classified / total_spend, 2) if total_spend else None)
    out.sort(key=lambda x: -x["spend"])
    return {
        "terms": out,
        "by_lane": by_lane,
        "total_spend": round(total_spend, 2),
        "classified_spend": classified,
        "unclassified_spend": by_lane["unclassified"]["spend"],
        # None, not 0, when there are no terms at all: nothing to classify is
        # not the same as classifying nothing.
        "classified_pct": pct,
        "confidence_bar": CONFIDENCE_BAR,
        "above_bar": (pct is not None and pct >= CONFIDENCE_BAR),
        "rules_active": len(rs),
    }


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


def readiness(config_path, cfg, account, marketplace):
    """The ten checks the Setup page draws. Every one measured. -> list.

    A tick means the evidence or the configuration EXISTS. It never means
    execution is enabled -- nothing in this console can write to Amazon -- and
    the wording says so rather than leaving it to be assumed.
    """
    wsid = str((account or {}).get("id") or "")
    conn = _db.get_db(config_path)

    def n(sql, args):
        try:
            return int(conn.execute(sql, args).fetchone()[0] or 0)
        except Exception:
            return 0

    # 1. Does an advertising profile exist for this account?
    profile, why_profile = "", ""
    try:
        from api import amazon_ads as _ads
        creds = _ads.creds_for(cfg() if callable(cfg) else cfg, account)
        gaps = _ads.missing(creds)
        profile = "" if gaps else str(creds.get("ads_profile_id") or "")
        why_profile = ("still needed: "
                       + ", ".join(g.replace("ads_", "") for g in gaps)
                       ) if gaps else ("profile " + profile)
    except Exception as e:
        why_profile = str(e)[:120]

    rs = rules(config_path, wsid, marketplace, active_only=True)
    branded = [r for r in rs if r["lane"] == "branded"]
    non_branded = [r for r in rs if r["lane"] == "non_branded"]
    exact_campaigns = [r for r in rs if r["evidence"] == "campaign_id"]

    cls = classify(config_path, wsid, marketplace)
    plan = plan_current(config_path, wsid, marketplace)
    plan_active = bool(plan and plan.get("status") == ACTIVE)

    # The CURRENT report's terms, not every report ever stored -- see
    # _term_report. This read 1,595 where 821 were real.
    _rid = _term_report(config_path, wsid, marketplace)
    terms_n = n("SELECT COUNT(*) FROM ppc_search_terms WHERE workspace_id=? "
                "AND marketplace=? AND report_id=?",
                (wsid, marketplace, _rid)) if _rid else 0
    camps_n = n("SELECT COUNT(DISTINCT campaign_id) FROM ads_campaign_daily "
                "WHERE workspace_id=? AND marketplace=?", (wsid, marketplace))

    # Is the nightly observation actually scheduled and running?
    sched_ok, sched_why = False, "the ads sync has never run"
    try:
        from data import scheduler as _sch
        st = _sch.status()
        for j in st.get("jobs") or []:
            if j.get("job_type") == "ads_sync":
                sched_ok = (j.get("status") == "ok")
                sched_why = ("last ran %s (%s)"
                             % (j.get("last_run") or "never", j.get("status")))
                break
        if not st.get("scheduler_running"):
            sched_why += " — the scheduler is not running"
            sched_ok = False
    except Exception as e:
        sched_why = str(e)[:120]

    return [
        {"key": "ads_profile", "title": "Ads profile",
         "ok": bool(profile), "note": why_profile},
        {"key": "search_terms", "title": "Search-term evidence",
         "ok": bool(terms_n), "note": ("%d terms stored" % terms_n) if terms_n
                                      else "no report stored yet"},
        {"key": "campaigns", "title": "Campaign mirror",
         "ok": bool(camps_n), "note": ("%d campaigns" % camps_n) if camps_n
                                      else "nothing mirrored yet"},
        {"key": "branded_rules", "title": "Branded rules",
         "ok": bool(branded), "note": "%d active" % len(branded)},
        {"key": "non_branded_rules", "title": "Non-branded rules",
         "ok": bool(non_branded), "note": "%d active" % len(non_branded)},
        {"key": "reviewed_campaigns", "title": "Reviewed campaigns",
         "ok": bool(exact_campaigns),
         "note": "%d exact assignments" % len(exact_campaigns)},
        {"key": "coverage", "title": "Classification coverage",
         "ok": bool(cls["above_bar"]),
         "note": ("%.2f%% of spend classified"
                  % (cls["classified_pct"] or 0.0)) if cls["classified_pct"]
                 is not None else "nothing to classify yet"},
        {"key": "plan", "title": "Active plan",
         "ok": plan_active,
         "note": (("revision %s, active" % plan["revision"]) if plan_active
                  else ("revision %s is still a draft" % plan["revision"]
                        if plan else "no plan written yet"))},
        {"key": "scheduled", "title": "Scheduled observation",
         "ok": sched_ok, "note": sched_why},
        # LAST, AND DELIBERATELY NOT A TICK FOR EXECUTION. Manual apply being
        # authorised says a person may press a button; it does not say this app
        # can write to Amazon, and it cannot (Rule 8).
        {"key": "manual_apply", "title": "Manual apply",
         "ok": True, "highlight": True,
         "note": "authorised, and still gated — nothing here writes to Amazon"},
    ]


# ---------------------------------------------------------------------------
# Current state -- the mirror, and what is honestly in it
# ---------------------------------------------------------------------------

# What the Current-state page wants, against what this app actually mirrors.
# The spec lists eight entity counts; four of them have a store behind them and
# four do not, and saying which is which is the difference between a screen that
# reports nought and a screen that explains nought.
_MIRRORED = {
    "campaigns": "ads_campaign_daily",
    "ad_groups": "ppc_search_terms",
    "product_ads": "ads_daily",
    "keywords": "ppc_search_terms",
}
_NOT_MIRRORED = {
    "targets": ("Product and audience targets are their own Amazon entity and "
                "this app has never pulled them — the Search Term Report shows "
                "where a target FIRED, not the target itself."),
    "negative_keywords": ("Negatives are a separate Amazon endpoint. Nothing "
                          "here reads them, so a count would be a guess and "
                          "nought would read as 'you have none'."),
    "negative_targets": ("Same as negatives: a separate endpoint nobody has "
                         "asked for yet."),
    "portfolios": ("Portfolios are a separate endpoint. Campaigns carry no "
                   "portfolio id in anything stored here."),
}


def current_state(config_path, workspace_id, marketplace, start=None, end=None):
    """The mirrored Amazon Ads structure, and a straight answer about the rest.

    WHAT IS REAL HERE comes from two stores that were filled for other reasons:
    ads_campaign_daily carries every campaign with its status and budget, and
    ppc_search_terms carries the ad group, the keyword and the match type of
    everything that actually fired. Between them that is four of the eight
    counts the page asks for, and the campaign table in full.

    THE OTHER FOUR ARE NOT STORED and are reported as unknown with the reason.
    A zero there would say "this account has no negative keywords", which for an
    account with 254 campaigns is a claim, and a false one.
    """
    conn = _db.get_db(config_path)

    def q(sql, args):
        try:
            return conn.execute(sql, args).fetchone()
        except Exception:
            return None

    where, args = "WHERE workspace_id=? AND marketplace=?", [workspace_id,
                                                             marketplace]
    if start and end:
        where += " AND date>=? AND date<=?"
        args += [start, end]

    counts = {}
    r = q("SELECT COUNT(DISTINCT campaign_id) n FROM ads_campaign_daily " + where,
          args)
    counts["campaigns"] = int((r["n"] if r else 0) or 0)
    r = q("SELECT COUNT(DISTINCT asin) n FROM ads_daily " + where
          + " AND asin<>'*'", args)
    counts["product_ads"] = int((r["n"] if r else 0) or 0)
    # Scoped to the current report. DISTINCT hides most of the damage here, but
    # not all of it: an ad group that existed only in a superseded report would
    # still be counted as one this account has.
    rid = _term_report(config_path, workspace_id, marketplace)
    r = q("SELECT COUNT(DISTINCT ad_group) n FROM ppc_search_terms "
          "WHERE workspace_id=? AND marketplace=? AND report_id=? "
          "AND COALESCE(ad_group,'') <> ''", [workspace_id, marketplace, rid])
    counts["ad_groups"] = int((r["n"] if r else 0) or 0)
    r = q("SELECT COUNT(DISTINCT keyword) n FROM ppc_search_terms "
          "WHERE workspace_id=? AND marketplace=? AND report_id=? "
          "AND COALESCE(keyword,'') <> ''", [workspace_id, marketplace, rid])
    counts["keywords"] = int((r["n"] if r else 0) or 0)
    for k in _NOT_MIRRORED:
        counts[k] = None

    # The campaigns themselves, with the child counts that CAN be derived.
    kw_by_campaign, ag_by_campaign = {}, {}
    try:
        for row in conn.execute(
                "SELECT campaign, COUNT(DISTINCT keyword) k, "
                "COUNT(DISTINCT ad_group) g FROM ppc_search_terms "
                "WHERE workspace_id=? AND marketplace=? AND report_id=? "
                "GROUP BY campaign", (workspace_id, marketplace, rid)):
            kw_by_campaign[row["campaign"]] = int(row["k"] or 0)
            ag_by_campaign[row["campaign"]] = int(row["g"] or 0)
    except Exception:
        pass

    camps = []
    for row in conn.execute(
            "SELECT campaign_id, MAX(campaign_name) name, MAX(status) status, "
            "MAX(budget) budget, MAX(ad_product) ad_product, "
            "MIN(date) first_seen, MAX(date) last_seen, "
            "ROUND(SUM(spend),2) spend "
            "FROM ads_campaign_daily " + where + " GROUP BY campaign_id",
            args):
        d = dict(row)
        nm = d.get("name") or ""
        d["ad_groups"] = ag_by_campaign.get(nm)
        d["keywords"] = kw_by_campaign.get(nm)
        # NOT ZERO. These are the entities nothing mirrors; a nought beside a
        # real campaign would be read as a fact about it.
        d["targets"] = None
        d["negatives"] = None
        d["product_ads"] = None
        camps.append(d)
    camps.sort(key=lambda x: -(_f(x.get("spend"))))

    last = q("SELECT MAX(fetched_at) t FROM ads_campaign_daily "
             "WHERE workspace_id=? AND marketplace=?",
             [workspace_id, marketplace])
    return {
        "counts": counts,
        "not_mirrored": _NOT_MIRRORED,
        "campaigns": camps,
        "last_synced": (last["t"] if last else "") or "",
        "why": ("Four of the eight entity counts have a store behind them in "
                "this app. The other four are separate Amazon endpoints nobody "
                "has pulled yet, and are shown as unknown rather than as nought "
                "— a zero beside 254 live campaigns would be a claim, and a "
                "false one."),
    }


def campaign_detail(config_path, workspace_id, marketplace, campaign_name):
    """One campaign's ad groups, keywords and the terms they caught.

    Built from the Search Term Report, which is what this app has. That report
    shows what FIRED, so a keyword with no impressions in the window does not
    appear -- said on the screen, because "this campaign has one keyword" and
    "one of its keywords got a click" are different statements.
    """
    conn = _db.get_db(config_path)
    groups = {}
    try:
        for r in conn.execute(
                "SELECT ad_group, keyword, match_type, "
                "  ROUND(SUM(spend),2) spend, SUM(clicks) clicks, "
                "  ROUND(SUM(sales),2) sales, SUM(orders) orders "
                # SUMS, so this one genuinely doubled: the same keyword appears
                # in every stored report and they were added together.
                "FROM ppc_search_terms WHERE workspace_id=? AND marketplace=? "
                "AND report_id=? AND campaign=? "
                "GROUP BY ad_group, keyword, match_type ORDER BY spend DESC",
                (workspace_id, marketplace,
                 _term_report(config_path, workspace_id, marketplace),
                 campaign_name)):
            g = groups.setdefault(r["ad_group"] or "(no ad group)",
                                  {"name": r["ad_group"] or "(no ad group)",
                                   "keywords": []})
            g["keywords"].append(dict(r))
    except Exception:
        pass
    return {
        "campaign": campaign_name,
        "ad_groups": list(groups.values()),
        "why": ("From the Search Term Report, so these are the keywords that "
                "actually fired in the report's window. A keyword with no "
                "impressions is not in it — that is not the same as the "
                "campaign not having one."),
    }
