"""listing/sourcing_viability.py -- SOURCING VIABILITY CHECK (document-demand risk).

A DIFFERENT QUESTION from listing/restricted.py, deliberately kept separate:

  restricted.py / getListingsRestrictions  ->  "will Amazon let me create this
                                                listing today?"
  this module                              ->  "if I list this freely today,
                                                which safety documents will
                                                Amazon demand months later, and
                                                can I actually produce them?"

The electric patio heater is the case this exists for. It was not gated and not
restricted -- it listed without a murmur, sold, and months later Amazon asked for
a BS EN 60335-2-30 test report that nobody had and that cannot be produced after
the fact for a generic import. getListingsRestrictions would have returned an
empty restrictions array the whole time. No gating API can answer this, because
the demand follows what the product physically IS, not which category it sits in.

Rules live in sourcing_viability_rules.json so new ones need no code change.

MATCHING (same discipline as the restricted checker):
  exclude       -- hard veto, checked first ("ring binder" is not jewellery)
  strong        -- fires alone
  corroborating -- a common word (fan, iron, ring, plate, paint) that only counts
                   WITH a context word from the same rule: "curling iron" fires,
                   "iron supplement" does not
  wattage_min / mah_min -- numeric triggers ("2000W" fires MAINS_ELECTRICAL)
  accessory adjacency   -- "patio heater COVER" names the accessory, not the
                           appliance. Shared rule, imported from restricted.py.

BEHAVIOUR (owner-approved): WARN and show the documents. Never HOLD, never edits
copy. It is a pre-sourcing prompt: confirm you can get the papers before you buy.
"""
import json
import os
import re

