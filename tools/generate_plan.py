"""What WOULD a generate run do? Answered without generating anything.

    "check and let me know if the current workflow of listing generation works
     while preventing the already created listing copies to be created again"

The arithmetic is in domain/generate_plan.py, shared with the /run/plan endpoint
the Generate screen uses -- so the command line and the screen cannot disagree
about what is about to happen (CLAUDE.md Rule 12).

It reads. It generates nothing, spends nothing and writes nothing.

    python tools/generate_plan.py                 # every connected account
    python tools/generate_plan.py jack_uk
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")


def show(cfg, wsid):
    from domain import generate_plan as GP
    p = GP.for_workspace(CONFIG_PATH, wsid, cfg)
    c = p["counts"]
    print("=" * 70)
    print("%s" % wsid)
    print("=" * 70)
    print("  already generated : %d SKUs, %d competitor ASINs"
          % (c["skus_on_record"], c["already_made"]))
    print("  input queue       : %d row(s)%s"
          % (c["queued"],
             ("  (imported %s)" % p["imported_at"]) if p.get("imported_at") else ""))
    print()
    print("  WOULD GENERATE    : %d" % c["generate"])
    print("  would skip        : %d  (already made)" % c["skip"])
    print("  repeated in queue : %d  (made once, by the first row)" % c["repeat"])
    print("  no ASIN in row    : %d" % c["no_asin"])
    print()
    print("  %s" % p["verdict"])
    if p.get("error"):
        print("  ERROR: %s" % p["error"])
    if p["generate"]:
        print("\n  to be generated:")
        for a in p["generate"][:30]:
            print("     ", a)
        if len(p["generate"]) > 30:
            print("      ...and %d more" % (len(p["generate"]) - 30))
    print()


def main():
    cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
    want = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if want:
        show(cfg, want)
        return 0
    import accounts as _acc
    for a in (_acc.load_accounts(cfg, CONFIG_PATH) or []):
        wsid = str(a.get("id") or "")
        if wsid:
            show(cfg, wsid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
