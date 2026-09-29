# -*- coding: utf-8 -*-
"""GOLDEN PAYLOADS: build_api_attributes must produce, byte for byte, what it
produced when these were recorded (docs/plans/build-api-attributes.md, step B0).

build_api_attributes turns one draft into the attributes Amazon judges. The
plan moves it out of the engine in small steps (B1-B6); each step must leave
every payload here identical. A difference is either a behaviour change the
owner approved (re-record, say why in the commit) or a bug in the move (revert).

    py -3.11 test_build_api_attributes_golden.py            check
    py -3.11 test_build_api_attributes_golden.py --record   re-record (never
                                                            to hide a difference)

Cases: tests_support/golden/build_api_attributes_cases.py -- hand-built schemas
(no real Amazon schema is kept in the repo), each run on UK and US, minimal mode
off and on. Measured line coverage of the function: about 70% of its lines.
KNOWN GAPS (add cases before moving these): the compliance-notes print, the
backfill of battery / num_batteries when the schema requires them with no
evidence, the final GHS safety net, lithium-cell counts, and the last wattage
sweep's dict branch.
"""
import contextlib
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests_support", "golden"))
os.chdir(HERE)
GOLDEN = os.path.join(HERE, "tests_support", "golden", "build_api_attributes.json")

# The generator reads CONFIG_PATH at import (attribute defaults, image hosting),
# so it is pointed at a throwaway folder holding a known attribute_defaults.json.
TMP = tempfile.mkdtemp(prefix="golden_attrs_")
json.dump({"KITCHEN": {"material": "Plastic", "blank": ""}},
          open(os.path.join(TMP, "attribute_defaults.json"), "w"))
os.environ["CONFIG_PATH"] = os.path.join(TMP, "app.json")
os.environ.pop("ALTASCRAPER_DB", None)

import amazon_listing_generator as G            # noqa: E402
import build_api_attributes_cases as C          # noqa: E402


def run_all():
    out = {}
    for name, row, pt, props, req, cfg in C.CASES:
        for mkt, mid in (("UK", C.UK), ("US", C.US)):
            for mm in (False, True):
                G.MARKETPLACE_ID = mid
                G.MINIMAL_MODE = mm
                with contextlib.redirect_stdout(io.StringIO()):
                    a = G.build_api_attributes(dict(row), pt, props, set(req), dict(cfg))
                out["%s|%s|%s" % (name, mkt, "minimal" if mm else "full")] = \
                    json.dumps(a, sort_keys=True, ensure_ascii=False)
    return out


got = run_all()
if "--record" in sys.argv:
    json.dump(got, open(GOLDEN, "w", encoding="utf-8"), indent=0, sort_keys=True, ensure_ascii=False)
    print("recorded %d payloads -> %s" % (len(got), GOLDEN))
    sys.exit(0)

want = json.load(open(GOLDEN, encoding="utf-8"))
fails = []
for k in sorted(set(want) | set(got)):
    if want.get(k) != got.get(k):
        fails.append(k)
        a, b = want.get(k) or "", got.get(k) or ""
        i = next((n for n in range(min(len(a), len(b))) if a[n] != b[n]), min(len(a), len(b)))
        print("  DIFFERENT %-44s at char %d:\n    was: %s\n    now: %s"
              % (k, i, a[max(0, i - 60):i + 80], b[max(0, i - 60):i + 80]))
print("%d golden payloads, %d identical, %d different" % (len(want), len(want) - len(fails), len(fails)))

# RULE 1 IS NEVER RECORDED AWAY. A golden file could otherwise pin a violation
# as "expected": these hold for every payload, whatever the recording says.
for k, v in sorted(got.items()):
    p = json.loads(v)
    if "merchant_suggested_asin" in p or "merchant_suggested_asin_type" in p:
        fails.append(k + " (merchant_suggested_asin)")
    ticked = k.startswith("exemption_ticked|")
    if ("supplier_declared_has_product_identifier_exemption" in p) != ticked:
        fails.append(k + " (exemption claimed %s the owner's tick)" % ("without" if not ticked else "ignoring"))
    ident = json.dumps(p.get("externally_assigned_product_identifier", ""))
    if "000000000000" in ident or "B0COMPETIT" in ident:
        fails.append(k + " (fake or competitor identifier)")
print("Rule 1 checked on %d payloads" % len(got))
print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
