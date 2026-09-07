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

    def _avail(aid, mkt):
        """What each panel can be filled from, PLUS whether Advertising is even
        connected for this account.

        The second half is the one that was missing, and it is why this screen
        looked broken rather than empty. Measured on the real config: five of the
        six accounts have no Advertising login at all, and every one of them was
        being told "nothing is stored for this window" -- which is true, and
        useless. "No login" and "a login that spent nothing" need entirely
        different things done about them.

        All three advertising endpoints go through here, so they cannot end up
        giving three different answers to the same question (Rule 12).
        """
        from domain import ppc_analytics as _pa

        av = _pa.availability(CONFIG_PATH, aid, mkt)
        acc = {}
        for a in ((_cfg() or {}).get("accounts") or []):
            if str(a.get("id") or "") == aid:
                acc = a
                break
        try:
            from api import amazon_ads as _ads
            av["connection"] = _ads.connection(_cfg, acc)
        except Exception as e:
            av["connection"] = {"ok": None, "profile_id": "", "missing": [],
                                "why": ("Could not check whether Advertising is "
                                        "connected: %s" % str(e)[:120])}
        return av

    def _placement_daily(aid, mkt, start, end):
        """Spend per placement per day, in the shape the chart draws.

        {dates: [...], series: [{key, label, values}]}. Empty when nothing is
        stored -- the placement report is a recent addition and an account that
        has not synced since has no rows, which is a real answer.
        """
        try:
            from domain import live_tracker as _lt
            from data import db as _db

            conn = _db.get_db(CONFIG_PATH)
            got, places = {}, []
            for r in conn.execute(
                    "SELECT date, placement, ROUND(SUM(spend),2) spend "
                    "FROM ads_placement_daily WHERE workspace_id=? AND "
                    "marketplace=? AND date>=? AND date<=? "
                    "GROUP BY date, placement", (aid, mkt, start, end)):
                got.setdefault(r["placement"], {})[r["date"]] = r["spend"]
                if r["placement"] not in places:
                    places.append(r["placement"])
            if not places:
                return {"dates": [], "series": []}
            import datetime as _d
            dates, d0 = [], _d.date.fromisoformat(start)
            d1 = _d.date.fromisoformat(end)
            while d0 <= d1:
                dates.append(d0.isoformat())
                d0 += _d.timedelta(days=1)
            # Biggest spender first, so the key reads in the order the eye needs.
            places.sort(key=lambda p: -sum((got.get(p) or {}).values()))
            return {"dates": dates, "series": [
                {"key": p,
                 "label": _lt.PLACEMENT_LABELS.get(p, p),
                 # A day with no row for THIS placement is None, not 0: the ad
                 # may simply not have shown there, which is not the same as
                 # showing there for nothing.
                 "values": [(got.get(p) or {}).get(d) for d in dates]}
                for p in places]}
        except Exception:
            return {"dates": [], "series": []}

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

        from domain import ppc_view as _pv_mod

        avail = _avail(aid, mkt)
        rates = _pa.rates(CONFIG_PATH, aid, mkt, start, end)
        now = _pa.totals_for(CONFIG_PATH, aid, mkt, start, end)
        before = _pa.totals_for(CONFIG_PATH, aid, mkt, pstart, pend)
        # WHICH DAYS HAVE FINISHED BEING ATTRIBUTED, worked out once for the
        # whole page so every panel agrees (Rule 12). The money columns keep the
        # full window; the judgements -- cohort, opportunity score -- are made
        # on the days whose sales have landed. See ppc_analytics.maturity().
        mat = _pa.maturity(CONFIG_PATH, aid, mkt, start, end)
        camps = _pa.campaigns(CONFIG_PATH, aid, mkt, start, end, rates,
                              judge_end=mat.get("mature_end"))
        days = _pa.daily(CONFIG_PATH, aid, mkt, start, end)

        # The panels the mockup draws that are not simple totals. Each is
        # computed once here rather than per panel, because they all read the
        # same daily rows and the same measured rates.
        terms = _pa.terms(CONFIG_PATH, aid, mkt, rates)
        # NO "PREVIOUS WASTED SPEND". It used to be fetched for the earlier
        # window and compared -- but wasted_spend reads the stored Search Term
        # Report, which is ONE fixed window with no day breakdown, so the two
        # calls returned the identical figure and the change arrow could only
        # ever read zero. Measured across 7, 14, 30 and 90 days: 251.56 every
        # time. A comparison that cannot vary is not a comparison.
        _wasted = _pa.wasted_spend(CONFIG_PATH, aid, mkt, start, end)

        return jsonify({
            "today": _pa.today_bar(CONFIG_PATH, aid, mkt),
            # THE TRAIL FOLLOWS THE WINDOW. It was `trail(..., 7)` with the end
            # hardcoded to today inside, so the seven cards showed the same
            # seven days whatever the date picker said -- "changing the time
            # period dont change the data".
            "trail": _pa.trail(CONFIG_PATH, aid, mkt, 7, start=start, end=end),
            "per_click": _pa.per_click_trend(days, rates.get("fee_rate"),
                                             rates.get("cogs_rate")),
            "efficiency": _pa.efficiency_trend(
                days, rates.get("breakeven_acos_pct")),
            # With the brand words, so the panel can name what it matched on.
            "branded": _pa.branded_split(
                terms, _pv_mod.brand_terms(CONFIG_PATH, aid)),
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
            # Why an arrow is blank when it is blank. A dash with no reason
            # reads as missing data; this says the data is there and it is the
            # COMPARISON that would be meaningless -- a prior TACOS of 0.4%
            # rising to 12% is arithmetic, not news.
            "change_floor": _pa.change_floor(now, before),
            "daily": days,
            # The days still being attributed, so the charts can mark them and
            # the page can say why the judgements stop short of the last day.
            "maturity": mat,
            # PROFIT AFTER ADVERTISING, the SAME figure the Sales page reports
            # minus the ad spend. Sent from the server rather than worked out in
            # the browser so the two screens cannot drift -- they had, and the
            # two numbers landed on opposite sides of zero with nothing on
            # either page to say they were answering different questions.
            "net_profit": _pa.net_profit(CONFIG_PATH, aid, mkt, start, end, now),
            "cohorts": _pa.cohorts(CONFIG_PATH, aid, mkt, start, end, camps, rates),
            "wasted": _wasted,
            # The headline 0-100 score, with all three parts and their weights,
            # so the number can be argued with rather than merely trusted. It
            # reports a refusal, naming the missing part, rather than scoring on
            # two legs out of three -- which would look identical to a real one.
            "efficiency_score": _pa.efficiency_score(
                now, rates, _wasted,
                _pa.cvr_baseline(CONFIG_PATH, aid, mkt, end)),
            # Which unit each change arrow is in. A ratio moves in POINTS and
            # money in per cent; 24.3% to 28.4% is +4.1pts, not +16.9%.
            "change_units": _pa.change_units(now),
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

        from domain import ppc_view as _pv

        rates = _pa.rates(CONFIG_PATH, aid, mkt, start, end)
        meta = _pv.report_meta(CONFIG_PATH, aid, mkt)

        # THE TABLE NOW MOVES WITH THE DATE PICKER -- when the rows carry days.
        #
        # It could not before, and the note below said so honestly: the report
        # was stored as one batch per window, so every window asked for returned
        # the same rows. Pulled at DAILY grain it carries the day, and the
        # backend re-queries rather than slicing a fixed batch in the browser.
        #
        # WHICH CASE THIS ACCOUNT IS IN IS MEASURED, NOT ASSUMED. An account can
        # hold both at once -- an old uploaded file and a new daily sync -- so
        # the window is only applied when there are dated rows to apply it to,
        # and `dated` tells the screen what to say either way.
        _dw = _pv.dated_window(CONFIG_PATH, aid, mkt,
                               (meta or {}).get("report_id"))
        _follows = bool(_dw.get("can_follow_picker"))
        rows = _pa.terms(CONFIG_PATH, aid, mkt, rates,
                         start=(start if _follows else None),
                         end=(end if _follows else None))
        now = _pa.totals_for(CONFIG_PATH, aid, mkt, start, end)
        before = _pa.totals_for(CONFIG_PATH, aid, mkt, pstart, pend)

        return jsonify({
            "ok": True, "account": aid, "marketplace": mkt,
            "window": {"start": start, "end": end,
                       "compare_start": pstart, "compare_end": pend},
            "availability": _avail(aid, mkt),
            "rates": rates,
            "totals": now, "previous": before,
            "change": _pa.change(now, before),
            "change_floor": _pa.change_floor(now, before),
            "terms": rows,
            "term_count": len(rows),
            "report": meta,
            "dated": _dw,
            "follows_picker": _follows,
            "report_note": (
                "" if not meta else
                (("These search terms are stored per day, so this table moves "
                  "with the date picker like the cards above it.")
                 if _follows else
                 ("These search terms come from the report covering %s to %s. "
                  "The cards above move with the date picker; this table does "
                  "not, because one report is one fixed window."
                  % (meta.get("date_from"), meta.get("date_to"))))),
            "by_match_type": _pa.by_group(rows, "match_type"),
            # The brand words go WITH the split, so the panel can say what it
            # matched on. A split with no statement of its rule cannot be
            # checked, and a wrong brand list looks identical to a wrong sum.
            "branded": _pa.branded_split(rows,
                                         _pv.brand_terms(CONFIG_PATH, aid)),
            # The saved words themselves, so the screen can show them as chips
            # and let one be removed. They were never sent, so a word that saved
            # was indistinguishable from one that did not.
            "brand_terms": _pv.brand_terms(CONFIG_PATH, aid),
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

        from domain import ppc_targeting as _pt

        rates = _pa.rates(CONFIG_PATH, aid, mkt, start, end)
        mat = _pa.maturity(CONFIG_PATH, aid, mkt, start, end)
        camps = _pa.campaigns(CONFIG_PATH, aid, mkt, start, end, rates,
                              judge_end=mat.get("mature_end"))
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
            "availability": _avail(aid, mkt),
            "rates": rates,
            "totals": _pa.totals_for(CONFIG_PATH, aid, mkt, start, end),
            "campaigns": camps,
            "cohorts": _pa.cohorts(CONFIG_PATH, aid, mkt, start, end, camps, rates),
            "by_ad_product": _pa.by_group(camps, "ad_product"),
            # SPEND BY MATCH TYPE, FROM THE TARGETING REPORT, NOT THE SEARCH
            # TERMS. The spec names the source twice -- "daily targeting-level
            # reports (keyword/target grain), NOT search term report" -- and the
            # difference is not academic: Amazon suppresses low-volume queries
            # from the Search Term Report, so a donut drawn from it is short of
            # the spend that was actually billed and does not add up to the
            # total printed beside it.
            #
            # `by_match_type_terms` is kept under its own name so the Search
            # Terms panel on this page still has its own figures, and so the two
            # can be compared rather than silently disagreeing.
            "by_match_type": _pt.by_match_type(
                CONFIG_PATH, aid, mkt, start, end,
                rates.get("fee_rate"), rates.get("cogs_rate")),
            "by_match_type_terms": _pa.by_group(terms, "match_type"),
            # The stacked area: one column per day, one lane per match type,
            # in the shape the app's own chart engine already takes.
            "match_type_daily": _pt.daily_by_match_type(CONFIG_PATH, aid, mkt,
                                                        start, end),
            "targeting": _pt.available(CONFIG_PATH, aid, mkt),
            # The click and spend shortfall against the campaign grain, MEASURED
            # rather than asserted -- auto campaigns and SB placements do not map
            # to keyword match types, so the two totals are shown side by side.
            "match_type_gap": _pt.gap(CONFIG_PATH, aid, mkt, start, end),
            "maturity": mat,
            "daily": _pa.daily(CONFIG_PATH, aid, mkt, start, end),
            "daily_by_product": _pa.daily_by_ad_product(CONFIG_PATH, aid, mkt,
                                                        start, end),
            # WHERE THE ADS APPEARED, per day. Sent because the spend-per-day
            # chart splits by ad product, and an account running only Sponsored
            # Products gets ONE band -- a chart with a single series is a line
            # that needs no key. The placement split is a real second cut of the
            # same money, from Amazon, with three live categories here and a
            # figure for every day. Read through domain/live_tracker, which owns
            # that table (Rule 12), rather than queried again here.
            "placement_daily": _placement_daily(aid, mkt, start, end),
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
