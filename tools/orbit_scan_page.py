"""tools/orbit_scan_page.py -- the WHOLE Sales page, element by element.

    python tools/orbit_scan_page.py --out orbit_sales_spec.md

WHY THIS RATHER THAN MORE MEASURING BY HAND
Matching a screen one detail at a time produces exactly what it sounds like:
the stat cards right, then the chart wrong, then the chart right and the
spacing wrong. Every round costs a look and a complaint. So this walks the
whole page once and writes down every element that carries visible weight --
its box, its type, its text, and the styling that decides how it reads -- in
reading order, as a specification to build from.

It attaches to a Chrome the owner is already signed into (see
tools/orbit_capture.py for why that and not a password), scrolls the page to
force anything lazy to render, and reports.

WHAT IT DELIBERATELY LEAVES OUT
Elements with no size, no text and no background: wrappers exist in their
hundreds and listing them buries the twenty things that matter.
"""
import argparse
import json
import os
import sys

DEFAULT_URL = "https://fullcircleorbit.com/brand/flux-footwear/ATVPDKIKX0DER"
CDP = "http://127.0.0.1:9222"

SCAN = r"""
() => {
  const out = {viewport: {w: innerWidth, h: innerHeight}, nodes: []};
  const PROPS = ["display","flex-direction","align-items","justify-content","gap",
                 "grid-template-columns","background-color","border","border-radius",
                 "padding","margin","font-size","font-weight","line-height","color",
                 "box-shadow","opacity","text-transform","letter-spacing",
                 "overflow","position"];
  const seen = new Set();
  const root = document.querySelector("[class*='_content_']") || document.body;

  const walk = (el, depth) => {
    if (depth > 14 || !el || seen.has(el)) return;
    seen.add(el);
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") return;
    const r = el.getBoundingClientRect();
    const own = [...el.childNodes]
      .filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(" ").trim();
    const paints = cs.backgroundColor !== "rgba(0, 0, 0, 0)" ||
                   cs.borderBottomWidth !== "0px" || cs.borderTopWidth !== "0px";
    const worth = (own && own.length < 120) || paints ||
                  el.tagName === "SVG" || el.tagName === "svg" ||
                  el.tagName === "BUTTON" || el.tagName === "SELECT" ||
                  el.tagName === "INPUT" || el.tagName === "TABLE";
    if (worth && r.width > 0 && r.height > 0) {
      const o = {depth, tag: el.tagName.toLowerCase(),
                 cls: String(el.className && el.className.baseVal !== undefined
                             ? el.className.baseVal : (el.className || "")).slice(0, 60),
                 text: own.slice(0, 90),
                 box: [ +r.width.toFixed(1), +r.height.toFixed(1),
                        +r.x.toFixed(1), +Math.round(r.y + scrollY) ]};
      PROPS.forEach(p => {
        const v = cs.getPropertyValue(p);
        if (v && v !== "none" && v !== "normal" && v !== "auto" &&
            v !== "0px" && v !== "rgba(0, 0, 0, 0)" && v !== "static")
          o[p] = v.trim();
      });
      out.nodes.push(o);
    }
    [...el.children].forEach(c => walk(c, depth + 1));
  };
  walk(root, 0);
  return out;
}
"""


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--cdp", default=CDP)
    p.add_argument("--out", default="orbit_sales_spec.md")
    p.add_argument("--width", type=int, default=1600)
    a = p.parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed")
        return 2

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(a.cdp)
        except Exception as e:
            print("Could not attach to Chrome on %s: %s\n\nStart it with "
                  "--remote-debugging-port=9222 and sign in." % (a.cdp, str(e)[:120]))
            return 2
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        page.set_viewport_size({"width": a.width, "height": 1000})
        page.goto(a.url, wait_until="commit", timeout=60000)
        # Wait for the data, not a fixed sleep: the charts arrive at ~8s.
        try:
            page.wait_for_function(
                "() => document.querySelectorAll('svg path').length > 20", timeout=45000)
        except Exception:
            pass
        page.wait_for_timeout(2000)
        # Scroll the whole way down so anything lazy renders, then back up.
        for _ in range(8):
            page.mouse.wheel(0, 900)
            page.wait_for_timeout(350)
        page.wait_for_timeout(1500)
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(800)

        data = page.evaluate(SCAN)
        page.screenshot(path="orbit_shots/full_page.png", full_page=True)
        page.close()

    nodes = data["nodes"]
    lines = ["# Orbit Sales page — the whole thing, measured", "",
             "Scanned at %dpx wide. Every element that carries visible weight, in "
             "reading order: its box as [w, h, x, y], its text, and the styling "
             "that decides how it reads." % data["viewport"]["w"], "",
             "Boxes are page pixels. `y` is from the top of the document, so the "
             "order below is the order down the screen.", "",
             "%d elements." % len(nodes), ""]
    # Reading order, then indented by depth so the structure is visible.
    for n in sorted(nodes, key=lambda x: (x["box"][3], x["box"][2])):
        head = "%s`%s`%s" % ("  " * min(n["depth"], 8), n["tag"],
                             ("." + n["cls"].split()[0]) if n["cls"] else "")
        lines.append("- %s — **%s×%s** at (%s, %s)"
                     % (head, n["box"][0], n["box"][1], n["box"][2], n["box"][3]))
        if n.get("text"):
            lines.append("    - text: `%s`" % n["text"])
        style = {k: v for k, v in n.items()
                 if k not in ("depth", "tag", "cls", "text", "box")}
        if style:
            lines.append("    - " + "; ".join("%s: `%s`" % (k, v)
                                              for k, v in sorted(style.items())))
    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("Wrote %s (%d elements) and orbit_shots/full_page.png"
          % (a.out, len(nodes)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
