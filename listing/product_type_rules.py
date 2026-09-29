"""listing/product_type_rules.py -- the engine's product-type rules: codes, inference, allowed types, routes, fallbacks.

Moved word for word out of amazon_listing_generator.py (Milestone 4, owner-approved 28 Sep 2026).
amazon_listing_generator.py still imports every name below, so dashboard.<name> and every
route that is handed one keep working exactly as before. Nothing here may
import dashboard (it would load a second copy of the app).
"""

import re


def derive_product_type_code(product_type: str) -> str:
    """First 3 letters of product_type, uppercased. e.g. COOKWARE_SET -> COO."""
    if not product_type:
        return "GEN"
    cleaned = re.sub(r"[^A-Za-z]", "", product_type).upper()
    return (cleaned[:3] or "GEN")


# Keyword -> Amazon product_type inference. Used ONLY when SP-API and the PDP
# scrape both fail to provide a product type (e.g. the SP-API app lacks the
# Catalog Items role). Ordered: the FIRST matching rule wins, so put more
# specific patterns before generic ones.
_PT_INFER_RULES = [
    (r"\bflash\s?light|\btorch\b|\bhead\s?lamp|\blantern\b|\bwork\s?light", "FLASHLIGHT"),
    (r"\bstring\s?light|\bfairy\s?light|\bfestoon", "STRING_LIGHT"),
    (r"\bdesk\s?lamp|\btable\s?lamp|\bfloor\s?lamp|\bbedside\s?lamp", "LAMP"),
    (r"\bceiling\s?light|\bwall\s?light|\bpendant|\bchandelier|\bsconce", "LIGHT_FIXTURE"),
    (r"\bbulb|\bled\s?light|\blighting|\blamp\b", "HOME_LIGHTING_AND_LAMPS"),
    (r"\bsecurity\s?camera|\bcctv|\bsurveillance|\bdoorbell\s?cam", "SECURITY_CAMERA"),
    (r"\bknife|\bknives|\bcleaver|\bchef'?s?\s?knife", "KITCHEN_KNIFE"),
    (r"\bcookware|\bpan\s?set|\bpot\s?set|\bsaucepan", "COOKWARE_SET"),
    (r"\bspatula|\bturner\b", "FOOD_SPATULA"),
    (r"\bglobe\b", "GLOBE"),
    (r"\bserum|\bcleanser|\bmoisturi|\bsunscreen|\bskincare|\bskin\s?care|\bcosmetic|\bface\s?cream", "BEAUTY"),
    (r"\bsupplement|\bvitamin|\bnebuli|\binhaler|\bthermometer|\bblood\s?pressure", "HEALTH_PERSONAL_CARE"),
    (r"\bhelmet|\bknee\s?pad|\belbow\s?pad|\bprotective\s?gear|\bguard\b", "POWERSPORTS_PROTECTIVE_GEAR"),
    (r"\bnet\b|\bgoal\s?net|\bsports\s?net", "SPORT_NET"),
    (r"\btarget\b|\bdart\s?board|\barchery", "SPORT_TARGET"),
    (r"\bdrill|\bwrench|\bscrewdriver|\bplier|\bhand\s?tool|\bpower\s?tool", "TOOLS"),
    (r"\bscrew|\bbolt|\bnut\b|\bbracket|\bhinge|\bfastener|\bhardware", "HARDWARE"),
    (r"\bart\s?(kit|set)|\bcraft\s?(kit|set)|\bpainting\s?set", "ART_CRAFT_KIT"),
    (r"\bfigure\b|\baction\s?figure|\bcollectible|\bfigurine", "TOY_FIGURE"),
    # ADDED FROM THE ROWS THAT HAD NO TYPE AT ALL -- and only where Amazon has
    # actually given this app a schema for the type, which is the evidence that
    # the name is real (CLAUDE.md Rule 4: do not guess what Amazon calls
    # something). The 96 confirmed names are in the schema_cache table.
    #
    # Found by listing the 32 blank listings and reading their titles:
    #
    #   "Miles Lubricants POE Refrigeration Oil"     -> MACHINE_LUBRICANT ✓
    #   "12V 10A AC to DC Adapter 120W Power Supply" -> no confirmed name
    #   "10X Magnifying Glass Desk Light Magnifier"  -> no confirmed name
    #   "1m x1m Artificial Plant Flower Wall Panel"  -> no confirmed name
    #
    # Only the first gets a rule. The others stay blank on purpose: an invented
    # product type is worse than none, because Amazon refuses it at submit and
    # the compliance gate believes it in the meantime. listing/product_type.py
    # raises a warning on what is left, so a blank is visible and fixable
    # instead of silent.
    (r"\blubricant|\bcompressor\s?oil|\brefrigerat\w*\s?oil"
     r"|\bhydraulic\s?oil|\bgear\s?oil|\bgrease\b", "MACHINE_LUBRICANT"),
]


