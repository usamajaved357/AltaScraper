"""domain/image_jobs.py -- the image generation jobs: queueing, workers, progress, instructions.

Moved out of dashboard.py (Milestone 4, owner-approved 28 Sep 2026: "pass the
required shared app state explicitly to the background-job modules").
The job code is unchanged except that each name it read from the app
module is now read as _app.<name>: a live lookup on the RUNNING app
module, handed in once by bind(), so a job still sees the current
workspace, records, config path -- and anything a test replaces -- at
the moment it runs. This module never imports dashboard (that would
load a second copy of the app).
"""

import base64 as _b64
from api.google_drive import (_DRIVE_FOLDER_CACHE, _drive_folder_id_from_url, _drive_get_or_create_subfolder, _drive_direct_url, _drive_make_public)  # moved (Milestone 4)
from domain.image_bytes import (_fetch_image_b64, _sniff_image_ext, _to_jpeg_bytes, _imgresult)  # moved (Milestone 4)
import json
import os
import re

_app = None


def bind(app_module):
    """Hand this module the running app module (dashboard.py does, once)."""
    global _app
    _app = app_module


def _sku_dir(sku):
    d = os.path.join(_app._account_media_root(), _app._safe_sku(sku))
    os.makedirs(d, exist_ok=True)
    return d


def _new_img_job(total, label="", plan=None):
    import time as _t, uuid as _u
    from domain.request_account import current as _rqa_current
    jid = _u.uuid4().hex[:12]
    with _app._IMG_JOBS_LOCK:
        from domain import job_owner as _jo
        _app._IMG_JOBS[jid] = _jo.stamp(
            {"status": "running", "total": total, "done": 0,
             "results": [], "error": "", "ts": _t.time(),
             "cancel": False, "label": label, "plan": plan or [],
             # WHICH ACCOUNT THIS BATCH BELONGS TO. Jobs carried an owner but no
             # account, so one person's batches were indistinguishable across
             # workspaces: the progress bar for a Nestwell batch appeared while
             # you were in Jack Reacherd, and "Stop all" on that screen ended it.
             # Accounts are independent; their jobs and their Stop buttons have
             # to be too. The REQUEST's account (the tab's), the same one its
             # images are filed under -- labelled with the server's open one,
             # Stop in the other tab ended it (two-tab review).
             "account": _rqa_current(_app._state)})
    try:
        with _app._IMG_JOBS_LOCK:
            for k in [k for k, v in _app._IMG_JOBS.items() if _t.time() - v.get("ts", 0) > 3600]:
                _app._IMG_JOBS.pop(k, None)
    except Exception:
        pass
    return jid


def _job_push(jid, result):
    with _app._IMG_JOBS_LOCK:
        j = _app._IMG_JOBS.get(jid)
        if j:
            j["results"].append(result)
            j["done"] = len(j["results"])


def _job_finish(jid, error=""):
    with _app._IMG_JOBS_LOCK:
        j = _app._IMG_JOBS.get(jid)
        if j:
            j["status"] = "error" if error else "done"
            if error:
                j["error"] = error


def _job_cancelled(jid):
    """Workers check this between images so a Stop-all takes effect promptly."""
    with _app._IMG_JOBS_LOCK:
        j = _app._IMG_JOBS.get(jid)
        return bool(j and j.get("cancel"))


def _img_instructions_path():
    """Sidecar file holding the user's custom image instructions that the AI
    should remember for EVERY image generation, on top of the strategist's brief."""
    return os.path.join(os.path.dirname(os.path.abspath(_app.CONFIG_PATH)), "_image_instructions.json")


def _load_img_instructions(aid=None):
    """Returns the custom instruction text. Stored per-account when an account is
    active, with a global fallback that applies to all accounts."""
    try:
        with open(_app._img_instructions_path(), encoding="utf-8") as f:
            d = json.load(f) or {}
    except Exception:
        d = {}
    # The request's account when there is one (a tab's own), else the open one.
    from domain import request_account as _rqa
    aid = aid or _rqa.current(_app._state)
    # per-account instruction wins; otherwise the global one
    return (d.get("by_account", {}).get(aid, "") or d.get("global", "") or "").strip()


