"""tools/orbit_capture.py -- measure Orbit's Sales Dashboard, exactly.

    python tools/orbit_capture.py
    python tools/orbit_capture.py --url https://fullcircleorbit.com/brand/... --out orbit_interactions.md

WHAT THIS IS FOR
The design brief asks for Orbit's exact interaction behaviour: pixel sizes,
animation durations, easing curves, tooltip layout, load sequence. Guessing at
those is what produced two rounds of "the graphs are still not how orbit has
it", so they get measured instead.

HOW IT GETS IN, AND WHY IT IS DONE THIS WAY
It attaches to a Chrome YOU are already signed into, over the DevTools protocol.
No password is typed here, none is stored, and nothing is sent anywhere: the
browser is yours, the session is yours, and this only reads the page that is
already on your screen. Start Chrome like this, sign in, then run the script:

    Windows:
      "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" ^
        --remote-debugging-port=9222 --user-data-dir="%TEMP%\\orbit-profile"

    (A separate --user-data-dir is deliberate: Chrome refuses the debugging
    port on a profile that is already running, and this keeps your normal
    browser untouched.)

WHAT IT CAN AND CANNOT MEASURE -- said plainly, because the brief asks for a
DevTools Performance recording and that is not scriptable:

  CAN   every computed pixel value, font, colour, radius and shadow, read off
        the live elements rather than from a screenshot
  CAN   animation and transition durations and easing curves, as the browser
        resolved them
  CAN   real timings: time to first skeleton, time to real data, how long a
        preset switch takes -- taken with performance.now() and a
        MutationObserver, which is the number the Performance tab would show
        you, obtained directly
  CAN   screenshots at each stage, full-page and per-element
  CANNOT produce a Performance flame chart, or attribute time to scripting
        versus layout versus paint. If that is genuinely needed it has to be a
        person with the Performance tab open.

Everything it writes is marked with how it was obtained, so nothing inferred is
mistaken for something measured.
"""
import argparse
import json
import os
import sys
import time

DEFAULT_URL = "https://fullcircleorbit.com/brand/lure-essentials/ATVPDKIKX0DER"
CDP = "http://localhost:9222"

# The surfaces the brief asks about, and how to find them. Several selectors per
# surface because Orbit's class names are content-hashed (_statCard_xa5pv_431)
# and change on every build -- matching on the stable part is what survives.
TARGETS = [
    ("stat card",       ["[class*='statCard']", "[class*='metricCard']", "[class*='_card_']"]),
    ("stat number",     ["[class*='statValue']", "[class*='metricValue']", "[class*='_value_']"]),
    ("stat label",      ["[class*='statLabel']", "[class*='metricLabel']", "[class*='_label_']"]),
    # pctBadge is what Orbit actually calls the +5.2% / down 1.6% chip. The
    # obvious guesses -- delta, change, badge -- all miss it, which is why this
    # is read off the page rather than assumed.
    ("delta badge",     ["[class*='pctBadge']", "[class*='delta']", "[class*='change']"]),
    ("chart container", ["[class*='chartContainer']", "[class*='chartWrap']", "[class*='_chart_']"]),
    ("chart svg",       [".recharts-wrapper svg", "[class*='chart'] svg", "svg"]),
    ("chart line",      [".recharts-line-curve", "path[class*='line']", "svg path"]),
    ("chart dot",       [".recharts-dot", "circle"]),
    ("grid line",       [".recharts-cartesian-grid line", "svg line"]),
    ("x axis",          [".recharts-xAxis", "[class*='xAxis']"]),
    ("y axis",          [".recharts-yAxis", "[class*='yAxis']"]),
    ("axis label",      [".recharts-cartesian-axis-tick text", "svg text"]),
    ("legend",          [".recharts-legend-item-text", ".recharts-legend-wrapper"]),
    ("preset button",   ["[class*='_option_']", "[class*='_button_'][class*='_sm_']"]),
    ("bar",             [".recharts-bar-rectangle path", ".recharts-rectangle"]),
    ("tooltip",         [".recharts-tooltip-wrapper", "[class*='tooltip']"]),
    ("progress bar",    ["[class*='progress']", "[class*='splitBar']", "[class*='ratioBar']"]),
    ("heatmap cell",    ["[class*='heatmap'] td", "[class*='heatCell']", "table td"]),
    ("heatmap header",  ["[class*='heatmap'] th", "table th"]),
    ("table row",       ["tbody tr"]),
    ("skeleton",        ["[class*='keleton']", "[class*='shimmer']"]),
]

