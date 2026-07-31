"""monitor/checker.py — Stage 3 hourly checker.

For each tracked ASIN x marketplace: fetch live offers (monitor/pricing), diff the seller set
against the stored baseline, raise in-app alerts, and append a snapshot to history. Runs on a
daemon thread while the app is up (catch-up on startup). Read-only surveillance through the
monitor account (default jack_uk). NO Slack, NO external notifications.

State (gitignored asin_monitor_history.json):
  baselines    : {"<asin>::<mkt>": <last fetch_offers result>}   -- for the next diff
  snapshots    : {"<asin>::<mkt>": [ {ts, seller_count, buybox_seller, sellers[], offers[]} ]}
  alerts       : [ {id, ts, type, asin, marketplace, label, seller_id, seller_name, ...} ]
  seller_names : {"<sellerId>::<mkt>": name}   -- one-time storefront resolution cache
"""
import json
import os
import threading
import time
import datetime

from monitor import asin_monitor as _store
from monitor import pricing as _pricing
from monitor import storefront_name as _sf

# An existing seller's landed-price move counts as a change only if it clears BOTH a
# percentage and an absolute floor (avoids alerting on 1p rounding).
PRICE_CHANGE_PCT = 5.0
PRICE_CHANGE_ABS = 1.0
_MONITOR_ACCOUNT_DEFAULT = "jack_uk"
_CALL_PACING_S = 1.5          # spacing between getItemOffers calls (rate-limit friendly)

_LOCK = threading.Lock()
_SCHED_STARTED = False
_STATUS = {"last_run": "", "last_run_ok": None, "checks": 0, "running": False}


# ---------------- storage ----------------
def _hist_path(config_path):
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), "asin_monitor_history.json")


