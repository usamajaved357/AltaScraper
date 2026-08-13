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
        jobs = [j for j in _pj.list_jobs(limit=100) if _jo.may_see(j, CONFIG_PATH)]
        return jsonify({"ok": True, "jobs": jobs, "counts": _pj.counts()})

    @app.route("/preview/job")
    def preview_job():
        jid = (request.args.get("job") or "").strip()
        sku = (request.args.get("sku") or "").strip()
        j = _pj.get(jid) if jid else (_pj.by_sku(sku) if sku else None)
        return jsonify({"ok": True, "job": j})

    @app.route("/preview/stop", methods=["POST"])
    def preview_stop():
        b = request.get_json(silent=True) or {}
        return jsonify({"ok": True, "stopped": _pj.stop((b.get("job") or "").strip())})
