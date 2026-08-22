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
import functools
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


@functools.lru_cache(maxsize=8192)
def wordish(term):
    """Whole-word (alphanumeric-boundary) matcher for a term.

    PUBLIC because listing/sourcing_viability.py matches words the same way. One
    matcher, one place -- two copies would drift and the two layers would start
    disagreeing about what counts as a word.

    KEPT ONCE BUILT. The terms come from fixed rulebooks on disk, so the same
    few thousand strings are asked for again and again -- and the answer for a
    given string never changes. Measured on the Listings screen (88 rows,
    jack_uk): 11,502 calls to re.escape and re.compile per request, all of them
    rebuilding patterns that had just been built. A compiled pattern is
    immutable, so handing the same one back is the same answer, not a shared
    mutable thing.
    """
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.I)


_wordish = wordish          # internal name kept so existing call sites don't move


# --- KEYWORD CLASSIFIER ------------------------------------------------------
# Distinctive single words that ARE strong enough to flag alone.
_STRONG_SINGLES = {
    "nebulizer", "nebuliser", "inhaler", "hydroquinone", "ephedra", "dmaa", "phenibut",
    "tianeptine", "kratom", "kava", "sarms", "yohimbine", "sildenafil", "tadalafil",
    "jammer", "freon", "taser", "slimjim",
    # Cannabinoid terms: distinctive, never ordinary English, and cbd_hemp is
    # PROHIBITED on both marketplaces -- these must be able to flag on their own.
    "cbd", "cannabidiol", "cannabinoid", "cannabinoids", "thc", "cannabis", "marijuana",
    # Tobacco/vaping is PROHIBITED in the US. These name the product itself and
    # are not ordinary English, so a bare "vape" must flag without needing a
    # product_type to corroborate -- a pasted title is often all Shape 1 gets.
    "vape", "vaping", "nicotine", "hookah", "shisha",
    # "upholstered" is the precise regulated term (fire-safety gated). "sofa" and
    # "mattress" stay corroborating on purpose: a sofa THROW or mattress PROTECTOR
    # is a textile, not gated furniture.
    "upholstered",
}
# Multi-word / digit-bearing terms that are nonetheless too BROAD to flag alone.
# NOTE: precise real-restriction terms (class 3 LASER, signal booster, high power vtx,
# high power laser, mw laser) are deliberately NOT here -- they name the actual restricted
# product and must stay STRONG. Only genuinely ambiguous fragments live here.
_BROAD_OVERRIDE = {
    "class 3", "class 4", "class ii", "class iiib", "medical grade", "1w", "heavy duty",
    "coolant gas", "high power",
    # Multi-word but still ambiguous: a "Cooking Oil Dispenser Bottle" is a
    # container, not groceries. Needs a grocery browse-node to count.
    "cooking oil",
}

# --- ACCESSORY DEMOTION (keyword tier) ---------------------------------------
# A keyword hit IMMEDIATELY followed by an accessory noun names the accessory,
# not the regulated product: "Patio Heater Cover" is a waterproof textile and
# "heater thermostat" is a spare part -- neither needs a BS EN 60335-2-30 test
# report. Adjacency is strict on purpose: "Patio Heater with Cover" (a real
# heater sold with a cover) and "Heater Protective Cover" both still flag.
# Over-flagging is the safe direction for a sourcing alarm; under-flagging is
# not. Keyed by category id so it can never leak across categories.
# ACCESSORY_NOUNS and accessory_pattern() are PUBLIC: listing/sourcing_viability.py
# applies the identical rule to appliance nouns, so the noun list and the
# adjacency pattern are defined here once and imported there.
ACCESSORY_NOUNS = [
    "cover", "covers", "case", "bag", "sleeve", "stand", "bracket",
    "brackets", "mount", "remote", "thermostat", "replacement", "spare",
    "spares", "part", "parts", "accessory", "accessories", "filter",
    "filters", "wheels", "casters",
    # THE THING THAT PUTS THE SUBSTANCE ON, which is not the substance. Added
    # when lubricants were brought under the chemicals rule and "Chain Oil
    # Applicator" -- a tool -- started asking for a safety data sheet. Same
    # shape as "Patio Heater Cover": the noun immediately after the trigger
    # names what is being sold.
    "applicator", "applicators", "dispenser", "dispensers", "gun", "guns",
    "nozzle", "nozzles", "pump", "pumps",
]

_ACCESSORY_SUFFIXES = {
    "electric_heating_appliances": ACCESSORY_NOUNS,
}


