"""Move hard-coded colours onto the shared colour tokens, so light mode works.

Owner, 29 Sep 2026: "yes change the light theme from hardcored onto shared
colors" (docs/decisions.md, UI). Kept so the migration can be repeated and
audited.

    py -3.11 tools/colour_tokens.py --report                 what would change, per CSS file
    py -3.11 tools/colour_tokens.py --apply FILE.css...      rewrite those CSS files
    py -3.11 tools/colour_tokens.py --apply-markup FILE...   inline style="" in templates,
                                                             CSS declarations in JS strings
    py -3.11 tools/colour_tokens.py --fix-pale FILE...       pale text left on a dark
                                                             ground that has since moved

THE RULE, per literal colour, by what it paints (role_of: bg, fg, bd, ov, any):
  1. Within MATCH_DE of a dark-theme --as-* token OF THAT ROLE: that token.
  2. Otherwise a generated palette variable --as-lit-<hex>[-role] in
     static/css/palette.css. Its DARK value is the literal itself, so dark mode
     does not change; its LIGHT value comes from light_of().
  rgba()/#rgba/#rrggbbaa keep their alpha: color-mix(in srgb, <var> N%, transparent).
  Custom-property DEFINITIONS (--ppc-bg: #...) are rewritten too; their role
  comes from the property's name.

Left as literals, because they are right in both themes: black shadows and
scrims (see-through near-black), and pale text on a SOLID coloured ground
(a badge, a primary button). Never touched: foundations.css, palette.css and
the two sign-in pages (they load neither). PDP files never snap to tokens.
"""
import colorsys
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(ROOT, "static", "css")
FOUND = os.path.join(CSS, "foundations.css")
PALETTE = os.path.join(CSS, "palette.css")
MAP_JSON = os.path.join(ROOT, "tools", "colour_palette_map.json")   # Rule 2 bars that other word in data file names
MATCH_DE = 4.0          # CIE76 distance; ~2.3 is "just noticeable"

LIT = re.compile(r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{4}\b|#[0-9a-fA-F]{3}\b|rgba?\(\s*[0-9.]+\s*,\s*[0-9.]+\s*,\s*[0-9.]+\s*(?:,\s*[0-9.]+%?\s*)?\)")
# The two sign-in pages load neither foundations.css nor palette.css and are
# always dark: a variable there would resolve to nothing.
SKIP_FILES = {"foundations.css", "palette.css", "login.css", "dash_login.css"}
# The product page is owner-locked ("i love my current pdp page", 28 Sep 2026)
# and pinned to its mockup colour for colour: its dark values stay EXACT, so
# nothing there is snapped to a nearby shared token -- every colour becomes a
# palette variable whose dark value is the mockup's own.
NOSNAP_FILES = {"pdp.css", "pdp_images.css"}


def parse(lit):
    s = lit.strip().lower()
    if s.startswith("#"):
        h = s[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        a = int(h[6:8], 16) / 255.0 if len(h) == 8 else 1.0
        return r, g, b, round(a, 3)
    nums = re.findall(r"[0-9.]+%?", s)
    r, g, b = (int(float(x)) for x in nums[:3])
    a = 1.0
    if len(nums) > 3:
        a = float(nums[3].rstrip("%")) / (100.0 if nums[3].endswith("%") else 1.0)
    return r, g, b, round(a, 3)


def hexof(r, g, b):
    return "#%02x%02x%02x" % (r, g, b)


def _lab(r, g, b):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    R, G, B = lin(r), lin(g), lin(b)
    X = (R * .4124 + G * .3576 + B * .1805) / .95047
    Y = (R * .2126 + G * .7152 + B * .0722)
    Z = (R * .0193 + G * .1192 + B * .9505) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return 116 * f(Y) - 16, 500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z))


def de(c1, c2):
    return math.dist(_lab(*c1), _lab(*c2))


def tokens():
    """Dark-theme --as-* colour tokens, name -> (r,g,b)."""
    src = open(FOUND, encoding="utf-8").read()
    dark = src.split('[data-theme="light"]')[0]
    out = {}
    for name, val in re.findall(r"(--as-[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\b", dark):
        if name not in out:
            out[name] = parse(val)[:3]
    # Only tokens meant to be painted with; the data-viz series are locked
    # hues for charts and would be the wrong meaning on a badge or a border.
    return {k: v for k, v in out.items() if not k.startswith("--as-viz-")}