def _save_img_instructions(text, aid=None, scope="account"):
    try:
        try:
            with open(_app._img_instructions_path(), encoding="utf-8") as f:
                d = json.load(f) or {}
        except Exception:
            d = {}
        d.setdefault("by_account", {})
        if scope == "global":
            d["global"] = text or ""
        else:
            aid = aid or _app._state.get("active_account_id", "") or ""
            d["by_account"][aid] = text or ""
        from domain import jsonstore as _js     # atomic (a crash cannot empty it)
        return bool(_js.write_json_atomic(_app._img_instructions_path(), d, indent=2))
    except Exception:
        return False


def _run_img_jobs_bg(jid, jobs, kind):
    """Crash-safe wrapper around the image worker.

    A worker that dies on an unhandled exception -- e.g. the genimage/aplus NameError, or
    any failure BEFORE the per-job try -- never reached _job_finish, so its job sat on
    "running" forever: the UI spun at 0/N and Stop looked broken (Stop only sets a `cancel`
    flag, which a dead worker never reads). This guarantees the job is always retired.
    """
    try:
        _app._run_img_jobs_parallel(jid, jobs, kind)
    except Exception as _we:
        try:
            _app._job_finish(jid, error=f"worker crashed: {type(_we).__name__}: {str(_we)[:160]}")
        except Exception:
            pass
    finally:
        # Belt-and-braces: whatever happened, never leave the job on "running".
        try:
            with _app._IMG_JOBS_LOCK:
                _j = _app._IMG_JOBS.get(jid)
                if _j and _j.get("status") == "running":
                    _j["status"] = "error"
                    _j["error"] = _j.get("error") or "worker exited without finishing"
        except Exception:
            pass


# How many products may be generated for at the same time. Small on purpose:
# every image is a paid model call, and the image APIs rate-limit per account, so
# a large pool converts "faster" into "throttled and more expensive". Three is
# roughly three times quicker than the old strictly-sequential worker without
# getting near the limits. ALTA_IMG_WORKERS overrides it.
def _img_worker_count():
    try:
        n = int(os.environ.get("ALTA_IMG_WORKERS") or 3)
    except Exception:
        n = 3
    return max(1, min(n, 8))


def _run_img_jobs_parallel(jid, jobs, kind):
    """Generate for several PRODUCTS at once, images within a product in order.

    The worker ran every image in one sequence, so generating 8 images each for
    two products meant 16 one after another -- the second product did not start
    until the first had completely finished. Grouping by SKU and running the
    groups concurrently is what "side by side" means here, and it keeps each
    product's own images in their intended order (main before secondaries).

    Splitting by SKU rather than round-robin also keeps a product's images
    together on one thread, so a rate-limit stall delays one product rather than
    smearing across all of them.
    """
    groups = {}
    for jb in jobs:
        groups.setdefault(str(jb.get("sku", "") or "_misc"), []).append(jb)
    chunks = list(groups.values())

    if len(chunks) <= 1:
        _app._run_img_jobs_bg_inner(jid, jobs, kind, finish=False)
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(_app._img_worker_count(), len(chunks))) as pool:
            list(pool.map(lambda c: _app._run_img_jobs_bg_inner(jid, c, kind, finish=False),
                          chunks))
    # Finished exactly once, by the dispatcher. Letting each worker finish the
    # job would retire it the moment the FIRST product was done, and the rest
    # would keep writing results into a job the UI had already stopped watching.
    _app._job_finish(jid)