def accessory_pattern(term, suffixes=None):
    """'<term> <accessory-noun>' matcher -- the shared strict-adjacency rule."""
    sfx = suffixes or ACCESSORY_NOUNS
    return re.compile(re.escape(term) + r"[\s\-]+(?:" + "|".join(re.escape(s) for s in sfx)
                      + r")(?![A-Za-z0-9])", re.I)


# --- COMPATIBILITY, which is the opposite of being the thing ----------------
# A cast-iron wok whose listing says "works on gas, ELECTRIC and induction hobs"
# was flagged as a mains-powered electrical product needing a BS EN 60335 test
# report. It is a lump of steel. The word "electric" was there, but it described
# what the pan is USED WITH, and a phrase like "works on" or "compatible with"
# is the ordinary English marker for that.
#
# This is the same shape as the accessory rule above -- "patio heater COVER" is
# not a heater -- applied to the words in front of a trigger rather than behind
# it. A false HIGH RISK is not a harmless extra check: it teaches people to
# ignore the ones that are real.
COMPAT_LEADS = [
    "works on", "works with", "works in", "work on", "work with",
    "compatible with", "compatible for", "suitable for", "suitable on",
    "for use on", "for use with", "for use in", "use on", "use with",
    "safe for", "safe on", "safe to use on", "designed for", "made for",
    "fits", "fits on", "fits all", "ideal for", "perfect for",
    "can be used on", "can be used with", "usable on",
]


def compat_pattern(term, leads=None):
    """'<compatibility phrase> ... <term>' matcher.

    The gap allows the list a real sentence uses -- "works on gas, electric and
    induction hobs" puts two words between the lead and the trigger -- but is
    short enough that a lead in one clause cannot reach a trigger in the next.
    """
    lead = "|".join(re.escape(s) for s in (leads or COMPAT_LEADS))
    return re.compile(r"(?:" + lead + r")\b[\w\s,/&'-]{0,40}?"
                      + re.escape(term) + r"(?![A-Za-z0-9])", re.I)


# WHAT A PRODUCT ACTS ON IS NOT WHAT IT IS.
#
# Third member of the same family as the accessory rule ("patio heater COVER")
# and the compatibility rule ("works on electric hobs"). Those cover the words
# BEHIND a trigger and the words IN FRONT of it. This covers the case where the
# trigger is the thing being removed, cleaned off, or protected against.
#
# The one that got reported: a floor scrub brush described as tackling "dried
# residue and ADHESIVE MARKS" was declared a HIGH RISK chemical product needing
# CLP classification, an SDS, REACH registration and a poison-centre
# notification. It is a brush. The word "adhesive" was in it because the brush
# scrapes adhesive off floors.
#
# Two shapes, because English puts it either way round:
#   verb first   "removes adhesive", "cleans grease", "protects against rust"
#   noun after   "adhesive marks", "grease residue", "rust stains"
#
# Deliberately generic. A rust REMOVER is still a chemical and must still fire --
# which it does, because "rust remover" is its own trigger term and the product
# is named by it; this only demotes the bare word when every occurrence of it is
# something the product is used AGAINST.
TARGET_LEADS = [
    "removes", "remove", "removing", "removal of", "removes any", "removes all",
    "lifts", "lift", "lifting", "cleans", "clean", "cleaning", "cleans off",
    "wipes", "wipe", "wipes away", "scrubs", "scrub", "scrapes", "scrape",
    "tackles", "tackle", "dissolves", "dissolve", "strips", "strip",
    "eliminates", "eliminate", "clears", "clear", "gets rid of",
    "protects against", "protect against", "prevents", "prevent",
    "resistant to", "resists", "guards against", "shields against",
    "against", "free from", "without any",
]

# Nouns that mark the trigger as a deposit or blemish rather than the product.
TARGET_TAILS = [
    "mark", "marks", "residue", "residues", "stain", "stains", "spill",
    "spills", "deposit", "deposits", "buildup", "build-up", "build up",
    "grime", "film", "smear", "smears", "streak", "streaks", "dirt",
    "damage", "corrosion", "odour", "odor", "smell", "smells",
]


