"""Research an ASIN, hand it to the Studio, and make an A+ module from it.

    "also the aplus content workflow through asin research tool works good"

Three separate pieces that each work alone. This drives the JOIN between them in
a real browser, because a handoff is exactly where two working things fail.
"""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5055"
ASIN = "B00L87YFL4"
FAIL = []


def ck(label, ok, extra=""):
    print("  %-54s %s%s" % (label, "OK" if ok else "FAIL",
                            ("  " + str(extra)) if extra else ""))
    if not ok:
        FAIL.append(label)


with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1500, "height": 950})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:170]))
    pg.goto(BASE + "/", wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(4500)

    print("== the research tool opens and looks up a real ASIN ==")
    ok = pg.evaluate("() => { if (typeof asinOpen==='function'){ asinOpen(); return true; } return false; }")
    ck("Research ASIN opens", ok)
    pg.wait_for_timeout(1200)
    # Drive the real controls -- #asin_input / #asin_mkt / asinLookup() -- rather
    # than guessing at selectors. The first run of this test guessed and reported
    # seven failures that were all its own.
    pg.evaluate("""(a) => {
        const i = document.getElementById('asin_input');
        if (i) i.value = a;
        const m = document.getElementById('asin_mkt');
        if (m) m.value = 'UK';
    }""", ASIN)
    pg.evaluate("() => { if (typeof asinLookup === 'function') asinLookup(); }")
    pg.wait_for_timeout(15000)

    got = pg.evaluate("""() => {
        const t = document.body.innerText;
        return { hasTitle: /LEGION|Triumph|Multivitamin/i.test(t),
                 hasStudioBtn: !!([...document.querySelectorAll('button')]
                    .find(x => /Image Studio/i.test(x.innerText))) };
    }""")
    ck("  it returned the product", got["hasTitle"])
    ck("  and offers the Image Studio", got["hasStudioBtn"])

    print("\n== the handoff carries the FACTS, not just the pictures ==")
    pg.evaluate("""() => {
        const b = [...document.querySelectorAll('button')]
          .find(x => /Image Studio/i.test(x.innerText));
        if (b) b.click();
    }""")
    pg.wait_for_timeout(4000)
    st = pg.evaluate("""() => {
        if (typeof STUDIO === 'undefined' || !STUDIO || !STUDIO.items) return null;
        const it = STUDIO.items[0] || {};
        return { sku: it.sku || '', title: (it.title||'').slice(0,40),
                 imgs: (it.images||[]).length,
                 attrs: Object.keys(it.attributes||{}).length,
                 ptype: it.product_type || '' };
    }""")
    ck("the studio received the product", st is not None)
    if st:
        ck("  with its images", st["imgs"] > 0, "%d" % st["imgs"])
        # THE POINT OF THIS TEST. Without the attributes an A+ module is a
        # layout with nothing true to put in it.
        ck("  and its specs", st["attrs"] > 0, "%d attributes" % st["attrs"])
        ck("  and its product type", bool(st["ptype"]), st["ptype"])

    print("\n== an A+ module generates from it ==")
    pg.evaluate("() => { if (typeof studioTab==='function') studioTab('aplus'); }")
    pg.wait_for_timeout(3500)
    mods = pg.evaluate("() => document.querySelectorAll('.apmodchk').length")
    ck("the module list loaded", mods > 0, "%d modules" % mods)
    pres = pg.evaluate("() => document.querySelectorAll('.appres').length")
    ck("  each offers a product-presence choice", pres > 0, "%d" % pres)

    print("\n== no javascript errors through the whole hand-off ==")
    real = [e for e in errs if "favicon" not in e.lower()]
    ck("nothing threw", not real, real[:3])
    b.close()

print("\n%d failed" % len(FAIL))
for f in FAIL:
    print("  -", f)
raise SystemExit(1 if FAIL else 0)