def _run_img_jobs_bg_inner(jid, jobs, kind, finish=True):
    """Background worker: runs a list of generation jobs, pushing each result.

    `finish=False` when several of these run as one job (see
    _run_img_jobs_parallel) -- the dispatcher retires the job after all of them.
    """
    # Custom instructions the user wants the AI to remember for EVERY image
    # (e.g. "always pure white background", "include our logo top-left", "no people").
    # We append them to each job's brief so they apply on top of the strategist.
    # The BATCH's account (stamped at enqueue), not whichever one is open when
    # this thread starts -- another tab may have switched since.
    _job_acct = next((str(j.get("_acct_id") or "") for j in (jobs or [])
                      if j.get("_acct_id")), "")
    _custom = _app._load_img_instructions(_job_acct or None)
    with _app.app.app_context():
        for job in jobs:
            if _app._job_cancelled(jid):
                _app._job_finish(jid, error="stopped by user")
                return
            label = job.get("label", "")
            ref = job.get("ref", "")
            if not ref:
                _app._job_push(jid, {"ok": False, "label": label, "sku": job.get("sku", ""),
                                "error": "no reference image"})
                continue
            try:
                payload = job.get("payload", {})
                # WHICH LISTING THIS PICTURE IS FOR.
                #
                # The SKU was on the job WRAPPER and the payload is what gets
                # dispatched, so it never arrived. Every endpoint here grounds
                # its image in the listing via _listing_for(), which needs a sku
                # or a listing and was getting neither -- so every image was
                # designed from a photograph and a title, with the bullets,
                # attributes and package contents never consulted.
                #
                # That is how a set comes back disagreeing with its own copy: an
                # image showing two carabiners under text that says one. Stamped
                # here rather than in each of the five callers, so a new kind of
                # image cannot be added without it.
                if job.get("sku") and not payload.get("sku"):
                    payload["sku"] = job.get("sku")
                if _custom:
                    # add to whatever brief field the endpoint reads, without
                    # clobbering the strategist's art direction.
                    payload["custom_instructions"] = _custom
                    if payload.get("art_direction") is not None:
                        payload["art_direction"] = (str(payload.get("art_direction", "")).rstrip()
                                                    + "\n\nUSER STANDING INSTRUCTIONS (always apply): " + _custom)
                # These handlers were extracted into route modules in Phase 3, so they're
                # no longer bare names in this module. Call them via the Flask view registry
                # (endpoint == function name) -- fixes "name 'genimage_from_concept' is not
                # defined" and the same latent break for recipe/source/secondary/aplus.
                # "recipe" here is the ENGINE, not the deleted saved-recipe feature.
                # The Creative button ("Generate 3 variations") runs through this
                # view, so genimage_recipe must stay even though no recipe UI is
                # left. See the header of static/js/genimage.js.
                # THE BATCH'S ACCOUNT, named on the internal request each image
                # is made through -- otherwise every lookup inside (the product's
                # facts, its rows, its instructions) fell back to whichever
                # account is open now, which another tab may have switched
                # (two-tab review). It was checked by the guard when the batch
                # was queued; an account inside the payload is never trusted.
                if isinstance(payload, dict):
                    payload.pop("account", None)
                    payload.pop("account_id", None)
                _job_q = ({"account": str(job.get("_acct_id"))}
                          if job.get("_acct_id") else {})
                if kind in ("recipe", "creative"):
                    with _app.app.test_request_context(json=payload, query_string=_job_q):
                        resp = _app.app.view_functions["genimage_recipe"]()
                elif kind == "concept":
                    with _app.app.test_request_context(json=payload, query_string=_job_q):
                        resp = _app.app.view_functions["genimage_from_concept"]()
                elif kind == "source":
                    with _app.app.test_request_context(json=payload, query_string=_job_q):
                        resp = _app.app.view_functions["genimage_process_source"]()
                elif kind == "secondary":
                    with _app.app.test_request_context(json=payload, query_string=_job_q):
                        resp = _app.app.view_functions["genimage_secondary_v2"]()
                elif kind == "aplus":
                    with _app.app.test_request_context(json=payload, query_string=_job_q):
                        resp = _app.app.view_functions["aplus_generate"]()
                else:
                    _app._job_push(jid, {"ok": False, "label": label, "error": "unknown job kind"})
                    continue
                if isinstance(resp, tuple):
                    data = resp[0].get_json()
                else:
                    data = resp.get_json()
                data = data or {"ok": False, "error": "no response"}
                data["label"] = label
                data["sku"] = job.get("sku", "")
                data["_kind"] = kind
                data["_payload"] = job.get("payload", {})
                # AUTO-SAVE every successful image to the SKU's media library so
                # background results are NEVER lost (even if the user closes the modal)
                if data.get("ok") and data.get("data_url"):
                    try:
                        sku = job.get("sku", "_misc")
                        du = data["data_url"]
                        # Decide a subfolder so each kind of image is filed inside
                        # the SKU folder rather than in one heap:
                        #
                        #   (root)          main / concepts
                        #   secondary       the PT01..PT08 supporting images
                        #   aplus/basic     A+ modules, standard tier
                        #   aplus/premium   A+ modules, premium tier
                        #
                        # THE KIND COMES FROM THE JOB, NOT THE BATCH. This read the
                        # batch-level `kind`, and the strategist -- which is how
                        # most images are actually made -- submits its whole batch
                        # as kind "concept" with the real kind on each job's
                        # payload (static/js/genimage.js _conceptJobs, and the bulk
                        # button in listings.js). So every strategist-made
                        # secondary and A+ image was filed at the SKU ROOT,
                        # indistinguishable from a main image.
                        #
                        # That is not only untidy. The folder IS the kind -- there
                        # is no image record anywhere, /media/list re-derives
                        # `group` from the directory name on every read -- so a
                        # misfiled image is permanently miscategorised, and the
                        # two guards that depend on it both stopped working:
                        # listing/images.py refuse_slot() would let an A+ image be
                        # sent to Amazon as the MAIN photo, and the "you already
                        # have N A+ images" warning never fired.
                        _kind = str(payload.get("kind", "") or kind or "").lower()
                        _sub = ""
                        if _kind == "aplus":
                            _tier = str(payload.get("tier", "") or data.get("tier", "") or "basic").lower()
                            _tier = "premium" if "prem" in _tier else "basic"
                            _sub = f"aplus/{_tier}"
                            # PREMIUM A+ IS TWO IMAGES, NOT ONE. Amazon renders
                            # premium modules at different sizes on desktop and on
                            # mobile, and a single asset cannot satisfy both -- so
                            # the tier folder is split again by which one this is.
                            # Basic A+ has no such split and keeps a flat folder.
                            _dev = str(payload.get("device", "") or data.get("device", "") or "").lower()
                            if _tier == "premium" and _dev in ("desktop", "mobile"):
                                _sub = f"aplus/premium/{_dev}"
                        elif _kind == "secondary":
                            _sub = "secondary"
                        # Resolve the image to RAW BYTES. The model may return a
                        # data: URL (base64) OR a remote https URL -- the old code
                        # only handled data: URLs, so URL-returning models saved
                        # NOTHING (empty Drive + empty library). Handle both.
                        raw_bytes = None
                        ext = "png"
                        if du.startswith("data:"):
                            head, _, raw = du.partition(",")
                            mime = (re.search(r"data:([^;]+)", head) or [None, "image/png"])[1]
                            ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "png")
                            try:
                                raw_bytes = _b64.b64decode(raw)
                            except Exception:
                                raw_bytes = None
                        elif re.match(r"^https?://", du.strip(), re.I):
                            try:
                                import urllib.request as _ur
                                from domain import url_policy as _urlp   # public only (M2)
                                _rq = _ur.Request(du.strip(), headers={"User-Agent": "Mozilla/5.0"})
                                with _urlp.urlopen(_rq, timeout=30) as _rr:
                                    raw_bytes = _rr.read(40 * 1024 * 1024)
                                    _ct = _rr.headers.get("Content-Type", "") if hasattr(_rr, "headers") else ""
                                if "jpeg" in _ct or "jpg" in _ct: ext = "jpg"
                                elif "webp" in _ct: ext = "webp"
                                elif "gif" in _ct: ext = "gif"
                            except Exception as _fe:
                                data["save_error"] = f"could not fetch image url: {str(_fe)[:120]}"
                                raw_bytes = None
                        if raw_bytes:
                            import time as _t
                            # Convert every generated image to JPEG: Amazon prefers
                            # JPEG for listing images and they're far smaller than the
                            # ~3-4 MB PNGs the models return. (No quality loss that
                            # matters at q90 for photographic product images.)
                            raw_bytes = _to_jpeg_bytes(raw_bytes, quality=90)
                            ext = "jpg"
                            # Naming: for LIVE Amazon listings we want Amazon's own
                            # convention {ASIN}.{TYPE}.{ext} (e.g. B000123456.MAIN.jpg,
                            # ...PT01.jpg for secondary, ...APLUS01.jpg for A+). The
                            # frontend passes 'asin' + 'img_code' on the job for that.
                            # Fall back to the old timestamp name when no code is set.
                            _asin = str(job.get("asin", "") or "").strip().upper()
                            _code = str(job.get("img_code", "") or "").strip().upper()
                            if _asin and _code:
                                fname = f"{_asin}.{_code}.{ext}"
                            else:
                                fname = f"generated_{int(_t.time()*1000)}.{ext}"
                            # Use the account captured when the batch was ENQUEUED, not
                            # whatever is active now -- a background job can finish after
                            # a redeploy or a workspace switch, and reading _state here is
                            # what misfiled images (and lost the user's A+ content).
                            _aid = str(job.get("_acct_id", "") or _app._state.get("active_account_id", "") or "")
                            _acct_root = _app._account_media_root(_aid) if _aid else _app._media_root()
                            _dir = os.path.join(_acct_root, _app._safe_sku(sku))
                            if _sub:
                                _dir = os.path.join(_dir, *_sub.split("/"))
                            os.makedirs(_dir, exist_ok=True)
                            _full = os.path.join(_dir, fname)
                            with open(_full, "wb") as f:
                                f.write(raw_bytes)
                            _pfx = f"/media/_acct/{_app._safe_sku(_aid)}" if _aid else "/media"
                            _subpart = f"{_sub}/" if _sub else ""
                            saved_url = f"{_pfx}/{_app._safe_sku(sku)}/{_subpart}{fname}"
                            data["saved_url"] = saved_url
                            data["saved_to_disk"] = True   # the persistent copy that survives redeploys
                            # OPTIONAL mirror to Drive. Drive is a nice-to-have backup, not
                            # required: the image is already safe on the persistent disk
                            # above. So "no Drive folder" is a normal state, not an error --
                            # surfacing it as drive_error made the UI look like the save
                            # failed when it fully succeeded on disk.
                            try:
                                # the account that OWNS this image (captured at enqueue),
                                # not whichever workspace is active now
                                acc = None
                                if _aid:
                                    try:
                                        import accounts as _accmod
                                        acc = _accmod.get_account(_app._cfg(), _aid, _app.CONFIG_PATH)
                                    except Exception:
                                        acc = None
                                # Never the OPEN account's Drive: if the batch's
                                # account is gone, the copy is simply not made.
                                if _aid and not acc:
                                    acc = None
                                else:
                                    acc = acc or _app._active_account()
                                folder = (acc or {}).get("drive_folder_url", "")
                                parent_id = _drive_folder_id_from_url(folder) if folder else ""
                                if not parent_id:
                                    data["drive_skipped"] = "no Drive folder configured (optional)"
                                else:
                                    _prod = ""
                                    try:
                                        # The BATCH's rows (a worker has no request,
                                        # so _ws() is the open account's).
                                        from data import backend as _be
                                        _st = (_be.store_for(_aid, _app._cfg(), _app.CONFIG_PATH)
                                               if _aid else None) or _app._ws()
                                        _rec = next((r for r in _app._records(_st)
                                                     if str(r.get("SKU", "")).strip() == str(sku).strip()), None)
                                        _prod = (_rec or {}).get("Title", "") or ""
                                    except Exception:
                                        _prod = ""
                                    dres = _app._drive_upload_image(parent_id, sku, _prod, _full,
                                                               filename=fname, subpath=_sub)
                                    if dres.get("id"):
                                        _app._drive_map_put(saved_url, {"drive_id": dres.get("id"),
                                                                   "direct_url": dres.get("direct_url", ""),
                                                                   "view_url": dres.get("view_url", "")})
                                        data["drive_direct_url"] = dres.get("direct_url", "")
                                    else:
                                        data["drive_error"] = "Drive upload returned no file id"
                            except Exception as _de:
                                data["drive_error"] = str(_de)[:200]
                    except Exception as _se:
                        data["save_error"] = str(_se)[:200]
                _app._job_push(jid, data)
            except Exception as e:
                _app._job_push(jid, {"ok": False, "label": label, "sku": job.get("sku", ""),
                                "error": str(e)[:200]})
    if finish:
        _app._job_finish(jid)
