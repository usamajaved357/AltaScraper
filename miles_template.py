"""
miles_template.py — Miles Lubricants main-image text compositor.

Overlays user-controlled text onto a BLANK Miles template (container + empty
black panel + gallons badge + MADE IN USA + MILES logo). No AI: only text is
drawn into the panel zones, matching the Miles reference layout:

  [badge]                         (baked into the blank)
  TITLE LINE 1                    (big, bold, left-aligned)
  TITLE LINE 2                    (big, lighter)
  ...
  GRADE / SUBTITLE                (large, centred)
  CHOICE OF MECHANICS             (fixed, medium)
  APPLICATION LINE 1              (big, bold, left-aligned)
  APPLICATION LINE 2              (big, lighter)

Public entry: render_onto_blank(blank_image, spec) -> PNG bytes
"""

import io
import base64
import urllib.request
import ssl
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_HERE = Path(__file__).parent
_FONT_DIR = _HERE / "miles_fonts"

WHITE = (255, 255, 255)

FIXED_SUBLINE = "CHOICE OF MECHANICS"

# Panel text area as fractions of the WHOLE image (the black panel's usable
# column, left-aligned text starts at panel_x0). Calibrated to the Miles 1500px
# reference. Override per-template via spec["panel"] = [x0,y0,x1,y1].
DEFAULT_PANEL = (0.075, 0.06, 0.40, 0.94)

# Vertical anchors (fraction of the WHOLE image height) for each block top.
# Tuned to the Miles reference where MADE IN USA is on the BARREL, leaving the
# whole panel free: title high, grade mid, application low. For a blank that has
# MADE IN USA on the PANEL instead, pass tighter zones via spec["zones"].
DEFAULT_ZONES = {
    "title_top":   0.345,
    "grade_top":   0.555,
    "choice_gap":  0.012,
    "app_top":     0.785,
}

# Font sizes as fractions of image height (so it scales with template size).
FS = {
    "title":    0.052,   # main title lines
    "title2":   0.052,   # second title line (same size, lighter weight)
    "grade":    0.060,   # the big grade line (80W-90)
    "subline":  0.034,   # CHOICE OF MECHANICS + secondary
    "app":      0.052,   # application lines
}


def _font(px, weight="bold"):
    """Load a Miles font at pixel size px. Saira Condensed for display text,
    Montserrat for the small label lines. Looks in miles_fonts/ AND the app
    root (so loose .ttf files in the app folder are found too)."""
    px = max(8, int(px))
    if weight == "label":
        names = ["Montserrat.ttf", "SairaCondensed-SemiBold.ttf"]
    elif weight == "semibold":
        names = ["SairaCondensed-SemiBold.ttf", "Montserrat.ttf"]
    else:
        names = ["SairaCondensed-Bold.ttf", "Montserrat.ttf"]
    search_dirs = [_FONT_DIR, _HERE]   # miles_fonts/ first, then app root
    for n in names:
        for d in search_dirs:
            p = d / n
            if p.exists():
                try:
                    f = ImageFont.truetype(str(p), px)
                    try:
                        if "Montserrat" in n:
                            f.set_variation_by_axes([600])
                    except Exception:
                        pass
                    return f
                except Exception:
                    continue
    # fallbacks
    for fp in ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(fp).exists():
            return ImageFont.truetype(fp, px)
    return ImageFont.load_default()


