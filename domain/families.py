"""domain/families.py -- parent and child listings, the way Seller Central shows them.

    "ALSO I WANT MY APP TO SHOW the parents and child relation like we have in
     amazon."

WHAT WAS MISSING

Everything needed to CREATE a variation family already existed and is well
tested -- listing/variations.py refuses bad ones, builds the payload and submits
it. Nothing existed to VIEW one. The Variations screen is a three-step creation
wizard over a FLAT list, and the only sign of a family anywhere in the app was
one line of text on a selected row of the Listings screen.

The data was not missing either. Amazon returns it on getListingsItem under
`relationships`, and routes/live_routes.py has parsed it since the mirror was
built -- into an in-memory cache, capped at 300 SKUs per sync, erased by a
restart. So the app knew, briefly, and forgot.

It is now read on the pass that already visits every SKU and stored on the
snapshot beside the thumbnails, which is why it survives.

WHAT A FAMILY IS HERE

Amazon's model is one PARENT that is not itself buyable, and CHILDREN that are.
The parent holds the title and the family; the children hold the colour, the
size, the price and the stock. So a family is:

    parent      the SKU whose relationships list childSkus
    children    the SKUs that name it in parentSkus
    theme       what differs between them -- COLOR, SIZE, COLOR/SIZE

BUILT FROM BOTH DIRECTIONS, ON PURPOSE
A child names its parent and a parent names its children, and either half can be
missing: a SKU may not have been enriched yet, or Amazon may answer one side and
throttle the other. Using only one direction loses a family whenever the SKU
that happened to carry the link was the one that failed. Both are read and
merged, and a family assembled from only one side is still a family.

ORPHANS ARE REPORTED, NOT HIDDEN
A child whose parent is not in this account's catalogue is a real thing --
usually a listing built against another seller's parent, or a parent that was
deleted. It gets its own group rather than disappearing, because a SKU that
silently belongs to no family is indistinguishable from one nobody has looked at.
"""

from domain import live_snapshots as _snap


def _s(v):
    return str(v or "").strip()


def _skus(v):
    """A list of SKUs from whatever the snapshot holds. Never raises."""
    if isinstance(v, str):
        v = [v]
    out, seen = [], set()
    for x in (v or []):
        x = _s(x)
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def build(items):
    """Snapshot items -> the families in them, plus what is left over.

    Returns {"families": [...], "orphans": [...], "singles": n, "counted": n}.

    Each family is:
        {parent_sku, parent (item or None), theme, children [items],
         child_count, listed_units, in_stock_children, orphan}
    """
    items = [it for it in (items or []) if isinstance(it, dict)]
    by_sku = {}
    for it in items:
        s = _s(it.get("sku"))
        if s:
            by_sku[s] = it

    # ---- both directions, merged -------------------------------------------
    # parent sku -> set of child skus
    tree, theme_of = {}, {}
    for it in items:
        sku = _s(it.get("sku"))
        if not sku:
            continue
        th = _s(it.get("variation_theme"))
        for kid in _skus(it.get("child_skus")):
            tree.setdefault(sku, [])
            if kid not in tree[sku]:
                tree[sku].append(kid)
            if th and not theme_of.get(sku):
                theme_of[sku] = th
        for par in _skus(it.get("parent_skus")):
            tree.setdefault(par, [])
            if sku not in tree[par]:
                tree[par].append(sku)
            # The theme is a property of the family, and a CHILD often carries it
            # when the parent's own record has not been read yet.
            if th and not theme_of.get(par):
                theme_of[par] = th

    def _qty(it):
        try:
            return int(str((it or {}).get("qty") or "").strip() or 0)
        except (TypeError, ValueError):
            return 0

    families, in_family = [], set()
    for parent_sku, kids in tree.items():
        parent = by_sku.get(parent_sku)
        children = [by_sku[k] for k in kids if k in by_sku]
        if not children and parent is None:
            continue                       # nothing of this family is here at all
        # Only SKUs that are ACTUALLY in this catalogue count towards "how many
        # of your listings are in a family". An orphan's missing parent is a
        # name, not a listing, and counting it made the stand-alone total come
        # out one short -- which is the kind of arithmetic nobody checks.
        if parent is not None:
            in_family.add(parent_sku)
        in_family.update(k for k in kids if k in by_sku)
        # Sorted by what differs, so colours and sizes read in a stable order
        # rather than in whatever order Amazon happened to answer.
        children.sort(key=lambda c: (_s(c.get("title")).lower(), _s(c.get("sku"))))
        units = sum(_qty(c) for c in children)
        families.append({
            "parent_sku": parent_sku,
            "parent": parent,
            # An ORPHAN family: the children are here, the parent is not. Said
            # rather than hidden -- usually a listing built against somebody
            # else's parent, or a parent that was deleted.
            "orphan": parent is None,
            "theme": theme_of.get(parent_sku, ""),
            "children": children,
            "child_count": len(children),
            "listed_units": units,
            "in_stock_children": sum(1 for c in children if _qty(c) > 0),
        })

    # Biggest families first: a 12-child family is the one worth looking at, and
    # an orphan goes last because it is a problem rather than a product.
    families.sort(key=lambda f: (f["orphan"], -f["child_count"], f["parent_sku"]))

    return {
        "families": families,
        "family_count": len(families),
        "in_family": len(in_family),
        # Everything that is not in a family. Not a fault -- most listings are
        # stand-alone -- but the number makes the coverage readable.
        "singles": max(0, len(by_sku) - len(in_family)),
        "counted": len(by_sku),
    }


def for_account(config_path, account_id, marketplace):
    """The families in one account+marketplace, from the stored snapshot."""
    rec = _snap.get(config_path, account_id, marketplace) or {}
    items = rec.get("items") or []
    out = build(items)
    # HOW MUCH OF THE CATALOGUE HAS ACTUALLY BEEN ASKED. Amazon only tells us
    # about a family when that SKU has been read individually, and the refresher
    # works through the catalogue a batch at a time. Without this, "no families"
    # reads as "you have none" when it may mean "nothing has been read yet".
    known = sum(1 for it in items if isinstance(it, dict)
                and (it.get("parent_skus") or it.get("child_skus")
                     or it.get("variation_theme") or it.get("img")))
    out["relationships_known_for"] = known
    out["snapshot_ts"] = rec.get("ts")
    return out
