"""listing/variations.py -- turning separate listings into one variation family.

WHAT A FAMILY ACTUALLY IS ON AMAZON
Three attributes, and every one of them has to agree:

    parentage_level              "parent" on the parent, "child" on each child
    variation_theme              the SAME value on all of them (SIZE, COLOR, ...)
    child_parent_sku_relationship  on each child, naming the parent's SKU

The parent is a real listing with its own SKU that nobody can buy: it carries the
title and the images the family shows in search, and the children carry the price
and the stock. Getting this wrong does not fail loudly -- Amazon accepts a
half-formed family and the products simply stop appearing, which is why every
check here happens BEFORE anything is sent.

THE THEME COMES FROM THE SCHEMA, NEVER FROM US
variation_theme is an enum whose allowed values differ per product type, and a
value that is not in that enum is rejected -- or worse, accepted and then
ignored. So the caller passes the live schema and the theme is read out of it
(CLAUDE.md Rule 4). If the schema has no variation_theme at all, that product
type does not support variations and the whole thing is refused with that
sentence, rather than sending a request that fails obscurely.

WHAT MAKES A MERGE REFUSABLE
Children must differ on the theme's own axis -- two SKUs both in "Large" under a
SIZE theme is not a variation family, it is two listings that will fight each
other -- and they must all be the same product type. Both are checked here, with
the reason, before a single call is made.

NOTHING IN THIS FILE TALKS TO AMAZON. It decides and it explains; the caller
sends. That is what makes the preview honest: the preview IS the payload.
"""

PARENT = "parent"
CHILD = "child"


def _theme_node(schema):
    """The variation_theme name node, wherever the schema keeps it."""
    vt = ((schema or {}).get("properties") or {}).get("variation_theme") or {}
    node = ((vt.get("items") or {}).get("properties") or {}).get("name")
    return node if isinstance(node, dict) else vt


def themes_from_schema(schema):
    """The themes this product type allows TODAY, straight from its schema.

    Measured against the live UK account on 14 Aug 2026: SPACE_HEATER lists 76
    themes of which 47 are marked $lifecycle.enumDeprecated, TOOLS 122 of which
    111 are. Offering a deprecated one is offering something Amazon no longer
    accepts, so they are removed -- an earlier version collected every enum value
    it could find and would have put all 47 dead SPACE_HEATER themes in the list.

    Returns [] when the type has no variation_theme at all, which means it cannot
    have variations and is a refusal rather than an empty dropdown.
    """
    node = _theme_node(schema)
    if not isinstance(node, dict):
        return []
    live = [v for v in (node.get("enum") or []) if isinstance(v, str) and v]
    dead = set((node.get("$lifecycle") or {}).get("enumDeprecated") or [])
    out = [v for v in live if v not in dead]
    if out or live:
        return out
    # Some schemas describe the field without an enum; examples are all there is.
    return [v for v in (node.get("examples") or []) if isinstance(v, str) and v]


def attribute_names(schema):
    """Every attribute name this product type has, or None if unknown.

    None and [] are different answers and only one of them is safe to act on:
    None means the schema did not say, so no axis can be ruled out; [] would
    mean the type genuinely has no attributes, which is not a real state.
    """
    names = (schema or {}).get("attribute_names")
    if isinstance(names, (list, tuple, set)):
        return {str(n) for n in names if n}
    props = (schema or {}).get("properties")
    # A whole schema, rather than the trimmed one -- then the properties ARE the
    # attribute list. The trimmed one keeps only variation_theme and the image
    # slots, so reading its properties would declare 100+ real attributes
    # missing, which is worse than not knowing.
    if isinstance(props, dict) and len(props) > 25:
        return set(props.keys())
    return None


