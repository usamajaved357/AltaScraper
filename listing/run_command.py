"""listing/run_command.py — build the generator CLI args for a per-listing Preview/Submit.

Extracted so the background preview-job worker builds the SAME command the live SSE
endpoint builds. This is a faithful port of routes/listing_routes.py stream()'s
api / api_submit arg-building: account scoping, dropshipping-sheet defaults, the
per-listing --skus / --minimal filter, and the brand-view marketplace. Pure function --
no Flask, no request context, no side effects.
"""
import glob as _glob
import json as _json
import os as _os


def build_api_run_args(mode, *, script, python_exe, skus="", minimal=False,
                       active_account=None, active_sheet_id="", active_tab="",
                       active_view="", cfg=None, config_path=""):
    """mode: 'api' (Preview) or 'api_submit' (Submit). Returns the full argv list
    (identical shape to what the SSE /run/<mode> endpoint runs for these modes)."""
    cfg = cfg or {}
    extra = (["api"] if mode == "api"
             else ["api", "submit"] if mode == "api_submit"
             else [mode])

    _acc = active_account
    if _acc:
        _acc_id = _acc.get("id") or ""
        if _acc_id and "--account-id" not in extra:
            extra += ["--account-id", _acc_id]
        _acc_sheet = _acc.get("output_spreadsheet_id") or ""
        _acc_tab = _acc.get("output_tab") or _acc.get("output_worksheet") or ""
        _acc_out_gid = str(_acc.get("output_tab_gid") or "")
        _acc_in_sheet = _acc.get("input_spreadsheet_id") or ""
        _acc_in_gid = str(_acc.get("input_tab_gid") or "")
        if _acc_sheet and "--sheet" not in extra:
            extra += ["--sheet", _acc_sheet]
        if _acc_tab and "--tab" not in extra:
            extra += ["--tab", _acc_tab]
        if _acc_out_gid and "--tab-gid" not in extra:
            extra += ["--tab-gid", _acc_out_gid]
        if _acc_in_sheet and "--input-sheet" not in extra:
            extra += ["--input-sheet", _acc_in_sheet]
        if _acc_in_gid and "--input-tab-gid" not in extra:
            extra += ["--input-tab-gid", _acc_in_gid]
        _acc_mkt = (_acc.get("default_marketplace") or "").strip().upper()
        if _acc_mkt not in ("US", "UK", "GB") and _acc.get("marketplaces"):
            for _mm in _acc["marketplaces"]:
                _mmu = str(_mm).strip().upper()
                if _mmu in ("US", "UK", "GB"):
                    _acc_mkt = _mmu
                    break
        if _acc_mkt and "--marketplace" not in extra:
            extra += ["--marketplace", _acc_mkt]
    else:
        # DROPSHIPPING (no active account): honour the user-assigned default sheets, if set.
        _ds_out = str(cfg.get("dropshipping_output_spreadsheet_id") or "").strip()
        _ds_otab = str(cfg.get("dropshipping_output_tab") or "").strip()
        _ds_ogid = str(cfg.get("dropshipping_output_tab_gid") or "").strip()
        _ds_in = str(cfg.get("dropshipping_input_spreadsheet_id") or "").strip()
        _ds_igid = str(cfg.get("dropshipping_input_tab_gid") or "").strip()
        if _ds_out and "--sheet" not in extra:
            extra += ["--sheet", _ds_out]
        if _ds_otab and "--tab" not in extra:
            extra += ["--tab", _ds_otab]
        if _ds_ogid and "--tab-gid" not in extra:
            extra += ["--tab-gid", _ds_ogid]
        if _ds_in and "--input-sheet" not in extra:
            extra += ["--input-sheet", _ds_in]
        if _ds_igid and "--input-tab-gid" not in extra:
            extra += ["--input-tab-gid", _ds_igid]

    # per-listing Preview/Submit: scope to these SKUs + the active sheet/tab/marketplace
    if skus and "--skus" not in extra:
        extra += ["--skus", skus]
    if minimal and "--minimal" not in extra:
        extra += ["--minimal"]
    if active_sheet_id:
        extra += ["--sheet", active_sheet_id]
    if active_tab:
        extra += ["--tab", active_tab]
    _mkt = ""
    if active_view:
        try:
            for _pf in _glob.glob(_os.path.join(_os.path.dirname(config_path), "brands", "*", "profile.json")):
                _p = _json.load(open(_pf, encoding="utf-8"))
                if (_p.get("brand_name") or "") == active_view:
                    _mkt = _p.get("marketplace", "") or ""
                    break
        except Exception:
            pass
    if _mkt:
        extra += ["--marketplace", _mkt]

    return [python_exe, "-u", script] + extra