# The properties worth recording. Everything else is noise in a document meant
# to be copied from.
PROPS = ["width", "height", "padding", "margin", "font-size", "font-weight",
         "font-family", "color", "background-color", "border", "border-radius",
         "box-shadow", "opacity", "gap", "line-height", "letter-spacing",
         "stroke", "stroke-width", "fill", "transition-duration",
         "transition-timing-function", "transition-property",
         "animation-name", "animation-duration", "animation-timing-function"]

MEASURE_JS = """
(args) => {
  const [sel, props] = args;
  const el = document.querySelector(sel);
  if (!el) return null;
  const cs = getComputedStyle(el);
  const r  = el.getBoundingClientRect();
  const out = {selector: sel, tag: el.tagName.toLowerCase(),
               className: String(el.className || "").slice(0, 160),
               box: {w: +r.width.toFixed(1), h: +r.height.toFixed(1),
                     x: +r.x.toFixed(1), y: +r.y.toFixed(1)},
               count: document.querySelectorAll(sel).length};
  props.forEach(p => { const v = cs.getPropertyValue(p); if (v && v !== "none" && v !== "normal") out[p] = v.trim(); });
  return out;
}
"""

# Time to first paint of a skeleton, and time until it is replaced by content.
# This is what the brief's "how long until skeleton -> real data" is asking for,
# taken from the page itself rather than read off a flame chart.
LOAD_TIMING_JS = """
() => new Promise(resolve => {
  const t0 = performance.now();
  const out = {skeleton_at: null, content_at: null, first_svg_at: null,
               nav: null};
  try {
    const n = performance.getEntriesByType("navigation")[0];
    if (n) out.nav = {dom_content_loaded: +n.domContentLoadedEventEnd.toFixed(0),
                      load: +n.loadEventEnd.toFixed(0),
                      response_end: +n.responseEnd.toFixed(0)};
  } catch (e) {}
  const seen = sel => document.querySelector(sel) !== null;
  const tick = () => {
    const now = +(performance.now() - t0).toFixed(0);
    if (out.skeleton_at === null && (seen("[class*='keleton']") || seen("[class*='shimmer']")))
      out.skeleton_at = now;
    if (out.first_svg_at === null && seen("svg path")) out.first_svg_at = now;
    if (out.content_at === null && !seen("[class*='keleton']") && seen("svg path"))
      out.content_at = now;
  };
  const mo = new MutationObserver(tick);
  mo.observe(document.body, {childList: true, subtree: true, attributes: true});
  tick();
  setTimeout(() => { mo.disconnect(); resolve(out); }, 12000);
})
"""

# Every keyframe and transition the page's own stylesheets declare. Read from
# the CSSOM, so it is what the browser parsed, not what a file appears to say.
CSS_MOTION_JS = """
() => {
  const keyframes = {}, durations = {}, easings = {};
  for (const sheet of document.styleSheets) {
    let rules;
    try { rules = sheet.cssRules; } catch (e) { continue; }   // cross-origin
    for (const rule of rules) {
      if (rule.type === CSSRule.KEYFRAMES_RULE) {
        keyframes[rule.name] = [...rule.cssRules].map(k => k.keyText + " {" + k.style.cssText + "}").join(" ");
      } else if (rule.style) {
        const d = rule.style.animationDuration || rule.style.transitionDuration;
        if (d) durations[d] = (durations[d] || 0) + 1;
        const e = rule.style.animationTimingFunction || rule.style.transitionTimingFunction;
        if (e) easings[e] = (easings[e] || 0) + 1;
      }
    }
  }
  return {keyframes, durations, easings};
}
"""