def target_pattern(term, leads=None, tails=None):
    """'<removal verb> ... <term>' or '<term> <deposit noun>' matcher.

    Same short gap as compat_pattern, for the same reason: a verb in one clause
    must not reach a trigger in the next.
    """
    lead = "|".join(re.escape(s) for s in (leads or TARGET_LEADS))
    tail = "|".join(re.escape(s) for s in (tails or TARGET_TAILS))
    t = re.escape(term)
    return re.compile(
        r"(?:(?:" + lead + r")\b[\w\s,/&'-]{0,40}?" + t + r"(?![A-Za-z0-9])"
        r"|" + t + r"\s+(?:" + tail + r")(?![A-Za-z0-9]))", re.I)


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
    "childrens_products": ["toy", "children", "toddler", "kids", "baby", "infant"],
    "lasers": ["laser pointer"],
    "refrigerants_ozone": ["refrigerant"],
    "jewelry_precious": ["jewelry", "jewellery", "gemstone"],
    "tobacco_vaping": ["tobacco", "vape", "vaping", "e-cigarette", "e-liquid", "nicotine"],
    # --- categories added by the patch merge ---------------------------------
    # A category signal flags ON ITS OWN, so every token here must mean the
    # product genuinely IS in the category. Broad ones are deliberately absent:
    # "electronics" would match Amazon's entire Electronics tree and flag every
    # gadget, which is how a check stops meaning anything. Only the specifically
    # regulated device names are listed.
    "electronics": ["signal booster", "rf transmitter", "radio transmitter",
                    "signal jammer", "radio frequency device"],
    "drugs_otc": ["medicine", "medication", "pharmacy", "otc drug",
                  "over-the-counter drug"],
    "alcohol": ["alcoholic beverage", "wine", "beer", "spirits", "liquor"],
    "explosives_fireworks": ["firearm", "ammunition", "firework", "pyrotechnic",
                             "explosive"],
    "composite_wood": ["composite wood", "engineered wood", "particleboard",
                       "particle board", "mdf", "fiberboard", "fibreboard",
                       "plywood", "chipboard"],
    "upholstered_furniture": ["upholstered", "sofa", "couch", "mattress",
                              "armchair", "recliner", "futon", "loveseat"],
    "animals": ["live animal", "live fish", "live insect", "live reptile", "livestock"],
    "cpap_ozone_cleaners": ["cpap", "ozone generator", "sleep apnea"],
    "pesticides_biocides": ["pesticide", "insecticide", "herbicide", "biocide",
                            "rodenticide", "pest control", "insect repellent"],
    "food_grocery": ["grocery", "gourmet food", "food & grocery",
                     "food and grocery", "grocery & gourmet", "pantry"],
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
    # "mains_electrical" retired 2026-08-11: being mains-powered is not a listing
    # RESTRICTION, it is a document-demand liability. That belongs to
    # listing/sourcing_viability.py (MAINS_ELECTRICAL), which detects it from
    # physical signals -- wattage, voltage, plug wording -- instead of the six
    # keywords this entry carried, and returns the full BS EN 60335 doc set.
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


def resolve_docs_display(doc_ids_or_strings):
    """Tier-3 uses doc_ids (resolve via catalog); master uses plain strings. Return display names.

    PUBLIC: listing/sourcing_viability.py resolves its document lists through this
    same function, so required_docs.json stays the one document catalog for the
    whole app and a doc renamed there changes everywhere at once.
    """
    catalog = _DOCS.get("docs") or {}
    out = []
    for d in (doc_ids_or_strings or []):
        if isinstance(d, str) and d in catalog:
            out.append(catalog[d].get("name", d))
        else:
            out.append(str(d))
    return out


_resolve_docs_display = resolve_docs_display     # internal name kept for existing call sites


def _unwrap_docs(raw, mkt):
    """A docs value may be a flat list OR a per-marketplace dict {"UK":[...],"US":[...]}.

    The merged master carries BOTH shapes: the hand-built categories use a flat
    list, and every entry that came from restricted_categories_patch.json uses the
    dict. Iterating the dict directly would render the KEYS ("US", "UK") as if
    they were document names, so it is unwrapped for the active marketplace here
    -- once, for every caller.
    """
    if isinstance(raw, dict):
        raw = raw.get(mkt) or raw.get("UK") or raw.get("US") or []
    return raw if isinstance(raw, list) else []


