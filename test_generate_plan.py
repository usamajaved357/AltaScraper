"""What a Generate run would do, answered before it does it.

    "check and let me know if the current workflow of listing generation works
     while preventing the already created listing copies to be created again"

The generator has always skipped products it had already made. The rule was
never the problem -- the problem was that the only way to SEE it working was to
press Generate and watch the log scroll, by which point the AI spend has begun.

The rules this has to get right, and each one costs money to get wrong:

  * an ASIN already generated is skipped
  * an ASIN appearing TWICE in the queue is made ONCE -- the first row takes the
    work and the second is skipped by it. A report that missed this overstates
    the work and the cost.
  * a full queue with NOTHING on record is called out in words. That is exactly
    what a broken duplicate check looks like, and it is indistinguishable from a
    genuine first run.
  * a store that could not be read produces no plan at all, rather than a
    confident "0 already made" that would invite a full regeneration
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from domain import generate_plan as GP  # noqa: E402

FAIL = []


def check(label, got, want):
    ok = got == want
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        FAIL.append(label)


def truthy(label, got):
    check(label, bool(got), True)


def row(asin="", url="", **kw):
    d = {"competitor_asin": asin, "amazon_url": url}
    d.update(kw)
    return d


print("== the ASIN is read the way the queue stores it ==")
check("competitor_asin is used first",
      GP.asin_of(row(asin="B0AAAAAAAA", url="https://amazon.co.uk/dp/B0BBBBBBBB")),
      "B0AAAAAAAA")
check("  falling back to the URL", GP.asin_of(row(url="https://amazon.co.uk/dp/B0CCCCCCCC")),
      "B0CCCCCCCC")
check("  and nothing when there is nothing", GP.asin_of(row()), "")
check("  a malformed asin field is not trusted",
      GP.asin_of(row(asin="not-an-asin", url="https://x/dp/B0DDDDDDDD")), "B0DDDDDDDD")

print("\n== an ASIN already generated is skipped ==")
p = GP.plan([row("B0AAAAAAAA"), row("B0BBBBBBBB")], {"B0AAAAAAAA"})
check("one skipped", p["counts"]["skip"], 1)
check("  one generated", p["counts"]["generate"], 1)
check("  and it names which", p["generate"], ["B0BBBBBBBB"])

print("\n== a repeat inside the queue is made ONCE ==")
# The rule is not "is it in the output" but "has it been seen YET" -- the run
# ADDS each ASIN as it goes, so the second row is skipped by the first.
p = GP.plan([row("B0NEWNEWNE"), row("B0NEWNEWNE"), row("B0NEWNEWNE")], set())
check("made once", p["counts"]["generate"], 1)
check("  the other two are repeats", p["counts"]["repeat"], 2)
# Reported separately from "already made": they are different situations and
# read differently to a person.
check("  and not counted as already made", p["counts"]["skip"], 0)

print("\n== a row with no ASIN is its own count ==")
p = GP.plan([row(), row("B0AAAAAAAA")], set())
check("counted", p["counts"]["no_asin"], 1)
check("  and does not become a generation", p["counts"]["generate"], 1)

print("\n== the verdicts say something useful ==")
truthy("an empty queue says to import",
       "Nothing is queued" in GP.plan([], {"B0AAAAAAAA"})["verdict"])
# THE DANGEROUS ONE. A full queue with nothing on record is what a broken
# duplicate check looks like, and it is indistinguishable from a first run.
v = GP.plan([row("B0AAAAAAAA")], set())["verdict"]
truthy("a queue with NOTHING on record is called out", "not seeing them" in v)
truthy("  and says a run would remake everything", "remake everything" in v)
truthy("  while allowing that a first run is legitimate", "first run" in v)
truthy("everything already made says so",
       "would make nothing new" in GP.plan([row("B0AAAAAAAA")], {"B0AAAAAAAA"})["verdict"])
truthy("all new says so",
       "are new" in GP.plan([row("B0BBBBBBBB")], {"B0AAAAAAAA"})["verdict"])
truthy("a mix gives both numbers",
       "would be skipped" in GP.plan([row("B0AAAAAAAA"), row("B0BBBBBBBB")],
                                     {"B0AAAAAAAA"})["verdict"])

print("\n== a store that could not be read produces no plan ==")
# WHAT THIS TEST ORIGINALLY ASSERTED WAS A FICTION, and the suite caught it.
#
# It called for_workspace() with a nonsense config path and expected an error.
# It passed alone and failed in the full suite, which is the signature of a
# state-dependent assumption -- and the assumption was wrong. An unknown path
# does not fail: the store opens an empty database quite happily. There is no
# honest way to make that read raise from here, so asserting that it does was
# testing a scenario that cannot occur.
#
# What IS real: load_existing_skus_and_asins CATCHES its own read errors and
# returns empty sets. Sensible for a run -- a generate should not die because a
# store hiccupped -- but it means an unreadable store and a fresh account give
# the same answer, and those need opposite responses. So the store is probed
# directly before a zero is trusted, and the VERDICT is the protection that
# actually fires.
got = GP.for_workspace("/nonexistent/config.json", "nosuchaccount", {})
truthy("an unknown account still returns a usable plan", "counts" in got)
truthy("  and says something rather than nothing", got.get("verdict"))
check("  claiming no prior work", got["counts"]["already_made"], 0)
# The disowning path exists for when a read genuinely does fail.
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "domain", "generate_plan.py"), encoding="utf-8").read()
truthy("a failed read is probed for, not assumed away", "_safe_records(ws)" in src)
truthy("  and a plan built on one disowns its own numbers",
       "Do not rely on the numbers" in src)

print("\n== it reads, and nothing else ==")
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "domain", "generate_plan.py"), encoding="utf-8").read()
code = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))
for banned in ("append_row", "update(", "insert", "delete", "put_listings",
               "messages.create", "urlopen"):
    check("it never %r" % banned, banned in code, False)
# And it calls the generator's OWN rule rather than a second copy of it.
truthy("it uses the generator's duplicate check",
       "load_existing_skus_and_asins" in code)
truthy("  and the generator's own output store", "output_ws" in code)

print("\n== the command line and the screen share it ==")
tool = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "tools", "generate_plan.py"), encoding="utf-8").read()
truthy("the CLI calls the shared module", "generate_plan as GP" in tool
       or "from domain import generate_plan" in tool)
rt = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "routes", "listing_routes.py"), encoding="utf-8").read()
truthy("and so does the endpoint", "generate_plan as _gp" in rt)
truthy("  which is /run/plan", '"/run/plan"' in rt)

print("\n%d failed" % len(FAIL))
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
