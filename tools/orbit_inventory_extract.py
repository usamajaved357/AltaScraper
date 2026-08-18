"""tools/orbit_inventory_extract.py -- Orbit's Inventory system, in full.

    python tools/orbit_inventory_extract.py routes
    python tools/orbit_inventory_extract.py clicks
    python tools/orbit_inventory_extract.py table
    python tools/orbit_inventory_extract.py tooltips
    python tools/orbit_inventory_extract.py steven
    python tools/orbit_inventory_extract.py design
    python tools/orbit_inventory_extract.py assemble
    python tools/orbit_inventory_extract.py all

WHAT THIS IS FOR
The earlier audit (orbit_full_audit.md) walked 45 routes and wrote down what was
on screen AT LOAD. It never clicked anything, so everything that matters about
Inventory -- what "Run AutoPilot" opens, what Steven answers, what a row expands
into, what an info tooltip explains -- is still unknown. This clicks.

WHY IT IS SPLIT INTO SUBCOMMANDS
A single run that visits every route, opens every modal and holds a conversation
with an AI agent takes tens of minutes and has many ways to fail. When it dies
at step 40 you do not want to redo steps 1-39. Each subcommand writes its own
fragment into orbit_inventory/ and `assemble` merges them, so any part can be
re-run alone.

HOW IT GETS IN
It attaches to a Chrome YOU started with the debugging port open and signed in
yourself. No password is typed here, none is stored, nothing is sent anywhere.

    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" ^
      --remote-debugging-port=9222 --user-data-dir="%TEMP%\\orbit-profile"

WHAT IT CANNOT DO
It reads what the browser renders and what the network carries. It cannot see
Orbit's server code, so every "how is this calculated" answer here is inferred
from field names, API payloads and tooltip copy -- and is labelled as inferred.
Nothing guessed is presented as measured.
"""
import argparse
import json
import os
import re
import sys
import time

BRAND = "flux-footwear"
MP = "ATVPDKIKX0DER"
BASE = "https://fullcircleorbit.com/brand/%s/%s" % (BRAND, MP)
CDP = "http://127.0.0.1:9222"
OUTDIR = "orbit_inventory"
SHOTS = os.path.join(OUTDIR, "shots")

# SECTIONS. The machinery below -- the settle that waits for real data, the
# screenshot walker that drives Orbit's inner scroller, the phase-stamped
# network recorder, the structural overlay finder -- is not specific to
# inventory. It took a day to get right, and a second copy of it pointed at the
# advertising routes would drift from this one immediately (Rule 12).
#
# So the route table and the output directory are per SECTION, chosen with
# --section, and everything else is shared.
#
# The PPC routes are from orbit_full_audit.md's own sidebar crawl:
#     Advertising    -> /ppc            (PPC Analytics)
#     Search Terms   -> /ppc/search-terms
#     Campaigns      -> /ppc/campaigns  (Campaign Analytics)
#     Live Tracker   -> /ppc/live
#     Dr PPC Console -> /agents/dr-ppc-grok
SECTIONS = {
    "inventory": {
        "outdir": "orbit_inventory",
        "routes": [
            ("overview",           BASE + "/inventory/overview"),
            ("inventory-index",    BASE + "/inventory"),
            ("inventory-overview", BASE + "/inventory/inventory-overview"),
            ("forecasting",        BASE + "/inventory/forecasting"),
            ("sales-forecast",     BASE + "/inventory/sales-forecast"),
            ("actions",            BASE + "/inventory/actions"),
            ("shipments",          BASE + "/inventory/shipments"),
            ("comms",              BASE + "/inventory/comms"),
            ("cogs-settings",      BASE + "/cogs"),
            ("reimbursements",     BASE + "/reimbursements"),
        ],
        # The cockpit buttons to click and document.
        "buttons": ["Run AutoPilot", "Open action queue", "Autopilot onboarding",
                    "Open reimbursements", "Steven actions"],
    },
    "ppc": {
        "outdir": "orbit_ppc",
        "routes": [
            ("ppc-analytics",  BASE + "/ppc"),
            ("search-terms",   BASE + "/ppc/search-terms"),
            ("campaigns",      BASE + "/ppc/campaigns"),
            ("live-tracker",   BASE + "/ppc/live"),
            ("dr-ppc",         BASE + "/agents/dr-ppc-grok"),
        ],
        # DELIBERATELY EMPTY BY DEFAULT.
        #
        # CLAUDE.md Rule 8: never change a bid or budget unless the user names
        # the exact new value. On an advertising screen the buttons are the
        # dangerous surface -- "apply", "optimise", "harvest", "negate" all
        # write to live campaigns spending real money on a client account.
        #
        # The clicks part therefore clicks NOTHING on ppc unless --buttons
        # names something explicitly. Capturing what a control would do is the
        # deliverable; triggering it is not.
        "buttons": [],
    },
}

ROUTES = SECTIONS["inventory"]["routes"]


def use_section(name):
    """Point the module at one section's routes and output directory."""
    global ROUTES, OUTDIR, SHOTS, COCKPIT_BUTTONS
    s = SECTIONS.get(name)
    if not s:
        raise SystemExit("unknown --section %r; try one of: %s"
                         % (name, ", ".join(sorted(SECTIONS))))
    ROUTES = s["routes"]
    OUTDIR = s["outdir"]
    SHOTS = os.path.join(OUTDIR, "shots")
    COCKPIT_BUTTONS = list(s["buttons"])
    return s


def PRIMARY():
    """The section's landing page -- the first route in its table.

    The parts below used to navigate to BASE + "/inventory/overview" written
    out in each body, so --section chose where the files were WRITTEN and not
    what was captured. Everything goes through here now.
    """
    return ROUTES[0][1]


def TOOLTIP_ROUTES():
    """Which routes to hunt tooltips on: the first three of the section.

    Tooltips are where Orbit states its own rules in its own words, and they
    are cheap to collect, so this takes the section's main screens rather than
    one.
    """
    return [(n, u) for n, u in ROUTES[:3]]


# The buttons named in the brief, plus the ones the earlier audit found on the
# cockpit. Matched on visible text because Orbit's class names are
# content-hashed (_statCard_xa5pv_431) and change every build.
#
# Replaced wholesale by use_section(); this is the inventory default so the tool
# behaves exactly as before when no --section is given.
COCKPIT_BUTTONS = list(SECTIONS["inventory"]["buttons"])

STEVEN_QUESTIONS = [
    "Which ASINs need reordering this week?",
    "What's the stockout risk for our top 5 products?",
    "Draft a purchase order for items running low",
    "What's our inventory health summary?",
    "Show me slow-moving inventory",
]

# Properties that decide how something reads. Everything else is noise in a
# document meant to be built from.
PROPS = ["display", "flex-direction", "align-items", "justify-content", "gap",
         "grid-template-columns", "background", "background-color", "background-image",
         "border", "border-radius", "padding", "margin", "font-size", "font-weight",
         "font-family", "line-height", "letter-spacing", "text-transform", "color",
         "box-shadow", "opacity", "position", "overflow", "width", "height",
         "min-height", "transition-duration", "transition-timing-function"]

# ---------------------------------------------------------------- page walker

