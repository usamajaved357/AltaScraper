"""domain/autofix_jobs.py -- the auto-fix jobs: state, stopping, preview and the background loop.

Moved out of dashboard.py (Milestone 4, owner-approved 28 Sep 2026: "pass the
required shared app state explicitly to the background-job modules").
The job code is unchanged except that each name it read from the app
module is now read as _app.<name>: a live lookup on the RUNNING app
module, handed in once by bind(), so a job still sees the current
workspace, records, config path -- and anything a test replaces -- at
the moment it runs. This module never imports dashboard (that would
load a second copy of the app).
"""

from listing import api_issues as _api_issues

_app = None


def bind(app_module):
    """Hand this module the running app module (dashboard.py does, once)."""
    global _app
    _app = app_module


def _af_new(skus, account_id, label=""):
    import time as _t, uuid as _u
    jid = _u.uuid4().hex[:12]
    with _app._AF_JOBS_LOCK:
        # retire anything older than an hour so the registry can't grow forever
        for k in [k for k, v in _app._AF_JOBS.items() if _t.time() - v.get("ts", 0) > 3600]:
            _app._AF_JOBS.pop(k, None)
        from domain import job_owner as _jo
        _app._AF_JOBS[jid] = _jo.stamp({
            "id": jid, "status": "running", "cancel": False, "error": "",
            "ts": _t.time(), "started_at": _t.strftime("%Y-%m-%d %H:%M:%S"),
            "account_id": account_id, "label": label,
            "skus": list(skus), "total": len(skus), "done": 0,
            "current": "", "current_round": 0,
            "summary": {"cleared": 0, "stuck": 0, "failed": 0, "not_run": len(skus)},
            "results": [],          # one entry per finished SKU
            "steps": [],            # human-readable progress lines
        })
    return jid


def _af_get(jid):
    with _app._AF_JOBS_LOCK:
        j = _app._AF_JOBS.get(jid)
        return dict(j) if j else None


def _af_active():
    """The job to show when no id is given: the newest RUNNING one, else the newest
    job of any status.

    The fallback matters. Returning only running jobs meant that the moment a run
    finished, this went None -- so the polling browser lost the final result and the
    panel just froze on the last tick. A finished job stays visible (for the hour it
    lives in the registry) so the outcome is always readable, including by someone who
    signs in after it ended.
    """
    # SCOPED TO THE ACCOUNT ASKING. The registry is process-wide and this
    # returned the newest job of ANY account, so opening Jack Reacherd showed a
    # Nestwell auto-fix in progress -- somebody else's SKUs, somebody else's
    # errors, and a Stop button next to them. The job already records the
    # account it was started for; it simply was not being read.
    #
    # A job stamped before accounts were recorded has none, and is still shown:
    # hiding work that is genuinely running is the worse failure.
    acct = str(_app._state.get("active_account_id", "") or "")
    with _app._AF_JOBS_LOCK:
        if not _app._AF_JOBS:
            return None
        def _mine(v):
            a = str(v.get("account_id") or "")
            return (not a) or (not acct) or a == acct
        pool_all = [v for v in _app._AF_JOBS.values() if _mine(v)]
        if not pool_all:
            return None
        run = [v for v in pool_all if v.get("status") == "running"]
        pool = run or pool_all
        return dict(sorted(pool, key=lambda x: x.get("ts", 0))[-1])


def _af_cancelled(jid):
    with _app._AF_JOBS_LOCK:
        j = _app._AF_JOBS.get(jid)
        return bool(j and j.get("cancel"))


def _af_stop(jid=""):
    """Stop one job, or every running job IN THIS ACCOUNT when jid is empty.

    "Every running job" meant every one on the server, so Stop in one workspace
    cancelled an auto-fix loop running in another -- work that was part-way
    through rewriting listings and had to be started again from the beginning.
    Naming a job id still stops exactly that job, wherever it belongs.
    """
    acct = str(_app._state.get("active_account_id", "") or "")
    n = 0
    with _app._AF_JOBS_LOCK:
        for k, j in _app._AF_JOBS.items():
            if j.get("status") != "running":
                continue
            if jid:
                if k != jid:
                    continue
            else:
                a = str(j.get("account_id") or "")
                if a and acct and a != acct:
                    continue
            j["cancel"] = True
            n += 1
    return n


