"""The barcode conflict, told on the field that causes it.

    "The app highlights the Brand Name field red. But the ROOT CAUSE is the
     EAN -- the user is using a barcode that belongs to someone else's product.
     The brand mismatch is a CONSEQUENCE, not the cause."

    "Be the FIRST thing highlighted, not the brand field"

    "The stale error message makes it impossible to know if your fix worked
     without re-submitting to Amazon."

Amazon blames `brand` in attributeNames for this refusal. That is a correct
report of what Amazon said and the wrong place to send someone: changing the
brand cannot work, because the catalogue entry belongs to another product. The
barcode is the thing to change.
"""
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(*p):
    with io.open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


def nojs(s):
    s = re.sub(r"(?s:/\*.*?\*/)", "", s)
    return re.sub(r"(?m:^[ \t]*//[^\n]*)", "", s)


ERRJS = read("static", "js", "amazon_errors.js")
AF = nojs(read("static", "js", "autofix.js"))
PDP = nojs(read("static", "js", "pdp.js"))
CSS = read("static", "css", "drawer.css")

print("== the parser lives with the other Amazon prose (Rule 12) ==")
yes("amzIdConflict is in amazon_errors.js", "function amzIdConflict(" in ERRJS)
yes("  and so is the sentence it renders", "function amzIdConflictLine(" in ERRJS)
yes("  both are exported", "global.amzIdConflict" in ERRJS
    and "global.amzIdConflictLine" in ERRJS)
# A SECOND REGEX OVER THE SAME SENTENCE is how two readers of one message come
# to disagree about what it said.
check("  the editor does not parse the message itself",
      "matches the ASIN" in AF, False)

print("\n== what it will and will not claim ==")
# CLAUDE.md rule 4 forbids inventing a FIELD NAME out of message prose. The same
# caution applies to a VALUE: "the catalogue has X" is a statement about someone
# else's product, and being wrong about it sends the reader to the wrong field.
yes("the ASIN is taken only in Amazon's own format",
    "var ASIN_RE = /\\b(B0[A-Z0-9]{8})\\b/;" in ERRJS)
yes("  and dropped when it is not", "if (asin && !ASIN_RE.test(asin)) asin = \"\";" in ERRJS)
yes("the brand is taken only when the message really carries it",
    'var brand = "";' in ERRJS and "if (bm) brand = bm[1].trim();" in ERRJS)

# RUN THE REAL PARSER, on the message Amazon actually sent -- recorded in
# domain/barcode_clash.py from his own data, 26 Aug 2026.
REAL = ("The standard product ids (such as UPC, ISBN, EAN, or JAN codes) provided "
        "matches the ASIN B0H8Q3VMPD, but some of the attribute value(s) conflict "
        "with what is already in the Amazon catalogue. The catalogue brand is "
        "\"AltaboltaVoo\".")
NO_BRAND = ("The standard product ids (such as UPC, ISBN, EAN, or JAN codes) provided "
            "matches the ASIN B0H8Q3VMPD, but some of the attribute value(s) conflict.")
UNRELATED = "The value provided for attribute \"item_name\" exceeds the maximum."

import json as _json
# json.dumps, NOT repr: the message Amazon sends contains its own double quotes
# ("AltaboltaVoo"), and repr-then-swap-quotes closed the JS string early.
harness = """
%s
const out = [];
out.push(amzIdConflict([{message: %s}], {barcode: "4545644574860"}));
out.push(amzIdConflict([{message: %s}], {barcode: "4545644574860"}));
out.push(amzIdConflict([{message: %s}], {barcode: "4545644574860"}));
out.push(amzIdConflictLine(out[0]));
console.log(JSON.stringify(out));
""" % (ERRJS.replace("})(window);", "})(globalThis);"),
       _json.dumps(REAL), _json.dumps(NO_BRAND), _json.dumps(UNRELATED))

fd, path = tempfile.mkstemp(suffix=".js", dir=HERE)
os.close(fd)
try:
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(harness)
    res = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        print("  node failed:", res.stderr[:400])
        FAILS.append("parser would not run")
        got = [None, None, None, ""]
    else:
        import json
        got = json.loads(res.stdout.strip().splitlines()[-1])
