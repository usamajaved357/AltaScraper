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
    target_pattern,
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


class _Lazy:
    """A {term: compiled pattern} map that compiles on first lookup.

    Behaves as the dict it replaces for the only thing callers do with it --
    .get(term) -- and returns None for a term the rule does not have, exactly as
    a dict would, so the demotion checks are unchanged.
    """
    __slots__ = ("_make", "_terms", "_cache")

    def __init__(self, make, terms):
        self._make = make
        self._terms = frozenset(terms or ())
        self._cache = {}

    def get(self, term, default=None):
        if term not in self._terms:
            return default
        pat = self._cache.get(term)
        if pat is None:
            pat = self._make(term)
            self._cache[term] = pat
        return pat

    def __len__(self):
        return len(self._terms)

    def __contains__(self, term):
        return term in self._terms


def _compile_rule(rc):
    """Compile one rule. The trigger patterns are built now, because every one of
    them is searched on every call; the demotion patterns are built on demand."""
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
        # PRODUCT TYPES THIS RULE CANNOT APPLY TO.
        #
        # A chair is not a cosmetic, whatever words are in its description, and
        # Amazon has already told us it is a chair. Without this, "sunscreen
        # fabric" -- a real outdoor-furniture textile -- made a garden recliner
        # demand a Cosmetic Product Safety Report, a Product Information File
        # and a full INCI ingredient list. Reported as "wrong compliance docs
        # and warnings are displayed", and rightly.
        #
        # A warning that cries wolf is worse than no warning: it teaches people
        # to click past the one that matters. So the product type, which is a
        # fact rather than an inference from prose, gets a veto.
        "not_types": {str(t).strip().upper()
                      for t in (rc.get("not_product_types") or []) if t},
        # PRODUCT TYPES THAT ARE THE ANSWER ON THEIR OWN.
        #
        # The veto above was the only thing the product type could do: it could
        # stop a rule, never start one. So the most authoritative fact available
        # -- what Amazon itself calls the product -- was ignored whenever the
        # title happened not to contain a listed word. Measured on the 173 stored
        # drafts:
        #
        #   product_type BATTERY     "6V 4R25 Zinc-Carbon Lantern Batteries"
        #                            no risk at all: the battery rule looks for
        #                            "lithium", and these are zinc-carbon
        #   product_type POWER_STRIP "6 Gang Extension Lead ... 2 Metre Cable"
        #                            no risk at all: "extension lead" was not a
        #                            trigger word, though a mains extension lead
        #                            is among the most enforced things there are
        #
        # A title is written by a person and can say anything. A product type is
        # chosen from Amazon's own taxonomy, so where one exists it is better
        # evidence than the prose -- and it is exactly what a rule like "this is
        # a battery" should key on. Treated as a STRONG signal: it fires alone.
        #
        # `exclude` and `not_product_types` still apply, so this cannot resurrect
        # a rule that has been told it does not apply here.
        "types": {str(t).strip().upper()
                  for t in (rc.get("product_types") or []) if t},
        # COMPILED ON FIRST USE, NOT AT IMPORT.
        #
        # These three helper patterns exist for every trigger term of every rule
        # -- 771 regexes across 15 rules -- and building them all at import cost
        # 3.3 seconds of a startup the app is measured on. Almost none are ever
        # needed: a demotion pattern is only consulted when its term actually
        # appeared in the text, which for most terms is never.
        #
        # So the term LIST is kept and the pattern is built the first time it is
        # asked for, then remembered. Same patterns, same answers, built only for
        # the handful of words a listing really contains.
        "accessory": _Lazy(lambda t: accessory_pattern(t, ACCESSORY_NOUNS),
                           strong + corrob),
        # And COMPATIBILITY demotes a context word: "works on electric hobs"
        # says what the product is used with, not what it is. See compat_pattern
        # in listing/restricted.py for the wok this exists for.
        "compat": _Lazy(compat_pattern, (trg.get("context") or []) + corrob),
        # AND WHAT THE PRODUCT IS USED AGAINST. Built for STRONG terms too,
        # unlike compat: a strong term fires the rule on its own, so it is
        # exactly the one that must not fire on "removes adhesive" or "adhesive
        # marks". See target_pattern in listing/restricted.py -- the brush this
        # exists for.
        "target": _Lazy(target_pattern, strong + corrob),
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

    # THE PRODUCT IS NOT THE THING IT CLEANS OFF. Same test as compatibility --
    # every occurrence of the word has to be inside the phrase before the word
    # is dropped, so a listing that says both "removes adhesive" AND "contains
    # adhesive" still has the second and still fires.
    def _only_target(term):
        pat = rule["target"].get(term)
        if pat is None:
            return False
        hits = len(_word_hits(term, text))
        return hits > 0 and hits == len(pat.findall(text))

    context_hits = [t for t in context_hits if not _only_compat(t)]
    corrob_hits = [t for t in corrob_hits if not _only_compat(t)]
    # Applied to STRONG as well, which compatibility is not: a strong term fires
    # the rule by itself, so it is the one that most needs demoting.
    strong_hits = [t for t in strong_hits if not _only_target(t)]
    corrob_hits = [t for t in corrob_hits if not _only_target(t)]

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


