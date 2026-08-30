"""A value read off Amazon must go back to the field it came from.

WHAT THIS PINS

listing/live_attributes.flatten() turns Amazon's getListingsItem attributes into
the flat dot-key map the app stores. amazon_listing_generator._renest() folds
that map back into the object tree Amazon wants at submit time. They are
inverses, and nothing enforces that except this file.

If they drift, the failure is silent in the worst way: the drawer shows
"180 grams" read off the live listing, someone accepts it, and the submit puts
180 somewhere else -- or drops the unit and sends a bare number. No exception, no
red text, and the first sign of it is Amazon rejecting a listing for a field
nobody touched.

WHY IT LOADS _renest INSTEAD OF RE-STATING IT

_renest is a closure inside build_api_attributes, which CLAUDE.md keeps in the
engine until Phase 6, so it cannot be imported. Copying its 40 lines into this
test would produce a test that passes forever while production drifts away from
it -- the copy would be what was tested. So the real function is lifted out of
the source by AST and executed as itself. It has no free variables (verified
below, so this stops being true loudly rather than quietly), which is what makes
that safe.

The round trip is deliberately NOT flatten(renest(x)) == x for arbitrary x.
Amazon's own shape carries an array-of-one wrapper and marketplace_id bookkeeping
that _renest never produces and never consumes -- that layer is applied further
down, by the normal attribute handling. The property that must hold is:

    flatten(amazon_shape)  ->  dot_keys
    _renest(dot_keys)      ->  the SAME tree, minus the wrapper

which is what is checked here, field by field, on shapes taken from real
listings.
"""
import ast
import sys

sys.path.insert(0, r"D:\AltaScraper")

from listing import live_attributes as LA        # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL\n      got  %r\n      want %r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


# ---------------------------------------------------------------------------
# Lift the REAL _renest out of the generator.
# ---------------------------------------------------------------------------
SRC = open(r"D:\AltaScraper\amazon_listing_generator.py", encoding="utf-8").read()
_tree = ast.parse(SRC)
_fn = None
for _node in ast.walk(_tree):
    if isinstance(_node, ast.FunctionDef) and _node.name == "_renest":
        _fn = _node
        break

print("\nloading the real _renest out of amazon_listing_generator.py")
truthy("_renest was found in the generator", _fn is not None)
if _fn is None:
    print("\n1 failed\n  FAILED: _renest has moved -- update this test to follow it")
    sys.exit(1)

# It must not close over anything, or executing it standalone would not be the
# same function. Names it may legitimately use: its own locals plus builtins.
_assigned = set()
for _n in ast.walk(_fn):
    if isinstance(_n, ast.Name) and isinstance(_n.ctx, ast.Store):
        _assigned.add(_n.id)
    elif isinstance(_n, ast.arg):
        # its own parameter, and any lambda's -- _renest sorts with
        # `key=lambda s: s.count(".")`, and `s` is bound, not free.
        _assigned.add(_n.arg)
