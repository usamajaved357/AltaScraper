"""listing/patches.py -- turning field changes into Amazon listing patch operations.

Moved word for word out of dashboard.py (Milestone 4, owner-approved 28 Sep 2026).
dashboard.py still imports every name below, so dashboard.<name> and every
route that is handed one keep working exactly as before. Nothing here may
import dashboard (it would load a second copy of the app).
"""



def _build_patches(changes, marketplace_id=""):
    """Translate approved {field:value} into SP-API JSON-Patch attribute ops.

    marketplace_id is the SELECTOR Amazon files each value under, and for IMAGES
    leaving it out was a silent no-op: the schema requires only media_location,
    so Amazon answered ACCEPTED, reported no issues, and filed the image against
    no marketplace. Images pushed from the app never arrived and nothing said
    why. Every *_image_locator patch is now built by listing/images.build_patch,
    which is the same builder /listing/image_push and the new-listing submit
    already use -- one shape, three callers (Rule 12), instead of three shapes.

    It defaults to "" so an old caller still works, but a caller that wants an
    image to actually land must pass it.
    """
    from listing import images as _img
    patches = []
    if "title" in changes:
        patches.append({"op": "replace", "path": "/attributes/item_name",
                        "value": [{"value": changes["title"]}]})
    if "description" in changes:
        patches.append({"op": "replace", "path": "/attributes/product_description",
                        "value": [{"value": changes["description"]}]})
    if "bullets" in changes:
        bl = changes["bullets"]
        if isinstance(bl, str):
            bl = [x for x in bl.split("\n") if x.strip()]
        patches.append({"op": "replace", "path": "/attributes/bullet_point",
                        "value": [{"value": x} for x in bl]})
    if "price" in changes and changes["price"]:
        patches.append({"op": "replace", "path": "/attributes/purchasable_offer",
                        "value": [{"our_price": [{"schedule": [{"value_with_tax": float(changes["price"])}]}]}]})
    if "main_image" in changes and changes["main_image"]:
        patches.append(_img.build_patch(_img.MAIN, changes["main_image"],
                                        marketplace_id))
    # generic attributes from the full editable list (keys like "attr:<name>")
    for k, v in changes.items():
        if not k.startswith("attr:"):
            continue
        name = k[5:]
        val = v
        if isinstance(val, str) and " | " in val:
            # multi-value attribute -> split back into list of {value}
            parts = [p.strip() for p in val.split(" | ") if p.strip()]
            if "image_locator" in name:
                patches.append(_img.build_patch(name, parts, marketplace_id))
            else:
                patches.append({"op": "replace", "path": f"/attributes/{name}",
                                "value": [{"value": p} for p in parts]})
        else:
            if "image_locator" in name:
                patches.append(_img.build_patch(name, val, marketplace_id))
            else:
                patches.append({"op": "replace", "path": f"/attributes/{name}",
                                "value": [{"value": val}]})
    return patches
