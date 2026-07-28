"""listing/restricted.py -- RESTRICTED / PROHIBITED PRODUCT-TYPE checker (not words).

Data (three files, clear precedence):
  master_restricted_reference.json -- PRIMARY breadth (all categories).
  restricted_product_types.json    -- AUTHORITATIVE for the owner's confirmed violations
                                      (verbatim Amazon notice text + source:amazon_notice).
  required_docs.json               -- doc catalog (doc_id -> definition).

check_restricted_type() is a SOURCING ALARM: read-only, never edits copy, never strips a
spec. It keeps PROHIBITED/GATED/RESTRICTED distinct, resolves status per active marketplace,
and returns an ACTION (BLOCK / WARN / NONE) plus every match. It NEVER returns a green "safe":
no match -> an explicit "not a clearance" message + a disguised-type caveat.

TUNING (owner-approved):
 * KEYWORD DEMOTION -- a bare common word ("mat","oil","rubber","laser","transmitter","tuner",
   "class 3"...) is CORROBORATING ONLY: it never flags on its own, only when a category/
   browse-node signal is also present. Distinctive terms ("nebulizer","slim jim","r-134a",
   "600mw","hydroquinone") and multi-word/unit-bearing terms are STRONG and can flag alone.
 * MARKETPLACE-UNKNOWN = WARN -- hard BLOCK only on a CONFIRMED (amazon_notice) prohibition
   for the KNOWN active marketplace. Unknown marketplace, or a marketplace-specific/threshold
   prohibition we can't confirm, -> WARN, never a hard block.
"""
import json
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MASTER_FILE = os.path.join(_ROOT, "master_restricted_reference.json")
_TIER3_FILE = os.path.join(_ROOT, "restricted_product_types.json")
_DOCS_FILE = os.path.join(_ROOT, "required_docs.json")

NO_MATCH_MESSAGE = ("No known restriction matched -- this is NOT a clearance. Unlisted or "
                    "disguised product types can still be restricted or prohibited by Amazon "
                    "or a regulator. Verify before sourcing/listing.")
MATCH_CAVEAT = ("Type matching is keyword-based: obvious cases are caught reliably, disguised "
                "or renamed products may slip through. This is a strong warning, not a guarantee.")


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


_MASTER = _load(_MASTER_FILE)
_TIER3 = _load(_TIER3_FILE)
_DOCS = _load(_DOCS_FILE)


def _wordish(term):
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.I)


# --- KEYWORD CLASSIFIER ------------------------------------------------------
# Distinctive single words that ARE strong enough to flag alone.
_STRONG_SINGLES = {
    "nebulizer", "nebuliser", "inhaler", "hydroquinone", "ephedra", "dmaa", "phenibut",
    "tianeptine", "kratom", "kava", "sarms", "yohimbine", "sildenafil", "tadalafil",
    "jammer", "freon", "taser", "slimjim",
}
# Multi-word / digit-bearing terms that are nonetheless too BROAD to flag alone.
# NOTE: precise real-restriction terms (class 3 LASER, signal booster, high power vtx,
# high power laser, mw laser) are deliberately NOT here -- they name the actual restricted
# product and must stay STRONG. Only genuinely ambiguous fragments live here.
_BROAD_OVERRIDE = {
    "class 3", "class 4", "class ii", "class iiib", "medical grade", "1w", "heavy duty",
    "coolant gas", "high power",
}


def classify_keyword(kw):
    """'strong' (may flag alone) vs 'corroborating' (needs a category signal)."""
    k = str(kw).strip().lower()
    if not k:
        return "corroborating"
    if k in _BROAD_OVERRIDE:
        return "corroborating"
    if k in _STRONG_SINGLES:
        return "strong"
    if (" " in k) or ("-" in k) or any(c.isdigit() for c in k):
        return "strong"
    return "corroborating"          # a bare single common word -> corroborating only


