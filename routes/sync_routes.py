"""routes/sync_routes.py -- two-way Amazon<->app sync endpoints (feature 2).

Everything here PROPOSES; the operator confirms per listing. No blind writes in either
direction. Pull and Push are separate paths. Account-gated on LIVE-confirmed capability.
The first live push is intentionally halted (listing/sync.push_to_amazon refuses) until
the gated one-listing test.

register(app, ...) injection pattern (bodies self-contained).
"""
from flask import request, jsonify
import time


def register(app, *, _cfg, _active_account, _records, _ws, _bust_records_cache):
    import domain.accounts as _acc
    from listing import sync as _sync

    # Map a sheet record -> the copy fields sync tracks (handles FIXED + Miles layouts).
    _FIELD_ALIASES = {
        "title": ["Title", "Product Title"],
        "item_highlights": ["Item Highlights"],
        "bullet_1": ["Bullet 1", "Bullet Point 1"], "bullet_2": ["Bullet 2", "Bullet Point 2"],
        "bullet_3": ["Bullet 3", "Bullet Point 3"], "bullet_4": ["Bullet 4", "Bullet Point 4"],
        "bullet_5": ["Bullet 5", "Bullet Point 5"],
        "description": ["Description (HTML)", "Description"],
        "search_terms": ["Search Terms / KW", "Backend Keywords"],
    }

    def _stored_copy(row):
        out = {}
        for f, names in _FIELD_ALIASES.items():
            out[f] = next((row.get(n, "") for n in names if row.get(n, "")), "")
        return out

    def _find_row(sku):
        for r in _records(_ws()):
            if str(r.get("SKU", "")).strip() == sku:
                return r
        return None

    def _regenerated_at(row):
        stamp = str(row.get("Regenerated", "") or "").strip()
        if not stamp:
            return 0
        try:
            return int(time.mktime(time.strptime(stamp[:16], "%Y-%m-%d %H:%M")))
        except Exception:
            return int(time.time())    # stamped but unparseable -> treat as recent

    @app.route("/sync/capabilities")
    def sync_capabilities():
        """Per-account capability so the UI can enable/disable the two buttons and show a
        reason. PULL reflects the LIVE read-test; PUSH is inferred until a real push."""
        cfg = _cfg()
        out = []
        for a in _acc.load_accounts(cfg):
            c = _sync.capability(a)
            out.append({"id": a.get("id"), "label": a.get("label", a.get("id")),
                        "seller_id": a.get("seller_id", ""),
                        "pull_enabled": c["pull_enabled"], "pull_confirmed": c["pull_confirmed"],
                        "push_enabled": c["push_enabled"], "push_confirmed": c["push_confirmed"],
                        "reason": c["reason"]})
        return jsonify({"ok": True, "accounts": out})

    @app.route("/sync/read_test", methods=["POST"])
    def sync_read_test():
        """LIVE READ-ONLY capability confirmation for the active account (getListingsItem on
        a dummy SKU). NOT_FOUND -> pull confirmed; Forbidden -> denied. Confirms PULL only."""
        acc = _active_account()
        if not acc:
            return jsonify({"ok": False, "error": "no active account"}), 400
        if not _acc.has_own_creds(acc):
            return jsonify({"ok": False, "error": "account not connected"}), 400
        try:
            from sp_api.api import ListingsItemsV20210801 as LI
            from sp_api.base import Marketplaces
        except Exception as e:
            return jsonify({"ok": False, "error": f"sp_api unavailable: {e}"}), 500
        mkt = (acc.get("default_marketplace") or "UK").upper()
        mkt = "UK" if mkt == "GB" else mkt
        mid = _acc.marketplace_id(mkt)
        try:
            li = LI(credentials=_acc.account_creds(acc),
                    marketplace=getattr(Marketplaces, mkt, Marketplaces.UK), timeout=60)
            li.get_listings_item(acc.get("seller_id", ""), "SYNC-READTEST-DUMMY",
                                 marketplaceIds=[mid] if mid else None, includedData="summaries")
            status = _sync.CONFIRMED; detail = "unexpected 200"
        except Exception as e:
            m = str(e).lower()
            if "not_found" in m or "not found" in m:
                status = _sync.CONFIRMED; detail = "NOT_FOUND -> read authorised"
            elif "forbidden" in m or "unauthor" in m or "access to requested" in m:
                # A 403 is ambiguous: deactivated (temporary) vs role gap (real). classify()
                # only auto-labels when Amazon says so, else 'blocked_unconfirmed' -- never a guess.
                status = _sync.classify_read_error(str(e)); detail = str(e)[:160]
            else:
                return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}), 502
        _sync.set_pull_result(acc.get("id", ""), status, detail)
        cap = _sync.capability(acc)
        return jsonify({"ok": True, "status": cap["status"], "pull_enabled": cap["pull_enabled"],
                        "reason": cap["reason"], "detail": detail})

    @app.route("/sync/mark_status", methods=["POST"])
    def sync_mark_status():
        """OPERATOR override for the active account's pull status -- name a cause the generic
        403 cannot (e.g. mark a suspended account 'deactivated'). Does NOT touch the Amazon
        account; a later successful re-test clears it."""
        b = request.get_json(force=True) or {}
        status = str(b.get("status", "")).strip()
        note = str(b.get("note", "")).strip()
        acc = _active_account()
        if not acc:
            return jsonify({"ok": False, "error": "no active account"}), 400
        if status not in (_sync.DEACTIVATED, _sync.ROLE_GAP, _sync.BLOCKED_UNCONFIRMED, _sync.UNTESTED):
            return jsonify({"ok": False, "error": "invalid status"}), 400
        _sync.mark_status(acc.get("id", ""), status, note)
        return jsonify({"ok": True, **_sync.capability(acc)})

    @app.route("/sync/status", methods=["POST"])
    def sync_status():
        b = request.get_json(force=True) or {}
        sku = str(b.get("sku", "")).strip()
        acc = _active_account()
        if not acc or not sku:
            return jsonify({"ok": False, "error": "need active account + sku"}), 400
        row = _find_row(sku)
        if not row:
            return jsonify({"ok": False, "error": "sku not in current view"}), 404
        st = _sync.compute_status(acc.get("id", ""), sku, _stored_copy(row), _regenerated_at(row))
        return jsonify({"ok": True, **st})

    @app.route("/sync/pull", methods=["POST"])
    def sync_pull():
        """PROPOSE a pull: fetch Amazon's copy, return it beside the stored copy for a
        side-by-side. Does NOT write to the sheet."""
        b = request.get_json(force=True) or {}
        sku = str(b.get("sku", "")).strip()
        acc = _active_account()
        if not acc or not sku:
            return jsonify({"ok": False, "error": "need active account + sku"}), 400
        row = _find_row(sku)
        if not row:
            return jsonify({"ok": False, "error": "sku not in current view"}), 404
        res = _sync.pull_from_amazon(_cfg(), acc, sku)
        if not res.get("ok"):
            return jsonify(res), 400
        stored = _stored_copy(row)
        st = _sync.compute_status(acc.get("id", ""), sku, stored, _regenerated_at(row))
        return jsonify({"ok": True, "sku": sku, "stored_copy": stored,
                        "amazon_copy": res["amazon_copy"], **st})

    @app.route("/sync/pull/apply", methods=["POST"])
    def sync_pull_apply():
        """Apply chosen Amazon fields INTO the sheet (after the operator reviewed the
        side-by-side). REGEN-SAFETY: never silently overwrite a row that was regenerated
        but not yet pushed -- refuse unless force=true."""
        b = request.get_json(force=True) or {}
        sku = str(b.get("sku", "")).strip()
        fields = b.get("fields") or {}          # {field: value} chosen by the operator
        force = bool(b.get("force"))
        acc = _active_account()
        if not acc or not sku:
            return jsonify({"ok": False, "error": "need active account + sku"}), 400
        row = _find_row(sku)
        if not row:
            return jsonify({"ok": False, "error": "sku not in current view"}), 404
        st = _sync.compute_status(acc.get("id", ""), sku, _stored_copy(row), _regenerated_at(row))
        if st["status"] == _sync.APP_AHEAD and not force:
            return jsonify({"ok": False, "blocked": True, "status": st,
                            "error": "this row is 'Regenerated -- not yet on Amazon'. A pull would "
                                     "overwrite freshly regenerated copy. Confirm force=true only if "
                                     "you intend to discard the regenerated copy."}), 409
        ws = _ws()
        # Was a hardcoded "SKU" literal here rather than the shared header name,
        # so a change to that constant would have broken sync alone, quietly.
        from listing import repo as _repo       # the ONE SKU->row lookup (Rule 12)
        found = _repo.locate(ws, sku)
        if found.error == "no SKU column":
            return jsonify({"ok": False, "error": found.error}), 400
        if not found.ok:
            return jsonify({"ok": False, "error": found.error}), 404
        trow, headers = found.row, found.headers
        applied = []
        from gspread.utils import rowcol_to_a1
        data = []
        for f, val in fields.items():
            names = _FIELD_ALIASES.get(f, [f])
            col = next((headers.index(n) + 1 for n in names if n in headers), None)
            if col:
                data.append({"range": rowcol_to_a1(trow, col), "values": [[val]]})
                applied.append(f)
        if data:
            ws.batch_update(data)
            _bust_records_cache()
        return jsonify({"ok": True, "applied": applied, "note": "pulled Amazon copy into the sheet"})

    @app.route("/sync/push", methods=["POST"])
    def sync_push():
        """PROPOSE a push: return the stored copy beside Amazon's current copy for review.
        No write. The actual write is /sync/push/confirm (currently gated-halted)."""
        b = request.get_json(force=True) or {}
        sku = str(b.get("sku", "")).strip()
        acc = _active_account()
        if not acc or not sku:
            return jsonify({"ok": False, "error": "need active account + sku"}), 400
        cap = _sync.capability(acc)
        if not cap["push_enabled"]:
            return jsonify({"ok": False, "error": "push not enabled: " + cap["reason"]}), 400
        row = _find_row(sku)
        if not row:
            return jsonify({"ok": False, "error": "sku not in current view"}), 404
        snap = _sync._snapshot(acc.get("id", ""), sku)
        return jsonify({"ok": True, "sku": sku, "stored_copy": _stored_copy(row),
                        "amazon_copy": (snap or {}).get("copy", {}),
                        "amazon_known": bool(snap),
                        "warn": None if snap else "Amazon copy unknown (never pulled) -- pull first "
                                                  "so you can see what a push would overwrite."})

    @app.route("/sync/push/confirm", methods=["POST"])
    def sync_push_confirm():
        """LIVE WRITE surface -- gated. Currently HALTED in listing/sync.push_to_amazon
        pending the reviewed one-listing first-push test."""
        b = request.get_json(force=True) or {}
        sku = str(b.get("sku", "")).strip()
        fields = b.get("fields") or {}
        acc = _active_account()
        if not acc or not sku:
            return jsonify({"ok": False, "error": "need active account + sku"}), 400
        res = _sync.push_to_amazon(_cfg(), acc, sku, fields)
        return jsonify(res), (200 if res.get("ok") else 400)