def _lum(r, g, b):
    def f(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(c1, c2):
    a, b = _lum(*c1), _lum(*c2)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


_LIGHT_SURFACE = (243, 245, 248)       # --as-surface-3 light, the darkest page text sits on
_TEXT_MIN = 4.5                        # WCAG AA for text


def _hls255(h, l, s):
    rr, gg, bb = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return int(round(rr * 255)), int(round(gg * 255)), int(round(bb * 255))


def _readable(h, l, s):
    """The same hue, darkened step by step until it reads as TEXT on a light
    surface (4.5:1). Lowering HLS lightness to a fixed 0.40 left greens and
    yellows at 2-3:1 -- still bright colours (ui review, 29 Sep 2026)."""
    l2 = min(l, 0.45)
    c = _hls255(h, l2, s)
    while contrast(c, _LIGHT_SURFACE) < _TEXT_MIN and l2 > 0.05:
        l2 -= 0.01
        c = _hls255(h, l2, s)
    return c


def light_of(r, g, b, role="any"):
    """THE LIGHT VALUE OF A DARK-THEME COLOUR, by one rule, told what the colour
    is FOR (role: bg, fg, bd, ov or any).

    Neutral (grey-blue) colours swap ends: a dark surface becomes a light one,
    light text becomes dark text. A colour that is ALREADY right for a light
    page is kept: a white card on the dark app (the Dr PPC console's panels)
    stays white, and the dark ink written on it stays dark -- swapping those
    turned a white card black. Coloured ones keep their hue: a dark tint
    becomes a pale tint; text, lines and accents are darkened until they read
    on a light surface. Borders get their own branch: through the surface rule
    a dark border became as pale as the card it edges, and vanished."""
    if role == "ov":
        return 16, 24, 40                          # a see-through wash: white lifts dark, ink tints light
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    # Grey by CHROMA, not HLS saturation: near white or near black, a tiny tint
    # reads as "fully saturated" in HLS (#f6f8fa is s=0.33), and was darkened
    # as if it were an accent.
    if (max(r, g, b) - min(r, g, b)) / 255.0 < 0.12:   # neutral
        s2 = min(s, 0.18)
        if role == "any" and l >= 0.85:
            return r, g, b                         # a near-white ground: already right
        if role in ("bg", "bd") and l >= 0.60:
            return r, g, b                         # a light surface or edge: already right
        if role == "fg" and l <= 0.40:
            return r, g, b                         # dark ink: already right
        if role == "bd":
            return _hls255(h, 0.74 + l * 0.15, s2)  # 0.74 .. 0.83, the --as-border family
        if l < 0.40:                               # a surface
            l2 = 0.985 - (l / 0.40) * 0.20         # 0.985 .. 0.785
            if l > 0.25:                           # raised greys
                l2 = 0.86 - (l - 0.25) / 0.15 * 0.14
            return _hls255(h, l2, s2)
        if role == "bg":                           # a mid-grey surface
            return _hls255(h, 0.78, s2)
        return _readable(h, 0.12 + (1.0 - l) / 0.60 * 0.30, s2)   # text and icons
    # coloured
    if role in ("bg", "bd") and l >= 0.70:
        return r, g, b                             # a pale tint: already right
    if role == "bd":
        return _hls255(h, 0.72, s * 0.6)           # a visible tinted edge
    if role == "bg" and l < 0.30:
        return _hls255(h, 0.93, s * 0.75)          # a dark tint behind something -> a pale one
    if role == "any" and l < 0.30:
        return _hls255(h, 0.93, s * 0.75)
    if role == "bg":
        return _hls255(h, min(l, 0.40), s)         # a solid button or badge ground
    return _readable(h, l, s)                      # text, a line or an accent

# Which shared tokens a colour may become, by what it paints. A light-grey
# BACKGROUND must not become a TEXT token (its light value is near-black) --
# that is how the Dr PPC console's inputs went dark.
_ROLE_TOKENS = {
    "bg": re.compile(r"(bg|surface|canvas|shell|rail|scrim|action-subtle$|^--as-action$|danger-solid)"),
    "fg": re.compile(r"(text-|^--as-action(-hover|-pressed|-fg)?$|focus-ring|danger-solid|"
                     r"^--as-(success|warning|danger|info|neutral|aftercare)$)"),
    "bd": re.compile(r"(border|^--as-action$|focus-ring|^--as-(success|warning|danger|info)$)"),
}


def role_of(prop):
    """bg / fg / bd / any, from a declaration's property -- or, for a custom
    property, from its name (--ppc-bg, --drp-ink, --pdp-line)."""
    p = prop.strip().rstrip(":").strip().lower()
    if p.startswith("--"):
        if re.search(r"(bg|panel|surface|card|canvas|input|field|track|ground|sheet|paper|tint|fill|shade|well)", p):
            return "bg"
        if re.search(r"(ink|text|fg|muted|dim|faint|placeholder|label|title|heading|copy)", p):
            return "fg"
        if re.search(r"(line|border|rule|divider|stroke|edge)", p):
            return "bd"
        return "any"
    if p.startswith("background"):
        return "bg"
    if p in ("color", "fill", "stroke", "-webkit-text-fill-color", "caret-color", "text-decoration-color"):
        return "fg"
    if p.startswith("border") or p.startswith("outline"):
        return "bd"
    return "any"


def is_shadow(c):
    r, g, b, a = c
    return a < 1.0 and max(r, g, b) <= 16                 # black at some alpha


_SNAP = [True]      # False while migrating a NOSNAP file


def replacement(lit, toks, lits, role="any", snap=None):
    if snap is None:
        snap = _SNAP[0]
    c = parse(lit)
    r, g, b, a = c
    if is_shadow(c):
        return None
    # A SEE-THROUGH WHITE is a hover or a lift on the dark theme. On a light
    # page the same job is done by a see-through dark, not by more white.
    if a < 0.999 and min(r, g, b) >= 230:
        role = "ov"
    pat = _ROLE_TOKENS.get(role)
    best, bd = None, 99.0
    for name, tv in (toks.items() if (snap and role != "ov") else ()):
        if pat is not None and not pat.search(name):
            continue
        d = de((r, g, b), tv)
        if d < bd:
            best, bd = name, d
    if bd <= MATCH_DE:
        var = "var(%s)" % best
    else:
        key = hexof(r, g, b)[1:] + ("" if role == "any" else "-" + role)
        lits[key] = (r, g, b, role)
        var = "var(--as-lit-%s)" % key
    if a >= 0.999:
        return var
    return "color-mix(in srgb, %s %s%%, transparent)" % (var, _pct(a))


def _pct(a):
    p = round(a * 100, 1)
    return str(int(p)) if p == int(p) else str(p)





def migrate(src, toks, lits):
    """Rewrite literals everywhere EXCEPT inside comments and in declarations
    of custom properties (lines `--x: #...`), which define variables."""
    # Comments are set aside as placeholders (no braces, no colours) and put
    # back afterwards. Cutting the text AT the comments instead left every rule
    # that has a comment inside it in two halves, neither a whole {...} -- and
    # those rules were silently skipped.
    saved = []

    def park(m):
        saved.append(m.group(0))
        return "/*@@%d@@*/" % (len(saved) - 1)
    body = re.sub(r"(?s)/\*.*?\*/", park, src)
    body = _mig_code(body, toks, lits)
    return re.sub(r"/\*@@(\d+)@@\*/", lambda m: saved[int(m.group(1))], body)


SOLID_VARS = re.compile(r"var\(--(red|ok|warn|accent|gold|as-action|as-danger|as-success|"
                        r"as-warning|as-info|as-danger-solid|as-viz-[a-z-]+)\)")


def _solid_bg(body):
    """Does this rule paint a solid, saturated background? Then white text on
    it is white on purpose (a badge, a primary button) in either theme."""
    for m in re.finditer(r"background(?:-color)?\s*:\s*([^;{}]*)", body):
        v = m.group(1)
        if SOLID_VARS.search(v):
            return True
        # Any other variable that is not a surface (a scoped accent such as
        # --ppc-blue or --pdp-orange) is a solid colour too.
        for name in re.findall(r"var\((--[a-z0-9-]+)", v):
            if not re.search(r"(bg|panel|surface|canvas|sidebar|input|line|border|scrim|shell|rail|"
                             r"subtle|dim|muted|ink|text|shadow|card|hover|row|track)", name):
                return True
        for lit in LIT.findall(v):
            r, g, b, a = parse(lit)
            h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
            if a > 0.8 and s > 0.35 and 0.25 < l < 0.75:
                return True
            if 0.5 <= a < 1 and max(r, g, b) <= 40:
                return True                        # a see-through scrim button (#0009 behind a white x)
    return False


def _is_white(lit):
    """Pale text of ANY hue (#fff, #eeeeff, #e0fff0): on a solid coloured ground
    it is pale on purpose, in either theme (ui review, 29 Sep 2026)."""
    r, g, b, a = parse(lit)
    l = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)[1]
    return a > 0.99 and l >= 0.85


