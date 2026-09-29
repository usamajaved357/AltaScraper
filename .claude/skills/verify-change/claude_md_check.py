"""Runs ONLY the CLAUDE.md wording checks from test_barcode_and_exemption.py.

Why this exists: in a clean worktree (no config.json / database) that test
crashes on its data checks before it reaches the part that reads CLAUDE.md, so
a normal test run never checks CLAUDE.md there. This script lifts that block out
of the test file itself (so it can never drift from the test) and runs it.

Usage (from the repo root):  py -3.11 .claude/skills/verify-change/claude_md_check.py
Exit 0 = CLAUDE.md passes the test's wording checks. Read-only.
"""
import sys

TEST = "test_barcode_and_exemption.py"
START = 'C = open("CLAUDE.md"'
END = 'print("\\nFAILURES'

src = open(TEST, encoding="utf-8").read()
i = src.find(START)
j = src.find(END, i)
if i < 0 or j < 0:
    print(f"could not find the CLAUDE.md block in {TEST}: the test changed; update this script")
    sys.exit(2)
block = src[i:j]

fails = []


def truthy(label, got):
    ok = bool(got)
    print(f"  {label:<60} {'OK' if ok else 'FAIL'}")
    if not ok:
        fails.append(label)


def falsy(label, got):
    ok = not bool(got)
    print(f"  {label:<60} {'OK' if ok else 'FAIL'}")
    if not ok:
        fails.append(label)


exec(compile(block, TEST + " (CLAUDE.md block)", "exec"), {"truthy": truthy, "falsy": falsy, "FAILS": fails})

src_dash = open("dashboard.py", encoding="utf-8").read()
truthy("dashboard.py still says 'CLAUDE.md rule 1' (test_title_is_a_source.py)", "CLAUDE.md rule 1" in src_dash)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
