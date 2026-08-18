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


# ---------------------------------------------------------------------------
# HOW THE FINISHED IMAGE IS BRANDED
# ---------------------------------------------------------------------------
#
#     "let the user chose the brand name for its item, whether he wants the
#      images to be unbranded (without brand name printed on it), or branded
#      (any name he can type or select from the registered trademarks"
#
# There were TWO rules before this and neither of them is what was asked for:
#
#     remove   erase whatever logo the photo has, blend the surface, leave it
#              clean. Right for a competitor's photo.
#     keep     reproduce the product's own logo faithfully. Right when the
#              photo is already the seller's own branded product.
#
# "Branded" is a THIRD thing: the photo is a plain supplier product, and it has
# to come out carrying the SELLER'S name. That is not the opposite of
# unbranded -- it is remove-then-apply, and doing it in one instruction matters
# because two passes over the same surface is how a ghost of the old logo
# survives under the new one.
#
# This is the app's actual business (CLAUDE.md Rule 1): brand new listings under
# the owner's own names, built from a competitor's product data. A generic photo
# becoming their own branded product is the whole point.

# The rules for what an image may SAY and how much product it may SHOW
# live in ONE module now, because /aplus/generate needs the same ones
# and a second copy is how the two paths drifted apart (Rule 12).
from domain.image_rules import (            # noqa: F401  (re-exported)
    _LIST_RULES, _IMAGE_TEXT_RULES, _PRESENCE_RULES, _SQUARE_CANVAS,
    _presence_rule,
)


BRAND_UNBRANDED = "unbranded"
BRAND_BRANDED = "branded"
BRAND_KEEP = "keep"

_RULE_REMOVE = (
    "LOGO RULE: If the product/packaging shows a BRAND LOGO, brand name, or store branding, "
    "REMOVE it cleanly — erase the logo and blend that area to match the surrounding product "
    "surface (same colour, material, finish), as if the logo was never there. Do NOT replace it "
    "with any other text or logo; leave it clean. If there is NO logo present, simply keep the "
    "product exactly as-is. Keep ALL other product details — shape, colours, proportions, "
    "material, and any NON-branding text (like size, directions) — unchanged."
)

_RULE_KEEP = (
    "LOGO RULE: KEEP the product's own brand logo and all its label text exactly as shown — this "
    "is the brand's real product. Reproduce the logo, brand name, and all text faithfully."
)


def _brand_rule(brand_mode, brand_name, remove_logo):
    """The logo instruction for this image, and the name actually applied.

    Returns (rule_text, brand_applied). `brand_applied` is "" for every mode
    that prints nothing, so a caller can say what happened without re-deriving
    it from the mode.

    `brand_mode` wins when it is set. When it is not, the older source/
    preserve_logo pair still decides -- every existing caller keeps working and
    nothing had to be migrated to add this.
    """
    mode = (brand_mode or "").lower()

    if mode == BRAND_BRANDED and brand_name:
        return (
            "BRANDING RULE: This product is being sold under the brand name "
            f"\"{brand_name}\". FIRST remove any existing brand logo, brand name or store "
            "branding from the product and packaging — erase it and blend the area into the "
            "surrounding surface so no trace, outline or shadow of the old marking remains. "
            f"THEN print \"{brand_name}\" onto the product or its packaging in the place the "
            "original branding occupied, as clean, professional, correctly spelled typography "
            "that follows the surface — its curve, perspective, lighting and material finish — "
            "so it reads as genuinely printed on the product rather than pasted over the photo. "
            "Keep the typography restrained and legible; do NOT invent a graphic logo, mascot or "
            "emblem, and do NOT add the name anywhere except where product branding belongs. "
            "Everything else — shape, colours, proportions, material, and all NON-branding text "
            "such as size or directions — stays exactly as in the reference.",
            brand_name,
        )

    if mode == BRAND_UNBRANDED:
        return (_RULE_REMOVE + " The finished image must carry NO brand name at all.", "")

    if mode == BRAND_KEEP:
        return (_RULE_KEEP, "")

    # No explicit mode: the original behaviour, decided by source/preserve_logo.
    return ((_RULE_REMOVE if remove_logo else _RULE_KEEP), "")


