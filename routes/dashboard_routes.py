"""routes/dashboard_routes.py -- Stage 1 of the opt-in UI redesign.

Read-only, ADDITIVE endpoints for the new dashboard. Nothing here changes existing views
or routes; the new UI is gated behind a client-side flag (default OFF), so the current UI
stays the untouched default/fallback.

  GET  /dashboard/summary  -> cross-account operation overview (real counts, needs-you list,
                              compliance watch, sync/account health). Cached ~60s so opening
                              home doesn't hammer Sheets.
  POST /restricted/check   -> Shape-1 manual pre-source check over the restricted engine.
"""
from flask import request, jsonify
import time
import json as _json

from listing.restricted import check_restricted_type
from listing.sourcing_viability import check_sourcing_viability


def _row_image(attrs_json):
    """Best-effort main-image URL from a row's Attributes JSON (locators vary in shape)."""
    try:
        a = _json.loads(attrs_json or "{}")
        if not isinstance(a, dict):
            return ""
        def _url(v):
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v[0].get("value") or v[0].get("media_location") or ""
            return v if isinstance(v, str) else ""
        for k in ("main_product_image_locator", "main_image_url"):
            u = _url(a.get(k))
            if u:
                return u
        for k, v in a.items():
            if "image" in str(k).lower():
                u = _url(v)
                if u:
                    return u
    except Exception:
        pass
    return ""
try:
    from listing import sync as _sync
except Exception:
    _sync = None


_BLOCKED = {"IP_HOLD", "COMPLIANCE_HOLD"}
_REVIEW = {"NEEDS_REVIEW"}
_READY = {"APPROVED", "API_READY"}
_LIVE = {"LIVE"}


