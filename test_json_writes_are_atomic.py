"""Stored JSON files are replaced atomically, never truncated and rewritten.

`json.dump(data, open(path, "w"))` empties the file before a byte is written,
so a crash, a full disk or a restart in that moment leaves it empty. For
config.json that is every credential; for the ASIN monitor it is every watched
ASIN and its baseline; for recipes, every saved treatment. domain/jsonstore
write_json_atomic (temp file + os.replace) is the one writer.

Reads source only for the scan; the behaviour check writes into a temp folder.
"""
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r" % (got,)))


print("\n1. no truncate-then-write of a JSON file in the app's own code")
SKIP_DIRS = {".git", ".venv", "__pycache__", "_merge_2026-07-04", "prototypes",
             "node_modules", ".claude"}
BAD = re.compile(r'json\.dump\([^\n]*open\([^\n]*["\']w["\']')
found = []
for root, dirs, files in os.walk(HERE):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in files:
        if not f.endswith(".py") or f.startswith("test_") or f.endswith(".baseline.py"):
            continue
        p = os.path.join(root, f)
        for i, line in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
            if BAD.search(line) and not line.lstrip().startswith("#") \
                    and "used to" not in line and "`" not in line:   # prose quoting it
                found.append("%s:%d" % (os.path.relpath(p, HERE), i))
check("json.dump(..., open(path, 'w')) one-liners", found, [])

# ...and the two-line form, `with open(p, "w") as f:` then `json.dump(..., f)`,
# which the one-liner scan missed (found 28 Sep 2026: the model-number counter,
# app_state.json, the Drive map, image instructions, Miles files). A write to a
# `tmp` path that is then os.replace()d IS atomic and is allowed; so is scripts/.
TWO = re.compile(r'with open\(([^\n]*?),\s*["\']w["\'][^\n]*\)\s+as\s+\w+:\s*\n\s*json\.dump\(')
found2 = []
for root, dirs, files in os.walk(HERE):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS | {"scripts", "tools"}]
    for f in files:
        if not f.endswith(".py") or f.startswith("test_") or f.endswith(".baseline.py"):
            continue
        p = os.path.join(root, f)
        s = open(p, encoding="utf-8", errors="replace").read()
        for m in TWO.finditer(s):
            if m.group(1).strip() in ("tmp", "_tmp", "tmp_path"):
                continue
            found2.append("%s:%d" % (os.path.relpath(p, HERE), s[:m.start()].count("\n") + 1))
check("with open(path, 'w') then json.dump -- two-line form", found2, [])

for rel, fn in (("monitor/asin_monitor.py", "def _save("),
                ("monitor/checker.py", "def _save_hist(")):
    src = open(os.path.join(HERE, rel), encoding="utf-8").read()
    body = src.split(fn)[1].split("\ndef ")[0]
    check(rel + " saves through write_json_atomic", "write_json_atomic" in body, True)

print("\n2. the monitor store round-trips through the atomic writer")
tmp = tempfile.mkdtemp(prefix="atomic_")
try:
    cfg = os.path.join(tmp, "config.json")
    from monitor import asin_monitor as AM
    AM._save(cfg, {"asins": [{"asin": "B0TEST0001"}]})
    got = json.load(open(os.path.join(tmp, "asin_monitor.json"), encoding="utf-8"))
    check("what was saved is what is read back", got, {"asins": [{"asin": "B0TEST0001"}]})
    check("no temp file is left behind",
          [f for f in os.listdir(tmp) if f.endswith(".tmp")], [])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n3. a replace refused for a moment (Windows: a reader has it open) is retried")
from domain import jsonstore as JS
tmp = tempfile.mkdtemp(prefix="atomic_")
real_replace = JS.os.replace
tries = []


def _flaky(a, b):
    tries.append(1)
    if len(tries) < 3:
        raise PermissionError("in use")
    return real_replace(a, b)


try:
    JS.os.replace = _flaky
    ok = JS.write_json_atomic(os.path.join(tmp, "x.json"), {"a": 1})
    check("the save succeeds after two refusals", (ok, len(tries)), (True, 3))
finally:
    JS.os.replace = real_replace
    shutil.rmtree(tmp, ignore_errors=True)

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
