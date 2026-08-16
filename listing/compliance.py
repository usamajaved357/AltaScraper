"""listing/compliance.py — proactive compliance-safe defaults.

apply_compliance_safe_defaults sets each hazard/regulatory field to its safest,
non-cascading 'not applicable / none' value from the live schema, so a non-chemical
retail item never errors on an empty or trigger-y compliance dropdown. _enum_for and
_pick_not_applicable are its schema helpers. Moved verbatim from
amazon_listing_generator.py in Phase 5 (behaviour unchanged); self-contained.
"""
import re

# Values that mean "no hazard / not regulated" -- preferred for family-1 fields,
# matched case-insensitively against the schema's own enum.
_NOT_APPLICABLE_SYNONYMS = (
    "not_applicable", "notapplicable", "not_app", "none", "no", "not_regulated",
    "non_hazardous", "no_ghs", "not_classified", "does_not_apply", "n_a", "na",
    "exempt", "no_warning_applicable",
)

# Family-1 compliance fields we proactively neutralise (in addition to whatever
# the live `required` list contains). These are the usual error sources.
_HAZARD_QUESTION_FIELDS = (
    "ghs", "hazmat", "pesticide_marking", "supplier_declared_material_regulation",
    "california_proposition_65_compliance_type", "contains_liquid_contents",
    "dangerous_goods_regulation",
)


# ---------------------------------------------------------------------------
# LISTING-COPY SCRUBBER -- belt-and-suspenders over the generation prompt.
# Amazon rejects listing copy containing seller self-promotion, shipping/
# fulfilment claims, external links, or unverifiable superlatives ("false/
# promotional claims or external links"). The prompt forbids these, but a model
# can still slip one in, so we strip them from the FINISHED copy before it is
# written to the sheet. Each function returns what it removed, so it's transparent.
# ---------------------------------------------------------------------------

# URLs / other-site references.
_SCRUB_URL_RE = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|co\.uk|net|org|io)\b\S*", re.I)

# A whole sentence carrying one of these is seller/shipping self-promotion Amazon
# rejects -- safe to drop the sentence (they're standalone marketing lines).
_SCRUB_SENTENCE_RE = re.compile(
    r"\b(?:sold\s+(?:by|exclusively\s+by)|quality\s+you\s+can\s+trust|trusted\s+brand|"
    r"handling\s+and\s+dispatch|processed\s+promptly|arrives?\s+in\b[^.]*condition|"
    r"unboxing\s+experience|without\s+a\s+long\s+wait|next[-\s]?day\s+delivery|"
    r"free\s+delivery|fast\s+delivery|ships?\s+from|in\s+stock|money[-\s]?back|"
    r"satisfaction\s+guarantee)\b", re.I)

# Single unverifiable superlatives / quality words -> removed in place.
_SCRUB_WORD_RE = re.compile(
    r"\b(?:premium|perfect|ultimate|impressive|pristine|flawless|top[-\s]?quality|"
    r"high[-\s]?quality|best[-\s]?selling|world[-\s]?class|exclusively|exclusive)\b", re.I)


def scrub_copy(text, html=False):
    """Strip Amazon-rejected promotional content from ONE copy field.
    Returns (clean_text, [removed]). html=True skips sentence-splitting so
    description markup isn't broken (only URLs + superlative words are removed)."""
    if not text or not isinstance(text, str):
        return text, []
    removed, s = [], text
    for u in _SCRUB_URL_RE.findall(s):
        removed.append("link:" + str(u)[:60])
    s = _SCRUB_URL_RE.sub("", s)
    if not html:
        kept = []
        for sent in re.split(r"(?<=[.!?])\s+", s):
            if _SCRUB_SENTENCE_RE.search(sent):
                removed.append("sentence:" + sent.strip()[:70])
            else:
                kept.append(sent)
        s = " ".join(kept)
    for w in sorted(set(m.group(0) for m in _SCRUB_WORD_RE.finditer(s))):
        removed.append("word:" + w)
    s = _SCRUB_WORD_RE.sub("", s)
    # tidy whitespace / dangling punctuation the removals leave behind
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    s = re.sub(r"[:–—-]\s*$", "", s).strip()
    return s, removed


def scrub_listing_copy(listing: dict):
    """Scrub the customer-facing copy fields of a generated listing dict IN PLACE.
    Returns human-readable notes on what was removed (empty list if clean)."""
    if not isinstance(listing, dict):
        return []
    notes = []
    for f in ("title", "item_highlights", "bullet_1", "bullet_2", "bullet_3",
              "bullet_4", "bullet_5"):
        v = listing.get(f)
        if isinstance(v, str) and v:
            clean, removed = scrub_copy(v, html=False)
            if removed:
                listing[f] = clean
                notes.append(f"{f}: " + "; ".join(removed))
    d = listing.get("description")
    if isinstance(d, str) and d:
        clean, removed = scrub_copy(d, html=True)
        if removed:
            listing["description"] = clean
            notes.append("description: " + "; ".join(removed))
    return notes


def _enum_for(prop: dict):
    """Pull the allowed-value enum for an attribute from its schema property."""
    if not isinstance(prop, dict):
        return []
    if isinstance(prop.get("enum"), list):
        return [str(x) for x in prop["enum"]]
    items = prop.get("items", {}) if isinstance(prop.get("items"), dict) else {}
    ip = items.get("properties", {}) if isinstance(items, dict) else {}
    for key in ("value", "class", "type"):
        vp = ip.get(key, {}) if isinstance(ip, dict) else {}
        if isinstance(vp, dict) and isinstance(vp.get("enum"), list):
            return [str(x) for x in vp["enum"]]
    if isinstance(items.get("enum"), list):
        return [str(x) for x in items["enum"]]
    return []


def _pick_not_applicable(enum):
    """From an enum, return the 'not applicable / none' value if present, else
    None. Never returns a value that is itself a cascade trigger like 'ghs'."""
    if not enum:
        return None
    low = {str(e).lower(): e for e in enum}
    for syn in _NOT_APPLICABLE_SYNONYMS:
        if syn in low:
            return low[syn]
    # fuzzy contains (e.g. "not_applicable_for_this_item")
    for lk, orig in low.items():
        if any(s in lk for s in ("not_applic", "not applic", "not_regul", "no_haz", "non_haz", "not_class")):
            return orig
    return None