def _mig_body(body, toks, lits):
    keep_white = _solid_bg(body)

    def decl(m):
        prop, val = m.group(1), m.group(2)
        is_text = role_of(prop) == "fg"

        def one(x):
            lit = x.group(0)
            if keep_white and is_text and _is_white(lit):
                return lit
            return replacement(lit, toks, lits, role_of(prop)) or lit
        return prop + LIT.sub(one, val)
    return re.sub(r"([-a-zA-Z0-9]+\s*:)([^;{}]*)", decl, body)


def _mig_code(code, toks, lits):
    # Rule by rule (the innermost {...}), so a declaration can see the rest of
    # its rule -- see _solid_bg.
    return re.sub(r"\{[^{}]*\}", lambda m: _mig_body(m.group(0), toks, lits), code)


def _write_atomic(path, text):
    """Whole file or nothing: a temporary file beside it, then a rename."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def write_palette(lits):
    keep = {}
    if os.path.exists(MAP_JSON):
        with open(MAP_JSON, encoding="utf-8") as fh:
            keep = {k: tuple(v) for k, v in json.loads(fh.read()).items()}
    keep.update(lits)
    _write_atomic(MAP_JSON, json.dumps({k: list(v) for k, v in sorted(keep.items())}, indent=0))
    dark = "\n".join("  --as-lit-%s: %s;" % (k, hexof(*v[:3])) for k, v in sorted(keep.items()))
    light = "\n".join("  --as-lit-%s: %s;" % (k, hexof(*light_of(*v))) for k, v in sorted(keep.items()))
    txt = ("/* static/css/palette.css -- GENERATED by tools/colour_tokens.py; do not edit by hand.\n"
           "   Colours the app used that are not one of the shared tokens. Dark = the colour\n"
           "   exactly as it was; light = derived by one rule (light_of). Owner, 29 Sep 2026:\n"
           "   hard-coded colours move onto shared colours so light mode works. */\n"
           ":root, [data-theme=\"dark\"] {\n" + dark + "\n}\n"
           "[data-theme=\"light\"] {\n" + light + "\n}\n")
    _write_atomic(PALETTE, txt)


STYLE_ATTR = re.compile(r'(style\s*=\s*")([^"]*)(")')
# A CSS declaration written inside a JS string: `background:#0d1220` -- the
# colour directly after the colon's value, with no quote in between (so chart
# option objects such as {color:"#fff"}, which feed a canvas, are left alone).
JS_DECL = re.compile(r"((?:background|background-color|color|border(?:-[a-z]+)?|outline|fill|stroke|"
                     r"box-shadow)\s*:\s*)([^;\"'`{}<>]*)")


def migrate_markup(src, toks, lits, is_js):
    """Inline styles in a template, or CSS declarations inside JS strings."""
    def attr(m):
        body = _mig_body("{" + m.group(2) + "}", toks, lits)[1:-1]
        return m.group(1) + body + m.group(3)
    out = STYLE_ATTR.sub(attr, src)
    if is_js:
        out = JS_DECL.sub(lambda m: m.group(1) + LIT.sub(
            lambda x: replacement(x.group(0), toks, lits, role_of(m.group(1))) or x.group(0), m.group(2)), out)
    return out


PALE_GROUND = re.compile(r"background(?:-color)?\s*:\s*var\((--as-lit-([0-9a-f]{6})-bg|--as-(?:bg-[a-z]+|surface-[0-9a-z]+))\)")


def _dark_neutral_ground(block):
    """The ground a rule paints, when it is a SURFACE that turns light in the
    light theme: a neutral --as-lit-...-bg, or a surface token."""
    for m in PALE_GROUND.finditer(block):
        if not m.group(2):
            return True
        r, g, b = int(m.group(2)[0:2], 16), int(m.group(2)[2:4], 16), int(m.group(2)[4:6], 16)
        if (max(r, g, b) - min(r, g, b)) / 255.0 < 0.12 and max(r, g, b) < 110:
            return True
    return False


def fix_pale(src, toks, lits):
    """PALE TEXT LEFT BEHIND ON A GROUND THAT MOVED. The first pass kept pale
    text on any solid dark ground as if it were a button; where that ground is
    a SURFACE it turns light in the light theme and the text vanishes (change
    review, 29 Sep 2026: typed text in the PPC and Inventory inputs). Here the
    text follows its ground: it becomes a text colour."""
    def fix_block(block):
        if not _dark_neutral_ground(block):
            return block
        return re.sub(r"((?:^|[;{\s])color\s*:\s*)(#[0-9a-fA-F]{3,6}\b)",
                      lambda m: m.group(1) + (replacement(m.group(2), toks, lits, "fg")
                                              if _is_white(m.group(2)) else m.group(2)), block)
    out = re.sub(r"\{[^{}]*\}", lambda m: fix_block(m.group(0)), src)
    return STYLE_ATTR.sub(lambda m: m.group(1) + fix_block("{" + m.group(2) + "}")[1:-1] + m.group(3), out)


def css_files():
    for dp, _dn, fns in os.walk(CSS):
        for fn in fns:
            if fn.endswith(".css") and fn not in SKIP_FILES:
                yield os.path.join(dp, fn)


def main(argv):
    toks = tokens()
    if "--report" in argv:
        tot = tok = lit = 0
        for f in sorted(css_files()):
            lits = {}
            src = open(f, encoding="utf-8-sig").read()
            new = migrate(src, toks, lits)
            a = new.count("var(--as-lit-") - src.count("var(--as-lit-")
            b = sum(new.count("var(%s)" % t) - src.count("var(%s)" % t) for t in toks)
            if a or b:
                print("%-50s tokens %4d  palette %4d" % (os.path.relpath(f, ROOT), b, a))
                tot += a + b; tok += b; lit += a
        print("total %d: %d onto tokens, %d onto palette variables" % (tot, tok, lit))
        return 0
    if "--fix-pale" in argv:
        files = [a for a in argv if a.endswith((".css", ".html", ".js"))]
        allp = {}
        for f in files:
            p = os.path.join(ROOT, f) if not os.path.isabs(f) else f
            raw = open(p, "rb").read()
            bom = raw.startswith(b"\xef\xbb\xbf")
            src = raw.decode("utf-8-sig")
            new = fix_pale(src, toks, allp)
            if new != src:
                open(p, "wb").write((b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8"))
                print("fixed", os.path.relpath(p, ROOT))
        write_palette(allp)
        return 0
    if "--apply-markup" in argv:
        files = [a for a in argv if a.endswith(".html") or a.endswith(".js")]
        allp = {}
        for f in files:
            p = os.path.join(ROOT, f) if not os.path.isabs(f) else f
            raw = open(p, "rb").read()
            bom = raw.startswith(b"\xef\xbb\xbf")
            src = raw.decode("utf-8-sig")
            new = migrate_markup(src, toks, allp, p.endswith(".js"))
            if new != src:
                open(p, "wb").write((b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8"))
                print("migrated", os.path.relpath(p, ROOT))
        write_palette(allp)
        return 0
    if "--apply" in argv:
        files = [a for a in argv if a.endswith(".css")]
        allp = {}
        for f in files:
            p = os.path.join(ROOT, f) if not os.path.isabs(f) else f
            raw = open(p, "rb").read()
            bom = raw.startswith(b"\xef\xbb\xbf")
            src = raw.decode("utf-8-sig")
            crlf = "\r\n" in src
            _SNAP[0] = os.path.basename(p) not in NOSNAP_FILES
            new = migrate(src.replace("\r\n", "\n"), toks, allp)
            _SNAP[0] = True
            if crlf:
                new = new.replace("\n", "\r\n")
            open(p, "wb").write((b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8"))
            print("migrated", os.path.relpath(p, ROOT))
        write_palette(allp)
        with open(MAP_JSON, encoding="utf-8") as fh:
            print("palette.css:", len(json.loads(fh.read())), "variables")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
