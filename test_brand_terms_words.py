# -*- coding: utf-8 -*-
"""Brand words are words, not letters (owner, 30 Sep 2026).

"branded keywords in the ppc analytics is not counting brand keywords as
words, it is counting a l t as separate letters". The save stores "alta" as one
word now, but letters stored before that fix stayed in ppc_brand_terms and a
one-letter word is a substring of nearly every search term. The one reader,
domain/ppc_view.brand_terms, ignores anything shorter than two letters.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TMP = tempfile.mkdtemp(prefix="brandw_")
CFG = os.path.join(TMP, "app.json")
json.dump({"accounts": [{"id": "a1"}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "b.db")
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


from domain import ppc_view as PV              # noqa: E402

# What the old save left behind for "alta", plus the real word.
PV.change_brand_terms(CFG, "a1", ["a", "l", "t", "alta"], [], "2026-09-30 10:00:00")
PV.change_brand_terms(CFG, "a2", ["Selvora"], [], "2026-09-30 10:00:00")
check("single letters are not brand words", PV.brand_terms(CFG, "a1"), ["alta"])
check("a normal word is kept (lower-cased)", PV.brand_terms(CFG, "a2"), ["selvora"])
brands = PV.brand_terms(CFG, "a1")
check("'ceiling fan' is NOT branded any more", bool(PV.is_branded("ceiling fan", brands)), False)
check("'alta ceiling fan' IS branded", bool(PV.is_branded("alta ceiling fan", brands)), True)

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