SCAN_JS = r"""
(props) => {
  const out = {url: location.href, viewport: {w: innerWidth, h: innerHeight}, nodes: []};
  const seen = new Set();
  const root = document.querySelector("[class*='_content_']") || document.body;
  const walk = (el, depth) => {
    if (depth > 16 || !el || seen.has(el)) return;
    seen.add(el);
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") return;
    const r = el.getBoundingClientRect();
    const own = [...el.childNodes].filter(n => n.nodeType === 3)
                  .map(n => n.textContent.trim()).join(" ").trim();
    const paints = cs.backgroundColor !== "rgba(0, 0, 0, 0)" ||
                   cs.backgroundImage !== "none" ||
                   cs.borderBottomWidth !== "0px" || cs.borderTopWidth !== "0px";
    const tag = el.tagName.toUpperCase();
    const worth = (own && own.length < 140) || paints ||
                  ["BUTTON","SELECT","INPUT","TABLE","TH","SVG","TEXTAREA","A"].includes(tag);
    if (worth && r.width > 0 && r.height > 0) {
      const o = {depth, tag: tag.toLowerCase(),
                 cls: String(el.className && el.className.baseVal !== undefined
                             ? el.className.baseVal : (el.className || "")).slice(0, 70),
                 text: own.slice(0, 130),
                 title: el.getAttribute('title') || el.getAttribute('aria-label') || '',
                 box: [+r.width.toFixed(1), +r.height.toFixed(1),
                       +r.x.toFixed(1), +Math.round(r.y + (window.__scrollTop||0))]};
      props.forEach(p => {
        const v = cs.getPropertyValue(p);
        if (v && v !== "none" && v !== "normal" && v !== "auto" &&
            v !== "0px" && v !== "rgba(0, 0, 0, 0)" && v !== "static")
          o[p] = v.trim().slice(0, 200);
      });
      out.nodes.push(o);
    }
    [...el.children].forEach(c => walk(c, depth + 1));
  };
  walk(root, 0);
  return out;
}
"""

# Orbit is an app shell: height:100% with an inner overflow-y:auto. A full_page
# screenshot therefore stops at the fold, which is why the earlier audit has no
# below-the-fold imagery at all. This finds the element that actually scrolls.
SCROLLER_JS = r"""
() => {
  let best = null, bestArea = 0;
  document.querySelectorAll('*').forEach(el => {
    const cs = getComputedStyle(el);
    if (!/(auto|scroll)/.test(cs.overflowY)) return;
    if (el.scrollHeight <= el.clientHeight + 40) return;
    const r = el.getBoundingClientRect();
    const area = r.width * r.height;
    if (area > bestArea) { bestArea = area; best = el; }
  });
  if (!best) return {found: false, scrollHeight: document.body.scrollHeight,
                     clientHeight: innerHeight};
  best.setAttribute('data-orbit-scroller', '1');
  return {found: true, scrollHeight: best.scrollHeight,
          clientHeight: best.clientHeight, cls: String(best.className).slice(0,70)};
}
"""

# What appeared on top of the page after a click: a dialog, drawer, sheet or
# overlay. Identified structurally (role, z-index, fixed position) rather than
# by class name, because the class names are hashed.
OVERLAY_JS = r"""
() => {
  const cands = [...document.querySelectorAll(
    "[role='dialog'],[role='alertdialog'],[aria-modal='true']," +
    "[class*='odal'],[class*='rawer'],[class*='verlay'],[class*='heet']," +
    "[class*='opover'],[class*='anel']")];
  const vis = cands.filter(el => {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' &&
           r.width > 120 && r.height > 80;
  });
  if (!vis.length) return null;
  // The one that sits highest and covers the most is the surface that opened.
  vis.sort((a, b) => {
    const z = e => parseInt(getComputedStyle(e).zIndex) || 0;
    const ar = e => { const r = e.getBoundingClientRect(); return r.width * r.height; };
    return (z(b) - z(a)) || (ar(b) - ar(a));
  });
  const el = vis[0];
  const cs = getComputedStyle(el), r = el.getBoundingClientRect();
  return {
    cls: String(el.className).slice(0, 90),
    role: el.getAttribute('role') || '',
    box: [+r.width.toFixed(1), +r.height.toFixed(1), +r.x.toFixed(1), +r.y.toFixed(1)],
    style: {position: cs.position, zIndex: cs.zIndex, background: cs.backgroundColor,
            backdropFilter: cs.backdropFilter, borderRadius: cs.borderRadius,
            boxShadow: cs.boxShadow, padding: cs.padding, border: cs.border},
    text: (el.innerText || '').trim().slice(0, 6000),
    headings: [...el.querySelectorAll('h1,h2,h3,h4')].map(h => h.innerText.trim()).slice(0, 40),
    buttons: [...el.querySelectorAll("button,[role='button']")]
               .map(b => (b.innerText || b.getAttribute('aria-label') || '').trim())
               .filter(Boolean).slice(0, 60),
    inputs: [...el.querySelectorAll('input,select,textarea')].map(i => ({
      tag: i.tagName.toLowerCase(), type: i.type || '', name: i.name || '',
      placeholder: i.placeholder || '', value: String(i.value || '').slice(0, 80),
      options: i.tagName === 'SELECT' ? [...i.options].map(o => o.text).slice(0, 30) : undefined
    })).slice(0, 60),
    tables: [...el.querySelectorAll('table')].map(t => ({
      headers: [...t.querySelectorAll('th')].map(h => h.innerText.trim()),
      rows: [...t.querySelectorAll('tbody tr')].slice(0, 5)
              .map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim()))
    }))
  };
}
"""


def _md(v):
    """A value, rendered so it survives a markdown table cell."""
    return str(v).replace("|", "\\|").replace("\n", " ")


class Doc:
    """Collects markdown and prints it as it goes, so a long run is watchable."""

    def __init__(self, path):
        self.path = path
        self.lines = []

    def __call__(self, s=""):
        print(s)
        self.lines.append(s)

    def json(self, obj, cap=12000):
        blob = json.dumps(obj, indent=2, ensure_ascii=False)
        if len(blob) > cap:
            blob = blob[:cap] + "\n... truncated ..."
        self("```json")
        self(blob)
        self("```")
        self()

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines) + "\n")
        print("\n-> wrote %s (%d lines)" % (self.path, len(self.lines)))