def missing_axes(theme, attrs):
    """Axes this theme names that the product type does not actually have.

    MEASURED on OUTDOOR_LIVING (live UK account, 17 Aug 2026). Amazon offered
    these ten themes for the type:

        COLOR, COLOR_NAME/MATERIAL_TYPE, COLOR_NAME/NUMBER_OF_ITEMS,
        ITEM_DISPLAY_HEIGHT, ITEM_WEIGHT, MATERIAL_TYPE, MATERIAL_TYPE/COLOR_NAME,
        SIZE, SIZE/PATTERN, VOLTAGE

    and the type's own 114 attributes include `color`, `size`, `pattern`,
    `item_weight`, `voltage`, `material` -- but NO `color_name`, no
    `material_type`, and no `item_display_height`. So five of the ten themes on
    offer name an axis that cannot be set on this product type at all.

    Before this, the checker blamed the products for it: "these products have no
    material_type set, and the family is grouped by it — Amazon needs a value on
    every child", which sends someone hunting for a field that does not exist.
    Same shape as the item_type_keyword bug below.

    No guessing at a substitute. `material_type` is not silently rewritten to
    `material` -- close names are not the same attribute, and CLAUDE.md Rule 4
    is explicit that a value is built from what the schema literally says. The
    theme is reported as unusable and the ones that do work are offered instead.
    """
    if attrs is None:
        return []                        # not known, so nothing can be ruled out
    return [a for a in theme_axes(theme) if a not in attrs]


def split_themes(themes, attrs):
    """(usable, [(theme, missing_axes), ...]) for a list of themes."""
    usable, blocked = [], []
    for t in themes or []:
        gone = missing_axes(t, attrs)
        (blocked.append((t, gone)) if gone else usable.append(t))
    return usable, blocked


def theme_axes(theme):
    """The attribute names a theme varies on.

    Amazon writes a theme as its attribute names joined by "/" -- COLOR/SIZE,
    VOLTAGE/WATTAGE, COLOR/SPECIFIC_USES_FOR_PRODUCT/FINISH_TYPE/SIZE -- and each
    part lowercased IS the attribute key. Confirmed against SPACE_HEATER, TOOLS
    and KITCHEN on the live account: every part of every theme resolves to a real
    property in the schema.

    An earlier version matched known words inside a flattened name, which got
    SIZE_COLOR right by luck and would have mangled the four-part themes
    entirely, inventing axes that do not exist and missing the ones that do.
    """
    return [p.strip().lower() for p in str(theme or "").split("/") if p.strip()]


