"""routes/keywords_routes.py -- Phase 1 of the analytics plan. Keywords.

    GET  /keywords/spy            marketplace search terms for a seed word
    GET  /keywords/asin-insights  the queries driving one ASIN
    GET  /keywords/rank-tracker   the watch list and what has been measured
    POST /keywords/rank-tracker/add | /remove | /check
    GET  /keywords/history        everything stored, week over week

NOTHING HERE RUNS ON ITS OWN. No scheduler, no background thread, no cron, no
APScheduler, no Celery. Every route in this file is reached because somebody
clicked something. That was the explicit instruction and it is also why the
history is uneven -- weeks nobody searched are simply absent -- so the screens
report what is stored rather than drawing a line through a gap.

A NEW TOOL, NOT A CHANGE TO AN OLD ONE. It reads the existing
domain/brand_analytics.py rather than modifying it, and stores through the new
domain/keyword_store.py. Nothing in the listing generator, the image tools, the
repricer or the COGS system is touched.

REPORTS ARE SLOW AND RATIONED, which shapes the whole design. Amazon builds
Brand Analytics reports on request, roughly one a minute, and they need Brand
Registry. brand_analytics.py already caches each pull per week on disk, so the
second person to ask for the same week pays nothing. The screens surface both
facts, because "no keywords" from an unregistered account and "no keywords" from
a quiet week look identical and only one is worth acting on.
"""
import datetime

from flask import jsonify, request