class Net:
    """Every request the page made, stamped with what we were doing at the time.

    Bodies are read after the page settles, not inside the event handler:
    blocking a Playwright event handler on a network read is a good way to
    deadlock the whole run.
    """

    def __init__(self, page):
        self.records = []
        self._pending = []
        self.phase = "load"
        page.on("response", self._on_response)

    def _on_response(self, resp):
        try:
            req = resp.request
            if req.resource_type not in ("xhr", "fetch"):
                return
            self._pending.append((self.phase, req.method, resp.url, resp.status, resp))
        except Exception:
            pass

    def drain(self):
        """Turn pending responses into records, reading top-level keys only."""
        for phase, method, url, status, resp in self._pending:
            rec = {"phase": phase, "method": method, "url": url, "status": status}
            try:
                body = resp.json()
                if isinstance(body, dict):
                    rec["top_level_keys"] = sorted(body.keys())[:40]
                    # One level down for the container keys, because "data" alone
                    # tells you nothing about the shape.
                    shape = {}
                    for k, v in list(body.items())[:12]:
                        if isinstance(v, dict):
                            shape[k] = {"type": "object", "keys": sorted(v.keys())[:30]}
                        elif isinstance(v, list):
                            first = v[0] if v else None
                            shape[k] = {"type": "array", "len": len(v),
                                        "item_keys": sorted(first.keys())[:40]
                                        if isinstance(first, dict) else type(first).__name__}
                        else:
                            shape[k] = {"type": type(v).__name__, "value": str(v)[:80]}
                    rec["shape"] = shape
                elif isinstance(body, list):
                    rec["top_level_keys"] = ["<array>"]
                    rec["shape"] = {"len": len(body),
                                    "item_keys": sorted(body[0].keys())[:40]
                                    if body and isinstance(body[0], dict) else None}
            except Exception:
                pass
            self.records.append(rec)
        self._pending = []

    def report(self, doc, phase_filter=None):
        self.drain()
        rows = [r for r in self.records
                if phase_filter is None or r["phase"] == phase_filter]
        if not rows:
            doc("No XHR/fetch calls captured.")
            doc()
            return
        doc("| phase | method | endpoint | status | top-level keys |")
        doc("| --- | --- | --- | --- | --- |")
        for r in rows:
            path = re.sub(r"^https?://[^/]+", "", r["url"])
            doc("| %s | %s | `%s` | %s | %s |"
                % (r["phase"], r["method"], _md(path[:150]), r["status"],
                   _md(", ".join(r.get("top_level_keys", []))[:160])))
        doc()
        doc("**Response shapes** (one level deep, no row data):")
        doc()
        seen = set()
        for r in rows:
            path = re.sub(r"^https?://[^/]+", "", r["url"]).split("?")[0]
            if path in seen or "shape" not in r:
                continue
            seen.add(path)
            doc("`%s %s`" % (r["method"], path))
            doc.json(r["shape"], cap=3000)


# ------------------------------------------------------------------- plumbing

def attach(pw, cdp):
    try:
        browser = pw.chromium.connect_over_cdp(cdp)
    except Exception as e:
        print("Could not attach to Chrome on %s\n  %s\n\n"
              "Start Chrome with the debugging port open and sign in to Orbit "
              "first:\n"
              '  chrome.exe --remote-debugging-port=9222 '
              '--user-data-dir="%%TEMP%%\\orbit-profile"' % (cdp, str(e)[:200]))
        return None
    return browser


def new_page(browser, width=1600, height=1000):
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.new_page()
    page.set_viewport_size({"width": width, "height": height})
    return page


def signed_in(page):
    u = (page.url or "").lower()
    return "login" not in u and "signin" not in u and "auth" not in u


def settle(page, timeout=45000):
    """Wait for real data, not a fixed sleep. Orbit's charts arrive around 8s.

    ABSENCE OF A SKELETON IS NOT PRESENCE OF THE DATA, and that was the bug that
    made this script's first real run useless. Orbit renders its shell, sidebar
    and headings immediately and fills the middle in later, so the skeleton
    check below passed within a second or two of navigation -- before the product
    table existed at all. part_table then reported "No <table> found on the
    overview route" for a route that has a 25-row table on it, and part_tooltips
    and part_design measured a page that was still mostly empty.

    So it now waits for the CONTENT as well: the network to go quiet, and then
    for something that only exists once the data has arrived. Both are bounded,
    and both failing is not fatal -- a page that never settles is still worth
    photographing, and the caller says what it found.
    """
    try:
        page.wait_for_function(
            "() => !document.querySelector(\"[class*='keleton'],[class*='himmer']\")",
            timeout=timeout)
    except Exception:
        pass
    # The data itself. networkidle is the reliable signal here -- measured: the
    # table appears on the same tick the last XHR resolves.
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    # A table, a chart or a stat card -- whichever this route has. Any of them
    # means the middle of the page has been filled in.
    try:
        page.wait_for_function(
            "() => !!(document.querySelector('table tbody tr') "
            "         || document.querySelector('svg [class*=recharts]') "
            "         || /\\d/.test(document.body.innerText))",
            timeout=12000)
    except Exception:
        pass
    page.wait_for_timeout(2500)


def shot(page, name):
    os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, name if name.endswith(".png") else name + ".png")
    try:
        page.screenshot(path=path)
    except Exception as e:
        print("  (screenshot %s failed: %s)" % (name, str(e)[:100]))
        return None
    return path


def shots_down(page, prefix, max_screens=8):
    """Photograph the whole page by driving the INNER scroller.

    full_page=True does not work on Orbit -- the app shell is height:100% with
    the scroll on a child, so a full-page shot stops at the fold. This steps the
    real scroller down a viewport at a time.
    """
    info = page.evaluate(SCROLLER_JS)
    paths = []
    if not info.get("found"):
        p = shot(page, "%s_full" % prefix)
        return ([p] if p else []), info
    steps = min(max_screens,
                max(1, int(info["scrollHeight"] / max(1, info["clientHeight"])) + 1))
    for i in range(steps):
        page.evaluate(
            "(i) => { const el = document.querySelector('[data-orbit-scroller]');"
            "  if (el) { el.scrollTop = i * (el.clientHeight - 60);"
            "            window.__scrollTop = el.scrollTop; } }", i)
        page.wait_for_timeout(700)
        p = shot(page, "%s_s%02d" % (prefix, i))
        if p:
            paths.append(p)
    page.evaluate("() => { const el = document.querySelector('[data-orbit-scroller]');"
                  "  if (el) { el.scrollTop = 0; window.__scrollTop = 0; } }")
    page.wait_for_timeout(500)
    return paths, info


def page_text(page):
    try:
        return page.evaluate("() => (document.body.innerText || '').trim()")
    except Exception:
        return ""


def find_by_text(page, text, tags=("button", "a", "[role='button']", "div", "span")):
    """A clickable whose visible text matches. Exact first, then contains."""
    for sel in ("%s:has-text(\"%s\")" % (t, text) for t in tags):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def close_overlay(page):
    """Get back to the page. Escape, then a close button, then a corner click."""
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    except Exception:
        pass
    if page.evaluate(OVERLAY_JS):
        for sel in ("[aria-label*='lose']", "button:has-text('Close')",
                    "button:has-text('Cancel')", "[class*='closeBtn']"):
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=2000)
                    page.wait_for_timeout(500)
                    break
            except Exception:
                continue
    if page.evaluate(OVERLAY_JS):
        try:
            page.mouse.click(6, 6)
            page.wait_for_timeout(400)
        except Exception:
            pass


def dump_scan(doc, data, limit=400):
    """The measured page, in reading order, indented by depth."""
    nodes = data.get("nodes", [])
    doc("%d elements measured at %dpx wide.  \n(Boxes are `w×h at (x, y)`; `y` "
        "is from the top of the document.)" % (len(nodes), data["viewport"]["w"]))
    doc()
    ordered = sorted(nodes, key=lambda x: (x["box"][3], x["box"][2]))
    for n in ordered[:limit]:
        head = "%s`%s`%s" % ("  " * min(n["depth"], 8), n["tag"],
                             ("." + n["cls"].split()[0]) if n["cls"] else "")
        doc("- %s — **%s×%s** at (%s, %s)"
            % (head, n["box"][0], n["box"][1], n["box"][2], n["box"][3]))
        if n.get("text"):
            doc("    - text: `%s`" % _md(n["text"]))
        if n.get("title"):
            doc("    - label: `%s`" % _md(n["title"]))
        style = {k: v for k, v in n.items()
                 if k not in ("depth", "tag", "cls", "text", "box", "title")}
        if style:
            doc("    - " + "; ".join("%s: `%s`" % (k, _md(v))
                                     for k, v in sorted(style.items())))
    if len(ordered) > limit:
        doc()
        doc("_(%d further elements omitted; re-run with a higher --limit for the "
            "rest.)_" % (len(ordered) - limit))
    doc()


