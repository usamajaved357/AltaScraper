"""Making a variation family, and every reason to refuse before sending one.

Amazon accepts a half-formed family without complaint and the products simply
stop appearing in search. There is no error to react to, so every check has to
happen BEFORE anything is sent -- which is what this file is mostly about.
"""
import sys
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

def truthy(l, g):
    check(l, bool(g), True)

from listing import variations as V

# The real shape, copied from what Amazon returned for SPACE_HEATER on the live
# UK account (14 Aug 2026): themes are slash-separated attribute names, and the
# node carries a $lifecycle.enumDeprecated list of ones no longer accepted.
SCHEMA = {"properties": {"variation_theme": {
    "type": "array",
    "items": {"properties": {"name": {
        "enum": ["SIZE", "COLOR", "SIZE/COLOR", "COLOR/VOLTAGE/WATTAGE",
                 "SIZE_NAME", "COLOR_NAME/SIZE_NAME"],
        "$lifecycle": {"enumDeprecated": ["SIZE_NAME", "COLOR_NAME/SIZE_NAME"]},
    }}},
}}}
NO_VAR_SCHEMA = {"properties": {"item_name": {"type": "array"}}}

# THE PARENT'S OWN SCHEMA, as Amazon returns it for parentageLevel=PARENT.
# Shaped from the real answer measured on the live UK account (SQUEEGEE,
# 2 Sep 2026): the identifier attributes are absent entirely, and `required`
# carries two the standalone schema never mentions.
# `required` is kept to what these fixtures' children can actually satisfy --
# the point being asserted is the TWO the parent schema adds and the standalone
# one never mentions, not the borrowing, which has its own tests below.
PARENT_SCHEMA = {
    "properties": {"variation_theme": SCHEMA["properties"]["variation_theme"]},
    "attribute_names": ["brand", "item_name", "variation_theme",
                        "child_parent_sku_relationship", "parentage_level"],
    "required": ["brand", "variation_theme", "child_parent_sku_relationship"],
}
STANDALONE_SCHEMA = SCHEMA


def _schema_for(pt, mkt, parentage=""):
    """The injected fetcher, now aware of parentage like the real one.

    Two different schemas, because that is the whole point: the theme checker
    must keep seeing the full one (the parent schema has no colour or size to
    check a theme against) and the parent builder must see the parent's.
    """
    if str(parentage or "").upper() == "PARENT":
        return PARENT_SCHEMA
    return STANDALONE_SCHEMA

def kid(sku, **attrs):
    # brand and item_type_keyword are now part of what a family must share, so a
    # fixture without them is a fixture that cannot form one -- which is the
    # point of the rule, and is asserted separately below.
    return {"sku": sku, "product_type": "SHIRT", "brand": "Acme",
            "item_type_keyword": "shirt", "attributes": attrs}

KIDS = [kid("SH-RED-S", size="Small"), kid("SH-RED-M", size="Medium"),
        kid("SH-RED-L", size="Large")]


print("=== the theme comes out of the schema, never out of us ===")
check("themes read from the product type", V.themes_from_schema(SCHEMA),
      ["SIZE", "COLOR", "SIZE/COLOR", "COLOR/VOLTAGE/WATTAGE"])
check("  deprecated themes are NOT offered",
      [t for t in V.themes_from_schema(SCHEMA) if "_NAME" in t], [])
check("a type with no variation_theme supports none",
      V.themes_from_schema(NO_VAR_SCHEMA), [])
check("  and neither does an empty schema", V.themes_from_schema({}), [])
check("SIZE varies on one axis", V.theme_axes("SIZE"), ["size"])
check("SIZE/COLOR varies on TWO, in order", V.theme_axes("SIZE/COLOR"), ["size", "color"])
check("  a three-part theme gives three", V.theme_axes("COLOR/VOLTAGE/WATTAGE"),
      ["color", "voltage", "wattage"])
check("  and a four-part one, verbatim from the live TOOLS schema",
      V.theme_axes("COLOR/SPECIFIC_USES_FOR_PRODUCT/FINISH_TYPE/SIZE"),
      ["color", "specific_uses_for_product", "finish_type", "size"])
