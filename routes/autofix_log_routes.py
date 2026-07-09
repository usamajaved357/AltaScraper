"""routes/autofix_log_routes.py -- persist auto-fix traces to disk so they survive a
page refresh.

The auto-fix trace is built in the browser and only shown in a pop-up, so refreshing the
page loses it. Each completed single/bulk auto-fix run POSTs its trace to /autofix/save_log,
which writes it to a timestamped file under <config-dir>/autofix_logs/ (that's the Render
persistent disk in production, so logs survive redeploys too).
"""
import os
import re
from datetime import datetime
from flask import request, jsonify


def register(app, *, CONFIG_PATH):
    _dir = os.path.join(os.path.dirname(os.path.abspath(str(CONFIG_PATH))), "autofix_logs")
    _NAME_RE = re.compile(r"autofix_[A-Za-z0-9_.-]+\.txt")

    @app.route("/autofix/save_log", methods=["POST"])
    def autofix_save_log():
        b = request.get_json(force=True) or {}
        text = str(b.get("text", "") or "")
        if not text.strip():
            return jsonify({"ok": False, "error": "empty trace"}), 400
        kind = re.sub(r"[^a-z0-9]+", "", str(b.get("kind", "log")).lower())[:12] or "log"
        acct = re.sub(r"[^A-Za-z0-9_-]+", "", str(b.get("account", "")))[:40] or "none"
        try:
            os.makedirs(_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = "autofix_%s_%s_%s.txt" % (kind, acct, ts)
            path = os.path.join(_dir, fname)
            _n = 1
            while os.path.exists(path):          # two runs in the same second -> suffix
                fname = "autofix_%s_%s_%s_%d.txt" % (kind, acct, ts, _n)
                path = os.path.join(_dir, fname)
                _n += 1
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return jsonify({"ok": True, "file": fname})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500

    @app.route("/autofix/logs", methods=["GET"])
    def autofix_list_logs():
        try:
            if not os.path.isdir(_dir):
                return jsonify({"ok": True, "logs": []})
            files = [f for f in os.listdir(_dir) if f.endswith(".txt")]
            files.sort(key=lambda f: os.path.getmtime(os.path.join(_dir, f)), reverse=True)
            out = [{"file": f,
                    "size": os.path.getsize(os.path.join(_dir, f)),
                    "mtime": int(os.path.getmtime(os.path.join(_dir, f)))}
                   for f in files[:200]]
            return jsonify({"ok": True, "logs": out})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500

    @app.route("/autofix/log", methods=["GET"])
    def autofix_get_log():
        f = str(request.args.get("file", "") or "")
        if not _NAME_RE.fullmatch(f):            # block path traversal
            return jsonify({"ok": False, "error": "bad name"}), 400
        path = os.path.join(_dir, f)
        if not os.path.isfile(path):
            return jsonify({"ok": False, "error": "not found"}), 404
        try:
            with open(path, encoding="utf-8") as fh:
                return jsonify({"ok": True, "file": f, "text": fh.read()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500