# ------------------------------------------------------------------ the parts

def part_routes(page, net, doc, args):
    """Every inventory route: what is on it, measured, photographed, and the
    calls it makes on load."""
    doc("# Part A — Inventory routes, measured")
    doc()
    doc("Captured %s from a signed-in Chrome over the DevTools protocol. Brand "
        "`%s`, marketplace `%s` (Amazon US)."
        % (time.strftime("%Y-%m-%d %H:%M"), BRAND, MP))
    doc()
    for name, url in ROUTES:
        doc("---")
        doc()
        doc("## Route: `%s`" % re.sub(r"^https?://[^/]+", "", url))
        doc()
        net.phase = "load:%s" % name
        t0 = time.time()
        try:
            page.goto(url, wait_until="commit", timeout=60000)
        except Exception as e:
            doc("Navigation failed: %s" % str(e)[:200])
            doc()
            continue
        settle(page)
        if not signed_in(page):
            doc("**Redirected to %s — Chrome is not signed in.** Sign in in that "
                "window and re-run." % page.url)
            doc()
            return False
        doc("Settled in **%d ms**." % int((time.time() - t0) * 1000))
        doc()
        paths, sinfo = shots_down(page, name)
        doc("Screenshots: %s  \nScroll container: `%s`"
            % (", ".join("`%s`" % p for p in paths) or "none", _md(sinfo)))
        doc()
        doc("### Visible text, whole page")
        doc()
        doc("```")
        doc(page_text(page)[:14000])
        doc("```")
        doc()
        doc("### Measured elements")
        doc()
        try:
            dump_scan(doc, page.evaluate(SCAN_JS, PROPS), limit=args.limit)
        except Exception as e:
            doc("Scan failed: %s" % str(e)[:200])
            doc()
        doc("### Calls made on load")
        doc()
        net.report(doc, phase_filter="load:%s" % name)
    return True


def part_clicks(page, net, doc, args):
    """The cockpit buttons: what each one opens."""
    doc("# Part B — Buttons and what they open")
    doc()
    url = PRIMARY()
    net.phase = "load:overview"
    page.goto(url, wait_until="commit", timeout=60000)
    settle(page)
    if not signed_in(page):
        doc("**Not signed in.**")
        return False

    for label in COCKPIT_BUTTONS:
        doc("---")
        doc()
        doc("## `%s`" % label)
        doc()
        btn = find_by_text(page, label)
        if not btn:
            doc("No control with this text found on the page.")
            doc()
            continue
        try:
            box = btn.bounding_box()
            style = btn.evaluate(
                "(el) => { const cs = getComputedStyle(el); const o = {};"
                " ['background','background-color','background-image','color','border',"
                "  'border-radius','padding','font-size','font-weight','box-shadow',"
                "  'letter-spacing','text-transform']"
                "  .forEach(p => o[p] = cs.getPropertyValue(p)); return o; }")
            doc("Button: **%.0f×%.0f** at (%.0f, %.0f)"
                % (box["width"], box["height"], box["x"], box["y"]) if box else "Button box unknown")
            doc()
            doc("| property | value |")
            doc("| --- | --- |")
            for k, v in style.items():
                if v and v not in ("none", "normal", "0px"):
                    doc("| %s | `%s` |" % (k, _md(v[:180])))
            doc()
        except Exception:
            pass

        before_url = page.url
        net.phase = "click:%s" % label
        try:
            btn.click(timeout=8000)
        except Exception as e:
            doc("Click failed: %s" % str(e)[:200])
            doc()
            continue
        page.wait_for_timeout(2500)
        settle(page, timeout=25000)
        slug = re.sub(r"[^a-z0-9]+", "_", label.lower())
        shot(page, "click_%s" % slug)

        if page.url != before_url:
            doc("**Navigates to** `%s`" % re.sub(r"^https?://[^/]+", "", page.url))
            doc()
            paths, _ = shots_down(page, "click_%s_page" % slug)
            doc("Screenshots: %s" % (", ".join("`%s`" % p for p in paths) or "none"))
            doc()
            doc("```")
            doc(page_text(page)[:10000])
            doc("```")
            doc()
        else:
            ov = page.evaluate(OVERLAY_JS)
            if ov:
                doc("**Opens an overlay** (`%s`, role=`%s`) — %s×%s at (%s, %s)"
                    % (ov["cls"], ov["role"] or "—", *ov["box"]))
                doc()
                doc("| style | value |")
                doc("| --- | --- |")
                for k, v in ov["style"].items():
                    if v and v not in ("none", "normal", "0px"):
                        doc("| %s | `%s` |" % (k, _md(str(v)[:180])))
                doc()
                if ov["headings"]:
                    doc("**Headings:** %s" % " · ".join(ov["headings"]))
                    doc()
                if ov["buttons"]:
                    doc("**Buttons:** %s" % " · ".join("`%s`" % b for b in ov["buttons"]))
                    doc()
                if ov["inputs"]:
                    doc("**Inputs:**")
                    doc.json(ov["inputs"], cap=4000)
                if ov["tables"]:
                    doc("**Tables:**")
                    doc.json(ov["tables"], cap=5000)
                doc("**Full text of the overlay:**")
                doc()
                doc("```")
                doc(ov["text"])
                doc("```")
                doc()
            else:
                doc("No overlay and no navigation — the page changed in place. "
                    "Text after the click:")
                doc()
                doc("```")
                doc(page_text(page)[:8000])
                doc("```")
                doc()

        doc("### Calls this click made")
        doc()
        net.report(doc, phase_filter="click:%s" % label)

        close_overlay(page)
        if page.url != url:
            net.phase = "renav"
            page.goto(url, wait_until="commit", timeout=60000)
            settle(page)
    return True


