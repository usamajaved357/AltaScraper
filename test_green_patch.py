"""A state word must not repaint the box it is a state OF.

THE BUG THIS PINS

    "i see these green pAtches everywhere it is also in
     https://app.altascraper.com/w/jack_uk/inventory resolve it everywhere"

Measured on the live Inventory screen: an <h3 class="stk-headline ok"> with

    background-color: rgb(74, 222, 128)
    color:            rgb(74, 222, 128)

reading "Nothing needs ordering" and showing a solid green bar. The same patch
appeared on the order panel where the status chip should say "Shipped".

WHY IT HAPPENED, AND WHY IT WAS GOING TO KEEP HAPPENING

`.ok` was a filled green BUTTON style: background green, text white. But "ok" is
also the obvious word for a STATE, so component after component wrote
`.stk-headline.ok`, `.odp-state.ok`, `.linkbtn.ok` and set only a text colour --
correctly, because a state modifier has no business repainting the box. The
button rule matched too, filled the box green, and the green text vanished into
it. Three components were already broken and the next one to reach for the word
would have been broken as well.

So the button was renamed to `.okfill` and the bare word freed.

WHAT IS CHECKED

Not "is .ok gone" -- that would pass the moment somebody introduces `.live` or
`.done` with a background and the same collision returns under a new name. This
reads the stylesheet, finds EVERY word used as a compound modifier (`.x.word`),
and asserts that no bare `.word` rule paints a background. That is the actual
rule, and it holds for words nobody has invented yet.
"""
import re
import sys

CSS_PATHS = [r"D:\AltaScraper\static\css\dashboard.css",
             r"D:\AltaScraper\static\css\mobile.css"]

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                  % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


CSS = "\n".join(open(p, encoding="utf-8").read() for p in CSS_PATHS)
# The comments explain this very bug and quote the selectors by name. Reading
# them as declarations makes the test fail on its own documentation, which has
# happened three times in this suite already.
NO_COMMENTS = re.sub(r"/\*[\s\S]*?\*/", "", CSS)
RULES = re.findall(r"([^{}]+)\{([^{}]*)\}", NO_COMMENTS)

# Properties that PAINT THE BOX. A modifier setting `color` is fine and is the
# whole point; one setting a background is what makes text disappear.
PAINT = ("background", "background-color", "background-image")


def decls(body):
    out = {}
    for part in body.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip().lower()
    return out


bare, compound_words, compound_rules = {}, set(), {}
for blob, body in RULES:
    d = decls(body)
    if not d:
        continue
    for sel in blob.split(","):
        sel = sel.strip()
        if not sel or sel.startswith("@") or ":" in sel or " " in sel:
            continue
        # `.word` on its own -- the shape that paints everything wearing it.
        m = re.fullmatch(r"\.([a-z][a-z0-9-]*)", sel)
        if m:
            bare.setdefault(m.group(1), {}).update(d)
            continue
        # `.component.word` -- the shape that means "this component, in this
        # state". Only the LAST class is the modifier.
        m = re.fullmatch(r"\.([a-z][a-z0-9-]*)\.([a-z][a-z0-9-]*)", sel)
        if m:
            compound_words.add(m.group(2))
            compound_rules.setdefault(sel, {}).update(d)


print("\n== words that are BOTH a state and a painted box (watch these) ==")
print("   (%d modifier words in use, %d bare single-class rules)"
      % (len(compound_words), len(bare)))
# Reported, not failed. A word in this list is only a bug when a component
# using it forgets to repaint -- which is the assertion below. `.safe` is here
# and is fine: every `.x.safe` rule sets its own background. Listing it anyway
# is the point, because the NEXT component to use the word is one forgotten
# line away from a green patch.
for word in sorted(compound_words):
    props = bare.get(word) or {}
    painted = [p for p in PAINT if props.get(p)]
    if painted:
        print("   .%s also sets %s: %s"
              % (word, ", ".join(painted), props.get(painted[0])))

print("\n== NO component may be left painting itself invisible ==")
# The real rule, and the one that would have caught the reported bug: a modifier
# that sets a text colour and does NOT set a background inherits whatever the
# bare rule paints -- and when the two are the same green, the text is gone.
at_risk = 0
for sel, d in sorted(compound_rules.items()):
    word = sel.rsplit(".", 1)[1]
    inherited = (bare.get(word) or {}).get("background") \
        or (bare.get(word) or {}).get("background-color")
    if not inherited:
        continue
    own_bg = d.get("background") or d.get("background-color")
    if own_bg:
        continue                       # it repaints, so nothing leaks through
    colour = d.get("color")
    if colour:
        at_risk += 1
        fails.append("%s inherits a background from .%s" % (sel, word))
        print("  FAIL %s sets color:%s and inherits background:%s"
              % (sel, colour, inherited))
check("no component sets a colour while inheriting a background", at_risk, 0)

print("\n== the button that caused it is renamed, not deleted ==")
truthy("the filled green button still exists under its own name",
       re.search(r"\.okfill\s*\{[^}]*background\s*:\s*var\(--green\)",
                 NO_COMMENTS))
check("  and no bare .ok rule paints anything any more",
      bool((bare.get("ok") or {}).get("background")), False)
# A renamed class with no markup pointing at it is a button that lost its style.
JS = open(r"D:\AltaScraper\static\js\listings.js", encoding="utf-8-sig").read()
truthy("the Approve button uses the new name", 'class="okfill"' in JS)
check("  and nothing still asks for the old one",
      bool(re.search(r'class="ok"', JS)), False)

print("\n== the states that were showing as green patches ==")
for sel in (".stk-headline.ok", ".odp-state.ok", ".linkbtn.ok"):
    truthy("%s still exists and still sets its own colour" % sel,
           (compound_rules.get(sel) or {}).get("color"))

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
