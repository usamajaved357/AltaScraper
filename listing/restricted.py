"""listing/restricted.py -- RESTRICTED / PROHIBITED PRODUCT-TYPE checker (not words).

The claims screener (listing/compliance.py) catches risky WORDS. This catches restricted
PRODUCT TYPES -- the bigger-money problem (a whole listing removed after it goes live).

Two data files, both editable:
  restricted_product_types.json -- type keywords + per-marketplace status/reason/regulator/docs
  required_docs.json            -- the compliance-document catalog (doc_id -> definition)

check_restricted_type() scans text + the captured product_type/category/browse-nodes against
the type list (whole-word/synonym, the esso-in-compressor discipline) and returns matches with
PROHIBITED vs RESTRICTED kept DISTINCT, each carrying its 'source' (amazon_notice = confirmed;
amazon_notice_pending = notice exists, text pending; unverified = educated guess). It NEVER
returns a green "safe": no match -> an explicit "not a clearance" message. WARN only; never
blocks generation.
"""
import json
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TYPES_FILE = os.path.join(_ROOT, "restricted_product_types.json")
_DOCS_FILE = os.path.join(_ROOT, "required_docs.json")

# The honest no-match line (also stored in the data file; this is the fallback).
NO_MATCH_MESSAGE = ("No known restriction matched -- this is NOT a clearance. Unlisted or "
                    "disguised product types can still be restricted or prohibited by Amazon "
                    "or a regulator. Verify before sourcing/listing.")

# Type-match caveat surfaced with every result -- matching a product to a TYPE is fuzzier
# than matching a word, so a disguised item ("portable pet mist device") may not match.
MATCH_CAVEAT = ("Type matching is keyword-based: obvious cases are caught reliably, disguised "
                "or renamed products may slip through. This is a strong warning, not a guarantee.")


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


_TYPES_DATA = _load(_TYPES_FILE)
_DOCS_DATA = _load(_DOCS_FILE)


def _wordish(term):
    """Whole-word pattern with a boundary guard on both ends (shared discipline: a term
    that is a substring of a longer word never matches)."""
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.I)


# Pre-compile each type's keyword patterns once.
_TYPE_PATTERNS = []
for _t in (_TYPES_DATA.get("types") or []):
    _pats = [(_kw, _wordish(_kw)) for _kw in (_t.get("keywords") or []) if _kw]
    _TYPE_PATTERNS.append((_t, _pats))


def _for_market(value, mkt):
    """A reason/regulator/docs field may be a plain value (same for all markets) or a
    per-market dict {"UK": ..., "US": ...}. Resolve for the requested marketplace."""
    if isinstance(value, dict) and ("UK" in value or "US" in value):
        return value.get(mkt, value.get("UK") or value.get("US"))
    return value


def _resolve_docs(doc_ids, mkt):
    """doc_id list -> full catalog entries (name/issued_by/proves/source), marketplace-tagged."""
    out = []
    catalog = _DOCS_DATA.get("docs") or {}
    for did in (doc_ids or []):
        meta = catalog.get(did, {})
        out.append({
            "id": did,
            "name": meta.get("name", did),
            "issued_by": meta.get("issued_by", ""),
            "proves": meta.get("proves", ""),
            "source": meta.get("source", "unverified"),
        })
    return out


def check_restricted_type(text="", marketplace="UK", product_type="", category_path="",
                          browse_nodes=None):
    """Scan the finished/captured product signals against the restricted-type list for a
    marketplace. Returns:
      {"matched": bool, "marketplace", "overall_status": "PROHIBITED"|"RESTRICTED"|"NONE",
       "matches": [{id,label,status,source,reason,regulator,docs:[...],matched_keywords}],
       "message", "caveat"}
    NEVER a green 'safe' -- no match yields an explicit not-a-clearance message."""
    mkt = (marketplace or "UK").upper()
    hay_parts = [str(text or ""), str(product_type or ""), str(category_path or "")]
    if browse_nodes:
        hay_parts.append(" ".join(str(b) for b in browse_nodes))
    hay = "  ".join(p for p in hay_parts if p)

    matches = []
    for entry, pats in _TYPE_PATTERNS:
        st = entry.get("status") or {}
        mkt_status = st.get(mkt)
        if not mkt_status:
            continue                       # this type carries no status for this marketplace
        hit_kws = [kw for kw, pat in pats if pat.search(hay)]
        if not hit_kws:
            continue
        matches.append({
            "id": entry.get("id", ""),
            "label": entry.get("label", ""),
            "status": mkt_status.get("value", "RESTRICTED"),
            "source": mkt_status.get("source", "unverified"),
            "reason": _for_market(entry.get("reason", ""), mkt),
            "regulator": _for_market(entry.get("regulator", ""), mkt),
            "docs": _resolve_docs(_for_market(entry.get("docs", []), mkt), mkt),
            "docs_note": entry.get("docs_note", ""),
            "asin_seen": entry.get("asin_seen", ""),
            "matched_keywords": hit_kws,
        })

    if any(m["status"] == "PROHIBITED" for m in matches):
        overall = "PROHIBITED"
    elif matches:
        overall = "RESTRICTED"
    else:
        overall = "NONE"

    result = {
        "matched": bool(matches),
        "marketplace": mkt,
        "overall_status": overall,
        "matches": matches,
        "caveat": MATCH_CAVEAT,
        "message": "" if matches else (_TYPES_DATA.get("no_match_message") or NO_MATCH_MESSAGE),
    }
    return result