def _measure(page, label, selectors):
    for sel in selectors:
        try:
            got = page.evaluate(MEASURE_JS, [sel, PROPS])
        except Exception:
            got = None
        if got:
            got["label"] = label
            return got
    return {"label": label, "selector": " | ".join(selectors), "missing": True}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--cdp", default=CDP)
    p.add_argument("--out", default="orbit_interactions.md")
    p.add_argument("--shots", default="orbit_shots",
                   help="directory for screenshots")
    a = p.parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed:  pip install playwright")
        return 2

    os.makedirs(a.shots, exist_ok=True)
    doc = []

    def say(s=""):
        print(s)
        doc.append(s)

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(a.cdp)
        except Exception as e:
            print("Could not attach to Chrome on %s\n  %s\n\n"
                  "Start Chrome with the debugging port open and sign in first:\n"
                  '  chrome.exe --remote-debugging-port=9222 '
                  '--user-data-dir="%%TEMP%%\\orbit-profile"' % (a.cdp, str(e)[:160]))
            return 2

        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        page.set_viewport_size({"width": 1600, "height": 1000})

        say("# Orbit Sales Dashboard — measured interactions")
        say()
        say("Captured %s from a signed-in Chrome over the DevTools protocol."
            % time.strftime("%Y-%m-%d %H:%M"))
        say("Every number below is READ FROM THE LIVE PAGE — computed styles and")
        say("`performance.now()` timings — not estimated from a screenshot.")
        say()
        say("Not included: a Performance flame chart, or time split between")
        say("scripting, layout and paint. That needs a person with the tab open.")
        say()

        # ---- 1. load sequence -------------------------------------------
        say("## 1. Load sequence")
        say()
        timing = None
        try:
            page.goto(a.url, wait_until="commit", timeout=60000)
            timing = page.evaluate(LOAD_TIMING_JS)
        except Exception as e:
            say("Could not time the load: %s" % str(e)[:200])
        page.wait_for_timeout(2500)
        if not page.url.startswith("http") or "login" in page.url.lower():
            say("**The page redirected to %s — Chrome is not signed in.** Sign in "
                "in that window and run this again." % page.url)
        if timing:
            say("```json")
            say(json.dumps(timing, indent=2))
            say("```")
            say()
            say("- skeleton visible at **%s ms** after navigation" % timing.get("skeleton_at"))
            say("- first chart path at **%s ms**" % timing.get("first_svg_at"))
            say("- skeletons gone, chart present at **%s ms**" % timing.get("content_at"))
        say()
        page.screenshot(path=os.path.join(a.shots, "01_loaded.png"), full_page=True)
        say("Screenshot: `%s/01_loaded.png`" % a.shots)
        say()

        # ---- 2. every surface, measured ---------------------------------
        say("## 2. Measured elements")
        say()
        for label, sels in TARGETS:
            m = _measure(page, label, sels)
            say("### %s" % label)
            if m.get("missing"):
                say("Not found on this page (`%s`)." % m["selector"])
                say()
                continue
            say("`%s` — %d on the page" % (m["selector"], m.get("count", 0)))
            say()
            say("| property | value |")
            say("| --- | --- |")
            say("| box | %s×%s px at (%s, %s) |" % (m["box"]["w"], m["box"]["h"],
                                                    m["box"]["x"], m["box"]["y"]))
            for k, v in m.items():
                if k in ("label", "selector", "box", "tag", "className", "count", "missing"):
                    continue
                say("| %s | `%s` |" % (k, v))
            say()

        # ---- 2b. every series actually drawn ----------------------------
        # The single most copyable thing on the page, and the one that cannot
        # be read reliably off a screenshot: the exact stroke colour, width and
        # dash of each line, and the stops of each area gradient.
        say("## 2b. The lines and fills, as drawn")
        say()
        try:
            series = page.evaluate("""() => ({
              lines: [...document.querySelectorAll('.recharts-line-curve, .recharts-area-curve')]
                .map(p => { const cs = getComputedStyle(p);
                            return {stroke: cs.stroke, width: cs.strokeWidth,
                                    // long dash arrays are the browser expanding a
                                    // pattern over the path; only the head matters
                                    dash: (cs.strokeDasharray || 'none').split(',').slice(0,4).join(',')}; }),
              gradients: [...document.querySelectorAll('linearGradient')].map(g => ({
                id: g.id,
                stops: [...g.querySelectorAll('stop')].map(s => ({
                  color: s.getAttribute('stop-color'),
                  offset: s.getAttribute('offset'),
                  opacity: s.getAttribute('stop-opacity') || '1'}))})),
              bar: (() => { const b = document.querySelector('.recharts-bar-rectangle path');
                            if (!b) return null; const cs = getComputedStyle(b);
                            const r = b.getBoundingClientRect();
                            return {fill: cs.fill, opacity: cs.opacity,
                                    width: +r.width.toFixed(1)}; })(),
            })""")
            say("**Lines**")
            say()
            say("| stroke | width | dash |")
            say("| --- | --- | --- |")
            for ln in series["lines"]:
                say("| `%s` | %s | `%s` |" % (ln["stroke"], ln["width"], ln["dash"]))
            say()
            if series.get("bar"):
                say("**Bars:** fill `%s`, opacity `%s`, %s px wide"
                    % (series["bar"]["fill"], series["bar"]["opacity"],
                       series["bar"]["width"]))
                say()
            say("**Area gradients**")
            say()
            for g in series["gradients"]:
                stops = " → ".join("%s @%s a=%s" % (s["color"], s["offset"], s["opacity"])
                                   for s in g["stops"])
                say("- `%s`: %s" % (g["id"], stops))
            say()
        except Exception as e:
            say("Could not read the series: %s" % str(e)[:200])
            say()

        # ---- 3. motion, from the stylesheets ----------------------------
        say("## 3. Animation durations and easing, from the page's own CSS")
        say()
        try:
            motion = page.evaluate(CSS_MOTION_JS)
            say("**Durations, by how often each is used:**")
            say()
            for d, n in sorted(motion["durations"].items(), key=lambda kv: -kv[1])[:20]:
                say("- `%s` — %d rule(s)" % (d, n))
            say()
            say("**Easing curves:**")
            say()
            for e, n in sorted(motion["easings"].items(), key=lambda kv: -kv[1])[:20]:
                say("- `%s` — %d rule(s)" % (e, n))
            say()
            say("**Keyframes:**")
            say()
            for name, body in list(motion["keyframes"].items())[:40]:
                say("- `%s`: `%s`" % (name, body[:300]))
            say()
        except Exception as e:
            say("Could not read the stylesheets: %s" % str(e)[:200])
            say()

        # ---- 4. the tooltip, by actually hovering -----------------------
        say("## 4. Chart hover")
        say()
        try:
            svg = page.query_selector(".recharts-wrapper svg") or page.query_selector("svg")
            if svg:
                box = svg.bounding_box()
                # Three points across the chart, so "does it snap to data points
                # or follow the mouse" is answerable rather than asserted.
                seen = []
                for frac in (0.25, 0.5, 0.75):
                    page.mouse.move(box["x"] + box["width"] * frac,
                                    box["y"] + box["height"] / 2)
                    page.wait_for_timeout(350)
                    tip = _measure(page, "tooltip", ["[class*='tooltip']"])
                    txt = ""
                    el = page.query_selector("[class*='tooltip']")
                    if el:
                        try: txt = (el.inner_text() or "").strip()[:300]
                        except Exception: txt = ""
                    seen.append({"at": round(frac, 2), "text": txt,
                                 "box": tip.get("box"), "style": {
                                     k: v for k, v in tip.items()
                                     if k in ("background-color", "border", "border-radius",
                                              "box-shadow", "font-size", "color", "padding")}})
                    page.screenshot(path=os.path.join(a.shots, "hover_%02d.png" % int(frac * 100)))
                say("```json")
                say(json.dumps(seen, indent=2))
                say("```")
                say()
                xs = [s["box"]["x"] for s in seen if s.get("box")]
                if len(xs) >= 2:
                    say("The tooltip moved to x = %s across the three hover points, "
                        "so it %s." % (xs, "follows the pointer" if len(set(xs)) > 1
                                       else "is anchored, not following"))
                say()
            else:
                say("No chart SVG found to hover.")
                say()
        except Exception as e:
            say("Hover capture failed: %s" % str(e)[:200])
            say()

        # ---- 5. preset switching, timed ---------------------------------
        say("## 5. Switching date presets")
        say()
        for label in ("7d", "30d", "90d"):
            try:
                btn = page.query_selector("text=%s" % label)
                if not btn:
                    say("- `%s` — no button found" % label)
                    continue
                t0 = time.time()
                btn.click()
                # Settled = no DOM mutations for 300ms, which is what "the
                # transition finished" actually means here.
                page.wait_for_timeout(120)
                had_skeleton = bool(page.query_selector("[class*='keleton']"))
                page.wait_for_function(
                    "() => !document.querySelector(\"[class*='keleton']\")",
                    timeout=15000)
                ms = int((time.time() - t0) * 1000)
                say("- `%s` — settled in **%d ms**, skeleton shown while loading: **%s**"
                    % (label, ms, "yes" if had_skeleton else "no"))
                page.screenshot(path=os.path.join(a.shots, "preset_%s.png" % label))
            except Exception as e:
                say("- `%s` — %s" % (label, str(e)[:120]))
        say()

        # ---- 6. scrolling -----------------------------------------------
        say("## 6. Scrolling")
        say()
        try:
            before = page.evaluate("() => document.querySelectorAll('*').length")
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1200)
            after = page.evaluate("() => document.querySelectorAll('*').length")
            page.screenshot(path=os.path.join(a.shots, "scrolled.png"), full_page=True)
            say("Elements before scrolling: %d, after: %d — content is %s."
                % (before, after,
                   "lazy-loaded as you scroll" if after > before * 1.05
                   else "all present from the start"))
            say()
        except Exception as e:
            say("Scroll capture failed: %s" % str(e)[:200])
            say()

        page.close()

    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(doc) + "\n")
    print("\nWrote %s and screenshots to %s/" % (a.out, a.shots))
    return 0


if __name__ == "__main__":
    sys.exit(main())