def check(parent_sku, children, theme, schema=None, product_type=""):
    """Everything wrong with this merge, as sentences. Empty list means go.

    `children` is [{sku, product_type, attributes:{...}}]. Checked BEFORE any
    call, because Amazon accepts a half-formed family without complaint and the
    products just quietly stop showing.
    """
    problems = []
    parent_sku = str(parent_sku or "").strip()
    kids = [c for c in (children or []) if str(c.get("sku") or "").strip()]

    if not parent_sku:
        problems.append("The family needs a parent SKU — a code for the group "
                        "itself, which nobody buys.")
    if len(kids) < 2:
        problems.append("A variation family needs at least two products. One "
                        "product on its own is just a listing.")
    if any(str(c.get("sku")).strip() == parent_sku for c in kids):
        problems.append("The parent SKU is also in the list of children. The "
                        "parent is the group, not one of the items in it.")

    seen = {}
    for c in kids:
        s = str(c.get("sku")).strip()
        seen[s] = seen.get(s, 0) + 1
    dupes = [s for s, n in seen.items() if n > 1]
    if dupes:
        problems.append("The same SKU is listed twice: %s." % ", ".join(sorted(dupes)))

    # ---- what every member of a family must share --------------------------
    # These are Amazon's constraints, not ours, and each is checked against what
    # Amazon CURRENTLY HOLDS for the SKU rather than against anything cached --
    # the caller fetches live attributes for exactly this reason. Where a value
    # is missing from Amazon's own response it is reported as unknown rather than
    # treated as matching, because "we could not read it" and "they agree" are
    # different answers and only one of them is safe to act on.
    #
    # probe_variation.py reads a family that already exists on the account and
    # prints what its parent and children actually share, so this list can be
    # confirmed against reality instead of taken on trust (CLAUDE.md Rule 4).
    for field, label, why in (
            ("product_type", "product type",
             "Amazon only groups products of the same type"),
            ("brand", "brand",
             "every product in a family has to carry the same brand"),
            ("item_type_keyword", "item type keyword",
             "Amazon uses it to place the family in the catalogue, so it has to "
             "be the same on all of them"),
    ):
        vals, unknown = set(), []
        for c in kids:
            v = str(c.get(field) or "").strip()
            if not v:
                unknown.append(str(c.get("sku")))
            else:
                vals.add(v.upper())
        if field == "product_type" and product_type:
            vals.add(str(product_type).strip().upper())
        if len(vals) > 1:
            problems.append("These have different %s values (%s). %s."
                            % (label, ", ".join(sorted(vals)), why))
        elif unknown and not (field == "item_type_keyword" and not vals):
            # A FIELD AMAZON DOES NOT CARRY IS NOT A FIELD WE CAN CONFIRM, and
            # refusing until it is confirmed is a refusal nobody can clear:
            # there is no box on the screen that sets item_type_keyword.
            #
            # MEASURED on a live UK listing (SQUEEGEE, 45 attributes returned):
            # Amazon sends brand, size, colour, material and the rest, and sends
            # NO item_type_keyword and no item_type_name. The only keyword-ish
            # attribute is generic_keyword. So this check fired on every pair of
            # products on the account and step 3 was unreachable for all of them.
            #
            # `not vals` is doing the work: NONE of the children carry the field,
            # which means the product type does not use it. If SOME carry it and
            # others do not, that is a genuine mismatch worth stopping for and it
            # still stops -- which is what test_variations.py asserts with
            # SH-NOKW.
            #
            # Brand and product type keep the strict rule. Amazon does return
            # both, and a family that disagrees on either is the half-formed one
            # that gets accepted and then quietly stops showing.
            problems.append("Could not read the %s for %s, so it cannot be "
                            "confirmed that they match — and %s."
                            % (label, ", ".join(unknown), why))

    attrs = attribute_names(schema)
    if not theme:
        problems.append("Pick what makes these products different from each "
                        "other — size, colour, and so on.")
    elif schema is not None:
        allowed = themes_from_schema(schema)
        if not allowed:
            problems.append("This product type does not support variations at "
                            "all — its schema has no variation theme, so there "
                            "is nothing to group these under.")
        elif theme not in allowed:
            problems.append("%s is not a variation theme this product type "
                            "allows. It permits: %s."
                            % (theme, ", ".join(allowed[:12])))
        else:
            # OFFERED BY AMAZON, BUT UNUSABLE ON THIS TYPE. See missing_axes():
            # five of OUTDOOR_LIVING's ten themes name an attribute the type
            # does not have. Named as such, with the themes that DO work, rather
            # than as a missing value on the products.
            gone = missing_axes(theme, attrs)
            if gone:
                works, _ = split_themes(allowed, attrs)
                problems.append(
                    "Amazon offers %s for %s, but %s has no %s attribute — there "
                    "is nowhere to set the value this grouping needs, on any "
                    "listing of this type. %s"
                    % (theme, product_type or "this product type",
                       product_type or "it",
                       " or ".join(gone),
                       ("Groupings that do work here: %s." % ", ".join(works[:10]))
                       if works else
                       "No grouping Amazon offers for this type is usable."))

    # The children must actually DIFFER on the axis they are grouped by. Two
    # SKUs both in "Large" under a SIZE theme is not a family: Amazon shows one
    # picker with two identical options and they compete with each other.
    if theme and len(kids) >= 2 and not missing_axes(theme, attrs):
        # `not missing_axes` gates the whole block: an axis the product type does
        # not have is already reported above as the type's limitation, and saying
        # "these products have no material_type set" underneath it points at the
        # products for something that is not about them.
        axes = theme_axes(theme)
        # Every axis must have a value on every child: Amazon builds one picker
        # per axis and a child missing a value cannot be selected in it.
        for axis in axes:
            missing = [str(c.get("sku")) for c in kids
                       if (c.get("attributes") or {}).get(axis) in (None, "")]
            if missing:
                problems.append("%s %s no %s set, and the family is grouped by "
                                "it — Amazon needs a value on every child."
                                % (", ".join(missing),
                                   "has" if len(missing) == 1 else "have", axis))

        # But uniqueness is across the COMBINATION, not each axis on its own.
        # Under SIZE_COLOR a Small/Red and a Small/Blue are a perfectly good
        # family -- they share a size and differ on colour, which is the whole
        # point of a two-axis theme. Checking each axis separately would reject
        # every real multi-axis family there is.
        if not any("no %s set" % a in p for a in axes for p in problems):
            combos = [tuple(str((c.get("attributes") or {}).get(a) or "").strip().lower()
                            for a in axes) for c in kids]
            if len(set(combos)) < len(combos):
                what = " and ".join(axes)
                problems.append("More than one product has the same %s. Children "
                                "have to differ on what the family varies by, or "
                                "they compete with each other instead of "
                                "grouping." % what)
    return problems


