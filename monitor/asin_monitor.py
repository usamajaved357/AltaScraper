"""monitor/asin_monitor.py — ASIN Monitor tracking-list storage (Stage 2).

Standalone competitor/hijacker monitor, SEPARATE from listing generation. This module owns
ONLY the tracked-ASIN list and its JSON store. There are NO SP-API calls here (that's the
Stage 3 checker) and NO UI. The store is machine-specific runtime state, so it is gitignored.

Per-ASIN record:
  { "id", "asin", "label", "marketplaces": [...], "condition", "added_at" }
"""
import json
import os
import re
import threading
import datetime

# All European marketplaces reachable from the EU SP-API region on ONE credential set
# (Jack Reacherd UK). Verified live: every id resolves on sellingpartnerapi-eu.
EU_MARKETPLACES = ["UK", "DE", "FR", "IT", "ES", "NL", "PL", "SE", "BE", "IE"]

_LOCK = threading.Lock()


def _store_path(config_path):
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), "asin_monitor.json")


def load(config_path):
    try:
        with open(_store_path(config_path), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("asins"), list):
            return d
    except Exception:
        pass
    return {"asins": []}


def _save(config_path, data):
    with open(_store_path(config_path), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def list_asins(config_path):
    return load(config_path).get("asins", [])


def _norm_asin(a):
    return str(a or "").strip().upper()


def _valid_asin(a):
    # Amazon ASINs are 10 chars, letters+digits (B0... or a 10-digit ISBN for books).
    return bool(re.fullmatch(r"[A-Z0-9]{10}", a))


def _now_iso():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _new_id(arr):
    mx = 0
    for r in arr:
        try:
            mx = max(mx, int(r.get("id", 0)))
        except Exception:
            pass
    return mx + 1


def _clean_marketplaces(marketplaces):
    mkts = [str(m).strip().upper() for m in (marketplaces or []) if str(m).strip()]
    mkts = [m for m in mkts if m in EU_MARKETPLACES]
    # de-dupe preserving order; default to all-EU when nothing valid was given
    seen, out = set(), []
    for m in mkts:
        if m not in seen:
            seen.add(m); out.append(m)
    return out or list(EU_MARKETPLACES)


def add(config_path, asin, label="", marketplaces=None, condition="New", sku="", status=""):
    """Add a tracked ASIN (or update label/marketplaces/condition/sku if it already exists).
    `sku` (your seller-SKU) and `status` are stored as CONTEXT -- useful when the ASIN came from
    an All Listings Report; they don't affect monitoring."""
    asin = _norm_asin(asin)
    if not _valid_asin(asin):
        return {"ok": False, "error": "ASIN must be 10 letters/digits, e.g. B0XXXXXXXX"}
    mkts = _clean_marketplaces(marketplaces)
    cond = (str(condition).strip() or "New")
    sku = str(sku or "").strip()
    status = str(status or "").strip()
    with _LOCK:
        data = load(config_path)
        arr = data.setdefault("asins", [])
        existing = next((r for r in arr if _norm_asin(r.get("asin")) == asin), None)
        if existing:
            existing["label"] = (label or existing.get("label", "")).strip()
            existing["marketplaces"] = mkts
            existing["condition"] = cond
            if sku:
                existing["sku"] = sku
            if status:
                existing["status"] = status
            _save(config_path, data)
            return {"ok": True, "updated": True, "item": existing}
        item = {"id": _new_id(arr), "asin": asin, "label": (label or "").strip(),
                "marketplaces": mkts, "condition": cond, "added_at": _now_iso()}
        if sku:
            item["sku"] = sku
        if status:
            item["status"] = status
        arr.append(item)
        _save(config_path, data)
        return {"ok": True, "item": item}


def remove(config_path, asin=None, id=None):
    """Remove a tracked ASIN by id (preferred) or by asin."""
    with _LOCK:
        data = load(config_path)
        arr = data.setdefault("asins", [])
        before = len(arr)
        if id is not None and str(id) != "":
            arr = [r for r in arr if str(r.get("id")) != str(id)]
        elif asin:
            a = _norm_asin(asin)
            arr = [r for r in arr if _norm_asin(r.get("asin")) != a]
        else:
            return {"ok": False, "error": "need an id or asin to remove"}
        data["asins"] = arr
        _save(config_path, data)
        return {"ok": True, "removed": before - len(arr)}