def _af_step(jid, msg):
    with _app._AF_JOBS_LOCK:
        j = _app._AF_JOBS.get(jid)
        if j:
            j["steps"].append(msg)
            del j["steps"][:-400]          # keep the tail bounded


def _af_set(jid, **kw):
    with _app._AF_JOBS_LOCK:
        j = _app._AF_JOBS.get(jid)
        if j:
            j.update(kw)


def _af_finish(jid, error=""):
    with _app._AF_JOBS_LOCK:
        j = _app._AF_JOBS.get(jid)
        if j:
            if j.get("cancel") and not error:
                j["status"] = "stopped"
            else:
                j["status"] = "error" if error else "done"
            if error:
                j["error"] = error


def _af_preview(sku, acct=""):
    """Run one Preview for `sku` and return (verdict, error_fields, lines).

    verdict: ok_preview | error | missing | busy | network | nocreds | unknown
    """
    from urllib.parse import quote as _q
    lines, verdict, n_err, fields = [], None, 0, []
    try:
        # Named, so the run route's own mismatch refusal applies if the open
        # account moved since the last check (request_account.mismatch_for_write).
        _acct_q = f"&account={_q(acct)}" if acct else ""
        with _app.app.test_request_context(f"/run/api?skus={_q(sku)}{_acct_q}"):
            resp = _app.app.view_functions["run"]("api")
            for chunk in resp.response:            # drives the generator to completion
                text = chunk.decode("utf-8", "replace") if isinstance(chunk, bytes) else str(chunk)
                for raw in text.splitlines():
                    if not raw.startswith("data: "):
                        continue
                    d = raw[6:]
                    lines.append(d)
                    if "[busy]" in d:
                        verdict = "busy"
                    if _app._AF_NET.search(d):
                        verdict = "network"
                    if "no seller_id" in d.lower():
                        verdict = "nocreds"
                    for m in _app._AF_EFIELD.finditer(d):
                        if m.group(1) not in fields:
                            fields.append(m.group(1))
                    # NEVER read the generator's explanatory prose as a per-row result:
                    # it names the SKU *and* the words "API_READY, APPROVED", which used
                    # to be misparsed as success.
                    if _app._AF_PROSE.search(d) or sku not in d:
                        continue
                    low = d.lower()
                    m = _app._AF_ERRNUM.search(d)
                    if m:
                        verdict, n_err = "error", int(m.group(1))
                    elif "not live" in low or "api call failed" in low or "api_error" in low:
                        verdict, n_err = "error", 0
                    elif "missing" in low and "skip" in low:
                        verdict = "missing"
                    elif "api_ready" in low or "preview clean" in low:
                        verdict = "ok_preview"
    except Exception as e:
        return "exception", fields, lines + [f"preview crashed: {type(e).__name__}: {e}"]
    return (verdict or "unknown"), fields, lines


def _run_autofix_bg(jid):
    """Crash-safe wrapper -- a worker that dies must never leave the job 'running'."""
    try:
        _app._run_autofix_bg_inner(jid)
    except Exception as e:
        try:
            _app._af_finish(jid, error=f"worker crashed: {type(e).__name__}: {str(e)[:200]}")
        except Exception:
            pass
    finally:
        try:
            with _app._AF_JOBS_LOCK:
                j = _app._AF_JOBS.get(jid)
                if j and j.get("status") == "running":
                    j["status"] = "error"
                    j["error"] = j.get("error") or "worker exited without finishing"
        except Exception:
            pass