def apply_compliance_safe_defaults(A: dict, props: dict, required: set, mid: str,
                                   is_battery: bool):
    """Proactively set every hazard/regulatory compliance field to its safest,
    non-cascading value (the 'not applicable / none' branch from the live schema),
    so a non-chemical retail item never errors on an empty or trigger-y compliance
    dropdown. Returns a list of (field, value, reason) describing what was set, so
    the dashboard can SHOW the user (choice 2b) and let them override.

    Battery fields are NOT neutralised here -- a real battery is filled honestly by
    the dedicated battery logic. This only handles the 'is there a hazard?' family.
    """
    notes = []
    # 1) the family-1 hazard questions Amazon offers a 'not applicable' for
    for f in _HAZARD_QUESTION_FIELDS:
        if f == "ghs":
            continue  # ghs is structural; handled by the dedicated GHS net
        prop = props.get(f, {}) if isinstance(props.get(f), dict) else {}
        enum = _enum_for(prop)
        # only act if the field is plausibly relevant (in schema OR required OR
        # already present with a value we need to validate)
        if not prop and f not in required and f not in A:
            continue
        # If the field is ALREADY set (by the AI or user), validate that value
        # against the schema's allowed list. A valid value is kept; an INVALID
        # one (e.g. the AI guessed hazmat="Transportation", which Amazon rejects)
        # is replaced with the not-applicable option. This is the fix for
        # "hazmat does not have the expected value(s)".
        if f in A:
            _cur = A[f]
            _curval = ""
            if isinstance(_cur, list) and _cur and isinstance(_cur[0], dict):
                _curval = str(_cur[0].get("value", ""))
            elif _cur is not None:
                _curval = str(_cur)
            if enum:
                _enum_low = {str(e).lower(): e for e in enum}
                if _curval.lower() in _enum_low:
                    continue  # already a valid Amazon value -> leave it
                # invalid -> replace with not-applicable (or safest valid value)
                na = _pick_not_applicable(enum) or enum[0]
                A[f] = [{"value": na, "marketplace_id": mid}]
                notes.append((f, na, f'auto: replaced invalid value "{_curval}" with a valid one'))
            # no enum to check against -> leave whatever is there
            continue
        # Not set yet -> fill with the not-applicable option.
        na = _pick_not_applicable(enum)
        if na is not None:
            A[f] = [{"value": na, "marketplace_id": mid}]
            notes.append((f, na, "auto: not-applicable (no hazard for this product)"))
        elif f in required and enum:
            # required but no 'not applicable' option -> safest available non-empty
            safe = enum[0]
            A[f] = [{"value": safe, "marketplace_id": mid}]
            notes.append((f, safe, "auto: required field, picked safest allowed value"))
    return notes


# --- IP / trademark violation scan, moved verbatim from amazon_listing_generator.py
# (Phase 5). _strip_html here is a copy of the engine's RUNTIME-LIVE variant (the engine
# has two _strip_html defs; the later one wins) so check_ip_violations behaves identically.

def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", " ",   html, flags=re.IGNORECASE)
    text = re.sub(r"<li>",      " - ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>",  "",    text)
    return re.sub(r"\s+", " ", text).strip()


def _split_brand_words(brand: str) -> set:
    """Brand 'AltaboltaVoo' or 'Green Haven' -> {'altaboltavoo'} or {'green', 'haven'}."""
    if not brand:
        return set()
    return {w.lower() for w in re.findall(r"[A-Za-z0-9]+", brand) if len(w) > 1}


# ---------------------------------------------------------------------------
# CLAIMS GROUNDING GATE -- a SPECIFIC standards/approval claim in the finished
# copy must appear in the product's OWN source documents (SDS/TDS/other). This is
# the code-level enforcement that was missing: fabricated OEM spec approvals
# ("meets Denison HF-2, Vickers I-286-S", "passes the Vickers 35VQ25 pump wear
# test") reached LIVE Miles listings because the "claims gate" lived only in the
# generation prompt and nothing verified it against source. check_unsupported_claims
# runs AFTER generation, over the finished copy only, and returns the ungrounded
# claims so the caller can HARD-HOLD the row.
#
# Deliberately LENIENT: it exists to catch a designation ABSENT from source, not
# formatting drift. Both sides are normalised (case, hyphen/space, VG/Part/Grade
# infixes, trailing part-numbers), so "ISO 46"~"ISO VG 46", "P-68"~"P68",
# "DIN 51524"~"DIN 51524-2" are NOT mismatches. Only SPECIFIC designations are
# checked: a code containing BOTH a letter and a digit (HF-2, I-286-S, 35VQ25,
# TES-295), an issuer name (Denison, Vickers, Cincinnati Milacron), or issuer+number
# (DIN 51524, AGMA 9005). Vague claims ("meets industry specifications") are left to
# the prompt, not hard-held. The product's OWN viscosity grade (AW-46, ISO 46) is
# excluded -- it is identity, not an external approval.
#
# KNOWN OPEN HOLE (tracked separately): bare quantified claims with no named
# standard ("rated to 250C", an invented viscosity/flash value) are NOT covered
# here -- that needs unit normalisation.
# ---------------------------------------------------------------------------

# Words that introduce a spec the copy claims to satisfy.
_CLAIM_TRIGGER_RE = re.compile(
    r"\b(?:meet|meets|meeting|met|exceed|exceeds|exceeding|pass|passes|passing|"
    r"passed|approved|approval|complies|comply|complying|conform|conforms|"
    r"conforming|certified|rated|per|according)\b", re.I)

# Spec-issuer names that, claimed as met, must be grounded in source. Distinct from
# the forbidden-BRAND list; this is about verifiable standards issuers. (Kept >=3
# chars and distinctive to avoid false hits; 2-char issuers like GM/ZF are handled
# by the forbidden-brand checker instead.)
_SPEC_ISSUERS = (
    "denison", "vickers", "cincinnati", "milacron", "eaton", "parker", "rexroth",
    "sundstrand", "sundyne", "racine", "sperry", "danfoss", "bosch",
    "agma", "afnor", "allison", "cummins", "caterpillar", "kubota", "komatsu",
    "deere", "mercedes", "volvo", "mack", "detroit", "meritor", "poclain",
)
_ISSUER_ALT = "|".join(re.escape(i) for i in _SPEC_ISSUERS)
_ISSUER_RE = re.compile(r"\b(" + _ISSUER_ALT + r")\b", re.I)
_ISSUER_NUM_RE = re.compile(r"\b(" + _ISSUER_ALT + r")\s*#?\s*([0-9][0-9A-Za-z\-./]*)", re.I)

# Candidate designation tokens; filtered to those with BOTH a letter and a digit.
_CODE_CANDIDATE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-./]{1,18}")
# The product's own viscosity grade -- excluded (identity, not an external approval).
_GRADE_RE = re.compile(r"^(?:iso|aw|vg|sae|iso-?vg)?[-\s]?\d{1,3}[a-z]?$", re.I)