def infer_product_type(comp_data: dict, item_name: str = "",
                       valid_types: dict = None, default: str = "HOME") -> str:
    """Best-effort product type when none came from SP-API or the scrape.
    Matches keywords from the title + item_type_keyword + breadcrumbs against
    known Amazon types. Returns a valid product type, or 'HOME' as a safe
    generic that exists in the schema (never the invalid literal 'PRODUCT').

    `default` IS WHAT COMES BACK WHEN NOTHING MATCHED, and it matters where the
    answer is being STORED rather than used once. "HOME" is the right fallback
    for a submit -- Amazon needs some type and HOME is a real one. It is the
    wrong thing to write onto a row: the compliance gate reads the stored type
    and would take "HOME" as a fact about the product, which for a 12V power
    supply would turn its electrical check OFF. listing/product_type.py passes
    "" so that a guess it did not actually make stays blank."""
    haystack = " ".join(str(x) for x in [
        item_name,
        comp_data.get("title", ""),
        comp_data.get("item_type_keyword", ""),
        " ".join(comp_data.get("browse_nodes", []) or []),
        " ".join(f"{k} {v}" for k, v in (comp_data.get("attributes") or {}).items()),
    ]).lower()

    for pat, ptype in _PT_INFER_RULES:
        if re.search(pat, haystack):
            # only return it if the schema actually knows this type (when we have
            # the valid_values map); otherwise still return it -- SP-API will
            # validate at export and Claude uses it as a strong hint.
            if not valid_types or ptype in valid_types or ptype == "HOME":
                return ptype
            return ptype
    return default


def _product_type_allows(cat_key, rule, product_type):
    """Can this category apply to a product Amazon files under `product_type`?

    True  -- yes, or there is nothing here that says otherwise.
    False -- no: the rules file names this type as one the category cannot
             cover, or names the only types it can and this is not one.

    RETURNS TRUE ON EVERY UNCERTAINTY. No product type, no rule, a type nobody
    has written a rule about: all of them mean "carry on as before". This
    function can only ever turn a flag DOWN, and only when a person has written
    down, in compliance_rules.json, that it does not apply. A compliance check
    that guesses its way to silence is worse than one that is noisy.

    THIS WAS BRIEFLY THE OPPOSITE. REMAINING_FIXES_HANDOFF.md asked for "if no
    product type is cached, skip category-specific compliance checks entirely",
    and it was built that way -- measured: 32 of 303 listings have no product
    type, and skipping withheld 10 electrical (HIGH) and 4 cookware (MEDIUM)
    flags. The owner then settled it the other way:

        "but why are we having products with no product type, the app should be
         able to pull the product type of the items, dont skip compliance checks"

    Which is the right answer to the right question: a missing product type is a
    gap to FILL, not a reason to stop checking. See listing/product_type.py,
    which fills it in.
    """
    pt = str(product_type or "").strip().upper()
    if not pt:
        return True
    never = [str(x).upper() for x in (rule.get("product_type_never") or []) if x]
    if any(n and n in pt for n in never):
        return False
    only = [str(x).upper() for x in (rule.get("product_type_only") or []) if x]
    if only:
        return any(o and o in pt for o in only)
    return True


