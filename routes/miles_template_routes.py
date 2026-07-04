"""routes/miles_template_routes.py — Miles main-image template endpoints, extracted from dashboard.py (Phase 3).

register(app, ...) injection pattern; route bodies moved VERBATIM (CLAUDE.md §10).
Injected: _cfg, _state, the template-index helpers (_load_miles_templates,
_save_miles_templates, _miles_tpl_dir), and media helpers (_sniff_image_ext, _sku_dir,
_safe_sku). miles_template (root module), anthropic and PIL are imported inline.

Routes: POST /miles_template/ai_fill, GET /miles_template/list,
        POST /miles_template/upload, POST /miles_template/delete,
        GET /miles_template/preview/<rid>, POST /miles_template/save_zones,
        POST /miles_template/render
"""
import json
import os
import re
import base64 as _b64

from flask import request, jsonify, send_from_directory


def register(app, *, _cfg, _state, _load_miles_templates, _save_miles_templates,
             _miles_tpl_dir, _sniff_image_ext, _sku_dir, _safe_sku):
    """Attach the /miles_template/* routes to the existing Flask app."""

    @app.route("/miles_template/ai_fill", methods=["POST"])
    def miles_template_ai_fill():
        """Use the AI to decide the panel text (title / grade subtitle / application)
        from the listing's title + specs. Returns a spec the UI can drop into the
        form. Body: {sku}."""
        b = request.get_json(force=True) or {}
        sku = b.get("sku", "")
        cfg = _cfg()
        key = (cfg.get("anthropic_api_key") or "").strip()
        if not key:
            return jsonify({"ok": False, "error": "No anthropic_api_key in config.json"}), 400
        # gather the listing's text from the active sheet rows already loaded
        title = b.get("title", "") or ""
        bullets = b.get("bullets", "") or ""
        specs = b.get("specs", "") or ""
        if not (title or bullets or specs):
            return jsonify({"ok": False, "error": "no listing text provided"}), 400
        prompt = (
            "You lay out the text panel for a Miles Lubricants product main image. "
            "The panel has these zones, top to bottom:\n"
            "- TITLE: the product family/name, 1-3 short words (e.g. 'INDUSTRIAL GEAR OIL', 'SXR COOLANT').\n"
            "- GRADE: the single most important viscosity/grade/spec, very short (e.g. '80W-90', 'ISO 32', 'ISO VG 46').\n"
            "- (CHOICE OF MECHANICS is fixed, do not output it.)\n"
            "- APPLICATION: what the fluid IS, 1-2 short words (e.g. 'HYDRAULIC FLUID', 'COMPRESSOR FLUID', 'GEAR OIL').\n\n"
            "Rules: ALL CAPS. Keep each field SHORT so it fits a narrow panel. No brand names of other companies. "
            "No marketing sentences. Pull the grade/viscosity exactly from the product text if present.\n\n"
            f"PRODUCT TITLE: {title}\n"
            f"BULLETS/COPY: {bullets[:1200]}\n"
            f"SPECS: {specs[:800]}\n\n"
            "Return ONLY JSON, no markdown:\n"
            '{"title":"", "grade":"", "application":"", "application_lines":2}'
        )
        try:
            import anthropic as _ant
            client = _ant.Anthropic(api_key=key)
            msg = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=300,
                messages=[{"role": "user", "content": prompt}])
            txt = "".join(getattr(p, "text", "") for p in msg.content).strip()
            txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
            data = json.loads(txt)
        except Exception as e:
            return jsonify({"ok": False, "error": f"AI failed: {str(e)[:200]}"}), 500
        spec = {
            "title": (data.get("title", "") or "").strip(),
            "subtitles": [{"text": (data.get("grade", "") or "").strip(), "lines": 1}],
            "application": {"text": (data.get("application", "") or "").strip(),
                            "lines": int(data.get("application_lines", 2) or 2)},
        }
        return jsonify({"ok": True, "spec": spec})


    @app.route("/miles_template/list", methods=["GET"])
    def miles_template_list():
        return jsonify({"ok": True, "templates": _load_miles_templates()})


    @app.route("/miles_template/upload", methods=["POST"])
    def miles_template_upload():
        """Save an uploaded blank template PNG and register it.
        Body: {label, container:'pail'|'drum', data:<dataURL>}"""
        b = request.get_json(force=True) or {}
        label = (b.get("label", "") or "").strip() or "Template"
        container = (b.get("container", "") or "drum").strip().lower()
        data = b.get("data", "") or ""
        if not data.startswith("data:"):
            return jsonify({"ok": False, "error": "no image data"}), 400
        try:
            head, _, raw = data.partition(",")
            mime = (re.search(r"data:([^;]+)", head) or [None, "image/png"])[1]
            ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "png")
            import time as _t
            fname = f"tpl_{container}_{int(_t.time())}.{ext}"
            with open(os.path.join(_miles_tpl_dir(), fname), "wb") as f:
                f.write(_b64.b64decode(raw))
        except Exception as e:
            return jsonify({"ok": False, "error": f"save failed: {e}"}), 500
        data_idx = _load_miles_templates()
        rid = "mt" + str(int(__import__("time").time() * 1000))
        rec = {"id": rid, "label": label, "container": container, "filename": fname}
        data_idx.append(rec)
        _save_miles_templates(data_idx)
        return jsonify({"ok": True, "template": rec})


    @app.route("/miles_template/delete", methods=["POST"])
    def miles_template_delete():
        b = request.get_json(force=True) or {}
        rid = b.get("id", "")
        data_idx = _load_miles_templates()
        keep, removed = [], None
        for t in data_idx:
            if t.get("id") == rid:
                removed = t
            else:
                keep.append(t)
        if removed:
            try:
                fp = os.path.join(_miles_tpl_dir(), removed.get("filename", ""))
                if os.path.exists(fp):
                    os.remove(fp)
            except Exception:
                pass
        _save_miles_templates(keep)
        return jsonify({"ok": True})


    @app.route("/miles_template/preview/<rid>")
    def miles_template_preview(rid):
        """Serve a stored blank template image."""
        for t in _load_miles_templates():
            if t.get("id") == rid:
                return send_from_directory(_miles_tpl_dir(), t.get("filename", ""))
        return ("not found", 404)


    @app.route("/miles_template/save_zones", methods=["POST"])
    def miles_template_save_zones():
        """Persist the text-zone rectangles (from the visual editor) for a template.
        Body: {id, zones:{title:[x0,y0,x1,y1], grade:[...], choice:[...], application:[...]}}
        Coordinates are fractions 0..1 of the image."""
        b = request.get_json(force=True) or {}
        rid = b.get("id", "")
        zones = b.get("zones", {}) or {}
        erase = b.get("erase", []) or []
        data_idx = _load_miles_templates()
        found = False
        for t in data_idx:
            if t.get("id") == rid:
                t["zones"] = zones
                t["erase"] = erase
                found = True
                break
        if not found:
            return jsonify({"ok": False, "error": "template not found"}), 404
        _save_miles_templates(data_idx)
        return jsonify({"ok": True})


    @app.route("/miles_template/render", methods=["POST"])
    def miles_template_render():
        """Render text onto a chosen blank template and save the result as a main
        image for the given SKU (scoped to the active account).
        Body: {template_id, sku, spec:{title,subtitles,application,container,...}}"""
        try:
            import miles_template as _mt
        except Exception as e:
            return jsonify({"ok": False, "error": f"miles_template import failed: {e}"}), 500
        b = request.get_json(force=True) or {}
        tid = b.get("template_id", "")
        sku = b.get("sku", "") or "_misc"
        spec = b.get("spec", {}) or {}
        tpl = next((t for t in _load_miles_templates() if t.get("id") == tid), None)
        if not tpl:
            return jsonify({"ok": False, "error": "template not found — upload one first"}), 404
        blank_path = os.path.join(_miles_tpl_dir(), tpl.get("filename", ""))
        if not os.path.exists(blank_path):
            return jsonify({"ok": False, "error": "template file missing"}), 404
        spec.setdefault("container", tpl.get("container", "drum"))
        # Use the template's saved zones (from the visual editor) unless the caller
        # passed explicit ones. This is what makes placement pixel-exact per template.
        if not spec.get("zones") and tpl.get("zones"):
            spec["zones"] = tpl["zones"]
        if not spec.get("erase") and tpl.get("erase"):
            spec["erase"] = tpl["erase"]
        try:
            png = _mt.render_onto_blank(blank_path, spec)
        except Exception as e:
            return jsonify({"ok": False, "error": f"render failed: {e}"}), 500
        # save into the account-scoped media library for this SKU
        try:
            import time as _t
            # name the file by its REAL format (sniffed from bytes), not a hardcoded
            # .png -- Amazon rejects a .png whose bytes are actually JPEG.
            _ext = _sniff_image_ext(png, "png")
            fname = f"main_{int(_t.time())}.{_ext}"
            d = _sku_dir(sku)
            with open(os.path.join(d, fname), "wb") as f:
                f.write(png)
            aid = _state.get("active_account_id", "") or ""
            pfx = f"/media/_acct/{_safe_sku(aid)}" if aid else "/media"
            url = f"{pfx}/{_safe_sku(sku)}/{fname}"
            # Return a SMALL thumbnail for instant preview (not the full 2616px image
            # as base64 -- that bloats the response and the browser). The full image
            # is loaded from `url`.
            data_url = ""
            try:
                from PIL import Image as _PImg
                import io as _io
                thumb = _PImg.open(_io.BytesIO(png)).convert("RGB")
                thumb.thumbnail((520, 520))
                buf = _io.BytesIO()
                thumb.save(buf, format="JPEG", quality=82)
                data_url = "data:image/jpeg;base64," + _b64.b64encode(buf.getvalue()).decode("ascii")
            except Exception:
                data_url = ""
            return jsonify({"ok": True, "url": url, "data_url": data_url})
        except Exception as e:
            return jsonify({"ok": False, "error": f"save failed: {e}"}), 500