def part_table(page, net, doc, args):
    """The product table: columns, sorting, search, a row, an expansion."""
    doc("# Part C — The product table")
    doc()
    url = PRIMARY()
    net.phase = "load:overview"
    page.goto(url, wait_until="commit", timeout=60000)
    settle(page)
    if not signed_in(page):
        doc("**Not signed in.**")
        return False

    anatomy = page.evaluate(r"""
    () => {
      const t = document.querySelector('table');
      if (!t) return null;
      const cs = getComputedStyle(t);
      const th = [...t.querySelectorAll('th')].map(h => {
        const s = getComputedStyle(h), r = h.getBoundingClientRect();
        return {text: h.innerText.trim(), width: +r.width.toFixed(1),
                padding: s.padding, fontSize: s.fontSize, fontWeight: s.fontWeight,
                color: s.color, textTransform: s.textTransform,
                letterSpacing: s.letterSpacing, background: s.backgroundColor,
                sortable: /[▽▼▲▾▴]/.test(h.innerText) ||
                          h.querySelector('svg') !== null};
      });
      const rows = [...t.querySelectorAll('tbody tr')];
      const first = rows[0];
      const rowStyle = first ? (() => { const s = getComputedStyle(first),
                                              r = first.getBoundingClientRect();
        return {height: +r.height.toFixed(1), borderBottom: s.borderBottom,
                background: s.backgroundColor}; })() : null;
      const cellStyle = first && first.querySelector('td')
        ? (() => { const s = getComputedStyle(first.querySelector('td'));
                   return {padding: s.padding, fontSize: s.fontSize,
                           lineHeight: s.lineHeight, color: s.color}; })() : null;
      // Every distinct status chip on the page, with its colours -- this is the
      // STATUS column legend, read off the rendered chips rather than guessed.
      const chips = {};
      rows.forEach(tr => {
        [...tr.querySelectorAll('td:last-child *, [class*="adge"], [class*="hip"], [class*="tatus"]')]
          .forEach(el => {
            const txt = (el.innerText || '').trim();
            if (!txt || txt.length > 24 || chips[txt]) return;
            const s = getComputedStyle(el);
            if (s.backgroundColor === 'rgba(0, 0, 0, 0)' && s.color === 'rgb(0, 0, 0)') return;
            chips[txt] = {color: s.color, background: s.backgroundColor,
                          border: s.border, borderRadius: s.borderRadius,
                          padding: s.padding, fontSize: s.fontSize,
                          fontWeight: s.fontWeight, textTransform: s.textTransform};
          });
      });
      return {
        tableStyle: {borderCollapse: cs.borderCollapse, width: cs.width,
                     background: cs.backgroundColor, fontSize: cs.fontSize},
        headers: th, rowCount: rows.length, rowStyle, cellStyle, statusChips: chips,
        sampleRows: rows.slice(0, 6).map(tr =>
          [...tr.querySelectorAll('td')].map(td => td.innerText.trim().slice(0, 60))),
        pagination: [...document.querySelectorAll('button')]
          .map(b => b.innerText.trim())
          .filter(t => /prev|next|page|\d+\s*\/\s*\d+/i.test(t)).slice(0, 12),
        counts: [...document.querySelectorAll('*')].map(e =>
          [...e.childNodes].filter(n => n.nodeType === 3)
            .map(n => n.textContent.trim()).join(' '))
          .filter(t => /\b\d+\s+(products|rows|ASINs|SKUs|results)\b/i.test(t))
          .slice(0, 10)
      };
    }""")
    if not anatomy:
        doc("No `<table>` found on the overview route.")
        doc()
        return True

    doc("## Table anatomy")
    doc()
    doc.json({k: v for k, v in anatomy.items() if k != "sampleRows"}, cap=14000)
    doc("**First rows as rendered** (values, so the column meanings are legible):")
    doc()
    doc.json(anatomy["sampleRows"], cap=4000)

    # Search
    doc("## Search")
    doc()
    try:
        box = page.locator("input[placeholder*='Search']").first
        if box.count():
            ph = box.get_attribute("placeholder")
            sty = box.evaluate(
                "(el) => { const cs = getComputedStyle(el); const r = el.getBoundingClientRect();"
                " return {w: r.width, h: r.height, background: cs.backgroundColor,"
                "  border: cs.border, borderRadius: cs.borderRadius, padding: cs.padding,"
                "  fontSize: cs.fontSize, color: cs.color, placeholderColor: cs.color}; }")
            doc("Placeholder: `%s`" % ph)
            doc()
            doc.json(sty, cap=1500)
            net.phase = "search"
            for term in (args.search_term, "B0"):
                box.fill(term)
                page.wait_for_timeout(1800)
                n = page.evaluate("() => document.querySelectorAll('tbody tr').length")
                doc("- searching `%s` → **%d rows**" % (term, n))
            shot(page, "table_search")
            box.fill("")
            page.wait_for_timeout(1500)
            doc()
            doc("Calls made while searching (empty means the filter is client-side):")
            doc()
            net.report(doc, phase_filter="search")
        else:
            doc("No search input found.")
            doc()
    except Exception as e:
        doc("Search probe failed: %s" % str(e)[:200])
        doc()

    # Sorting
    doc("## Sorting")
    doc()
    net.phase = "sort"
    for i, h in enumerate(anatomy["headers"]):
        name = h["text"].strip()
        if not name:
            continue
        try:
            th = page.locator("th").nth(i)
            before = page.evaluate(
                "() => [...document.querySelectorAll('tbody tr')].slice(0,5)"
                ".map(r => (r.innerText||'').replace(/\\s+/g,' ').slice(0,60))")
            th.click(timeout=4000)
            page.wait_for_timeout(1500)
            after = page.evaluate(
                "() => [...document.querySelectorAll('tbody tr')].slice(0,5)"
                ".map(r => (r.innerText||'').replace(/\\s+/g,' ').slice(0,60))")
            hdr_now = page.locator("th").nth(i).inner_text().strip()
            changed = before != after
            doc("### `%s`" % name)
            doc()
            doc("- clicking it %s the row order; header now reads `%s`"
                % ("**changes**" if changed else "does not change", _md(hdr_now)))
            if changed:
                doc("- top rows before: `%s`" % _md(" / ".join(before[:3])))
                doc("- top rows after:  `%s`" % _md(" / ".join(after[:3])))
            # Second click: does it reverse?
            th.click(timeout=4000)
            page.wait_for_timeout(1400)
            again = page.evaluate(
                "() => [...document.querySelectorAll('tbody tr')].slice(0,5)"
                ".map(r => (r.innerText||'').replace(/\\s+/g,' ').slice(0,60))")
            doc("- clicking again: %s"
                % ("reverses (descending ↔ ascending)" if again != after
                   else "no further change — single-direction sort"))
            doc()
        except Exception as e:
            doc("### `%s`" % name)
            doc()
            doc("- not clickable / failed: %s" % str(e)[:120])
            doc()
    doc("Calls made while sorting (empty means sorting is client-side):")
    doc()
    net.report(doc, phase_filter="sort")

    # Expand arrow
    doc("## Row expansion (the ▶ control)")
    doc()
    net.phase = "expand"
    try:
        before_rows = page.evaluate("() => document.querySelectorAll('tbody tr').length")
        arrow = None
        for sel in ("tbody tr:first-child [class*='xpand']",
                    "tbody tr:first-child button:has-text('▶')",
                    "tbody tr:first-child svg", "tbody tr:first-child button"):
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                arrow = loc
                break
        if arrow:
            arrow.click(timeout=5000)
            page.wait_for_timeout(1800)
            after_rows = page.evaluate("() => document.querySelectorAll('tbody tr').length")
            shot(page, "table_expanded")
            doc("Rows before: **%d**, after: **%d** — %d row(s) revealed."
                % (before_rows, after_rows, after_rows - before_rows))
            doc()
            expanded = page.evaluate(
                "() => [...document.querySelectorAll('tbody tr')].slice(0,4)"
                ".map(r => r.innerText.replace(/\\s+/g,' ').slice(0,300))")
            doc.json(expanded, cap=3000)
            anim = page.evaluate(
                "() => { const r = document.querySelector('tbody tr:nth-child(2)');"
                " if (!r) return null; const cs = getComputedStyle(r);"
                " return {transition: cs.transition, animation: cs.animation,"
                "         duration: cs.transitionDuration || cs.animationDuration,"
                "         easing: cs.transitionTimingFunction}; }")
            doc("Expansion motion, as the browser resolved it:")
            doc.json(anim, cap=1200)
            arrow.click(timeout=5000)
            page.wait_for_timeout(1200)
        else:
            doc("No expand control found on the first row.")
            doc()
    except Exception as e:
        doc("Expansion probe failed: %s" % str(e)[:200])
        doc()
    net.report(doc, phase_filter="expand")

    # Row click -> drawer
    doc("## Clicking a row")
    doc()
    net.phase = "rowclick"
    try:
        page.locator("tbody tr").first.click(timeout=6000)
        page.wait_for_timeout(2500)
        shot(page, "table_row_drawer")
        ov = page.evaluate(OVERLAY_JS)
        if ov:
            doc("Opens `%s` — %s×%s at (%s, %s)" % (ov["cls"], *ov["box"]))
            doc()
            doc.json({k: ov[k] for k in ("style", "headings", "buttons", "inputs", "tables")},
                     cap=8000)
            doc("**Drawer text:**")
            doc()
            doc("```")
            doc(ov["text"])
            doc("```")
            doc()
        elif page.url != url:
            doc("Navigates to `%s`" % re.sub(r"^https?://[^/]+", "", page.url))
            doc()
            doc("```")
            doc(page_text(page)[:8000])
            doc("```")
            doc()
        else:
            doc("Row click did nothing visible.")
            doc()
        net.report(doc, phase_filter="rowclick")
        close_overlay(page)
    except Exception as e:
        doc("Row click failed: %s" % str(e)[:200])
        doc()
    return True


