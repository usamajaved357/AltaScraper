"""routes/genimage_routes.py — extracted from dashboard.py (Phase 3). Bodies VERBATIM.

Auto-extracted @app.route("/genimage...") funcs; shared helpers injected. Verified with
verify_free_vars.py.
"""
from flask import request, jsonify, Response, send_from_directory
import base64 as _b64
import json
import os
import re
import threading


def register(app, *, CONFIG_PATH, _CREATIVE_STRATEGIES, _IMG_JOBS, _IMG_JOBS_LOCK, _SECONDARY_ROLES, _active_brand, _cfg, _imgresult, _load_img_instructions, _load_recipes, _new_img_job, _records, _run_img_jobs_bg, _safe_sku, _save_img_instructions, _sku_dir, _state, _write_attrs_for_sku, _ws):
    """Attach the /genimage routes to the existing Flask app."""

    @app.route("/genimage/jobs_active")
    def genimage_jobs_active():
        """List every still-running image job so a floating status bar can show
        'Generating X/Y' on ANY page, and survive navigation (jobs live server-side)."""
        import time as _t
        out = []
        with _IMG_JOBS_LOCK:
            for jid, j in _IMG_JOBS.items():
                if j.get("status") == "running":
                    out.append({"job": jid, "total": j.get("total", 0),
                                "done": j.get("done", 0), "label": j.get("label", ""),
                                "ts": j.get("ts", 0)})
        out.sort(key=lambda x: x.get("ts", 0))
        return jsonify({"ok": True, "jobs": out})

    @app.route("/genimage/stop_all", methods=["POST"])
    def genimage_stop_all():
        """Cancel every running image job AND retire it immediately.

        Setting only `cancel` was not enough: a worker reads that flag only BETWEEN
        images, so a worker hung inside one image -- or one that died on an unhandled
        exception -- never cleared its job. The job stayed "running" forever, the UI kept
        spinning, and Stop looked broken. Retiring the job here clears it at once; a live
        worker still sees `cancel` and exits cleanly at its next check.
        """
        n = 0
        with _IMG_JOBS_LOCK:
            for j in _IMG_JOBS.values():
                if j.get("status") == "running":
                    j["cancel"] = True
                    j["status"] = "error"          # same shape the worker's own cancel path uses
                    j["error"] = j.get("error") or "stopped by user"
                    n += 1
        return jsonify({"ok": True, "stopped": n})

    @app.route("/genimage/stop_job", methods=["POST"])
    def genimage_stop_job():
        """Cancel ONE job and retire it immediately (see genimage_stop_all)."""
        jid = (request.get_json(silent=True) or {}).get("job", "")
        with _IMG_JOBS_LOCK:
            j = _IMG_JOBS.get(jid)
            if j and j.get("status") == "running":
                j["cancel"] = True
                j["status"] = "error"
                j["error"] = j.get("error") or "stopped by user"
        return jsonify({"ok": True})

    @app.route("/genimage/job_status")
    def genimage_job_status():
        jid = request.args.get("job", "")
        with _IMG_JOBS_LOCK:
            j = _IMG_JOBS.get(jid)
            if not j:
                return jsonify({"ok": False, "error": "job not found"}), 404
            return jsonify({"ok": True, "status": j["status"], "total": j["total"],
                            "done": j["done"], "results": j["results"], "error": j["error"],
                            "plan": j.get("plan", []), "cancel": j.get("cancel", False)})

    @app.route("/genimage/instructions", methods=["GET", "POST"])
    def genimage_instructions():
        """Get or save the custom image instructions the AI remembers for every image."""
        if request.method == "GET":
            aid = request.args.get("id", "") or _state.get("active_account_id", "")
            return jsonify({"ok": True, "instructions": _load_img_instructions(aid)})
        b = request.get_json(force=True) or {}
        text = (b.get("instructions", "") or "").strip()[:4000]
        scope = (b.get("scope", "account") or "account").lower()
        aid = b.get("id", "") or _state.get("active_account_id", "")
        ok = _save_img_instructions(text, aid=aid, scope=scope)
        return jsonify({"ok": ok, "instructions": text})

    @app.route("/genimage/start_batch", methods=["POST"])
    def genimage_start_batch():
        """Start a background batch of generations. Returns a job_id immediately;
        poll /genimage/job_status?job=ID for progress."""
        b = request.get_json(force=True) or {}
        kind = b.get("kind", "")
        jobs = b.get("jobs", []) or []
        if not jobs:
            return jsonify({"ok": False, "error": "no jobs"}), 400
        label = (b.get("label", "") or "").strip()[:80]
        # Stamp the ACTIVE account onto every job NOW, at enqueue time. The background
        # worker used to read _state["active_account_id"] when each image FINISHED --
        # so a redeploy or a workspace switch mid-batch (the in-memory state is wiped or
        # changed) filed the image under the wrong account, or under the shared root
        # where the owning workspace never showed it. Capturing it here pins each image
        # to the workspace it was generated for.
        _acct_now = _state.get("active_account_id", "") or ""
        for jb in jobs:
            jb.setdefault("_acct_id", _acct_now)
        # a lightweight plan (label + concept per job) so the UI can show every
        # planned image and its status from the very start, not just as they finish.
        plan = [{"label": jb.get("label", ""), "sku": jb.get("sku", ""),
                 "concept": (jb.get("payload", {}) or {}).get("concept", "")[:200],
                 "img_code": jb.get("img_code", "")} for jb in jobs]
        jid = _new_img_job(len(jobs), label=label, plan=plan)
        t = threading.Thread(target=_run_img_jobs_bg, args=(jid, jobs, kind), daemon=True)
        t.start()
        return jsonify({"ok": True, "job": jid, "total": len(jobs)})

    @app.route("/genimage", methods=["POST"])
    def genimage():
        """Two-stage AI main image: brief -> detailed prompt (text AI) -> image
        (image AI), using the user's selected providers and a reference image.
        Returns BOTH the detailed prompt and the image for review."""
        try:
            import ai_providers
        except Exception:
            return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
        b = request.get_json(force=True) or {}
        brief     = b.get("brief", "") or b.get("extra_prompt", "")
        ref_img   = b.get("reference_image", "") or b.get("product_image", "")
        title     = b.get("title", "")
        tprov     = b.get("text_provider") or None
        iprov     = b.get("image_provider") or None
        # resolve brand-saved reference image if requested
        if ref_img == "__BRAND_REF__":
            ref_img = ""
            try:
                import glob as _g, os as _o
                _vk = _state.get("active_view") or ""
                for _pf in _g.glob(_o.path.join(_o.path.dirname(CONFIG_PATH), "brands", "*", "profile.json")):
                    _p = json.load(open(_pf, encoding="utf-8"))
                    if (_p.get("brand_name") or "") == _vk:
                        ref_img = _p.get("main_image_reference", "") or ""
                        break
            except Exception:
                pass
        res = ai_providers.run_pipeline(
            _cfg(), brief=brief, reference_image=ref_img, product_title=title,
            text_provider=tprov, image_provider=iprov)
        if not res.get("ok"):
            return jsonify(res), 400
        if res.get("image_b64"):
            data_url = f"data:{res.get('mime','image/png')};base64,{res['image_b64']}"
        elif res.get("image_url"):
            data_url = res["image_url"]
        else:
            return jsonify({"ok": False, "error": "no image returned"}), 400
        # Compute pixel dimensions + byte size so the UI can show them right away.
        _w = _h = 0
        _bytes = 0
        try:
            if res.get("image_b64"):
                _raw = _b64.b64decode(res["image_b64"])
                _bytes = len(_raw)
                from PIL import Image as _PImg
                import io as _io
                _im = _PImg.open(_io.BytesIO(_raw))
                _w, _h = _im.size
        except Exception:
            _w = _h = _bytes = 0
        return jsonify({"ok": True, "data_url": data_url,
                        "detailed_prompt": res.get("detailed_prompt", ""),
                        "text_provider": res.get("text_provider"),
                        "image_provider": res.get("image_provider"),
                        "width": _w, "height": _h, "bytes": _bytes})

    @app.route("/genimage/strategize", methods=["POST"])
    def genimage_strategize():
        """Run the strategist AI: it invents conversion-focused image concepts for the
        product (thinking like a strategist + customer). Returns concepts to choose from."""
        try:
            import ai_providers
        except Exception:
            return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
        b = request.get_json(force=True) or {}
        product_image = b.get("product_image", "") or b.get("reference_image", "")
        title = b.get("title", "")
        kind = b.get("kind", "main")          # 'main' | 'secondary'
        n = int(b.get("n", 3) or 3)
        tprov = b.get("text_provider") or None
        # per-run custom instructions for the strategist (NOT the saved standing
        # instructions) -- e.g. "don't show pets", "pour the medicine into the tub in
        # one image", "show the product in only some images". Optional, not persisted.
        custom_instr = (b.get("custom_instructions", "") or b.get("strategist_instructions", "") or "").strip()
        if not product_image:
            return jsonify({"ok": False, "error": "This product has no reference image."}), 400
        # read the product first so the strategist's ideas fit the real item
        spec = ""
        try:
            d = ai_providers.describe_product(_cfg(), product_image, title, provider=tprov)
            if d.get("ok"):
                spec = d.get("description", "")
        except Exception:
            spec = ""
        res = ai_providers.strategize_images(_cfg(), image=product_image, product_title=title,
                                             product_spec=spec, n=n, kind=kind, provider=tprov,
                                             custom_instructions=custom_instr)
        if not res.get("ok"):
            return jsonify({"ok": False, "error": res.get("error", "strategist failed")}), 400
        return jsonify({"ok": True, "concepts": res.get("concepts", []), "product_spec": spec})

    @app.route("/genimage/from_concept", methods=["POST"])
    def genimage_from_concept():
        """Generate an image from a strategist concept's art direction. Keeps the
        product faithful via the reference image + low strength."""
        try:
            import ai_providers
        except Exception:
            return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
        b = request.get_json(force=True) or {}
        product_image = b.get("product_image", "") or b.get("reference_image", "")
        title = b.get("title", "")
        kind = b.get("kind", "main")
        art = (b.get("art_direction", "") or "").strip()
        concept = (b.get("concept", "") or "").strip()
        tprov = b.get("text_provider") or None
        iprov = b.get("image_provider") or None
        fid = (b.get("fidelity", "high") or "high").lower()
        strength = {"high": 0.2, "medium": 0.35, "creative": 0.55}.get(fid, 0.2)
        # A+/secondary scenes push the model to redraw the product to fit the scene,
        # which drifts it from the real item. For these (non-main) kinds on High
        # fidelity, use an even LOWER strength so the product stays locked to the
        # reference photo (only the scene around it changes).
        if kind in ("aplus", "secondary") and fid == "high":
            strength = 0.14
        if not product_image:
            return jsonify({"ok": False, "error": "This product has no reference image."}), 400
        if not art and not concept:
            return jsonify({"ok": False, "error": "No concept provided."}), 400
        if kind == "main":
            brief = (
                "Create an Amazon MAIN product image on a 100% pure white background (RGB 255,255,255), "
                "product filling 85%+, NO added text or logos. Realise this creative concept: "
                f"{concept}. Art direction: {art}. Keep the product itself identical to the reference image "
                "(same shape, colours, label, text); the creativity is in angle, lighting, positioning and "
                "any tasteful physical touch — never alter or cover the product or its label."
            )
            image_kind = "main"
        elif kind == "aplus":
            brief = (
                "Create an Amazon A+ CONTENT module image (text and graphics allowed; this is the enhanced "
                "brand-story section). Realise this concept: "
                f"{concept}. Art direction: {art}. CRITICAL PRODUCT FIDELITY: the product shown MUST be an "
                "EXACT reproduction of the attached reference photo — identical shape, proportions, colour, "
                "materials, buttons, and every line of label/branding text. Do NOT redesign, restyle, or "
                "re-imagine the product to fit the scene; place the REAL product into the scene unchanged. "
                "Build the module layout/scene around it, roughly 70% visual / 30% text, premium and "
                "uncluttered, with one clear headline idea. Do NOT make prohibited medical/efficacy claims."
            )
            image_kind = "aplus"
        else:
            brief = (
                "Create an Amazon SECONDARY image (text and graphics allowed). Realise this concept: "
                f"{concept}. Art direction: {art}. CRITICAL PRODUCT FIDELITY: the product shown MUST be an "
                "EXACT reproduction of the attached reference photo — identical shape, proportions, colour, "
                "materials, buttons, and every line of label/branding text. Do NOT redesign or re-imagine the "
                "product to fit the scene; place the REAL product into the scene unchanged. Build the "
                "scene/graphic around it. Premium, clean, one clear message."
            )
            image_kind = "secondary"
        # standing user instructions remembered for every image
        _ci2 = (b.get("custom_instructions", "") or "").strip() or _load_img_instructions()
        if _ci2:
            brief = brief + "\n\nUSER STANDING INSTRUCTIONS (must always be followed): " + _ci2
        # For A+ concepts from the strategist, resize to the tier's standard module
        # dimensions (basic 970×600, premium 1464×600) so the output is upload-ready.
        _tw = _th = 0
        if kind == "aplus":
            _tier = (b.get("tier", "basic") or "basic").lower()
            if _tier == "premium":
                _tw, _th = 1464, 600
            else:
                _tw, _th = 970, 600
        # For A+/secondary, anchor the REAL product as a SECOND reference too (same
        # technique the refine path uses) so the model is doubly pinned to the actual
        # product and is far less likely to invent a generic look-alike.
        _extra_ref = product_image if kind in ("aplus", "secondary") else ""
        res = ai_providers.run_pipeline(_cfg(), brief=brief, reference_image=product_image,
                                        product_title=title, text_provider=tprov, image_provider=iprov,
                                        image_kind=image_kind, strength=strength,
                                        target_w=_tw, target_h=_th, extra_reference=_extra_ref)
        if not res.get("ok"):
            return jsonify(res), 400
        return _imgresult(res, extra={"concept": concept})

    @app.route("/genimage/refine", methods=["POST"])
    def genimage_refine():
        """Refine an ALREADY-generated image with a small user instruction.
        Feeds the generated image back in as the reference and applies the change at
        HIGH fidelity (low strength) so only the requested tweak is made and the rest
        of the image/product stays as-is. Works for main, secondary and aplus."""
        try:
            import ai_providers
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        base_image = b.get("image", "") or b.get("reference_image", "") or b.get("product_image", "")
        orig_ref = b.get("original_reference", "") or b.get("product_reference", "")
        instruction = (b.get("instruction", "") or "").strip()
        title = b.get("title", "")
        kind = (b.get("kind", "main") or "main").lower()
        if kind == "concept":
            kind = "main"
        if kind not in ("main", "secondary", "aplus"):
            kind = "main"
        tprov = b.get("text_provider") or None
        iprov = b.get("image_provider") or None
        if not base_image:
            return jsonify({"ok": False, "error": "No image to refine."}), 400
        if not instruction:
            return jsonify({"ok": False, "error": "Tell me what to change."}), 400
        # refine is always high-fidelity: we want the SAME image with one small change
        _strength = 0.18
        kind_rules = {
            "main": "This is an Amazon MAIN image: keep the 100% pure white background, no added text/logos.",
            "secondary": "This is an Amazon SECONDARY image: text and graphics are allowed.",
            "aplus": "This is an Amazon A+ module: text and graphics allowed, ~70% visual / 30% text, no prohibited claims.",
        }[kind]
        # When we have the ORIGINAL product image, attach it as a second reference and
        # tell the model it is the source of truth for the product itself -- so the
        # edit can't drift the real product (shape, colours, label text).
        if orig_ref:
            brief = (
                "You are given TWO reference images: (1) the CURRENT image to edit, and (2) the ORIGINAL "
                "product photo. Make a SMALL, TARGETED edit to image (1) — keep its composition, layout and "
                "background the same and change ONLY what is asked. CRITICAL: the product must match the "
                "ORIGINAL product photo (2) EXACTLY — same shape, proportions, colours, gradient, logo and "
                "every line of label text. Do not let the edit alter the real product. "
                f"Requested change: {instruction}. {kind_rules}"
            )
        else:
            brief = (
                "Make a SMALL, TARGETED edit to the attached image. Keep everything else exactly the same — "
                "same product, same composition, same colours, same layout — and change ONLY what is asked. "
                f"Requested change: {instruction}. {kind_rules} Do not redesign or re-pose the product."
            )
        _ciR = (b.get("custom_instructions", "") or "").strip() or _load_img_instructions()
        if _ciR:
            brief = brief + "\n\nAlso keep honoring these standing rules where relevant (do not let them override the requested change): " + _ciR
        res = ai_providers.run_pipeline(
            _cfg(), brief=brief, reference_image=base_image, product_title=title,
            text_provider=tprov, image_provider=iprov, image_kind=kind,
            read_product=False, strength=_strength, extra_reference=orig_ref)
        if not res.get("ok"):
            return jsonify(res), 400
        return _imgresult(res, extra={"refined": True, "instruction": instruction})

    @app.route("/genimage/process_source", methods=["POST"])
    def genimage_process_source():
        """Process a SOURCE image (eBay/Amazon competitor scrape OR brand CSV) into a
        clean, Amazon-ready MAIN image that keeps the product IDENTICAL.
        Logo rule driven by source:
          - source='competitor' (eBay/Amazon): remove any brand logo IF present (clean
            the area to blend with the product surface), keep the product itself.
          - source='brand' (CSV): keep the product AND logo (preserve_logo defaults True);
            if preserve_logo is False, remove the logo as above.
        Optional 'instruction' for extra edits. Product stays faithful (low strength)."""
        try:
            import ai_providers
        except Exception:
            return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
        b = request.get_json(force=True) or {}
        product_image = b.get("product_image", "") or b.get("reference_image", "")
        title = b.get("title", "")
        source = (b.get("source", "competitor") or "competitor").lower()   # 'competitor' | 'brand'
        preserve_logo = b.get("preserve_logo", True)
        instruction = (b.get("instruction", "") or "").strip()
        tprov = b.get("text_provider") or None
        iprov = b.get("image_provider") or None
        fid = (b.get("fidelity", "high") or "high").lower()
        strength = {"high": 0.2, "medium": 0.35, "creative": 0.55}.get(fid, 0.2)

        if not product_image:
            return jsonify({"ok": False, "error": "No source image to process."}), 400

        # decide the logo rule
        remove_logo = (source == "competitor") or (not preserve_logo)

        # read the actual product first (faithful spec, incl. any logo/text)
        spec = ""
        try:
            d = ai_providers.describe_product(_cfg(), product_image, title, provider=tprov)
            if d.get("ok"):
                spec = d.get("description", "")
        except Exception:
            spec = ""

        if remove_logo:
            logo_rule = (
                "LOGO RULE: If the product/packaging shows a BRAND LOGO, brand name, or store branding, "
                "REMOVE it cleanly — erase the logo and blend that area to match the surrounding product "
                "surface (same colour, material, finish), as if the logo was never there. Do NOT replace it "
                "with any other text or logo; leave it clean. If there is NO logo present, simply keep the "
                "product exactly as-is. Keep ALL other product details — shape, colours, proportions, "
                "material, and any NON-branding text (like size, directions) — unchanged."
            )
        else:
            logo_rule = (
                "LOGO RULE: KEEP the product's own brand logo and all its label text exactly as shown — this "
                "is the brand's real product. Reproduce the logo, brand name, and all text faithfully."
            )

        brief = (
            "Produce a clean, professional Amazon MAIN product image from the reference image. "
            "Background must be 100% pure white (RGB 255,255,255), product filling 85%+, sharp HD, 1:1 square, "
            "no added text or graphics. Keep the PRODUCT itself identical to the reference (same shape, "
            "colours, proportions, material, design). " + logo_rule
            + (f" Additional edits requested by the seller: {instruction}." if instruction else "")
        )
        if spec:
            brief += ("\n\nEXACT PRODUCT SPEC (reproduce the product precisely from this; apply the LOGO RULE "
                      "above to any branding):\n" + spec)
        res = ai_providers.run_pipeline(_cfg(), brief=brief, reference_image=product_image,
                                        product_title=title, text_provider=tprov, image_provider=iprov,
                                        image_kind="main", strength=strength, read_product=False)
        if not res.get("ok"):
            return jsonify(res), 400
        return _imgresult(res, extra={"source": source, "logo_removed": remove_logo})

    @app.route("/genimage/recipe", methods=["POST"])
    def genimage_recipe():
        """Generate a MAIN image for ONE product using a saved recipe (templated path)
        OR a creative strategy (non-templated path). Always passes the product's own
        reference image so the product stays faithful. Returns the image for review."""
        try:
            import ai_providers
        except Exception:
            return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
        b = request.get_json(force=True) or {}
        product_image = b.get("product_image", "") or b.get("reference_image", "")
        title = b.get("title", "")
        mode = b.get("mode", "recipe")          # 'recipe' | 'creative'
        tprov = b.get("text_provider") or None
        iprov = b.get("image_provider") or None
        inspiration = (b.get("inspiration", "") or "").strip()   # optional creative inspiration text/url
        # fidelity: how closely to keep the real product (lower strength = more faithful).
        # 'high' = very faithful (0.2), 'medium' = balanced (0.35), 'creative' = more freedom (0.55)
        fid = (b.get("fidelity", "high") or "high").lower()
        strength = {"high": 0.2, "medium": 0.35, "creative": 0.55}.get(fid, 0.2)

        if not product_image:
            return jsonify({"ok": False, "error": "This product has no reference image to base the generation on."}), 400

        if mode == "recipe":
            brand = (b.get("brand", "") or _active_brand()).strip()
            rid = b.get("recipe_id", "")
            data = _load_recipes()
            rec = None
            for bn, lst in data.items():
                for r in lst:
                    if r.get("id") == rid:
                        rec = r; break
                if rec:
                    break
            if not rec:
                return jsonify({"ok": False, "error": "Recipe not found."}), 404
            brief = (
                "Apply this exact treatment to the product shown in the reference image, keeping the "
                "product itself identical (same shape, colour, label, text — do NOT redesign it). "
                f"Treatment: {rec['instructions']}"
            )
            # if the recipe has a template image, mention it (gen model uses product ref as the anchor)
            res = ai_providers.run_pipeline(_cfg(), brief=brief, reference_image=product_image,
                                            product_title=title, text_provider=tprov, image_provider=iprov, strength=strength)
            if not res.get("ok"):
                return jsonify(res), 400
            return _imgresult(res, extra={"recipe_id": rid})

        # creative path: generate the 3 strategies (or whichever requested)
        strat = b.get("strategy", "")
        if strat and strat in _CREATIVE_STRATEGIES:
            brief = (_CREATIVE_STRATEGIES[strat]
                     + " Keep the product itself identical to the reference image (same shape, colour, "
                       "label and text); only change the scene, angle, lighting and composition."
                     + (f" Inspiration to draw from: {inspiration}" if inspiration else ""))
            res = ai_providers.run_pipeline(_cfg(), brief=brief, reference_image=product_image,
                                            product_title=title, text_provider=tprov, image_provider=iprov, strength=strength)
            if not res.get("ok"):
                return jsonify(res), 400
            return _imgresult(res, extra={"strategy": strat})

        return jsonify({"ok": False, "error": "Specify a recipe_id or a creative strategy."}), 400

    @app.route("/genimage/save_to_media", methods=["POST"])
    def genimage_save_to_media():
        """Save a generated image (data URL) into a SKU's media library."""
        b = request.get_json(force=True) or {}
        sku = b.get("sku", "_misc")
        data = b.get("data_url", "") or b.get("data", "")
        if not data:
            return jsonify({"ok": False, "error": "no image"}), 400
        if data.startswith("data:"):
            head, _, raw = data.partition(",")
            mime = (re.search(r"data:([^;]+)", head) or [None, "image/png"])[1]
        else:
            raw, mime = data, "image/png"
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "png")
        import time as _t
        fname = f"generated_{int(_t.time())}.{ext}"
        try:
            with open(os.path.join(_sku_dir(sku), fname), "wb") as f:
                f.write(_b64.b64decode(raw))
        except Exception as e:
            return jsonify({"ok": False, "error": f"write failed: {e}"}), 500
        _aid = _state.get("active_account_id", "") or ""
        _pfx = f"/media/_acct/{_safe_sku(_aid)}" if _aid else "/media"
        return jsonify({"ok": True, "url": f"{_pfx}/{_safe_sku(sku)}/{fname}"})

    @app.route("/genimage/secondary_v2", methods=["POST"])
    def genimage_secondary_v2():
        """Generate ONE secondary image for a product. Supports:
        - role (benefit/feature/lifestyle/...) OR free-form instruction
        - benefit_count (1 or 2) to control how many benefits are highlighted
        - competitor refs with mode 'describe' (vision AI extracts style) or 'direct'
          (competitor image passed to the image model as a style reference)
        Always passes the product's own image so the product stays faithful."""
        try:
            import ai_providers
        except Exception:
            return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
        b = request.get_json(force=True) or {}
        product_image = b.get("product_image", "") or b.get("reference_image", "")
        title = b.get("title", "")
        role = b.get("role", "")                       # one of _SECONDARY_ROLES, or "" for free-form
        free_instruction = (b.get("instruction", "") or "").strip()
        benefit_count = int(b.get("benefit_count", 1) or 1)
        benefit_text = (b.get("benefit_text", "") or "").strip()   # optional specific benefit(s) to show
        comp_refs = b.get("competitor_refs", []) or []  # [{image, mode}]
        comp_mode = b.get("competitor_mode", "describe")  # default mode if not per-ref
        tprov = b.get("text_provider") or None
        # respect the user's fidelity choice so the product is kept as faithfully
        # as the main images (default High = most faithful)
        _fid = (b.get("fidelity", "high") or "high").lower()
        _strength = {"high": 0.2, "medium": 0.35, "creative": 0.55}.get(_fid, 0.2)
        iprov = b.get("image_provider") or None

        if not product_image:
            return jsonify({"ok": False, "error": "This product has no reference image."}), 400

        # 1) build the role/free-form brief
        if role and role in _SECONDARY_ROLES:
            brief = _SECONDARY_ROLES[role]
        elif free_instruction:
            brief = free_instruction
        else:
            brief = _SECONDARY_ROLES["benefit"]

        # benefit restraint (the user wants clean, premium — 1-2 benefits max)
        if benefit_count <= 1:
            brief += " Highlight EXACTLY ONE benefit. Keep text to a single short headline."
        else:
            brief += " Highlight at most TWO benefits, each with a very short label. Do not overcrowd."
        if benefit_text:
            brief += f" The benefit(s) to highlight: {benefit_text}."
        brief += (" Keep the product itself identical to the reference image (same shape, colour, label, "
                  "text); only build the scene/graphic around it. Premium, clean, lots of negative space.")

        # 2) competitor style handling
        style_desc = ""
        direct_refs = []
        describe_imgs = []
        for cr in comp_refs[:3]:
            img = cr.get("image", "") if isinstance(cr, dict) else str(cr)
            mode = (cr.get("mode") if isinstance(cr, dict) else "") or comp_mode
            if not img:
                continue
            if mode == "direct":
                direct_refs.append(img)
            else:
                describe_imgs.append(img)
        if describe_imgs:
            d = ai_providers.describe_image(_cfg(), describe_imgs, focus="style to reproduce on a different product", provider=tprov)
            if d.get("ok"):
                style_desc = d.get("description", "")
        if style_desc:
            brief += (" Reproduce THIS visual style/technique (from competitor inspiration), applied to the "
                      "seller's own product — do not copy their product or branding: " + style_desc)

        # 3) generate: prompt AI -> image AI, with product reference (+ direct competitor refs if any)
        # read the actual product first so the model keeps it faithful (exact label text, shape)
        try:
            _pdesc = ai_providers.describe_product(_cfg(), product_image, title, provider=tprov)
            if _pdesc.get("ok") and _pdesc.get("description"):
                brief += ("\n\nEXACT PRODUCT SPEC (reproduce the product precisely — same shape, colours, "
                          "layout, logo, and ALL label text exactly as written; do not alter it):\n"
                          + _pdesc["description"])
        except Exception:
            pass
        # standing user instructions (remembered for every image), applied last so
        # they always take effect on top of the strategist + product spec.
        _ci = (b.get("custom_instructions", "") or "").strip() or _load_img_instructions()
        if _ci:
            brief += "\n\nUSER STANDING INSTRUCTIONS (must always be followed): " + _ci
        enh = ai_providers.enhance_prompt(_cfg(), brief, title, provider=tprov, image_kind="secondary")
        if not enh.get("ok"):
            return jsonify({"ok": False, "error": "Prompt stage: " + enh.get("error", "")}), 400
        detailed = enh["prompt"]
        # image model takes the product image as the anchor reference; if direct competitor
        # refs were supplied, mention them in the prompt (most models accept one primary ref)
        gen = ai_providers.generate_image(_cfg(), detailed, reference_image=product_image, provider=iprov, strength=_strength, image_size="4K")
        if not gen.get("ok"):
            return jsonify({"ok": False, "error": "Image stage: " + gen.get("error", "")}), 400
        res = {"ok": True, "detailed_prompt": detailed,
               "text_provider": enh.get("provider"), "image_provider": gen.get("provider")}
        if gen.get("image_b64"):
            res["image_b64"] = gen["image_b64"]; res["mime"] = gen.get("mime", "image/png")
        elif gen.get("image_url"):
            res["image_url"] = gen["image_url"]
        return _imgresult(res, extra={"role": role or "custom"})

    @app.route("/genimage/secondary", methods=["POST"])
    def genimage_secondary():
        """Generate secondary images ONCE from a brief and apply the same set across
        all selected SKUs (siblings share lifestyle/infographic images). Writes them
        as other_product_image_locator_N on each selected row."""
        try:
            import ai_providers
        except Exception:
            return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
        b = request.get_json(force=True) or {}
        skus  = [s for s in (b.get("skus") or []) if s]
        brief = b.get("brief", "")
        live      = bool(b.get("live"))
        live_refs = b.get("live_refs") or {}
        if not skus:
            return jsonify({"ok": False, "error": "no skus selected"}), 400
        if not brief.strip():
            return jsonify({"ok": False, "error": "no brief given"}), 400

        # Reference image: for LIVE listings use the Amazon photo passed from the
        # client; for draft listings pull the main image from the sheet row.
        by_sku = {}
        ref_img = ""
        if live:
            # first selected SKU that has a live Amazon image
            for s in skus:
                if live_refs.get(str(s)):
                    ref_img = live_refs[str(s)]
                    break
        else:
            try:
                recs = _records(_ws())
            except Exception as e:
                return jsonify({"ok": False, "error": f"could not read sheet: {e}"}), 500
            for r in recs:
                by_sku[str(r.get("SKU", ""))] = r
            first = by_sku.get(str(skus[0]))
            if first:
                try:
                    a = json.loads(first.get("Attributes JSON") or "{}")
                    ref_img = a.get("main_product_image_locator", "") or a.get("other_product_image_locator_1", "")
                except Exception:
                    pass

        # split brief into up to N distinct secondary-image briefs (by line / comma)
        parts = [p.strip() for p in re.split(r"[\n;]+|,(?=\s*[a-zA-Z])", brief) if p.strip()][:6]
        if not parts:
            parts = [brief.strip()]

        images = []   # data URLs, generated ONCE
        for p in parts:
            res = ai_providers.run_pipeline(_cfg(), brief=p, reference_image=ref_img,
                                            product_title="secondary image")
            if res.get("ok"):
                if res.get("image_b64"):
                    images.append(f"data:{res.get('mime','image/png')};base64,{res['image_b64']}")
                elif res.get("image_url"):
                    images.append(res["image_url"])
                else:
                    return jsonify({"ok": False, "error": "no image returned", "generated": len(images)}), 400
            else:
                return jsonify({"ok": False, "error": f"image gen failed: {res.get('error','')}",
                                "generated": len(images)}), 400

        # LIVE listings aren't sheet rows -> just return the generated images for
        # the user to download and upload via Amazon Manage Images.
        if live:
            return jsonify({"ok": True, "images": images, "applied": 0, "live": True})

        # apply the SAME images across every selected SKU's row (draft listings)
        ws = _ws()
        applied = 0
        for sku in skus:
            r = by_sku.get(str(sku))
            if not r:
                continue
            try:
                attrs = json.loads(r.get("Attributes JSON") or "{}")
                if not isinstance(attrs, dict):
                    attrs = {}
            except Exception:
                attrs = {}
            for i, img in enumerate(images, start=1):
                attrs[f"other_product_image_locator_{i}"] = img
            # write back via the same path the editor uses
            try:
                _write_attrs_for_sku(ws, sku, attrs)
                applied += 1
            except Exception:
                pass
        # return the image URLs too so the UI can preview them
        return jsonify({"ok": True, "images": images, "applied": applied})