PRODUCT_ROUTES = [
    (["cookware", "saucepan", "pots and pans", "frying pan", "casserole", "pan set"],
     "FILE1", "COOKWARE_SET", "11715891"),
    (["floor lamp", "standing lamp", "corner lamp", "rgb led lamp", "mood lamp"],
     "FILE1", "LAMP", "10709381"),
    (["light bar", "rgb light", "led bar", "tv backlight", "gaming light", "backlights"],
     "FILE1", "LAMP", "3764800031"),
    (["solar light", "security light", "outdoor light", "motion sensor"],
     "FILE1", "LAMP", "13679891"),
    (["shelf bracket", "floating shelf", "wall bracket", "mount bracket"],
     "FILE1", "HARDWARE", "1938668031"),
    (["changeover switch", "rotary cam", "cam switch", "electrical switch",
      "bearing puller", "gear puller", "extractor"],
     "FILE1", "HARDWARE", "1938353031"),
    (["golf", "chipping net", "practice net", "swing trainer"],
     "FILE1", "SPORT_TARGET", "26971320031"),
    (["teeth whitening", "whitening powder", "whitening strips"],
     "FILE2", "HEALTH_PERSONAL_CARE", "74136031"),
    (["night cream", "day cream", "face cream", "skin care", "moisturi", "collagen",
      "sleeping mask", "serum"],
     "FILE2", "BEAUTY", "18918424031"),
    (["body lotion", "body cream", "glutathione", "whitening lotion"],
     "FILE2", "BEAUTY", "344269031"),
    (["hair fibre", "hair fiber", "hair loss", "hair growth", "elixir"],
     "FILE2", "HEALTH_PERSONAL_CARE", "2867979031"),
    (["shampoo", "conditioner", "curl cream", "hair spray", "scalp scrub"],
     "FILE2", "HEALTH_PERSONAL_CARE", "18918425031"),
    (["hair dryer", "blow dryer"],
     "FILE2", "HEALTH_PERSONAL_CARE", "2868092031"),
    (["straightener", "hair straighten", "heated brush", "curling iron", "curler"],
     "FILE2", "HEALTH_PERSONAL_CARE", "74099031"),
    (["body spray", "perfume", "fragrance", "body mist"],
     "FILE2", "BEAUTY", "2790134031"),
    (["garlic press", "mandoline", "slicer", "chopper", "kitchen tool", "kitchen gadget"],
     "FILE2", "KITCHEN", "3187111031"),
    (["blender", "juicer", "food processor", "deep fryer", "air fryer"],
     "FILE2", "KITCHEN", "3538310031"),
    (["mop", "bucket set", "shelving unit", "shelf unit", "storage rack", "clothes rail"],
     "FILE2", "HOME", "3579745031"),
    (["extension lead", "power strip", "plug socket"],
     "FILE2", "HOME", "3538310031"),
    (["security camera", "cctv", "indoor camera", "surveillance"],
     "FILE2", "HOME", "3538310031"),
    (["massager", "shiatsu", "back massager"],
     "FILE2", "HEALTH_PERSONAL_CARE", "3360475031"),
]


# Product types THIS unified template accepts (from its Valid Values tab).
TEMPLATE_PRODUCT_TYPES = {
    "KITCHEN", "CORRECTIVE_EYEGLASSES", "GLOBE", "COOKWARE_SET", "AUTO_BATTERY",
    "CAR_ELECTRONICS", "FOOD_SPATULA", "HEALTH_PERSONAL_CARE", "KITCHEN_KNIFE",
    "HANDBAG", "AUTO_ACCESSORY", "HARDWARE", "SPORT_TARGET", "BEAUTY",
    "SUNGLASSES", "SECURITY_CAMERA", "LAMP", "SNOW_GLOBE", "HOME",
}


# Best-effort browse node when the sheet's type is trusted (blank is acceptable;
# recommended_browse_nodes is not a required field).
PT_DEFAULT_NODE = {
    "COOKWARE_SET": "11715891", "LAMP": "10709381", "HARDWARE": "1938668031",
    "SPORT_TARGET": "26971320031", "HEALTH_PERSONAL_CARE": "66280031",
    "BEAUTY": "18918424031", "KITCHEN": "3187111031", "HOME": "3579745031",
}


def _norm_pt(s: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "", str(s).strip().upper().replace(" ", "_"))