def _docs_for_match(entry, mkt):
    """Resolve the display docs for a matched entry, MARKETPLACE-AWARE.

    Tier-3 docs are authoritative (they come from real Amazon notices) but are a
    single flat list with no marketplace dimension. The merged master often has
    a per-marketplace dict for the same category. Showing only tier-3 therefore
    handed a US seller the UK document list -- 'HSE / GB biocidal product
    authorisation' for a US pesticide, which is the wrong regulator entirely.

    So: tier-3 first (authority preserved), then the active marketplace's master
    docs appended, de-duplicated. Nothing is lost and the marketplace-correct
    documents are always present.
    """
    out, seen = [], set()

    def _add(items):
        for d in items:
            k = str(d).strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append(d)

    raw = entry.get("docs_tier3")
    mraw = entry.get("docs_master_raw")
    # Marketplace-specific docs lead: a US seller must read "EPA registration"
    # first, not the UK regulator. Tier-3's authority is over STATUS and reason,
    # which are unaffected -- its docs still follow, nothing is dropped.
    if isinstance(mraw, dict):
        _add(_resolve_docs_display(_unwrap_docs(mraw, mkt)))
    if raw is not None:
        _add(_resolve_docs_display(_unwrap_docs(raw, mkt)))
    elif not isinstance(mraw, dict):
        _add(entry.get("docs") or [])
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
        _docs_raw = e.get("docs")
        canon[cid] = {
            "id": cid,
            "label": e.get("label", cid),
            "keywords": list(e.get("trigger_keywords") or []),
            "statuses": {
                "UK": {"value": _master_status_for(e, "UK"), "source": "master_research"},
                "US": {"value": _master_status_for(e, "US"), "source": "master_research"},
            },
            # Patched-in categories carry no detail/note; their marketplaces map
            # already spells out the rule ("GATED -- EPA registration required
            # under FIFRA"), which _master_status_for surfaces as the status.
            "reason": e.get("detail") or e.get("note") or "",
            "regulator": e.get("regulator", ""),
            # Flat list resolved now; a per-marketplace dict is kept raw and
            # resolved per request by _docs_for_match, which knows the marketplace.
            "docs": _resolve_docs_display(_docs_raw) if isinstance(_docs_raw, list) else [],
            "docs_master_raw": _docs_raw if isinstance(_docs_raw, dict) else None,
            "depth": e.get("depth", ""),
            # Patch-only field, surfaced so an operator sees WHY a category is
            # prone to firing on innocent copy before they act on the flag.
            "false_positive_warning": e.get("false_positive_warning", ""),
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
        # prefer tier-3 verbatim reason/docs/regulator BY SOURCE PRECEDENCE, so a later
        # generic UNVERIFIED entry (e.g. medical_device_general) never clobbers an earlier
        # CONFIRMED one's richer docs/reason (e.g. nebulizer_inhaler's verbatim 510(k) set).
        _ent_rank = max([_SRC_RANK.get((sv or {}).get("source", ""), 0)
                         for sv in (e.get("status") or {}).values()] or [0])
        if _ent_rank >= base.get("_meta_rank", -1):
            base["_meta_rank"] = _ent_rank
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
for _cid, _e in _ENTRIES.items():
    _e["kw_strong"] = [(kw, _wordish(kw)) for kw in _e["keywords"] if classify_keyword(kw) == "strong"]
    _e["kw_corrob"] = [(kw, _wordish(kw)) for kw in _e["keywords"] if classify_keyword(kw) == "corroborating"]
    # one "<keyword> <accessory-noun>" pattern per strong keyword, compiled once
    _sfx = _ACCESSORY_SUFFIXES.get(_cid)
    _e["kw_accessory"] = ({kw: accessory_pattern(kw, _sfx)
                           for kw, _pat in _e["kw_strong"]} if _sfx else {})
    # ONE PASS BEFORE EIGHTEEN. This entry's strong keywords as a single
    # alternation, with the SAME boundary guards wordish() puts on each one:
    #
    #     (?<![A-Za-z0-9])(?:nebulizer|inhaler|...)(?![A-Za-z0-9])
    #
    # It matches exactly when at least one of the individual patterns matches --
    # the engine backtracks between alternatives at each position, so a keyword
    # that fails its right-hand boundary does not stop another from being tried
    # there. Equivalent by construction, and checked against the old path over
    # every listing in the database plus adversarial strings (test_restricted_
    # screen.py).
    #
    # WHY: the Listings screen ran 73,919 regex searches for 88 rows -- 840
    # patterns per row, against titles that match none of them. Almost every
    # entry can now be dismissed with one search instead of eighteen.
    _e["kw_screen"] = (re.compile(
        r"(?<![A-Za-z0-9])(?:"
        + "|".join(re.escape(kw) for kw, _p in _e["kw_strong"])
        + r")(?![A-Za-z0-9])", re.I) if _e["kw_strong"] else None)


def _accessory_only(entry, text, hits):
    """True when EVERY keyword hit names an accessory to the restricted product
    rather than the product itself. See _ACCESSORY_SUFFIXES. One hit that is not
    accessory-qualified is enough to keep the whole match."""
    pats = entry.get("kw_accessory") or {}
    if not pats or not hits:
        return False
    for kw in hits:
        pat = pats.get(kw)
        if pat is None or not pat.search(text):
            return False
    return True


# Context that DISQUALIFIES a category signal (avoids cross-category false positives, e.g. a
# PET_TOY / "Pet Supplies" product wrongly read as a children's toy off the word "toy").
_CATEGORY_EXCLUDE = {
    "childrens_products": ["pet", "dog", "cat", "aquarium"],
    # A pet bed/cushion is not regulated upholstered furniture, and doll's-house
    # furniture is not a sofa.
    "upholstered_furniture": ["pet", "dog", "cat", "doll", "dolls", "toy"],
    # Glassware, openers, racks and coolers are not alcohol.
    "alcohol": ["glass", "glasses", "opener", "rack", "cooler", "decanter",
                "aerator", "non-alcoholic", "alcohol-free"],
    # Animal-print and plush goods are not live animals or animal parts.
    "animals": ["toy", "plush", "costume", "print", "sticker"],
    # Keep drugs_otc to human medicines; veterinary sits under pet products.
    "drugs_otc": ["veterinary", "pet"],
    # Grocery-adjacent hardware is not food: tea-light holders, coffee grinders,
    # oil dispensers, spice racks and storage tubs.
    "food_grocery": ["candle", "holder", "dispenser", "grinder", "rack",
                     "container", "storage", "mug", "cup", "utensil"],
}


def _category_haystack(product_type, category_path, browse_nodes):
    """The product's category words, lowercased, as one string.

    Built ONCE PER PRODUCT. It used to be built inside _category_signal, which
    is called once per category in the rulebook -- so the same three fields were
    joined and lowercased forty-six times for every single listing on the
    screen, always giving the same string.
    """
    return "  ".join(str(x) for x in (product_type, category_path,
                     " ".join(browse_nodes or [])) if x).lower()


def _category_signal(cid, product_type, category_path, browse_nodes, hay=None):
    """Does this product look like it is IN category `cid`?

    `hay` is the product's category words, already joined. Passing it in is the
    only reason this takes it: the caller has forty-six of these to do and the
    answer to "what are this product's category words" does not change between
    them. Left optional so every other call site is unaffected.
    """
    tokens = _CATEGORY_SIGNALS.get(cid)
    if not tokens:
        return False
    if hay is None:
        hay = _category_haystack(product_type, category_path, browse_nodes)
    for ex in _CATEGORY_EXCLUDE.get(cid, []):
        if _wordish(ex).search(hay):
            return False
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
    _hay = _category_haystack(product_type, category_path, browse_nodes)
    for cid, e in _ENTRIES.items():
        cat_sig = _category_signal(cid, product_type, category_path, browse_nodes,
                                   hay=_hay)
        # The screen first: one search that can only fail if every one of this
        # entry's strong keywords would have failed. See kw_screen above.
        _screen = e.get("kw_screen")
        strong_hits = ([] if (_screen is None or not _screen.search(text_hay))
                       else [kw for kw, pat in e["kw_strong"]
                             if pat.search(text_hay)])
        # DEMOTION RULE: a corroborating word only counts WITH a category signal.
        matched = bool(strong_hits) or cat_sig
        if not matched:
            continue
        # AND ONLY THEN the corroborating words. They are read in exactly one
        # place -- used_kws below, behind `if cat_sig` -- and they do not decide
        # `matched`, so computing them without a category signal was work whose
        # answer was thrown away. Half the searches on this screen were that.
        corrob_hits = ([kw for kw, pat in e["kw_corrob"] if pat.search(text_hay)]
                       if cat_sig else [])
        # An ACCESSORY to a restricted product is not the restricted product.
        # Only ever suppresses when no category signal says the product really
        # is in the category.
        if strong_hits and not cat_sig and _accessory_only(e, text_hay, strong_hits):
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
            "docs": _docs_for_match(e, mkt),
            "depth": e.get("depth", ""),
            "matched_keywords": used_kws,
            "category_signal": cat_sig,
            "asin_seen": e.get("asin_seen", ""),
            "false_positive_warning": e.get("false_positive_warning", ""),
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
