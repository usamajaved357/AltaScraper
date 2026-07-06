"""routes/drive_routes.py — Google Drive endpoints, extracted from dashboard.py (Phase 3).

WHY THIS SHAPE
--------------
Mirrors the existing dashboard_brand_patch.register(app, ...) pattern already used
in this codebase: the shared helpers (_cfg, _active_account, _media_root and the
_drive_* utilities) are still used by other route groups that live in dashboard.py,
so they are INJECTED here rather than moved. The route bodies below are moved
VERBATIM from dashboard.py — no logic changes (CLAUDE.md §10).

Routes:
  GET  /drive/status   -> is a Drive folder configured + which SA email to share with
  GET  /drive/test     -> step-by-step Drive connectivity diagnosis
  POST /drive/upload   -> upload a saved local image into the account's Drive folder
"""
import os
import re
import json

from flask import request, jsonify


def register(app, *, _active_account, _cfg, _media_root,
             _drive_folder_id_from_url, _drive_service, _drive_upload_image):
    """Attach the /drive/* routes to the existing Flask app."""

    @app.route("/drive/test")
    def drive_test():
        """Diagnose the active account's Drive setup so an empty folder isn't a
        mystery: checks (1) a folder URL is set, (2) it parses to an ID, (3) the
        service account can read it, (4) it can create a folder + upload a tiny file,
        (5) make it public. Returns a step-by-step result."""
        steps = []
        def add(ok, label, detail=""):
            steps.append({"ok": bool(ok), "label": label, "detail": str(detail)[:300]})
        try:
            acc = _active_account()
        except Exception as e:
            return jsonify({"ok": False, "steps": [{"ok": False, "label": "active account", "detail": str(e)}]})
        sa_email = ""
        try:
            with open(_cfg()["google_service_account_json"], encoding="utf-8") as f:
                sa_email = (json.load(f) or {}).get("client_email", "")
        except Exception:
            sa_email = ""
        folder = (acc or {}).get("drive_folder_url", "")
        add(bool(folder), "Drive folder URL is set on this account", folder or "EMPTY — set it in Account & sheets")
        parent_id = _drive_folder_id_from_url(folder)
        add(bool(parent_id), "Folder URL parses to an ID", parent_id or "could not extract an ID from the URL")
        if not parent_id:
            return jsonify({"ok": False, "service_account": sa_email, "steps": steps})
        try:
            svc = _drive_service()
            add(True, "Drive API client built", "")
        except Exception as e:
            add(False, "Drive API client", str(e))
            return jsonify({"ok": False, "service_account": sa_email, "steps": steps})
        # can the service account SEE the folder?
        try:
            meta = svc.files().get(fileId=parent_id, fields="id,name,permissions",
                                   supportsAllDrives=True).execute()
            add(True, "Service account can access the folder", f"folder name: {meta.get('name','?')}")
        except Exception as e:
            add(False, "Service account can access the folder",
                f"{str(e)[:160]} -> SHARE the folder with {sa_email} as Editor")
            return jsonify({"ok": False, "service_account": sa_email, "steps": steps})
        # try a test upload
        try:
            import tempfile, base64 as _b
            # 1x1 png
            png = _b.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
            tf = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tf.write(png); tf.close()
            dres = _drive_upload_image(parent_id, "_drivetest", "Connection Test", tf.name,
                                       filename="drive_test.png")
            if dres.get("id"):
                add(True, "Test image uploaded + made public", dres.get("direct_url", ""))
                # clean up the test file
                try:
                    svc.files().delete(fileId=dres["id"], supportsAllDrives=True).execute()
                except Exception:
                    pass
            else:
                add(False, "Test image upload", "upload returned no id")
            try:
                os.remove(tf.name)
            except Exception:
                pass
        except Exception as e:
            _em = str(e)
            if "storageQuotaExceeded" in _em or "do not have storage" in _em or "storage quota" in _em.lower():
                add(False, "Test image upload",
                    "SERVICE ACCOUNTS HAVE NO DRIVE STORAGE. Your folder is a personal 'My Drive' "
                    "folder, so Google bills the upload to the service account (which has 0 quota) -> 403. "
                    "FIX (either one): (A) Create a SHARED DRIVE, add " + sa_email + " as Content Manager, "
                    "move this folder into it, and use that folder's URL; OR (B) set 'drive_impersonate_email' "
                    "in config.json to your Google email and enable domain-wide delegation for the service account.")
            else:
                add(False, "Test image upload", f"{_em[:160]} -> usually means {sa_email} needs Editor (not just 'anyone with link')")
        all_ok = all(s["ok"] for s in steps)
        return jsonify({"ok": all_ok, "service_account": sa_email, "steps": steps})

    @app.route("/drive/status")
    def drive_status():
        """Report whether the active account has a Drive folder configured + the
        service-account email to share it with."""
        acc = _active_account()
        folder = (acc or {}).get("drive_folder_url", "") if acc else ""
        fid = _drive_folder_id_from_url(folder)
        sa_email = ""
        try:
            c = _cfg()
            with open(c["google_service_account_json"], encoding="utf-8") as fh:
                sa_email = (json.load(fh) or {}).get("client_email", "")
        except Exception:
            sa_email = ""
        return jsonify({"ok": True, "configured": bool(fid), "folder_url": folder,
                        "folder_id": fid, "service_account_email": sa_email,
                        "account_label": (acc or {}).get("label", "") if acc else ""})

    @app.route("/drive/upload", methods=["POST"])
    def drive_upload():
        """Upload a previously-saved local image to the active account's Drive folder,
        into a {SKU}_{ProductName} subfolder. Body: {sku, product_name, relpath}."""
        b = request.get_json(force=True) or {}
        sku = b.get("sku", "")
        product_name = b.get("product_name", "")
        relpath = b.get("relpath", "")     # path under the media root (as served by /media)
        acc = _active_account()
        if not acc:
            return jsonify({"ok": False, "error": "no active account"}), 400
        folder = acc.get("drive_folder_url", "")
        parent_id = _drive_folder_id_from_url(folder)
        if not parent_id:
            return jsonify({"ok": False, "error": "no Drive folder configured for this account"}), 400
        # resolve the local file safely under the media root
        m = re.match(r"^/?media/(.+)$", str(relpath)) or re.match(r"^(.+)$", str(relpath))
        rel = m.group(1) if m else ""
        local = os.path.normpath(os.path.join(_media_root(), rel))
        if not local.startswith(os.path.normpath(_media_root())) or not os.path.isfile(local):
            return jsonify({"ok": False, "error": "file not found"}), 404
        try:
            result = _drive_upload_image(parent_id, sku, product_name, local)
            # result = {"id","view_url","direct_url"}; expose direct_url as the link to
            # use for Amazon, plus view_url for a human-clickable Drive page.
            return jsonify({"ok": True,
                            "link":       result.get("direct_url", ""),   # Amazon-usable
                            "direct_url": result.get("direct_url", ""),
                            "view_url":   result.get("view_url", ""),
                            "drive_id":   result.get("id", "")})
        except Exception as e:
            return jsonify({"ok": False, "error": f"Drive upload failed: {str(e)[:200]}"}), 502