# When a product's exact type isn't in this template, map it to the NEAREST
# available type. Order matters (first match wins); HOME is the final catch-all.
# Matching is whole-word on alphanumeric-tokenised text, so 'chair' never hits
# 'hair' and 'lightweight' never hits 'light'.
_PT_FALLBACK_RULES = [
    (["snow globe"], "SNOW_GLOBE"),
    (["globe", "atlas"], "GLOBE"),
    (["sunglasses", "sunglass"], "SUNGLASSES"),
    (["eyeglasses", "spectacles", "reading glasses", "prescription glasses", "optical frame"], "CORRECTIVE_EYEGLASSES"),
    (["cctv", "security camera", "surveillance camera", "ip camera", "webcam", "doorbell camera", "dash cam", "dashcam"], "SECURITY_CAMERA"),
    (["lamp", "lamps", "bulb", "bulbs", "chandelier", "sconce", "lantern", "lighting",
      "downlight", "spotlight", "floodlight", "light fixture", "ceiling light", "wall light",
      "pendant light", "led light", "string light", "night light", "desk light",
      "wall lamp", "desk lamp", "floor lamp", "table lamp"], "LAMP"),
    (["knife", "cleaver", "kitchen knife", "chef knife", "paring knife"], "KITCHEN_KNIFE"),
    (["spatula", "turner", "ladle"], "FOOD_SPATULA"),
    (["cookware", "saucepan", "frying pan", "casserole", "wok", "stockpot", "pots and pans"], "COOKWARE_SET"),
    (["blender", "juicer", "mixer", "peeler", "grater", "slicer", "chopper", "food processor", "air fryer", "kettle", "toaster", "whisk", "utensil", "kitchen gadget", "kitchen tool"], "KITCHEN"),
    (["handbag", "purse", "tote", "backpack", "satchel", "clutch", "shoulder bag", "crossbody"], "HANDBAG"),
    (["car battery", "vehicle battery", "leisure battery"], "AUTO_BATTERY"),
    (["car stereo", "head unit", "car audio", "car speaker"], "CAR_ELECTRONICS"),
    (["car", "automotive", "vehicle", "number plate", "seat cover", "floor mat", "wing mirror", "wiper"], "AUTO_ACCESSORY"),
    (["serum", "moisturiser", "moisturizer", "face cream", "body cream", "night cream", "lotion", "cosmetic", "skincare", "makeup", "fragrance", "perfume", "mascara", "lipstick", "face mask"], "BEAUTY"),
    (["massager", "supplement", "trimmer", "shaver", "toothbrush", "grooming", "scalp", "manicure"], "HEALTH_PERSONAL_CARE"),
    (["dartboard", "archery", "practice net", "chipping net", "golf net", "shooting target", "target board"], "SPORT_TARGET"),
    (["tool", "tools", "bracket", "fixing", "screw", "drill", "wrench", "hardware", "mount", "hinge", "hook", "fastener", "clamp"], "HARDWARE"),
]


def _fallback_pt(text: str) -> str:
    """Map an unsupported product to the NEAREST available template type.
    Returns 'HOME' (the generic catch-all) when nothing more specific fits."""
    t = " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "
    for keywords, pt in _PT_FALLBACK_RULES:
        if any(f" {kw} " in t for kw in keywords):
            return pt
    return "HOME"


def detect_route(title: str, category: str, product_type: str) -> tuple:
    """
    Return (file_id, product_type, browse_node).
      1) Trust the sheet's Product Type when this template accepts it.
      2) Else keyword-route with LEFT word-boundary matching, so 'chair' can no
         longer match 'hair'.
      3) Else return ('', '', '') -- a SKIP signal; the caller skips and flags the
         row instead of forcing it into HOME.
    """
    text     = f"{title} {category} {product_type}".lower()
    pt_sheet = _norm_pt(product_type)

    # 1) Trust the explicit sheet value if the template supports it.
    if pt_sheet in TEMPLATE_PRODUCT_TYPES:
        node = PT_DEFAULT_NODE.get(pt_sheet, "")
        for keywords, file_id, pt, browse_node in PRODUCT_ROUTES:
            if pt == pt_sheet and any(re.search(r"\b" + re.escape(kw), text) for kw in keywords):
                node = browse_node
                break
        fid = "FILE1" if pt_sheet in {"COOKWARE_SET", "LAMP", "HARDWARE", "SPORT_TARGET"} else "FILE2"
        return fid, pt_sheet, node

    # 2) Keyword routing with left word-boundary matching.
    for keywords, file_id, pt, browse_node in PRODUCT_ROUTES:
        if any(re.search(r"\b" + re.escape(kw), text) for kw in keywords):
            if pt in TEMPLATE_PRODUCT_TYPES:
                return file_id, pt, browse_node

    # 3) Unsupported type -> map to the NEAREST available type (never skip).
    fb  = _fallback_pt(text)
    fid = "FILE1" if fb in {"COOKWARE_SET", "LAMP", "HARDWARE", "SPORT_TARGET"} else "FILE2"
    return fid, fb, PT_DEFAULT_NODE.get(fb, "")