def _norm_spec(s: str) -> str:
    """Canonicalise a designation / source blob for lenient comparison: lowercase,
    drop VG/Part/Grade/etc. infix words, then strip everything non-alphanumeric."""
    s = s.lower()
    s = re.sub(r"\b(?:vg|part|no|nr|class|grade|type|level|approval|approved|spec|"
               r"specification|specifications|standard|standards|category|series|"
               r"sequence|test)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def _grounded(token: str, norm_source: str) -> bool:
    """True if `token` appears in the normalised source, tolerating trailing
    part-number differences (DIN 51524 ~ DIN 51524-2 ~ DIN 51524 Part 2)."""
    nt = _norm_spec(token)
    if len(nt) < 3:
        return True                      # too generic to verify -> never flag
    if nt in norm_source:
        return True
    core = nt[:max(4, len(nt) - 2)]      # lenient: allow trailing-part drift
    return core in norm_source


def _looks_like_code(tok: str) -> bool:
    return (bool(re.search(r"[A-Za-z]", tok)) and bool(re.search(r"\d", tok))
            and not _GRADE_RE.match(tok))


def check_unsupported_claims(listing: dict, source_text: str) -> dict:
    """Verify every SPECIFIC standards/approval claim in the finished copy against
    the product's OWN source documents.

    Returns {"has_ungrounded": bool, "ungrounded": [{"claim","token"}], "summary"}.
    Returns empty (nothing flagged) when source_text is blank -- the caller handles
    the no-source case separately (refuse to generate), so this never hard-holds a
    row merely because we have nothing to check against."""
    result = {"has_ungrounded": False, "ungrounded": [], "summary": ""}
    if not source_text or not source_text.strip():
        return result
    norm_source = _norm_spec(source_text)

    blocks = [
        listing.get("title", ""), listing.get("item_highlights", ""),
        listing.get("bullet_1", ""), listing.get("bullet_2", ""),
        listing.get("bullet_3", ""), listing.get("bullet_4", ""),
        listing.get("bullet_5", ""), _strip_html(listing.get("description", "")),
    ]
    text = ". ".join(b for b in blocks if b)
    sentences = re.split(r"(?<=[.!?;:])\s+|\n+|•|<li>|</li>", text)

    seen = set()
    for sent in sentences:
        sent = sent.strip()
        if not sent or not _CLAIM_TRIGGER_RE.search(sent):
            continue
        referenced = []
        # issuer + number combined standards (DIN 51524, AGMA 9005)
        for m in _ISSUER_NUM_RE.finditer(sent):
            referenced.append(m.group(1) + " " + m.group(2))
        # bare issuer names claimed as met (meets Denison ...)
        for m in _ISSUER_RE.finditer(sent):
            referenced.append(m.group(1))
        # specific alphanumeric codes (HF-2, I-286-S, 35VQ25, TES-295)
        for tok in _CODE_CANDIDATE_RE.findall(sent):
            if _looks_like_code(tok):
                referenced.append(tok)
        for tok in referenced:
            if _grounded(tok, norm_source):
                continue
            key = (_norm_spec(tok), sent[:50])
            if key in seen:
                continue
            seen.add(key)
            result["ungrounded"].append({"claim": sent[:180], "token": tok})

    if result["ungrounded"]:
        result["has_ungrounded"] = True
        toks = ", ".join(sorted({u["token"] for u in result["ungrounded"]}))
        result["summary"] = ("UNGROUNDED CLAIM(S) -- not found in product source docs: "
                             + toks)
    return result


# ---------------------------------------------------------------------------
# FORBIDDEN-BRAND SCANNER (step c) -- OEM/competitor trademark names must NOT
# appear in the finished Miles/brand copy at all (distinct from the claims gate,
# which is about whether a claim is grounded). Tiered to keep false-positives out
# of lubricant copy:
#   TIER A -- distinctive names, matched as BARE whole words (John Deere, Kubota).
#   TIER B -- ambiguous names, matched ONLY in their full multi-word form
#             (Case IH, Atlas Copco) -- NEVER the bare word ("Case" in "4x1
#             Gallon/Case" is a packaging term and is fine).
#   plus the 44 OEM spec codes, and Vickers/Denison/Cincinnati Milacron.
# WHOLE-WORD matched with a boundary guard so a name that is a SUBSTRING of an
# ordinary word never fires -- e.g. "Esso" inside "compressor" must NOT hit.
# Scans the FINISHED copy only (title/highlights/bullets/description/keywords),
# never the source docs. A hit hard-holds the row via the locked "HOLD:" prefix.
# ---------------------------------------------------------------------------
import os as _os

_TIER_A_BARE = [
    "John Deere", "Deere", "Kubota", "Caterpillar", "Komatsu", "Kioti", "Kiota",
    "Fendt", "Claas", "Valtra", "Landini", "Mahindra", "Volvo", "Bobcat", "JCB",
    "Hitachi", "Kobelco", "Doosan", "Hyundai", "Liebherr", "Manitowoc", "CompAir",
    "Sullair", "Kaeser", "Cummins", "Freightliner", "Peterbilt", "Kenworth",
    "Navistar", "MaxxForce", "Meritor", "Vickers", "Danfoss", "Rexroth",
    "Bosch Rexroth", "Poclain", "Mobil", "Castrol", "Chevron", "Valvoline",
    "Pennzoil", "Texaco", "AMSOIL", "Motul", "Havoline", "Motorcraft", "Citgo",
    "Conoco", "Esso", "Aisin", "Fuchs", "Kluber", "Anderol", "Krytox",
    "Lubriplate", "SuperTech", "AGCO", "McCormick", "Steiger", "TYM", "Boge",
    "Worthington", "Kendall", "Denison", "Milacron",
]
_TIER_B_FULL = [
    "Case IH", "New Holland", "Ford New Holland", "Massey-Ferguson", "LS Tractor",
    "Deutz-Fahr", "Volvo CE", "Link-Belt", "Ingersoll Rand", "Atlas Copco",
    "Quincy Compressor", "Gardner Denver", "Chicago Pneumatic", "FS Curtis",
    "Detroit Diesel", "Allison Transmission", "Mack Trucks", "Western Star",
    "Eaton Fuller", "Eaton Vickers", "Dana Spicer", "Parker Hannifin",
    "Sauer-Danfoss", "Linde Hydraulics", "Shell Tellus", "Shell Rotella",
    "Shell Rimula", "Total Dacnis", "Total Rubia", "BP Energol", "Petro-Canada",
    "Phillips 66", "Royal Purple", "Lucas Oil", "Lucas Heavy Duty", "Red Line",
    "Liqui Moly", "Liqui-Moly", "Schaeffer Manufacturing", "Mystik JT-6",
    "Warren Distribution", "Quaker State", "MAG 1", "Nye Lubricants",
    "Dow Corning", "Jet-Lube", "Cincinnati Milacron",
]

# 44 OEM spec codes loaded from the repo-root file (single source of truth).
_SPEC_FILE = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                           "forbidden_specs.txt")
try:
    FORBIDDEN_SPEC_CODES = [l.strip() for l in open(_SPEC_FILE, encoding="utf-8") if l.strip()]
except Exception:
    FORBIDDEN_SPEC_CODES = []


def _wordish(term: str):
    """Whole-word pattern with a boundary guard on BOTH ends so a term that is a
    substring of a longer word never matches ('Esso' in 'compressor' -> no hit)."""
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.I)


_FORBIDDEN_TERMS = _TIER_A_BARE + _TIER_B_FULL + FORBIDDEN_SPEC_CODES
_FORBIDDEN_PATTERNS = [(t, _wordish(t)) for t in _FORBIDDEN_TERMS]