check("  the part IS the attribute name, underscores and all",
      V.theme_axes("ITEM_WEIGHT"), ["item_weight"])


print("\n=== a good merge passes ===")
check("no problems", V.check("SH-PARENT", KIDS, "SIZE", SCHEMA, "SHIRT"), [])


print("\n=== and every bad one is refused, with the reason ===")
def why(parent, kids, theme, schema=SCHEMA, pt="SHIRT"):
    return " | ".join(V.check(parent, kids, theme, schema, pt))

truthy("no parent SKU", "needs a parent SKU" in why("", KIDS, "SIZE"))
truthy("only one child", "at least two products" in why("P", KIDS[:1], "SIZE"))
truthy("the parent is also a child",
       "parent is the group" in why("SH-RED-S", KIDS, "SIZE"))
truthy("the same SKU twice",
       "listed twice" in why("P", KIDS + [kid("SH-RED-S", size="Small")], "SIZE"))
truthy("no theme picked", "what makes these products different" in why("P", KIDS, ""))
truthy("a theme this type does not allow",
       "not a variation theme this product type allows" in why("P", KIDS, "FLAVOR"))
truthy("  and it says which ARE allowed", "SIZE, COLOR" in why("P", KIDS, "FLAVOR"))
truthy("a product type that cannot vary at all",
       "does not support variations at all" in why("P", KIDS, "SIZE", NO_VAR_SCHEMA))

print("  -- the ones that would silently produce a broken family --")
same = [kid("A", size="Large"), kid("B", size="Large")]
truthy("two children with the SAME size under a SIZE theme",
       "has the same size" in why("P", same, "SIZE"))
truthy("  and it explains why that is not a family",
       "compete with each other" in why("P", same, "SIZE"))
blank = [kid("A", size="Small"), kid("B")]
truthy("a child with no value on the axis", "no size set" in why("P", blank, "SIZE"))
truthy("  naming which one", "B has no size" in why("P", blank, "SIZE"))
mixed = [dict(kid("A", size="S"), product_type="SHIRT"),
         dict(kid("B", size="M"), product_type="SHOES")]
truthy("children of different product types",
       "different product type values" in why("P", mixed, "SIZE", SCHEMA, ""))

print("  -- a two-axis theme checks BOTH axes --")
two = [kid("A", size="S", color="Red"), kid("B", size="S", color="Blue")]
check("same size, different colour is a valid SIZE_COLOR family",
      V.check("P", two, "SIZE/COLOR", SCHEMA, "SHIRT"), [])
same_both = [kid("A", size="S", color="Red"), kid("B", size="S", color="Red")]
truthy("identical on both axes is refused",
       V.check("P", same_both, "SIZE/COLOR", SCHEMA, "SHIRT"))


print("\n=== the preview IS the payload ===")
b = V.build("SH-PARENT", KIDS, "SIZE", "SHIRT")
p = b["parent"]
check("the parent is marked as one",
      p["attributes"]["parentage_level"], [{"value": "parent"}])
check("  carries the theme", p["attributes"]["variation_theme"], [{"name": "SIZE"}])
check("  and is NOT buyable: no price", "purchasable_offer" in p["attributes"], False)
check("  and no stock", "fulfillment_availability" in p["attributes"], False)

check("every child is marked as one", len(b["children"]), 3)
c0 = b["children"][0]
check("  parentage", c0["attributes"]["parentage_level"], [{"value": "child"}])
check("  the same theme as the parent",
      c0["attributes"]["variation_theme"], [{"name": "SIZE"}])
check("  and it names its parent",
      c0["attributes"]["child_parent_sku_relationship"],
      [{"child_relationship_type": "variation", "parent_sku": "SH-PARENT"}])
check("all three point at the same parent",
      {x["attributes"]["child_parent_sku_relationship"][0]["parent_sku"]
       for x in b["children"]}, {"SH-PARENT"})
check("no child carries a price either",
      any("purchasable_offer" in x["attributes"] for x in b["children"]), False)
check("the axes travel with it", b["axes"], ["size"])