def part_tooltips(page, net, doc, args):
    """Hover every info icon and record what it explains -- this is where the
    rule definitions ("what makes an ASIN critical") actually live."""
    doc("# Part D — Info tooltips")
    doc()
    doc("Orbit states its own rules in these tooltips. Everything here is copy "
        "read off the page, not inference.")
    doc()
    for name, url in TOOLTIP_ROUTES():
        doc("## Route `%s`" % name)
        doc()
        net.phase = "tooltips:%s" % name
        page.goto(url, wait_until="commit", timeout=60000)
        settle(page)
        if not signed_in(page):
            doc("**Not signed in.**")
            return False
        n = page.evaluate(r"""
        () => {
          const cands = [...document.querySelectorAll(
            "[class*='nfo'],[aria-label*='nfo'],[title],[data-tooltip]," +
            "svg[class*='nfo'],[class*='ooltip-trigger'],[class*='elp']")]
            .filter(el => { const r = el.getBoundingClientRect();
                            return r.width > 6 && r.width < 60 && r.height < 60; });
          cands.forEach((el, i) => el.setAttribute('data-orbit-tip', String(i)));
          return cands.length;
        }""")
        doc("%d candidate info trigger(s) found." % n)
        doc()
        for i in range(min(n, args.max_tooltips)):
            try:
                el = page.locator("[data-orbit-tip='%d']" % i).first
                if not el.count() or not el.is_visible():
                    continue
                near = el.evaluate(
                    "(e) => { let p = e; for (let k=0;k<4 && p;k++) p = p.parentElement;"
                    "  return p ? (p.innerText||'').replace(/\\s+/g,' ').slice(0,120) : ''; }")
                static = el.get_attribute("title") or el.get_attribute("data-tooltip") or ""
                el.hover(timeout=4000)
                page.wait_for_timeout(900)
                tip = page.evaluate(r"""
                () => {
                  const t = [...document.querySelectorAll(
                     "[role='tooltip'],[class*='ooltip'],[class*='opover']")]
                    .filter(el => { const cs = getComputedStyle(el);
                                    const r = el.getBoundingClientRect();
                                    return cs.display!=='none' && cs.visibility!=='hidden'
                                           && r.width>20 && r.height>10; });
                  if (!t.length) return null;
                  const el = t[t.length-1], cs = getComputedStyle(el),
                        r = el.getBoundingClientRect();
                  return {text: (el.innerText||'').trim().slice(0,1200),
                          box: [+r.width.toFixed(1), +r.height.toFixed(1),
                                +r.x.toFixed(1), +r.y.toFixed(1)],
                          style: {background: cs.backgroundColor, color: cs.color,
                                  border: cs.border, borderRadius: cs.borderRadius,
                                  padding: cs.padding, fontSize: cs.fontSize,
                                  lineHeight: cs.lineHeight, maxWidth: cs.maxWidth,
                                  boxShadow: cs.boxShadow}};
                }""")
                if tip or static:
                    doc("### Near: `%s`" % _md(near))
                    doc()
                    if static:
                        doc("`title` attribute: `%s`" % _md(static))
                        doc()
                    if tip:
                        doc("> %s" % tip["text"].replace("\n", "  \n> "))
                        doc()
                        doc("Tooltip box %s×%s at (%s, %s):" % tuple(tip["box"]))
                        doc.json(tip["style"], cap=1200)
                        shot(page, "tip_%s_%02d" % (name, i))
            except Exception:
                continue
        doc()
    return True


def part_steven(page, net, doc, args):
    """Steven: open the agent and actually talk to it."""
    doc("# Part E — Steven, the inventory agent")
    doc()
    url = PRIMARY()
    net.phase = "load:overview"
    page.goto(url, wait_until="commit", timeout=60000)
    settle(page)
    if not signed_in(page):
        doc("**Not signed in.**")
        return False

    opened = False
    for label in ("Steven actions", "Ask Steven for forecast plan", "Steven"):
        btn = find_by_text(page, label)
        if btn:
            net.phase = "steven:open"
            try:
                btn.click(timeout=8000)
                page.wait_for_timeout(3000)
                opened = True
                doc("Opened via `%s`." % label)
                doc()
                break
            except Exception:
                continue
    if not opened:
        # The floating agent dock, ~100px circular avatar bottom-right.
        try:
            page.evaluate(
                "() => { const el = [...document.querySelectorAll('*')].find(e => {"
                "  const cs = getComputedStyle(e), r = e.getBoundingClientRect();"
                "  return cs.position === 'fixed' && r.width > 50 && r.width < 140"
                "     && parseFloat(cs.borderRadius) > 20"
                "     && r.y > innerHeight * 0.6 && r.x > innerWidth * 0.6; });"
                "  if (el) el.setAttribute('data-orbit-dock','1'); }")
            dock = page.locator("[data-orbit-dock]").first
            if dock.count():
                net.phase = "steven:open"
                dock.click(timeout=6000)
                page.wait_for_timeout(3000)
                opened = True
                doc("Opened via the floating agent dock (bottom-right avatar).")
                doc()
        except Exception:
            pass
    if not opened:
        doc("Could not find a way to open Steven on this route.")
        doc()
        return True

    shot(page, "steven_open")
    ov = page.evaluate(OVERLAY_JS)
    doc("## The interface that opens")
    doc()
    if ov:
        doc("`%s` (role=`%s`) — %s×%s at (%s, %s)"
            % (ov["cls"], ov["role"] or "—", *ov["box"]))
        doc()
        doc.json({k: ov[k] for k in ("style", "headings", "buttons", "inputs")}, cap=8000)
        doc("**Everything it says before being asked anything** — this is the "
            "capability list, in Orbit's own words:")
        doc()
        doc("```")
        doc(ov["text"])
        doc("```")
        doc()
    else:
        doc("No overlay detected; the agent may squeeze the app shell instead "
            "(the audit noted `--chat-drawer-width`). Page text:")
        doc()
        doc("```")
        doc(page_text(page)[:8000])
        doc("```")
        doc()
    doc("### Calls made when opening Steven")
    doc()
    net.report(doc, phase_filter="steven:open")

    doc("## Conversation")
    doc()
    doc("Each question was typed into Steven's own input and the reply is "
        "transcribed verbatim.")
    doc()
    for qi, q in enumerate(STEVEN_QUESTIONS):
        doc("### Q%d — %s" % (qi + 1, q))
        doc()
        net.phase = "steven:q%d" % (qi + 1)
        try:
            inp = None
            for sel in ("textarea", "input[type='text']", "[contenteditable='true']"):
                loc = page.locator(sel).last
                if loc.count() and loc.is_visible():
                    inp = loc
                    break
            if not inp:
                doc("No input found — cannot ask.")
                doc()
                break
            before = page.evaluate("() => (document.body.innerText||'').length")
            inp.click(timeout=4000)
            inp.fill(q)
            page.wait_for_timeout(400)
            page.keyboard.press("Enter")
            # Wait for the answer to stop growing rather than a fixed sleep --
            # these stream in, and a fixed wait truncates them.
            stable, last = 0, -1
            for _ in range(int(args.steven_wait / 1.5)):
                page.wait_for_timeout(1500)
                now = page.evaluate("() => (document.body.innerText||'').length")
                if now == last and now > before:
                    stable += 1
                    if stable >= 3:
                        break
                else:
                    stable = 0
                last = now
            shot(page, "steven_q%d" % (qi + 1))
            reply = page.evaluate(r"""
            () => {
              const pools = [...document.querySelectorAll(
                "[class*='essage'],[class*='ubble'],[class*='hat'] li," +
                "[class*='hat'] p,[role='log'] *")];
              const txts = pools.map(e => (e.innerText||'').trim())
                                .filter(t => t.length > 40);
              return txts.length ? txts[txts.length-1].slice(0, 8000)
                                 : (document.body.innerText||'').slice(-6000);
            }""")
            doc("> " + reply.replace("\n", "  \n> "))
            doc()
            net.report(doc, phase_filter="steven:q%d" % (qi + 1))
        except Exception as e:
            doc("Failed: %s" % str(e)[:200])
            doc()
    return True