def check_forbidden_brands(listing: dict) -> dict:
    """Scan the FINISHED copy for any forbidden OEM/competitor name or spec code.
    Returns {"has_forbidden": bool, "hits": [{"term","field"}], "summary": str}."""
    result = {"has_forbidden": False, "hits": [], "summary": ""}
    fields = [
        ("title", listing.get("title", "")),
        ("item_highlights", listing.get("item_highlights", "")),
        ("bullet_1", listing.get("bullet_1", "")),
        ("bullet_2", listing.get("bullet_2", "")),
        ("bullet_3", listing.get("bullet_3", "")),
        ("bullet_4", listing.get("bullet_4", "")),
        ("bullet_5", listing.get("bullet_5", "")),
        ("description", _strip_html(listing.get("description", ""))),
        ("keywords", listing.get("search_terms", "") or listing.get("backend_keywords", "")),
    ]
    seen = set()
    for fname, text in fields:
        if not text:
            continue
        for term, pat in _FORBIDDEN_PATTERNS:
            if pat.search(text):
                k = (term.lower(), fname)
                if k in seen:
                    continue
                seen.add(k)
                result["hits"].append({"term": term, "field": fname})
    if result["hits"]:
        result["has_forbidden"] = True
        names = ", ".join(sorted({h["term"] for h in result["hits"]}))
        result["summary"] = "FORBIDDEN BRAND/SPEC in copy: " + names
    return result


def forbidden_names_block(safe_alternatives_text: str = "") -> str:
    """The prompt section (step b) that feeds the AI the real names to avoid. Rendered
    as its OWN section so it survives even when source_docs are present."""
    block = (
        "\n===================================\n"
        "FORBIDDEN OEM / COMPETITOR NAMES -- ZERO TOLERANCE\n"
        "===================================\n"
        "NEVER write any of these competitor or OEM brand names anywhere in the title, "
        "bullets, item highlights, description or keywords. If a SOURCE DOCUMENT mentions "
        "one, describe the capability generically or use the safe-alternative wording "
        "instead -- never echo the name into the listing.\n"
        "FORBIDDEN NAMES: " + ", ".join(_TIER_A_BARE + _TIER_B_FULL) + "\n"
    )
    if FORBIDDEN_SPEC_CODES:
        block += "FORBIDDEN OEM SPEC CODES: " + ", ".join(FORBIDDEN_SPEC_CODES) + "\n"
    if safe_alternatives_text and safe_alternatives_text.strip():
        block += "\nSAFE ALTERNATIVES TO USE INSTEAD:\n" + safe_alternatives_text.strip()[:1500] + "\n"
    block += (
        "\nCLARIFIER: the ordinary word 'Case' in a pack size such as '4x1 Gallon/Case' "
        "is a PACKAGING term and is fine -- it is NOT the 'Case IH' tractor brand. Only "
        "the full form 'Case IH' is forbidden; the same applies to other Tier-B names "
        "(only the full multi-word form is forbidden, never the bare common word).\n"
    )
    block += (
        "\nAMAZON-SAFE PHRASING (avoid tripping the pesticide/medical claim filters): do NOT "
        "use antimicrobial/pesticide/medical wording (kill, eliminate, destroy, repel, prevent "
        "growth, fights bacteria/mould/odour, disinfect, sanitise, antimicrobial, medical grade, "
        "therapeutic). PREFER plain descriptive wording over action wording -- 'reduces wear' "
        "not 'protects against wear', 'runs clean' not 'controls deposits', 'resists rust' not "
        "'prevents corrosion'. The claim is true either way; just phrase it descriptively.\n"
    )
    return block


# ---------------------------------------------------------------------------
# RESTRICTED-PHRASING CHECK (feature 1) -- true, grounded wording that nonetheless
# reads as a pesticide/antimicrobial/medical claim to Amazon's filters. Pure pattern
# match (NO AI), whole-word via the same _wordish primitive. A hit WARNs (soften
# before submit), never hard-holds. The list is an editable repo-root file
# (restricted_phrasing.txt), kept conservative so it never nags on normal lube
# language ("rust protection", "reduces wear").
# ---------------------------------------------------------------------------
_RESTRICTED_FILE = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                                 "restricted_phrasing.txt")
try:
    RESTRICTED_PHRASES = [l.strip() for l in open(_RESTRICTED_FILE, encoding="utf-8")
                          if l.strip() and not l.strip().startswith("#")]
except Exception:
    RESTRICTED_PHRASES = []
_RESTRICTED_PATTERNS = [(p, _wordish(p)) for p in RESTRICTED_PHRASES]


def check_restricted_phrasing(listing: dict) -> dict:
    """Scan finished copy for phrasing Amazon's pesticide/medical filters dislike.
    WARN-level (never a hard hold). Returns
    {"has_flagged": bool, "hits": [{"phrase","field"}], "summary": str}."""
    result = {"has_flagged": False, "hits": [], "summary": ""}
    fields = [
        ("title", listing.get("title", "")),
        ("item_highlights", listing.get("item_highlights", "")),
        ("bullet_1", listing.get("bullet_1", "")), ("bullet_2", listing.get("bullet_2", "")),
        ("bullet_3", listing.get("bullet_3", "")), ("bullet_4", listing.get("bullet_4", "")),
        ("bullet_5", listing.get("bullet_5", "")),
        ("description", _strip_html(listing.get("description", ""))),
    ]
    seen = set()
    for fname, text in fields:
        if not text:
            continue
        for phrase, pat in _RESTRICTED_PATTERNS:
            if pat.search(text):
                k = (phrase.lower(), fname)
                if k in seen:
                    continue
                seen.add(k)
                result["hits"].append({"phrase": phrase, "field": fname})
    if result["hits"]:
        result["has_flagged"] = True
        result["summary"] = "RESTRICTED PHRASING: " + ", ".join(sorted({h["phrase"] for h in result["hits"]}))
    return result


# ---------------------------------------------------------------------------
# CATEGORY-AWARE CLAIMS SCREENER (task #18) -- UPGRADES the single restricted-
# phrasing list into a category-SEGMENTED rulebook driven by the product's
# product_type. Two layers:
#   LAYER 1  category_lane_block(product_type) -> a per-category "safe lane" taught
#            in the generation prompt (prevention: teaches the SWAP, not just a ban).
#   LAYER 2  check_category_claims(listing, product_type) -> a pure pattern-match scan
#            of the FINISHED copy against that category's trigger file (enforcement).
# Pure pattern-match, NO AI call. Whole-word via the SAME _wordish primitive (so "nsf"
# never matches "transfer"). WARN only -- never blocks; the operator stays the final
# gate. Category comes from product_type; blank/unknown -> STRICTEST (screen against
# ALL categories), never guess-safe. Trigger lists are plain editable per-category
# files in claims_rules/ so they can be tuned without touching code.
# ---------------------------------------------------------------------------
_CLAIMS_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                            "claims_rules")
_LANES = ("supplements", "skincare", "cleaning", "devices", "pet", "general")
_RULE_NAMES = {
    "supplements": "disease / health claim",
    "skincare":    "cosmetic drug claim",
    "cleaning":    "pesticide / antimicrobial claim",
    "devices":     "medical-device claim",
    "pet":         "animal-health claim",
    "general":     "unverifiable claim",
}
# Invented / unverifiable certifications -- risky in ANY category (AMBER). Appended to
# every lane so e.g. "BPA-free" with no supporting doc is flagged regardless of the
# product's category.
_INVENTED_CERT = [
    "bpa-free", "bpa free", "non-toxic", "food-safe", "food safe", "phthalate-free",
    "formaldehyde-free", "chemical-free", "hypoallergenic", "clinically proven",
    "doctor recommended", "dermatologist recommended", "fda approved", "eco-certified",
]


