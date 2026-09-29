"""routes/preview_job_routes.py — background Preview/Submit jobs (queue + visibility).

Thin endpoints over listing/preview_jobs. The heavy lifting (queue, worker, run-lock
serialisation) lives in that module; this only builds the command and exposes state.

  POST /preview/enqueue {sku, mode, minimal?}  -> {ok, job, counts}  enqueue (runs now or queues)
  GET  /preview/jobs                            -> {ok, jobs, counts} for the global panel
  GET  /preview/job?job=&sku=                   -> {ok, job}          full log+status for the drawer
  POST /preview/stop {job}                       -> {ok, stopped}      cancel a queued/running job
"""
import sys as _sys
from flask import request, jsonify

from listing import preview_jobs as _pj
from listing.run_command import build_api_run_args


def register(app, *, CONFIG_PATH, SCRIPT, _cfg, _active_account, _state, _require_publish):

    @app.route("/preview/enqueue", methods=["POST"])
    def preview_enqueue():
        b = request.get_json(force=True) or {}
        sku = str(b.get("sku", "")).strip()
        mode = str(b.get("mode", "api")).strip()
        minimal = bool(b.get("minimal"))
        if not sku:
            return jsonify({"ok": False, "error": "no sku"}), 400
        if mode not in ("api", "api_submit"):
            return jsonify({"ok": False, "error": "mode must be 'api' (preview) or 'api_submit'"}), 400
        # THE SAME ACCOUNT CHECK /run/<mode> MAKES. This queued a preview or a
        # SUBMIT for whatever account the server had selected, whatever the page
        # was showing (known-issues #4). One function decides it for both.
        from domain import request_account as _req_acct
        _mismatch = _req_acct.mismatch_for_write(request, _state, what="queued")
        if _mismatch:
            return jsonify({"ok": False, "error": _mismatch}), 409
        # PUBLISH GATE for submit (mirror listing_routes): a read-only workspace must never
        # reach the generator, or a submit would publish into the default (jack_uk) catalogue.
        if mode == "api_submit":
            try:
                _require_publish()
            except Exception as e:
                return jsonify({"ok": False, "error": str(e).replace("\n", " ")}), 403
        try:
            _acc = _active_account()
        except Exception:
            _acc = None
        # NO ACCOUNT, NO JOB (owner decision, read.txt 29 Sep 2026: "A preview
        # job must have an explicit account at the time it starts. Do not infer
        # ownership later from whichever account happens to be open."). /run
        # already refused here; the queue let the job through with no
        # --account-id, and the generator's credential fallback is the global
        # block. Refused before anything is queued, in the words /run uses.
        if not str((_acc or {}).get("id") or "").strip():
            return jsonify({"ok": False, "error": (
                "No account is open. Open the account this preview is for, "
                "then try again.")}), 400
        args = build_api_run_args(
            mode, script=SCRIPT, python_exe=_sys.executable, skus=sku, minimal=minimal,
            active_account=_acc,
            active_sheet_id=_state.get("active_sheet_id"),
            active_tab=_state.get("active_tab"),
            active_view=_state.get("active_view") or "",
            cfg=(_cfg() if _cfg else {}), config_path=CONFIG_PATH)
        # Name the account and the person. The run is keyed per account and per
        # SKU rather than against one global lock, so a job now waits only for
        # work that would genuinely collide with it -- and Stop can tell whose
        # run it is.
        from domain import job_owner as _jo
        jid = _pj.enqueue(sku, mode, args, label=sku,
                          account_id=str((_acc or {}).get("id", "") or ""),
                          owner=_jo.current())
        return jsonify({"ok": True, "job": jid, "counts": _pj.counts()})

    @app.route("/preview/jobs")
    def preview_jobs():
        """Your queue, not the server's.

        Every job was listed to everyone, so one person's Preview/Submit queue
        filled another's screen. Same rule as the image and auto-fix registries
        (domain/job_owner.py): your own, plus everything if you manage users."""
        from domain import job_owner as _jo
        from auth import users as _users
        # ...and only for accounts the caller may open (see /preview/job).
        jobs = [j for j in _pj.list_jobs(limit=100) if _jo.may_see(j, CONFIG_PATH)
                and (not j.get("account_id")
                     or _users.caller_may_see(CONFIG_PATH, j.get("account_id")))]
        return jsonify({"ok": True, "jobs": jobs, "counts": _pj.counts()})

    @app.route("/preview/job")
    def preview_job():
        """One job's log. YOURS, and for the account you are in.

        Any job id or SKU answered with that job, whoever ran it and for
        whichever account -- the same rule /preview/jobs above already applied
        to the list (master audit, 28 Sep 2026)."""
        from domain import job_owner as _jo
        jid = (request.args.get("job") or "").strip()
        sku = (request.args.get("sku") or "").strip()
        acct = str(request.args.get("account") or "").strip()
        if not acct:
            try:
                acct = str((_active_account() or {}).get("id") or "")
            except Exception:
                acct = ""
        j = _pj.get(jid) if jid else (_pj.by_sku(sku, account_id=acct) if sku else None)
        if j and not _jo.may_see(j, CONFIG_PATH):
            j = None
        # AND FOR AN ACCOUNT THE CALLER MAY OPEN. may_see() lets a user manager
        # see everyone's jobs, and job ids are sequential -- so ?job=pj1, pj2...
        # walked other accounts' run logs (account-scope review, Milestone 2).
        if j and j.get("account_id"):
            from auth import users as _users
            if not _users.caller_may_see(CONFIG_PATH, j.get("account_id")):
                j = None
        return jsonify({"ok": True, "job": j})

    @app.route("/preview/stop", methods=["POST"])
    def preview_stop():
        """Stop YOUR job. Stopping someone else's is never what was meant
        (domain/job_owner.mine_only), and any id used to do it."""
        from domain import job_owner as _jo
        b = request.get_json(force=True, silent=True) or {}
        jid = (b.get("job") or "").strip()
        j = _pj.get(jid) if jid else None
        if j and not _jo.mine_only(j):
            return jsonify({"ok": False, "stopped": False,
                            "error": "That run was started by someone else."}), 403
        return jsonify({"ok": True, "stopped": _pj.stop(jid)})
