"""The generator's arguments are built by ONE set of functions (architecture batch A9).

/run/<mode> (routes/listing_routes.py) and the background preview queue
(listing/run_command.build_api_run_args) each spelled out the same two blocks:
the account's arguments (--account-id, sheets, gids, marketplace) and the
Preview/Submit scope (--skus, --minimal, the open sheet/tab, the brand view's
marketplace). Both now call listing/run_command.account_args and api_scope_args.

The reference below is the /run code as it was before A9, WORD FOR WORD, so this
proves the shared functions give exactly the same argv for every input shape --
including the awkward ones (no default marketplace, MX first in the list, GB,
a brand view with a profile on disk, empty values).
"""
import itertools
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


# ---- the pre-A9 /run code, verbatim (listing_routes.py run()/stream()) ----
def OLD_run_extra(mode, _scope_acc, _req_skus, _req_minimal, _scope_sheet, _scope_tab,
                  _scope_view, CONFIG_PATH):
    extra = ([] if mode == "generate"
             else ["api", "submit"] if mode == "api_submit"
             else ["api", "verify"] if mode == "api_verify"
             else [mode])
    if mode == "regen":
        _sid, _tab, _mkt = _scope_sheet, _scope_tab, "US"
        extra = ["regen"]
        if _req_skus: extra += ["--skus", _req_skus]
        if _sid: extra += ["--sheet", _sid]
        if _tab: extra += ["--tab", _tab]
        if _mkt: extra += ["--marketplace", _mkt]
    _acc = _scope_acc
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
    if mode in ("api", "api_submit", "api_verify"):
        _api_skus = _req_skus
        if _api_skus and "--skus" not in extra:
            extra += ["--skus", _api_skus]
        if _req_minimal and "--minimal" not in extra:
            extra += ["--minimal"]
        _sid = _scope_sheet
        _tab = _scope_tab
        _mkt = ""
        _vk = _scope_view
        if _vk:
            try:
                import glob as _glob, os as _os
                for _pf in _glob.glob(_os.path.join(_os.path.dirname(CONFIG_PATH), "brands", "*", "profile.json")):
                    _p = json.load(open(_pf, encoding="utf-8"))
                    if (_p.get("brand_name") or "") == _vk:
                        _mkt = _p.get("marketplace", "") or ""
                        break
            except Exception:
                pass
        if _sid:
            extra += ["--sheet", _sid]
        if _tab:
            extra += ["--tab", _tab]
        if _mkt:
            extra += ["--marketplace", _mkt]
    return extra


# ---- the new path: the same two steps, through the shared functions ----
from listing import run_command as RC


def NEW_run_extra(mode, acc, skus, minimal, sheet, tab, view, config_path):
    extra = ([] if mode == "generate"
             else ["api", "submit"] if mode == "api_submit"
             else ["api", "verify"] if mode == "api_verify"
             else [mode])
    if mode == "regen":             # this block is unchanged in the route
        extra = ["regen"]
        if skus: extra += ["--skus", skus]
        if sheet: extra += ["--sheet", sheet]
        if tab: extra += ["--tab", tab]
        extra += ["--marketplace", "US"]
    if acc:
        extra = RC.account_args(extra, acc)
    if mode in ("api", "api_submit", "api_verify"):
        extra = RC.api_scope_args(extra, skus=skus, minimal=minimal, sheet=sheet,
                                  tab=tab, view=view, config_path=config_path)
    return extra


import atexit, shutil
TMP = tempfile.mkdtemp(prefix="altarunargs_")
atexit.register(shutil.rmtree, TMP, True)
CFG = os.path.join(TMP, "config.json")
os.makedirs(os.path.join(TMP, "brands", "b1"))
json.dump({"brand_name": "Selvora", "marketplace": "US"},
          open(os.path.join(TMP, "brands", "b1", "profile.json"), "w"))

ACCS = [None, {},
        {"id": "jack_uk", "output_spreadsheet_id": "S", "output_tab": "T", "output_tab_gid": 5,
         "input_spreadsheet_id": "I", "input_tab_gid": 0, "default_marketplace": "uk"},
        {"id": "sheelady_us", "output_worksheet": "W", "marketplaces": ["MX", "ca", " us ", "UK"]},
        {"id": "x", "default_marketplace": "DE", "marketplaces": ["DE"]},
        {"id": "g", "default_marketplace": "gb"},
        {"id": "", "output_spreadsheet_id": "S2"}]
MODES = ["generate", "retry", "export", "regen", "api", "api_submit", "api_verify"]
n = 0
for mode, acc, skus, minimal, sheet, tab, view in itertools.product(
        MODES, ACCS, ["", "A,B"], [False, True], ["", "SS"], [None, "TT"],
        ["", "Selvora", "Nobody"]):
    old = OLD_run_extra(mode, acc, skus, minimal, sheet, tab, view, CFG)
    new = NEW_run_extra(mode, acc, skus, minimal, sheet, tab, view, CFG)
    n += 1
    if old != new:
        check("%s acc=%s skus=%r min=%s sheet=%r tab=%r view=%r"
              % (mode, (acc or {}).get("id"), skus, minimal, sheet, tab, view), new, old)
        break
print("  /run's argv identical for %d input combinations" % n)

print("=== the preview queue builds the same argv as /run for api / api_submit ===")
for mode, acc, skus, minimal, sheet, tab, view in itertools.product(
        ["api", "api_submit"], [a for a in ACCS if a], ["A"], [False, True],
        ["", "SS"], ["", "TT"], ["", "Selvora"]):
    q = RC.build_api_run_args(mode, script="gen.py", python_exe="py", skus=skus,
                              minimal=minimal, active_account=acc, active_sheet_id=sheet,
                              active_tab=tab, active_view=view, cfg={}, config_path=CFG)
    r = ["py", "-u", "gen.py"] + OLD_run_extra(mode, acc, skus, minimal, sheet, tab, view, CFG)
    if mode == "api":        # /run passes ["api"] for Preview too
        pass
    if q != r:
        check("queue == /run for %s %s" % (mode, acc.get("id")), q, r)
        break
else:
    check("queue == /run for every account shape", True, True)

print("=== the route really uses the shared functions ===")
src = open("routes/listing_routes.py", "rb").read().decode("utf-8")
check("/run calls account_args", "_rc.account_args(extra, _acc)" in src, True)
check("/run calls api_scope_args", "_rc.api_scope_args(" in src, True)
check("  and no longer spells the block out", '_acc.get("output_tab_gid")' in src, False)

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\none argument builder")