def _run_autofix_bg_inner(jid):
    """Suggest -> Apply -> Preview, per SKU, until clean / stuck / stopped."""
    job = _app._af_get(jid)
    if not job:
        return
    skus = job["skus"]
    acct = job["account_id"]

    # CHECKED BEFORE EVERY STEP, not once per SKU. Suggest, apply and Preview
    # all act on the server's open account (a worker has no page to name one),
    # so a switch in another tab part-way through a SKU sent that SKU's later
    # rounds to the other account's same-SKU row (background-jobs audit).
    def _moved():
        if (_app._state.get("active_account_id") or "") != (acct or ""):
            _app._af_finish(jid, error="Workspace changed while auto-fix was running, so it "
                                  "stopped to avoid editing another account's listings. "
                                  "Go back to the original workspace and run it again.")
            return True
        return False

    with _app.app.app_context():
        for idx, sku in enumerate(skus):
            if _app._af_cancelled(jid):
                _app._af_step(jid, "Stopped by user.")
                break
            # The worker writes to whatever sheet _ws() resolves, which follows the
            # ACTIVE workspace. If the user switches account mid-run we would edit the
            # wrong account's rows -- refuse rather than corrupt someone else's sheet.
            if (_app._state.get("active_account_id") or "") != (acct or ""):
                _app._af_finish(jid, error="Workspace changed while auto-fix was running, so it "
                                      "stopped to avoid editing another account's listings. "
                                      "Go back to the original workspace and run it again.")
                return

            _app._af_set(jid, current=sku, current_round=0)
            _app._af_step(jid, f"[{idx+1}/{len(skus)}] {sku} — starting")
            rounds, prev_errors, outcome, diagnosis = [], None, "failed", ""

            for rnd in range(1, _app._AF_MAX_ROUNDS + 1):
                if _app._af_cancelled(jid):
                    break
                _app._af_set(jid, current_round=rnd)
                entry = {"round": rnd, "suggestions": [], "applied": [], "skipped": [],
                         "verdict": None, "error_fields": [], "diagnosis": ""}

                # 1) ask for suggestions
                if _moved():
                    return
                try:
                    with _app.app.test_request_context(json={"sku": sku},
                                                  query_string={"account": acct} if acct else {}):
                        sres = _app.app.view_functions["suggest"]().get_json() or {}
                except Exception as e:
                    entry["diagnosis"] = f"/suggest crashed: {e}"
                    rounds.append(entry); diagnosis = entry["diagnosis"]; break
                if not sres.get("ok"):
                    err = str(sres.get("error") or "unknown")
                    entry["diagnosis"] = f"/suggest failed: {err}"
                    rounds.append(entry); diagnosis = entry["diagnosis"]; break

                allsug = sres.get("suggestions") or []
                entry["suggestions"] = [{"field": s.get("field"), "value": s.get("value", ""),
                                         "source": s.get("source", ""),
                                         "code_owned": bool(s.get("_code_owned"))} for s in allsug]
                ai = [s for s in allsug if not s.get("_code_owned")]
                code_owned = len(allsug) - len(ai)
                _app._af_step(jid, f"[{idx+1}/{len(skus)}] {sku} — round {rnd}: "
                              f"{len(ai)} AI suggestion(s), {code_owned} code-owned")

                # 2) apply them -- ONE batched write for the whole round. The old
                # path called /edit per field (2-3 reads + a write + a cache-bust
                # EACH), which tripped Google's per-minute quota (429) on multi-SKU
                # runs. Collapsing a round into a single write also cuts wall-clock.
                for s in ai:
                    if not s.get("value"):
                        entry["skipped"].append({"field": s.get("field"), "reason": "empty AI value"})
                _batch = [{"target": "attr", "key": s.get("field"), "value": s.get("value")}
                          for s in ai if s.get("value")]
                if _batch and not _app._af_cancelled(jid):
                    if _moved():
                        return
                    try:
                        _ap, _sk = _app._apply_edits_batch(sku, _batch)
                        entry["applied"].extend(_ap)
                        entry["skipped"].extend(_sk)
                    except Exception as e:
                        for _s2 in _batch:
                            entry["skipped"].append({"field": _s2.get("key"),
                                                     "reason": f"batch edit crashed: {e}"})

                # nothing new to apply and nothing code-owned -> the AI is out of ideas
                if rnd > 1 and not entry["applied"] and code_owned == 0:
                    entry["diagnosis"] = ("Nothing new to apply and no code-owned fields left. "
                                          + ("Amazon still rejects: " + ", ".join(prev_errors.split("|"))
                                             if prev_errors else "The AI has no more suggestions."))
                    rounds.append(entry); outcome = "stuck"; diagnosis = entry["diagnosis"]; break

                # 3) preview
                _app._af_step(jid, f"[{idx+1}/{len(skus)}] {sku} — round {rnd}: previewing against Amazon…")
                if _moved():
                    return
                verdict, fields, _lines = _app._af_preview(sku, acct)
                entry["verdict"] = verdict
                entry["error_fields"] = fields
                rounds.append(entry)

                if _app._af_cancelled(jid):
                    break
                if verdict == "ok_preview":
                    entry["diagnosis"] = "Amazon accepted the Preview. Ready to Submit."
                    outcome = "cleared"; diagnosis = entry["diagnosis"]
                    _app._af_step(jid, f"[{idx+1}/{len(skus)}] {sku} — ✓ clean, ready to submit")
                    break
                if verdict in ("network", "nocreds", "busy", "exception"):
                    entry["diagnosis"] = f"Environment issue ({verdict}) — not a listing problem."
                    outcome = "failed"; diagnosis = entry["diagnosis"]; break
                if verdict == "error":
                    key = "|".join(sorted(fields))
                    entry["diagnosis"] = "Amazon flagged: " + (", ".join(fields) or "(no field named)")
                    # A CATALOGUE MATCH IS NOT A FIELD TO TRY HARDER AT.
                    #
                    #     "a color is not something amazon should stuck on"
                    #
                    # And it was not really stuck on the colour. Amazon code 8541
                    # means our data MATCHES an existing ASIN and disagrees with
                    # it; the field it names is where the disagreement is, not a
                    # value that is wrong. The only value that would satisfy it
                    # is Amazon's own -- which would attach our new product to
                    # somebody else's ASIN, the piggyback listing Rule 1 exists
                    # to prevent. So this stops on the FIRST round rather than
                    # spending another one re-applying a value that was already
                    # right. listing/api_issues.py owns the recognition and
                    # decides on the CODE, never the prose (Rule 4).
                    try:
                        _rec = _api_issues.parse(
                            (next((r for r in _app._records(_app._ws())
                                   if str(r.get("SKU", "")).strip() == sku), {}) or {})
                            .get("API Issues JSON"))
                        _cc = _api_issues.catalogue_conflict(_rec)
                    except Exception:
                        _cc = None
                    if _cc:
                        entry["diagnosis"] = _api_issues.catalogue_conflict_note(_cc)
                        outcome = "stuck"; diagnosis = entry["diagnosis"]
                        _app._af_step(jid, f"[{idx+1}/{len(skus)}] {sku} — stopped: Amazon "
                                      f"matched this to an existing ASIN")
                        break
                    if prev_errors is not None and prev_errors == key:
                        entry["diagnosis"] += " — identical to the previous round, no progress."
                        outcome = "stuck"; diagnosis = entry["diagnosis"]
                        _app._af_step(jid, f"[{idx+1}/{len(skus)}] {sku} — stuck on: {', '.join(fields)}")
                        break
                    prev_errors = key
                    continue
                entry["diagnosis"] = f"Unclear outcome ({verdict}). Stopped for safety."
                outcome = "failed"; diagnosis = entry["diagnosis"]; break

            if _app._af_cancelled(jid):
                _app._af_step(jid, "Stopped by user.")
                break

            with _app._AF_JOBS_LOCK:
                j = _app._AF_JOBS.get(jid)
                if j:
                    j["results"].append({"sku": sku, "outcome": outcome,
                                         "diagnosis": diagnosis, "rounds": rounds})
                    j["done"] = len(j["results"])
                    s = j["summary"]
                    s[outcome] = s.get(outcome, 0) + 1
                    s["not_run"] = max(0, j["total"] - j["done"])

    _app._af_finish(jid)