# Worked-out verdicts, kept because the answer depends only on the text and the
# rules -- and _RULES is read once at import, so editing the rules file already
# requires a restart, which empties this with it. There is nothing else that can
# make an entry stale.
_VIABILITY_CACHE = {}
_VIABILITY_CACHE_MAX = 4000


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

    # THE SAME TEXT ALWAYS GIVES THE SAME ANSWER, so it is only worked out once.
    #
    # This is pure: rules in, text in, verdict out, no clock and no I/O. It is
    # also expensive -- fifteen rules of roughly a hundred compiled patterns
    # each. Profiled on the Listings screen: 55 rows produced 90,290 regex
    # searches taking 3.46 of the route's 3.91 seconds, and every one of them was
    # recomputing an answer it had already produced on the previous page load.
    #
    # Keyed on everything that can change the verdict. A listing whose title is
    # edited gets a new key and is evaluated again, which is the whole point.
    _key = (hay, str(marketplace or "").upper(),
            None if docs_held is None
            else tuple(sorted(str(d).strip().lower() for d in docs_held)))
    _hit = _VIABILITY_CACHE.get(_key)
    if _hit is not None:
        return _hit

    mkt = (marketplace or "").upper()
    mkt_known = mkt in ("UK", "US")
    held = {str(d).strip().lower() for d in (docs_held or [])}
    asserted = docs_held is not None
    template = _RULES.get("warning_template") or WARNING_TEMPLATE

    # The product type Amazon has assigned, which is a fact rather than an
    # inference from the words in a description. Upper-cased once.
    _pt = str(product_type or "").strip().upper()

    risks = []
    for rule in _RULE_LIST:
        # A rule that cannot apply to this KIND of thing never fires, whatever
        # its description happens to say. "Sunscreen fabric" is a garden-chair
        # textile and was demanding a Cosmetic Product Safety Report.
        if _pt and _pt in rule.get("not_types", ()):
            continue
        fired, signals = _evaluate(rule, hay)
        # AMAZON'S OWN CLASSIFICATION, when the words did not settle it. A title
        # is written by a person; a product type is chosen from Amazon's
        # taxonomy, so where the two could disagree this is the better evidence.
        # It fires the rule on its own and says so, so the reason on screen reads
        # "Amazon lists this as a BATTERY" rather than naming a word that is not
        # in the title.
        if not fired and _pt and _pt in rule.get("types", ()):
            fired = True
            signals = ["Amazon lists this as %s" % _pt]
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

    out = {
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
    # Bounded, and oldest-out when it fills: a long session on a large catalogue
    # should not grow this without limit, and the rows being looked at now are
    # the ones worth remembering.
    if len(_VIABILITY_CACHE) >= _VIABILITY_CACHE_MAX:
        for _old in list(_VIABILITY_CACHE)[:_VIABILITY_CACHE_MAX // 4]:
            _VIABILITY_CACHE.pop(_old, None)
    _VIABILITY_CACHE[_key] = out
    return out


def sourcing_warning_lines(result):
    """The note lines for a viability result -- ONE formatter, used by both the
    generation path and the dashboard modal so the wording can never drift."""
    return list((result or {}).get("warnings") or [])
