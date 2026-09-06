"""routes/ppc_analytics_routes.py -- the three advertising screens.

    GET /ppc/analytics/overview     PPC Analytics
    GET /ppc/analytics/terms        Search Terms
    GET /ppc/analytics/campaigns    Campaign Analytics
    GET /ppc/analytics/terms.csv    the search terms, whole

Its own file because these are new features (CLAUDE.md Rule 7), and because
routes/ppc_routes.py already owns /ppc/analytics -- the older Search Term Report
screen, which stays exactly as it is.

ONE COMPUTATION LAYER, THREE VIEWS. Every figure comes from
domain/ppc_analytics.py. Three screens quoting three different ACOSes for the
same window is what that arrangement exists to prevent (Rule 12), and these
routes do no arithmetic of their own.

NOTHING HERE WRITES. No bid, no budget, no campaign state (Rule 8). Every one of
these is a GET.

WHAT IS NOT AVAILABLE IS SAID, NOT STUBBED. Each reply carries `availability`,
and the pages render the reason in place of the panel. The build specs asked for
placeholder data where a source is missing; that was declined, because it has
been complained about twice -- "i still see the organic vs ppc sales graph as a
placeholder" -- and because a stub is indistinguishable from a measurement once
it is drawn.
"""
import datetime as _dt

from flask import jsonify, request

import domain.request_account as _req_acct