print("\n=== the suggested parent SKU is only a suggestion ===")
check("built from what the children share",
      V.suggest_parent_sku(KIDS), "SH-RED-PARENT")
check("  it does not stop mid-token",
      V.suggest_parent_sku([kid("ABC-1"), kid("ABC-2")]), "ABC-PARENT")
check("nothing in common falls back to the first",
      V.suggest_parent_sku([kid("XX"), kid("ZZZZ")]), "XX-PARENT")
check("no children, no suggestion", V.suggest_parent_sku([]), "")

print("\n=== the endpoints: preview decides, apply sends ===")
import os, json, tempfile, shutil
from flask import Flask
import routes.variations_routes as vr

TMP = tempfile.mkdtemp(prefix="altavar_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "jack_uk", "seller_id": "S1"}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "v.db")

from domain import live_snapshots as LS
WS, MKT = "jack_uk", "UK"
LS.save(CFG, WS, MKT, [
    {"sku": "SH-RED-S", "asin": "B01", "title": "Shirt Small", "product_type": "SHIRT",
     "attributes": {"size": "Small"}},
    {"sku": "SH-RED-M", "asin": "B02", "title": "Shirt Medium", "product_type": "SHIRT",
     "attributes": {"size": "Medium"}},
    {"sku": "SH-DUP",   "asin": "B03", "title": "Shirt Medium too", "product_type": "SHIRT",
     "attributes": {"size": "Medium"}},
    {"sku": "SH-TAKEN", "asin": "B04", "title": "Already grouped", "product_type": "SHIRT",
     "attributes": {"size": "Large"}, "parent_sku": "OTHER-PARENT"},
], report_source="test")

# Preview now reads each SKU from AMAZON rather than from the snapshot, because
# the constraints are about what Amazon holds right now -- merging on a stale
# brand produces a family Amazon accepts and then does not show. So the client is
# stubbed with what Amazon would return, including one SKU it refuses.
from api import amazon_listings as _AL
_LIVE = {
    "SH-RED-S": {"brand": "Acme", "item_type_keyword": "shirt", "size": "Small"},
    "SH-RED-M": {"brand": "Acme", "item_type_keyword": "shirt", "size": "Medium"},
    "SH-DUP":   {"brand": "Acme", "item_type_keyword": "shirt", "size": "Medium"},
    "SH-TAKEN": {"brand": "Acme", "item_type_keyword": "shirt", "size": "Large",
                 "child_parent_sku_relationship": "OTHER-PARENT"},
    "SH-OTHERBRAND": {"brand": "Rival", "item_type_keyword": "shirt", "size": "XL"},
}
def _fake_get_item(creds, mkt, seller, sku, mkt_id, included=None, timeout=60):
    d = _LIVE.get(sku)
    if d is None:
        return {"status": _AL.FAILED, "attributes": None, "product_type": "",
                "error": "not found", "http_code": 404, "raw": None}
    attrs = {k: [{"value": v}] for k, v in d.items()}
    return {"status": _AL.OK, "attributes": attrs, "product_type": "SHIRT",
            "error": "", "http_code": None, "raw": {}}
_AL.get_item = _fake_get_item

app = Flask(__name__); app.secret_key = "t"
vr.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
            _active_account=lambda: {"id": WS, "seller_id": "S1"},
            _state={"active_account_id": WS, "active_marketplace": MKT},
            _sp_creds=lambda m="UK": {},
            _schema_for=_schema_for)
cl = app.test_client()

cand = cl.get("/variations/candidates").get_json()
check("candidates come from the cached catalogue", cand["count"], 4)
check("  and say which are already in a family",
      [i["sku"] for i in cand["items"] if i["parent_sku"]], ["SH-TAKEN"])
check("filtering works", cl.get("/variations/candidates?q=red").get_json()["count"], 2)

th = cl.get("/variations/themes?product_type=SHIRT").get_json()
check("themes come from the schema", th["themes"],
      ["SIZE", "COLOR", "SIZE/COLOR", "COLOR/VOLTAGE/WATTAGE"])
check("  and it says the check really ran", th["checked"], True)

def prev(skus, theme, parent=""):
    return cl.post("/variations/preview",
                   json={"skus": skus, "theme": theme, "parent_sku": parent}).get_json()

