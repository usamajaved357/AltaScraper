"""routes/media_recover_routes.py -- find images the library is not showing.

/media/list shows ONE folder: the active workspace's. That is the right default
-- accounts must not see each other's work -- but it means an image saved while
a different workspace (or none) was open is invisible, and "invisible" and
"deleted" look identical from the screen.

These routes look at the WHOLE media folder regardless of workspace, so the
difference is visible, and let the owner move an orphaned folder into the
workspace that owns it.

    GET  /media/recover/survey   read-only: every image on the disk, by location
    POST /media/recover/move     move SKU folders between locations (dry-run first)
"""
from flask import jsonify, request

import domain.media_recover as _mr


def register(app, *, _media_root, _cfg, CONFIG_PATH, _guard=None):
    @app.route("/media/recover/survey")
    def media_recover_survey():
        """What is on the disk, and can the disk be trusted. Changes nothing."""
        import os
        try:
            import accounts as _acc
            ids = [a.get("id", "") for a in _acc.load_accounts(_cfg(), CONFIG_PATH,
                                                               persist=False)]
        except Exception:
            ids = []
        root = _media_root()
        res = _mr.survey(root, known_account_ids=[i for i in ids if i])
        res["accounts"] = [i for i in ids if i]
        res["disk"] = _mr.disk_evidence(os.path.dirname(os.path.abspath(CONFIG_PATH)))
        return jsonify({"ok": True, **res})

    @app.route("/media/recover/move", methods=["POST"])
    def media_recover_move():
        """Move SKU folders from one workspace's media folder to another.

        Defaults to a dry run: the caller sees the exact file list first and
        must send dry_run=false to actually move anything.
        """
        b = request.get_json(force=True) or {}
        src = str(b.get("from", "") or "")
        dst = str(b.get("to", "") or "")
        skus = b.get("skus") or None
        dry = b.get("dry_run")
        dry = True if dry is None else bool(dry)
        try:
            res = _mr.relocate(_media_root(), src, dst, skus=skus, dry_run=dry)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        code = 200 if res.get("ok") else 400
        return jsonify(res), code
