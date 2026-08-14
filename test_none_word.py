"""The word "None", stored as though it were a value.

THE SYMPTOM: the compliance panel read

    IP: forbidden phrase — compatible with None

There is no such phrase. The forbidden phrase was "compatible with"; "None" was
the NEXT CELL, joined onto it by a panel that concatenates the notes.

WHERE IT COMES FROM. The generator's own prompt asks the model for "battery /
electrical / chemical flags or None", so the model writes the word and it is
stored as content. 361 cells in this database carry one -- 193 in compliance
notes, 168 in the VOC source -- and every one is then displayed, searched and
concatenated as though somebody had typed it.

FIXED AT BOTH ENDS, because 361 rows already exist:
  * nothing new is written -- the storage boundary drops a value that IS the
    word
  * and the panel reads defensively, so the rows already stored stop showing it

AND ONLY WHEN IT IS THE WHOLE VALUE. A compliance note that genuinely begins
"None — operates at 240 V AC mains voltage; no batteries" is a real sentence
about a real product. There is one in this database. It must survive.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from data.column_map import header_dict_to_row

print("=== nothing new is stored as the word ===")
r = header_dict_to_row({"SKU": "X-1", "Compliance Notes": "None"})
check("a note that is exactly None becomes empty", r.get("compliance_notes"), "")
for w in ["none", "NONE", " None ", "null", "NaN", "n/a", "undefined"]:
    r = header_dict_to_row({"SKU": "X", "Compliance Notes": w})
    check("  %-12r too" % w, r.get("compliance_notes"), "")

print("\n=== but a real sentence survives ===")
REAL = "None — operates at 240 V AC mains voltage; no batteries, no hazardous materials"
r = header_dict_to_row({"SKU": "X", "Compliance Notes": REAL})
check("a note that BEGINS with None is untouched", r.get("compliance_notes"), REAL)
r = header_dict_to_row({"SKU": "X", "Compliance Notes": "Nonelectrical parts only"})
check("and a word that merely contains it", r.get("compliance_notes"),
      "Nonelectrical parts only")
r = header_dict_to_row({"SKU": "X", "Title": "None More Black T-Shirt"})
check("  including in a title", r.get("title"), "None More Black T-Shirt")

print("\n=== a genuine null is still a null, not an empty string ===")
# "no value recorded" and "recorded as blank" are different facts, and the
# numeric columns already depend on the difference.
r = header_dict_to_row({"SKU": "X", "Compliance Notes": None})
check("None the value stays NULL", r.get("compliance_notes"), None)

print("\n=== the panel reads defensively too, for the 361 already stored ===")
JS = open("static/js/listings.js", encoding="utf-8").read()
truthy("there is a reader that drops the word", "function _noneless" in JS)
truthy("  and the IP panel uses it", "_noneless(r.notes)" in JS)
truthy("  on both fields it joins", "_noneless(r.comp_notes)" in JS)
# The same care: only the whole value.
truthy("it only matches the WHOLE value",
       "/^(none|null|nan|undefined)$/i" in JS)

print("\n=== and the regulator is no longer an object ===")
# {"UK": "OPSS / UKCA ...", "US": "CPSC / UL / ETL"} put through esc() printed
# the literal "[object Object]" beside every rule on the same panel.
truthy("the marketplace's own regulator is picked", "g[mkt]" in JS)
truthy("  with the others named rather than dropped",
       'Object.keys(g).map' in JS)
truthy("  and a plain string still works", 'typeof g === "string"' in JS)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