def part_design(page, net, doc, args):
    """The cockpit banner and stat cards, to the pixel."""
    doc("# Part F — Design specification")
    doc()
    net.phase = "design"
    page.goto(PRIMARY(), wait_until="commit", timeout=60000)
    settle(page)
    if not signed_in(page):
        doc("**Not signed in.**")
        return False

    doc("## Design tokens the page defines")
    doc()
    tokens = page.evaluate(r"""
    () => {
      const out = {};
      for (const sheet of document.styleSheets) {
        let rules; try { rules = sheet.cssRules; } catch (e) { continue; }
        for (const rule of rules) {
          if (!rule.style || !rule.selectorText) continue;
          if (!/^:root|^html|^\[data-theme/.test(rule.selectorText)) continue;
          for (const p of rule.style) if (p.startsWith('--'))
            out[p] = rule.style.getPropertyValue(p).trim();
        }
      }
      return out;
    }""")
    doc.json(tokens, cap=9000)

    doc("## Motion, from the page's own stylesheets")
    doc()
    motion = page.evaluate(r"""
    () => {
      const keyframes = {}, durations = {}, easings = {};
      for (const sheet of document.styleSheets) {
        let rules; try { rules = sheet.cssRules; } catch (e) { continue; }
        for (const rule of rules) {
          if (rule.type === CSSRule.KEYFRAMES_RULE) {
            keyframes[rule.name] = [...rule.cssRules]
              .map(k => k.keyText + ' {' + k.style.cssText + '}').join(' ').slice(0, 300);
          } else if (rule.style) {
            const d = rule.style.animationDuration || rule.style.transitionDuration;
            if (d) durations[d] = (durations[d] || 0) + 1;
            const e = rule.style.animationTimingFunction || rule.style.transitionTimingFunction;
            if (e) easings[e] = (easings[e] || 0) + 1;
          }
        }
      }
      return {durations, easings, keyframeCount: Object.keys(keyframes).length,
              keyframes};
    }""")
    doc("Durations by frequency, easing curves, and every named keyframe:")
    doc.json({"durations": motion["durations"], "easings": motion["easings"],
              "keyframeCount": motion["keyframeCount"]}, cap=4000)
    doc.json(motion["keyframes"], cap=9000)

    doc("## The cockpit banner")
    doc()
    banner = page.evaluate(r"""
    () => {
      // The banner is the widest painted block above the stat-card row that
      // carries the "critical ASINs" line. Found by content, not class name.
      const hit = [...document.querySelectorAll('*')].find(e =>
        /critical ASINs need action/i.test(e.textContent || '') &&
        e.getBoundingClientRect().width > 500);
      if (!hit) return null;
      let el = hit;
      for (let i = 0; i < 6 && el.parentElement; i++) {
        const cs = getComputedStyle(el);
        if (cs.backgroundImage !== 'none' ||
            cs.backgroundColor !== 'rgba(0, 0, 0, 0)') break;
        el = el.parentElement;
      }
      const cs = getComputedStyle(el), r = el.getBoundingClientRect();
      const style = {};
      ['background','background-image','background-color','background-size',
       'border','border-radius','padding','margin','box-shadow','overflow',
       'min-height','backdrop-filter','color']
        .forEach(p => { const v = cs.getPropertyValue(p);
                        if (v && v !== 'none') style[p] = v.slice(0, 400); });
      const texts = [...el.querySelectorAll('*')].map(c => {
        const own = [...c.childNodes].filter(n => n.nodeType === 3)
                      .map(n => n.textContent.trim()).join(' ').trim();
        if (!own) return null;
        const s = getComputedStyle(c), rr = c.getBoundingClientRect();
        return {text: own.slice(0, 110), fontSize: s.fontSize,
                fontWeight: s.fontWeight, color: s.color,
                letterSpacing: s.letterSpacing, lineHeight: s.lineHeight,
                textTransform: s.textTransform,
                box: [+rr.width.toFixed(1), +rr.height.toFixed(1),
                      +rr.x.toFixed(1), +rr.y.toFixed(1)]};
      }).filter(Boolean);
      return {box: [+r.width.toFixed(1), +r.height.toFixed(1),
                    +r.x.toFixed(1), +r.y.toFixed(1)], style, texts};
    }""")
    if banner:
        doc("Banner box: **%s×%s** at (%s, %s)" % tuple(banner["box"]))
        doc()
        doc("| property | value |")
        doc("| --- | --- |")
        for k, v in banner["style"].items():
            doc("| %s | `%s` |" % (k, _md(v)))
        doc()
        doc("**Every text element inside it:**")
        doc.json(banner["texts"], cap=10000)
        try:
            page.locator("text=critical ASINs need action").first.screenshot(
                path=os.path.join(SHOTS, "cockpit_banner.png"))
        except Exception:
            pass
    else:
        doc("Could not locate the cockpit banner by its text.")
        doc()

    doc("## The stat cards")
    doc()
    cards = page.evaluate(r"""
    () => {
      const names = ['NETWORK UNITS','AMAZON FBA','COGS VALUE','REVIEW QUEUE',
                     'Revenue at Risk','Inventory at Cost','Avg Cover'];
      const out = [];
      names.forEach(n => {
        const hit = [...document.querySelectorAll('*')].find(e => {
          const own = [...e.childNodes].filter(x => x.nodeType === 3)
                        .map(x => x.textContent.trim()).join(' ').trim();
          return own && own.toLowerCase() === n.toLowerCase();
        });
        if (!hit) return;
        let card = hit;
        for (let i = 0; i < 5 && card.parentElement; i++) {
          const r = card.getBoundingClientRect();
          if (r.width > 140 && r.height > 60) break;
          card = card.parentElement;
        }
        const cs = getComputedStyle(card), r = card.getBoundingClientRect();
        const style = {};
        ['background','background-image','background-color','border','border-radius',
         'padding','box-shadow','gap','display','flex-direction','min-width']
          .forEach(p => { const v = cs.getPropertyValue(p);
                          if (v && v !== 'none') style[p] = v.slice(0, 300); });
        const parts = [...card.querySelectorAll('*')].map(c => {
          const own = [...c.childNodes].filter(x => x.nodeType === 3)
                        .map(x => x.textContent.trim()).join(' ').trim();
          if (!own) return null;
          const s = getComputedStyle(c);
          return {text: own.slice(0, 90), fontSize: s.fontSize, fontWeight: s.fontWeight,
                  color: s.color, letterSpacing: s.letterSpacing,
                  textTransform: s.textTransform};
        }).filter(Boolean);
        out.push({label: n, box: [+r.width.toFixed(1), +r.height.toFixed(1),
                                  +r.x.toFixed(1), +r.y.toFixed(1)], style, parts});
      });
      return out;
    }""")
    doc.json(cards, cap=16000)

    doc("## Tab bar, active vs inactive")
    doc()
    tabs = page.evaluate(r"""
    () => {
      const words = ['Overview','Forecasting','Actions','Shipments','Comms'];
      const out = [];
      words.forEach(w => {
        const el = [...document.querySelectorAll('a,button,[role="tab"]')]
          .find(e => (e.innerText || '').trim() === w);
        if (!el) return;
        const cs = getComputedStyle(el), r = el.getBoundingClientRect();
        const style = {};
        ['color','background-color','background-image','border','border-bottom',
         'border-radius','padding','font-size','font-weight','opacity',
         'letter-spacing','box-shadow']
          .forEach(p => { const v = cs.getPropertyValue(p);
                          if (v && v !== 'none') style[p] = v.slice(0,200); });
        out.push({tab: w, active: /ctive|elected/.test(String(el.className)) ||
                                  el.getAttribute('aria-selected') === 'true',
                  className: String(el.className).slice(0,70),
                  box: [+r.width.toFixed(1), +r.height.toFixed(1),
                        +r.x.toFixed(1), +r.y.toFixed(1)], style});
      });
      return out;
    }""")
    doc.json(tabs, cap=8000)
    shot(page, "design_overview_top")
    return True


