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


# EVERY TEST'S TEMPORARY FILES GO IN ONE PLACE, AND THAT PLACE IS DELETED.
#
# Most of these tests call tempfile.mkdtemp() at module level and never remove
# it -- forty-odd directories per run, several holding a SQLite database. They
# accumulate silently until the disk fills, and then nothing works and nothing
# says why:
#
#   31 Aug 2026   4,802 stale dirs, 1.56 GB, C: at 0 GB free
#                 sqlite3.OperationalError: unable to open database file
#    8 Sep 2026   1,146 stale dirs, C: at 0.63 GB free
#                 "Starting the CLR failed with HRESULT 8007000e"
#
# Fixing it in each test would be forty edits and the forty-first would forget.
# Python's tempfile reads TMPDIR/TEMP/TMP, so pointing those at a directory of
# our own catches every mkdtemp, NamedTemporaryFile and gettempdir in every
# test -- whatever prefix it uses, including the ones with no prefix at all --
# and one rmtree at the end takes the lot.
#
# It is scoped to the CHILD processes, not to this one: nothing outside the run
# is touched, and a test that writes somewhere absolute is unaffected. The run
# lock above already guarantees only one suite is running, so the directory
# cannot belong to anybody else.
_TMP_ROOT = None


def _tmp_env():
    """The environment the tests run in: their own scratch directory."""
    global _TMP_ROOT
    if _TMP_ROOT is None:
        _TMP_ROOT = tempfile.mkdtemp(prefix="alta_run_")
    env = dict(os.environ)
    env["TMPDIR"] = _TMP_ROOT
    env["TEMP"] = _TMP_ROOT
    env["TMP"] = _TMP_ROOT
    return env


def _tmp_cleanup():
    """Remove it. Never raises -- a file still held open must not fail the run."""
    global _TMP_ROOT
    if not _TMP_ROOT:
        return 0
    import shutil
    freed = 0
    try:
        for dirpath, _dirs, files in os.walk(_TMP_ROOT):
            for f in files:
                try:
                    freed += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
        shutil.rmtree(_TMP_ROOT, ignore_errors=True)
    except Exception:
        pass
    _TMP_ROOT = None
    return freed


def _run(cmd, cwd=ROOT, timeout=900):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace",
                           env=_tmp_env())
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


LOCK = os.path.join(ROOT, ".run_tests.lock")


def _claim_lock():
    """Refuse to run while another run is going, and say why.

    WHY: two suites at once produced a red that was not a fault. test_startup
    _speed.py times how long the app takes to build and fails over 6 seconds;
    on a quiet machine it measures about 4.1s, but with a second suite importing
    the app and hammering SQLite at the same time it went over and reported a
    regression that did not exist.

    A red that is not a fault is worse than no test: it is what teaches everyone
    to skim past red. So the second run stops and explains itself instead.

    A stale lock -- a run killed part-way -- is cleared rather than blocking
    forever: it names the pid so a real clash can still be seen.
    """
    try:
        if os.path.exists(LOCK):
            age = time.time() - os.path.getmtime(LOCK)
            who = ""
            try:
                who = open(LOCK, encoding="utf-8").read().strip()
            except Exception:
                pass
            if age < 3600:
                print("Another test run appears to be going (%s, started %d min "
                      "ago).\nTwo at once make the timing tests fail for no "
                      "reason -- see test_startup_speed.py.\nWait for it, or "
                      "delete %s if it is stale."
                      % (who or "unknown", age // 60, LOCK))
                return False
            print("(clearing a stale lock from %s)" % (who or "an earlier run"))
        open(LOCK, "w", encoding="utf-8").write("pid %d" % os.getpid())
    except Exception:
        pass          # never let the lock itself stop the tests running
    return True


def _release_lock():
    try:
        if os.path.exists(LOCK):
            os.remove(LOCK)
    except Exception:
        pass


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    if not _claim_lock():
        return 2

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
    # AND THE SCRATCH DIRECTORY GOES. Reported rather than silent, because the
    # number is the thing that used to accumulate: at ~35 MB a run it took the
    # disk to zero twice, and both times the failure was somewhere else
    # entirely -- "unable to open database file", then "Starting the CLR
    # failed". See _tmp_env above.
    _freed = _tmp_cleanup()
    if _freed > 1024 * 1024:
        print("cleaned up %.0f MB of test scratch files" % (_freed / 1024.0 / 1024.0))

    for name, code, out in failed:
        print("\n" + "-" * 70)
        print("FAILED: %s (exit %s)" % (name, code))
        lines = [l for l in out.splitlines() if l.strip()]
        # The assertion lines are what is wanted, not the whole run.
        hits = [l for l in lines if "FAIL" in l or "Error" in l or "error" in l]
        for l in (hits or lines)[-14:]:
            print("   " + l[:200])
        # A timing test that failed is worth a second look before it is believed:
        # it is the one kind that can go red because the machine was busy.
        if "startup" in name or "speed" in name:
            print("   NOTE: this one measures wall-clock time. Run it on its own"
                  " before believing it -- it measures about 4.1s against a 6s"
                  " ceiling on a quiet machine.")

    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        # BOTH, AND IN THIS ORDER. main() removes the scratch directory on the
        # normal path and reports what it freed; this catches the runs that end
        # any other way -- a Ctrl-C, an early return, an exception -- because
        # those are exactly the runs that used to leave the most behind.
        _tmp_cleanup()
        _release_lock()
