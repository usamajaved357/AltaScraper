"""Content you CANNOT GET TO -- clipped, not merely scrolled.

    "i have seen the page cutting my visuals and getting out of the screen where
     i can not see the text or graphics"

Two different faults hide behind that sentence and they need different fixes:

  OVERFLOW   the page is wider than the window, so there is a horizontal
             scrollbar and the content is at least reachable.
  CLIPPED    an element is wider than an ancestor that has overflow:hidden, so
             the content is simply GONE. No scrollbar, no way to reach it. This
             is the one that loses text and graphics, and it is invisible to a
             page-width check because the page width is fine.

This looks for both, at several widths, on the real app with real data.
"""
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5055"
WIDTHS = [int(x) for x in (sys.argv[1:] or ["1920", "1440", "1280", "1100"])]

SECTIONS = ["listings", "trackers", "alerts", "leading", "notify", "sqp",
            "inventory", "orders", "returns", "daily", "weekly", "sales",
            "traffic", "hourly", "finance", "variations", "monitor",
            "imagestudio", "imagerefs", "ppc", "sourcing", "aiusage", "sync"]

PROBE = """
() => {
  const docW = document.documentElement.clientWidth;
  const out = { docW, scrollW: document.documentElement.scrollWidth,
                clipped: [], overflow: [] };
  const seen = new Set();
  document.querySelectorAll('body *').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    if (r.bottom < 0 || r.top > 20000) return;

    // --- CLIPPED: wider than an ancestor that hides the excess -------------
    let p = el.parentElement;
    while (p && p !== document.documentElement) {
      const pcs = getComputedStyle(p);
      const pr = p.getBoundingClientRect();
      const hidesX = (pcs.overflowX === 'hidden' || pcs.overflowX === 'clip');
      if (hidesX && pr.width > 2 && r.right > pr.right + 2) {
        const key = 'C' + el.tagName + (el.className || '') + (el.id || '');
        if (!seen.has(key)) {
          seen.add(key);
          out.clipped.push({
            tag: el.tagName, id: el.id || '',
            cls: String(el.className || '').slice(0, 46),
            lost: Math.round(r.right - pr.right),
            by: p.tagName + '.' + String(p.className || '').slice(0, 26),
            text: (el.textContent || '').trim().slice(0, 46)
          });
        }
        break;
      }
      p = p.parentElement;
    }

    // --- OVERFLOW: sticks past the window and nothing scrolls it ----------
    if (r.right > docW + 1) {
      let q = el.parentElement, scrollable = false;
      while (q && q !== document.body) {
        const qcs = getComputedStyle(q);
        if (qcs.overflowX === 'auto' || qcs.overflowX === 'scroll' ||
            qcs.overflowX === 'hidden' || qcs.overflowX === 'clip') {
          scrollable = true; break;
        }
        q = q.parentElement;
      }
      if (!scrollable && cs.position !== 'fixed') {
        const key = 'O' + el.tagName + (el.className || '') + (el.id || '');
        if (!seen.has(key)) {
          seen.add(key);
          out.overflow.push({
            tag: el.tagName, id: el.id || '',
            cls: String(el.className || '').slice(0, 46),
            over: Math.round(r.right - docW),
            text: (el.textContent || '').trim().slice(0, 46)
          });
        }
      }
    }
  });
  out.clipped.sort((a, b) => b.lost - a.lost);
  out.overflow.sort((a, b) => b.over - a.over);
  out.clipped = out.clipped.slice(0, 5);
  out.overflow = out.overflow.slice(0, 5);
  return out;
}
"""

with sync_playwright() as pw:
    b = pw.chromium.launch()
    for w in WIDTHS:
        pg = b.new_page(viewport={"width": w, "height": 900})
        pg.goto(BASE + "/", wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(5000)
        print("\n" + "=" * 78)
        print("VIEWPORT %dpx    (VIEWS=%s)" % (
            w, pg.evaluate("() => (typeof VIEWS!=='undefined') ? (VIEWS||[]).length : '?'")))
        print("=" * 78)
        for sec in SECTIONS:
            try:
                pg.evaluate("(s) => { if (typeof navTo === 'function') navTo(s); }", sec)
                pg.wait_for_timeout(2600)
                r = pg.evaluate(PROBE)
            except Exception as e:
                print("%-13s ERROR %s" % (sec, str(e)[:60]))
                continue
            page_over = r["scrollW"] - r["docW"]
            if not r["clipped"] and not r["overflow"] and page_over <= 1:
                continue
            print("%-13s page+%-5d clipped=%d overflow=%d"
                  % (sec, page_over, len(r["clipped"]), len(r["overflow"])))
            for c in r["clipped"]:
                print("    CLIPPED -%-4dpx %-5s #%-14s .%-26s by %-24s %r"
                      % (c["lost"], c["tag"], c["id"][:14], c["cls"][:26],
                         c["by"][:24], c["text"]))
            for o in r["overflow"]:
                print("    OVER    +%-4dpx %-5s #%-14s .%-26s %r"
                      % (o["over"], o["tag"], o["id"][:14], o["cls"][:26], o["text"]))
        pg.close()
    b.close()