def _load_image(src):
    if isinstance(src, Image.Image):
        return src.convert("RGBA")
    if not src:
        return None
    s = str(src).strip()
    try:
        if s.startswith("data:"):
            _, _, b64 = s.partition(",")
            return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
        if s.startswith(("http://", "https://")):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(s, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                return Image.open(io.BytesIO(r.read())).convert("RGBA")
        p = Path(s)
        if p.exists():
            return Image.open(p).convert("RGBA")
    except Exception:
        pass
    return None


def _fit(draw, text, max_w, start_px, weight):
    """Largest font (<=start_px) whose width fits max_w."""
    px = start_px
    while px > 12:
        f = _font(px, weight)
        if draw.textlength(text, font=f) <= max_w:
            return f
        px -= 2
    return _font(12, weight)


def _line_h(draw, font):
    b = draw.textbbox((0, 0), "Ag", font=font)
    return b[3] - b[1]


def _draw_left(draw, x, y, text, font, fill):
    draw.text((x, y), text, font=font, fill=fill)
    return _line_h(draw, font)


def _draw_center(draw, cx, y, text, font, fill):
    w = draw.textlength(text, font=font)
    draw.text((cx - w / 2, y), text, font=font, fill=fill)
    return _line_h(draw, font)


def _wrap(text, want_lines):
    words = text.split()
    if want_lines <= 1 or len(words) <= 1:
        return [text]
    target = len(text) / want_lines
    lines, cur, cl = [], [], 0
    for w in words:
        if cur and cl + len(w) > target and len(lines) < want_lines - 1:
            lines.append(" ".join(cur)); cur, cl = [], 0
        cur.append(w); cl += len(w) + 1
    if cur:
        lines.append(" ".join(cur))
    return lines


def _text_with_tracking(draw, xy, text, font, fill, tracking=0.0, shadow=None):
    """Draw text with per-letter tracking (em fraction) and an optional shadow.
    tracking is in fraction of font size (e.g. -0.04 like Saira in the brand
    file). shadow = (dx, dy, rgba) draws a soft offset shadow first."""
    x, y = xy
    size = getattr(font, "size", 40)
    track_px = tracking * size
    def _run(ox, oy, col):
        cx = x + ox
        for ch in text:
            draw.text((cx, y + oy), ch, font=font, fill=col)
            cx += draw.textlength(ch, font=font) + track_px
    if shadow:
        dx, dy, scol = shadow
        _run(dx, dy, scol)
    _run(0, 0, fill)


def _tracked_width(draw, text, font, tracking=0.0):
    size = getattr(font, "size", 40)
    track_px = tracking * size
    w = 0.0
    for ch in text:
        w += draw.textlength(ch, font=font) + track_px
    return max(0.0, w - track_px)


def _fit_block_to_box(draw, lines, box, weight, align="left", max_px=None, size_cap=None):
    """Fit text into a box with Figma-accurate typography: tight line-height,
    letter tracking matched to the brand fonts, and a subtle shadow on label
    text so it reads as printed-on rather than pasted-over."""
    bx0, by0, bx1, by1 = box
    bw, bh = (bx1 - bx0), (by1 - by0)
    if bw <= 2 or bh <= 2 or not lines:
        return
    # Brand typography (from the Miles Figma file):
    #  - Saira Condensed display text: letter-spacing -0.04em, line-height 80%
    #  - Montserrat labels: letter-spacing +0.01em, line-height ~93%, soft shadow
    if weight == "label":
        tracking, lh_factor = 0.01, 1.02
        shadow = None
    else:
        tracking, lh_factor = -0.03, 0.92
        shadow = None
    cap = int(bh)
    if size_cap:
        cap = min(cap, int(bh * size_cap))
    px = cap
    while px > 8:
        f = _font(px, weight)
        widest = max(_tracked_width(draw, ln, f, tracking) for ln in lines)
        lh = _line_h(draw, f) * lh_factor
        if widest <= bw and lh * len(lines) <= bh:
            break
        px -= 2
    f = _font(px, weight)
    lh = _line_h(draw, f) * lh_factor
    total_h = lh * len(lines)
    # subtle shadow for label text (Montserrat) per the Figma spec
    if weight == "label":
        off = max(1, int(px * 0.025))
        shadow = (off, off * 2, (0, 0, 0, 64))
    y = by0 + max(0, (bh - total_h) / 2)
    for ln in lines:
        w = _tracked_width(draw, ln, f, tracking)
        if align == "center":
            x = bx0 + (bw - w) / 2
        elif align == "right":
            x = bx1 - w
        else:
            x = bx0
        _text_with_tracking(draw, (x, y), ln, f, WHITE, tracking, shadow)
        y += lh


def _render_with_zones(base, draw, spec, zones, W, H):
    """Explicit-zone renderer. Each zone is a dict OR a bare [x0,y0,x1,y1] list.
    Zone dict may carry: box:[x0,y0,x1,y1], align, bold, size (fraction cap),
    and (for custom zones) text. Built-in zone keys title/grade/choice/
    application pull their text from the spec; any other key is a custom text
    zone using its own "text"."""
    def norm(z):
        if isinstance(z, dict):
            bx = z.get("box")
            if not bx or len(bx) != 4:
                return None
            return {"box": (bx[0]*W, bx[1]*H, bx[2]*W, bx[3]*H),
                    "align": z.get("align", "left"),
                    "weight": "bold" if z.get("bold", True) else "semibold",
                    "size": z.get("size"),
                    "text": z.get("text", "")}
        if isinstance(z, (list, tuple)) and len(z) == 4:
            return {"box": (z[0]*W, z[1]*H, z[2]*W, z[3]*H),
                    "align": "left", "weight": "bold", "size": None, "text": ""}
        return None

    subs = spec.get("subtitles") or []
    app = spec.get("application") or {}
    for key, zraw in zones.items():
        z = norm(zraw)
        if not z:
            continue
        # resolve the text for this zone
        if key == "title":
            txt = (spec.get("title") or "").strip().upper()
            want = 2 if len(txt.split()) > 2 else 1
        elif key == "grade":
            txt = (subs[0].get("text") if subs else "").strip().upper()
            want = 2 if (subs and int(subs[0].get("lines", 1) or 1) >= 2) else 1
        elif key == "choice":
            if not spec.get("draw_choice", True):
                continue
            txt = FIXED_SUBLINE
            want = 2
            z["weight"] = "label"   # CHOICE OF MECHANICS uses Montserrat, like Figma
        elif key == "application":
            txt = (app.get("text") or "").strip().upper()
            want = 2 if int(app.get("lines", 1) or 1) >= 2 else 1
        else:
            # custom text zone
            txt = (z.get("text") or "").strip().upper()
            want = 2 if len(txt.split()) > 2 else 1
        if not txt:
            continue
        _fit_block_to_box(draw, _wrap(txt, want), z["box"], z["weight"],
                          z["align"], size_cap=z.get("size"))


def render_onto_blank(blank_image, spec: dict) -> bytes:
    base = _load_image(blank_image)
    if base is None:
        raise ValueError("could not load blank template image")
    base = base.convert("RGBA")
    W, H = base.size
    draw = ImageDraw.Draw(base)

    # Eraser: paint filled rectangles over baked elements the user wants gone
    # (e.g. a MADE IN USA badge). Each erase box is [x0,y0,x1,y1] in fractions.
    # We sample the panel colour from a point just to the LEFT of the box (inside
    # the panel margin, away from the container) so we match the black panel.
    for eb in (spec.get("erase") or []):
        if not eb or len(eb) != 4:
            continue
        ex0, ey0, ex1, ey1 = eb[0]*W, eb[1]*H, eb[2]*W, eb[3]*H
        col = None
        rgb = base.convert("RGB")
        # try several sample points near the box that are likely panel-black
        for sxf, syf in ((eb[0]-0.02, (eb[1]+eb[3])/2),   # just left of box
                         (eb[0]+0.005, eb[1]-0.02),        # just above box
                         (0.06, (eb[1]+eb[3])/2)):         # panel left margin
            sx = max(0, min(W-1, int(sxf*W)))
            sy = max(0, min(H-1, int(syf*H)))
            p = rgb.getpixel((sx, sy))
            # accept only dark samples (the black panel)
            if p[0] < 40 and p[1] < 40 and p[2] < 55:
                col = p
                break
        if col is None:
            col = (6, 6, 6)   # fall back to the panel black #060606
        draw.rectangle([ex0, ey0, ex1, ey1], fill=col + (255,))

    # If the template carries explicit user-defined zones, use them (pixel-exact,
    # Figma-style). This is the reliable path once the user calibrates a template.
    zones = spec.get("zones")
    if zones and isinstance(zones, dict) and len(zones) > 0:
        _render_with_zones(base, draw, spec, zones, W, H)
        out = io.BytesIO()
        base.convert("RGB").save(out, format="PNG")
        return out.getvalue()

    # ----- fallback: auto-fit band layout (used before a template is calibrated)
    panel = spec.get("panel") or DEFAULT_PANEL
    x0 = panel[0] * W
    x1 = panel[2] * W
    col_w = x1 - x0
    cx = (x0 + x1) / 2
    fill = WHITE

    # The vertical band available for text: between the gallons badge (top) and
    # the bottom of the panel. For a MADE-IN-USA-on-panel blank, the caller can
    # pass spec["band"]=[top_frac, bottom_frac]; default clears both badges.
    band = spec.get("band") or [0.34, 0.66]
    band_top = band[0] * H
    band_bot = band[1] * H
    band_h = band_bot - band_top

    # ---- Build the list of blocks to lay out (each: lines + base size + align)
    # scale multiplier lets us shrink everything uniformly if it would overflow.
    def build_blocks(scale):
        blocks = []
        # TITLE (left, big)
        title = (spec.get("title") or "").strip().upper()
        if title:
            tlines = _wrap(title, 2) if len(title.split()) > 1 else [title]
            for i, ln in enumerate(tlines):
                blocks.append({"text": ln, "size": FS["title"] * scale,
                               "weight": "bold" if i == 0 else "semibold",
                               "align": "left", "gap": 0.20})
            blocks[-1]["gap"] = 0.55     # bigger gap after the title block
        # SUBTITLES (first = big grade, rest medium; centred)
        for si, sub in enumerate(spec.get("subtitles") or []):
            txt = (sub.get("text") or "").strip().upper()
            if not txt:
                continue
            want = 2 if int(sub.get("lines", 1) or 1) >= 2 else 1
            big = (si == 0)
            for ln in _wrap(txt, want):
                blocks.append({"text": ln,
                               "size": (FS["grade"] if big else FS["subline"]) * scale,
                               "weight": "bold" if big else "semibold",
                               "align": "center", "gap": 0.14 if big else 0.10})
        # CHOICE OF MECHANICS (fixed, centred)
        if spec.get("draw_choice", True):
            for ln in _wrap(FIXED_SUBLINE, 2):
                blocks.append({"text": ln, "size": FS["subline"] * scale,
                               "weight": "label", "align": "center", "gap": 0.10})
            if blocks:
                blocks[-1]["gap"] = 0.55     # gap before application
        # APPLICATION (left, big)
        app = spec.get("application") or {}
        app_txt = (app.get("text") or "").strip().upper()
        if app_txt:
            want = 2 if int(app.get("lines", 1) or 1) >= 2 else 1
            alines = _wrap(app_txt, want)
            for i, ln in enumerate(alines):
                blocks.append({"text": ln, "size": FS["app"] * scale,
                               "weight": "bold" if i == 0 else "semibold",
                               "align": "left", "gap": 0.20})
        return blocks

    def measure(blocks):
        total = 0
        for b in blocks:
            f = _fit(draw, b["text"], col_w, int(b["size"] * H), b["weight"])
            b["_font"] = f
            b["_h"] = _line_h(draw, f)
            total += b["_h"] * (1.0 + b["gap"])
        return total

    # Shrink uniformly until everything fits the band.
    scale = 1.0
    blocks = build_blocks(scale)
    total = measure(blocks)
    while total > band_h and scale > 0.4:
        scale -= 0.06
        blocks = build_blocks(scale)
        total = measure(blocks)

    # Centre the whole stack vertically within the band.
    y = band_top + max(0, (band_h - total) / 2)
    for b in blocks:
        if b["align"] == "left":
            _draw_left(draw, x0, y, b["text"], b["_font"], fill)
        else:
            _draw_center(draw, cx, y, b["text"], b["_font"], fill)
        y += b["_h"] * (1.0 + b["gap"])

    out = io.BytesIO()
    base.convert("RGB").save(out, format="PNG")
    return out.getvalue()


if __name__ == "__main__":
    spec = {
        "container": "pail",
        "title": "INDUSTIAL GEAR OIL",
        "subtitles": [
            {"text": "80W-90", "lines": 1},
        ],
        "application": {"text": "HYDRAULIC FLUID", "lines": 2},
    }
    import sys
    blank = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/_tpl_pail.png"
    data = render_onto_blank(blank, spec)
    open("/home/claude/_ref_render.png", "wb").write(data)
    print("wrote", len(data))
