"""A test reads a FEATURE, not a file (Milestone 4, tests_support/README.md).

Two things are checked here:

1. THE MANIFEST TELLS THE TRUTH. Every file listed for a feature exists, and is
   really part of the app -- a JS/CSS part is linked from templates/dashboard.html
   in the listed order, a template part is included by its original, a Python
   part is imported by its original. A manifest that listed a file the app never
   loads would let a test pass on code nobody runs.
2. THE HOOK WORKS, in both languages, and only for what it should: a text read
   of a split original returns the joined feature; a binary read, and any other
   file, come back untouched. Tried on a PRACTICE manifest in separate processes,
   so the real one is never touched.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SUP = os.path.join(HERE, "tests_support")
fails = []


def truthy(label, cond):
    print("  %-74s %s" % (label, "OK" if cond else "FAIL"))
    if not cond:
        fails.append(label)


def raw(rel):
    """The file itself, never through the hook (binary read)."""
    with open(os.path.join(HERE, *rel.split("/")), "rb") as fh:
        return fh.read().decode("utf-8")


print("== the manifest tells the truth ==")
with open(os.path.join(SUP, "features.json"), "rb") as fh:
    M = {k: v for k, v in json.loads(fh.read().decode("utf-8")).items() if not k.startswith("_")}
truthy("the seven big files are all listed", len(M) == 7)
HTML = raw("templates/dashboard.html")
for key, parts in M.items():
    truthy("%s lists itself" % key, key in parts)
    for rel in parts:
        truthy("  %s exists" % rel, os.path.exists(os.path.join(HERE, *rel.split("/"))))
    if len(parts) < 2:
        continue
    if key.endswith((".js", ".css")):
        pos = [HTML.find("/" + rel) for rel in parts]
        truthy("  every part of %s is loaded by the page" % key, all(p >= 0 for p in pos))
        truthy("  ...in the listed order", pos == sorted(pos))
    elif key.endswith(".html"):
        orig = raw(key)
        for rel in parts[1:]:
            inc = rel.split("templates/", 1)[-1]
            truthy("  %s is included by the page" % inc, ('include "%s"' % inc) in orig)
    elif key.endswith(".py"):
        orig = raw(key)
        for rel in parts[1:]:
            mod = rel[:-3].replace("/", ".")
            truthy("  %s is imported by %s" % (mod, key),
                   re.search(r"(from|import)\s+%s\b" % re.escape(mod), orig) is not None)

print("\n== the hook works, and only where it should ==")
d = tempfile.mkdtemp(prefix="feat_")
practice = os.path.join(d, "features.json")
with open(practice, "w", encoding="utf-8") as fh:
    json.dump({"static/js/sales.js": ["static/js/sales.js", "static/js/salescharts.js"]}, fh)
env = dict(os.environ)
env["ALTA_FEATURES_JSON"] = practice
env["PYTHONPATH"] = SUP
env["NODE_OPTIONS"] = "--require " + os.path.join(SUP, "feature_read.js")

py = subprocess.run([sys.executable, "-c", (
    "import io\n"
    "t = open('static/js/sales.js', encoding='utf-8').read()\n"
    "b = open('static/js/sales.js', 'rb').read().decode('utf-8')\n"
    "o = io.open('static/js/pnl.js', encoding='utf-8').read()\n"
    "print(int('function salesCombo(' in t), int('function salesCombo(' in b), int('function pnlRender(' in o))\n")],
    cwd=HERE, env=env, capture_output=True, text=True)
got = (py.stdout or "").split()
truthy("Python: a text read of the original gets the whole feature", got[:1] == ["1"])
truthy("Python: a binary read gets the file alone", got[1:2] == ["0"])
truthy("Python: another file is untouched", got[2:3] == ["1"])

js = subprocess.run(["node", "-e", (
    "const fs=require('fs');"
    "const t=fs.readFileSync('static/js/sales.js','utf8');"
    "const b=fs.readFileSync('static/js/sales.js').toString('utf8');"
    "const o=fs.readFileSync('static/js/pnl.js','utf8');"
    "console.log(+t.includes('function salesCombo('), +b.includes('function salesCombo('), +o.includes('function pnlRender('));")],
    cwd=HERE, env=env, capture_output=True, text=True)
got = (js.stdout or "").split()
truthy("Node: a text read of the original gets the whole feature", got[:1] == ["1"])
truthy("Node: a buffer read gets the file alone", got[1:2] == ["0"])
truthy("Node: another file is untouched", got[2:3] == ["1"])

print("\n== the runner turns it on ==")
RT = raw("run_tests.py")
truthy("run_tests.py puts tests_support on PYTHONPATH", 'env["PYTHONPATH"] = sup' in RT)
truthy("run_tests.py preloads feature_read.js in Node", "feature_read.js" in RT and "NODE_OPTIONS" in RT)

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\nall feature-source checks passed")