finally:
    try:
        os.remove(path)
    except OSError:
        pass

real, nobrand, other, line = got
print("\n  -- run against the message Amazon actually sent --")
check("the ASIN comes out", (real or {}).get("asin"), "B0H8Q3VMPD")
check("  and the catalogue brand", (real or {}).get("brand"), "AltaboltaVoo")
check("  and the barcode", (real or {}).get("barcode"), "4545644574860")
# THE SAME MESSAGE WITHOUT A BRAND IN IT must not produce one.
check("no brand in the message, no brand claimed", (nobrand or {}).get("brand"), "")
check("  but the ASIN is still reported", (nobrand or {}).get("asin"), "B0H8Q3VMPD")
check("an unrelated error is not read as a conflict", other, None)
# "Be one clear sentence, not a paragraph of Amazon legal text"
yes("the sentence names the ASIN", "B0H8Q3VMPD" in (line or ""))
yes("  and the owning brand", "AltaboltaVoo" in (line or ""))
yes("  and the barcode", "4545644574860" in (line or ""))
check("  and it is one sentence", (line or "").count(".") <= 2, True)

print("\n== where it is drawn ==")
#     "Appear directly under the EAN input field with a red border"
yes("the barcode row wraps its control", 'class="dw2-idwrap' in AF)
yes("  and is flagged when there is a conflict", '(_idc ? " bad" : "")' in AF)
yes("  with the warning under the box", 'class="dw2-idclash"' in AF)
yes("the input itself goes red", ".dw2-idwrap.bad .ed{" in CSS
    and "border-color:var(--red)" in CSS)
yes("  and the warning has a red border",
    re.search(r"\.dw2-idclash\{[^}]*border:1px solid var\(--red\)", CSS) is not None)
#     "The brand field can show a secondary note ... but the EAN field is where
#      the user needs to act first."
yes("the brand gets a note, not the alarm", 'class="dw2-idnote"' in AF
    and "Change the barcode, not this." in AF)
yes("  and only when Amazon named a catalogue brand", "(_idc && _idc.brand)" in AF)
# Quieter on purpose -- dressing the symptom in the same red is what sent people
# to the wrong field.
yes("  drawn quieter than the warning above it",
    re.search(r"\.dw2-idnote\{[^}]*color:var\(--muted\)", CSS) is not None)

print("\n== the stored error stops reading as current ==")
#     "After the user changed the brand ... the error banner still shows the old
#      message. Show a note: 'You've changed this field -- Preview or Submit
#      again to verify the fix'"
yes("edited fields are remembered per listing", "let PDP_EDITED_FIELDS" in PDP)
yes("  cleared when a different listing opens",
    "PDP_EDITED_FIELDS = new Set();" in PDP)
# Amazon complains about `brand`, not about "Brand". Without the map the two
# never meet and nothing is ever marked.
yes("the app's column names are mapped to Amazon's",
    "const PDP_COL_TO_ATTR" in PDP and '"Brand": "brand"' in PDP)
yes("  the saver records the edit", "pdpFieldEdited(sku, target, key)" in
    nojs(read("static", "js", "autofix.js")))
yes("an answered complaint is marked, not rewritten",
    "const answered = i =>" in PDP and "pdp-errstale" in PDP)
# THE MESSAGE IS LEFT ALONE. It records what was SENT; editing it would
# misreport what Amazon was actually told.
yes("  Amazon's own wording is still printed", "esc(i.message" in PDP)
yes("  the headline says how many are since edited", "since edited" in PDP)
yes("  and the banner redraws at once, not at the next render",
    'querySelector(".pdp-errors")' in PDP)

# MEASURED IN CHROME on draft 7.96_3Days_B0841BD4JY with the reply planted and
# then restored:
#   parser      {asin: B0H8Q3VMPD, brand: AltaboltaVoo, barcode: 4545644574860}
#   input       border rgb(242,114,114), wrapper .bad
#   warning     5px under the box, red border, one sentence naming all three
#   brand note  "Amazon's catalogue has AltaboltaVoo for this barcode..."
#   banner      2 problems -> "1 since edited" the moment Brand was saved,
#               the other complaint untouched, Amazon's wording still there
#   no page errors

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
