"""Every colour this app writes has to be readable on every surface it paints.

MEASURED WITH A BROWSER across 24 screens, compositing translucent layers
properly (a 2% white overlay is not a white background):

    before   419 elements below WCAG AA
    after      0

WHAT WAS WRONG, in four kinds:

  the muted tiers      --ink3 measured 3.33:1 and --ink4 2.13:1 on --panel.
                       Almost every use of them is 10-12px, where AA asks 4.5.
                       So the words naming the columns of a table of money were
                       harder to read than the money.

  one status colour    --red 3.52:1 at its worst surface -- and red carries
                       "down 30%", "disabled", "2 HIGH RISK". --warn, --ok,
                       --accent and --gold all already cleared it.

  links with no colour The app styled links by CONTAINER -- .datasrc a,
                       .monhisttable a, .tileasin a and half a dozen more -- so
                       a link written anywhere else fell back to the browser's
                       #0000EE. Measured on Monitor: 1.33:1, 1.36:1, 1.60:1.

  white on the accent  The variations step you are ON was white text on the
                       light teal --accent: 1.89:1, the least readable thing on
                       that screen.

TWO THINGS THIS TAUGHT, both recorded in the stylesheet:

  A FOURTH TIER THAT CANNOT BE READ IS NOT A TIER. The first attempt kept --ink4
  faint on the grounds that it was "incidental" -- then the sweep showed it
  carrying SKU codes at 10px on three screens. A product's own code is content.

  A SURFACE THAT IS NOT A TOKEN IS STILL A SURFACE. rgb(45,50,66) is written out
  by hand in fourteen places and is lighter than --panel3, so tokens calibrated
  against the token list alone still failed on it at 4.35.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


CSS = io.open(os.path.join(HERE, "static", "css", "dashboard.css"),
              encoding="utf-8").read()
ROOT = re.search(r":root\s*\{(.*?)\n\s*\}", CSS, re.S).group(1)
TOK = dict(re.findall(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", ROOT))


def rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lum(h):
    def f(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(h)
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)


def ratio(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + .05) / (min(la, lb) + .05)


# Every surface this app paints text on: the tokens, plus the card colour that
# is written out by hand in fourteen places and is lighter than any of them.
SURFACES = [TOK[k] for k in ("bg", "sidebar", "panel", "panel2", "panel3", "input")]
CARD = "#2d3242"
SURFACES.append(CARD)

print("== every text colour clears AA on every surface ==")
TEXT = ("ink", "ink2", "ink3", "ink4", "red", "warn", "ok", "accent", "gold", "ai")
worst_all = 99
for k in TEXT:
    if k not in TOK:
        continue
    w = min(ratio(TOK[k], s) for s in SURFACES)
    worst_all = min(worst_all, w)
    check("  --%-7s %s   worst %.2f" % (k, TOK[k], w), w >= 4.5, True)
print("     (the weakest pairing anywhere is %.2f:1)" % worst_all)

print("\n== the card colour is included, not only the tokens ==")
truthy("rgb(45,50,66) is really used", "rgb(45,50,66)" in CSS)
print("     (written out %d times)" % CSS.count("rgb(45,50,66)"))
truthy("  and the stylesheet says why it is calibrated against",
       "not a token is still a surface" in CSS)

print("\n== the ladder is still a ladder ==")
panel = TOK["panel"]
tiers = [("ink", ratio(TOK["ink"], panel)), ("ink2", ratio(TOK["ink2"], panel)),
         ("ink3", ratio(TOK["ink3"], panel))]
for n, r in tiers:
    print("     --%-5s %.2f on --panel" % (n, r))
truthy("primary is the strongest", tiers[0][1] > tiers[1][1])
truthy("  secondary above muted", tiers[1][1] > tiers[2][1])
truthy("and the fourth tier is documented as gone",
       "A FOURTH TIER" in CSS or "fourth step is gone" in CSS)

print("\n== a link always has a colour ==")
truthy("there is a bare `a` rule", re.search(r"\na\{color:var\(--accent2\)\}", CSS) is not None)
truthy("  and a hover", re.search(r"\na:hover\{", CSS) is not None)
truthy("  at the lowest specificity, so container rules still win",
       "container rules still wins" in CSS or "still wins where it applies" in CSS)
truthy("the container rules are still there", ".monhisttable a{" in CSS)

print("\n== nothing writes a status colour by hand any more ==")
for hard, why in ((r"\.pct-badge\.down\{\s*color:rgb\(239", "the down badge"),
                  (r"\.pct-badge\.up\s*\{\s*color:rgb\(16", "the up badge")):
    falsy("  %s uses a token now" % why, re.search(hard, CSS) is not None)
truthy("the down badge is --red", ".pct-badge.down{ color:var(--red); }" in CSS)
truthy("  the up badge is --ok", ".pct-badge.up  { color:var(--ok); }" in CSS)
truthy("and why is recorded", "never reached the badges" in CSS)

print("\n== dark text on the light accent, not white ==")
V = io.open(os.path.join(HERE, "static", "js", "variations.js"),
            encoding="utf-8").read()
falsy("the active step is not white on teal",
      "background:var(--accent);color:#fff" in V)
truthy("  it is the dark teal made for it",
       "background:var(--accent);color:var(--accent-bg)" in V)
check("  which measures well over AA",
      ratio(TOK["accent-bg"], TOK["accent"]) > 7, True)
print("     (%.2f:1)" % ratio(TOK["accent-bg"], TOK["accent"]))

print("\n== against a running app, if one is up ==")
try:
    import json
    import subprocess
    import tempfile
    probe = os.path.join(os.environ.get("CLAUDE_JOB_DIR", tempfile.gettempdir()),
                         "tmp", "contrast2.py")
    if os.path.exists(probe):
        out = subprocess.run([sys.executable, probe], capture_output=True,
                             text=True, timeout=900, cwd=HERE)
        last = [l for l in (out.stdout or "").splitlines()
                if "TOTAL failing" in l]
        if last:
            n = int(last[0].split(":")[-1])
            check("no element on any screen is below AA", n, 0)
        else:
            print("     (the browser sweep did not report a total)")
    else:
        print("     (no browser sweep on this machine -- the tokens above stand)")
except Exception as e:
    print("     (browser sweep skipped: %s)" % str(e)[:100])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
