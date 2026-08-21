"""routes/brandview_routes.py -- one account, EVERY marketplace, side by side.

WHAT THIS FIXES, AND IT IS NOT A MISSING FEATURE SO MUCH AS A LIE.

The sidebar has offered "All marketplaces" all along. Every screen accepts it,
and every screen throws it away: static/js/scopeq.js drops the parameter, and
routes that do receive it turn it into the account's default --

    routes/traffic_routes.py:65   if not mkt or mkt == "__all__":
    routes/hourly_routes.py:23        mkt = str(acc.get("default_marketplace") or "")

-- so the answer is about ONE marketplace. Measured 21 Aug 2026 in a browser:
with "All marketplaces" showing in the sidebar, the Sales screen said "United
Kingdom Time", drew a week-to-date chart in pounds, and made no new request at
all after the switch. Jack Reacherd sells in ten marketplaces; the screen showed
one of them under a heading that said all.

WHAT IT ANSWERS
For the open account and a window: one row per marketplace it sells in, with the
figures the Sales screen already shows for a single one, and the same window
immediately before it so each row carries a change rather than a bare number.

CURRENCIES ARE GROUPED, NEVER SUMMED
    "keep grouping by currency, don't sum across them"      -- the owner, 20 Aug
So there is a subtotal per currency and no grand total anywhere. Adding pounds
to euros needs a rate and a date, and a single number that hides both is worse
than no number: it is one nobody can check. The rows are ordered by revenue
inside each currency, biggest first.

IT ASKS AMAZON FOR NOTHING
Every figure comes from sales_daily, which the rotation already fills for every
marketplace (domain/live_refresher.py). Opening this cannot spend report quota
and cannot be slow because of Amazon.

AND IT USES THE SAME RESOLVER AS THE SINGLE-MARKETPLACE SCREEN
domain/sales_data.totals, with the same basis and the same VAT rate, so a row
here and the Sales screen with that marketplace open cannot disagree (rule 12).
"""
import datetime as _dt

from flask import request, jsonify

