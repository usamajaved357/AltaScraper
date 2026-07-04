"""routes/media_routes.py — media library endpoints, extracted from dashboard.py (Phase 3).

register(app, ...) injection pattern. The media routes share many helpers with the
rest of the app (media roots, safe-sku, the _drive_* utilities, records/worksheet),
so all are injected and the route bodies move VERBATIM (CLAUDE.md §10). Only stdlib
os/re/base64 and the Flask helpers are imported locally.

Routes:
  GET  /media/<path>   -> serve a stored media file
  POST /media/upload   -> save an uploaded/generated image (+ optional auto-Drive push)
  GET  /media/list     -> list the active account's stored images grouped by SKU
  POST /media/delete   -> delete a stored image (local + Drive if mapped)
"""
import os
import re
import base64 as _b64

from flask import request, jsonify, send_from_directory


def register(app, *, _media_root, _safe_sku, _sku_dir, _state, _active_account,
             _drive_folder_id_from_url, _records, _ws, _drive_upload_image,
             _drive_map_put, _account_media_root, _sniff_image_ext, _to_jpeg_bytes,
             _drive_map_remove, _drive_delete_file):
    """Attach the /media/* routes to the existing Flask app."""

    @app.route("/media/<path:relpath>")
    def media_serve(relpath):
        """Serve a stored media file by its media/<sku>/<file> path."""
        return send_from_directory(_media_root(), relpath)

    @app.route("/media/upload", methods=["POST"])
    def media_upload():
        """Save an uploaded image (base64 data URL or raw b64) under media/<sku>/.
        Returns the served URL. Used for reference uploads and saving generations."""
        b = request.get_json(force=True) or {}
        sku  = b.get("sku", "_misc")
        data = b.get("data", "")            # data URL or bare base64
        name = b.get("name", "")           # optional original filename
        kind = b.get("kind", "ref")        # 'ref' | 'generated' | 'main'
        # optional subfolder to organize images inside the SKU folder, e.g.
        # "aplus/basic", "aplus/premium", "secondary". Sanitized to a safe set of
        # path segments (letters/digits/_/-) so it can never traverse outside.
        subfolder = b.get("subfolder", "") or ""
        safe_segs = []
        for seg in str(subfolder).replace("\\", "/").split("/"):
            seg = re.sub(r"[^A-Za-z0-9_-]", "", seg).strip()
            if seg and seg not in (".", ".."):
                safe_segs.append(seg)
        subfolder = "/".join(safe_segs[:3])  # cap depth
        if not data:
            return jsonify({"ok": False, "error": "no image data"}), 400
        mime = "image/png"
        if data.startswith("data:"):
            head, _, data = data.partition(",")
            m = re.search(r"data:([^;]+)", head)
            if m: mime = m.group(1)
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
               "image/webp": "webp", "image/gif": "gif"}.get(mime, "png")
        # data can be: a data-URL (base64, handled above), bare base64, OR a remote
        # https URL (some image models return a URL, not base64). If it's a URL, fetch
        # the real image bytes -- otherwise b64decode fails and we'd save nothing,
        # leaving an EMPTY Drive folder (the bug). Resolve all three to raw bytes.
        raw = None
        if re.match(r"^https?://", data.strip(), re.I):
            try:
                import urllib.request as _ur
                _req = _ur.Request(data.strip(), headers={"User-Agent": "Mozilla/5.0"})
                with _ur.urlopen(_req, timeout=30) as _r:
                    raw = _r.read()
                _ct = ""
                try:
                    _ct = _r.headers.get("Content-Type", "") if hasattr(_r, "headers") else ""
                except Exception:
                    _ct = ""
                if "jpeg" in _ct or "jpg" in _ct: ext = "jpg"
                elif "webp" in _ct: ext = "webp"
                elif "gif" in _ct: ext = "gif"
                elif "png" in _ct: ext = "png"
            except Exception as e:
                return jsonify({"ok": False, "error": f"could not fetch image URL: {str(e)[:160]}"}), 400
        else:
            try:
                raw = _b64.b64decode(data)
            except Exception as e:
                return jsonify({"ok": False, "error": f"bad base64: {e}"}), 400
        if not raw:
            return jsonify({"ok": False, "error": "no image bytes resolved"}), 400
        # AUTHORITATIVE: name the file by the REAL format read from the bytes, not the
        # mime label or Content-Type (either can be wrong -- a model may hand back JPEG
        # bytes tagged image/png, which Amazon then rejects). The bytes never lie.
        ext = _sniff_image_ext(raw, ext)
        # 'ref' uploads (a reference image the user provides) are kept as-is so we
        # don't degrade a source photo; GENERATED/main images are converted to JPEG
        # (Amazon-preferred, much smaller). Skip re-encoding if it's already JPEG.
        if kind != "ref" and ext != "jpg":
            raw = _to_jpeg_bytes(raw, quality=90)
            ext = "jpg"
        import time as _t
        base = _safe_sku(os.path.splitext(name)[0]) if name else kind
        fname = f"{kind}_{int(_t.time())}_{base}.{ext}"[:140]
        d = _sku_dir(sku)
        if subfolder:
            d = os.path.join(d, *subfolder.split("/"))
            os.makedirs(d, exist_ok=True)
        fpath = os.path.join(d, fname)
        try:
            with open(fpath, "wb") as f:
                f.write(raw)
        except Exception as e:
            return jsonify({"ok": False, "error": f"write failed: {e}"}), 500
        aid = _state.get("active_account_id", "") or ""
        _pfx = f"/media/_acct/{_safe_sku(aid)}" if aid else "/media"
        _subpart = f"{subfolder}/" if subfolder else ""
        url = f"{_pfx}/{_safe_sku(sku)}/{_subpart}{fname}"

        # AUTO-DRIVE: for generated/main images, push to the account's Drive folder
        # right away, make it public, and record the mapping so (a) we can hand Amazon
        # a usable direct URL and (b) deleting the local copy also deletes it on Drive.
        drive_direct = drive_view = drive_id = ""
        drive_error = ""
        try:
            if kind in ("generated", "main"):
                acc = _active_account()
                folder = (acc or {}).get("drive_folder_url", "")
                parent_id = _drive_folder_id_from_url(folder)
                if not parent_id:
                    drive_error = "no Drive folder configured for this account"
                if parent_id:
                    _prod = ""
                    try:
                        _rec = next((r for r in _records(_ws())
                                     if str(r.get("SKU", "")).strip() == str(sku).strip()), None)
                        _prod = (_rec or {}).get("Title", "") or ""
                    except Exception:
                        _prod = ""
                    res = _drive_upload_image(parent_id, sku, _prod, fpath, filename=fname, subpath=subfolder)
                    drive_direct = res.get("direct_url", "")
                    drive_view   = res.get("view_url", "")
                    drive_id     = res.get("id", "")
                    if drive_id:
                        _drive_map_put(url, {"drive_id": drive_id,
                                             "direct_url": drive_direct,
                                             "view_url": drive_view})
                    else:
                        drive_error = "Drive upload returned no file id"
        except Exception as _e:
            # never let a Drive hiccup fail the LOCAL save; the image is still saved.
            # But DO report the reason so an empty Drive folder isn't a silent mystery.
            drive_direct = drive_view = drive_id = ""
            drive_error = str(_e)[:200]

        return jsonify({"ok": True, "url": url, "name": fname, "sku": _safe_sku(sku),
                        "drive_direct_url": drive_direct, "drive_view_url": drive_view,
                        "drive_id": drive_id, "drive_error": drive_error})

    @app.route("/media/list")
    def media_list():
        """List stored media grouped by SKU for the ACTIVE account only, so each
        workspace shows its own image library. Optional ?sku= filters."""
        aid = _state.get("active_account_id", "") or ""
        root = _account_media_root(aid)
        # URL prefix that media_serve can resolve back to this root
        url_prefix = f"/media/_acct/{_safe_sku(aid)}" if aid else "/media"
        only = request.args.get("sku")
        out = []
        try:
            skus = [only] if only else sorted(os.listdir(root))
            for s in skus:
                sd = os.path.join(root, _safe_sku(s)) if only else os.path.join(root, s)
                if not os.path.isdir(sd):
                    continue
                base = os.path.basename(sd)
                if base == "_acct":      # never list the account container itself
                    continue
                files = []
                # walk the SKU folder AND its subfolders (e.g. aplus/basic, aplus/premium,
                # secondary) so organized A+ content is listed too, tagged by group.
                for dirpath, dirnames, filenames in os.walk(sd):
                    rel = os.path.relpath(dirpath, sd)
                    group = "" if rel == "." else rel.replace(os.sep, "/")
                    for fn in sorted(filenames, reverse=True):
                        if fn.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp", "gif"):
                            _fp = os.path.join(dirpath, fn)
                            _w = _h = 0
                            _sz = 0
                            try:
                                _sz = os.path.getsize(_fp)
                                from PIL import Image as _PImg
                                with _PImg.open(_fp) as _im:
                                    _w, _h = _im.size
                            except Exception:
                                _w = _h = 0
                            _urlpath = f"{base}/{group}/{fn}" if group else f"{base}/{fn}"
                            files.append({"name": fn, "url": f"{url_prefix}/{_urlpath}",
                                          "width": _w, "height": _h, "bytes": _sz,
                                          "group": group})
                if files:
                    # sort so root images come first, then grouped (aplus/basic, etc.)
                    files.sort(key=lambda x: (x.get("group", ""), x["name"]), reverse=False)
                    out.append({"sku": base, "count": len(files), "files": files})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        return jsonify({"ok": True, "folders": out})

    @app.route("/media/delete", methods=["POST"])
    def media_delete():
        b = request.get_json(force=True) or {}
        url = b.get("url", "")
        # Accept both legacy /media/<sku>/<file> and account-scoped
        # /media/_acct/<aid>/<sku>/<file>. Resolve relative to the media root and
        # guard against path traversal.
        m = re.match(r"^/media/(.+)$", url or "")
        if not m:
            return jsonify({"ok": False, "error": "bad url"}), 400
        relpath = m.group(1)
        if ".." in relpath or relpath.startswith("/"):
            return jsonify({"ok": False, "error": "bad path"}), 400
        fpath = os.path.normpath(os.path.join(_media_root(), relpath))
        if not fpath.startswith(os.path.normpath(_media_root())):
            return jsonify({"ok": False, "error": "bad path"}), 400
        try:
            if os.path.exists(fpath):
                os.remove(fpath)
            # Also remove from Drive if we have a record for this image, so the user's
            # "delete from workspace" truly removes it everywhere (local + Drive).
            drive_removed = False
            try:
                info = _drive_map_remove(url)
                if info and info.get("drive_id"):
                    drive_removed = _drive_delete_file(info["drive_id"])
            except Exception:
                drive_removed = False
            return jsonify({"ok": True, "drive_removed": drive_removed})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
