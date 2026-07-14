"""routes/autofix_job_routes.py — auto-fix as a SERVER-SIDE background job.

Auto-fix used to run as a JavaScript loop in the browser, so it died the moment the
browser stopped running JS: a locked screen, a slept laptop, a closed tab, a re-login.
These routes drive the same Suggest -> Apply -> Preview loop on the SERVER instead.

  POST /autofix/start   {skus:[...]}  -> {ok, job}   start (or reject if one is running)
  GET  /autofix/state   [?job=ID]     -> the live job (defaults to the running one)
  POST /autofix/stop    {job?:ID}     -> stop one job, or every running job

The job registry is SERVER state, so ANY signed-in browser sees the same progress --
including a different device, or the same user after signing back in. The run continues
until every SKU is done or the user presses Stop.
"""
from flask import request, jsonify


def register(app, *, _af_new, _af_get, _af_active, _af_stop, _run_autofix_bg, _state, _threading):
    """Attach the /autofix/* job routes to the existing Flask app."""

    @app.route("/autofix/start", methods=["POST"])
    def autofix_start():
        b = request.get_json(force=True) or {}
        skus = [str(s).strip() for s in (b.get("skus") or []) if str(s).strip()]
        if not skus:
            return jsonify({"ok": False, "error": "no SKUs selected"}), 400
        # One auto-fix run at a time: each Preview drives the generator subprocess, which
        # is itself serialised by the run lock. Two concurrent runs would just queue up
        # behind each other and make the progress meaningless.
        # NB: _af_active() also returns the last FINISHED job (so a poller can read the
        # final result), so check the STATUS -- not merely that a job exists, or the
        # first completed run would block every run after it.
        cur = _af_active()
        if cur and cur.get("status") == "running":
            return jsonify({"ok": False, "error": "an auto-fix run is already in progress",
                            "job": cur.get("id"), "running": True}), 409
        jid = _af_new(skus, _state.get("active_account_id", "") or "",
                      label=(b.get("label") or "").strip()[:80])
        t = _threading.Thread(target=_run_autofix_bg, args=(jid,), daemon=True)
        t.start()
        return jsonify({"ok": True, "job": jid, "total": len(skus)})

    @app.route("/autofix/state")
    def autofix_state():
        """The live job. With no ?job= it returns whichever run is active, so a browser
        that just signed in can attach to work that was already under way."""
        jid = (request.args.get("job") or "").strip()
        j = _af_get(jid) if jid else _af_active()
        if not j:
            return jsonify({"ok": True, "job": None})
        return jsonify({"ok": True, "job": j})

    @app.route("/autofix/stop", methods=["POST"])
    def autofix_stop():
        b = request.get_json(silent=True) or {}
        n = _af_stop((b.get("job") or "").strip())
        return jsonify({"ok": True, "stopped": n})