def _load_hist(config_path):
    try:
        with open(_hist_path(config_path), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("baselines", {}); d.setdefault("snapshots", {})
            d.setdefault("alerts", []); d.setdefault("seller_names", {})
            return d
    except Exception:
        pass
    return {"baselines": {}, "snapshots": {}, "alerts": [], "seller_names": {}}


def _save_hist(config_path, d):
    with open(_hist_path(config_path), "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _key(asin, mkt):
    return f"{asin}::{mkt}"


# ---------------- public read API (routes use these) ----------------
def get_alerts(config_path, unread_only=False, limit=100):
    al = _load_hist(config_path).get("alerts", [])
    if unread_only:
        al = [a for a in al if not a.get("read")]
    return list(reversed(al))[:limit]        # newest first


def unread_count(config_path):
    return sum(1 for a in _load_hist(config_path).get("alerts", []) if not a.get("read"))


def mark_alerts_read(config_path, ids=None):
    with _LOCK:
        d = _load_hist(config_path)
        idset = {str(i) for i in ids} if ids else None
        for a in d.get("alerts", []):
            if idset is None or str(a.get("id")) in idset:
                a["read"] = True
        _save_hist(config_path, d)
    return True


def get_history(config_path, asin, marketplace=None, limit=60):
    d = _load_hist(config_path)
    out = {}
    for k, snaps in d.get("snapshots", {}).items():
        a, m = k.split("::", 1)
        if a != str(asin).strip().upper():
            continue
        if marketplace and m != str(marketplace).upper():
            continue
        out[k] = snaps[-limit:]
    return out


def status():
    return dict(_STATUS)


# ---------------- the diff ----------------
def diff(prev, cur):
    """prev/cur = fetch_offers results (prev None on first check). Returns event dicts."""
    events = []
    cur_off = {o["seller_id"]: o for o in cur.get("offers", []) if o.get("seller_id")}
    if not prev:
        return events                          # first check -> baseline only, no alerts
    prev_off = {o["seller_id"]: o for o in prev.get("offers", []) if o.get("seller_id")}
    for sid, co in cur_off.items():
        if sid not in prev_off:
            events.append({"type": "new_seller", "seller_id": sid, "offer": co})
    for sid, po in prev_off.items():
        if sid not in cur_off:
            events.append({"type": "seller_removed", "seller_id": sid, "offer": po})
    for sid, co in cur_off.items():
        po = prev_off.get(sid)
        if not po:
            continue
        a, b = po.get("landed"), co.get("landed")
        if a is None or b is None:
            continue
        if abs(b - a) >= PRICE_CHANGE_ABS and (a == 0 or abs(b - a) / a * 100.0 >= PRICE_CHANGE_PCT):
            events.append({"type": "price_change", "seller_id": sid, "offer": co, "from": a, "to": b})
    pbb = (prev.get("summary") or {}).get("buybox_seller")
    cbb = (cur.get("summary") or {}).get("buybox_seller")
    if cbb and pbb != cbb:
        events.append({"type": "buybox_change", "seller_id": cbb,
                       "offer": cur_off.get(cbb, {}), "from": pbb, "to": cbb})
    return events


# ---------------- alert building ----------------
def _next_alert_id(d):
    mx = 0
    for a in d.get("alerts", []):
        try:
            mx = max(mx, int(a.get("id", 0)))
        except Exception:
            pass
    return mx + 1


def _seller_name(d, sid, mkt, resolve):
    """Cached seller-name lookup. `resolve`=True does the one-time storefront fetch (isolated
    module); result cached (even "" so we don't re-hit Amazon every hour)."""
    if not sid:
        return ""
    names = d.setdefault("seller_names", {})
    k = f"{sid}::{mkt}"
    if k in names:
        return names[k]
    nm = _sf.resolve_seller_name(sid, mkt) if resolve else ""
    if resolve:
        names[k] = nm
    return nm


def _fmt_price(o):
    lp = o.get("landed")
    if lp is None:
        return ""
    cur = o.get("currency", "")
    chan = "FBA" if o.get("fba") else "FBM"
    fb = ""
    if o.get("feedback_pct") is not None:
        fb = f", {o.get('feedback_pct')}% ({o.get('feedback_count')})"
    return f"{lp} {cur} ({chan}{fb})"


def _detail(ev, o, mkt):
    t = ev["type"]
    if t == "new_seller":
        return f"New seller {ev['seller_id']} — {_fmt_price(o)}"
    if t == "seller_removed":
        return f"Seller {ev['seller_id']} left the listing"
    if t == "price_change":
        return f"{ev['seller_id']} price {ev.get('from')}→{ev.get('to')} {o.get('currency','')}"
    if t == "buybox_change":
        frm = ev.get("from") or "(none)"
        return f"Buy Box changed hands: {frm} → {ev['seller_id']}"
    return t


def _make_alert(d, item, mkt, ev):
    o = ev.get("offer") or {}
    sid = ev.get("seller_id", "")
    resolve = ev["type"] in ("new_seller", "buybox_change")   # resolve name only when it matters
    name = _seller_name(d, sid, mkt, resolve)
    return {
        "id": _next_alert_id(d), "ts": _now(), "type": ev["type"],
        "asin": item.get("asin"), "marketplace": mkt, "label": item.get("label", ""),
        "seller_id": sid, "seller_name": name,
        "price": o.get("landed"), "currency": o.get("currency", ""),
        "fba": o.get("fba"), "condition": o.get("condition", ""), "buybox": o.get("buybox"),
        "feedback_pct": o.get("feedback_pct"), "feedback_count": o.get("feedback_count"),
        "storefront": _sf.storefront_url(sid, mkt) if sid else "",
        "detail": _detail(ev, o, mkt), "read": False,
    }


# ---------------- the check ----------------
def _resolve_creds(cfg, config_path):
    import accounts as _acc
    aid = cfg.get("asin_monitor_account") or _MONITOR_ACCOUNT_DEFAULT
    acc = _acc.get_account(cfg, aid, config_path) if hasattr(_acc, "get_account") else None
    if not acc:
        return None, f"monitor account '{aid}' not found"
    try:
        return _acc.account_creds(acc), ""
    except Exception as e:
        return None, f"could not build creds for {aid}: {str(e)[:120]}"


def check_all(cfg, config_path, log=print):
    """One full pass over every tracked ASIN x marketplace. Returns a summary dict."""
    if cfg.get("asin_monitor_enabled", True) is False:
        return {"ok": False, "error": "monitoring disabled (asin_monitor_enabled=false)"}
    items = _store.list_asins(config_path)
    if not items:
        _STATUS.update(last_run=_now(), last_run_ok=True, checks=0)
        return {"ok": True, "checks": 0, "note": "no ASINs tracked"}
    creds, err = _resolve_creds(cfg, config_path)
    if err:
        _STATUS.update(last_run=_now(), last_run_ok=False)
        log("[asin-monitor] " + err)
        return {"ok": False, "error": err}

    _STATUS["running"] = True
    checks, new_alerts, fails = 0, 0, 0
    try:
        with _LOCK:
            d = _load_hist(config_path)
        for it in items:
            asin = it.get("asin")
            cond = it.get("condition", "New")
            for mkt in (it.get("marketplaces") or _store.EU_MARKETPLACES):
                res = _pricing.fetch_offers(creds, asin, mkt, cond)
                checks += 1
                if not res.get("ok"):
                    fails += 1
                    log(f"[asin-monitor] {asin} {mkt}: {res.get('error')}")
                    time.sleep(_CALL_PACING_S)
                    continue
                k = _key(asin, mkt)
                prev = d["baselines"].get(k)
                for ev in diff(prev, res):
                    d["alerts"].append(_make_alert(d, it, mkt, ev))
                    new_alerts += 1
                d["snapshots"].setdefault(k, []).append({
                    "ts": _now(),
                    "seller_count": res["summary"].get("seller_count"),
                    "total_offer_count": res["summary"].get("total_offer_count"),
                    "buybox_seller": res["summary"].get("buybox_seller"),
                    "sellers": [o["seller_id"] for o in res["offers"]],
                    "offers": res["offers"],
                })
                d["snapshots"][k] = d["snapshots"][k][-200:]     # cap history per key
                d["baselines"][k] = res
                time.sleep(_CALL_PACING_S)
        d["alerts"] = d["alerts"][-1000:]
        with _LOCK:
            _save_hist(config_path, d)
        _STATUS.update(last_run=_now(), last_run_ok=(fails == 0), checks=checks)
        return {"ok": True, "checks": checks, "alerts": new_alerts, "fails": fails}
    finally:
        _STATUS["running"] = False


def check_now_async(cfg, config_path):
    """Run a full check on a background thread (for the 'Check now' button)."""
    if _STATUS.get("running"):
        return {"ok": False, "error": "a check is already running"}
    threading.Thread(target=lambda: check_all(cfg, config_path),
                     daemon=True, name="asin-monitor-now").start()
    return {"ok": True, "started": True}


# ---------------- scheduler ----------------
def start_scheduler(cfg_getter, config_path, interval=3600, initial_delay=25):
    """Start the hourly daemon loop once. cfg_getter is a callable returning current config."""
    global _SCHED_STARTED
    if _SCHED_STARTED:
        return
    _SCHED_STARTED = True

    def _loop():
        time.sleep(initial_delay)                 # let the app finish booting
        while True:
            try:
                cfg = cfg_getter() if callable(cfg_getter) else cfg_getter
                check_all(cfg, config_path)
            except Exception as e:
                print("[asin-monitor] scheduler error:", str(e)[:200])
            time.sleep(interval)

    threading.Thread(target=_loop, daemon=True, name="asin-monitor").start()
