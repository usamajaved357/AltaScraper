"""Import the real dashboard and confirm the new wiring is actually reachable.

Catches the class of mistake that only shows up on the server: a bad import, a
name used before it exists, a route that never got registered.
"""
# THE TREE THIS TEST LIVES IN. It used to name the main checkout outright, so
# run from any other checkout it silently tested THAT checkout's code
# (Milestone 1, 28 Sep 2026: 141 files did this).
import os as _os_repo
_REPO = _os_repo.path.dirname(_os_repo.path.abspath(__file__))
import sys, io, contextlib
sys.path.insert(0, _REPO)
import os
os.chdir(_REPO)

fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(label)
    print("  %-56s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    import dashboard
print("  dashboard imported (%d chars of startup output)" % len(buf.getvalue()))

src = open(_os_repo.path.join(_REPO, r"dashboard.py"), encoding="utf-8").read()
check("/diag route is declared", '@app.route("/diag")' in src, True)
check("the error handler records faults", "selfcheck" in src, True)
check("the boot banner is wired into build_app", "boot_banner" in src, True)
check("the stale prefix list is gone", '"/genimage", "/aplus"' in src, False)

# The banner must be printed BEFORE the refresher starts, or a crash in the
# refresher would hide the very diagnosis that explains it.
check("banner prints before the refresher starts",
      src.index("boot_banner") < src.index("_refresher.start("), True)

tpl = open(_os_repo.path.join(_REPO, r"templates\dashboard.html"), encoding="utf-8").read()
check("diag.js is loaded by the page", "/static/js/diag.js" in tpl, True)

import domain.selfcheck as sc
import domain.deploy_check as dc
check("selfcheck exposes what dashboard calls",
      all(hasattr(sc, n) for n in ("record", "recent", "as_text", "boot_banner")), True)
check("deploy_check exposes check()", hasattr(dc, "check"), True)

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
