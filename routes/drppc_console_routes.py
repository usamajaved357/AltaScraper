"""routes/drppc_console_routes.py -- the Dr PPC Console.

    GET  /drppc/console/setup          readiness, rules, classification
    GET  /drppc/console/state          the mirrored Amazon Ads structure
    GET  /drppc/console/state/campaign one campaign's ad groups and keywords
    GET  /drppc/console/plan           the current plan and its revisions
    POST /drppc/console/plan           save a NEW revision (always a draft)
    POST /drppc/console/plan/activate  make one revision the approved strategy
    POST /drppc/console/rule           add a reviewed lane rule
    POST /drppc/console/rule/delete    remove one

Its own file because it is its own feature (CLAUDE.md Rule 7), and separate from
routes/drppc_routes.py, which is the older checker.

NOTHING HERE WRITES TO AMAZON. The console records what this business intends --
its plan, its lane rules, its judgement -- and reads what Amazon has already
said. No bid, no budget, no campaign state (Rule 8); the four POSTs write to
this app's own tables and nowhere else.
"""
from flask import jsonify, request

import domain.request_account as _req_acct


def register(app, *, CONFIG_PATH, _cfg, _state, _active_account):

    def _scope():
        b = request.get_json(silent=True) or {}
        aid = _req_acct.named(request) or str(b.get("account") or "").strip()
        if not aid:
            aid = str((_state or {}).get("active_account_id", "") or "")
        if not aid:
            try:
                aid = str((_active_account() or {}).get("id") or "")
            except Exception:
                aid = ""
        mkt = (request.args.get("marketplace") or b.get("marketplace")
               or _state.get("active_marketplace") or "").upper()
        if aid and (not mkt or mkt == "__ALL__"):
            for a in ((_cfg() or {}).get("accounts") or []):
                if str(a.get("id") or "") == aid:
                    mkt = str(a.get("default_marketplace") or "").upper()
                    if not mkt:
                        ms = [str(m).upper() for m in (a.get("marketplaces") or [])
                              if str(m).upper() != "__ALL__"]
                        mkt = ms[0] if ms else ""
                    break
        return aid, mkt

    def _account(aid):
        for a in ((_cfg() or {}).get("accounts") or []):
            if str(a.get("id") or "") == aid:
                return a
        return {}

    def _need(aid, mkt):
        if aid and mkt:
            return None
        return jsonify({"ok": False, "error": (
            "Open an account and pick a marketplace first — a plan and its "
            "lane rules belong to one advertiser in one marketplace.")}), 400

    def _who():
        try:
            from auth import guard as _g
            u = _g.current_user() or {}
            return str(u.get("email") or u.get("name") or "")
        except Exception:
            return ""

    @app.route("/drppc/console/setup")
    def drppc_console_setup():
        """Everything the Setup + readiness page draws.

        One call: the checks, the rules, what they classify and the evidence
        behind it all read the same window and the same rule set, so the
        coverage figure at the top cannot disagree with the table at the bottom.
        """
        from domain import drppc_console as _dc

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        acc = _account(aid)
        checks = _dc.readiness(CONFIG_PATH, _cfg, acc, mkt)
        cls = _dc.classify(CONFIG_PATH, aid, mkt)
        plan = _dc.plan_current(CONFIG_PATH, aid, mkt)

        # WHAT IS ACTUALLY LEFT TO DO, derived from the checks rather than
        # written out beside them -- a hard-coded list goes stale the moment a
        # check starts passing, and then tells somebody to do something twice.
        todo = []
        for c in checks:
            if c["ok"] or c["key"] == "manual_apply":
                continue
            todo.append({
                "branded_rules": "Add reviewed branded search-term rules.",
                "non_branded_rules": "Add reviewed non-branded search-term rules.",
                "reviewed_campaigns": ("Assign exact reviewed campaign ids to "
                                       "the non_branded lane."),
                "coverage": ("Classify more spend — %s of it is still "
                             "unclassified."
                             % ("%.2f%%" % (100 - (cls["classified_pct"] or 0))
                                if cls["classified_pct"] is not None else "all")),
                "plan": "Approve and activate a Goals + Strategy + Budget plan.",
                "scheduled": ("Start the scheduler so the nightly observation "
                              "runs on its own."),
                "ads_profile": "Connect this account's Advertising login.",
                "search_terms": "Pull or upload a Search Term Report.",
                "campaigns": "Let the advertising sync mirror the campaigns.",
            }.get(c["key"], c["title"]))

        # SECTION 1 -- the workspace panel. Display name, credentials and ads
        # profile are READ-ONLY here and say where they are edited: Settings ->
        # Accounts owns them, and a second editor for one field is how two
        # screens start disagreeing about it (Rule 12).
        blk = dict(acc.get("drppc") or {})
        profile_id, profile_why = "", ""
        try:
            from api import amazon_ads as _ads
            creds = _ads.creds_for(_cfg(), acc)
            gaps = _ads.missing(creds)
            profile_id = "" if gaps else str(creds.get("ads_profile_id") or "")
            profile_why = ("This account has no Advertising login yet — "
                           + ", ".join(g.replace("ads_", "") for g in gaps)
                           + " still needed.") if gaps else ""
        except Exception as e:
            profile_why = str(e)[:160]

        sched = {"running": False, "job": None, "why": ""}
        runs = []
        try:
            from data import scheduler as _sch
            st = _sch.status()
            sched["running"] = bool(st.get("scheduler_running"))
            for j in st.get("jobs") or []:
                if j.get("job_type") == "ads_sync":
                    sched["job"] = j
                    break
            if not st.get("apscheduler_installed"):
                sched["why"] = ("APScheduler is not installed, so nothing runs "
                                "on a timer — the sync runs when a button is "
                                "pressed.")
            runs = _sch.history(job_types=["ads_sync", "sales_sync"],
                                workspace_id=aid, limit=6)
        except Exception as e:
            sched["why"] = str(e)[:160]

        state = _dc.current_state(CONFIG_PATH, aid, mkt)

        return jsonify({
            "ok": True, "account": aid, "marketplace": mkt,
            "account_label": acc.get("label") or aid,
            "workspace": {
                "display_name": acc.get("label") or aid,
                "status": ("active" if profile_id else "not connected"),
                "analysis_profile": blk.get("analysis_profile")
                                    or "Non-branded growth v1",
                "ads_profile": profile_id,
                "ads_profile_why": profile_why,
                "scheduled_observation": bool(blk.get("scheduled_observation")),
                "exclude_legacy": bool(blk.get("exclude_legacy", True)),
                # NOT a stored setting, and not a switch. Manual apply being
                # authorised means a person may press a button; this app cannot
                # write to Amazon at all (Rule 8), so a toggle here would be
                # offering something that does not exist.
                "manual_apply": True,
            },
            # SECTION 4 -- runtime, every line measured rather than asserted.
            "runtime": [
                {"key": "profile", "ok": bool(profile_id),
                 "badge": "Profile resolved" if profile_id else "No profile",
                 "title": "Advertising profile",
                 "note": profile_id or (profile_why or "not connected")},
                {"key": "mirror", "ok": bool(state.get("last_synced")),
                 "badge": "Mirror fresh" if state.get("last_synced")
                          else "Never mirrored",
                 "title": "Campaign mirror",
                 "note": ("last synced " + state["last_synced"])
                         if state.get("last_synced") else "nothing stored yet",
                 "note2": "%d campaigns" % (state["counts"].get("campaigns") or 0)},
                {"key": "rules", "ok": bool(cls["rules_active"]),
                 "badge": "Configured" if cls["rules_active"] else "No rules",
                 "title": "Lane rules",
                 "note": "%d active" % cls["rules_active"]},
                {"key": "plan", "ok": bool(plan and plan.get("status") == "active"),
                 "badge": ("Version confirmed"
                           if plan and plan.get("status") == "active"
                           else "No active revision"),
                 "title": "Plan",
                 "note": (("revision %s" % plan["revision"]) if plan
                          else "nothing written yet")},
                {"key": "writes", "ok": True, "badge": "Read-only",
                 "title": "Amazon writes",
                 "note": "this console never writes to Amazon",
                 "note2": "brand mode: manual apply"},
            ],
            "schedule": sched,
            "runs": runs,
            "checks": checks,
            "todo": todo,
            "classification": dict(
                {k: v for k, v in cls.items() if k != "terms"},
                # How many terms the percentage was worked out over. None, not
                # 0, when there are none: "0 terms" and "no report yet" read the
                # same on screen and mean different things.
                total_terms=(len(cls["terms"]) or None)),
            # The evidence itself, biggest spender first -- the terms worth
            # writing a rule about are the ones at the top.
            "evidence": cls["terms"][:60],
            "rules": _dc.rules(CONFIG_PATH, aid, mkt),
            "campaigns_total": state["counts"].get("campaigns"),
            "plan": ({"revision": plan["revision"], "status": plan["status"],
                      "title": plan.get("title") or ""} if plan else None),
            "lanes": list(_dc.LANES), "matches": list(_dc.MATCHES),
            "evidence_types": list(_dc.EVIDENCE),
        })

    @app.route("/drppc/console/settings", methods=["POST"])
    def drppc_console_settings():
        """Save the console's OWN settings onto the account.

        Only the three fields this console owns: the analysis profile and the
        two policy toggles. The display name, the credentials and the ads
        profile are NOT written here -- Settings -> Accounts owns those, and a
        second editor for one field is how two screens start disagreeing about
        it (Rule 12). This panel shows them and says where they are edited.

        Goes through config/settings.py, which is the single reader and writer
        of config.json.
        """
        from config import settings as _cs

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        b = request.get_json(force=True) or {}
        raw = _cs.read_raw(CONFIG_PATH)
        hit = None
        for a in (raw.get("accounts") or []):
            if str(a.get("id") or "") == aid:
                hit = a
                break
        if hit is None:
            return jsonify({"ok": False,
                            "error": "no account of that id in config"}), 404
        blk = dict(hit.get("drppc") or {})
        if "analysis_profile" in b:
            blk["analysis_profile"] = str(b.get("analysis_profile") or "")[:80]
        for k in ("scheduled_observation", "exclude_legacy"):
            if k in b:
                blk[k] = bool(b.get(k))
        hit["drppc"] = blk
        if not _cs.write_raw(raw, CONFIG_PATH):
            return jsonify({"ok": False,
                            "error": "config.json could not be written"}), 500
        return jsonify({"ok": True, "drppc": blk, "note": (
            "Saved. These decide eligibility only — nothing here runs analysis "
            "or touches Amazon.")})

    @app.route("/drppc/console/state")
    def drppc_console_state():
        """The mirrored Amazon Ads structure, and a straight answer about the rest."""
        from domain import drppc_console as _dc

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        start = (request.args.get("start") or "").strip() or None
        end = (request.args.get("end") or "").strip() or None
        got = _dc.current_state(CONFIG_PATH, aid, mkt, start, end)
        got.update({"ok": True, "account": aid, "marketplace": mkt})
        return jsonify(got)

    @app.route("/drppc/console/state/campaign")
    def drppc_console_campaign():
        from domain import drppc_console as _dc

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        name = (request.args.get("campaign") or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "no campaign named"}), 400
        got = _dc.campaign_detail(CONFIG_PATH, aid, mkt, name)
        got["ok"] = True
        return jsonify(got)

    @app.route("/drppc/console/plan")
    def drppc_console_plan_get():
        from domain import drppc_console as _dc

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        plan = _dc.plan_current(CONFIG_PATH, aid, mkt)
        return jsonify({
            "ok": True, "account": aid, "marketplace": mkt,
            "plan": plan,
            "history": _dc.plan_history(CONFIG_PATH, aid, mkt),
            # The vocabulary the form's dropdowns offer, from the server, so a
            # goal cannot be saved with a scope the evaluator does not know.
            "vocab": {
                "scope": ["brand", "asin", "goal", "strategic_lane",
                          "portfolio", "campaign", "reserve"],
                "operator": ["between", "at_most", "at_least", "exactly"],
                "unit": ["currency", "percent", "number", "rank", "roas"],
                "window": ["not_evaluable", "latest_complete_day",
                           "trailing_7_complete_days", "trailing_14_complete_days",
                           "plan_to_date", "latest_fresh_evidence"],
                "aggregation": ["not_specified", "sum", "recomputed_ratio",
                                "latest_value"],
                "priority": ["critical", "high", "normal", "low"],
                "lane": list(_dc.LANES),
            },
        })

    @app.route("/drppc/console/plan", methods=["POST"])
    def drppc_console_plan_save():
        """Save a NEW revision. Always a draft; never overwrites one.

        A draft is not strategy until it is activated, so saving can never
        change what the analyst is allowed to propose -- which is what makes
        saving safe to do often.
        """
        from domain import drppc_console as _dc

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        b = request.get_json(force=True) or {}
        body = b.get("body")
        if not isinstance(body, dict):
            return jsonify({"ok": False,
                            "error": "the plan body must be an object"}), 400
        got = _dc.plan_save_draft(CONFIG_PATH, aid, mkt, body, _who())
        return jsonify({"ok": True, "note": (
            "Saved as revision %s, a draft. It does not govern anything until "
            "you activate it." % got["revision"]), **got})

    @app.route("/drppc/console/plan/activate", methods=["POST"])
    def drppc_console_plan_activate():
        from domain import drppc_console as _dc

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        b = request.get_json(force=True) or {}
        ok, why = _dc.plan_activate(CONFIG_PATH, aid, mkt, b.get("revision"),
                                    _who())
        if not ok:
            return jsonify({"ok": False, "error": why}), 400
        return jsonify({"ok": True, "note": (
            "Revision %s is now the approved strategy. The one it replaced is "
            "kept, so anything proposed under it can still be explained."
            % b.get("revision"))})

    @app.route("/drppc/console/rule", methods=["POST"])
    def drppc_console_rule_add():
        from domain import drppc_console as _dc

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        b = request.get_json(force=True) or {}
        rid, why = _dc.rule_add(
            CONFIG_PATH, aid, mkt, lane=b.get("lane"),
            evidence=b.get("evidence") or "search_term",
            match_type=b.get("match_type") or "contains",
            pattern=b.get("pattern"), priority=b.get("priority", 100),
            rationale=b.get("rationale") or "", who=_who())
        if why:
            return jsonify({"ok": False, "error": why}), 400
        return jsonify({"ok": True, "id": rid, "note": (
            "Rule saved. It classifies from now on — press refresh to see what "
            "it caught.")})

    @app.route("/drppc/console/rule/delete", methods=["POST"])
    def drppc_console_rule_delete():
        from domain import drppc_console as _dc

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        b = request.get_json(force=True) or {}
        n = _dc.rule_remove(CONFIG_PATH, aid, mkt, b.get("id"))
        if not n:
            return jsonify({"ok": False,
                            "error": "no rule of that id in this account"}), 404
        return jsonify({"ok": True, "deleted": n})
