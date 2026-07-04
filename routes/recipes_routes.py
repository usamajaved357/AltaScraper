"""routes/recipes_routes.py — per-brand image "recipe" endpoints, extracted from dashboard.py (Phase 3).

register(app, ...) injection pattern. Shared helpers (_active_brand, _load_recipes,
_save_recipes, _media_root) are injected; stdlib os/re/base64 are imported here.
Route bodies moved VERBATIM (CLAUDE.md §10).

Routes:
  POST/GET /recipes/list   -> list a brand's image recipes (+ all brands' recipes)
  POST     /recipes/save   -> create/update a recipe (persists data-URL templates)
  POST     /recipes/delete -> delete a recipe
"""
import os
import re
import base64 as _b64

from flask import request, jsonify


def register(app, *, _active_brand, _load_recipes, _save_recipes, _media_root):
    """Attach the /recipes/* routes to the existing Flask app."""

    @app.route("/recipes/list", methods=["POST", "GET"])
    def recipes_list():
        """List image recipes for a brand (recipes are per-brand)."""
        b = request.get_json(force=True, silent=True) or {}
        brand = (b.get("brand", "") or request.args.get("brand", "") or _active_brand()).strip()
        data = _load_recipes()
        items = data.get(brand, []) if brand else []
        # also expose recipes from ALL brands so the user can reuse across (clearly labelled)
        everything = []
        for bn, lst in data.items():
            for r in lst:
                everything.append({**r, "brand": bn})
        return jsonify({"ok": True, "brand": brand, "recipes": items, "all_recipes": everything})

    @app.route("/recipes/save", methods=["POST"])
    def recipes_save():
        """Create/update an image recipe for a brand.
        Body: {brand, id?, name, template_image(dataURL/url), instructions}."""
        b = request.get_json(force=True) or {}
        brand = (b.get("brand", "") or _active_brand()).strip()
        if not brand:
            return jsonify({"ok": False, "error": "No brand context — open a brand/account first."}), 400
        name = (b.get("name", "") or "").strip()
        instructions = (b.get("instructions", "") or "").strip()
        template_image = b.get("template_image", "") or ""
        if not name:
            return jsonify({"ok": False, "error": "Recipe needs a name."}), 400
        if not instructions:
            return jsonify({"ok": False, "error": "Describe the changes/treatment for this recipe."}), 400
        # if template image is a data URL, persist it to the media library under _recipes
        if template_image.startswith("data:"):
            try:
                head, _, raw = template_image.partition(",")
                mime = (re.search(r"data:([^;]+)", head) or [None, "image/png"])[1]
                ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "png")
                import time as _t
                fname = f"recipe_{int(_t.time())}.{ext}"
                d = os.path.join(_media_root(), "_recipes")
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, fname), "wb") as f:
                    f.write(_b64.b64decode(raw))
                template_image = f"/media/_recipes/{fname}"
            except Exception:
                pass
        data = _load_recipes()
        lst = data.setdefault(brand, [])
        rid = b.get("id", "") or ("r" + str(int(__import__("time").time() * 1000)))
        existing = next((r for r in lst if r.get("id") == rid), None)
        rec = {"id": rid, "name": name, "template_image": template_image,
               "instructions": instructions, "ts": int(__import__("time").time())}
        if existing:
            existing.update(rec)
        else:
            lst.append(rec)
        _save_recipes(data)
        return jsonify({"ok": True, "id": rid, "recipe": rec})

    @app.route("/recipes/delete", methods=["POST"])
    def recipes_delete():
        b = request.get_json(force=True) or {}
        brand = (b.get("brand", "") or _active_brand()).strip()
        rid = b.get("id", "")
        data = _load_recipes()
        if brand in data:
            data[brand] = [r for r in data[brand] if r.get("id") != rid]
            _save_recipes(data)
        return jsonify({"ok": True})
