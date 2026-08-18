"""routes/sqp_routes.py -- Keywords (Search Query Performance).

    GET /sqp   the queries for one account and week, with the funnel diagnosed

ONE ENDPOINT. The arithmetic and the diagnosis are in domain/search_query.py and
take rows rather than a connection, so they can be tested exhaustively without
Amazon. This file asks for the report and hands it over.

A REFUSAL IS NOT AN EMPTY WEEK. This report needs Brand Registry. An account
without it gets a permission error from Amazon, and an account with it that
simply had no searches gets an empty report -- those look identical on a screen
and only one of them is worth doing anything about. The error is caught and
named, because "no keywords this week" for a brand-registered account is a
finding, and for an unregistered one it is a lie.

REPORTS ARE SLOW AND RATIONED. Amazon builds these on request, roughly one a
minute, so api/sp_reports already reuses a recent one rather than asking again --
the same machinery the Sales screen uses (CLAUDE.md Rule 12). Nothing here is on
a timer.
"""
import datetime

from flask import jsonify, request

from domain import search_query as _sq


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None):
    """Attach /sqp to the app."""

    def _scope():
        aid = (request.args.get("id") or request.args.get("account_id") or "").strip()
        mkt = (request.args.get("marketplace") or "").strip().upper()
        if not aid or not mkt:
            acc = {}
            try:
                acc = (_active_account() or {}) if callable(_active_account) else {}
            except Exception:
                acc = {}
            aid = aid or str(acc.get("id") or (_state or {}).get("active_account_id") or "")
            mkt = mkt or str(acc.get("default_marketplace")
                             or (_state or {}).get("active_marketplace") or "").upper()
        return aid, (mkt or "UK")

    @app.route("/sqp", methods=["GET"])
    def sqp_screen():
        wsid, mkt = _scope()
        # SQP is reported by WEEK. Default to the week that finished most
        # recently rather than the current one, which is always partial.
        today = datetime.date.today()
        end = today - datetime.timedelta(days=today.weekday() + 1)   # last Saturday
        start = end - datetime.timedelta(days=6)
        s = (request.args.get("start") or "").strip() or start.isoformat()
        e = (request.args.get("end") or "").strip() or end.isoformat()
        try:
            datetime.date.fromisoformat(s)
            datetime.date.fromisoformat(e)
        except ValueError:
            return jsonify({"ok": False, "error": "Bad dates."}), 400

        try:
            import accounts as _acc
            cfg = (_cfg() or {}) if callable(_cfg) else {}
            accts = _acc.load_accounts(cfg, CONFIG_PATH) or []
            acc = next((a for a in accts if str(a.get("id")) == str(wsid)), None)
            if not acc:
                return jsonify({"ok": False,
                                "error": "That account is not connected."}), 400
            creds = _acc.account_creds(acc)
            mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
        except Exception as ex:
            return jsonify({"ok": False,
                            "error": "Could not read the account: %s" % str(ex)[:160]}), 500

        try:
            from api import sp_reports as _rep
            from sp_api.api import Reports
            from sp_api.base import Marketplaces
            mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.UK
            rc = Reports(credentials=creds, marketplace=mkt_enum, timeout=90)
            # fetch_json returns (payload, source, built_at) -- `source` says
            # whether Amazon built this now or handed back a recent one, which
            # is worth passing on rather than implying it was just pulled.
            payload, source, built_at = _rep.fetch_json(
                rc, _sq.REPORT_TYPE,
                marketplace_ids=[mid] if mid else None,
                options={"reportPeriod": "WEEK"},
                start_time=s + "T00:00:00Z",
                end_time=e + "T23:59:59Z")
        except Exception as ex:
            msg = str(ex)
            low = (type(ex).__name__ + " " + msg).lower()
            status = getattr(ex, "status", "")
            # AMAZON'S HONEST ANSWER IS "I CANNOT TELL YOU WHY".
            #
            # It accepts the request from any account and then ends the report
            # FATAL, whether the account lacks Brand Registry or the week
            # genuinely had no searches. There is no field that separates them,
            # so this does not pick one -- picking would send somebody hunting a
            # sales problem that does not exist, or the reverse. Both are named,
            # with the way to tell them apart.
            if status == "FATAL":
                return jsonify({
                    "ok": False, "reason": "fatal",
                    "error": "Amazon accepted the request for this report and "
                             "then could not produce it. There are only two "
                             "reasons for that and Amazon does not say which: "
                             "either this account is not enrolled in Brand "
                             "Registry (Search Query Performance is a Brand "
                             "Analytics report and needs it), or there genuinely "
                             "were no searches in that week. If the account IS "
                             "brand registered, try a week you know had sales — "
                             "if that also comes back like this, it is the "
                             "enrolment.",
                    "detail": msg[:200]}), 502
            if status == "CANCELLED":
                return jsonify({
                    "ok": False, "reason": "no_data",
                    "error": "Amazon has no Search Query data for that week.",
                    "detail": msg[:200]}), 200
            # THE DISTINCTION THAT MATTERS. Amazon refuses this report outright
            # for an account without Brand Registry. Reported as an empty week,
            # that reads as "nobody searched for us", which is a completely
            # different and much more alarming thing.
            if any(k in low for k in ("forbidden", "unauthorized", "accessdenied",
                                      "access to requested resource",
                                      "not eligible", "brand")):
                return jsonify({
                    "ok": False, "reason": "not_brand_registered",
                    "error": "Amazon will not give this report to this account. "
                             "Search Query Performance needs Brand Registry — "
                             "this is a permission, not an empty week.",
                    "detail": msg[:200]}), 403
            return jsonify({"ok": False,
                            "error": "%s" % msg[:200]}), 502

        rows = _sq.parse(payload)
        built = _sq.build(rows)
        out = {"ok": True, "account": wsid, "marketplace": mkt,
               "start": s, "end": e,
               "rows": built, "summary": _sq.summary(built),
               "min_impressions": _sq.MIN_IMPRESSIONS,
               "weak_share": _sq.WEAK_SHARE,
               "queries_read": len(rows),
               # How fresh this really is. Amazon rations these -- roughly one a
               # minute -- so a recent one is reused rather than rebuilt, and
               # saying "reused, built at X" is honest where a silent reuse
               # implies figures that were just pulled.
               "source": source, "built_at": built_at}
        if not rows:
            # Said out loud: an account WITH Brand Registry and no searches is a
            # real, and quite serious, finding.
            out["note"] = ("Amazon returned this report but it has no queries in "
                           "it for that week. For a brand-registered account "
                           "that means nobody searched and found you — it is not "
                           "a missing permission.")
        return jsonify(out)
