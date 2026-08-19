"""routes/drppc_routes.py -- the Dr PPC console.

    GET  /drppc/status   is the Advertising API connected, and what is missing
    POST /drppc/run      pull the reports and produce the findings
    GET  /drppc/raw      Amazon's UNTOUCHED response, for checking the mapping

BUILT BEFORE THE CONNECTION EXISTS, deliberately, so that the day credentials
arrive there is a screen to point at them rather than a project to start.

WHICH MEANS ONE HONEST CAVEAT, and /drppc/raw is the answer to it. CLAUDE.md
Rule 4 says never guess what Amazon returns -- read the schema. With no
connection the schema cannot be read, so every field name in
api/amazon_ads.MAPPING comes from Amazon's documentation rather than from a live
response. /drppc/raw returns exactly what Amazon sends, untouched, so the first
thing to do once connected is compare the two and correct MAPPING. That is Rule
4's own prescription, wired in from the start instead of added after the first
wrong number.

NOTHING HERE WRITES. api/amazon_ads whitelists its only POST to the reporting
paths, so no route above it can reach a bid, a budget or a campaign state
(Rule 8). The console names the exact change it would make and stops.
"""
import datetime

from flask import jsonify, request

from domain import dr_ppc as _dr


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None):
    """Attach /drppc/* to the app."""

    def _scope():
        aid = (request.args.get("id") or request.args.get("account_id") or "").strip()
        mkt = (request.args.get("marketplace") or "").strip().upper()
        b = request.get_json(silent=True) or {}
        aid = aid or str(b.get("id") or "").strip()
        mkt = mkt or str(b.get("marketplace") or "").strip().upper()
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

    def _account(wsid):
        try:
            import accounts as _acc
            cfg = (_cfg() or {}) if callable(_cfg) else {}
            accts = _acc.load_accounts(cfg, CONFIG_PATH) or []
            return next((a for a in accts if str(a.get("id")) == str(wsid)), None), cfg
        except Exception:
            return None, {}

    @app.route("/drppc/status", methods=["GET"])
    def drppc_status():
        """Connected or not, and precisely what is still needed.

        "Not connected" and "connected wrongly" need different answers, and a
        console that shows an empty page for both is a console that sends
        somebody looking for campaigns that are running perfectly well.
        """
        wsid, mkt = _scope()
        acc, cfg = _account(wsid)
        try:
            from api import amazon_ads as _ads
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Advertising module unavailable: %s"
                                     % str(e)[:150]}), 500
        st = _ads.test(cfg, acc, mkt)
        st["account"] = wsid
        st["marketplace"] = mkt
        if not st.get("connected"):
            st["how"] = [
                "The Advertising API is a SEPARATE login from SP-API — its own "
                "developer registration, its own Login-with-Amazon application "
                "and its own refresh token. An SP-API token will not work here.",
                "Apply at advertising.amazon.com/API/docs — Amazon reviews it.",
                "Once approved you need four things: client id, client secret, "
                "refresh token, and a PROFILE id (one advertising account in "
                "one marketplace).",
                "Put the first three in AI & settings. Then this screen lists "
                "the profiles the login can see, and you pick one.",
            ]
        return jsonify(st)

    @app.route("/drppc/raw", methods=["GET"])
    def drppc_raw():
        """Amazon's response, untouched. The Rule 4 diagnostic.

        Every field name this app reads was taken from documentation rather
        than from a live response, because there was no connection to read one.
        This is how that gets corrected: call it once, compare against
        amazon_ads.MAPPING, fix what does not match.
        """
        wsid, mkt = _scope()
        acc, cfg = _account(wsid)
        what = (request.args.get("what") or "campaigns").strip()
        try:
            from api import amazon_ads as _ads
            creds = _ads.creds_for(cfg, acc)
            gaps = _ads.missing(creds)
            if gaps:
                return jsonify({"ok": False, "connected": False,
                                "missing": gaps,
                                "error": "Not connected yet, so there is no "
                                         "response to show."}), 400
            got = _ads.raw_sample(creds, mkt, what)
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "%s: %s" % (type(e).__name__, str(e)[:250])}), 502
        return jsonify({"ok": True, "what": what, "raw": got,
                        "mapping": _ads.MAPPING,
                        "note": "Compare the keys in `raw` against `mapping`. "
                                "Anything this app reads that is not there is a "
                                "field name to correct in api/amazon_ads.py."})

    @app.route("/drppc/run", methods=["POST"])
    def drppc_run():
        """Pull the reports and produce the findings.

        Two Amazon reports, each of which Amazon BUILDS on request and takes up
        to a couple of minutes — so this is a button, and it says when it is
        still waiting rather than returning an empty console.
        """
        wsid, mkt = _scope()
        b = request.get_json(silent=True) or {}
        acc, cfg = _account(wsid)
        try:
            days = int(b.get("days") or 30)
        except ValueError:
            days = 30
        days = max(1, min(days, 90))
        end = datetime.date.today() - datetime.timedelta(days=1)
        start = end - datetime.timedelta(days=days - 1)

        try:
            from api import amazon_ads as _ads
            creds = _ads.creds_for(cfg, acc)
            gaps = _ads.missing(creds)
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Advertising module unavailable: %s"
                                     % str(e)[:150]}), 500
        if gaps:
            # NOT an empty console. A PPC screen with no ad data and no
            # explanation is the same screen as one with no ad spend.
            return jsonify({
                "ok": False, "connected": False, "missing": gaps,
                "error": "The Amazon Advertising API is not connected yet, so "
                         "there is no campaign data to read. This is a separate "
                         "login from SP-API and only the account owner can "
                         "create it."}), 400

        out = {"ok": True, "connected": True, "account": wsid,
               "marketplace": mkt, "start": start.isoformat(),
               "end": end.isoformat(), "days": days}
        errors = []
        camp_rows, term_rows = [], []
        try:
            r = _ads.report(creds, mkt, "campaign", start.isoformat(), end.isoformat())
            if r.get("ok"):
                camp_rows = r.get("rows") or []
            else:
                errors.append("campaigns: " + str(r.get("error"))[:200])
        except Exception as e:
            errors.append("campaigns: %s: %s" % (type(e).__name__, str(e)[:180]))
        try:
            r = _ads.report(creds, mkt, "search_term", start.isoformat(), end.isoformat())
            if r.get("ok"):
                term_rows = r.get("rows") or []
            else:
                errors.append("search terms: " + str(r.get("error"))[:200])
        except Exception as e:
            errors.append("search terms: %s: %s" % (type(e).__name__, str(e)[:180]))

        # The ACOS target: whatever was given, else nothing. The rules refuse to
        # invent one, and say so on the screen -- see domain/dr_ppc.target_for.
        target = b.get("target_acos")
        try:
            target = float(target) if target not in (None, "") else None
        except (TypeError, ValueError):
            target = None
        if target and target > 1:
            target = target / 100.0            # "30" means 30%

        cur = ""
        try:
            cur = str((_ads.creds_for(cfg, acc) or {}).get("ads_currency") or "")
        except Exception:
            cur = ""

        res = _dr.run(camp_rows, term_rows, target=target, currency=cur)
        out.update(res)
        out["campaigns"] = camp_rows
        out["rows_read"] = {"campaigns": len(camp_rows), "terms": len(term_rows)}
        if errors:
            out["problems"] = errors
            # Findings computed from half the data are findings about half the
            # account, and that has to be visible.
            out.setdefault("notes", []).append(
                "Some of the data could not be read, so these findings are "
                "based on less than the full picture: " + "; ".join(errors))
        return jsonify(out)
