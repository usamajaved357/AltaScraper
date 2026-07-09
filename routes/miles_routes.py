"""routes/miles_routes.py — Miles Lubricants harvest/generate endpoints, extracted from dashboard.py (Phase 3).

register(app, ...) injection pattern; route bodies moved VERBATIM (CLAUDE.md §10).
Injected shared helpers/state (all stay in dashboard.py for now): _miles_set_pref,
_miles_get_pref, CONFIG_PATH, SCRIPT, _MILES_STATE (shared run state), _active_account,
_miles_load_history, _miles_save_history, _run_lock, _running. Dependencies were
verified with an AST free-variable check (no undefined names).

Routes: POST /miles/sheet_pref, GET /miles/sheet_pref, POST /miles/upload,
        POST /miles/clear_history, POST /miles/stop, GET /miles/generate,
        GET /miles/optimize, GET /miles/run, GET /miles/results
"""
import json
import os
import re
import subprocess
import sys

from flask import request, jsonify, Response


def register(app, *, _miles_set_pref, _miles_get_pref, CONFIG_PATH, SCRIPT, _MILES_STATE,
             _active_account, _miles_load_history, _miles_save_history, _run_lock, _running):
    """Attach the /miles/* routes to the existing Flask app."""

    def _claim_run(max_seconds=600):
        """Self-healing busy-lock claim. Returns True if WE claimed the run, False only
        if a genuinely-live run is still going. On Render an SSE stream the proxy kills
        (or the user navigates away from) never runs its release `finally`, so
        _running['on'] can stay True forever and wedge every future harvest/generate with
        '[busy]'. This reclaims the lock when the previous run's process is already dead,
        or the run is older than max_seconds -- so a stuck lock heals itself instead of
        needing an app restart."""
        import time as _t
        with _run_lock:
            if _running.get("on"):
                proc = _running.get("proc")
                started = _running.get("started") or 0.0
                dead = (proc is None) or (proc.poll() is not None)
                too_old = (_t.time() - started) > max_seconds
                if not (dead or too_old):
                    return False            # a real run is genuinely in progress
            _running["on"] = True
            _running["started"] = _t.time()
            _running["proc"] = None
            return True

    @app.route("/miles/sheet_pref", methods=["POST"])
    def miles_sheet_pref_set():
        """Persist the output Sheet ID/tab so the user need not re-paste it each run."""
        b = request.get_json(force=True) or {}
        ok = _miles_set_pref(b.get("sheet", ""), b.get("tab", ""))
        return jsonify({"ok": bool(ok)})


    @app.route("/miles/sheet_pref", methods=["GET"])
    def miles_sheet_pref_get():
        """Return the saved output Sheet ID/tab for the active account (for pre-fill)."""
        return jsonify(_miles_get_pref())


    @app.route("/miles/upload", methods=["POST"])
    def miles_upload():
        """Receive the item-number list (parsed client-side from CSV/XLSX) and stash
        it for the harvest run. Body: {items:[...]}."""
        b = request.get_json(force=True) or {}
        items = [str(x).strip() for x in (b.get("items") or []) if str(x).strip()]
        # de-dup preserve order
        seen, clean = set(), []
        for it in items:
            if it not in seen:
                seen.add(it); clean.append(it)
        _MILES_STATE["items"] = clean
        done = _miles_load_history()
        already = [it for it in clean if it in done]
        return jsonify({"ok": True, "count": len(clean), "items": clean[:50],
                        "already_harvested": already})


    @app.route("/miles/clear_history", methods=["POST"])
    def miles_clear_history():
        """Forget which item numbers were harvested, so they can run again."""
        done = _miles_load_history()
        n = len(done)
        _miles_save_history(set())
        # ALSO clear the permanent text store -- otherwise items saved there are still
        # treated as 'done' and skipped even after clearing history (the reason
        # 'Clear harvested history' seemed not to work). Now it fully resets.
        store_n = 0
        try:
            _sp = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "miles_bundles_store.json")
            if os.path.exists(_sp):
                _sd = json.load(open(_sp, encoding="utf-8"))
                store_n = len(_sd) if isinstance(_sd, dict) else 0
                json.dump({}, open(_sp, "w", encoding="utf-8"))
        except Exception:
            pass
        return jsonify({"ok": True, "cleared": n, "store_cleared": store_n})


    @app.route("/miles/stop", methods=["POST"])
    def miles_stop():
        """Kill any in-flight harvest OR generation subprocess immediately, then
        release the busy lock so a new run can start."""
        _MILES_STATE["cancel"] = True
        # Kill the generator subprocess if one is running
        proc = _running.get("proc")
        if proc and proc.poll() is None:
            try:
                import signal as _sig
                proc.send_signal(_sig.SIGTERM)
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass
        try:
            with _run_lock:
                _running["on"] = False
        except Exception:
            _running["on"] = False
        _running["proc"] = None
        return jsonify({"ok": True, "killed": proc is not None})


    @app.route("/miles/generate")
    def miles_generate():
        """Run the generator's 'miles' mode: turn harvested bundles into Amazon
        draft listings (compliance + IP + copy). Streams the generator output."""
        _cfg_path = str(CONFIG_PATH)
        # scope to the active account's sheet + marketplace, like generate does
        try:
            _acc = _active_account()
        except Exception:
            _acc = None

        # user-provided output sheet/tab (override account defaults). Accept a bare
        # ID or a full Google Sheets URL.
        import re as _re
        def _sheet_id(s):
            s = (s or "").strip()
            m = _re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", s)
            return m.group(1) if m else s
        _user_sheet = _sheet_id(request.args.get("sheet", ""))
        _user_tab   = (request.args.get("tab", "") or "").strip()
        try:
            _user_limit = int(request.args.get("limit", "0") or "0")
        except ValueError:
            _user_limit = 0
        _use_ba = request.args.get("use_ba", "") == "1"

        def stream():
            # Log what we received so it's visible in the panel
            yield (f"data: [params] sheet='{_user_sheet[:20]}...' "
                   f"tab='{_user_tab or '(none)'}' "
                   f"limit={_user_limit or 'all'}\n\n")
            busy = not _claim_run()
            if busy:
                yield "data: [busy] a run is already in progress\n\n"
                yield "event: end\ndata: end\n\n"
                return
            try:
                # Do NOT hard-block on the local miles_bundles.json here. The engine's 'miles'
                # mode back-fills any uploaded SKU that's missing locally straight from its Drive
                # folder (bundle_from_drive reads the harvested PDFs/SDS), so DRIVE is the source
                # of truth -- generation works from the Drive folders even when this machine has
                # no local bundle (harvested elsewhere, or on Render). The engine itself prints
                # "No harvested bundles found" only if the local store AND Drive are both empty.
                extra = ["miles"]
                if _acc:
                    _aid = _acc.get("id") or ""
                    if _aid:
                        extra += ["--account-id", _aid]
                    _amkt = (_acc.get("default_marketplace") or "").strip().upper()
                    if _amkt in ("US", "UK", "GB"):
                        extra += ["--marketplace", _amkt]
                # Output sheet/tab: user input wins, else account default.
                _out_sheet = _user_sheet or (_acc.get("output_spreadsheet_id") if _acc else "") or ""
                _out_tab   = _user_tab or (_acc.get("output_tab") or _acc.get("output_worksheet") if _acc else "") or ""
                if _out_sheet:
                    extra += ["--sheet", _out_sheet]
                if _out_tab:
                    extra += ["--tab", _out_tab]
                if _user_limit and _user_limit > 0:
                    extra += ["--limit", str(_user_limit)]
                    yield f"data: [limit] generating up to {_user_limit} listing(s) this run\n\n"
                if _use_ba:
                    extra += ["--use-brand-analytics"]
                    yield "data: [BA] real Amazon search data (Brand Analytics) ENABLED for this run\n\n"
                if _acc and "image_template" in (_acc.get("features") or []):
                    extra += ["--auto-image"]
                    yield "data: [image] Auto main image ENABLED -- a templated main image will be generated per listing\n\n"
                if _user_sheet or _user_tab:
                    yield (f"data: [target] writing to sheet '{_out_sheet[:16]}...' / tab "
                           f"'{_out_tab or '(default)'}'\n\n")
                # GENERATION SET = every item folder in Drive (NOT the uploaded Excel,
                # which is HARVEST-ONLY). We scan Drive fresh each time and write the
                # full list to miles_items.json, so Generate never depends on a stale
                # file or on whether a spreadsheet was uploaded this session. run_miles
                # back-fills any missing from Drive and skips any SKU already present on
                # ANY tab -- so this builds exactly the missing listing copies.
                try:
                    import miles_import as _MG
                    _base_g = os.path.dirname(os.path.abspath(_cfg_path))
                    _cfg_g = json.load(open(_cfg_path, encoding="utf-8"))
                    _drv_g, _derr_g = _MG.build_drive_rw(_cfg_g, _base_g)
                    _all_items = _MG.list_all_item_folders(_drv_g, log=lambda m: None) if _drv_g else []
                    with open(os.path.join(_base_g, "miles_items.json"), "w", encoding="utf-8") as _itf:
                        json.dump(_all_items, _itf)
                    if _all_items:
                        yield (f"data: [items] {len(_all_items)} item folder(s) in Drive -- building the "
                               f"ones not already in the sheet (existing rows on ANY tab are skipped)\n\n")
                    else:
                        yield (f"data: [items] Drive scan returned nothing"
                               f"{(' ('+_derr_g+')') if _derr_g else ''} -- falling back to all "
                               f"locally-harvested items in the store\n\n")
                except Exception as _ie:
                    yield f"data: [items] could not scan Drive for item list: {_ie}\n\n"
                args = [sys.executable, "-u", SCRIPT] + extra
                yield f"data: [start] {' '.join(args)}\n\n"
                p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1,
                                     cwd=os.path.dirname(os.path.abspath(_cfg_path)))
                _running["proc"] = p
                for line in iter(p.stdout.readline, ""):
                    if line:
                        yield f"data: {line.rstrip()}\n\n"
                p.wait()
                yield f"data: [done] generation finished (exit {p.returncode})\n\n"
            except GeneratorExit:
                # The browser closed the SSE connection (navigated away / refreshed /
                # stale tab). Kill the subprocess if running, release the lock, and
                # RE-RAISE without yielding -- yielding here is what caused the noisy
                # 'generator ignored GeneratorExit' RuntimeError in the terminal.
                try:
                    _p = _running.get("proc")
                    if _p and _p.poll() is None:
                        _p.terminate()
                except Exception:
                    pass
                with _run_lock:
                    _running["on"] = False
                _running["proc"] = None
                raise
            except Exception as e:
                import traceback as _tb
                yield f"data: [error] {type(e).__name__}: {str(e)[:200]}\n\n"
                yield f"data:   {_tb.format_exc().splitlines()[-1][:200]}\n\n"
                with _run_lock:
                    _running["on"] = False
                _running["proc"] = None
                yield "event: end\ndata: end\n\n"
                return
            # normal completion: release lock and signal end
            with _run_lock:
                _running["on"] = False
            _running["proc"] = None
            yield "event: end\ndata: end\n\n"
        return Response(stream(), mimetype="text/event-stream")


    @app.route("/miles/optimize")
    def miles_optimize():
        """PHASE 2: pull real Search Query Performance for the live ASINs in the
        Miles sheet and rewrite the copy to front-load converting queries."""
        _cfg_path = str(CONFIG_PATH)
        try:
            _acc = _active_account()
        except Exception:
            _acc = None
        import re as _re
        def _sheet_id(s):
            s = (s or "").strip()
            m = _re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", s)
            return m.group(1) if m else s
        _user_sheet = _sheet_id(request.args.get("sheet", ""))
        _user_tab   = (request.args.get("tab", "") or "").strip()

        def stream():
            yield (f"data: [start] SQP optimize -- sheet='{_user_sheet[:16]}...' "
                   f"tab='{_user_tab or '(default)'}'\n\n")
            busy = not _claim_run()
            if busy:
                yield "data: [busy] a run is already in progress\n\n"
                yield "event: end\ndata: end\n\n"
                return
            try:
                extra = ["miles-optimize"]
                if _acc:
                    _aid = _acc.get("id") or ""
                    if _aid:
                        extra += ["--account-id", _aid]
                    _amkt = (_acc.get("default_marketplace") or "").strip().upper()
                    if _amkt in ("US", "UK", "GB"):
                        extra += ["--marketplace", _amkt]
                _out_sheet = _user_sheet or (_acc.get("output_spreadsheet_id") if _acc else "") or ""
                _out_tab   = _user_tab or (_acc.get("output_tab") or _acc.get("output_worksheet") if _acc else "") or ""
                if _out_sheet:
                    extra += ["--sheet", _out_sheet]
                if _out_tab:
                    extra += ["--tab", _out_tab]
                args = [sys.executable, "-u", SCRIPT] + extra
                yield f"data: [start] {' '.join(args)}\n\n"
                p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1,
                                     cwd=os.path.dirname(os.path.abspath(_cfg_path)))
                _running["proc"] = p
                for line in iter(p.stdout.readline, ""):
                    if line:
                        yield f"data: {line.rstrip()}\n\n"
                p.wait()
                yield f"data: [done] optimize finished (exit {p.returncode})\n\n"
            except GeneratorExit:
                try:
                    _p = _running.get("proc")
                    if _p and _p.poll() is None:
                        _p.terminate()
                except Exception:
                    pass
                with _run_lock:
                    _running["on"] = False
                _running["proc"] = None
                raise
            except Exception as e:
                import traceback as _tb
                yield f"data: [error] {type(e).__name__}: {str(e)[:200]}\n\n"
                yield f"data:   {_tb.format_exc().splitlines()[-1][:200]}\n\n"
                with _run_lock:
                    _running["on"] = False
                _running["proc"] = None
                yield "event: end\ndata: end\n\n"
                return
            with _run_lock:
                _running["on"] = False
            _running["proc"] = None
            yield "event: end\ndata: end\n\n"
        return Response(stream(), mimetype="text/event-stream")


    @app.route("/miles/run")
    def miles_run():
        """Stream the Miles harvest over SSE. Reads the stashed item numbers, runs
        the harvester (search -> match -> scrape -> download -> Drive -> bundle)."""
        # Read state in the request context (SSE generator runs outside it).
        _items = list(_MILES_STATE.get("items") or [])
        _skip_done = (request.args.get("skip_done", "1") == "1")
        _cfg_path = str(CONFIG_PATH)
        # Resolve the output target + account HERE (request context) so the harvest
        # can CHAIN generation once it finishes -- the SSE generator below runs
        # outside request context and can't call _active_account()/_miles_get_pref().
        try:
            _acc = _active_account()
        except Exception:
            _acc = None
        _pref = _miles_get_pref()

        def stream():
            if not _items:
                yield "data: [error] No item numbers uploaded. Upload a CSV/Excel first.\n\n"
                yield "event: end\ndata: end\n\n"
                return
            _my_token = None
            busy = not _claim_run()
            if not busy:
                _my_token = __import__("time").time()
                _running["miles_token"] = _my_token
            if busy:
                yield "data: [busy] a run is already in progress\n\n"
                yield "event: end\ndata: end\n\n"
                return
            try:
                try:
                    import miles_import as _M   # available for the whole harvest below
                except Exception as _ie:
                    yield f"data: [error] miles_import import failed: {_ie}\n\n"
                    yield "event: end\ndata: end\n\n"
                    return

                def _generate_missing():
                    """Harvest is done -> build listing copies for EVERY item folder in
                    Drive that is NOT already in the output sheet. The uploaded Excel is
                    HARVEST-ONLY; the generation set comes from Drive (all harvested
                    folders), and run_miles skips any SKU already present in the sheet
                    (replace_existing=False), so re-hitting Harvest never duplicates a
                    row -- it only fills in what's missing."""
                    yield "data: \n\n"
                    yield "data: [generate] scanning Drive for harvested item folders...\n\n"
                    _base_g = os.path.dirname(os.path.abspath(_cfg_path))
                    try:
                        _cfg_g = json.load(open(_cfg_path, encoding="utf-8"))
                    except Exception as _ce:
                        yield f"data: [error] cannot read config for generation: {_ce}\n\n"
                        return
                    _drv_g, _derr_g = _M.build_drive_rw(_cfg_g, _base_g)
                    if not _drv_g:
                        yield f"data: [error] cannot scan Drive for generation: {_derr_g}\n\n"
                        return
                    _all = _M.list_all_item_folders(_drv_g, log=lambda m: None)
                    if not _all:
                        yield "data: [generate] no item folders found in Drive -- nothing to generate.\n\n"
                        return
                    yield (f"data: [generate] {len(_all)} item folder(s) in Drive; building the ones "
                           f"not already in the sheet (existing rows are skipped)...\n\n")
                    try:
                        with open(os.path.join(_base_g, "miles_items.json"), "w", encoding="utf-8") as _f:
                            json.dump(_all, _f)
                    except Exception as _we:
                        yield f"data: [error] could not write item list for generation: {_we}\n\n"
                        return
                    # Account/sheet-scoped generation command (mirrors /miles/generate).
                    gen_extra = ["miles"]
                    if _acc:
                        _aid = _acc.get("id") or ""
                        if _aid:
                            gen_extra += ["--account-id", _aid]
                        _amkt = (_acc.get("default_marketplace") or "").strip().upper()
                        if _amkt in ("US", "UK", "GB"):
                            gen_extra += ["--marketplace", _amkt]
                    # The saved pref may hold a full Google Sheets URL -- extract the
                    # bare spreadsheet ID (the generator's --sheet expects an ID, not a
                    # URL). Mirrors _sheet_id() in /miles/generate.
                    _raw_sheet = (_pref.get("sheet") or (_acc.get("output_spreadsheet_id") if _acc else "") or "")
                    _sm = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", _raw_sheet)
                    _out_sheet = _sm.group(1) if _sm else _raw_sheet.strip()
                    _out_tab   = (_pref.get("tab") or ((_acc.get("output_tab") or _acc.get("output_worksheet")) if _acc else "") or "")
                    if _out_sheet:
                        gen_extra += ["--sheet", _out_sheet]
                    if _out_tab:
                        gen_extra += ["--tab", _out_tab]
                    if _acc and "image_template" in (_acc.get("features") or []):
                        gen_extra += ["--auto-image"]
                        yield "data: [image] Auto main image ENABLED for generated listings\n\n"
                    args = [sys.executable, "-u", SCRIPT] + gen_extra
                    yield f"data: [start] {' '.join(args)}\n\n"
                    _gp = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True, bufsize=1,
                                           cwd=_base_g)
                    _running["proc"] = _gp
                    for _line in iter(_gp.stdout.readline, ""):
                        if _line:
                            yield f"data: {_line.rstrip()}\n\n"
                    _gp.wait()
                    _running["proc"] = None
                    yield f"data: [done] generation finished (exit {_gp.returncode})\n\n"

                done = _miles_load_history()
                # Also treat anything already in the PERMANENT store as done -- its
                # text is saved, so there's no need to re-scrape it.
                try:
                    _app_dir = os.path.dirname(os.path.abspath(_cfg_path))
                    _store_path = os.path.join(_app_dir, "miles_bundles_store.json")
                    _store = json.load(open(_store_path, encoding="utf-8"))
                    if isinstance(_store, dict):
                        done = set(done) | set(_store.keys())
                except Exception:
                    pass
                items = _items
                if _skip_done:
                    # Verify each 'done' item's files STILL EXIST in Drive. If the user
                    # deleted the PDFs from Drive, re-harvest it instead of trusting the
                    # local history/text-store (the old bug: deleted-from-Drive items
                    # were skipped forever). If Drive can't be checked, DON'T silently
                    # skip everything -- surface why, and only skip items we can confirm
                    # are still present.
                    # Emit immediately so the log shows life while Drive auth happens.
                    yield "data: [start] connecting to Drive to check what's already harvested...\n\n"
                    _drv = None
                    _drv_err = ""
                    try:
                        _cfg_for_drv = json.load(open(_cfg_path, encoding="utf-8"))
                        _base_for_drv = os.path.dirname(os.path.abspath(_cfg_path))
                        _drv, _drv_err = _M.build_drive_rw(_cfg_for_drv, _base_for_drv)
                    except Exception as _de:
                        _drv = None; _drv_err = str(_de)[:160]
                    if _drv is None:
                        # Can't verify Drive -> do NOT skip on text-store/history alone,
                        # or the user can never re-harvest. Tell them and run everything.
                        yield (f"data: [note] Could not check Drive to confirm which items "
                               f"still have files{(' ('+_drv_err+')') if _drv_err else ''}; "
                               f"running all {len(items)} item(s) rather than skipping blindly.\n\n")
                    else:
                        skipped, _revived = [], []
                        _items_after = []
                        _newly_skipped = []                        # had Drive files but NOT in local history
                        # DRIVE is the source of truth for "already harvested": if the
                        # item's folder holds at least one file, skip it -- even when our
                        # LOCAL history / text-store never recorded it (cleared history,
                        # a different machine, or a prior run on another install). The
                        # old code only checked Drive for items already in `done`, so an
                        # item whose files WERE in Drive but absent from local history
                        # dropped into the else-branch and got needlessly re-harvested.
                        #
                        # Each check is 2 Drive list calls (network). STREAM the result of
                        # each item as it comes in -- if we accumulated and dumped after the
                        # loop, the log would sit on an empty box for many seconds while N
                        # items are checked silently (looked like "nothing is happening").
                        _ntotal = len(items)
                        yield (f"data: [check] verifying {_ntotal} item(s) against Drive "
                               f"(skip anything already harvested)...\n\n")
                        for _idx, it in enumerate(items, 1):
                            _one_log = []
                            _has = _M.item_has_drive_files(_drv, it,
                                                           log=lambda m: _one_log.append(str(m)))
                            for _cl in _one_log:                   # live per-item detail
                                yield f"data: {_cl}\n\n"
                            if _has:
                                skipped.append(it)
                                if it not in done:
                                    _newly_skipped.append(it)
                                    done.add(it)                   # sync local history to Drive
                            else:
                                if it in done:
                                    _revived.append(it)            # was 'done' but files gone
                                    done.discard(it)               # forget stale 'done'
                                _items_after.append(it)            # (re-)harvest it
                            if _idx % 25 == 0 and _idx != _ntotal:
                                yield f"data: [check] {_idx}/{_ntotal} checked...\n\n"
                        items = _items_after
                        # Persist history when Drive told us something new (files exist for
                        # items local history didn't know about).
                        if _newly_skipped:
                            _miles_save_history(done)
                            yield (f"data: Skipping {len(_newly_skipped)} item(s) whose files were "
                                   f"already in Drive (not in local history): "
                                   f"{', '.join(_newly_skipped[:20])}\n\n")
                        if _revived:
                            yield (f"data: Re-harvesting {len(_revived)} item(s) whose files were "
                                   f"deleted from Drive: {', '.join(_revived[:20])}\n\n")
                            _miles_save_history(done)
                            # also drop revived items from the permanent text store so
                            # they actually re-scrape (the store otherwise marks them done)
                            try:
                                _sp = os.path.join(os.path.dirname(os.path.abspath(_cfg_path)),
                                                   "miles_bundles_store.json")
                                _sd = json.load(open(_sp, encoding="utf-8"))
                                if isinstance(_sd, dict):
                                    for _it in _revived:
                                        _sd.pop(_it, None)
                                    json.dump(_sd, open(_sp, "w", encoding="utf-8"))
                            except Exception:
                                pass
                        if skipped:
                            yield (f"data: Skipping {len(skipped)} item(s) already saved "
                                   f"(files still present in Drive): "
                                   f"{', '.join(skipped[:20])}\n\n")
                if not items:
                    yield (f"data: [note] Nothing new to harvest -- all {len(_items)} uploaded item(s) "
                           "already have their files in Drive. Building any missing listings now...\n\n")
                    yield from _generate_missing()
                    with _run_lock:
                        if _running.get("miles_token") == _my_token:
                            _running["on"] = False
                    yield "event: end\ndata: end\n\n"
                    return

                # Count against the FULL uploaded list, not just the remaining items.
                # e.g. uploaded 146, 25 already harvested (skipped) -> the harvest of the
                # remaining 121 shows as [26/146] .. [146/146], so the numbers line up
                # with the sheet the user uploaded instead of restarting at [1/121].
                _orig_total  = len(_items)                 # full uploaded count (e.g. 146)
                _done_before = _orig_total - len(items)    # already harvested / skipped (e.g. 25)
                if _done_before > 0:
                    yield (f"data: [start] Miles harvest -- {_done_before} of {_orig_total} already "
                           f"harvested (skipped); harvesting the remaining {len(items)} "
                           f"as {_done_before + 1}-{_orig_total} of {_orig_total}\n\n")
                else:
                    yield f"data: [start] Miles harvest -- {_orig_total} item number(s)\n\n"
                import asyncio
                try:
                    import miles_import as _miles
                except Exception as e:
                    yield f"data: [error] miles_import import failed: {e}\n\n"
                    yield "event: end\ndata: end\n\n"
                    return

                cfg = json.load(open(_cfg_path, encoding="utf-8"))
                base_dir = os.path.dirname(os.path.abspath(_cfg_path))

                # Stream progress live by running per-item and yielding as we go.
                import miles_import as _M
                drive_service, derr = _M.build_drive_rw(cfg, base_dir)
                if derr:
                    yield f"data: [error] Drive unavailable -- files will NOT be saved: {derr}\n\n"
                    drive_service = None
                else:
                    yield "data: Drive connected -- files will be saved per item number.\n\n"

                results = {"products": [], "needs_review": [], "not_found": [], "errors": []}
                total = _orig_total              # count against the FULL uploaded list
                _MILES_STATE["cancel"] = False   # clear any stale cancel request
                for i, item in enumerate(items, 1):
                    _pos = _done_before + i      # position within the uploaded list (e.g. 26)
                    if _MILES_STATE.get("cancel"):
                        yield f"data: [stopped] cancelled after {_pos-1}/{total} item(s)\n\n"
                        break
                    yield f"data: [{_pos}/{total}] {item} -- searching...\n\n"
                    _item_log = []
                    try:
                        res = asyncio.run(_M.harvest_item(item, drive_service,
                                                          log=lambda m: _item_log.append(str(m))))
                    except Exception as e:
                        import traceback as _tb
                        for _l in _item_log:
                            yield f"data: {_l}\n\n"
                        results["errors"].append({"item": item, "message": f"{type(e).__name__}: {str(e)[:160]}"})
                        yield f"data: [error]   {item}: {type(e).__name__}: {str(e)[:160]}\n\n"
                        yield f"data:   (trace) {_tb.format_exc().splitlines()[-1][:160]}\n\n"
                        continue
                    # stream the harvester's own detailed lines (search diag, page size, pdfs)
                    for _l in _item_log:
                        yield f"data: {_l}\n\n"
                    st = res.get("status")
                    if st == _M.OK:
                        p = res["product"]
                        results["products"].append(p)
                        _nfiles = len(p.get("pdf_files", []))
                        # Only remember it as 'done' if we actually got files. A 0-file
                        # OK is a partial result -- let it re-run next time, don't skip.
                        if _nfiles > 0:
                            done.add(item)
                        yield (f"data:   OK -- '{(p.get('title') or '')[:45]}' | "
                               f"{_nfiles} file(s) | "
                               f"{'SDS' if p.get('sds_text') else 'no SDS'}"
                               f"{'' if _nfiles else '  (0 files -- will retry next run)'} | {res.get('message','')}\n\n")
                    elif st == _M.NEEDS_REVIEW:
                        results["needs_review"].append({"item": item, "message": res.get("message", "")})
                        yield f"data:   NEEDS_REVIEW -- {res.get('message','')}\n\n"
                    elif st == _M.NOT_FOUND:
                        results["not_found"].append({"item": item, "message": res.get("message", "")})
                        yield f"data:   NOT_FOUND -- {res.get('message','')}\n\n"
                    else:
                        results["errors"].append({"item": item, "message": res.get("message", "")})
                        yield f"data: [error]   {item}: {res.get('message','')}\n\n"

                _miles_save_history(done)
                _MILES_STATE["results"] = {
                    "ok": len(results["products"]),
                    "needs_review": results["needs_review"],
                    "not_found": results["not_found"],
                    "errors": results["errors"],
                    "products": results["products"],
                }
                # Persist harvested bundles into a PERMANENT store keyed by item
                # number (merge, never overwrite). This way an item harvested once is
                # kept forever -- you never have to re-harvest it to regenerate. The
                # 'latest run' file is also written for convenience.
                try:
                    _app_dir = os.path.dirname(os.path.abspath(_cfg_path))
                    _store_path = os.path.join(_app_dir, "miles_bundles_store.json")
                    # load existing permanent store
                    try:
                        _store = json.load(open(_store_path, encoding="utf-8"))
                        if not isinstance(_store, dict):
                            _store = {}
                    except Exception:
                        _store = {}
                    # merge this run's products in, keyed by item_number
                    for _p in results["products"]:
                        _key = _p.get("item_number") or _p.get("sku") or ""
                        if _key:
                            _store[_key] = _p
                    json.dump(_store, open(_store_path, "w", encoding="utf-8"))
                    # also write the latest-run file (back-compat)
                    _bundle_path = os.path.join(_app_dir, "miles_bundles.json")
                    json.dump(results["products"], open(_bundle_path, "w", encoding="utf-8"))
                except Exception:
                    pass
                yield (f"data: [done] harvested {len(results['products'])} | "
                       f"review {len(results['needs_review'])} | "
                       f"not found {len(results['not_found'])} | "
                       f"errors {len(results['errors'])}\n\n")
                # Harvest finished -> automatically build listing copies for every Drive
                # item folder not yet in the output sheet (the requested one-click flow).
                yield from _generate_missing()
            except GeneratorExit:
                # browser closed the SSE connection; kill any chained generation
                # subprocess, release lock if we own it, re-raise
                try:
                    _p = _running.get("proc")
                    if _p and _p.poll() is None:
                        _p.terminate()
                except Exception:
                    pass
                _running["proc"] = None
                with _run_lock:
                    if _running.get("miles_token") == _my_token:
                        _running["on"] = False
                raise
            except Exception as e:
                import traceback as _tb
                yield f"data: [error] {type(e).__name__}: {str(e)[:200]}\n\n"
                yield f"data:   {_tb.format_exc().splitlines()[-1][:200]}\n\n"
                try:
                    _p = _running.get("proc")
                    if _p and _p.poll() is None:
                        _p.terminate()
                except Exception:
                    pass
                _running["proc"] = None
                with _run_lock:
                    if _running.get("miles_token") == _my_token:
                        _running["on"] = False
                yield "event: end\ndata: end\n\n"
                return
            with _run_lock:
                # Only release if THIS run still owns the lock. A wedged old
                # stream finishing late must not clear a newer run's lock.
                if _running.get("miles_token") == _my_token:
                    _running["on"] = False
            yield "event: end\ndata: end\n\n"
        return Response(stream(), mimetype="text/event-stream")


    @app.route("/miles/results")
    def miles_results():
        """Return the last harvest's summary for the UI."""
        r = _MILES_STATE.get("results")
        if not r:
            return jsonify({"ok": False, "message": "no harvest run yet"})
        # don't ship the full product text blobs to the list view; summarise
        prods = [{"item_number": p.get("item_number"), "title": p.get("title"),
                  "pdf_count": len(p.get("pdf_files", [])),
                  "has_sds": bool(p.get("sds_text"))}
                 for p in r.get("products", [])]
        return jsonify({"ok": True, "summary": {
            "ok": r.get("ok", 0), "needs_review": r.get("needs_review", []),
            "not_found": r.get("not_found", []), "errors": r.get("errors", []),
            "products": prods}})