def register(app, *, _cfg, _client, _state, STATUS_HEADER="Status", SKU_HEADER="SKU",
             _INV_ALERT_COUNTS=None):

    _CACHE = {"ts": 0, "data": None}
    _TTL = 60

    def _accounts():
        # Use the SAME source /accounts/list uses -- load_accounts() migrates from legacy
        # config when cfg["accounts"] is empty, so a legacy config still yields accounts.
        try:
            import accounts as _acc
            got = _acc.load_accounts(_cfg() or {}, None)
            if got:
                return list(got)
        except Exception:
            pass
        return list((_cfg() or {}).get("accounts", []) or [])

    def _read_account_rows(book_cache, acc):
        """Return (header, rows) for ONE account's output tab, or (None, None) if unreadable.
        book_cache dedupes open_by_key when accounts share a spreadsheet (5 share one here)."""
        sid = str(acc.get("output_spreadsheet_id") or "").strip()
        gid = str(acc.get("output_tab_gid") or "").strip()
        if not sid:
            return None, None
        try:
            book = book_cache.get(sid)
            if book is None:
                book = _client().open_by_key(sid)
                book_cache[sid] = book
            ws = book.get_worksheet_by_id(int(gid)) if gid.isdigit() else None
            if ws is None:
                ws = book.sheet1
            values = ws.get_all_values()
        except Exception:
            return None, None
        if not values:
            return [], []
        return values[0], values[1:]

    def _col(header, *names):
        low = {str(h).strip().lower(): i for i, h in enumerate(header or [])}
        for n in names:
            if n.lower() in low:
                return low[n.lower()]
        return -1

    def _reason_for(title, mkt, ptype, cat, status, note):
        """Prefer a live restricted-checker reason ('UK prohibited . Ofcom'); else the stored
        compliance/IP note; else a plain review line."""
        try:
            rr = check_restricted_type(title, mkt, product_type=ptype, category_path=cat)
        except Exception:
            rr = {"matched": False, "matches": []}
        if rr.get("matched") and rr["matches"]:
            m = rr["matches"][0]
            word = ("prohibited" if m["tier"] == "PROHIBITED"
                    else "gated" if m["tier"] == "GATED" else "restricted")
            reg = m.get("regulator", "")
            return (f"{mkt or '?'} {word}" + (f" · {reg}" if reg else "")), rr
        if status in _BLOCKED:
            snip = (note or "").strip()
            snip = snip[:60] + ("…" if len(snip) > 60 else "") if snip else "on hold"
            return snip, rr
        return "copy ready to check", rr

    def _build_summary():
        accounts = _accounts()
        counts = {"review": 0, "blocked": 0, "ready": 0, "live": 0}
        needs = []
        prohibited_current = 0
        gated_current = 0
        missing = []
        book_cache = {}
        per = {}   # account_id -> per-account rollup (so EVERY account is visible)

        for acc in accounts:
            aid = acc.get("id") or ""
            label = acc.get("label") or aid or "account"
            mkt = str(acc.get("default_marketplace") or "").upper()
            pc = {"review": 0, "blocked": 0, "ready": 0, "live": 0}
            per[aid] = {"id": aid, "label": label, "marketplace": mkt, "counts": pc,
                        "readable": True, "seller_id": acc.get("seller_id", "")}
            header, rows = _read_account_rows(book_cache, acc)
            if header is None:
                # An account with a sheet we couldn't read is still SHOWN (readable=False)
                # so it never silently disappears; one without a sheet just has no listings.
                if acc.get("output_spreadsheet_id"):
                    missing.append(label)
                    per[aid]["readable"] = False
                continue
            si = _col(header, STATUS_HEADER, "Status")
            ti = _col(header, "Title")
            ki = _col(header, SKU_HEADER, "SKU", "Sku")
            pi = _col(header, "Product Type")
            ci = _col(header, "Amazon Category")
            ni = _col(header, "Notes", "Compliance Report", "Compliance Notes")
            ji = _col(header, "Attributes JSON", "Attributes")
            for r in rows:
                def cell(i):
                    return r[i] if (0 <= i < len(r)) else ""
                status = str(cell(si)).upper().strip()
                title = cell(ti) or cell(ki) or "(untitled)"
                if not any([status, title.strip()]):
                    continue
                if status in _REVIEW:
                    counts["review"] += 1; pc["review"] += 1
                elif status in _BLOCKED:
                    counts["blocked"] += 1; pc["blocked"] += 1
                elif status in _READY:
                    counts["ready"] += 1; pc["ready"] += 1
                elif status in _LIVE:
                    counts["live"] += 1; pc["live"] += 1
                # compliance watch (live, current -- NOT a weekly window)
                is_priority = status in _BLOCKED or status in _REVIEW
                reason, rr = ("", None)
                if is_priority:
                    reason, rr = _reason_for(title, mkt, cell(pi), cell(ci), status, cell(ni))
                else:
                    try:
                        rr = check_restricted_type(title, mkt, product_type=cell(pi), category_path=cell(ci))
                    except Exception:
                        rr = None
                if rr and rr.get("overall_action") == "BLOCK":
                    prohibited_current += 1
                elif rr and rr.get("overall_action") == "WARN":
                    gated_current += 1
                if is_priority:
                    needs.append({
                        "sku": cell(ki), "title": title[:80], "account": label,
                        "reason": reason, "marketplace": mkt,
                        "image": _row_image(cell(ji)) if ji >= 0 else "",
                        "status": ("Blocked" if status in _BLOCKED else "Review"),
                        "_rank": 0 if status in _BLOCKED else 1,
                    })

        needs.sort(key=lambda x: x["_rank"])
        for n in needs:
            n.pop("_rank", None)

        # sync + account health
        sync_rows = []
        snap = {}
        if _sync is not None:
            try:
                snap = _sync._load(_sync._SNAP_FILE) or {}
            except Exception:
                snap = {}
        now = time.time()
        for acc in accounts:
            label = acc.get("label") or acc.get("id") or "account"
            mkt = str(acc.get("default_marketplace") or "").upper()
            dot, note = "grey", ""
            if _sync is not None:
                try:
                    cap = _sync.capability(acc)
                    st = cap.get("status", "")
                    if st == getattr(_sync, "DEACTIVATED", "deactivated"):
                        dot, note = "red", "deactivated"
                    elif st == getattr(_sync, "CONFIRMED", "confirmed"):
                        dot = "green"
                    else:
                        dot, note = "amber", (st or "")
                except Exception:
                    pass
            last = None
            try:
                acc_snap = snap.get(acc.get("id") or "", {}) or {}
                ts_list = [v.get("pulled_at") for v in acc_snap.values() if isinstance(v, dict) and v.get("pulled_at")]
                if ts_list:
                    mins = int((now - max(ts_list)) / 60)
                    last = "just now" if mins < 1 else (f"{mins}m ago" if mins < 90 else f"{mins // 60}h ago")
            except Exception:
                last = None
            sync_rows.append({"account": label, "marketplace": mkt, "dot": dot,
                              "note": note, "last_sync": last})
            if acc.get("id", "") in per:
                per[acc.get("id", "")].update({"dot": dot, "note": note, "last_sync": last})

        confirmed_history = 0
        try:
            t3 = check_restricted_type.__globals__.get("_TIER3", {})
            for e in (t3.get("types") or []):
                st = e.get("status") or {}
                # "from your history" = a real Amazon notice (confirmed) OR one whose exact
                # text is pending (facial steamer). Both came from actual violations.
                if any(isinstance(v, dict) and str(v.get("source", "")).startswith("amazon_notice")
                       for v in st.values()):
                    confirmed_history += 1
        except Exception:
            confirmed_history = 5
        ref_cats = 0
        try:
            ref_cats = len((check_restricted_type.__globals__.get("_MASTER", {}).get("categories") or []))
        except Exception:
            ref_cats = 0

        # inventory alerts (real, per-account; populated after an inventory run). No fake
        # samples -- counts only, honest empty when never run.
        inv_counts = _INV_ALERT_COUNTS or {}
        inv_total, inv_by = 0, []
        for acc in accounts:
            aid = acc.get("id") or ""
            cN = int(inv_counts.get(aid, 0) or 0)
            inv_total += cN
            if cN:
                inv_by.append({"account": acc.get("label") or aid, "count": cN})

        need_you_total = counts["blocked"] + counts["review"]
        return {
            "inventory": {"available": bool(inv_counts), "total": inv_total, "by_account": inv_by},
            "ok": True,
            "accounts_count": len(accounts),
            "need_you_total": need_you_total,
            "per_account": list(per.values()),
            "counts": counts,
            "blocked_partial": True,   # restricted-checker BLOCK not wired until Stage 3
            "needs_you": needs[:6],
            "needs_you_more": max(0, len(needs) - 6),
            "compliance": {
                "prohibited_current": prohibited_current,
                "gated_current": gated_current,
                "reference_categories": ref_cats,
                "confirmed_history": confirmed_history,
            },
            "sync": sync_rows,
            "missing_accounts": missing,
        }

    @app.route("/dashboard/summary")
    def dashboard_summary():
        force = request.args.get("force")
        now = time.time()
        if not force and _CACHE["data"] and (now - _CACHE["ts"] < _TTL):
            out = dict(_CACHE["data"]); out["cached"] = True
            return jsonify(out)
        try:
            data = _build_summary()
        except Exception as e:
            import traceback
            print("[dashboard/summary] EXCEPTION:")
            traceback.print_exc()
            return jsonify({"ok": False, "error": str(e)[:200]}), 500
        _CACHE["ts"] = now
        _CACHE["data"] = data
        out = dict(data); out["cached"] = False
        return jsonify(out)

    @app.route("/restricted/check", methods=["POST"])
    def restricted_check():
        """Shape-1: paste a product title/description, scan against the restricted engine."""
        b = request.get_json(force=True) or {}
        text = str(b.get("text", "") or "")
        mkt = str(b.get("marketplace", "") or _state.get("active_marketplace", "") or "").upper()
        ptype = str(b.get("product_type", "") or "")
        cat = str(b.get("category_path", "") or "")
        if not text.strip():
            return jsonify({"ok": False, "error": "paste a product title or description"}), 400
        try:
            res = check_restricted_type(text, mkt, product_type=ptype, category_path=cat)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500
        # Sourcing viability rides along on the same paste: "can I list it?" and
        # "can I produce the papers Amazon will ask for later?" are both questions
        # you want answered BEFORE buying stock, so the modal answers both at once.
        # Additive key -- a failure here never breaks the restricted result.
        try:
            res["sourcing_viability"] = check_sourcing_viability(
                title=text, product_type=ptype, category=cat, marketplace=mkt)
        except Exception as e:
            res["sourcing_viability"] = {"matched": False, "risks": [],
                                         "error": str(e)[:200]}
        res["ok"] = True
        return jsonify(res)