def register(app, *, CONFIG_PATH, _CREATIVE_STRATEGIES, _IMG_JOBS, _IMG_JOBS_LOCK, _SECONDARY_ROLES, _active_brand, _cfg, _imgresult, _load_img_instructions, _load_recipes, _new_img_job, _records, _run_img_jobs_bg, _safe_sku, _save_img_instructions, _sku_dir, _state, _write_attrs_for_sku, _ws, _APLUS_MODULES=None):
    """Attach the /genimage routes to the existing Flask app."""
    _APLUS_MODULES = _APLUS_MODULES or {}

    def _listing_for(b):
        """The listing's own content, for grounding the image in what the thing
        actually IS.

        The browser has the row on screen and sends it; where it did not, the
        SKU is enough to find it here. A photograph cannot say how big something
        is or what it is for -- with no scale a model renders a hand tool the
        size of a machine, convincingly -- and all of it was already in the
        listing, one lookup away.

        Returns None when nothing is known, so generation behaves exactly as it
        did before rather than failing.
        """
        given = (b or {}).get("listing")
        if isinstance(given, dict) and given:
            return given
        sku = str((b or {}).get("sku") or "").strip()
        if not sku:
            return None
        try:
            from domain import listing_lookup as _ll
            return _ll.row_by_sku(_ws(), sku) or None
        except Exception:
            return None

    def _by_product(j):
        """Progress per PRODUCT, not just a single running total.

        A batch of 8 images each for two products reported "0/16", which reads as
        one enormous job and says nothing about which product is where. The plan
        already carries the SKU for every planned image, so the breakdown costs
        nothing to produce and answers the question actually being asked: how far
        along is each item?
        """
        planned, done, failed = {}, {}, {}
        for p in (j.get("plan") or []):
            sku = str(p.get("sku") or "") or "(unassigned)"
            planned[sku] = planned.get(sku, 0) + 1
        for r in (j.get("results") or []):
            sku = str((r or {}).get("sku") or "") or "(unassigned)"
            done[sku] = done.get(sku, 0) + 1
            if not (r or {}).get("ok"):
                failed[sku] = failed.get(sku, 0) + 1
        return [{"sku": s, "total": planned[s], "done": done.get(s, 0),
                 "failed": failed.get(s, 0)}
                for s in sorted(planned)]

    @app.route("/genimage/jobs_active")
    def genimage_jobs_active():
        """List the caller's still-running image jobs so a floating status bar can
        show 'Generating X/Y' on ANY page, and survive navigation (jobs live
        server-side).

        Filtered by owner. It used to return EVERY running job on the server, so
        with two people signed in the owner's status bar reported their VA's
        image generation -- work they had not started and could not act on.
        Someone who can manage users still sees everything, deliberately: they
        are accountable for what it costs."""
        import time as _t
        from domain import job_owner as _jo
        # AND BY ACCOUNT. Owner alone was not enough: one person working across
        # several workspaces saw a Nestwell batch's progress bar while looking at
        # Jack Reacherd, describing work that belongs to a different business and
        # offering a Stop button that would end it.
        #
        # A job stamped before accounts were recorded has no account at all --
        # shown rather than hidden, because making existing work disappear from
        # its own progress bar is the worse failure.
        _acct = str(_state.get("active_account_id", "") or "")
        out, elsewhere = [], 0
        with _IMG_JOBS_LOCK:
            for jid, j in _IMG_JOBS.items():
                if j.get("status") != "running" or not _jo.may_see(j, CONFIG_PATH):
                    continue
                j_acct = str(j.get("account") or "")
                if j_acct and _acct and j_acct != _acct:
                    elsewhere += 1
                    continue
                out.append({"job": jid, "total": j.get("total", 0),
                            "done": j.get("done", 0), "label": j.get("label", ""),
                            "ts": j.get("ts", 0), "mine": _jo.mine_only(j),
                            "account": j_acct,
                            "products": _by_product(j)})
        out.sort(key=lambda x: x.get("ts", 0))
        # Reported, not hidden: "nothing running" and "nothing running HERE" are
        # different, and only one of them means you can safely close the laptop.
        return jsonify({"ok": True, "jobs": out, "elsewhere": elsewhere,
                        "account": _acct})

    @app.route("/genimage/stop_all", methods=["POST"])
    def genimage_stop_all():
        """Cancel every running image job AND retire it immediately.

        Setting only `cancel` was not enough: a worker reads that flag only BETWEEN
        images, so a worker hung inside one image -- or one that died on an unhandled
        exception -- never cleared its job. The job stayed "running" forever, the UI kept
        spinning, and Stop looked broken. Retiring the job here clears it at once; a live
        worker still sees `cancel` and exits cleanly at its next check.

        Stops only the CALLER'S jobs. "Stop all" means all of yours -- cancelling
        a colleague's half-finished batch from a button on your own screen is
        never what was meant, and a manager who can SEE another job still cannot
        end it from here.
        """
        from domain import job_owner as _jo
        # AND ONLY IN THIS ACCOUNT. "Stop all" pressed in Jack Reacherd must not
        # end a Nestwell batch: they are different businesses, the images cost
        # money, and the button is nowhere near the work it was killing. Scoped
        # to the account the same way the progress bar is, so what Stop ends is
        # exactly what the bar was showing.
        _acct = str(_state.get("active_account_id", "") or "")
        n, skipped = 0, 0
        with _IMG_JOBS_LOCK:
            for j in _IMG_JOBS.values():
                if j.get("status") != "running" or not _jo.mine_only(j):
                    continue
                j_acct = str(j.get("account") or "")
                if j_acct and _acct and j_acct != _acct:
                    skipped += 1
                    continue
                j["cancel"] = True
                j["status"] = "error"          # same shape the worker's own cancel path uses
                j["error"] = j.get("error") or "stopped by user"
                n += 1
        return jsonify({"ok": True, "stopped": n, "left_running_elsewhere": skipped})

    @app.route("/genimage/stop_job", methods=["POST"])
    def genimage_stop_job():
        """Cancel ONE job and retire it immediately (see genimage_stop_all)."""
        from domain import job_owner as _jo
        jid = (request.get_json(silent=True) or {}).get("job", "")
        with _IMG_JOBS_LOCK:
            j = _IMG_JOBS.get(jid)
            if j and not _jo.mine_only(j):
                return jsonify({"ok": False, "forbidden": True,
                                "error": "That job belongs to someone else."}), 403
            if j and j.get("status") == "running":
                j["cancel"] = True
                j["status"] = "error"
                j["error"] = j.get("error") or "stopped by user"
        return jsonify({"ok": True})

    @app.route("/genimage/job_status")
    def genimage_job_status():
        from domain import job_owner as _jo
        jid = request.args.get("job", "")
        with _IMG_JOBS_LOCK:
            j = _IMG_JOBS.get(jid)
            if not j:
                return jsonify({"ok": False, "error": "job not found"}), 404
            if not _jo.may_see(j, CONFIG_PATH):
                # Same answer as "not found" on purpose: whether a job id exists
                # is itself information about someone else's work.
                return jsonify({"ok": False, "error": "job not found"}), 404
            return jsonify({"ok": True, "status": j["status"], "total": j["total"],
                            "done": j["done"], "results": j["results"], "error": j["error"],
                            "plan": j.get("plan", []), "cancel": j.get("cancel", False),
                            "products": _by_product(j)})

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
        # ordered candidates (local/upload -> cache -> source URL); fall back to the single ref
        _ref = (b.get("product_images") if (ref_img != "__BRAND_REF__" and b.get("product_images")) else ref_img)
        res = ai_providers.run_pipeline(
            _cfg(), brief=brief, reference_image=_ref, product_title=title,
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
        # Ordered image sources: uploaded/local -> cached copy -> source URL. The resolver in
        # ai_providers tries them in order and uses the first that is a VALID image, so an
        # expired scrape URL falls through to a local/cached copy instead of failing.
        product_images = b.get("product_images") or ([product_image] if product_image else [])
        title = b.get("title", "")
        kind = b.get("kind", "main")          # 'main' | 'secondary'
        n = int(b.get("n", 3) or 3)
        tprov = b.get("text_provider") or None
        # per-run custom instructions for the strategist (NOT the saved standing
        # instructions) -- e.g. "don't show pets", "pour the medicine into the tub in
        # one image", "show the product in only some images". Optional, not persisted.
        custom_instr = (b.get("custom_instructions", "") or b.get("strategist_instructions", "") or "").strip()
        if not product_images:
            return jsonify({"ok": False, "error": "This product has no reference image."}), 400
        # read the product first so the strategist's ideas fit the real item
        spec = ""
        try:
            d = ai_providers.describe_product(_cfg(), product_images, title,
                                              provider=tprov,
                                              listing=_listing_for(b))
            if d.get("ok"):
                spec = d.get("description", "")
        except Exception:
            spec = ""
        # The listing goes to the STRATEGIST as well as to the vision step. The
        # vision step returns a paraphrase of the photograph, and the facts that
        # matter most for a set of images -- what is in the box, and how many --
        # do not survive it.
        res = ai_providers.strategize_images(_cfg(), image=product_images, product_title=title,
                                             product_spec=spec, n=n, kind=kind, provider=tprov,
                                             custom_instructions=custom_instr,
                                             listing=_listing_for(b))
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

        # HOW MUCH OF THE PRODUCT THIS CONCEPT NEEDS. The strategist decides it
        # per concept, because the right answer depends on the product -- a
        # bench needs scale against a person, a supplement needs its facts
        # panel. Defaults to hero, which is what every image used to be.
        presence = (b.get("product_presence", "") or "hero").strip().lower()
        if presence not in _PRESENCE_RULES:
            presence = "hero"

        # A product-free graphic needs no product photograph, and demanding one
        # would refuse exactly the concepts that break up a repetitive set.
        if not product_image and presence != "none":
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
                f"{concept}. Art direction: {art}. Premium, clean, one clear message.\n"
                + _presence_rule(presence)
            )
            image_kind = "secondary"
        # WHAT THE PICTURE IS ALLOWED TO CONTAIN.
        #
        # The brief above tells the model to reproduce the reference photo
        # EXACTLY -- which is right for the product's shape and colour, and wrong
        # for how many objects are in shot. Supplier photos are routinely a
        # bundle or a collage, so "reproduce it exactly" reproduces items that
        # are not being sold.
        #
        # Measured: a listing shipping four pieces produced a labelled flat-lay
        # of FIVE, because the reference showed five and the brief never said
        # otherwise -- and the callout lines then pointed at the wrong objects,
        # naming a strap as the carabiner. The concept text had it right; the
        # image step was the only one still working blind.
        #
        # Applies to every kind, and names no product: the same rule has to hold
        # for a grease gun, a table and a torch.
        try:
            _facts = ai_providers.listing_facts(_listing_for(b) or {}) or ""
        except Exception:
            _facts = ""
        if _facts:
            brief += (
                "\n\nWHAT THIS PRODUCT ACTUALLY IS -- from the listing itself. This "
                "OUTRANKS the reference photograph on contents and quantities:\n"
                + _facts
                + "\n\nSHOW ONLY WHAT IS SOLD. If the facts above list what is in the "
                  "box, show exactly those items and exactly those quantities -- no "
                  "extra piece, no spare, no duplicate, and nothing that appears in "
                  "the reference photo but is not on that list. Reference photos are "
                  "often a bundle, a multi-pack or a collage; copy the product's "
                  "appearance from it, never its object count. Where a quantity is "
                  "not stated, show one.\n"
                  "IF THE IMAGE HAS CALLOUTS OR LABELS: every label must name the "
                  "object its line actually touches, and only items on the list may "
                  "be labelled. A label pointing at the wrong part is worse than no "
                  "label."
            )

        # WHAT THE IMAGE IS ALLOWED TO SAY. This path had no such rule, and it
        # is the path the strategist uses -- so the only images with no guard on
        # their wording were the ones nobody wrote the wording for. It is what
        # produced "AMINO ACIDS / L ranteine" on a real ingredient panel.
        if kind in ("secondary", "aplus"):
            brief += _IMAGE_TEXT_RULES

        # standing user instructions remembered for every image
        _ci2 = (b.get("custom_instructions", "") or "").strip() or _load_img_instructions()
        if _ci2:
            brief = brief + "\n\nUSER STANDING INSTRUCTIONS (must always be followed): " + _ci2
        # For A+ concepts from the strategist, resize to the tier's standard module
        # dimensions (basic 970×600, premium 1464×600) so the output is upload-ready.
        _tw = _th = 0
        if kind == "aplus":
            _tier = (b.get("tier", "basic") or "basic").lower()
            # THE MODULE'S OWN SIZE, when the caller names one. Every
            # strategist-made A+ image used to come out at one flat size per
            # tier, so a three-across module and a full-width banner were
            # generated as the same shape and then squeezed into different
            # slots -- which is a large part of why the modules did not look
            # like they belonged on one page.
            _mod_id = (b.get("module") or "").strip()
            _mod = None
            if _mod_id:
                for _m in (_APLUS_MODULES.get(_tier) or []):
                    if _m.get("id") == _mod_id:
                        _mod = _m
                        break
            if _mod:
                _tw, _th = int(_mod["w"]), int(_mod["h"])
            elif _tier == "premium":
                _tw, _th = 1464, 600
            else:
                _tw, _th = 970, 600
        # For A+/secondary, anchor the REAL product as a SECOND reference too (same
        # technique the refine path uses) so the model is doubly pinned to the actual
        # product and is far less likely to invent a generic look-alike.
        #
        # EXCEPT when the concept is a product-free graphic. Handing the model a
        # photograph of the product while telling it not to draw the product is
        # a contradiction, and the picture wins over the sentence every time --
        # which is precisely how every slot ended up with another photograph of
        # the same bottle. The written spec still travels in the brief, so the
        # graphic can still quote the product's real numbers.
        _want_ref = presence != "none"
        _ref_img = product_image if _want_ref else ""
        _extra_ref = (product_image
                      if (_want_ref and kind in ("aplus", "secondary")) else "")
        res = ai_providers.run_pipeline(_cfg(), brief=brief, reference_image=_ref_img,
                                        product_title=title, text_provider=tprov, image_provider=iprov,
                                        image_kind=image_kind, strength=strength,
                                        target_w=_tw, target_h=_th, extra_reference=_extra_ref,
                                        # NO VISION READ FOR A PRODUCT-FREE IMAGE.
                                        #
                                        # The reading is injected as "EXACT PRODUCT SPEC
                                        # (reproduce the product PRECISELY from this)",
                                        # which is an instruction to DRAW THE PRODUCT --
                                        # and it beat the rule telling it not to.
                                        #
                                        # MEASURED: a concept tagged "none", whose own text
                                        # said "no product photo", came back as a large
                                        # bottle on a kitchen counter. Withholding the
                                        # reference image was not enough while the spec
                                        # block was still saying reproduce it.
                                        #
                                        # The facts a graphic needs -- the numbers, the
                                        # claims, the palette -- already travel in the
                                        # brief from the listing, which is the better
                                        # source for them anyway.
                                        read_product=_want_ref)
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
        # READ THE PRODUCT. This was off, and it is why refine felt like it knew
        # nothing about the item: with read_product=False the pipeline skips the
        # vision stage entirely, so no EXACT PRODUCT SPEC is ever folded into the
        # brief and the prompt AI rewrites the picture from the instruction alone.
        # The spec is read from the ORIGINAL product photo where we have one --
        # reading it from the generated image would describe a copy of a copy and
        # let every edit compound the last one's mistakes.
        res = ai_providers.run_pipeline(
            _cfg(), brief=brief, reference_image=base_image, product_title=title,
            text_provider=tprov, image_provider=iprov, image_kind=kind,
            read_product=True, spec_image=(orig_ref or base_image),
            strength=_strength, extra_reference=orig_ref)
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
        # HOW THE FINISHED IMAGE IS BRANDED. Asked for as:
        #   "let the user chose the brand name for its item, whether he wants
        #    the images to be unbranded (without brand name printed on it), or
        #    branded (any name he can type or select from the registered
        #    trademarks"
        # See _brand_rule below for what each mode does and why "branded" is a
        # THIRD rule rather than the opposite of "unbranded".
        brand_mode = (b.get("brand_mode", "") or "").lower()
        brand_name = (b.get("brand_name", "") or "").strip()
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
            d = ai_providers.describe_product(_cfg(), product_image, title,
                                              provider=tprov,
                                              listing=_listing_for(b))
            if d.get("ok"):
                spec = d.get("description", "")
        except Exception:
            spec = ""

        logo_rule, brand_applied = _brand_rule(brand_mode, brand_name, remove_logo)

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
        return _imgresult(res, extra={"source": source, "logo_removed": remove_logo,
                                      "brand_mode": brand_mode or ("keep" if not remove_logo
                                                                   else "unbranded"),
                                      "brand_applied": brand_applied})

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
        #
        # Each role now carries HOW MUCH PRODUCT it needs as well as its brief.
        # `detail` and `usecase` were offered on screen and did not exist here,
        # so choosing either silently produced a benefit infographic -- the two
        # roles most likely to break up a repetitive set were the two that
        # quietly did not work.
        _spec = _SECONDARY_ROLES.get(role) if role else None
        if _spec:
            brief = _spec["brief"]
            presence = _spec["present"]
        elif free_instruction:
            brief = free_instruction
            presence = "hero"        # free text: assume the product is wanted
        else:
            brief = _SECONDARY_ROLES["benefit"]["brief"]
            presence = _SECONDARY_ROLES["benefit"]["present"]

        # benefit restraint (the user wants clean, premium — 1-2 benefits max)
        if benefit_count <= 1:
            brief += " Highlight EXACTLY ONE benefit. Keep text to a single short headline."
        else:
            brief += " Highlight at most TWO benefits, each with a very short label. Do not overcrowd."
        if benefit_text:
            brief += f" The benefit(s) to highlight: {benefit_text}."
        brief += " " + _presence_rule(presence)

        # WHAT THE IMAGE IS ALLOWED TO SAY.
        #
        # The listing COPY is checked -- IP rules, compliance rules, a ban on
        # medical claims and unverifiable superlatives. Text drawn ONTO an image
        # went through none of that, and a secondary image is published copy in
        # every way that matters to Amazon.
        #
        # It matters because the model writes the words itself. Asked for a calm
        # lifestyle shot with "nothing clinical, nothing medical, no captions",
        # it returned a headline reading "Float Into Recovery" -- a health claim,
        # invented, on an image that would have gone straight to a live listing.
        # The same run captioned a dimensions image with packed measurements
        # (~28 cm, 16 cm) that appear in no source and are simply not known.
        #
        # Generic on purpose: this governs every product in every category, so
        # it constrains the KIND of statement rather than any particular claim.
        brief += _IMAGE_TEXT_RULES

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
            _pdesc = ai_providers.describe_product(_cfg(), product_image, title,
                                                   provider=tprov,
                                                   listing=_listing_for(b))
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
        # THE INSTRUCTION AND THE ATTACHMENT MUST AGREE. Telling the model "do
        # not show the product" while handing it the product photograph as a
        # reference is a contradiction, and the reference wins -- which is
        # exactly how every slot ended up with another picture of the bottle.
        # For a product-free graphic the reference is withheld and the model
        # works from the written spec instead.
        _ref = "" if presence == "none" else product_image
        gen = ai_providers.generate_image(_cfg(), detailed, reference_image=_ref, provider=iprov,
                                          strength=(_strength if _ref else None), image_size="4K")
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

        # Persist every generated image to the media library so this bulk path is as
        # safe as the Studio batch: without this, a live-listing set was returned to the
        # screen only (lost on reload) and a draft set lived only as a base64 blob in the
        # sheet. Saved under the first selected SKU's "secondary" folder, account-scoped.
        # Additive: what gets written to the row / submitted is unchanged.
        try:
            _aid0 = _state.get("active_account_id", "") or ""
            _first = _safe_sku(skus[0])
            _secdir = os.path.join(_sku_dir(skus[0]), "secondary")
            os.makedirs(_secdir, exist_ok=True)
            import time as _t0
            for _i, _img in enumerate(images, start=1):
                if not str(_img).startswith("data:"):
                    continue   # a remote URL: nothing local to write
                try:
                    _head, _, _raw = _img.partition(",")
                    _mime = (re.search(r"data:([^;]+)", _head) or [None, "image/png"])[1]
                    _ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(_mime, "png")
                    with open(os.path.join(_secdir, f"secondary_{int(_t0.time()*1000)}_{_i}.{_ext}"), "wb") as _f:
                        _f.write(_b64.b64decode(_raw))
                except Exception:
                    pass
        except Exception:
            pass   # library save is a safety net; never fail generation over it

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

