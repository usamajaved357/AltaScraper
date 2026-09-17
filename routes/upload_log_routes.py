"""routes/upload_log_routes.py -- the Upload history page's data.

    GET /uploads/list?account=&kind=      this account's uploads, newest first
    GET /uploads/detail/<id>?account=     one upload, with its per-row report
    GET /uploads/file/<id>?account=       the ORIGINAL file, as uploaded
    GET /uploads/report/<id>?account=     the processing report, as CSV

WHOSE UPLOADS. Every address names the account. The doorman (auth/guard.py)
refuses an account the signed-in user may not open, and an upload is served only
when it belongs to the account named -- so an id guessed from another account
answers 404, never another company's cost sheet.

Recording lives in domain/upload_log.py; each upload route calls it.
"""
import os

from flask import jsonify, request, Response, send_file


def register(app, *, CONFIG_PATH, _state):

    def _account():
        return str(request.args.get("account") or request.args.get("id")
                   or (_state or {}).get("active_account_id") or "").strip()

    @app.route("/uploads/list")
    def uploads_list():
        from domain import upload_log as _ul
        aid = _account()
        if not aid:
            return jsonify({"ok": False, "error": "Open an account first."}), 400
        kind = str(request.args.get("kind") or "").strip() or None
        try:
            limit = int(request.args.get("limit") or 200)
        except ValueError:
            limit = 200
        return jsonify({"ok": True, "account": aid,
                        "kinds": _ul.KINDS,
                        "uploads": _ul.recent(CONFIG_PATH, aid, kind=kind, limit=limit)})

    @app.route("/uploads/detail/<int:upload_id>")
    def uploads_detail(upload_id):
        from domain import upload_log as _ul
        rec = _ul.get(CONFIG_PATH, upload_id, _account())
        if not rec:
            return jsonify({"ok": False, "error": "No such upload in this account."}), 404
        rec["has_file"] = bool(_ul.file_path(CONFIG_PATH, rec)) and bool(rec.get("bytes"))
        rec.pop("stored_path", None)
        rec["report"] = rec.get("report", [])[:1000]
        return jsonify({"ok": True, "upload": rec})

    @app.route("/uploads/file/<int:upload_id>")
    def uploads_file(upload_id):
        from domain import upload_log as _ul
        rec = _ul.get(CONFIG_PATH, upload_id, _account())
        path = _ul.file_path(CONFIG_PATH, rec) if rec else ""
        if not path:
            return jsonify({"ok": False, "error": "That file is not available."}), 404
        return send_file(path, as_attachment=True,
                         download_name=os.path.basename(rec.get("filename") or "upload"))

    @app.route("/uploads/report/<int:upload_id>")
    def uploads_report(upload_id):
        from domain import upload_log as _ul
        rec = _ul.get(CONFIG_PATH, upload_id, _account())
        if not rec:
            return jsonify({"ok": False, "error": "No such upload in this account."}), 404
        base = os.path.splitext(os.path.basename(rec.get("filename") or "upload"))[0]
        name = "report-%d-%s.csv" % (upload_id, "".join(
            c if (c.isalnum() or c in "._-") else "_" for c in base)[:80])
        return Response(_ul.report_csv(rec), mimetype="text/csv", headers={
            "Content-Disposition": 'attachment; filename="%s"' % name})