def _parse_lane_line(line: str):
    """'SEVERITY | phrase | swap' -> (severity, phrase, swap). A bare line with no '|'
    (or an unrecognised first field) is treated as a RED phrase."""
    parts = [p.strip() for p in line.split("|")]
    if len(parts) == 1:
        return "RED", parts[0], ""
    sev = parts[0].upper()
    if sev not in ("RED", "AMBER"):
        return "RED", parts[0], (parts[1] if len(parts) > 1 else "")
    phrase = parts[1] if len(parts) > 1 else ""
    swap = parts[2] if len(parts) > 2 else ""
    return sev, phrase, swap


def _load_lane(name: str):
    """Load one category's trigger file into (severity, phrase, swap, rule, pattern) rows."""
    rules = []
    path = _os.path.join(_CLAIMS_DIR, name + ".txt")
    try:
        for raw in open(path, encoding="utf-8"):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            sev, phrase, swap = _parse_lane_line(line)
            if phrase:
                rules.append((sev, phrase, swap, _RULE_NAMES.get(name, "claim"), _wordish(phrase)))
    except Exception:
        pass
    return rules


_CATEGORY_RULES = {name: _load_lane(name) for name in _LANES}
# Fold the conservative restricted_phrasing.txt list into the cleaning lane (RED) so
# nothing check_restricted_phrasing catches regresses out of the category screener.
for _p in RESTRICTED_PHRASES:
    _CATEGORY_RULES["cleaning"].append(
        ("RED", _p, "", _RULE_NAMES["cleaning"], _wordish(_p)))
# Invented-certification (AMBER) applies to EVERY lane.
for _lane in _LANES:
    for _p in _INVENTED_CERT:
        _CATEGORY_RULES[_lane].append(
            ("AMBER", _p, "", "unverifiable / invented certification", _wordish(_p)))
# ALWAYS-ON claim buckets (task #14 Part B): PERFORMANCE + SUPERIORITY claims are a
# Restricted-Products risk in EVERY category and REGARDLESS of source (a competitor
# saying it is not a defence), so they fire on every lane. Their rule labels come from
# _RULE_NAMES, set here just before the files are loaded.
_RULE_NAMES["performance"] = "performance claim -- not documentable"
_RULE_NAMES["superiority"] = "superiority claim -- not documentable"
_ALWAYS_ON = _load_lane("performance") + _load_lane("superiority")
for _lane in _LANES:
    _CATEGORY_RULES[_lane].extend(_ALWAYS_ON)


def lane_for_product_type(product_type: str):
    """Map a product_type to its claims lane. Blank/unknown -> None, so the caller
    screens against ALL lanes -- an unknown category is treated as risky, never
    guessed safe."""
    s = re.sub(r"[^A-Za-z0-9]+", " ", str(product_type or "")).upper()
    if not s.strip():
        return None

    def has(*ks):
        return any(k in s for k in ks)

    if has("SUPPLEMENT", "VITAMIN", "NUTRITION", "DIETARY", "PROTEIN", "HERBAL", "PROBIOTIC"):
        return "supplements"
    if has("SKIN", "COSMETIC", "FACIAL", "LOTION", "MOISTURIZ", "MOISTURIS", "SERUM",
           "MAKEUP", "BEAUTY", "SHAMPOO", "SUNSCREEN", "DEODORANT", "CREAM"):
        return "skincare"
    if has("CLEAN", "DISINFECT", "SANITIZ", "SANITIS", "DETERGENT", "BLEACH", "PESTICIDE",
           "INSECTICIDE", "HERBICIDE", "FUNGICIDE", "REPELLENT", "SOAP"):
        return "cleaning"
    if has("MEDICAL", "THERAPEUTIC", "NEBULIZER", "INHALER", "THERMOMETER",
           "ORTHOPEDIC", "MASSAGE", "FIRST AID", "BLOOD PRESSURE", "HEALTH CARE"):
        return "devices"
    if has("PET", "DOG", "CAT", "ANIMAL", "VETERINARY", "AQUARIUM", "BIRD", "POULTRY"):
        return "pet"
    return "general"


# The safe-lane teaching text injected into the generation prompt (Layer 1). Each lane
# teaches what to DO (describe what it IS/DOES) with concrete SWAPS, not just a ban list.
_LANE_TEACH = {
    "supplements": (
        "SUPPLEMENTS / INGESTIBLES -- the HIGHEST disease-claim risk. Use structure/"
        "function language ONLY (supports, maintains, promotes, helps). NEVER say a "
        "product treats, cures, prevents, or diagnoses any disease, and never name a "
        "condition (arthritis, diabetes, depression, cancer). SWAPS: 'treats joint pain' "
        "-> 'supports joint comfort'; 'reduces inflammation' -> 'supports a healthy "
        "inflammatory response'; 'lowers cholesterol' -> 'supports already-healthy "
        "cholesterol'."),
    "skincare": (
        "SKINCARE / COSMETICS -- APPEARANCE language only, no drug claims. Describe how "
        "the product makes skin look and feel; never a skin disease it treats. SWAPS: "
        "'treats dry skin' -> 'moisturises'; 'heals eczema' -> 'soothes the feel of dry, "
        "irritated-looking skin'; 'anti-aging' -> 'reduces the appearance of fine lines'."),
    "cleaning": (
        "CLEANING / CHEMICAL -- the pesticide trap. Do NOT say kill, sanitize, disinfect, "
        "antibacterial, antimicrobial, or mould-resistant unless the product is an "
        "EPA/HSE-registered pesticide. SWAPS: 'kills bacteria' -> 'cleans surfaces'; "
        "'disinfects' -> 'cleans and freshens'; 'mould-resistant' -> 'resists mould "
        "build-up'."),
    "devices": (
        "DEVICES -- no medical-device framing unless the product is actually registered. "
        "Avoid medical grade, therapeutic, nebuliser, inhaler, 'FDA cleared', 'treats "
        "pain'. SWAPS: 'medical grade' -> 'professional style'; 'therapeutic massage' -> "
        "'relaxing massage'; 'treats pain' -> 'helps you feel soothed'."),
    "pet": (
        "PET -- animal use does NOT exempt a health or pesticide claim. The same rules as "
        "human supplements/devices apply. SWAPS: 'cures infection' -> 'supports skin "
        "health'; 'kills fleas' -> 'helps manage fleas' (unless registered)."),
    "general": (
        "GENERAL HARDWARE -- light touch. Describe what the product physically IS and "
        "DOES. Avoid inventing certifications (BPA-free, non-toxic, food-safe) unless you "
        "have a document proving it."),
}
_LANE_COMMON = (
    "\n===================================\n"
    "CLAIMS SAFE-LANE -- MANDATORY\n"
    "===================================\n"
    "Describe what the product physically IS and DOES -- never what it treats, cures, "
    "kills, prevents, or diagnoses. Give the plain-descriptive version, e.g. 'kills "
    "bacteria' -> 'cleans surfaces', 'treats dry skin' -> 'moisturises', 'prevents rust' "
    "-> 'resists corrosion'. HONESTY RULE: if a claim has to be mentally reframed or "
    "justified to be defensible, OMIT it.\n")


