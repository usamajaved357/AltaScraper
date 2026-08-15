"""Run every test and report a number that means something.

    py -3.11 run_tests.py            everything
    py -3.11 run_tests.py sales      only files whose name contains "sales"

WHY THIS EXISTS

A full run used to report six failures that were not failures. Five of the
`test_*.py` files were one-off SP-API probes that call the live Amazon API and
exit non-zero whenever an account is not authorised for that product type; a
sixth needed two file paths on the command line. So the honest answer to "do the
tests pass" was "forty-six do, and six are not tests", which nobody can hold in
their head -- and a suite that always shows red is a suite whose red is ignored.

Those five are now `probe_*.py`, alongside the probe scripts that were already
named that way, and this runner never touches them. What is left is tests: they
need no network, no credentials and no arguments, and any red here is real.

test_useredit.js is the one exception and it is handled rather than skipped: it
reads two JSON fixtures captured from the real /users/list and /users/me, so the
runner generates them into a temporary directory first and passes them in. A
test that only runs when someone remembers the incantation is a test that stops
being run.
"""
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable or "python"


def _find(prefix, ext):
    return sorted(f for f in os.listdir(ROOT)
                  if f.startswith(prefix) and f.endswith(ext))


def _run(cmd, cwd=ROOT, timeout=900):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or ""), time.time() - t0
    except subprocess.TimeoutExpired:
        return 124, "TIMED OUT after %ss" % timeout, time.time() - t0
    except Exception as e:            # a missing interpreter, mostly
        return 125, "COULD NOT RUN: %s" % e, time.time() - t0


def _fixtures():
    """Capture the two JSON files test_useredit.js needs. Returns paths or None."""
    gen = os.path.join(ROOT, "make_useredit_fixtures.py")
    if not os.path.exists(gen):
        return None
    d = tempfile.mkdtemp(prefix="alta_fixtures_")
    a = os.path.join(d, "users_list.json")
    b = os.path.join(d, "users_me.json")
    code, out, _ = _run([PY, gen, a, b])
    if code != 0 or not (os.path.exists(a) and os.path.exists(b)):
        print("  (could not capture the users fixtures: %s)" % out.strip()[-200:])
        return None
    return a, b


# Tests that need an argument, and what to give them.
EXTRA_ARGS = {}


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else ""

    fx = _fixtures()
    if fx:
        EXTRA_ARGS["test_useredit.js"] = list(fx)

    jobs = []
    for f in _find("test_", ".py"):
        jobs.append((f, [PY, os.path.join(ROOT, f)]))
    for f in _find("test_", ".js"):
        jobs.append((f, ["node", os.path.join(ROOT, f)] + EXTRA_ARGS.get(f, [])))
    if only:
        jobs = [j for j in jobs if only.lower() in j[0].lower()]

    if not jobs:
        print("nothing matches %r" % only)
        return 1

    print("Running %d test files%s\n" % (len(jobs), (" matching %r" % only) if only else ""))
    failed, skipped, slow = [], [], []
    for name, cmd in jobs:
        code, out, secs = _run(cmd)
        if secs > 20:
            slow.append((name, secs))
        if code == 0:
            print("  %-34s ok    %5.1fs" % (name, secs))
        elif code == 125:
            skipped.append((name, out.strip()[:120]))
            print("  %-34s SKIP  %5.1fs  %s" % (name, secs, out.strip()[:60]))
        else:
            failed.append((name, code, out))
            print("  %-34s FAIL  %5.1fs  (exit %s)" % (name, secs, code))

    print("\n" + "=" * 70)
    print("%d files, %d passed, %d failed%s"
          % (len(jobs), len(jobs) - len(failed) - len(skipped), len(failed),
             (", %d could not run" % len(skipped)) if skipped else ""))
    probes = _find("probe_", ".py")
    if probes and not only:
        print("(%d probe_*.py scripts were not run: they call the live Amazon API "
              "and are diagnostics, not tests)" % len(probes))
    if slow:
        print("slowest: " + ", ".join("%s %.0fs" % s for s in
                                      sorted(slow, key=lambda x: -x[1])[:3]))

    for name, code, out in failed:
        print("\n" + "-" * 70)
        print("FAILED: %s (exit %s)" % (name, code))
        lines = [l for l in out.splitlines() if l.strip()]
        # The assertion lines are what is wanted, not the whole run.
        hits = [l for l in lines if "FAIL" in l or "Error" in l or "error" in l]
        for l in (hits or lines)[-14:]:
            print("   " + l[:200])

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
