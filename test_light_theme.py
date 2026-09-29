"""Light mode: every colour is a shared token or a palette variable.

Owner, 29 Sep 2026: "yes change the light theme from hardcored onto shared
colors" (docs/decisions.md, UI). tools/colour_tokens.py did the move and wrote
static/css/palette.css. This pins what makes light mode work at all:

  * No plain colour is left in the app's stylesheets, except the two kinds
    that are right in both themes: black shadows, and white text on a solid
    coloured button or badge.
  * Every palette variable a stylesheet, template or script uses is DEFINED,
    for both themes -- an undefined var() paints nothing, silently.
  * palette.css loads straight after the tokens, before anything that uses it.
  * The switch exists and light is offered.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


def nocomments(s):
    return re.sub(r"(?s)/\*.*?\*/", "", s)


CSS_DIR = os.path.join(HERE, "static", "css")
SKIP = {"foundations.css", "palette.css", "login.css", "dash_login.css"}
LIT = re.compile(r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{4}\b|#[0-9a-fA-F]{3}\b|rgba?\([^)]*\)")

def _pale(s):
    h = s.lstrip("#")
    if not re.fullmatch(r"[0-9a-f]{3,8}", h):
        return False
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (max(r, g, b) + min(r, g, b)) / 510.0 >= 0.85


# The ground a rule paints, when it is a SURFACE (it turns light in the light
# theme): pale text on it would vanish, so it is not the button exemption
# (change review, 29 Sep 2026: typed text in the PPC and Inventory inputs).
SURFACE = re.compile(r"background(?:-color)?\s*:\s*var\((--as-lit-([0-9a-f]{6})-bg|--as-(?:bg-[a-z]+|surface-[0-9a-z]+))\)")


def _on_surface(rule):
    for m in SURFACE.finditer(rule):
        if not m.group(2):
            return True
        r, g, b = (int(m.group(2)[i:i + 2], 16) for i in (0, 2, 4))
        if max(r, g, b) - min(r, g, b) < 31 and max(r, g, b) < 110:
            return True
    return False


# White ON PURPOSE in both themes, where the ground is set elsewhere (a fixed
# chart colour per segment). Each with its reason.
ALLOWED = {".rp-sbar div": "repricer money bar: every segment is a fixed chart colour"}


def scan(rule, where, left, selector=""):
    if selector.strip() in ALLOWED:
        return
    for prop, val in re.findall(r"([-a-zA-Z0-9]+)\s*:\s*([^;{}\"]*)", rule):
        for lit in LIT.findall(val):
            s = lit.replace(" ", "").lower()
            # A see-through near-black -- a shadow, or the scrim behind a
            # dialog -- dims the page the same way in either theme.
            n = [float(x) for x in re.findall(r"[0-9.]+", s)] if s.startswith("rgba") else []
            shadow = len(n) == 4 and max(n[:3]) <= 16 and n[3] < 1
            hx = s.lstrip("#")
            if s.startswith("#") and len(hx) in (4, 8):          # #rgba / #rrggbbaa
                full = "".join(c * 2 for c in hx) if len(hx) == 4 else hx
                shadow = max(int(full[i:i + 2], 16) for i in (0, 2, 4)) <= 16 and full[6:8] != "ff"
            # Pale text of any hue on a rule that paints its own SOLID ground:
            # a badge or a button, pale on purpose in both themes.
            white = (prop.lower() in ("color", "fill") and "background" in rule
                     and not _on_surface(rule) and _pale(s))
            if not (shadow or white):
                left.append("%s: %s:%s" % (where, prop, lit))


print("== no plain colour left in the app's stylesheets ==")
left = []
for dp, _dn, fns in os.walk(CSS_DIR):
    for fn in fns:
        if not fn.endswith(".css") or fn in SKIP:
            continue
        rel = os.path.relpath(os.path.join(dp, fn), HERE)
        src = nocomments(read(rel))
        for m in re.finditer(r"([^{}]*)(\{[^{}]*\})", src):
            scan(m.group(2), rel, left, m.group(1).split("}")[-1])
check("only black shadows and white-on-solid text remain", left[:8], [])

print("\n== nor in the templates' inline styles ==")
tleft = []
TPLS = [os.path.join("templates", "dashboard.html"), os.path.join("templates", "brand_panel.html")] + \
       [os.path.join("templates", "screens", f) for f in os.listdir(os.path.join(HERE, "templates", "screens"))
        if f.endswith(".html")]
for rel in TPLS:
    for st in re.findall(r'style\s*=\s*"([^"]*)"', re.sub(r"(?s)<!--.*?-->", "", read(rel))):
        scan("{" + st + "}", rel, tleft)
check("inline styles use tokens too", tleft[:8], [])

print("\n== every palette variable used is defined, in both themes ==")
PAL = read("static", "css", "palette.css")
dark_part, light_part = PAL.split('[data-theme="light"]', 1)
dark = set(re.findall(r"(--as-lit-[a-z0-9-]+)\s*:", dark_part))
light = set(re.findall(r"(--as-lit-[a-z0-9-]+)\s*:", light_part))
check("the two themes define the same variables", sorted(dark ^ light)[:5], [])
used = set()
for dp, _dn, fns in os.walk(HERE):
    if any(x in dp for x in ("node_modules", ".git", "active", "__pycache__", "tests_support")):
        continue
    for fn in fns:
        if fn.endswith((".css", ".html", ".js")) and fn != "palette.css":
            try:
                used |= set(re.findall(r"var\((--as-lit-[a-z0-9-]+)\)", read(os.path.relpath(os.path.join(dp, fn), HERE))))
            except (UnicodeDecodeError, OSError):
                pass
check("every var(--as-lit-...) in use is defined", sorted(used - dark)[:5], [])
check("  and there are some in use (the move happened)", len(used) > 100, True)

print("\n== readable in light mode ==")
# Defined is not enough: a text colour must read on a light page, and an edge
# must still show against white (ui review, 29 Sep 2026: greens and golds at
# 2-3:1, borders that vanished).


def _lum(h):
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def _ratio(a, b):
    x, y = _lum(a), _lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


LIGHT = dict(re.findall(r"(--as-lit-[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;", light_part))
weak_fg = sorted(k for k, v in LIGHT.items() if k.endswith("-fg") and _ratio(v, "#f3f5f8") < 4.5)
check("every text colour is at least 4.5:1 on a light surface", weak_fg[:6], [])
weak_bd = sorted(k for k, v in LIGHT.items() if k.endswith("-bd") and _ratio(v, "#ffffff") < 1.2)
check("every border still shows against white", weak_bd[:6], [])

print("\n== loading and switching ==")
H = read("templates", "dashboard.html")
f = H.index("/static/css/foundations.css")
p = H.index("/static/css/palette.css")
nxt = H.find('rel="stylesheet"', f + 10)
check("palette.css is the stylesheet right after the tokens", H.find("/static/css/", nxt) == p, True)
T = read("static", "js", "theme.js")
check("light is offered", "var LIGHT_READY = true;" in T, True)
check("the top bar has the switch", 'id="themebtn"' in H and "altaThemeToggleBtn()" in H, True)
check("  and it says what it will do", "Switch to the light theme" in T and "Switch to the dark theme" in T, True)

print("\nFAILURES: %d" % len(FAILS) if FAILS else "\nFAILURES: 0")
sys.exit(1 if FAILS else 0)
