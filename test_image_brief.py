"""The facts about the product have to survive the rewrite.

A better product spec alone did not fix the pictures, and this is why: the spec
is handed to a prompt model that REWRITES it into an evocative photography brief.
What that model drops first is exactly what matters -- "NO teeth", "12 cm long",
"four slots, not five" -- because they read as dull constraints in a paragraph
about light and mood. So they are appended AFTER the rewrite, verbatim.
"""
import sys
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

def truthy(l, g):
    check(l, bool(g), True)

from domain import ai_providers as A

SPEC = """1. FORM & PROPORTIONS: a flat steel slashing blade, gently curved.
2. MATERIAL: forged carbon steel, matte grey, lightly pitted.
4. COLOURS: blade bare steel; handle black.

8. SCALE — HOW BIG IS IT REALLY: approximately 38 cm end to end, held in one
hand, about the length of a forearm.

9. EDGES, PROFILE AND WORKING PARTS: the cutting edge is plain and bevelled on
one side only. There are exactly 2 mounting holes in the tang.

10. WHAT IS NOT THERE: the blade is plain-edged with NO teeth and NO serrations.
There is no guard, no second handle and no wheels.
"""

print("=== the facts that must not be paraphrased away ===")
out = A.hard_constraints(SPEC)
truthy("something is produced", out)
truthy("it is labelled as overriding", "NON-NEGOTIABLE" in out)
truthy("  and says not to add anything unlisted",
       "not add any feature" in out.lower())
truthy("  and that an absent feature must not appear", "must not appear" in out)

print("\n  -- the absences, which are what get invented --")
truthy("NO teeth survives", "NO teeth" in out)
truthy("  NO serrations too", "NO serrations" in out)
truthy("  no guard", "no guard" in out)
truthy("  no second handle", "no second handle" in out)

print("\n  -- the scale, which is why a hand tool renders giant --")
truthy("the real size survives", "38 cm" in out)
truthy("  and what it is held with", "one" in out and "hand" in out)

print("\n  -- and the counts --")
truthy("the exact count survives", "exactly 2 mounting holes" in out)

print("\n=== but not the whole spec, or it is just the spec again ===")
check("the colour section is left to the prompt writer", "handle black" in out, False)
check("  and the material section", "forged carbon steel" in out, False)
# The preamble is deliberately long; what matters is that the SPEC lines kept
# are only the ones that carry facts, not the whole description again.
_kept = [l for l in out.splitlines() if l.startswith("- ")]
truthy("  only a handful of lines are carried over", 0 < len(_kept) <= 12)

print("\n=== it is safe on anything ===")
check("no spec, nothing appended", A.hard_constraints(""), "")
check("  None too", A.hard_constraints(None), "")
check("  and a spec with nothing worth keeping",
      A.hard_constraints("A nice bottle. It is blue. The label is centred."), "")
truthy("a spec with NO headings still keeps its absences",
       "no teeth" in A.hard_constraints(
           "It is a blade. It has no teeth at all and no guard.").lower())
long_spec = "\n".join("10. WHAT IS NOT THERE: no thing %d" % i for i in range(80))
truthy("a runaway spec is capped rather than pasted whole",
       len(A.hard_constraints(long_spec).splitlines()) < 50)

print("\n=== and it is actually wired into the pipeline ===")
import inspect
src = inspect.getsource(A.run_pipeline)
truthy("run_pipeline appends it", "hard_constraints(product_spec)" in src)
truthy("  AFTER the prompt is written, not before",
       src.index("enhance_prompt(") < src.index("hard_constraints("))

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