def build(parent_sku, children, theme, product_type, parent_attributes=None):
    """The exact payloads a merge would send. This IS the preview.

    Returns {"parent": {...}, "children": [{...}]} where each entry carries the
    sku and the attributes to write. The caller submits them; nothing is sent
    from here, so what is shown and what is sent cannot drift apart.
    """
    kids = [c for c in (children or []) if str(c.get("sku") or "").strip()]

    parent = {
        "sku": str(parent_sku).strip(),
        "product_type": product_type,
        "attributes": dict(parent_attributes or {}),
        # The parent is NOT buyable. It carries no price and no stock -- those
        # belong to the children, and putting them here creates a listing that
        # competes with its own family.
        "role": "parent",
    }
    parent["attributes"].update({
        "parentage_level": [{"value": PARENT}],
        "variation_theme": [{"name": theme}],
    })

    out_children = []
    for c in kids:
        out_children.append({
            "sku": str(c.get("sku")).strip(),
            "product_type": c.get("product_type") or product_type,
            "role": "child",
            "attributes": {
                "parentage_level": [{"value": CHILD}],
                "variation_theme": [{"name": theme}],
                "child_parent_sku_relationship": [{
                    "child_relationship_type": "variation",
                    "parent_sku": str(parent_sku).strip(),
                }],
            },
        })

    return {"parent": parent, "children": out_children,
            "theme": theme, "axes": theme_axes(theme),
            "product_type": product_type}


# ---------------------------------------------------------------------------
# WHAT THE PARENT HAS TO CARRY
#
# The parent is a real listing and Amazon holds it to the product type's rules
# like any other. Built with only parentage_level, variation_theme, a title and
# the GTIN exemption, EVERY merge was rejected, for every product type. Measured
# on the live UK account, 17 Aug 2026, merging two OUTDOOR_LIVING slashers:
#
#   Amazon answered INVALID -- 'Brand Name' is required but missing.;
#   'Are batteries required?' is required but missing.;
#   'Dangerous Goods Regulations' is required but missing.
#
# It stopped at the parent and touched no children, which is the one thing that
# went right: half a family is the state Amazon accepts in silence.
#
# NOT FIXED BY READING THAT MESSAGE. CLAUDE.md Rule 4 forbids deriving an
# attribute name from Amazon's prose, and this message shows exactly why it
# would fail anyway: the type's schema lists six required attributes and
# batteries_required is not among them, so "read `required` and fill it" would
# have missed two of the three. Amazon applies conditional requirements the
# top-level list does not show.
#
# THE RULE INSTEAD: the parent inherits every attribute all its children AGREE
# on. That is what a parent is -- the description the family has in common --
# and it needs no list of names at all. Every value written is a value Amazon
# already holds on a child, copied in Amazon's own shape, so nothing is invented
# and nothing is guessed. Attributes the children differ on are the varying ones
# and are exactly what must NOT go on the parent.

# Attributes that are never inherited, whatever the children say.
_NEVER_ON_PARENT = frozenset({
    # A PARENT CANNOT BE BOUGHT. Price and stock belong to the children; on the
    # parent they create a listing that competes with its own family.
    "purchasable_offer", "fulfillment_availability", "list_price",
    "merchant_shipping_group", "condition_type", "condition_note",
    # CLAUDE.md Rule 1: never sent, from anywhere, for any reason.
    "merchant_suggested_asin",
    # A container has no barcode of its own. It goes up under the exemption,
    # never with a child's identifier, which belongs to one physical product.
    "externally_assigned_product_identifier",
    # Set from the theme, not copied.
    "parentage_level", "variation_theme", "child_parent_sku_relationship",
})


def _same(values):
    """Do these attribute values all say the same thing?"""
    import json as _json
    try:
        first = _json.dumps(values[0], sort_keys=True)
    except (TypeError, ValueError):
        return False
    for v in values[1:]:
        try:
            if _json.dumps(v, sort_keys=True) != first:
                return False
        except (TypeError, ValueError):
            return False
    return True


def required_from_schema(schema):
    """The attributes this product type cannot go up without."""
    req = (schema or {}).get("required")
    return [str(r) for r in req if r] if isinstance(req, (list, tuple)) else []