from domain import brand_analytics as _ba
from domain import keyword_store as _ks


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None):
    """Attach the /keywords/* routes."""

    def _scope():
        """Which account and marketplace this request is about.

        Same shape as sqp_routes._scope, deliberately: both screens ask the same
        question of the same data and should resolve it the same way.
        """
        b = request.get_json(silent=True) or {} if request.method == "POST" else {}
        aid = str(b.get("id") or request.args.get("id")
                  or request.args.get("account_id") or "").strip()
        mkt = str(b.get("marketplace") or request.args.get("marketplace")
                  or "").strip().upper()
        if not aid or not mkt:
            acc = {}
            try:
                acc = (_active_account() or {}) if callable(_active_account) else {}
            except Exception:
                acc = {}
            aid = aid or str(acc.get("id")
                             or (_state or {}).get("active_account_id") or "")
            mkt = mkt or str(acc.get("default_marketplace")
                             or (_state or {}).get("active_marketplace") or "").upper()
        return aid, (mkt or "UK")

    def _wrong_account(asked):
        """The same guard the rest of the app uses (domain/account_scope.py).

        A new screen that reads a named account's data with that account's own
        credentials is exactly the shape that had to be closed across eleven
        routes. Adding a twelfth without it would reopen it.
        """
        from domain import account_scope as _acctscope
        open_id = (_state or {}).get("active_account_id")
        if _acctscope.is_mismatch(asked, open_id):
            return jsonify(_acctscope.refusal(asked, open_id, "keyword data")), 409
        return None

    def _last_full_week():
        """The week that FINISHED most recently. The current one is partial, and
        a partial week compared against a whole one always looks like a crash."""
        today = datetime.date.today()
        end = today - datetime.timedelta(days=today.weekday() + 1)   # last Saturday
        return (end - datetime.timedelta(days=6)).isoformat(), end.isoformat()

    def _dates():
        s0, e0 = _last_full_week()
        s = (request.values.get("start") or "").strip() or s0
        e = (request.values.get("end") or "").strip() or e0
        try:
            datetime.date.fromisoformat(s)
            datetime.date.fromisoformat(e)
        except ValueError:
            return None, None, jsonify({"ok": False,
                                        "error": "Bad dates."}), 400
        return s, e, None, None

    def _creds(wsid, mkt):
        """(creds, error_response). Named separately so every route refuses the
        same way rather than each inventing its own message."""
        try:
            import accounts as _acc
            cfg = (_cfg() or {}) if callable(_cfg) else {}
            accts = _acc.load_accounts(cfg, CONFIG_PATH) or []
            acc = next((a for a in accts if str(a.get("id")) == str(wsid)), None)
            if not acc:
                return None, (jsonify({"ok": False, "error":
                    "That account is not connected."}), 400)
            if not _acc.seller_scope_allowed(acc):
                # A borrowed token answers for the LENDER, so this would return
                # another seller's keyword data under this account's name.
                return None, (jsonify({"ok": False, "error":
                    "This workspace borrows another account's Amazon app, so it "
                    "cannot read its own Brand Analytics."}), 403)
            return _acc.account_creds(acc), None
        except Exception as ex:
            return None, (jsonify({"ok": False, "error":
                "Could not read the account: %s" % str(ex)[:160]}), 500)

    def _brand_registry_hint(ex):
        """Amazon's permission error, translated once.

        An account without Brand Registry gets a permission failure, and an
        account WITH it that had no searches gets an empty report. On a screen
        those look the same and only one of them is worth doing anything about.
        """
        t = str(ex).lower()
        if "access" in t or "unauthor" in t or "forbidden" in t or "403" in t:
            return ("Amazon refused this report. Brand Analytics needs Brand "
                    "Registry on this selling account — an account without it "
                    "cannot pull search terms at all. That is different from a "
                    "week with no searches.")
        return None

    # ------------------------------------------------------------ Keyword Spy
    @app.route("/keywords/spy", methods=["GET"])
    def keywords_spy():
        """Marketplace search terms, filtered to a seed word.

        The report is the WHOLE marketplace's top search terms -- it is not
        per-seller data -- so the seed is a filter over what Amazon returned,
        not a query sent to Amazon. Saying that matters: somebody expecting
        "search anything" will otherwise read an empty result as a bug rather
        than as "that word is not in this marketplace's top terms".
        """
        wsid, mkt = _scope()
        bad = _wrong_account(request.args.get("id"))
        if bad:
            return bad
        seed = (request.args.get("q") or "").strip()
        s, e, err, code = _dates()
        if err:
            return err, code
        creds, cerr = _creds(wsid, mkt)
        if cerr:
            return cerr

        try:
            rows = _ba.fetch_search_terms(creds, marketplace=mkt,
                                          start_iso=s, end_iso=e,
                                          log=lambda *a, **k: None)
        except Exception as ex:
            hint = _brand_registry_hint(ex)
            return jsonify({"ok": False,
                            "error": hint or ("Amazon could not return the "
                                              "search terms report: %s"
                                              % str(ex)[:200]),
                            "brand_registry": bool(hint)}), 502

        total = len(rows)
        if seed:
            low = seed.lower()
            rows = [r for r in rows if low in str(r.get("term", "")).lower()]
        rows = sorted(rows, key=lambda r: (r.get("rank") or 999999999))[:300]

        # SAVE ON EVERY SEARCH -- that is the whole mechanism by which history
        # accumulates without a scheduler.
        saved = 0
        try:
            saved = _ks.save_search_terms(wsid, mkt, rows, s, e, seed=seed,
                                          config_path=CONFIG_PATH)
        except Exception:
            saved = 0        # a storage failure must not lose the answer

        return jsonify({"ok": True, "rows": rows, "count": len(rows),
                        "total_in_report": total, "seed": seed,
                        "start": s, "end": e, "saved": saved,
                        "note": ("This is the whole marketplace's top search "
                                 "terms report, filtered to your word — not a "
                                 "search sent to Amazon.")})

    # --------------------------------------------------------- ASIN Insights
    @app.route("/keywords/asin-insights", methods=["GET"])
    def keywords_asin_insights():
        """The search queries that produced impressions, clicks and purchases
        for ONE ASIN.

        WHAT THIS IS NOT: a reverse-ASIN lookup on a competitor. Search Query
        Performance is reported for ASINs the CONNECTED SELLER owns; Amazon
        does not hand over another seller's query performance. Asked for a
        competitor's ASIN it returns nothing, which is a true answer that reads
        like a broken feature unless the screen says so.
        """
        wsid, mkt = _scope()
        bad = _wrong_account(request.args.get("id"))
        if bad:
            return bad
        asin = (request.args.get("asin") or "").strip().upper()
        if not asin:
            return jsonify({"ok": False, "error": "Enter an ASIN."}), 400
        s, e, err, code = _dates()
        if err:
            return err, code
        creds, cerr = _creds(wsid, mkt)
        if cerr:
            return cerr

        try:
            rows = _ba.fetch_sqp_for_asin(creds, asin, marketplace=mkt,
                                          start_iso=s, end_iso=e,
                                          log=lambda *a, **k: None)
        except Exception as ex:
            hint = _brand_registry_hint(ex)
            return jsonify({"ok": False,
                            "error": hint or ("Amazon could not return Search "
                                              "Query Performance for %s: %s"
                                              % (asin, str(ex)[:200])),
                            "brand_registry": bool(hint)}), 502

        # RATES ARE COMPUTED HERE AND NAMED HONESTLY. Amazon's "click share" is
        # this ASIN's share of ALL clicks for the query across every seller, and
        # this report does not contain it. clicks/impressions is our own
        # click-through rate. They are different numbers and only one of them is
        # available, so only that one is shown -- under its own name.
        out = []
        for r in rows:
            imp = int(r.get("impressions") or 0)
            clk = int(r.get("clicks") or 0)
            pur = int(r.get("purchases") or 0)
            out.append({**r,
                        "ctr": round(clk / imp * 100, 2) if imp else None,
                        "cvr": round(pur / clk * 100, 2) if clk else None})

        saved = 0
        try:
            saved = _ks.save_sqp(wsid, mkt, asin, rows, s, e,
                                 config_path=CONFIG_PATH)
        except Exception:
            saved = 0

        return jsonify({"ok": True, "asin": asin, "rows": out,
                        "count": len(out), "start": s, "end": e,
                        "saved": saved,
                        "note": ("Search Query Performance covers ASINs this "
                                 "selling account owns. A competitor's ASIN "
                                 "returns nothing — Amazon does not share "
                                 "another seller's query performance."),
                        "rates_note": ("CTR is clicks ÷ impressions and CVR is "
                                       "purchases ÷ clicks, both for this "
                                       "listing. Neither is Amazon's “click "
                                       "share”, which this report does not "
                                       "contain.")})

    # ---------------------------------------------------------- Rank Tracker
    @app.route("/keywords/rank-tracker", methods=["GET"])
    def keywords_rank_tracker():
        wsid, mkt = _scope()
        bad = _wrong_account(request.args.get("id"))
        if bad:
            return bad
        kw = (request.args.get("keyword") or "").strip()
        asin = (request.args.get("asin") or "").strip().upper()
        return jsonify({
            "ok": True,
            "watch": _ks.watch_list(wsid, mkt, config_path=CONFIG_PATH),
            "history": _ks.rank_history(wsid, mkt, kw or None, asin or None,
                                        config_path=CONFIG_PATH),
            "counts": _ks.stored_counts(wsid, mkt, config_path=CONFIG_PATH),
            # Said on the route, not only in the page, so anything else that
            # ever reads this cannot mistake the signal for a position.
            "what_this_measures": (
                "Search VISIBILITY, not organic position. Nothing available "
                "here can measure organic rank: SP-API has no rank endpoint, "
                "and scraping search results is against Amazon's terms and "
                "would risk the selling account. What is recorded is this "
                "ASIN's impressions, clicks and purchases for the keyword in "
                "the chosen week."),
        })

    @app.route("/keywords/rank-tracker/add", methods=["POST"])
    def keywords_rank_add():
        wsid, mkt = _scope()
        b = request.get_json(silent=True) or {}
        bad = _wrong_account(b.get("id"))
        if bad:
            return bad
        kw = str(b.get("keyword") or "").strip()
        asin = str(b.get("asin") or "").strip().upper()
        if not kw or not asin:
            return jsonify({"ok": False,
                            "error": "Both a keyword and an ASIN are needed."}), 400
        _ks.watch_add(wsid, mkt, kw, asin, config_path=CONFIG_PATH)
        return jsonify({"ok": True,
                        "watch": _ks.watch_list(wsid, mkt, config_path=CONFIG_PATH)})

    @app.route("/keywords/rank-tracker/remove", methods=["POST"])
    def keywords_rank_remove():
        wsid, mkt = _scope()
        b = request.get_json(silent=True) or {}
        bad = _wrong_account(b.get("id"))
        if bad:
            return bad
        _ks.watch_remove(wsid, mkt, str(b.get("keyword") or ""),
                         str(b.get("asin") or ""), config_path=CONFIG_PATH)
        return jsonify({"ok": True,
                        "watch": _ks.watch_list(wsid, mkt, config_path=CONFIG_PATH)})

    @app.route("/keywords/rank-tracker/check", methods=["POST"])
    def keywords_rank_check():
        """Check the watched pairs ONCE, because somebody pressed the button.

        ONE SQP PULL PER ASIN, not per pair: the report is per ASIN and contains
        every query for it, so ten keywords on one ASIN is one report, not ten.
        Amazon rations these at roughly one a minute and brand_analytics caches
        per week, so getting this wrong would be slow and rude rather than
        merely wasteful.
        """
        wsid, mkt = _scope()
        b = request.get_json(silent=True) or {}
        bad = _wrong_account(b.get("id"))
        if bad:
            return bad
        s, e, err, code = _dates()
        if err:
            return err, code
        creds, cerr = _creds(wsid, mkt)
        if cerr:
            return cerr

        watch = _ks.watch_list(wsid, mkt, config_path=CONFIG_PATH)
        only = [str(x).strip().upper() for x in (b.get("asins") or []) if x]
        if only:
            watch = [w for w in watch if w["asin"] in only]
        if not watch:
            return jsonify({"ok": False,
                            "error": "Nothing is being watched yet."}), 400

        by_asin = {}
        for w in watch:
            by_asin.setdefault(w["asin"], []).append(w["keyword"])

        checked, failed = 0, []
        for asin, kws in by_asin.items():
            try:
                rows = _ba.fetch_sqp_for_asin(creds, asin, marketplace=mkt,
                                              start_iso=s, end_iso=e,
                                              log=lambda *a, **k: None)
            except Exception as ex:
                failed.append({"asin": asin, "error": str(ex)[:160]})
                continue
            try:
                _ks.save_sqp(wsid, mkt, asin, rows, s, e, config_path=CONFIG_PATH)
            except Exception:
                pass
            index = {str(r.get("query", "")).strip().lower(): r for r in rows}
            for kw in kws:
                sig = index.get(kw.strip().lower())
                # A keyword with NO row is recorded as zeros, not skipped. "This
                # keyword produced no impressions that week" is a finding; a gap
                # in the history is not, and would read later as "never checked".
                _ks.save_rank_check(wsid, mkt, kw, asin, sig or {}, start=s,
                                    config_path=CONFIG_PATH)
                checked += 1

        return jsonify({"ok": True, "checked": checked,
                        "asins_pulled": len(by_asin), "failed": failed,
                        "start": s, "end": e,
                        "watch": _ks.watch_list(wsid, mkt, config_path=CONFIG_PATH),
                        "history": _ks.rank_history(wsid, mkt,
                                                    config_path=CONFIG_PATH)})

    # --------------------------------------------------------------- History
    @app.route("/keywords/history", methods=["GET"])
    def keywords_history():
        """Everything stored for this account, and week-over-week movement.

        Reads only. This page never calls Amazon -- it is the record of what the
        other two screens have already pulled, which is what makes it instant
        and free to open.
        """
        wsid, mkt = _scope()
        bad = _wrong_account(request.args.get("id"))
        if bad:
            return bad
        weeks = _ks.weeks_available(wsid, mkt, config_path=CONFIG_PATH)
        q = (request.args.get("q") or "").strip()
        this_w = (request.args.get("week") or "").strip() or (
            weeks[0]["report_start"] if weeks else "")
        prev_w = (request.args.get("prev") or "").strip() or (
            weeks[1]["report_start"] if len(weeks) > 1 else "")

        rows = (_ks.keywords_for_week(wsid, mkt, this_w, q,
                                      config_path=CONFIG_PATH)
                if this_w else [])
        movers = (_ks.compare_weeks(wsid, mkt, this_w, prev_w, q,
                                    config_path=CONFIG_PATH)
                  if (this_w and prev_w) else [])
        return jsonify({
            "ok": True, "weeks": weeks, "week": this_w, "prev": prev_w,
            "rows": rows, "movers": movers, "q": q,
            "counts": _ks.stored_counts(wsid, mkt, config_path=CONFIG_PATH),
            "rank_note": ("Search frequency rank counts DOWN: 1 is the most "
                          "searched term. A keyword whose rank fell has become "
                          "MORE popular, so “moved” is shown as last week's "
                          "rank minus this week's — positive means rising."),
            "gap_note": ("History only holds weeks somebody actually searched "
                         "in. A keyword missing from one side of a comparison "
                         "usually means no pull that week, not that it "
                         "disappeared, so it is not counted as a movement."),
        })

    return app