p = prev(["SH-RED-S", "SH-RED-M"], "SIZE")
check("a good merge can apply", p["can_apply"], True)
check("  with no problems", p["problems"], [])
check("  and suggests a parent SKU", p["parent_sku"], "SH-RED-PARENT")
check("  the preview carries the real payload",
      p["payload"]["parent"]["attributes"]["variation_theme"], [{"name": "SIZE"}])
check("  which the parent has no price in",
      "purchasable_offer" in p["payload"]["parent"]["attributes"], False)

print("  -- the parent is built against the PARENT schema --")
# Amazon's parentageLevel=PARENT resolves the schema down to what a variation
# container is. MEASURED on the live UK account (SQUEEGEE, 2 Sep 2026): the
# standalone schema requires 6 attributes and carries 112 properties; the parent
# schema requires 8 and carries 83, and the three identifier attributes are
# ABSENT from it -- not required, not optional, not named in any of the
# conditionals they appear in on the standalone one.
_pattrs = p["payload"]["parent"]["attributes"]
check("the parent is built from the parent's own schema",
      p["parent_schema"], "parent")
truthy("  which asks for what the standalone schema never mentioned",
       "child_parent_sku_relationship" in p["parent_required"]
       and "variation_theme" in p["parent_required"])

# THE EXEMPTION IS GONE, and not because a rule says so -- because the field
# does not exist at this parentage level. Amazon has no product identifier on a
# parent, so there is nothing to exempt and nothing to declare.
check("no GTIN exemption is claimed on the parent",
      "supplier_declared_has_product_identifier_exemption" in _pattrs, False)
check("  and no identifier is sent either",
      "externally_assigned_product_identifier" in _pattrs, False)
check("  and never merchant_suggested_asin (Rule 1)",
      "merchant_suggested_asin" in _pattrs, False)

# WHAT THE PARENT SCHEMA DOES DEMAND, in ITS shape rather than the child's:
# items.required is ["child_relationship_type"], the enum is ["variation"], and
# additionalProperties is false -- there is no parent_sku property on a parent.
_rel = _pattrs.get("child_parent_sku_relationship")
truthy("the relationship the parent schema requires is sent", _rel)
check("  as one entry", len(_rel or []), 1)
check("  saying only what kind of relationship it heads",
      (_rel or [{}])[0].get("child_relationship_type"), "variation")
check("  and NOT naming a parent SKU, which the parent's schema has no room for",
      "parent_sku" in (_rel or [{}])[0], False)
# The child's version is the other way round and must not have changed.
_kid0 = p["payload"]["children"][0]["attributes"]["child_parent_sku_relationship"][0]
check("a CHILD still names its parent", _kid0.get("parent_sku"), "SH-RED-PARENT")

# THE THEME CHECKER MUST NOT READ THE PARENT SCHEMA. It drops colour, size and
# every other varying attribute -- 29 of SQUEEGEE's 112 -- so asked of it, every
# theme on every product type names an axis the type "does not have".
check("themes still come from the full schema, not the parent's",
      prev(["SH-RED-S", "SH-RED-M"], "SIZE")["can_apply"], True)
_th = cl.get("/variations/themes?product_type=SHIRT").get_json()
check("  and the theme list is unchanged by any of this", _th["themes"],
      ["SIZE", "COLOR", "SIZE/COLOR", "COLOR/VOLTAGE/WATTAGE"])

# A FETCHER THAT CANNOT ANSWER FOR THE PARENT SAYS SO. Falling back to the
# standalone list is defensible; pretending it was the parent's is not.
import flask as _flask_mod
_app2 = _flask_mod.Flask(__name__); _app2.secret_key = "t"
vr.register(_app2, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
            _active_account=lambda: {"id": WS, "seller_id": "S1"},
            _state={"active_account_id": WS, "active_marketplace": MKT},
            _sp_creds=lambda m="UK": {},
            _schema_for=lambda pt, mkt: SCHEMA)      # the old two-argument shape
_old = _app2.test_client().post(
    "/variations/preview",
    json={"skus": ["SH-RED-S", "SH-RED-M"], "theme": "SIZE"}).get_json()
