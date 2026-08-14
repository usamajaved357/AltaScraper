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


def themes_from_schema(schema):
    """The variation themes this product type allows, straight from its schema.

    Returns [] when the type has no variation_theme -- which means it does not
    support variations at all, and is a refusal rather than an empty dropdown.
    """
    props = ((schema or {}).get("properties") or {})
    vt = props.get("variation_theme") or {}
    # Amazon nests this as an array of objects with a `name` enum. Several
    # shapes exist across product types, so each is tried rather than assumed.
    out = []

    def _collect(node):
        if not isinstance(node, dict):
            return
        for key in ("enum", "examples"):
            for v in (node.get(key) or []):
                if isinstance(v, str) and v and v not in out:
                    out.append(v)
        for sub in ("items", "properties", "anyOf", "oneOf", "allOf"):
            n = node.get(sub)
            if isinstance(n, dict):
                for v in n.values():
                    _collect(v)
                _collect(n)
            elif isinstance(n, list):
                for v in n:
                    _collect(v)

    _collect(vt)
    return out


def theme_axes(theme):
    """The attributes a theme varies on. SIZECOLOR varies on two, not one."""
    t = str(theme or "").upper().replace("_", "").replace("-", "")
    known = ["SIZE", "COLOR", "COLOUR", "STYLE", "MATERIAL", "FLAVOR", "FLAVOUR",
             "SCENT", "PATTERN", "COUNT", "MODEL", "PACKAGE_QUANTITY"]
    axes = []
    rest = t
    for k in sorted(known, key=len, reverse=True):
        flat = k.replace("_", "")
        if flat in rest:
            axes.append(k.lower().replace("colour", "color").replace("flavour", "flavor"))
            rest = rest.replace(flat, "", 1)
    return axes or [t.lower()]


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

    types = {str(c.get("product_type") or "").strip().upper()
             for c in kids if c.get("product_type")}
    if product_type:
        types.add(str(product_type).strip().upper())
    if len(types) > 1:
        problems.append("These are different product types (%s). Amazon only "
                        "groups products of the same type."
                        % ", ".join(sorted(t for t in types if t)))

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

    # The children must actually DIFFER on the axis they are grouped by. Two
    # SKUs both in "Large" under a SIZE theme is not a family: Amazon shows one
    # picker with two identical options and they compete with each other.
    if theme and len(kids) >= 2:
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
