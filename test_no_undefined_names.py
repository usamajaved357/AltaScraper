"""No Python module in the app uses a name that is defined nowhere.

WHY THIS EXISTS. `routes/listing_routes.py` read `_state_account`, a variable
nothing defined, so any request with no account open raised NameError
(known-issues #2). An earlier refactor left `_req_account` behind the same way
and /run/generate answered 500 on every call. Both were found by reading code,
days later. pyflakes finds this class of bug in seconds and says nothing about
anything else -- only its "undefined name" message is checked here, so style
and unused imports cannot turn this red (Milestone 1, 28 Sep 2026).

Every file is also compiled, so one that does not parse at all fails here too.

Skipped, loudly, when pyflakes is not installed rather than passing silently.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

DIRS = ["routes", "domain", "data", "listing", "api", "auth", "services",
        "monitor", "config", "repositories"]

# EVERY APP MODULE AT THE ROOT TOO, not only the two big ones: the root holds
# shims and working modules (miles_template.py, ppc_module.py, ...) the app
# imports. Left out: tests and probes, baselines, and PATCH_*.py, which are
# fragments meant to be pasted into another file and cannot stand alone.
def _root_modules():
    return sorted(f for f in os.listdir(HERE)
                  if f.endswith(".py")
                  and not f.startswith(("test_", "probe_", "PATCH_"))
                  and "baseline" not in f)


# A FILE THAT DOES NOT PARSE is worse than an undefined name, and pyflakes
# words that a dozen different ways -- so every file is compiled here instead.
_BAD = ("undefined name",)


def _unparseable(targets):
    out = []
    for t in targets:
        files = [t] if t.endswith(".py") else [
            os.path.join(dp, f) for dp, _dn, fs in os.walk(t)
            if "__pycache__" not in dp for f in fs if f.endswith(".py")]
        for fp in files:
            try:
                with open(fp, "rb") as fh:
                    compile(fh.read(), fp, "exec")
            except SyntaxError as e:
                out.append("%s:%s: does not parse: %s" % (fp, e.lineno, e.msg))
    return out


def main():
    try:
        import pyflakes  # noqa: F401
    except ImportError:
        print("pyflakes is not installed -- this check could not run.")
        return 125            # run_tests.py reports this as "could not run"
    targets = [os.path.join(HERE, d) for d in DIRS if os.path.isdir(os.path.join(HERE, d))]
    targets += [os.path.join(HERE, f) for f in _root_modules()]
    p = subprocess.run([sys.executable, "-m", "pyflakes"] + targets,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    bad = [l for l in (p.stdout + p.stderr).splitlines()
           if any(k in l for k in _BAD)]
    bad += _unparseable(targets)
    for l in bad:
        print("  " + l.replace(HERE + os.sep, ""))
    print("%d undefined name(s) or unparseable file(s) in %d targets"
          % (len(bad), len(targets)))
    print("FAILURES: %d" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