def part_assemble(args):
    """Merge the fragments into the single document the brief asks for."""
    order = [("routes", "Part A — Inventory routes, measured"),
             ("clicks", "Part B — Buttons and what they open"),
             ("table", "Part C — The product table"),
             ("tooltips", "Part D — Info tooltips"),
             ("steven", "Part E — Steven, the inventory agent"),
             ("design", "Part F — Design specification")]
    out = ["# Orbit — Inventory system, complete extraction", "",
           "Brand `%s`, marketplace `%s` (Amazon US). Captured %s from a "
           "signed-in Chrome over the DevTools protocol."
           % (BRAND, MP, time.strftime("%Y-%m-%d %H:%M")), "",
           "**How to read this.** Everything below is either MEASURED (read off "
           "the live page: computed styles, rendered text, network responses) or "
           "QUOTED (Orbit's own tooltip and agent copy). Where a calculation is "
           "inferred from field names rather than stated by Orbit, it is marked "
           "*inferred*. Orbit's server code is not visible, so no formula here "
           "should be treated as confirmed unless Orbit states it.", "",
           "Screenshots are in `%s/`." % SHOTS, "", "## Contents", ""]
    present = []
    for slug, title in order:
        p = os.path.join(OUTDIR, "%s.md" % slug)
        if os.path.exists(p):
            present.append((slug, title, p))
            out.append("- %s" % title)
        else:
            out.append("- %s — *not captured (run `%s`)*" % (title, slug))
    out += ["", "---", ""]
    for slug, title, p in present:
        with open(p, encoding="utf-8") as f:
            out.append(f.read())
        out += ["", "---", ""]
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("Wrote %s from %d fragment(s)." % (args.out, len(present)))
    return 0


PARTS = {"routes": part_routes, "clicks": part_clicks, "table": part_table,
         "tooltips": part_tooltips, "steven": part_steven, "design": part_design}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("part", choices=list(PARTS) + ["assemble", "all"])
    p.add_argument("--section", default="inventory", choices=sorted(SECTIONS),
                   help="which part of Orbit to capture. Chooses the route "
                        "table and the output directory; everything else is "
                        "shared (Rule 12).")
    p.add_argument("--buttons", default="",
                   help="comma-separated button labels to click. On --section "
                        "ppc this is EMPTY by default and must be named "
                        "explicitly: an advertising button writes to live "
                        "campaigns spending real money (CLAUDE.md Rule 8).")
    p.add_argument("--cdp", default=CDP)
    p.add_argument("--out", default="")
    p.add_argument("--width", type=int, default=1600)
    p.add_argument("--limit", type=int, default=400,
                   help="max elements listed per route in the scan")
    p.add_argument("--max-tooltips", type=int, default=30)
    p.add_argument("--steven-wait", type=float, default=60,
                   help="seconds to let each Steven answer finish streaming")
    p.add_argument("--search-term", default="sandal")
    a = p.parse_args(argv)

    # Point the module at the chosen section BEFORE anything reads ROUTES,
    # OUTDIR or SHOTS -- part_assemble included, which globs OUTDIR.
    sec = use_section(a.section)
    if a.buttons.strip():
        globals()["COCKPIT_BUTTONS"] = [b.strip() for b in a.buttons.split(",")
                                        if b.strip()]
    if not a.out:
        a.out = "orbit_%s_complete.md" % a.section
    print("section: %s -> %s (%d route(s), %d button(s) to click)"
          % (a.section, OUTDIR, len(ROUTES), len(COCKPIT_BUTTONS)))
    if a.section != "inventory" and not COCKPIT_BUTTONS:
        print("  no buttons will be clicked. Pass --buttons \"A,B\" to click "
              "specific ones -- but read CLAUDE.md Rule 8 first: an "
              "advertising control writes to live campaigns.")

    if a.part == "assemble":
        return part_assemble(a)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed:  pip install playwright")
        return 2

    os.makedirs(SHOTS, exist_ok=True)
    todo = list(PARTS) if a.part == "all" else [a.part]

    with sync_playwright() as pw:
        browser = attach(pw, a.cdp)
        if not browser:
            return 2
        for name in todo:
            print("\n" + "=" * 70)
            print("PART: %s" % name)
            print("=" * 70 + "\n")
            page = new_page(browser, a.width)
            net = Net(page)
            doc = Doc(os.path.join(OUTDIR, "%s.md" % name))
            try:
                ok = PARTS[name](page, net, doc, a)
            except Exception as e:
                doc()
                doc("**This part stopped early: %s**" % str(e)[:300])
                ok = True
                print("part %s raised: %s" % (name, str(e)[:300]))
            doc.save()
            try:
                page.close()
            except Exception:
                pass
            if ok is False:
                print("\nStopped: not signed in. Sign in to Orbit in the debug "
                      "Chrome window, then re-run.")
                return 3

    if a.part == "all":
        part_assemble(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