# --- CATEGORY SIGNAL (primary signal; keywords only corroborate) -------------
# canonical id -> tokens that, seen in product_type / category_path / browse-node,
# mean the product genuinely IS in that restricted category. Conservative.
_CATEGORY_SIGNALS = {
    "supplements": ["supplement", "dietary supplement", "vitamin", "probiotic"],
    "cosmetics_topicals": ["cosmetic", "skincare", "skin care", "moisturizer", "moisturiser",
                           "sunscreen"],
    "medical_devices": ["medical device", "nebulizer", "inhaler", "blood pressure monitor"],
    "lithium_batteries": ["power bank", "power station", "lithium battery"],
    "radio_wireless_fpv": ["drone", "fpv", "quadcopter"],
    "hazmat_dangerous_goods": ["aerosol"],
    "childrens_products": ["toy", "children", "toddler"],
    "pesticides_biocides": ["pesticide", "insecticide", "herbicide"],
    "lasers": ["laser pointer"],
    "refrigerants_ozone": ["refrigerant"],
    "jewelry_precious": ["jewelry", "jewellery", "gemstone"],
    "tobacco_vaping": ["tobacco", "vape", "e-cigarette"],
}

# Source precedence: a confirmed status must not be overwritten by a weaker one.
_SRC_RANK = {"amazon_notice": 3, "amazon_notice_pending": 2, "unverified": 1,
             "master_research": 0, "": 0}

# Tier-3 confirmed-violation ids -> their canonical (master) id, so the authoritative
# status/reason/source overlays the master breadth on the same concept.
_TIER3_TO_CANON = {
    "power_bank": "lithium_batteries",
    "fpv_video_goggles": "radio_wireless_fpv",
    "nebulizer_inhaler": "medical_devices",
    "opaque_eyewear": "opaque_eyewear",
    "facial_steamer_diffuser": "facial_steamer_diffuser",
    "supplements_ingestible": "supplements",
    "cosmetics_skincare": "cosmetics_topicals",
    "pesticide_biocide": "pesticides_biocides",
    "medical_device_general": "medical_devices",
    "radio_transmitter": "radio_wireless_fpv",
    "laser_pointer": "lasers",
    "mains_electrical": "mains_electrical",
    "childrens_product": "childrens_products",
    "hazmat_flammable": "hazmat_dangerous_goods",
    "weapons_adjacent": "weapons_knives",
}


def _norm_tier(value):
    """Free-form status text -> behaviour tier."""
    v = str(value or "").upper()
    if "GATED" in v:
        return "GATED"
    if "PROHIBITED" in v:
        if any(x in v for x in ("UNLESS", "EXCEPT", "MOSTLY", "_OR_", "OR PROHIBITED")):
            return "CONDITIONAL"
        return "PROHIBITED"
    if "RESTRICTED" in v or "ALLOWED_WITH_LIMIT" in v:
        return "RESTRICTED"
    return "RESTRICTED"


def _resolve_docs_display(doc_ids_or_strings):
    """Tier-3 uses doc_ids (resolve via catalog); master uses plain strings. Return display names."""
    catalog = _DOCS.get("docs") or {}
    out = []
    for d in (doc_ids_or_strings or []):
        if isinstance(d, str) and d in catalog:
            out.append(catalog[d].get("name", d))
        else:
            out.append(str(d))
    return out


def _master_status_for(entry, mkt):
    """Resolve a master entry's status text for a marketplace (marketplaces map first)."""
    mkts = entry.get("marketplaces") or {}
    if mkt in mkts:
        return mkts[mkt]
    return entry.get("status", "")


# --- Build canonical entries: master breadth + tier-3 overlay ---------------
def _build_entries():
    canon = {}
    # 1) master -> canonical
    for e in (_MASTER.get("categories") or []):
        cid = e.get("id")
        if not cid:
            continue
        canon[cid] = {
            "id": cid,
            "label": e.get("label", cid),
            "keywords": list(e.get("trigger_keywords") or []),
            "statuses": {
                "UK": {"value": _master_status_for(e, "UK"), "source": "master_research"},
                "US": {"value": _master_status_for(e, "US"), "source": "master_research"},
            },
            "reason": e.get("detail") or e.get("note") or "",
            "regulator": e.get("regulator", ""),
            "docs": _resolve_docs_display(e.get("docs") or []),
            "depth": e.get("depth", ""),
        }
    # 2) tier-3 overlay (authoritative status/reason/source for the owner's confirmed hits)
    for e in (_TIER3.get("types") or []):
        tid = e.get("id")
        cid = _TIER3_TO_CANON.get(tid, tid)
        base = canon.get(cid)
        if base is None:
            base = {"id": cid, "label": e.get("label", cid), "keywords": [],
                    "statuses": {}, "reason": "", "regulator": "", "docs": [], "depth": "solid"}
            canon[cid] = base
        # union keywords
        for kw in (e.get("keywords") or []):
            if kw not in base["keywords"]:
                base["keywords"].append(kw)
        # overlay per-marketplace status by SOURCE PRECEDENCE so a later unverified entry
        # (e.g. radio_transmitter) never clobbers an earlier confirmed one (fpv_video_goggles).
        st = e.get("status") or {}
        for mkt, sv in st.items():
            if isinstance(sv, dict) and sv.get("value"):
                new = {"value": sv["value"], "source": sv.get("source", "unverified")}
                cur = base["statuses"].get(mkt)
                if cur is None or _SRC_RANK.get(new["source"], 0) >= _SRC_RANK.get(cur.get("source", ""), 0):
                    base["statuses"][mkt] = new
        # prefer tier-3 verbatim reason/docs/regulator where present
        if e.get("reason"):
            base["reason_tier3"] = e["reason"]
        if e.get("regulator"):
            base["regulator_tier3"] = e["regulator"]
        if e.get("docs"):
            base["docs_tier3"] = e["docs"]
        if e.get("asin_seen"):
            base["asin_seen"] = e["asin_seen"]
    return canon


