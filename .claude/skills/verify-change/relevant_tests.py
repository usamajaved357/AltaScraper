"""Lists the root test files relevant to a set of changed files.

A test is relevant if it mentions the changed file by path or file name, or
imports its module (e.g. `routes.listing_routes`, `listing_routes`). Tests in
this repo mostly read the source files they check by name, so this is a good
first cut; it is not a guarantee.

Usage (from the repo root):
    py -3.11 .claude/skills/verify-change/relevant_tests.py static/js/listings.js routes/listing_routes.py
    py -3.11 .claude/skills/verify-change/relevant_tests.py --changed --base <task-base>
        # files changed since the task base (HEAD when start-task ran) + uncommitted
    py -3.11 .claude/skills/verify-change/relevant_tests.py --changed
        # no --base: merge-base with origin/main (on the long-running development
        # branch that includes every earlier task -- pass --base instead)
Prints one test file per line, then a count. Read-only.
"""
import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scope_check import GIT  # noqa: E402  (same git discovery)


def changed_files(base=None):
    if not base:
        r = subprocess.run([GIT, "merge-base", "HEAD", "origin/main"], capture_output=True, text=True)
        base = r.stdout.strip() or "HEAD"
    out = set()
    for args in (["diff", "--name-only", base], ["ls-files", "--others", "--exclude-standard"]):
        r = subprocess.run([GIT, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
        out |= {l.strip() for l in r.stdout.splitlines() if l.strip()}
    return sorted(out)


def needles(path):
    p = path.replace("\\", "/")
    leaf = os.path.basename(p)
    stem, ext = os.path.splitext(leaf)
    n = {p, leaf}
    if ext == ".py":
        mod = p[:-3].replace("/", ".")
        n |= {mod, "import " + stem, "from " + mod, stem + ".py"}
    return n


def main(argv):
    base = None
    if "--base" in argv:
        i = argv.index("--base")
        if i + 1 >= len(argv):
            print("--base needs a commit")
            return 2
        base = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    changed_mode = (not argv) or argv == ["--changed"]
    files = changed_files(base) if changed_mode else argv
    files = [f for f in files if not os.path.basename(f).startswith("test_")]
    tests = sorted(glob.glob("test_*.py") + glob.glob("test_*.js"))
    direct = [] if changed_mode else sorted({f for f in argv if os.path.basename(f).startswith("test_")})
    hits = set(direct)
    for t in tests:
        try:
            s = open(t, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for f in files:
            if any(x in s for x in needles(f)):
                hits.add(t)
                break
    for t in sorted(hits):
        print(t)
    print(f"-- {len(hits)} relevant test file(s) for {len(files)} changed file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
