"""monitor/checker.py — Stage 3 hourly checker.

For each tracked ASIN x marketplace: fetch live offers (monitor/pricing), diff the seller set
against the stored baseline, raise in-app alerts, and append a snapshot to history. Runs on a
daemon thread while the app is up (catch-up on startup). Read-only surveillance through the
monitor account (default jack_uk). NO Slack, NO external notifications.

State (gitignored asin_monitor_history.json):
  baselines    : {"<asin>::<mkt>": <last fetch_offers_batch result>}  -- for the next diff
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
from monitor import known_sellers as _ks

# An existing seller's landed-price move counts as a change only if it clears BOTH a
# percentage and an absolute floor (avoids alerting on 1p rounding).
PRICE_CHANGE_PCT = 5.0
PRICE_CHANGE_ABS = 1.0
_MONITOR_ACCOUNT_DEFAULT = "jack_uk"
_CALL_PACING_S = 1.5          # (legacy single-call pacing; batch path uses _BATCH_PACING_S)
_BATCH_SIZE = 20              # getItemOffersBatch does up to 20 (asin x marketplace) per call
_BATCH_PACING_S = 2.0         # spacing between batch calls (the batch endpoint is heavier)
# HOW LONG A MARKETPLACE WITH NO OFFERS IS LEFT ALONE.
#
# This was 24 hours, and the scheduler below also runs every 24 hours -- so a
# marketplace already known to have nothing was re-checked on EVERY cycle and
# the resting never actually rested anything. Found while running a listing
# through the pipeline: the log filled with
#
#     [asin-monitor] B0DR96KVM2 IE: Bad Request
#     [asin-monitor] B0CJ39XVF1 UK..IE: QuotaExceeded
#
# ten marketplaces deep for ASIN after ASIN, and the quota it spent was the
# quota the generate and preview steps were waiting on.
#
# A week. A competitor expanding into Ireland is worth catching; it is not worth
# catching within a day at the price of everything else, and "Check now" still
# forces an immediate scan of everything.
_RESCAN_DEAD_AFTER = 7 * 24 * 3600
_SCHED_INTERVAL = 24 * 3600   # set by start_scheduler; used for next-run ETA + overload warning

# MINIMUM GAP BETWEEN CHECKS OF THE SAME LIVE MARKETPLACE.
#
# This did not exist. A LIVE marketplace was re-checked on EVERY cycle, and the
# cycle ran hourly -- so every tracked ASIN in every marketplace it sells in was
# hitting Amazon 24 times a day. With a few dozen ASINs across a dozen
# marketplaces that is the single largest consumer of the SP-API quota in the
# app, and it competes with the live-catalogue refresh and with anything the user
# is actually waiting on.
#
# Hijackers and buy-box changes do not need hourly detection to be useful; daily
# is what this is for. Pressing "Check now" still forces an immediate scan, so
# nothing is lost when you genuinely want an answer.
_MIN_RECHECK_LIVE = 24 * 3600

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


def get_seller_names(config_path):
    """The cached SellerId->name map ({'<sellerId>::<mkt>': name}) for enriching the history
    view. Read-only; never triggers a fetch."""
    return _load_hist(config_path).get("seller_names", {})


def seller_info(config_path, cfg, seller_id):
    """Everything the Label modal needs: the seller's CURRENT global classification + name, its
    FOOTPRINT across stored data (how many ASINs / marketplaces it appears on = the blast radius of
    a label), and evidence for the misclassification warning. Read-only."""
    sid = str(seller_id or "").strip()
    d = _load_hist(config_path)
    snaps = d.get("snapshots", {})
    names = d.get("seller_names", {})
    asins, mkts, latest = set(), set(), None
    for key, slist in snaps.items():
        if not slist or "::" not in key:
            continue
        a, m = key.split("::", 1)
        for o in (slist[-1].get("offers") or []):
            if o.get("seller_id") == sid:
                asins.add(a); mkts.add(m); latest = o
    cur = _ks.current(cfg, sid)
    resolved = _ks.name_for(sid, cfg) or next((v for k, v in names.items()
                                               if k.startswith(sid + "::") and v), "")
    if cur["kind"] == "amazon":
        name = "Amazon"
    elif cur["kind"] in ("me", "authorised"):
        name = cur["label"]
    else:
        name = resolved
    return {"seller_id": sid, "kind": cur["kind"], "name": name,
            "footprint": {"asin_count": len(asins), "marketplace_count": len(mkts),
                          "asins": sorted(asins), "marketplaces": sorted(mkts)},
            "evidence": ({"feedback_count": latest.get("feedback_count"),
                          "fba": bool(latest.get("fba"))} if latest else {})}


def log_manual_label(config_path, entry):
    """Append a manual-classification entry to the audit log (who/what/when/previous)."""
    with _LOCK:
        d = _load_hist(config_path)
        d.setdefault("manual_labels", []).append(entry)
        d["manual_labels"] = d["manual_labels"][-500:]
        _save_hist(config_path, d)


def get_manual_labels(config_path, limit=100):
    return list(reversed(_load_hist(config_path).get("manual_labels", [])))[:limit]


def overview(config_path, cfg):
    """Per-tracked-ASIN latest offer picture with every seller classified me/amazon/authorised/
    unknown, plus a top summary ('is anyone sitting on my listings right now'). Read-only: uses
    the stored snapshots + the cached names; no live Amazon calls."""
    d = _load_hist(config_path)
    names = d.get("seller_names", {})
    known_names = _ks.load(cfg).get("names", {})    # manually-stored names (editable in config)
    snaps = d.get("snapshots", {})
    mstate = d.get("market_state", {})
    items = _store.list_asins(config_path)
    rows, total_unknown, unknowns = [], set(), []
    n_clean = n_unknown = n_checked = 0

    def _first_seen(slist, sid):
        for snap in slist:                          # slist is oldest -> newest
            if sid in (snap.get("sellers") or []):
                return snap.get("ts", "")
        return (slist[-1].get("ts", "") if slist else "")
    for it in items:
        asin = it.get("asin")
        per_mkt, asin_unknown, asin_checked = [], False, False
        for mkt in (it.get("marketplaces") or _store.EU_MARKETPLACES):
            se = mstate.get(_key(asin, mkt)) or {}
            live = se.get("live")                  # True=has offers, False=dead(skipped), None=never checked
            last_checked = se.get("last_checked", "")
            slist = snaps.get(_key(asin, mkt)) or []
            if not slist:
                # never got offers: not checked yet, a known-dead marketplace we now skip, or a
                # check that failed (transient error) -- surface each honestly, never "undefined".
                per_mkt.append({"marketplace": mkt, "checked": bool(se), "live": bool(live),
                                "skipped": (live is False), "error": se.get("last_error", ""),
                                "seller_count": 0, "sellers": [], "ts": "",   # never undefined
                                "last_checked": last_checked})
                continue
            asin_checked = True
            snap = slist[-1]
            bb = snap.get("buybox_seller")
            sellers = []
            for o in (snap.get("offers") or []):
                sid = o.get("seller_id")
                if not sid:
                    continue
                nm = names.get(f"{sid}::{mkt}", "") or known_names.get(sid, "")
                cls = _ks.classify(sid, mkt, cfg, name=nm)
                unknown = cls["kind"] == "unknown"
                if unknown:
                    asin_unknown = True
                    total_unknown.add(f"{sid}::{mkt}")
                    fc = o.get("feedback_count")
                    new_acct = (fc is None or fc == 0)
                    unknowns.append({
                        "asin": asin, "label": it.get("label", ""), "marketplace": mkt,
                        "seller_id": sid, "name": nm, "buybox": (sid == bb),
                        "price": o.get("landed"), "currency": o.get("currency", ""),
                        "fba": bool(o.get("fba")),
                        "feedback_pct": o.get("feedback_pct"), "feedback_count": fc,
                        "new_account": new_acct,                   # classic new-hijacker signature
                        # HIGH RISK: FBA + zero feedback + holding the Buy Box on my listing =
                        # a brand-new account with physical stock of my product winning the sale.
                        "high_risk": (bool(o.get("fba")) and new_acct and (sid == bb)),
                        "first_seen": _first_seen(slist, sid),
                        "storefront": _sf.storefront_url(sid, mkt)})
                sellers.append({"id": sid, "kind": cls["kind"], "label": cls["label"],
                                "buybox": (sid == bb), "fba": bool(o.get("fba")),
                                "feedback_pct": o.get("feedback_pct"),
                                "feedback_count": o.get("feedback_count"),
                                "storefront": _sf.storefront_url(sid, mkt) if unknown else ""})
            # Buy-Box first, then me, Amazon, authorised, unknown last (the eye lands on threats)
            _ord = {"me": 1, "amazon": 2, "authorised": 3, "unknown": 4}
            sellers.sort(key=lambda s: (0 if s["buybox"] else 1, _ord.get(s["kind"], 5)))
            per_mkt.append({"marketplace": mkt, "checked": True, "ts": snap.get("ts"),
                            "seller_count": len(sellers), "sellers": sellers,
                            "live": (live is not False), "skipped": (live is False),
                            "last_checked": last_checked})
        if asin_checked:
            n_checked += 1
            n_unknown += 1 if asin_unknown else 0
            n_clean += 0 if asin_unknown else 1
        rows.append({"asin": asin, "label": it.get("label", ""),
                     "marketplaces": it.get("marketplaces") or _store.EU_MARKETPLACES,
                     "per_marketplace": per_mkt, "has_unknown": asin_unknown, "checked": asin_checked})
    # MULTI-ACCOUNT: same resolved NAME under multiple seller IDs = strong bad-actor signal
    # (e.g. "Woux LLC" running 4 IDs on BE). Tag each with how many IDs share its name.
    name_ids = {}
    for u in unknowns:
        if u.get("name"):
            name_ids.setdefault(u["name"], set()).add(u["seller_id"])
    for u in unknowns:
        u["multi_account"] = len(name_ids.get(u.get("name", ""), {u["seller_id"]})) if u.get("name") else 1
    # per-marketplace unknown concentration (surfaces hotspots like Belgium)
    by_mkt = {}
    for key in total_unknown:                       # {sid::mkt}
        mk = key.split("::", 1)[1]
        by_mkt[mk] = by_mkt.get(mk, 0) + 1
    # scariest first: HIGH RISK, then brand-new (0-feedback), then lowest feedback count
    unknowns.sort(key=lambda u: (0 if u.get("high_risk") else 1, 0 if u["new_account"] else 1,
                                 (u["feedback_count"] if u["feedback_count"] is not None else 1e9)))
    summary = {"tracked": len(items), "checked": n_checked, "clean": n_clean,
               "with_unknown": n_unknown, "total_unknown": len(total_unknown),
               "new_accounts": sum(1 for u in unknowns if u["new_account"]),
               "high_risk": sum(1 for u in unknowns if u.get("high_risk")),
               "by_marketplace": dict(sorted(by_mkt.items(), key=lambda kv: -kv[1]))}
    return {"rows": rows, "summary": summary, "unknowns": unknowns,
            "eu_marketplaces": _store.EU_MARKETPLACES}


def status():
    return dict(_STATUS)


# ---------------- the diff ----------------
def diff(prev, cur):
    """prev/cur = fetch_offers_batch results (prev None on first check). Returns event dicts."""
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


def _should_check(state_entry, force):
    """Decide whether to check a marketplace this cycle (dead-marketplace skipping)."""
    if force or not state_entry:
        return True                              # forced, or never checked (first run)
    since = time.time() - state_entry.get("last_checked_ts", 0)
    if state_entry.get("live"):
        # A live marketplace used to be re-checked on EVERY cycle. With an hourly
        # cycle that was 24 checks a day per ASIN per marketplace -- the app's
        # biggest quota consumer, competing with everything the user is waiting
        # on. Once a day is what hijacker detection actually needs; "Check now"
        # still forces an immediate scan.
        return since >= _MIN_RECHECK_LIVE
    return since >= _RESCAN_DEAD_AFTER           # stale dead -> re-scan


def _process_result(d, it, mkt, res, cfg, config_path, log):
    """Diff a fetch result vs its baseline -> alerts, record the snapshot, resolve unknown seller
    names + auto-classify Amazon. Returns the number of new alerts."""
    asin = it.get("asin")
    k = _key(asin, mkt)
    prev = d["baselines"].get(k)
    new_alerts = 0
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
    d["snapshots"][k] = d["snapshots"][k][-200:]
    d["baselines"][k] = res
    for _o in res["offers"]:
        _sid = _o.get("seller_id")
        if not _sid:
            continue
        _nk = f"{_sid}::{mkt}"
        if _nk in d["seller_names"]:
            continue
        if _ks.classify(_sid, mkt, cfg)["kind"] == "unknown":
            _nm = _sf.resolve_seller_name(_sid, mkt)
            d["seller_names"][_nk] = _nm
            if _nm and _ks.looks_like_amazon(_nm, mkt):
                if _ks.auto_add_amazon(config_path, _sid, mkt, _nm):
                    log(f"[asin-monitor] auto-classified {_sid} as Amazon ('{_nm}') on {mkt} -- written to config.")
                try:
                    cfg.setdefault("known_sellers", {}).setdefault("amazon", {}).setdefault(mkt, [])
                    if _sid not in [(e.get("id") if isinstance(e, dict) else e)
                                    for e in cfg["known_sellers"]["amazon"][mkt]]:
                        cfg["known_sellers"]["amazon"][mkt].append(_sid)
                except Exception:
                    pass
    return new_alerts


def check_all(cfg, config_path, log=print, force_rescan=False):
    """One cycle. Skips DEAD marketplaces (unless forced / >24h), checks the rest via the BATCH
    Pricing endpoint (20 per call), records live/dead per marketplace, and reports cycle cost."""
    if cfg.get("asin_monitor_enabled", True) is False:
        return {"ok": False, "error": "monitoring disabled (asin_monitor_enabled=false)"}
    items = _store.list_asins(config_path)
    if not items:
        _STATUS.update(last_run=_now(), last_run_ok=True, checks=0, api_calls=0)
        return {"ok": True, "checks": 0, "note": "no ASINs tracked"}
    creds, err = _resolve_creds(cfg, config_path)
    if err:
        _STATUS.update(last_run=_now(), last_run_ok=False)
        log("[asin-monitor] " + err)
        return {"ok": False, "error": err}

    _STATUS["running"] = True
    try:
        with _LOCK:
            d = _load_hist(config_path)
        ms = d.setdefault("market_state", {})
        # 1) build the to-check list, SKIPPING dead marketplaces (unless forced / stale)
        tocheck, skipped = [], 0
        for it in items:
            asin = it.get("asin")
            cond = it.get("condition", "New")
            for mkt in (it.get("marketplaces") or _store.EU_MARKETPLACES):
                if _should_check(ms.get(_key(asin, mkt)), force_rescan):
                    tocheck.append({"asin": asin, "marketplace": mkt, "condition": cond, "it": it})
                else:
                    skipped += 1
        # 2) batch through the Pricing API (20 per call), paced + backed-off inside fetch_offers_batch
        t0 = time.monotonic()
        api_calls, new_alerts, fails = 0, 0, 0
        for i in range(0, len(tocheck), _BATCH_SIZE):
            chunk = tocheck[i:i + _BATCH_SIZE]
            results = _pricing.fetch_offers_batch(creds, chunk, log=log)
            api_calls += 1
            for req, res in zip(chunk, results):
                asin, mkt, it = req["asin"], req["marketplace"], req["it"]
                se = ms.setdefault(_key(asin, mkt), {})
                se["last_checked"] = _now()
                se["last_checked_ts"] = time.time()
                if not res.get("ok"):
                    fails += 1                    # transient error -> leave prior live/dead state
                    se["last_error"] = str(res.get("error", ""))[:140]
                    log(f"[asin-monitor] {asin} {mkt}: {res.get('error')}")
                    continue
                se.pop("last_error", None)         # cleared on a successful check
                has_offers = (res["summary"].get("seller_count") or 0) > 0
                se["live"] = has_offers           # dead = returned no offers (skip next cycles)
                if has_offers:
                    se["last_offers_at"] = _now()
                new_alerts += _process_result(d, it, mkt, res, cfg, config_path, log)
            if i + _BATCH_SIZE < len(tocheck):
                time.sleep(_BATCH_PACING_S)
        dur = round(time.monotonic() - t0, 1)
        d["alerts"] = d["alerts"][-1000:]
        with _LOCK:
            _save_hist(config_path, d)
        overload = bool(_SCHED_INTERVAL and dur > _SCHED_INTERVAL * 0.9)
        _STATUS.update(last_run=_now(), last_run_ok=(fails == 0), checks=len(tocheck),
                       api_calls=api_calls, duration=dur, skipped=skipped, interval=_SCHED_INTERVAL,
                       next_run_ts=(time.time() + _SCHED_INTERVAL), overload=overload)
        return {"ok": True, "checks": len(tocheck), "api_calls": api_calls, "duration": dur,
                "alerts": new_alerts, "skipped": skipped, "fails": fails, "overload": overload}
    finally:
        _STATUS["running"] = False


def check_now_async(cfg, config_path, force_rescan=False):
    """Run a full check on a background thread (for the 'Check now' / 'Re-scan all' buttons).
    force_rescan=True checks EVERY selected marketplace (ignores dead-market skipping) for one cycle."""
    if _STATUS.get("running"):
        return {"ok": False, "error": "a check is already running"}
    threading.Thread(target=lambda: check_all(cfg, config_path, force_rescan=force_rescan),
                     daemon=True, name="asin-monitor-now").start()
    return {"ok": True, "started": True, "rescan": bool(force_rescan)}


# ---------------- scheduler ----------------
def start_scheduler(cfg_getter, config_path, interval=3600, initial_delay=25):
    """Start the hourly daemon loop once. cfg_getter is a callable returning current config."""
    global _SCHED_STARTED, _SCHED_INTERVAL
    if _SCHED_STARTED:
        return
    _SCHED_STARTED = True
    _SCHED_INTERVAL = interval

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
