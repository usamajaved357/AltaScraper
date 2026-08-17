"""probe_sales_legend.py -- does clicking the chart key actually hide the line?

    python probe_sales_legend.py

WHY A BROWSER AND NOT A UNIT TEST
The thing asked for is a click. Asserting that the string 'scToggleSeries' is
present in the file proves the button exists, not that it works: the handler
could throw, the redraw could nest a second chart inside the first, or the
series could come back on the next redraw. All three are the actual failure
modes here, and only a real click finds them.

Attaches to the Chrome the owner already has open (tools/orbit_capture.py
explains why that and not a fresh browser -- the app is behind a login), opens
our own Sales page, and clicks.
"""
import json
import re
import sys
import time

CDP = "http://127.0.0.1:9222"
APP = "http://127.0.0.1:5000"


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = ctx.new_page()
        try:
            run(page)
        finally:
            page.close()


def run(page):
    page.goto(APP + "/", wait_until="domcontentloaded")
    time.sleep(1.5)

    # The app opens on the account chooser, and Sales means nothing until an
    # account is picked -- every figure on it belongs to one seller account.
    page.evaluate("() => { if (typeof enterAccount === 'function') enterAccount('jack_uk'); }")
    time.sleep(3.0)
    # Then the Sales screen. The nav is drawn by JS, so ask the app to navigate
    # rather than guessing at a URL.
    page.evaluate("() => { if (typeof navTo === 'function') navTo('sales'); }")
    time.sleep(2.0)
    # The combo chart is drawn from a fetch, so wait for it rather than sleeping
    # a fixed time and hoping.
    for _ in range(40):
        if page.query_selector("#sales_combo_svg"):
            break
        time.sleep(0.5)

    svg = page.query_selector("#sales_combo_svg")
    if not svg:
        print("NO CHART -- #sales_combo_svg never appeared.")
        print("   screen:", page.evaluate("() => document.title"))
        body = page.evaluate("() => (document.getElementById('sales_charts')||{}).innerText || ''")
        print("   sales_charts says:", (body or "")[:300])
        return

    def state():
        """What is on the chart right now, read from the DOM."""
        return page.evaluate("""() => {
          const wrap = document.getElementById('sales_combo_wrap');
          const svg  = document.getElementById('sales_combo_svg');
          if(!wrap || !svg) return null;
          return {
            wraps:  document.querySelectorAll('#sales_combo_wrap').length,
            svgs:   document.querySelectorAll('#sales_combo_svg').length,
            lines:  svg.querySelectorAll('path.series').length,
            bars:   svg.querySelectorAll('path.bar').length,
            keys:   Array.from(wrap.querySelectorAll('button.sc-key')).map(b => ({
                      text: b.innerText.trim(),
                      off:  b.classList.contains('off'),
                      pressed: b.getAttribute('aria-pressed'),
                    })),
            // The left money axis, so a rescale can be seen
            axis:   Array.from(svg.querySelectorAll('text'))
                      .filter(t => +t.getAttribute('text-anchor="end"'.slice(0,0) || 0) === 0)
                      .slice(0, 6).map(t => t.textContent.trim()),
          };
        }""")

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    before = state()
    print("=== the chart as drawn ===")
    print("  line paths: %d   bars: %d   key items: %d"
          % (before["lines"], before["bars"], len(before["keys"])))
    for k in before["keys"]:
        print("    %-22s off=%-5s aria-pressed=%s" % (k["text"], k["off"], k["pressed"]))

    if not before["keys"]:
        print("FAIL: the key has no buttons in it.")
        return

    # EVERY ITEM MUST START ON. "they are enabled by default" was explicit.
    on_at_start = [k["text"] for k in before["keys"] if not k["off"]]
    print("\n=== 1. everything starts switched on ===")
    ok = len(on_at_start) == len(before["keys"])
    print("  %s  %d of %d are on" % ("ok  " if ok else "FAIL",
                                     len(on_at_start), len(before["keys"])))

    # Click the LAST key item, so we are not testing the easy first one.
    target = before["keys"][-1]["text"]
    print("\n=== 2. clicking %r hides it ===" % target)
    page.click("#sales_combo_wrap button.sc-key:last-of-type")
    time.sleep(0.6)
    after = state()
    if not after:
        print("  FAIL  the chart disappeared after the click")
        return
    print("  line paths %d -> %d   bars %d -> %d"
          % (before["lines"], after["lines"], before["bars"], after["bars"]))
    hid = [k for k in after["keys"] if k["off"]]
    print("  now off: %s" % ([k["text"] for k in hid] or "nothing"))
    print("  %s  something was actually removed from the chart"
          % ("ok  " if (after["lines"] < before["lines"]
                        or after["bars"] < before["bars"]) else "FAIL"))
    print("  %s  the key item is marked off" % ("ok  " if hid else "FAIL"))
    print("  %s  it is still listed so it can be switched back on"
          % ("ok  " if len(after["keys"]) == len(before["keys"]) else "FAIL"))

    # THE BUG THIS IS REALLY LOOKING FOR: outerHTML replacement done wrong
    # nests a second chart inside the first, and everything still "works"
    # until the second click.
    print("\n=== 3. the redraw replaced the chart, not nested one inside it ===")
    print("  %s  #sales_combo_wrap count = %d (must be 1)"
          % ("ok  " if after["wraps"] == 1 else "FAIL", after["wraps"]))
    print("  %s  #sales_combo_svg  count = %d (must be 1)"
          % ("ok  " if after["svgs"] == 1 else "FAIL", after["svgs"]))

    print("\n=== 4. clicking it again brings it back ===")
    page.click("#sales_combo_wrap button.sc-key:last-of-type")
    time.sleep(0.6)
    back = state()
    print("  line paths %d   bars %d" % (back["lines"], back["bars"]))
    same = (back["lines"] == before["lines"] and back["bars"] == before["bars"])
    print("  %s  the chart is back to what it was" % ("ok  " if same else "FAIL"))
    print("  %s  nothing is marked off"
          % ("ok  " if not [k for k in back["keys"] if k["off"]] else "FAIL"))
    print("  %s  still exactly one chart (%d wraps)"
          % ("ok  " if back["wraps"] == 1 else "FAIL", back["wraps"]))

    # HIDE EVERYTHING. An empty plot must say it is empty because things are
    # hidden, not look like a period with no sales.
    print("\n=== 5. hiding everything says so ===")
    n = len(back["keys"])
    for i in range(n):
        page.click("#sales_combo_wrap button.sc-key >> nth=%d" % i)
        time.sleep(0.35)
    end = page.evaluate("""() => {
      const w = document.getElementById('sales_combo_wrap');
      return w ? {text: w.innerText, wraps: document.querySelectorAll('#sales_combo_wrap').length,
                  lines: document.querySelectorAll('#sales_combo_svg path.series').length,
                  bars: document.querySelectorAll('#sales_combo_svg path.bar').length} : null;
    }""")
    if end:
        said = "hidden" in (end["text"] or "").lower()
        print("  lines %d  bars %d  wraps %d" % (end["lines"], end["bars"], end["wraps"]))
        print("  %s  the screen explains the chart is empty because it is hidden"
              % ("ok  " if said else "FAIL"))
    else:
        print("  FAIL  the chart vanished entirely")

    # Put it back, so the owner's own screen is not left with everything hidden.
    for i in range(n):
        page.click("#sales_combo_wrap button.sc-key >> nth=%d" % i)
        time.sleep(0.3)

    print("\n=== 6. card size (asked: Orbit's cards are smaller than ours) ===")
    cards = page.evaluate("""() => Array.from(document.querySelectorAll('.statcard, .stat-card'))
        .slice(0, 8).map(c => ({
          h: Math.round(c.getBoundingClientRect().height),
          w: Math.round(c.getBoundingClientRect().width),
          text: (c.innerText || '').replace(/\\n/g, ' | ').slice(0, 70),
        }))""")
    if not cards:
        print("  no stat cards found on this screen")
    for c in cards:
        print("  %4dx%-4d  %s" % (c["w"], c["h"], c["text"]))
    if cards:
        tall = [c for c in cards if c["h"] > 130]
        print("  %s  Orbit's are 104px; ours are %s"
              % ("ok  " if not tall else "note",
                 sorted({c["h"] for c in cards})))

    print("\n=== javascript errors during all of that ===")
    print("  %s  %s" % ("ok  " if not errors else "FAIL", errors or "none"))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("probe could not run: %s: %s" % (type(exc).__name__, exc))
        sys.exit(1)
