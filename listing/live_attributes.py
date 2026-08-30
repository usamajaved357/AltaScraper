"""listing/live_attributes.py -- what Amazon holds for a SKU, in the app's own shape.

THE ONE JOB: turn Amazon's getListingsItem `attributes` block into the flat
dot-key map the app stores in a listing's Attributes JSON, so the drawer can put
Amazon's live value beside our own. Nothing here calls Amazon (that is
api/amazon_listings.get_item) and nothing here decides anything.

WHY THIS IS THE DANGEROUS DIRECTION, AND WHAT KEEPS IT HONEST

The app already converts the OTHER way. amazon_listing_generator._renest folds
flat dot-keys back into the object tree Amazon wants at submit time:

    "battery.weight.value": "180"          ->  battery: {weight: {value: "180",
    "battery.weight.unit":  "grams"                               unit:  "grams"}}

This file is that function's inverse. If the two are not EXACT inverses, a value
read off Amazon and saved back lands in a different field than it came from --
silently, with no error, and only visible once Amazon rejects the listing or
quietly stores the number under the wrong key. test_live_attributes.py therefore
does not test this file against a copy of _renest; it loads the REAL _renest out
of the generator and round-trips through it, so the day somebody edits _renest,
this file's test is what fails.

WHERE THE "COLLAPSE" RULE COMES FROM -- NOT FROM ME

Amazon wraps almost everything: `brand: [{"value": "Selvora", "marketplace_id":
"A1F83G8C2ARO7P"}]`. The app stores that as plain `brand`, not `brand.value`.
But `item_weight: [{"value": 180, "unit": "grams"}]` IS stored as two dot-keys,
`item_weight.value` and `item_weight.unit`. So something has to decide when a
`value` key is the attribute itself and when it is a sub-field.

That decision is already made, by dashboard._extract_subfields, and it is one
line (dashboard.py:663):

    keys = [k for k in sub.keys() if k not in _SUBFIELD_PLUMBING]
    if keys == ["value"]:
        return []                 # -> a plain scalar attribute, no sub-fields

So: strip the plumbing keys, and if the only key left is a value key, the node IS
the value. That is the rule below, applied at every depth. It is copied from the
schema reader deliberately -- inventing a second rule here is how the drawer
would end up showing `supplier_declared_dg_hz_regulation` twice, once as a bare
key from Amazon and once as `.value` from the generator (CLAUDE.md Rule 12).

WHAT IS DELIBERATELY NOT FLATTENED

purchasable_offer and fulfillment_availability are arrays inside arrays -- a
price schedule, not a product attribute. _renest cannot represent them at all
(it has no array support), so a value read out of them could never be written
back. They are reported in `skipped` rather than dropped without a word, and the
drawer already shows price and quantity as their own rows.
"""

# Amazon's own wrapper bookkeeping. Same set as dashboard._SUBFIELD_PLUMBING --
# if that gains a member, this must too, which is why the name matches.
PLUMBING = ("language_tag", "marketplace_id", "audience")

# The keys Amazon puts a plain value under. Same three as
# routes/variations_routes._VALUE_KEYS; media_location is the image one, and
# leaving it out is what once made every image slot read "empty".
VALUE_KEYS = ("value", "name", "media_location")

# The copy. Stored in COLUMNS (Title, Bullet 1..5, Description), not in
# Attributes JSON, and edited by their own controls in the drawer -- so they are
# returned separately rather than being poured into the attribute grid, where
# they would appear as a second title box that disagrees with the first.
CONTENT_KEYS = ("item_name", "bullet_point", "product_description",
                "generic_keyword")

# Offer data, not product data. See the module docstring.
SKIP_KEYS = ("purchasable_offer", "fulfillment_availability")

_MAX_DEPTH = 8


def _num(v):
    """One scalar as the app stores it: a string.

    Booleans come back from Amazon as real JSON booleans, and str(True) is
    "True", which is not a value Amazon accepts back -- its enums are "true" and
    "false". A value that reads correctly on screen and is rejected on submit is
    worse than one that is obviously wrong, so they are normalised here.

    Integral floats lose the ".0" for the same reason a person would not type
    it: Amazon sent 180.0 for a whole number of grams and "180" round-trips
    identically. A genuine decimal keeps every digit.
    """
    if isinstance(v, bool):                  # before int: bool IS an int
        return "true" if v else "false"
    if isinstance(v, float):
        try:
            if v == int(v):
                return str(int(v))
        except (ValueError, OverflowError):  # nan / inf
            pass
    return str(v)


def _strip(d):
    """A node without Amazon's wrapper bookkeeping."""
    return {k: v for k, v in d.items() if str(k) not in PLUMBING}


def _scalar(v, depth=0):
    """The plain value inside whatever Amazon wrapped it in. "" when there is none."""
    if depth > _MAX_DEPTH:
        return ""
    while isinstance(v, list) and v:
        v = v[0]
    if isinstance(v, list):        # empty list
        return ""
    if isinstance(v, dict):
        d = _strip(v)
        for k in VALUE_KEYS:
            if k in d:
                return _scalar(d[k], depth + 1)
        return ""
    if v is None:
        return ""
    return _num(v)


def _walk(prefix, node, out, multi, top, depth=0):
    """One attribute into flat dot-keys, the inverse of _renest's descent."""
    if depth > _MAX_DEPTH:
        return
    if isinstance(node, list):
        if not node:
            return
        # MORE THAN ONE VALUE IS REPORTED, NOT AVERAGED AWAY.
        # special_feature can hold four entries. Showing the first as if it were
        # the whole answer, in a box someone can edit and save, would drop the
        # other three on the next submit without ever saying so. The count goes
        # back to the caller, which renders these read-only.
        if len(node) > 1:
            multi[top] = len(node)
        node = node[0]
    if not isinstance(node, dict):
        if node is None:
            return
        s = _num(node)
        if s != "":
            out[prefix] = s
        return
    d = _strip(node)
    if not d:
        return
    keys = list(d.keys())
    # THE RULE, from dashboard._extract_subfields (see the module docstring).
    if len(keys) == 1 and str(keys[0]) in VALUE_KEYS:
        s = _scalar(d[keys[0]], depth + 1)
        if s != "":
            out[prefix] = s
        return
    for k in sorted(keys, key=str):
        _walk(prefix + "." + str(k), d[k], out, multi, top, depth + 1)


def flatten(attributes):
    """Amazon's attributes block -> the app's flat dot-key map. Never raises.

    -> {"values":  {dot_key: str}   attributes, in Attributes-JSON shape
        "content": {key: [str]}     title/bullets/description/keywords, in order
        "multi":   {top_key: int}   attributes Amazon holds >1 value for
        "skipped": [str]}           offer blocks that cannot round-trip
    """
    values, content, multi, skipped = {}, {}, {}, []
    if not isinstance(attributes, dict):
        return {"values": values, "content": content, "multi": multi,
                "skipped": skipped}
    for k, v in attributes.items():
        key = str(k)
        if key in SKIP_KEYS:
            skipped.append(key)
            continue
        if key in CONTENT_KEYS:
            # Kept as a LIST. bullet_point is five entries and the order is the
            # order they appear on the page; collapsing it to the first one
            # would quietly lose four bullets.
            items = v if isinstance(v, list) else [v]
            got = [s for s in (_scalar(x) for x in items) if s]
            if got:
                content[key] = got
            continue
        _walk(key, v, values, multi, key)
    return {"values": values, "content": content, "multi": multi,
            "skipped": skipped}
