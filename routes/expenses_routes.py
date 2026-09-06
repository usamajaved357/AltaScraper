"""routes/expenses_routes.py -- the costs Amazon knows nothing about.

    GET    /expenses            everything recorded, and what it comes to here
    POST   /expenses            add one
    POST   /expenses/update     change one
    POST   /expenses/delete     remove one
    POST   /expenses/accept     take the suggested Amazon subscription

Its own file because it is its own feature (CLAUDE.md Rule 7). The arithmetic --
how a monthly amount is apportioned across a window -- belongs to
domain/expenses.py and is not repeated here (Rule 12).

WHY THIS EXISTS AT ALL. The P&L is built from what Amazon reports, and Amazon
reports nothing about the accountant, the software, the packaging or the postage
bought elsewhere. It also charges a monthly selling subscription against the
ACCOUNT rather than any order, so every order-joined fee query in the app is
blind to it by construction -- measured at 60.00 on nestwell_goods, against
1.28 of "other" fees the per-order query could see.
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
        return aid, mkt

    def _window():
        import datetime as _dt
        start = (request.args.get("start") or "").strip()
        end = (request.args.get("end") or "").strip()
        if start and end:
            return start, end
        today = _dt.date.today()
        return today.replace(day=1).isoformat(), today.isoformat()

    @app.route("/expenses")
    def expenses_list():
        """Everything recorded, plus what falls inside the window asked for.

        Both, deliberately: a cost recorded but outside the window still exists
        and should be visible, or somebody adds it twice.
        """
        from domain import expenses as _exp

        aid, mkt = _scope()
        if not aid:
            return jsonify({"ok": False,
                            "error": "open an account first"}), 400
        start, end = _window()
        try:
            window = _exp.for_window(CONFIG_PATH, aid, mkt or None, start, end)
            suggested = (_exp.suggest(CONFIG_PATH, aid, mkt, start, end)
                         if mkt else None)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500
        return jsonify({
            "ok": True, "account": aid, "marketplace": mkt,
            "start": start, "end": end,
            "all": _exp.all_for(CONFIG_PATH, aid, mkt or None),
            "window": window,
            # The Amazon charge that belongs to no order, offered ready to add
            # rather than described in a note somebody has to act on.
            "suggested": suggested,
            "note": ("A monthly amount is shared out across the days of it that "
                     "fall inside the window, so a fortnight carries half a "
                     "month's subscription rather than all of it."),
        })

    @app.route("/expenses", methods=["POST"])
    def expenses_add():
        from domain import expenses as _exp

        aid, mkt = _scope()
        if not aid:
            return jsonify({"ok": False,
                            "error": "open an account first"}), 400
        b = request.get_json(force=True) or {}
        # A blank marketplace means the whole account, which is right for an
        # accountant's fee and wrong for nothing.
        new_id, why = _exp.add(
            CONFIG_PATH, aid,
            name=b.get("name"), amount=b.get("amount"),
            starts=b.get("starts"),
            marketplace=(str(b.get("marketplace") or "").strip().upper() or None),
            category=b.get("category") or "", currency=b.get("currency") or "",
            ends=b.get("ends") or None, note=b.get("note") or "")
        if why:
            return jsonify({"ok": False, "error": why}), 400
        return jsonify({"ok": True, "id": new_id})

    @app.route("/expenses/update", methods=["POST"])
    def expenses_update():
        from domain import expenses as _exp

        aid, _mkt = _scope()
        b = request.get_json(force=True) or {}
        eid = b.get("id")
        if not aid or not eid:
            return jsonify({"ok": False,
                            "error": "need an account and an id"}), 400
        fields = {k: v for k, v in b.items()
                  if k in ("name", "category", "amount", "currency", "starts",
                           "ends", "note", "marketplace")}
        n, why = _exp.update(CONFIG_PATH, aid, eid, **fields)
        if why:
            return jsonify({"ok": False, "error": why}), 400
        if not n:
            return jsonify({"ok": False,
                            "error": "no cost of that id in this account"}), 404
        return jsonify({"ok": True, "updated": n})

    @app.route("/expenses/delete", methods=["POST"])
    def expenses_delete():
        from domain import expenses as _exp

        aid, _mkt = _scope()
        b = request.get_json(force=True) or {}
        eid = b.get("id")
        if not aid or not eid:
            return jsonify({"ok": False,
                            "error": "need an account and an id"}), 400
        n = _exp.remove(CONFIG_PATH, aid, eid)
        if not n:
            return jsonify({"ok": False,
                            "error": "no cost of that id in this account"}), 404
        return jsonify({"ok": True, "deleted": n,
                        "note": "Profit for every window this cost touched "
                                "will go up by its share of it."})

    @app.route("/expenses/accept", methods=["POST"])
    def expenses_accept():
        """Take the suggested Amazon subscription as a recorded monthly cost.

        One press instead of reading a figure out of a note and retyping it.
        Re-checks the suggestion rather than trusting what the browser sends --
        a stale page would otherwise record a number that is no longer right.
        """
        from domain import expenses as _exp

        aid, mkt = _scope()
        if not aid or not mkt:
            return jsonify({"ok": False, "error": (
                "open an account and pick a marketplace — this charge belongs "
                "to one marketplace's account")}), 400
        start, end = _window()
        s = _exp.suggest(CONFIG_PATH, aid, mkt, start, end)
        if not s:
            return jsonify({"ok": False, "error": (
                "there is nothing to add: either Amazon has charged nothing "
                "outside the orders in this window, or a matching cost is "
                "already recorded")}), 400
        new_id, why = _exp.add(CONFIG_PATH, aid, name=s["name"],
                               amount=s["amount"], starts=s["starts"],
                               marketplace=mkt, category=s["category"],
                               note="Added from the P&L's unattributed Amazon "
                                    "charge for %s to %s." % (start, end))
        if why:
            return jsonify({"ok": False, "error": why}), 400
        return jsonify({"ok": True, "id": new_id, "amount": s["amount"],
                        "note": "Recorded as a monthly cost. It is subtracted "
                                "from profit from now on, apportioned across "
                                "whatever window you ask for."})