truthy("an older fetcher falls back and the preview says which schema it used",
       _old["parent_schema"].startswith("standalone"))
check("  and still claims no exemption",
      "supplier_declared_has_product_identifier_exemption"
      in _old["payload"]["parent"]["attributes"], False)

bad = prev(["SH-RED-M", "SH-DUP"], "SIZE")
check("two products of the same size cannot apply", bad["can_apply"], False)
truthy("  and it says why", any("same size" in x for x in bad["problems"]))

taken = prev(["SH-RED-S", "SH-TAKEN"], "SIZE")
check("a product already in a family cannot apply", taken["can_apply"], False)
truthy("  naming it", any("SH-TAKEN" in x for x in taken["problems"]))

print("  -- what a family must SHARE, checked against Amazon's live answer --")
LS.save(CFG, WS, MKT, [
    {"sku": "SH-RED-S", "asin": "B01", "title": "Shirt Small", "product_type": "SHIRT"},
    {"sku": "SH-RED-M", "asin": "B02", "title": "Shirt Medium", "product_type": "SHIRT"},
    {"sku": "SH-DUP", "asin": "B03", "title": "Dup", "product_type": "SHIRT"},
    {"sku": "SH-TAKEN", "asin": "B04", "title": "Taken", "product_type": "SHIRT"},
    {"sku": "SH-OTHERBRAND", "asin": "B05", "title": "Other brand", "product_type": "SHIRT"},
], report_source="test")
brand = prev(["SH-RED-S", "SH-OTHERBRAND"], "SIZE")
check("a different BRAND cannot join the family", brand["can_apply"], False)
truthy("  naming both brands", any("ACME" in x and "RIVAL" in x
                                   for x in brand["problems"]))
truthy("  and saying why it matters",
       any("same brand" in x for x in brand["problems"]))

_LIVE["SH-NOKW"] = {"brand": "Acme", "size": "XS"}      # no item_type_keyword
LS.save(CFG, WS, MKT, [
    {"sku": "SH-RED-S", "asin": "B01", "title": "S", "product_type": "SHIRT"},
    {"sku": "SH-NOKW", "asin": "B06", "title": "No keyword", "product_type": "SHIRT"},
], report_source="test")
nokw = prev(["SH-RED-S", "SH-NOKW"], "SIZE")
check("an unreadable item type keyword is not treated as a match",
      nokw["can_apply"], False)
truthy("  it says it could not be CONFIRMED, not that it differs",
       any("cannot be confirmed" in x for x in nokw["problems"]))

# THE CASE THAT MADE STEP 3 UNREACHABLE. Above, one child has the keyword and
# one does not, which is a real mismatch and rightly stops. Here NEITHER has it,
# because the product type does not use it -- measured on a live UK SQUEEGEE
# listing, where Amazon returns 45 attributes and item_type_keyword is not among
# them. Demanding a field Amazon does not send is a refusal with nothing on the
# screen that could clear it, and it fired on every pair on the account.
_LIVE["SH-NOKW2"] = {"brand": "Acme", "size": "S"}
_LIVE["SH-NOKW3"] = {"brand": "Acme", "size": "M"}
LS.save(CFG, WS, MKT, [
    {"sku": "SH-NOKW2", "asin": "B08", "title": "No keyword S", "product_type": "SHIRT"},
    {"sku": "SH-NOKW3", "asin": "B09", "title": "No keyword M", "product_type": "SHIRT"},
], report_source="test")
none_kw = prev(["SH-NOKW2", "SH-NOKW3"], "SIZE")
check("a field the product type does not use at all does not block",
      none_kw["can_apply"], True)
check("  and it is not reported as a problem either",
      [p for p in none_kw["problems"] if "item type keyword" in p], [])
# Brand keeps the strict rule: Amazon DOES return it, so silence there would be
# a family merged on something never checked.
_LIVE["SH-NOBRAND"] = {"size": "L"}
LS.save(CFG, WS, MKT, [
    {"sku": "SH-NOKW2", "asin": "B08", "title": "No keyword S", "product_type": "SHIRT"},
    {"sku": "SH-NOBRAND", "asin": "B10", "title": "No brand", "product_type": "SHIRT"},
], report_source="test")
nobrand = prev(["SH-NOKW2", "SH-NOBRAND"], "SIZE")
check("an unreadable BRAND still blocks", nobrand["can_apply"], False)