def category_lane_block(product_type: str = "") -> str:
    """LAYER 1: the category-aware safe-lane prompt section, keyed off product_type.
    Blank/unknown product_type -> the STRICTEST lane (supplements-level), never the
    lightest -- unknown category is treated as risky."""
    lane = lane_for_product_type(product_type)
    if lane is None:
        teach = _LANE_TEACH["supplements"]
        label = "CATEGORY UNKNOWN -> STRICTEST (disease-claim) RULES APPLIED"
    else:
        teach = _LANE_TEACH.get(lane, _LANE_TEACH["general"])
        label = "CATEGORY: " + lane.upper()
    return _LANE_COMMON + label + "\n" + teach + "\n"


def check_category_claims(listing: dict, product_type: str = "") -> dict:
    """LAYER 2: scan the FINISHED copy against the product's category trigger list.
    WARN-level, never a hard hold. Blank/unknown product_type -> screen against ALL
    lanes (strictest). Returns {"has_flagged", "hits":[{phrase,field,severity,category,
    rule,swap}], "lane", "unknown_category", "summary", "note"}."""
    lane = lane_for_product_type(product_type)
    unknown = lane is None
    lanes = list(_LANES) if unknown else [lane]
    fields = [
        ("title", listing.get("title", "")),
        ("item_highlights", listing.get("item_highlights", "")),
        ("bullet_1", listing.get("bullet_1", "")), ("bullet_2", listing.get("bullet_2", "")),
        ("bullet_3", listing.get("bullet_3", "")), ("bullet_4", listing.get("bullet_4", "")),
        ("bullet_5", listing.get("bullet_5", "")),
        ("description", _strip_html(listing.get("description", ""))),
    ]
    hits, seen = [], set()
    for ln in lanes:
        for sev, phrase, swap, rule, pat in _CATEGORY_RULES.get(ln, []):
            for fname, text in fields:
                if not text:
                    continue
                if pat.search(text):
                    k = (phrase.lower(), fname)
                    if k in seen:
                        continue
                    seen.add(k)
                    hits.append({"phrase": phrase, "field": fname, "severity": sev,
                                 "category": ln, "rule": rule, "swap": swap})
    result = {"has_flagged": bool(hits), "hits": hits,
              "lane": ("ALL" if unknown else lane),
              "unknown_category": unknown, "summary": "", "note": ""}
    if hits:
        lvl = "RED" if any(h["severity"] == "RED" for h in hits) else "AMBER"
        phrases = sorted({h["phrase"] for h in hits})
        cats = sorted({h["category"] for h in hits})
        tail = " (category unknown -- screened against all rules)" if unknown else ""
        result["summary"] = ("CLAIM RISK [%s]: %s -- %s%s"
                             % (lvl, ", ".join(phrases), "/".join(cats), tail))
        result["note"] = "REVIEW: " + result["summary"]
    return result


# ---------------------------------------------------------------------------
# REGULATED / CERTIFICATION CLAIMS (NSF / H1 / FDA / food-grade / 21 CFR / USDA)
# present in the FINISHED copy but NOT in the product's own source docs. Whole-word
# matched via the SAME _wordish primitive the forbidden-brand scanner uses -- so
# "nsf" NEVER matches "tra-nsf-er" (the substring bug that lived in the audit's own
# reimplementation). This is the single source of truth for the check; the audit
# calls THIS function, so a passing audit validates this exact logic.
# (Not yet wired into the generation gate -- that gate enforces named-standard
# grounding only; adding a regulated-claim gate is a separate decision.)
# ---------------------------------------------------------------------------
# Whole-word patterns with FLEXIBLE internal separators so "food grade" == "food-grade"
# == "foodgrade", and the boundary guard so "nsf" never matches "tra-nsf-er".
_REG_PATTERNS = [
    ("nsf h1",          re.compile(r"(?<![a-z0-9])nsf[\s-]*h-?1(?![a-z0-9])", re.I)),
    ("nsf",             re.compile(r"(?<![a-z0-9])nsf(?![a-z0-9])", re.I)),
    ("fda",             re.compile(r"(?<![a-z0-9])fda(?![a-z0-9])", re.I)),
    ("food grade",      re.compile(r"(?<![a-z0-9])food[\s-]*grade(?![a-z0-9])", re.I)),
    ("food contact",    re.compile(r"(?<![a-z0-9])food[\s-]*contact(?![a-z0-9])", re.I)),
    ("incidental food", re.compile(r"(?<![a-z0-9])incidental[\s-]*food(?![a-z0-9])", re.I)),
    ("21 cfr",          re.compile(r"(?<![a-z0-9])21[\s-]*cfr(?![a-z0-9])", re.I)),
    ("usda",            re.compile(r"(?<![a-z0-9])usda(?![a-z0-9])", re.I)),
    ("halal",           re.compile(r"(?<![a-z0-9])halal(?![a-z0-9])", re.I)),
    ("kosher",          re.compile(r"(?<![a-z0-9])kosher(?![a-z0-9])", re.I)),
]


def check_regulated_claims(listing: dict, source_text: str) -> dict:
    """A regulated/certification claim (NSF / H1 / FDA / food-grade / 21 CFR / USDA)
    in the finished copy is UNSUPPORTED only when the source docs contain NO food-grade
    evidence AT ALL (any marker, any wording). This 'does the source support the concept'
    test avoids two false-positive traps: substring ('nsf' in 'transfer') AND wording
    ('food grade' in copy vs 'food-grade' in source). Returns
    {"has_unsupported": bool, "hits": [markers-in-copy], "summary": str}."""
    result = {"has_unsupported": False, "hits": [], "summary": ""}
    blocks = [listing.get("title", ""), listing.get("item_highlights", ""),
              listing.get("bullet_1", ""), listing.get("bullet_2", ""),
              listing.get("bullet_3", ""), listing.get("bullet_4", ""),
              listing.get("bullet_5", ""), _strip_html(listing.get("description", "")),
              listing.get("search_terms", "") or listing.get("backend_keywords", "")]
    copy = " ".join(b for b in blocks if b)
    src  = source_text or ""
    copy_hits   = [name for name, rx in _REG_PATTERNS if rx.search(copy)]
    src_has_any = any(rx.search(src) for _, rx in _REG_PATTERNS)
    if copy_hits and not src_has_any:
        result["has_unsupported"] = True
        result["hits"] = copy_hits
        result["summary"] = ("UNSUPPORTED REGULATED CLAIM(S) -- source has NO food-grade "
                             "evidence: " + ", ".join(sorted(set(copy_hits))))
    return result