_ENTRIES = _build_entries()
# pre-classify each entry's keywords once
for _e in _ENTRIES.values():
    _e["kw_strong"] = [(kw, _wordish(kw)) for kw in _e["keywords"] if classify_keyword(kw) == "strong"]
    _e["kw_corrob"] = [(kw, _wordish(kw)) for kw in _e["keywords"] if classify_keyword(kw) == "corroborating"]


def _category_signal(cid, product_type, category_path, browse_nodes):
    tokens = _CATEGORY_SIGNALS.get(cid)
    if not tokens:
        return False
    hay = "  ".join(str(x) for x in (product_type, category_path,
                    " ".join(browse_nodes or [])) if x).lower()
    return any(_wordish(t).search(hay) for t in tokens)


def check_restricted_type(text="", marketplace="UK", product_type="", category_path="",
                          browse_nodes=None):
    """Sourcing alarm. Returns:
      {"matched", "marketplace", "marketplace_known", "overall_action":BLOCK|WARN|NONE,
       "matches":[{id,label,status,tier,source,action,reason,regulator,docs,depth,
                   matched_keywords,category_signal}],
       "message","caveat"}."""
    mkt = (marketplace or "").upper()
    mkt_known = mkt in ("UK", "US")
    text_hay = str(text or "")

    matches = []
    for cid, e in _ENTRIES.items():
        cat_sig = _category_signal(cid, product_type, category_path, browse_nodes)
        strong_hits = [kw for kw, pat in e["kw_strong"] if pat.search(text_hay)]
        corrob_hits = [kw for kw, pat in e["kw_corrob"] if pat.search(text_hay)]
        # DEMOTION RULE: a corroborating word only counts WITH a category signal.
        matched = bool(strong_hits) or cat_sig
        if not matched:
            continue

        st = e["statuses"].get(mkt) if mkt_known else None
        tier = _norm_tier(st["value"]) if st else "RESTRICTED"
        source = st["source"] if st else ""

        # ACTION: hard BLOCK only on a CONFIRMED prohibition for the KNOWN marketplace.
        if mkt_known and tier == "PROHIBITED" and source == "amazon_notice":
            action = "BLOCK"
        else:
            action = "WARN"

        used_kws = strong_hits + ([k for k in corrob_hits] if cat_sig else [])
        matches.append({
            "id": cid,
            "label": e["label"],
            "status": (st["value"] if st else "unknown for this marketplace"),
            "tier": tier,
            "source": source,
            "action": action,
            "reason": e.get("reason_tier3") or e.get("reason", ""),
            "regulator": e.get("regulator_tier3") or e.get("regulator", ""),
            "docs": _resolve_docs_display(e["docs_tier3"]) if e.get("docs_tier3") else e["docs"],
            "depth": e.get("depth", ""),
            "matched_keywords": used_kws,
            "category_signal": cat_sig,
            "asin_seen": e.get("asin_seen", ""),
        })

    if any(m["action"] == "BLOCK" for m in matches):
        overall = "BLOCK"
    elif matches:
        overall = "WARN"
    else:
        overall = "NONE"

    return {
        "matched": bool(matches),
        "marketplace": mkt,
        "marketplace_known": mkt_known,
        "overall_action": overall,
        "matches": matches,
        "caveat": MATCH_CAVEAT,
        "message": "" if matches else (_MASTER.get("_meta", {}).get("no_match_message")
                                       or _TIER3.get("no_match_message") or NO_MATCH_MESSAGE),
    }