_used = {n.id for n in ast.walk(_fn)
         if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
_free = sorted(_used - _assigned - set(dir(__builtins__)) - set(vars(__import__("builtins"))))
check("it closes over nothing, so running it here runs the real thing", _free, [])

_ns = {}
exec(compile(ast.Module(body=[_fn], type_ignores=[]), "<renest>", "exec"), _ns)
renest = _ns["_renest"]


def roundtrip(label, amazon_shape, want_flat, want_tree):
    """flatten -> dot keys -> _renest -> tree, checked at both ends."""
    got = LA.flatten({"k": amazon_shape})
    flat = got["values"]
    check(label + ": flattens to the app's dot-keys", flat, want_flat)
    check(label + ": _renest folds it back", renest(dict(flat)), want_tree)


# ---------------------------------------------------------------------------
print("\nthe collapse rule -- when a `value` key IS the attribute")
# ---------------------------------------------------------------------------
# dashboard._extract_subfields returns [] when the only non-plumbing key is
# "value", i.e. a plain scalar attribute. flatten must agree, or the drawer
# shows the same field twice.
roundtrip("brand (value + plumbing)",
          [{"value": "Selvora", "marketplace_id": "A1F83G8C2ARO7P"}],
          {"k": "Selvora"},
          {"k": "Selvora"})

roundtrip("a language-tagged single value",
          [{"value": "Wall Mounted Can Crusher", "language_tag": "en_GB",
            "marketplace_id": "A1F83G8C2ARO7P"}],
          {"k": "Wall Mounted Can Crusher"},
          {"k": "Wall Mounted Can Crusher"})

roundtrip("an image locator (media_location, not value)",
          [{"media_location": "https://m.media-amazon.com/images/I/61qid.jpg",
            "marketplace_id": "A1F83G8C2ARO7P"}],
          {"k": "https://m.media-amazon.com/images/I/61qid.jpg"},
          {"k": "https://m.media-amazon.com/images/I/61qid.jpg"})

# ---------------------------------------------------------------------------
print("\nvalue + unit -- two keys, so it must NOT collapse")
# ---------------------------------------------------------------------------
roundtrip("item_weight",
          [{"value": 180, "unit": "grams", "marketplace_id": "A1F83G8C2ARO7P"}],
          {"k.unit": "grams", "k.value": "180"},
          {"k": {"unit": "grams", "value": "180"}})

roundtrip("a genuine decimal keeps its digits",
          [{"value": 12.75, "unit": "centimeters"}],
          {"k.unit": "centimeters", "k.value": "12.75"},
          {"k": {"unit": "centimeters", "value": "12.75"}})

# ---------------------------------------------------------------------------
print("\ntwo levels deep -- the leg/cable shape that caused the original bug")
# ---------------------------------------------------------------------------
roundtrip("battery.weight.{value,unit} + a collapsing sibling",
          [{"weight": {"value": 180, "unit": "grams"},
            "cell_composition": [{"value": "lithium_ion"}],
            "marketplace_id": "A1F83G8C2ARO7P"}],
          {"k.cell_composition": "lithium_ion",
           "k.weight.unit": "grams",
           "k.weight.value": "180"},
          {"k": {"cell_composition": "lithium_ion",
                 "weight": {"unit": "grams", "value": "180"}}})

roundtrip("item_dimensions, three axes of value+unit",
          [{"length": {"value": 20.0, "unit": "centimeters"},
            "width": {"value": 10.0, "unit": "centimeters"},
            "marketplace_id": "A1F83G8C2ARO7P"}],
          {"k.length.unit": "centimeters", "k.length.value": "20",
           "k.width.unit": "centimeters", "k.width.value": "10"},
          {"k": {"length": {"unit": "centimeters", "value": "20"},
                 "width": {"unit": "centimeters", "value": "10"}}})

# ---------------------------------------------------------------------------
print("\nscalars the app has to be able to send back")
# ---------------------------------------------------------------------------
check("a JSON true becomes \"true\", not Python's \"True\"",
      LA.flatten({"exempt": [{"value": True}]})["values"], {"exempt": "true"})
check("and false is not mistaken for empty",
      LA.flatten({"exempt": [{"value": False}]})["values"], {"exempt": "false"})
check("180.0 loses the .0 nobody would type",
      LA.flatten({"n": [{"value": 180.0}]})["values"], {"n": "180"})
check("an integer stays an integer",
      LA.flatten({"n": [{"value": 7}]})["values"], {"n": "7"})
check("a null is absent, not the word None",
      LA.flatten({"n": [{"value": None}]})["values"], {})
check("an empty array yields nothing",
      LA.flatten({"n": []})["values"], {})
check("plumbing alone yields nothing",
      LA.flatten({"n": [{"marketplace_id": "A1F", "language_tag": "en_GB"}]})["values"], {})

# ---------------------------------------------------------------------------
print("\nmore than one value is REPORTED, never silently truncated")
# ---------------------------------------------------------------------------
_multi = LA.flatten({"special_feature": [{"value": "portable"},
                                         {"value": "rechargeable"},
                                         {"value": "waterproof"}]})
check("the first value is shown", _multi["values"], {"special_feature": "portable"})
check("and the count comes with it, so the cell can be read-only",
      _multi["multi"], {"special_feature": 3})
check("a single value is not flagged as multi",
      LA.flatten({"brand": [{"value": "Selvora"}]})["multi"], {})
check("a multi nested DEEPER still flags its top-level attribute",
      LA.flatten({"battery": [{"cell_composition": [{"value": "a"},
                                                    {"value": "b"}]}]})["multi"],
      {"battery": 2})

# ---------------------------------------------------------------------------
print("\nthe copy is kept apart from the attribute grid")
# ---------------------------------------------------------------------------
_c = LA.flatten({
    "item_name": [{"value": "Expandable Garden Hose", "language_tag": "en_GB"}],
    "bullet_point": [{"value": "one"}, {"value": "two"}, {"value": "three"}],
    "brand": [{"value": "Selvora"}],
})
check("the title does not land in the attribute grid (it has its own box)",
      _c["values"], {"brand": "Selvora"})
check("all five bullets survive, in order",
      _c["content"]["bullet_point"], ["one", "two", "three"])
check("the title is there for the caller that wants it",
      _c["content"]["item_name"], ["Expandable Garden Hose"])
check("bullets are not counted as a multi-value attribute",
      _c["multi"], {})

# ---------------------------------------------------------------------------
print("\nthe offer blocks are declared, not dropped in silence")
# ---------------------------------------------------------------------------
_o = LA.flatten({
    "purchasable_offer": [{"currency": "GBP",
                           "our_price": [{"schedule": [{"value_with_tax": 12.99}]}]}],
    "fulfillment_availability": [{"fulfillment_channel_code": "DEFAULT",
                                  "quantity": 10}],
    "brand": [{"value": "Selvora"}],
})
check("no price schedule leaks into the attribute grid", _o["values"], {"brand": "Selvora"})
check("both are named in `skipped` so nothing vanishes without a word",
      sorted(_o["skipped"]), ["fulfillment_availability", "purchasable_offer"])

# ---------------------------------------------------------------------------
print("\nit never raises, whatever Amazon sends")
# ---------------------------------------------------------------------------
for _junk in (None, [], "", 0, {"k": "a bare string"}, {"k": 5}, {"k": [[[["deep"]]]]},
              {"k": {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": "x"}}}}}}}}}):
    try:
        LA.flatten(_junk)
    except Exception as e:                                    # noqa: BLE001
        fails.append("flatten raised on %r: %s" % (_junk, e))
        print("  FAIL flatten raised on %r: %s" % (_junk, e))
check("survives nonsense input", [f for f in fails if "raised" in f], [])

# ---------------------------------------------------------------------------
print("\nthe rule is the schema reader's rule, not a second one")
# ---------------------------------------------------------------------------
_DASH = open(r"D:\AltaScraper\dashboard.py", encoding="utf-8").read()
truthy("dashboard still collapses a lone `value` to a plain attribute",
       'if keys == ["value"]:' in _DASH)
check("and this module uses the same plumbing set",
      sorted(LA.PLUMBING), sorted(["language_tag", "marketplace_id", "audience"]))
truthy("which is still what dashboard._SUBFIELD_PLUMBING holds",
       '_SUBFIELD_PLUMBING = {"language_tag", "marketplace_id", "audience"}' in _DASH)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