# ---------------------------------------------------------------------------
# NUMERIC GROUNDING -- a quantified figure in the copy is a fabrication ONLY if,
# after UNIT-NORMALISATION and TOLERANCE, it neither appears in nor is derivable
# from the source. Derivable = same value in different units (F<->C), inside a
# source-stated range, or within a small rounding tolerance. This is the whole
# point: a legit F/C conversion is NOT a mismatch, so it must never HOLD.
# Two tiers: a number with an explicit unit AND a performance-property keyword
# that can't be derived is CONFIDENT (-> HOLD); every other ungrounded figure is
# UNCERTAIN (-> WARN note, never a hard hold). Malformed concatenations (460Miles,
# 0FG) carry no unit + keyword, so they can never HOLD.
# ---------------------------------------------------------------------------
_UNIT_FIG_RE = re.compile(
    r"(-?\d[\d,]*(?:\.\d+)?)\s*°?\s*(cSt|centistokes?|ppm|%|hours?|hrs?|kg|Nm|[FC]\b)", re.I)
_PERF_KW_RE = re.compile(
    r"(flash\s*point|pour\s*point|viscosity\s*index|\bVI\b|timken|zinc|demulsibility|"
    r"oxidation|copper\s*corrosion|kinematic|viscosit)", re.I)
_KW_NUM_RE = re.compile(
    r"(?:flash\s*point|pour\s*point|viscosity\s*index|\bVI\b|timken|zinc|demulsibility|"
    r"oxidation|copper\s*corrosion|iso\s*vg|\biso\b)\D{0,18}(-?\d[\d,]*(?:\.\d+)?)", re.I)
_PACK_NEAR_RE = re.compile(
    r"\b(gallon|gal|oz|ounce|pail|drum|quart|litre|liter|ml|pack|case|lb|pound)\b", re.I)


def _parse_numbers(text: str):
    """(floats, ranges) from a blob. Thousands commas stripped; ranges '44-48' /
    '44 to 48' captured so a copy value inside them grounds."""
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text or "")
    ranges = []
    for m in re.finditer(r"(-?\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(-?\d+(?:\.\d+)?)", t):
        try:
            a, b = float(m.group(1)), float(m.group(2))
            ranges.append((min(a, b), max(a, b)))
        except Exception:
            pass
    nums = []
    for m in re.finditer(r"-?\d+(?:\.\d+)?", t):
        try:
            nums.append(float(m.group(0)))
        except Exception:
            pass
    return nums, ranges


def _num_status(n: float, src_nums, src_ranges) -> str:
    """'grounded' -- n (or its F<->C conversion) matches a source number within tight
    tolerance (+/-1 or +/-2%) or falls in a source range. 'near' -- loosely close
    (rounding / product-variant / messy source -- UNCERTAIN, warn not hold). 'far' --
    nothing anywhere near, even converted (likely fabricated)."""
    cands = (n, (n - 32.0) * 5.0 / 9.0, n * 9.0 / 5.0 + 32.0)   # value, F->C, C->F
    for c in cands:
        if any(abs(c - s) <= max(1.0, abs(s) * 0.02) for s in src_nums):
            return "grounded"
    if any(lo - 0.5 <= n <= hi + 0.5 for lo, hi in src_ranges):
        return "grounded"
    for c in cands:
        if any(abs(c - s) <= max(8.0, abs(s) * 0.15) for s in src_nums):
            return "near"
    for lo, hi in src_ranges:
        span = abs(hi - lo) + 5.0
        if lo - span <= n <= hi + span:
            return "near"
    return "far"


def check_numeric_grounding(listing: dict, source_text: str) -> dict:
    """Unit-normalised numeric grounding. Returns
    {"has_fabricated": bool, "fabricated": [figs], "warnings": [figs], "summary"}.
    Empty when source is blank (the caller refuses no-source rows separately)."""
    result = {"has_fabricated": False, "fabricated": [], "warnings": [], "summary": ""}
    if not (source_text or "").strip():
        return result
    blocks = [listing.get("title", ""), listing.get("item_highlights", ""),
              listing.get("bullet_1", ""), listing.get("bullet_2", ""),
              listing.get("bullet_3", ""), listing.get("bullet_4", ""),
              listing.get("bullet_5", ""), _strip_html(listing.get("description", ""))]
    copy = " ".join(b for b in blocks if b)
    src_nums, src_ranges = _parse_numbers(source_text)
    seen = set()

    def _val(raw):
        try:
            return float(raw.replace(",", "").rstrip("."))
        except Exception:
            return None

    # CONFIDENT vs UNCERTAIN split on unit-bearing figures.
    for m in _UNIT_FIG_RE.finditer(copy):
        n = _val(m.group(1))
        if n is None:
            continue
        ctx = copy[max(0, m.start() - 35):m.end() + 5]
        if _PACK_NEAR_RE.search(ctx):
            continue
        # A figure preceded by "at"/"@" is a MEASUREMENT CONDITION ("at 40C", "at
        # 100C", "at 130C") -- the reference temperature a property is measured at,
        # not a claimed value. Never a fabrication.
        if re.search(r"(?:\bat|@)\s*$", copy[max(0, m.start() - 5):m.start()], re.I):
            continue
        key = round(n, 2)
        if key in seen:
            continue
        seen.add(key)
        st = _num_status(n, src_nums, src_ranges)
        if st == "grounded":
            continue
        if st == "far" and _PERF_KW_RE.search(ctx):
            result["fabricated"].append(m.group(0).strip())     # unit + property, nothing near -> HOLD
        else:
            result["warnings"].append(m.group(0).strip()[:48])  # near-miss or unit-only -> WARN

    # Keyword-adjacent numbers WITHOUT a unit -> WARN only (never HOLD).
    for m in _KW_NUM_RE.finditer(copy):
        n = _val(m.group(1))
        if n is None or round(n, 2) in seen:
            continue
        if _num_status(n, src_nums, src_ranges) == "far":
            result["warnings"].append(m.group(0).strip()[:48])

    if result["fabricated"]:
        result["has_fabricated"] = True
        result["summary"] = ("UNSUPPORTED FIGURE(S) not in/derivable from source: "
                             + ", ".join(result["fabricated"]))
    return result


