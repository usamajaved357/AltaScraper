"""A box that cannot scroll must never be told to keep the scroll to itself.

THE BUG THIS PINS

`overscroll-behavior:contain` means: when this box has run out of room to
scroll, do NOT hand the leftover scroll to the page behind it. On a box that
really scrolls -- a drawer, a dropdown with a height limit -- that is exactly
right, and it stops a flick reaching the end of a list and then yanking the
whole page.

On a box that can NEVER scroll it is a trap. The browser treats any box with an
`overflow` value other than `visible` as a scrolling box, including
`overflow:hidden`, which is used all over this app purely to clip content to a
card's rounded corners. Put the two together and you have told the browser
"this frame owns the wheel" about a frame that never moves. The wheel goes in
and nothing comes out.

`.ltwrap` -- the rounded frame around the listings table -- was in that state.
Every listing on the Listings screen sits inside it, so putting the cursor
anywhere over the list froze the page; moving it into the margin outside the
frame and scrolling worked again. Reported as:

    "when i place my cursor in this area and scroll up or down the screen does
     not move, but when i take my cursor outside of these border the screen is
     able to scroll"

WHY THIS TEST IS NOT A STRING MATCH

Asserting `.ltwrap` is absent from one particular line would pass the moment
somebody adds the same pair to a different box, and the same freeze comes back
somewhere else. So this reads the stylesheet, finds EVERY selector that asks
for containment, and checks that each one is genuinely scrollable: a height cap
AND overflow auto or scroll. That is the actual rule, and it holds for boxes
that do not exist yet.
"""
import re
import sys

CSS_PATH = r"D:\AltaScraper\static\css\dashboard.css"
JS_PATH = r"D:\AltaScraper\static\js\listings.js"

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


CSS = open(CSS_PATH, encoding="utf-8").read()

# Comments carry the explanation of this very bug, including the words
# "overscroll-behavior" and ".ltwrap". Reading them as declarations would make
# the test fail on its own documentation -- which has happened here before.
NO_COMMENTS = re.sub(r"/\*[\s\S]*?\*/", "", CSS)

# Flat rule blocks. A rule nested in an @media still matches, because its own
# body has no braces in it; the @media's opening line simply never forms a
# match of its own and is skipped.
RULES = re.findall(r"([^{}]+)\{([^{}]*)\}", NO_COMMENTS)


def decls(body):
    out = {}
    for part in body.split(";"):
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        out[k.strip().lower()] = v.strip().lower()
    return out


# One selector may be styled by several rules (.drawer sets its size in one
# place and its shadow in another), so everything a selector is ever given is
# merged before it is judged -- otherwise a real scroller looks unscrollable
# just because its declarations are spread out.
merged = {}
for sel_blob, body in RULES:
    d = decls(body)
    if not d:
        continue
    for sel in sel_blob.split(","):
        sel = sel.strip()
        if not sel or sel.startswith("@") or sel.startswith("from") or sel.startswith("to"):
            continue
        merged.setdefault(sel, {}).update(d)


def scrollable(props):
    """Can a person actually scroll inside this box?

    Two things are needed and neither is enough alone: something that stops it
    growing to fit its content, and an overflow that produces a scrollbar
    rather than a clip. `overflow:hidden` clips -- it is a scrolling box to the
    browser, but not one any user can move.
    """
    capped = any(props.get(k) for k in ("max-height", "height"))
    of = " ".join(props.get(k, "") for k in ("overflow", "overflow-y"))
    return capped and ("auto" in of or "scroll" in of)


print("\n== every box that claims the wheel must be able to use it ==")
claimers = sorted(s for s, p in merged.items()
                  if "contain" in p.get("overscroll-behavior", ""))
truthy("something still asks for containment (the rule was not just deleted)",
       claimers)
for sel in claimers:
    p = merged[sel]
    check("  %s is genuinely scrollable" % sel, scrollable(p), True)
    if not scrollable(p):
        print("       height=%r max-height=%r overflow=%r overflow-y=%r"
              % (p.get("height"), p.get("max-height"),
                 p.get("overflow"), p.get("overflow-y")))

print("\n== the listings frame specifically ==")
lt = merged.get(".ltwrap", {})
truthy(".ltwrap still exists", lt)
check(".ltwrap still clips to the rounded card", lt.get("overflow"), "hidden")
check(".ltwrap does NOT contain the scroll",
      "contain" in lt.get("overscroll-behavior", ""), False)
# The point of the check above is only worth anything if this is still the box
# the listings table is drawn inside.
JS = open(JS_PATH, encoding="utf-8-sig").read()
truthy("the listings table is still drawn inside .ltwrap", 'card ltwrap' in JS)

print("\n== the boxes that DO contain it are the ones that should ==")
# Named so a future reader can see the intent survived, not just the syntax:
# a slide-in panel and a dropdown both sit over the page and both scroll.
truthy("the detail drawer still contains its scroll",
       "contain" in merged.get(".drawer", {}).get("overscroll-behavior", ""))

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