def register(app, *, CONFIG_PATH, _cfg, _state, _active_account):

    def _scope():
        """Which account, marketplace and window this request is about."""
        aid = _req_acct.named(request)
        if not aid:
            aid = str((_state or {}).get("active_account_id", "") or "")
        if not aid:
            try:
                aid = str((_active_account() or {}).get("id") or "")
            except Exception:
                aid = ""
        mkt = (request.args.get("marketplace")
               or _state.get("active_marketplace") or "").upper()
        if aid and (not mkt or mkt == "__ALL__"):
            # Advertising belongs to ONE marketplace -- an advertising profile
            # is one advertiser in one marketplace -- so "all marketplaces"
            # cannot be answered and the account's own default is used.
            for a in ((_cfg() or {}).get("accounts") or []):
                if str(a.get("id") or "") == aid:
                    mkt = str(a.get("default_marketplace") or "").upper()
                    if not mkt:
                        ms = [str(m).upper() for m in (a.get("marketplaces") or [])
                              if str(m).upper() != "__ALL__"]
                        mkt = ms[0] if ms else ""
                    break
        return aid, mkt

    def _window():
        from domain import ppc_analytics as _pa
        start = (request.args.get("start") or "").strip()
        end = (request.args.get("end") or "").strip()
        if start and end:
            span = ((_dt.date.fromisoformat(end)
                     - _dt.date.fromisoformat(start)).days + 1)
            pe = _dt.date.fromisoformat(start) - _dt.timedelta(days=1)
            ps = pe - _dt.timedelta(days=max(span, 1) - 1)
            return start, end, ps.isoformat(), pe.isoformat()
        try:
            days = max(1, min(365, int(request.args.get("days") or 30)))
        except (TypeError, ValueError):
            days = 30
        return _pa.window(days)

    def _need(aid, mkt):
        if aid and mkt:
            return None
        return jsonify({"ok": False, "error": (
            "Open an account and pick a marketplace first — advertising "
            "figures belong to one account in one marketplace.")}), 400

    @app.route("/ppc/analytics/overview")
    def ppc_analytics_overview():
        """Everything the PPC Analytics page draws.

        One call rather than eight, because every panel is a different cut of
        the same window and eight calls would each re-measure the account's fee
        rate.
        """
        from domain import ppc_analytics as _pa

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        start, end, pstart, pend = _window()

        avail = _pa.availability(CONFIG_PATH, aid, mkt)
        rates = _pa.rates(CONFIG_PATH, aid, mkt, start, end)
        now = _pa.totals_for(CONFIG_PATH, aid, mkt, start, end)
        before = _pa.totals_for(CONFIG_PATH, aid, mkt, pstart, pend)
        camps = _pa.campaigns(CONFIG_PATH, aid, mkt, start, end, rates)

        return jsonify({
            "ok": True, "account": aid, "marketplace": mkt,
            "window": {"start": start, "end": end,
                       "compare_start": pstart, "compare_end": pend},
            "availability": avail,
            "rates": rates,
            "totals": now,
            "previous": before,
            # None per metric when the previous window has no data. A move from
            # nothing to something is not a rise, and +100% would read as one.
            "change": _pa.change(now, before),
            "daily": _pa.daily(CONFIG_PATH, aid, mkt, start, end),
            "cohorts": _pa.cohorts(CONFIG_PATH, aid, mkt, start, end, camps, rates),
            "wasted": _pa.wasted_spend(CONFIG_PATH, aid, mkt, start, end),
            "by_ad_product": _pa.by_group(camps, "ad_product"),
            "campaigns": camps[:100],
            "campaign_count": len(camps),
            "asins": _pa.asins(CONFIG_PATH, aid, mkt, start, end, rates),
        })

    @app.route("/ppc/analytics/terms")
    def ppc_analytics_terms():
        """Everything the Search Terms page draws."""
        from domain import ppc_analytics as _pa

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        start, end, pstart, pend = _window()

        rates = _pa.rates(CONFIG_PATH, aid, mkt, start, end)
        rows = _pa.terms(CONFIG_PATH, aid, mkt, rates)
        now = _pa.totals_for(CONFIG_PATH, aid, mkt, start, end)
        before = _pa.totals_for(CONFIG_PATH, aid, mkt, pstart, pend)

        # THE REPORT'S OWN WINDOW, WHICH IS NOT THE PAGE'S.
        #
        # The search term report covers one fixed window chosen when it was
        # pulled; the date picker above the table moves the KPI cards, which
        # come from the daily tables. Saying so is the difference between a
        # confusing screen and an honest one -- the table does not move when
        # the dates do, and somebody will notice.
        from domain import ppc_view as _pv
        meta = _pv.report_meta(CONFIG_PATH, aid, mkt)

        return jsonify({
            "ok": True, "account": aid, "marketplace": mkt,
            "window": {"start": start, "end": end,
                       "compare_start": pstart, "compare_end": pend},
            "availability": _pa.availability(CONFIG_PATH, aid, mkt),
            "rates": rates,
            "totals": now, "previous": before,
            "change": _pa.change(now, before),
            "terms": rows,
            "term_count": len(rows),
            "report": meta,
            "report_note": (
                "" if not meta else
                ("These search terms come from the report covering %s to %s. "
                 "The cards above move with the date picker; this table does "
                 "not, because one report is one fixed window."
                 % (meta.get("date_from"), meta.get("date_to")))),
            "by_match_type": _pa.by_group(rows, "match_type"),
            "branded": _pa.branded_split(rows),
            "wasted": _pa.wasted_spend(CONFIG_PATH, aid, mkt, start, end),
        })

    @app.route("/ppc/analytics/campaigns")
    def ppc_analytics_campaigns():
        """Everything the Campaign Analytics page draws."""
        from domain import ppc_analytics as _pa

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        start, end, pstart, pend = _window()

        rates = _pa.rates(CONFIG_PATH, aid, mkt, start, end)
        camps = _pa.campaigns(CONFIG_PATH, aid, mkt, start, end, rates)
        terms = _pa.terms(CONFIG_PATH, aid, mkt, rates)

        # The search terms of each campaign, for the expanded row. Grouped here
        # rather than fetched per row: the whole report is already in hand, and
        # a call per expanded campaign would be 254 calls to show one table.
        by_campaign = {}
        for t in terms:
            by_campaign.setdefault(t["campaign"], []).append(t)
        for k in by_campaign:
            by_campaign[k].sort(key=lambda x: -(x["spend"] or 0))
            by_campaign[k] = by_campaign[k][:50]

        return jsonify({
            "ok": True, "account": aid, "marketplace": mkt,
            "window": {"start": start, "end": end,
                       "compare_start": pstart, "compare_end": pend},
            "availability": _pa.availability(CONFIG_PATH, aid, mkt),
            "rates": rates,
            "totals": _pa.totals_for(CONFIG_PATH, aid, mkt, start, end),
            "campaigns": camps,
            "cohorts": _pa.cohorts(CONFIG_PATH, aid, mkt, start, end, camps, rates),
            "by_ad_product": _pa.by_group(camps, "ad_product"),
            "by_match_type": _pa.by_group(terms, "match_type"),
            "daily": _pa.daily(CONFIG_PATH, aid, mkt, start, end),
            "terms_by_campaign": by_campaign,
        })

    @app.route("/ppc/analytics/terms.csv")
    def ppc_analytics_terms_csv():
        """Every search term, whole.

        Not the page's first two hundred: an export that silently truncates is
        worse than none, because nothing on the file says it is short.
        """
        import csv as _csv
        import io as _io
        from flask import Response
        from domain import ppc_analytics as _pa

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        start, end, _ps, _pe = _window()
        rates = _pa.rates(CONFIG_PATH, aid, mkt, start, end)
        rows = _pa.terms(CONFIG_PATH, aid, mkt, rates, limit=100000)

        cols = ["search_term", "keyword", "match_type", "campaign", "ad_group",
                "impressions", "clicks", "spend", "orders", "sales", "acos_pct",
                "roas", "ctr_pct", "cpc", "cpa", "cvr_pct", "profit",
                "opportunity", "branded", "product_target"]
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(cols)
        for r in rows:
            w.writerow([("" if r.get(c) is None else r.get(c)) for c in cols])
        # utf-8-sig: Excel opens a plain UTF-8 CSV in the wrong encoding and
        # mangles every pound sign and every accented term.
        data = buf.getvalue().encode("utf-8-sig")
        name = "search-terms-%s-%s.csv" % (aid, mkt)
        return Response(data, mimetype="text/csv", headers={
            "Content-Disposition": 'attachment; filename="%s"' % name})