from routes import scope as _scope_mod


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach /brand/marketplaces to the existing Flask app."""

    def _account_by_id(aid):
        try:
            from domain import accounts as _acc_mod
            return _acc_mod.get_account(
                _cfg() if callable(_cfg) else (_cfg or {}), aid, CONFIG_PATH)
        except Exception:
            return None

    def _range():
        """The window, resolved to two dates. The same shape the Sales screen
        uses, so a figure here and a figure there cover the same days."""
        today = _dt.date.today()
        start = (request.args.get("start") or "").strip()
        end = (request.args.get("end") or "").strip()
        if not start or not end:
            try:
                days = max(1, min(400, int(request.args.get("days") or 30)))
            except (TypeError, ValueError):
                days = 30
            # Yesterday, because Amazon's today never exists and a partial day
            # read as a whole one makes every "down on last period" wrong.
            end_d = today - _dt.timedelta(days=1)
            start_d = end_d - _dt.timedelta(days=days - 1)
            return start_d.strftime("%Y-%m-%d"), end_d.strftime("%Y-%m-%d")
        return start, end

    def _previous(start, end):
        """The window of the same length immediately before this one."""
        s = _dt.datetime.strptime(start, "%Y-%m-%d").date()
        e = _dt.datetime.strptime(end, "%Y-%m-%d").date()
        n = (e - s).days + 1
        pe = s - _dt.timedelta(days=1)
        ps = pe - _dt.timedelta(days=n - 1)
        return ps.strftime("%Y-%m-%d"), pe.strftime("%Y-%m-%d")

    def _marketplaces_for(acc, wsid):
        """Which marketplaces to show, and where the list comes from.

        The account's own list first -- it is what the picker offers, so the
        two cannot disagree. Falling back to whatever has DATA matters for an
        account whose marketplaces have never been detected: showing nothing
        because a config field is empty would hide real sales.
        """
        out = [str(m or "").strip().upper()
               for m in (acc or {}).get("marketplaces") or []
               if str(m or "").strip()]
        seen = set()
        out = [m for m in out if not (m in seen or seen.add(m))]
        try:
            from data import db as _db
            rows = _db.get_db(CONFIG_PATH).execute(
                "SELECT DISTINCT marketplace FROM sales_daily WHERE workspace_id=?",
                (wsid,)).fetchall()
            for r in rows:
                m = str(r[0] or "").strip().upper()
                if m and m not in seen:
                    seen.add(m)
                    out.append(m)
        except Exception:
            pass
        dflt = str((acc or {}).get("default_marketplace") or "").strip().upper()
        if dflt and dflt not in seen:
            out.append(dflt)
        return out

    @app.route("/brand/marketplaces")
    def brand_marketplaces():
        """Every marketplace this account sells in, over one window."""
        from domain import sales_data as _sd
        acc, wsid, _mkt = _scope_mod.resolve(
            state=_state, account=_active_account() or {},
            asked_id=request.args.get("id"),
            asked_marketplace=None,
            load_account=_account_by_id)
        if not wsid or wsid == "_no_account":
            return jsonify({"ok": False, "error": _scope_mod.NO_ACCOUNT}), 400
        start, end = _range()
        pstart, pend = _previous(start, end)
        vat = _sd.vat_rate_for(_cfg, wsid)

        rows = []
        for mkt in _marketplaces_for(acc, wsid):
            try:
                now = _sd.totals(CONFIG_PATH, wsid, mkt, start, end,
                                 vat_rate=vat, basis="order")
                was = _sd.totals(CONFIG_PATH, wsid, mkt, pstart, pend,
                                 vat_rate=vat, basis="order")
            except Exception as e:
                rows.append({"marketplace": mkt, "error": str(e)[:120]})
                continue
            # A marketplace with NOTHING is still listed, quietly. It is the
            # answer to "are we selling there yet", and dropping it would make
            # a marketplace that stopped selling look like one that was never
            # connected.
            rows.append({
                "marketplace": mkt,
                "currency": now.get("currency") or was.get("currency") or "",
                "days": now.get("days") or 0,
                "ordered_sales": now.get("ordered_sales"),
                "units": now.get("units"),
                "orders": now.get("orders"),
                "total_fees": now.get("total_fees"),
                "cogs": now.get("cogs"),
                "profit": now.get("profit"),
                "margin_pct": now.get("margin_pct"),
                "refunds": now.get("refunds"),
                "prev_ordered_sales": was.get("ordered_sales"),
                "prev_units": was.get("units"),
                "prev_profit": was.get("profit"),
            })

        # BY CURRENCY, AND NO GRAND TOTAL. Adding pounds to euros needs a rate
        # and a date; a single number that hides both is one nobody can check.
        by_cur = {}
        for r in rows:
            if r.get("error"):
                continue
            cur = r.get("currency") or ""
            if not cur:
                continue
            b = by_cur.setdefault(cur, {"currency": cur, "marketplaces": 0,
                                        "ordered_sales": 0.0, "units": 0,
                                        "orders": 0, "profit": 0.0,
                                        "profit_complete": True,
                                        "prev_ordered_sales": 0.0})
            b["marketplaces"] += 1
            b["ordered_sales"] += float(r.get("ordered_sales") or 0)
            b["prev_ordered_sales"] += float(r.get("prev_ordered_sales") or 0)
            b["units"] += int(r.get("units") or 0)
            b["orders"] += int(r.get("orders") or 0)
            # A subtotal of profit is only a profit if EVERY row that SOLD
            # something has one. One marketplace with an uncosted SKU makes the
            # whole subtotal an understatement, and an understated profit is
            # the one that gets acted on.
            #
            # A marketplace that sold nothing does NOT make it incomplete. It
            # has no profit because there was no trade, which is a different
            # thing from a profit that could not be worked out -- and calling
            # the euro subtotal "incomplete" because France was quiet would
            # teach the reader to ignore the word where it matters.
            if r.get("profit") is None:
                if float(r.get("ordered_sales") or 0) or int(r.get("units") or 0):
                    b["profit_complete"] = False
            else:
                b["profit"] += float(r["profit"])
        for b in by_cur.values():
            b["ordered_sales"] = round(b["ordered_sales"], 2)
            b["prev_ordered_sales"] = round(b["prev_ordered_sales"], 2)
            b["profit"] = round(b["profit"], 2) if b["profit_complete"] else None
        # A CURRENCY WITH NOTHING IN IT IS NOT A SUBTOTAL. jack_uk had a euro
        # card reading "EUR - 1 marketplace, 0.00, 0 units, 0 orders" beside the
        # real one, because France has a stored row with a currency on it and no
        # sales. Those marketplaces are already named in the "no sales in this
        # period" fold below; a headline card of zeros only makes the one that
        # matters harder to find.
        by_cur = {k: b for k, b in by_cur.items()
                  if b["ordered_sales"] or b["units"] or b["orders"]
                  or b["prev_ordered_sales"]}

        # Biggest first inside each currency; a marketplace with no revenue
        # sorts last rather than being dropped.
        rows.sort(key=lambda r: (r.get("currency") or "zzz",
                                 -(float(r.get("ordered_sales") or 0))))
        return jsonify({
            "ok": True,
            "workspace": wsid,
            "account_label": (acc or {}).get("label") or wsid,
            "start": start, "end": end,
            "prev_start": pstart, "prev_end": pend,
            "rows": rows,
            "by_currency": [by_cur[k] for k in sorted(by_cur)],
            "note": ("Each marketplace in its own currency. There is no total "
                     "across currencies: adding pounds to euros needs an "
                     "exchange rate and a date, and a figure that hides both "
                     "cannot be checked."),
            "source": ("Read from what has already been pulled — this screen "
                       "asks Amazon for nothing."),
        })