def parent_attributes(children, theme, title="", marketplace_id="", extra=None,
                      required=None):
    """What the parent listing should carry, and what it could not settle.

    `children` is [{sku, raw}] where raw is Amazon's own attribute dict for that
    SKU -- its wrappers untouched, so what goes back up is the shape that came
    down (Rule 4: the schema, not our idea of it).

    Returns {attributes, inherited, differ, images_from} where `differ` names the
    attributes the children disagreed on. Those are reported, never averaged and
    never taken from whichever child happened to be first.
    """
    kids = [c for c in (children or []) if (c or {}).get("raw")]
    attrs, inherited, differ = {}, [], []

    keys = set()
    for c in kids:
        keys |= set((c.get("raw") or {}).keys())
    for k in sorted(keys):
        if k in _NEVER_ON_PARENT:
            continue
        vals = [(c.get("raw") or {}).get(k) for c in kids]
        if any(v is None for v in vals):
            # Present on some children and not others is a disagreement, not an
            # absence: writing one child's value onto the family would describe
            # the others as something they never said.
            differ.append(k)
            continue
        if _same(vals):
            attrs[k] = vals[0]
            inherited.append(k)
        else:
            differ.append(k)

    # The three that make it a parent rather than a listing.
    attrs["parentage_level"] = [{"value": PARENT}]
    attrs["variation_theme"] = [{"name": theme}]
    # No barcode of its own -- the exemption, per CLAUDE.md Rule 1, never an
    # invented one.
    attrs.setdefault("supplier_declared_has_product_identifier_exemption",
                     [{"value": True, "marketplace_id": marketplace_id}]
                     if marketplace_id else [{"value": True}])
    if title:
        attrs["item_name"] = ([{"value": title, "language_tag": "en_GB",
                                "marketplace_id": marketplace_id}]
                              if marketplace_id else [{"value": title}])

    # WHAT AGREEMENT CANNOT SETTLE, AND THE TYPE STILL DEMANDS.
    #
    # Two slashers do not share a description or a set of bullet points -- they
    # were written separately -- so neither is inherited, and OUTDOOR_LIVING
    # requires both. Measured, second attempt, once brand and the rest were
    # inherited:
    #
    #   'Bullet Point' is required but missing.; 'Product Description' is
    #   required but missing.
    #
    # A parent needs its own copy of these, and there is no honest way to derive
    # one from two different texts. So the first child's is BORROWED -- a real
    # choice, which is why every borrowed attribute is named with the SKU it came
    # from, shown in the preview, and editable before anything is sent. Silently
    # taking whichever child sorted first is the version of this that nobody
    # would ever notice.
    #
    # Only for what the schema actually requires. An optional attribute the
    # children disagree on stays off the parent, where it belongs.
    borrowed = {}
    want = list(required or [])
    # The picture search shows IS the parent's, so it is worth borrowing whether
    # or not the type demands one: a family with no image is a family nobody
    # clicks.
    want.append("main_product_image_locator")
    for k in want:
        if k in attrs or k in _NEVER_ON_PARENT:
            continue
        for c in kids:
            got = (c.get("raw") or {}).get(k)
            if got:
                attrs[k] = got
                borrowed[k] = str(c.get("sku") or "")
                break

    for k, v in (extra or {}).items():
        attrs[k] = v                       # an explicit choice wins over all of it
        borrowed.pop(k, None)

    return {"attributes": attrs, "inherited": inherited, "differ": differ,
            "borrowed": borrowed,
            "images_from": borrowed.get("main_product_image_locator", ""),
            "unresolved": [k for k in (required or [])
                           if k not in attrs and k not in _NEVER_ON_PARENT]}


def suggest_parent_sku(children, theme=""):
    """A parent SKU built from what the children share, for the box to start in.

    Only ever a suggestion: it is shown in an editable field, because a SKU is
    permanent on Amazon and a generated one that nobody looked at is how an
    account ends up full of codes that mean nothing to anyone.
    """
    skus = [str(c.get("sku") or "").strip() for c in (children or [])
            if str(c.get("sku") or "").strip()]
    if not skus:
        return ""
    # The shared leading text, cut at a separator so it does not stop mid-token.
    first = skus[0]
    n = len(first)
    for s in skus[1:]:
        n = min(n, len(s))
        while n and first[:n].lower() != s[:n].lower():
            n -= 1
    stem = first[:n].rstrip("-_ .")
    if len(stem) < 3:
        stem = first.rstrip("-_ .")
    return "%s-PARENT" % stem
