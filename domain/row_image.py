"""domain/row_image.py -- a listing row's main image, read ONE way.

Moved out of routes/dashboard_routes.py (28 Sep 2026) when a second route needed
it: /submit/precheck read `r["attributes"]` and `r["main_image"]`, keys a row
never has -- a row keeps its attributes as TEXT in "Attributes JSON" -- so even
once it could read rows at all it would never have found an image (CLAUDE.md
Rule 12: one reader, not two).
"""
import json as _json


def main_image(attrs_json, strict=False):
    """Best-effort main-image URL from a row's Attributes JSON (locators vary in shape).

    `strict` reads only the main-image fields -- what the submit sends as the
    main image -- without falling back to any other key that mentions "image"
    (right for a thumbnail, wrong for a warning about the main image)."""
    try:
        a = _json.loads(attrs_json or "{}") if not isinstance(attrs_json, dict) else attrs_json
        if not isinstance(a, dict):
            return ""

        def _url(v):
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v[0].get("value") or v[0].get("media_location") or ""
            return v if isinstance(v, str) else ""
        if strict:
            # Only the field the submit sends as the main image.
            return _url(a.get("main_product_image_locator")) or ""
        for k in ("main_product_image_locator", "main_image_url"):
            u = _url(a.get(k))
            if u:
                return u
        for k, v in a.items():
            if "image" in str(k).lower():
                u = _url(v)
                if u:
                    return u
    except Exception:
        pass
    return ""


# Whether Amazon can use an image is NOT decided here: it depends on the app's
# public address, and domain/image_urls.main_image_problem is the one rule,
# shared with the submit itself (review of batch 8).