def check_ip_violations(listing: dict, brand: str, ip_rules: dict,
                        competitor_brands=None) -> dict:
    """
    Universal IP scan. Two checks:
      1. Forbidden comparative phrases ("compatible with", "OEM approved", etc.).
         Scans EVERYWHERE including title.
      2. Unrecognised capitalised words in body copy. ANY capitalised word that
         isn't a sentence opener / brand / safelisted / acronym / short word
         is treated as a potential brand mention -> flagged.
         Title is EXCLUDED from caps scanning by default because Amazon titles
         use Title Case by convention (every word capitalised), which would
         produce constant false positives.

    Returns {
      "has_violations":  bool,
      "phrases_found":   [list of matched forbidden phrases],
      "unknown_caps":    [list of unrecognised capitalised tokens],
      "summary":         short string for the Notes column,
    }
    """
    empty = {"has_violations": False, "phrases_found": [],
             "unknown_caps": [], "competitor_hits": [], "summary": ""}
    if not ip_rules:
        return empty

    title = listing.get("title", "")
    body_blocks = [
        listing.get("bullet_1", ""), listing.get("bullet_2", ""),
        listing.get("bullet_3", ""), listing.get("bullet_4", ""),
        listing.get("bullet_5", ""),
        _strip_html(listing.get("description", "")),
        listing.get("search_terms", ""),
    ]
    phrase_scan_text = " ".join([title] + [b for b in body_blocks if b])
    phrase_scan_lower = phrase_scan_text.lower()

    # --- Forbidden comparative phrases (title INCLUDED) ----------------------
    phrases_found = []
    for phrase in ip_rules.get("forbidden_phrases", []):
        try:
            if re.search(rf"\b{re.escape(phrase.lower())}\b", phrase_scan_lower):
                phrases_found.append(phrase)
        except re.error:
            if phrase.lower() in phrase_scan_lower:
                phrases_found.append(phrase)

    # --- COMPETITOR BRAND (the real IP risk, and it is EVIDENCE not a guess) --
    # The app pulls the competitor's title/specs to build a NEW listing under the
    # owner's own brand (CLAUDE.md §1). The genuine exposure is the competitor's
    # brand name LEAKING into that copy. Until now nothing checked for it: this
    # function only ever received the OWNER's brand, as a safe word. So the one
    # name we can prove is a trademark was the one name we never looked for.
    #
    # Scanned with the same _wordish boundary guard used by check_forbidden_brands
    # so a brand never matches inside a longer word ("Esso" in "compressor").
    competitor_hits = []
    for cb in (competitor_brands or []):
        cb = (cb or "").strip()
        if len(cb) < 3:
            continue                      # 1-2 char "brands" match far too much
        if cb.lower() in _split_brand_words(brand):
            continue                      # same as our own brand -- not a leak
        if _wordish(cb).search(phrase_scan_text):
            competitor_hits.append(cb)

    # --- Unrecognised capitalised words (title EXCLUDED) ---------------------
    brand_words   = _split_brand_words(brand)
    safe_lc       = ip_rules.get("safe_capitalised_lc", set())
    unknown_caps  = []
    seen_unknowns = set()

    caps_scan_text = " ".join(b for b in body_blocks if b)
    # Treat each body block as ending in implicit period so cross-block words
    # don't get falsely scanned as mid-sentence.
    caps_scan_text = ". ".join(b for b in body_blocks if b)
    # A DASH ENDS A LABEL JUST AS A COLON DOES.
    #
    # Bullets are written in this app's own house style -- an ALL-CAPS label,
    # then an em-dash, then the sentence:
    #
    #     200 KG LOAD CAPACITY — Heavy-duty aluminium carabiner and ...
    #
    # Splitting only on . ! ? : ; left "Heavy-duty" looking like a capitalised
    # word in the MIDDLE of a sentence, which is what this scan treats as a
    # possible brand. Every bullet the app writes therefore contributed one
    # false positive, and five bullets is above the tolerance of four -- so a
    # perfectly ordinary listing went to IP_HOLD on the strength of its own
    # formatting. Measured on a real one: "Heavy-duty, Aerial, Yoga, Sensory,
    # Swing" reported as possible brands, none of which is a brand.
    #
    # Em-dash, en-dash, and a spaced hyphen used the same way.
    sentences = re.split(r"(?<=[.!?:;])\s+|\s+[—–]\s+|\s+-\s+", caps_scan_text)
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        tokens = re.findall(r"[A-Za-z][A-Za-z\-']*", sent)
        for i, tok in enumerate(tokens):
            if not tok or not tok[0].isupper():
                continue
            if i == 0:                              # sentence opener -- skip
                continue
            tok_lc = tok.lower()
            # Contractions and possessives are ordinary English, never brands.
            # "Father's", "You're" and "Whole'" were all reported as suspected
            # brands on a real run -- they are a family word, a pronoun and a
            # stray quote mark. Reduce to the base word and judge THAT.
            tok_lc = tok_lc.rstrip("'")
            if "'" in tok_lc:
                _stem, _, _suffix = tok_lc.rpartition("'")
                if _stem and _suffix in ("s", "re", "t", "ll", "ve", "d", "m"):
                    tok_lc = _stem
            if not tok_lc:
                continue
            if tok_lc in brand_words:               # our own brand
                continue
            if tok_lc in safe_lc:                   # explicit allowlist
                continue
            # Strip common compound suffixes ("PFOA-free", "Water-Resistant", "Lead-safe")
            # and re-check against safelist with just the head word
            head = re.sub(r"-(free|resistant|proof|safe|friendly|ready|grade|tested|certified|approved|coated|treated|based)$",
                          "", tok_lc)
            if head and head != tok_lc and head in safe_lc:
                continue
            # Pure-uppercase short tokens (<=5) treated as acronyms
            if tok.isupper() and len(tok) <= 15:   # ALL-CAPS = emphasis label (PORTABLE, OUTDOOR, SECONDS), not a brand
                continue
            # Single letter (e.g. "I" in some contexts) -- skip
            if len(tok) <= 1:
                continue
            # Already reported this token in this listing -- skip duplicates
            if tok_lc in seen_unknowns:
                continue
            seen_unknowns.add(tok_lc)
            unknown_caps.append(tok)

    # Allow a tolerance -- proper nouns slip through (place names, sentence
    # parsing edge cases). Trigger violation only beyond the threshold.
    threshold = ip_rules.get("max_unrecognised", 4)
    caps_violation = len(unknown_caps) > threshold

    # A competitor brand in our copy is PROOF, so it violates on its own. The
    # capitalised-word scan stays a guess and keeps its tolerance threshold.
    has_violations = bool(phrases_found) or caps_violation or bool(competitor_hits)

    summary_parts = []
    if competitor_hits:
        summary_parts.append(f"COMPETITOR BRAND in copy: {', '.join(competitor_hits[:5])}")
    if phrases_found:
        summary_parts.append(f"phrases: {', '.join(phrases_found[:5])}")
    if caps_violation:
        summary_parts.append(f"possible brand words (unconfirmed): {', '.join(unknown_caps[:8])}")

    return {
        "has_violations":  has_violations,
        "phrases_found":   phrases_found,
        "unknown_caps":    unknown_caps,
        "competitor_hits": competitor_hits,
        "summary":         ("IP RISK | " + " | ".join(summary_parts)) if summary_parts else "",
    }
