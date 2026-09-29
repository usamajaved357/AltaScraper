# -*- coding: utf-8 -*-
"""The lessons register stays true (BUG -> LESSON -> PREVENTION, 29 Sep 2026).

docs/lessons.md maps bug CLASSES to their permanent prevention. This test
keeps it honest, so a lesson cannot be claimed without the check behind it:
  * every class has Pattern, Evidence, Prevention, Status, Applies when
  * Status is PREVENTED / PARTIAL / DOCUMENTED; PREVENTED and PARTIAL name a
    prevention; PARTIAL and DOCUMENTED say what is still not caught
  * every prevention file named exists; every "rule X" is a real guard rule
  * every guard rule that cites a lesson cites one that exists
  * every commit cited as evidence exists (when git is available)
  * from 29 Sep 2026 on, a FIXED entry in docs/known-issues.md names its
    regression test (test_*) or browser check (tools/browser_*) -- the
    per-bug record the workflow requires (older entries are not re-judged)
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


import arch_rules as A                          # noqa: E402

TEXT = open(os.path.join(HERE, "docs", "lessons.md"), encoding="utf-8").read()
FIELDS = ("Pattern", "Evidence", "Prevention", "Status", "Applies when")


def parse(text):
    out = {}
    for block in re.split(r"(?m)^## ", text)[1:]:
        name = block.split("\n", 1)[0].strip()
        if not name.startswith("L-"):
            continue
        fields = {}
        for m in re.finditer(r"(?m)^- (%s): (.*)$" % "|".join(re.escape(f) for f in FIELDS), block):
            fields[m.group(1)] = m.group(2).strip()
        out[name] = fields
    return out


def files_named(s):
    return re.findall(r"((?:tools/)?(?:test_|browser_)[\w]+\.(?:py|js))", s)


LESSONS = parse(TEXT)
print("== the register is well formed ==")
check("there are lessons", len(LESSONS) >= 5, True)
for name, f in LESSONS.items():
    check("%s has every field" % name, [x for x in FIELDS if not f.get(x)], [])
    status = (f.get("Status") or "").split()[0] if f.get("Status") else ""
    check("%s status is known" % name, status in ("PREVENTED", "PARTIAL", "DOCUMENTED"), True)
    named = files_named(f.get("Prevention", ""))
    if status in ("PREVENTED", "PARTIAL"):
        check("%s names a prevention" % name, bool(named), True)
    if status in ("PARTIAL", "DOCUMENTED"):
        check("%s says what is still not caught" % name, "--" in f.get("Status", ""), True)
    missing = [n for n in named if not os.path.exists(os.path.join(HERE, *n.split("/")))
               and not os.path.exists(os.path.join(HERE, "tools", n))]
    check("%s: every prevention file exists" % name, missing, [])
    rules = re.findall(r"rule ([a-z][a-z-]+)", f.get("Prevention", ""))
    check("%s: every guard rule named is real" % name, [r for r in rules if r not in A.RULES], [])

print("\n== the guard's rules and the lessons point at each other ==")
cited = {m for d in A.RULES.values() for m in re.findall(r"Lesson (L-[a-z-]+)", d)}
check("every lesson a guard rule cites exists", sorted(cited - set(LESSONS)), [])
used = {r for f in LESSONS.values() for r in re.findall(r"rule ([a-z][a-z-]+)", f.get("Prevention", ""))}
check("the rules added from lessons are named by a lesson",
      sorted({"swallowed-write-failure", "config-path-literal"} - used), [])

print("\n== evidence is real, never invented ==")
shas = sorted({s for f in LESSONS.values() for s in re.findall(r"\b([0-9a-f]{7})\b", f.get("Evidence", ""))})
check("evidence cites commits", len(shas) >= 10, True)
git = None
gd = os.path.expandvars(r"%LOCALAPPDATA%\GitHubDesktop")
if os.path.isdir(gd):
    apps = sorted(d for d in os.listdir(gd) if d.startswith("app-"))
    if apps:
        cand = os.path.join(gd, apps[-1], "resources", "app", "git", "cmd", "git.exe")
        git = cand if os.path.exists(cand) else None
if git:
    missing = [s for s in shas if subprocess.run([git, "-C", HERE, "cat-file", "-e", s + "^{commit}"],
                                                 capture_output=True).returncode != 0]
    check("every commit cited as evidence exists", missing, [])
else:
    print("  (git not found: commit existence not checked)")

print("\n== from 29 Sep 2026, a FIXED bug names its test ==")
KI = open(os.path.join(HERE, "docs", "known-issues.md"), encoding="utf-8").read()
entries = re.split(r"(?m)^(?=- |\d+\. |## )", KI)
dated = [e for e in entries if re.search(r"FIXED[^\n]{0,40}(29|30) Sep 2026|FIXED[^\n]{0,40}[0-9]{1,2} (Oct|Nov|Dec) 2026", e)]
check("there are dated FIXED entries to judge", len(dated) >= 3, True)
bare = [e.strip().splitlines()[0][:90] for e in dated
        if not re.search(r"test_[\w]+\.(py|js)|tools/browser_[\w]+\.py", e)]
check("each names a regression test or a browser check", bare, [])

print("\n== the checks catch a bad entry (self-test) ==")
BAD = ("## L-made-up\n- Pattern: x\n- Evidence: deadbee (no such commit)\n"
       "- Prevention: test_does_not_exist.py, rule no-such-rule\n- Status: PARTIAL\n- Applies when: y\n")
b = parse(BAD)["L-made-up"]
check("a missing prevention file is found", [n for n in files_named(b["Prevention"])
                                            if not os.path.exists(os.path.join(HERE, n))], ["test_does_not_exist.py"])
check("an invented guard rule is found",
      [r for r in re.findall(r"rule ([a-z][a-z-]+)", b["Prevention"]) if r not in A.RULES], ["no-such-rule"])
check("a PARTIAL with no stated gap is found", "--" in b["Status"], False)
if git:
    check("an invented commit is found",
          subprocess.run([git, "-C", HERE, "cat-file", "-e", "deadbee^{commit}"], capture_output=True).returncode != 0, True)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
