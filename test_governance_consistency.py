"""The development process is one consistent system (read.txt 29 Sep 2026, Priority 2).

"Do not create a second competing engineering process." The autonomous feature
workflow (.claude/skills/build-feature) orchestrates the existing skills,
agents, tools and docs. This keeps them honest with each other:
  - CLAUDE.md §19 lists exactly the skills and agents that exist;
  - build-feature names only skills, agents, tools and docs that exist;
  - the four autonomy levels are written down, and the plan-gate exception
    exists in CLAUDE.md Rule 7 and start-task step 9 together (never one alone);
  - no skill or agent still sends working files to the old checkout's active/.
Read-only; reads raw bytes.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


def src(p):
    return open(p, "rb").read().decode("utf-8")


CL = src("CLAUDE.md")
sec19 = CL[CL.index("## 19. CAPABILITIES"):CL.index("## 20.")]
skills_disk = sorted(d for d in os.listdir(".claude/skills")
                     if os.path.isfile(os.path.join(".claude/skills", d, "SKILL.md")))
agents_disk = sorted(f[:-3] for f in os.listdir(".claude/agents") if f.endswith(".md"))
sk_line = sec19[sec19.index("Skills (`.claude/skills/`):"):sec19.index("Agents (")]
ag_line = sec19[sec19.index("Agents (`.claude/agents/`):"):sec19.index("They are")]
check("CLAUDE.md lists every skill on disk",
      [s for s in skills_disk if s not in sk_line], [])
check("  and every agent", [a for a in agents_disk if a not in ag_line], [])

BF = src(".claude/skills/build-feature/SKILL.md")
named = set(re.findall(r"`([a-z][a-z-]+)`", BF))
known = set(skills_disk) | set(agents_disk)
unknown_names = sorted(n for n in named if "-" in n and n not in known)
check("build-feature names only skills/agents that exist", unknown_names, [])
paths = set(re.findall(r"`((?:docs|tools|data|routes|domain|auth|static)/[\w./-]+\.\w+)`", BF))
paths |= set(re.findall(r"(tools/[\w_]+\.py|run_tests\.py)", BF))
check("  and only files that exist", sorted(p for p in paths if not os.path.exists(p)), [])
for lv in ("**L1**", "**L2**", "**L3**", "**L4**"):
    check("  states autonomy level " + lv, lv in BF, True)

OM = src("docs/product-operating-model.md")
check("the operating model has the four levels",
      all("| %d |" % n in OM for n in (1, 2, 3, 4)), True)
check("  and names build-feature as the procedure", "build-feature" in OM, True)

ST = src(".claude/skills/start-task/SKILL.md")
check("plan-gate exception in CLAUDE.md Rule 7 and start-task together",
      ("build-feature" in CL[CL.index("## 7."):CL.index("## 8.")]) and ("EXCEPTION" in ST
                                                                       and "build-feature" in ST), True)
check("  and it never covers Level 3 or 4",
      "Level 3 real actions and Level 4 still wait" in ST
      and "Level 3 real actions and Level 4 (push, merge," in CL, True)

stale = []
for base in (".claude/skills", ".claude/agents"):
    for d, _dirs, files in os.walk(base):
        for f in files:
            if f.endswith(".md") and re.search(r"<main checkout>[/\\]active", src(os.path.join(d, f))):
                stale.append(os.path.join(d, f))
check("no skill/agent writes to the old checkout's active/", stale, [])

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\none process, consistent with itself")