from listing.restricted import (
    ACCESSORY_NOUNS,
    accessory_pattern,
    compat_pattern,
    resolve_docs_display,
    wordish,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RULES_FILE = os.path.join(_ROOT, "sourcing_viability_rules.json")

NO_MATCH_MESSAGE = ("No document-demand risk detected -- this is NOT a clearance. Amazon can "
                    "request safety documentation for any product at any time.")
CAVEAT = ("Signal-based detection: obvious cases are caught reliably, vaguely-worded ones may "
          "slip through. Confirm you can obtain the documents BEFORE sourcing.")
WARNING_TEMPLATE = ("SOURCING RISK [{rule}]: Amazon will likely request {docs}. "
                    "As a reseller you probably cannot provide these.")


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


_RULES = _load(_RULES_FILE)

# A number followed by W/watt(s). The lookahead rejects a dimension ("60W x 40H"),
# the one place a bare W does not mean watts.
_WATTAGE_RE = re.compile(r"(?<![A-Za-z0-9])(\d{2,5})\s*(?:w|watt|watts)(?![A-Za-z0-9])"
                         r"(?!\s*[x×]\s*\d)", re.I)
_MAH_RE = re.compile(r"(?<![A-Za-z0-9])(\d{2,7})\s*mah(?![A-Za-z0-9])", re.I)


def _compile_rule(rc):
    """Pre-compile every pattern for one rule, once at import."""
    trg = rc.get("triggers") or {}
    strong = list(trg.get("strong") or [])
    corrob = list(trg.get("corroborating") or [])
    return {
        "id": rc.get("id", ""),
        "label": rc.get("label", rc.get("id", "")),
        "risk": str(rc.get("risk", "MEDIUM")).upper(),
        "avoid_if_no_docs": bool(rc.get("avoid_if_no_docs")),
        "reason": rc.get("reason", ""),
        "regulator": rc.get("regulator") or {},
        "docs": rc.get("docs") or {},
        "strong": [(t, wordish(t)) for t in strong],
        "context": [(t, wordish(t)) for t in (trg.get("context") or [])],
        "corrob": [(t, wordish(t)) for t in corrob],
        "exclude": [(t, wordish(t)) for t in (rc.get("exclude") or [])],
        # Accessory adjacency applies to every trigger term, so "patio heater
        # cover", "charger stand" and "trampoline cover" all demote.
        "accessory": {t: accessory_pattern(t, ACCESSORY_NOUNS) for t in (strong + corrob)},
        # And COMPATIBILITY demotes a context word: "works on electric hobs"
        # says what the product is used with, not what it is. See compat_pattern
        # in listing/restricted.py for the wok this exists for.
        "compat": {t: compat_pattern(t)
                   for t in (trg.get("context") or []) + corrob},
        "wattage_min": int(trg.get("wattage_min") or 0),
        "mah_min": int(trg.get("mah_min") or 0),
    }


_RULE_LIST = [_compile_rule(rc) for rc in (_RULES.get("risk_classes") or [])]


def _numeric_max(pattern, text):
    vals = [int(m.group(1)) for m in pattern.finditer(text)]
    return max(vals) if vals else 0


def _all_accessory(rule, text, hits):
    """True when EVERY trigger hit names an accessory ("patio heater COVER").

    One un-qualified hit keeps the match -- "Patio Heater with Cover 2100W" is a
    heater. Identical rule to listing/restricted.py, imported not copied.
    """
    if not hits:
        return False
    for term in hits:
        pat = rule["accessory"].get(term)
        if pat is None or not pat.search(text):
            return False
    return True


def _word_hits(term, text):
    """Every whole-word occurrence of a term. Used to compare against the
    compatibility matches, so "electric" twice with only one of them inside
    "works on ... electric" still counts as real evidence."""
    return wordish(term).findall(text)


def _evaluate(rule, text):
    """Return (fired, signals) for one rule."""
    # 1. exclude is a hard veto, checked before anything else.
    vetoed = [t for t, pat in rule["exclude"] if pat.search(text)]
    if vetoed:
        return False, []

    strong_hits = [t for t, pat in rule["strong"] if pat.search(text)]
    corrob_hits = [t for t, pat in rule["corrob"] if pat.search(text)]
    context_hits = [t for t, pat in rule["context"] if pat.search(text)]

    # COMPATIBILITY IS NOT IDENTITY. A word that appears ONLY inside a phrase
    # like "works on electric hobs" describes what the product is used with.
    # Dropped from the evidence rather than the whole rule vetoed: a listing
    # that says both "works on electric hobs" AND "1500W mains powered" still
    # has the second, and should still fire.
    def _only_compat(term):
        pat = rule["compat"].get(term)
        if pat is None:
            return False
        hits = len(_word_hits(term, text))
        return hits > 0 and hits == len(pat.findall(text))

    context_hits = [t for t in context_hits if not _only_compat(t)]
    corrob_hits = [t for t in corrob_hits if not _only_compat(t)]

    # 2. an accessory to the product is not the product.
    word_hits = strong_hits + corrob_hits
    if word_hits and _all_accessory(rule, text, word_hits):
        return False, []

    watts = _numeric_max(_WATTAGE_RE, text) if rule["wattage_min"] else 0
    mah = _numeric_max(_MAH_RE, text) if rule["mah_min"] else 0

    signals = []
    if strong_hits:
        signals += [f"names the product: {t}" for t in strong_hits]
    # 3. DEMOTION: a common word counts only alongside a context word.
    if corrob_hits and context_hits:
        signals += [f"{c} + {ctx}" for c in corrob_hits for ctx in context_hits[:1]]
    if rule["wattage_min"] and watts >= rule["wattage_min"]:
        signals.append(f"wattage {watts}W at or above {rule['wattage_min']}W")
    if rule["mah_min"] and mah >= rule["mah_min"]:
        signals.append(f"capacity {mah}mAh at or above {rule['mah_min']}mAh")

    return bool(signals), signals


def _docs_for(rule, mkt):
    """Documents for the active marketplace, resolved through the shared catalogue."""
    docs = rule.get("docs") or {}
    raw = docs.get(mkt) or docs.get("UK") or docs.get("US") or []
    return resolve_docs_display(raw if isinstance(raw, list) else [])


def check_sourcing_viability(title="", bullets=None, product_type="", category="",
                             marketplace="UK", docs_held=None):
    """Document-demand risk for a product, BEFORE sourcing it.

    title       -- product title (or any pasted text)
    bullets     -- list of bullet strings, or a single string
    product_type/category -- optional extra context, searched with the title
    marketplace -- "UK" / "US"
    docs_held   -- optional list of documents you can actually produce. When
                   given, each risk reports what is still missing; when omitted,
                   every document is treated as outstanding.

    Returns:
      {"matched", "marketplace", "marketplace_known", "verdict", "overall_action",
       "risks":[{id,label,risk,reason,signals,regulator,docs,docs_missing,warning}],
       "warnings":[str], "message", "caveat"}

    verdict: VIABLE      -- nothing fired, or you hold every document
             NEEDS_DOCS  -- fired; get the documents before committing to stock
             AVOID       -- a high-risk rule fired and you asserted you hold none
                            of its documents
    overall_action is always WARN or NONE. This layer never blocks.
    """
    if isinstance(bullets, (list, tuple)):
        bullet_text = " ".join(str(b or "") for b in bullets)
    else:
        bullet_text = str(bullets or "")
    hay = " ".join(str(x or "") for x in (title, bullet_text, product_type, category)).strip()

    mkt = (marketplace or "").upper()
    mkt_known = mkt in ("UK", "US")
    held = {str(d).strip().lower() for d in (docs_held or [])}
    asserted = docs_held is not None
    template = _RULES.get("warning_template") or WARNING_TEMPLATE

    risks = []
    for rule in _RULE_LIST:
        fired, signals = _evaluate(rule, hay)
        if not fired:
            continue
        docs = _docs_for(rule, mkt if mkt_known else "UK")
        missing = [d for d in docs if str(d).strip().lower() not in held]
        risks.append({
            "id": rule["id"],
            "label": rule["label"],
            "risk": rule["risk"],
            "reason": rule["reason"],
            "signals": signals,
            "regulator": (rule["regulator"] or {}).get(mkt, "") if mkt_known else rule["regulator"],
            "docs": docs,
            "docs_missing": missing,
            "avoid_if_no_docs": rule["avoid_if_no_docs"],
            "warning": template.format(rule=rule["id"], docs="; ".join(missing or docs)),
        })

    # HIGH risks first, then the order the rules are written in.
    risks.sort(key=lambda r: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(r["risk"], 3))

    if not risks or all(not r["docs_missing"] for r in risks):
        verdict = "VIABLE"
    elif asserted and any(r["avoid_if_no_docs"] and len(r["docs_missing"]) == len(r["docs"])
                          for r in risks):
        verdict = "AVOID"
    else:
        verdict = "NEEDS_DOCS"

    return {
        "matched": bool(risks),
        "marketplace": mkt,
        "marketplace_known": mkt_known,
        "verdict": verdict,
        "overall_action": "WARN" if risks else "NONE",
        "risks": risks,
        "warnings": [r["warning"] for r in risks],
        "caveat": _RULES.get("caveat") or CAVEAT,
        "message": "" if risks else (_RULES.get("no_match_message") or NO_MATCH_MESSAGE),
    }


def sourcing_warning_lines(result):
    """The note lines for a viability result -- ONE formatter, used by both the
    generation path and the dashboard modal so the wording can never drift."""
    return list((result or {}).get("warnings") or [])