# THE OTHER HALF OF THE SAME BUG, checked in the source because it is about what
# is asked of Amazon rather than what is done with the answer. get_item reads the
# product type from summaries and falls back to productTypes -- but productTypes
# was not in the request, so the fallback could never fire. Measured live:
# summaries came back EMPTY and productTypes held "SQUEEGEE", so product_type was
# "" for every real listing and every merge failed on it.
_AL_SRC = open("api/amazon_listings.py", encoding="utf-8").read()
truthy("get_item asks Amazon for productTypes, or its fallback cannot fire",
       'included=("attributes", "summaries", "issues", "productTypes")' in _AL_SRC)
truthy("  and still reads the fallback", 'data.get("productTypes")' in _AL_SRC)

LS.save(CFG, WS, MKT, [
    {"sku": "SH-RED-S", "asin": "B01", "title": "S", "product_type": "SHIRT"},
    {"sku": "SH-RED-M", "asin": "B02", "title": "M", "product_type": "SHIRT"},
    {"sku": "SH-GHOST", "asin": "B07", "title": "Ghost", "product_type": "SHIRT"},
], report_source="test")
ghost = prev(["SH-RED-S", "SH-GHOST"], "SIZE")
check("a SKU Amazon will not return blocks the merge", ghost["can_apply"], False)
truthy("  rather than being merged on data we could not read",
       any("could not read" in x for x in ghost["problems"]))

LS.save(CFG, WS, MKT, [
    {"sku": "SH-RED-S", "asin": "B01", "title": "Shirt Small", "product_type": "SHIRT"},
    {"sku": "SH-RED-M", "asin": "B02", "title": "Shirt Medium", "product_type": "SHIRT"},
    {"sku": "SH-DUP", "asin": "B03", "title": "Dup", "product_type": "SHIRT"},
    {"sku": "SH-TAKEN", "asin": "B04", "title": "Taken", "product_type": "SHIRT"},
], report_source="test")

gone = prev(["SH-RED-S", "NOT-A-SKU"], "SIZE")
check("a SKU that is not in the catalogue cannot apply", gone["can_apply"], False)
truthy("  and says to sync", any("Press Sync" in x for x in gone["problems"]))

check("apply refuses without confirmation",
      cl.post("/variations/apply", json={"skus": ["SH-RED-S", "SH-RED-M"],
                                         "theme": "SIZE"}).status_code, 400)
r = cl.post("/variations/apply", json={"confirmed": True, "theme": "SIZE",
                                       "parent_sku": "P", "skus": ["SH-RED-M", "SH-DUP"]})
check("apply re-checks rather than trusting the browser", r.status_code, 400)
truthy("  with the same reason the preview gave", "same size" in r.get_json()["error"])

print("\n=== permissions ===")
from auth import guard as G
check("looking sends nothing, so it is open",
      G.required_permission("/variations/preview", "POST"), None)
check("  and so is the candidate list",
      G.required_permission("/variations/candidates", "GET"), None)
check("but applying is publishing",
      G.required_permission("/variations/apply", "POST"), "publish")
# CHANGED DELIBERATELY. Variations is its own page feature now, so it can be
# turned off for one person without taking the whole Listings area with it.
# It still INHERITS listings until somebody sets it, so what anyone can see
# today is unchanged -- which is the property test_page_permissions.py asserts.
check("the screen is its own page", G.feature_for("/variations/preview"), "variations")
from auth import users as U
check("  which falls back to listings until it is set",
      U.FEATURE_PARENT.get("variations"), "listings")
_lister = {"active": True, "role": "lister", "features": {}}
check("  so a lister still sees it exactly as before",
      U.feature_level(_lister, "variations"), U.feature_level(_lister, "listings"))

os.environ.pop("ALTASCRAPER_DB", None)
shutil.rmtree(TMP, ignore_errors=True)

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
