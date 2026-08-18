"""routes/aplus_routes.py — Amazon A+ Content endpoints, extracted from dashboard.py (Phase 3).

register(app, ...) injection pattern; bodies VERBATIM (CLAUDE.md §10). Injected:
_APLUS_MODULES (the module catalog dict), _cfg, _load_img_instructions, _imgresult.
ai_providers and anthropic are imported inline in the bodies.

Routes: GET /aplus/modules, POST /aplus/generate
"""
import re

from flask import request, jsonify


def register(app, *, _APLUS_MODULES, _cfg, _load_img_instructions, _imgresult):
    """Attach the /aplus/* routes to the existing Flask app."""

    @app.route("/aplus/modules", methods=["GET"])
    def aplus_modules():
        """The A+ module catalog (basic + premium) with exact dimensions.

        A module carrying a `mobile` size can be generated twice -- once for
        each screen -- and the mobile one is COMPOSED for a phone rather than
        being the desktop asset scaled down.
        """
        try:
            import dashboard as _dash
            note = getattr(_dash, "APLUS_MOBILE_IS_ASSUMED", "")
        except Exception:
            note = ""
        return jsonify({"ok": True, "modules": _APLUS_MODULES,
                        # Said out loud rather than left to be discovered: the
                        # desktop figures are Amazon's published ones, the
                        # mobile default is this app's (CLAUDE.md Rule 4).
                        "mobile_size_note": note})


    @app.route("/aplus/generate", methods=["POST"])
    def aplus_generate():
        """Generate ONE A+ Content module image at its exact Amazon dimensions, plus
        the suggested module text (70% visual / 30% text). Always passes the product
        reference image. Body: {product_image, title, tier, module_id, instruction,
        benefit_text}."""
        try:
            import ai_providers
        except Exception:
            return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
        b = request.get_json(force=True) or {}
        product_image = b.get("product_image", "") or b.get("reference_image", "")
        title = b.get("title", "")
        tier = b.get("tier", "basic")
        module_id = b.get("module_id", "")
        instruction = (b.get("instruction", "") or "").strip()
        benefit_text = (b.get("benefit_text", "") or "").strip()
        tprov = b.get("text_provider") or None
        # respect the user's fidelity choice so the product is kept as faithfully
        # as the main images (default High = most faithful)
        _fid = (b.get("fidelity", "high") or "high").lower()
        _strength = {"high": 0.2, "medium": 0.35, "creative": 0.55}.get(_fid, 0.2)
        iprov = b.get("image_provider") or None

        if not product_image:
            return jsonify({"ok": False, "error": "This product has no reference image."}), 400
        mod = None
        for m in _APLUS_MODULES.get(tier, []):
            if m["id"] == module_id:
                mod = m; break
        if not mod:
            return jsonify({"ok": False, "error": "Unknown A+ module."}), 404

        # WHICH SCREEN THIS ONE IS FOR. A module that declares a mobile size can
        # be generated twice, and the mobile one is COMPOSED for a phone rather
        # than being the desktop asset squeezed into a narrow column -- a
        # headline sized to read across 1464px is a few pixels tall on a phone.
        viewport = (b.get("viewport", "desktop") or "desktop").lower()
        _mob = mod.get("mobile") or {}
        if viewport == "mobile" and _mob:
            _w, _h = int(_mob["w"]), int(_mob["h"])
        else:
            viewport = "desktop"
            _w, _h = int(mod["w"]), int(mod["h"])

        brief = (
            f"Design an Amazon A+ Content module: '{mod['name']}'. {mod['desc']} "
            f"EXACT output size: {_w}x{_h} pixels (aspect ratio {_w}:{_h}). "
            "Follow the 70% visual / 30% text rule, premium and clean. "
            + ("THIS IS THE MOBILE RENDITION, read on a phone in a narrow "
               "column. It carries the SAME message as the desktop version and "
               "is composed differently for it: far larger type, fewer words, "
               "elements STACKED vertically rather than side by side, and the "
               "subject bigger in frame. Do not lay it out wide and expect it "
               "to be legible small. "
               if viewport == "mobile" else
               "Text must still be readable when this is scaled down on a "
               "phone. ")
            + (f"Seller's instruction: {instruction}. " if instruction else "")
            + (f"Benefit(s) to feature: {benefit_text}. " if benefit_text else "")
        )
        # read the actual product first so A+ keeps it faithful
        # Multi-image modules (three/four small images) are the ones that drift: asking
        # the model to render the product several times at small size makes it invent a
        # generic stand-in. For these, lower the strength hard and instruct it to reuse
        # the SAME exact product in every sub-image rather than redrawing variations.
        _multi_image_mods = {"three_image_text", "four_quadrant"}
        if _fid == "high":
            _strength = 0.12 if module_id in _multi_image_mods else 0.16
        if module_id in _multi_image_mods:
            brief += (
                " CRITICAL: every sub-image in this module must show the SAME identical product from the "
                "attached reference — do NOT invent variations or a generic look-alike; reuse the exact same "
                "product (same shape, colour, proportions, label text), only changing angle or context "
                "between the small images."
            )
        # THE LISTING'S OWN WORDS GO WITH THE PHOTOGRAPH.
        # A photograph cannot say how big something is or what it is for, and
        # those are the two ways a generated image is most often wrong. The
        # browser already has the row on screen, so it sends it.
        _listing = b.get("listing") or None
        try:
            _pdesc = ai_providers.describe_product(_cfg(), product_image, title,
                                                   provider=tprov, listing=_listing)
            if _pdesc.get("ok") and _pdesc.get("description"):
                brief += ("\n\nEXACT PRODUCT SPEC (reproduce the product precisely — same shape, colours, "
                          "layout, logo, and ALL label text exactly as written):\n" + _pdesc["description"])
        except Exception:
            pass
        _ci3 = (b.get("custom_instructions", "") or "").strip() or _load_img_instructions()
        if _ci3:
            brief = brief + "\n\nUSER STANDING INSTRUCTIONS (must always be followed): " + _ci3
        enh = ai_providers.enhance_prompt(_cfg(), brief, title, provider=tprov, image_kind="aplus")
        if not enh.get("ok"):
            return jsonify({"ok": False, "error": "Prompt stage: " + enh.get("error", "")}), 400
        # _w/_h, not mod["w"]/mod["h"] -- these three lines decide the shape that
        # is asked for and the shape it is cut to, so a mobile rendition built
        # from the desktop numbers would be the desktop image again.
        detailed = enh["prompt"] + (
            f"\n\nIMPORTANT: output the image at exactly {_w}x{_h} pixels."
            "\nKeep every word and every important edge inside the middle 88% "
            "of the frame. Text against the edge is how one of these gets "
            "ruined.")
        _ar = ai_providers._closest_aspect_ratio(_w, _h)
        gen = ai_providers.generate_image(_cfg(), detailed, reference_image=product_image,
                                          provider=iprov, strength=_strength,
                                          aspect_ratio=_ar, image_size="4K",
                                          extra_reference=product_image)
        if not gen.get("ok"):
            return jsonify({"ok": False, "error": "Image stage: " + gen.get("error", "")}), 400
        # EXACT DIMENSIONS. The model returns a roughly square image whatever it
        # is asked for, so this is what makes it uploadable. It no longer
        # cover-crops a large mismatch -- doing that discarded 59% of the height
        # on a premium banner and cut every headline in half.
        if gen.get("image_b64"):
            try:
                gen["image_b64"] = ai_providers._resize_to_exact(gen["image_b64"], _w, _h)
                gen["mime"] = "image/png"
                gen["resized_to"] = f"{_w}x{_h}"
                gen["viewport"] = viewport
            except Exception as _re:
                gen["resize_error"] = str(_re)[:120]

        # also draft the module copy (separate from the image, so text is reliable)
        copy_text = ""
        try:
            key = (_cfg().get("anthropic_api_key") or "").strip()
            if key:
                import anthropic
                client = anthropic.Anthropic(api_key=key)
                msg = client.messages.create(
                    model="claude-sonnet-4-5", max_tokens=400,
                    system=("Write concise Amazon A+ module copy: one short headline (<=8 words) and "
                            "2-3 short benefit-led sentences. No claims like 'best seller', '#1', pricing, "
                            "or external links. Return JSON {\"headline\":\"\",\"body\":\"\"} only."),
                    messages=[{"role": "user", "content": f"Product: {title}\nModule: {mod['name']}\n"
                               f"Benefit(s): {benefit_text or '(infer sensible benefits)'}"}])
                raw = "".join(getattr(x, "text", "") for x in msg.content).strip()
                raw = re.sub(r"^```json|```$", "", raw).strip()
                copy_text = raw
        except Exception:
            copy_text = ""

        res = {"ok": True, "detailed_prompt": detailed,
               "text_provider": enh.get("provider"), "image_provider": gen.get("provider"),
               "module": mod, "copy": copy_text}
        if gen.get("image_b64"):
            res["image_b64"] = gen["image_b64"]; res["mime"] = gen.get("mime", "image/png")
        elif gen.get("image_url"):
            res["image_url"] = gen["image_url"]
        return _imgresult(res, extra={"module_id": module_id, "module": mod, "copy": copy_text})
