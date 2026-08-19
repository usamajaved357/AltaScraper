"""Does the Image refs page actually do what was asked?

    "allow me to swich between images within the folder of the sku by the arrows
     as we have an option in the google drive and also write the name of the
     item first 4 words only and the asin of the item along with the main image
     of the item on the folder"

Driven through a real browser, because both halves are behaviour: whether a
folder header carries the product, and whether an arrow moves you to the next
picture without leaving the viewer.
"""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5055"
FAIL = []


def check(label, ok, extra=""):
    print("  %-58s %s%s" % (label, "OK" if ok else "FAIL", (" " + str(extra)) if extra else ""))
    if not ok:
        FAIL.append(label)


with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
    pg.on("console", lambda m: errs.append("console:" + m.text[:140]) if m.type == "error" else None)

    pg.goto(BASE + "/", wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(4000)
    pg.evaluate("() => navTo('imagerefs')")
    pg.wait_for_timeout(5000)

    print("== the folder says which product it is ==")
    n_folders = pg.evaluate("() => document.querySelectorAll('.mediafolder').length")
    check("there are SKU folders", n_folders > 0, "(%d)" % n_folders)
    if n_folders:
        info = pg.evaluate("""
          () => {
            const f = document.querySelector('.mediafolder');
            const s = f.querySelector('summary');
            return {
              hasPic: !!s.querySelector('.mfpic'),
              picIsImg: !!s.querySelector('img.mfpic'),
              name: (s.querySelector('.mfname') || {}).textContent || '',
              asin: (s.querySelector('.mfasin') || {}).textContent || '',
              sku:  (s.querySelector('.mfsku')  || {}).textContent || '',
              full: (s.querySelector('.mfname') || {}).title || ''
            };
          }
        """)
        check("  the folder shows a picture slot", info["hasPic"])
        check("  a real main image, not the placeholder", info["picIsImg"],
              "(placeholder shown -> catalogue has no image for this SKU)")
        check("  the SKU is still shown", bool(info["sku"]), repr(info["sku"][:30]))
        words = [w for w in info["name"].replace("…", "").split() if w]
        check("  the name is at most four words", len(words) <= 4,
              "(%d: %r)" % (len(words), info["name"][:40]))
        check("  a name is shown at all", bool(info["name"]), repr(info["name"][:40]))
        check("  the ASIN is shown", bool(info["asin"]), repr(info["asin"]))
        if info["full"]:
            check("  the full title is still available on hover", len(info["full"]) > 0)

    print("\n== arrows step through the folder ==")
    # Open the first folder with more than one picture.
    opened = pg.evaluate("""
      () => {
        const fs = [...document.querySelectorAll('.mediafolder')];
        for (const f of fs) {
          f.open = true;
          if (f.querySelectorAll('.mediacell img').length > 1) return true;
        }
        return false;
      }
    """)
    check("a folder with more than one image exists", opened)
    if opened:
        pg.wait_for_timeout(900)
        pg.evaluate("""
          () => {
            const f = [...document.querySelectorAll('.mediafolder')]
                       .find(x => x.querySelectorAll('.mediacell img').length > 1);
            f.querySelector('.mediacell img').click();
          }
        """)
        pg.wait_for_timeout(1200)
        st = pg.evaluate("""
          () => {
            const v = document.getElementById('ilpreview');
            if (!v) return null;
            return {
              hasPrev: !!v.querySelector('.ilprev'),
              hasNext: !!v.querySelector('.ilnext'),
              count: (v.querySelector('#ilpreviewcount') || {}).textContent || '',
              src: (v.querySelector('#ilpreviewimg') || {}).src || '',
              prevOff: !!(v.querySelector('.ilprev') || {}).classList?.contains('off')
            };
          }
        """)
        check("the viewer opened", st is not None)
        if st:
            check("  it has a previous arrow", st["hasPrev"])
            check("  and a next arrow", st["hasNext"])
            check("  and says where you are", "of" in st["count"], repr(st["count"]))
            first_src = st["src"]

            # Click next.
            pg.evaluate("() => document.querySelector('#ilpreview .ilnext').click()")
            pg.wait_for_timeout(700)
            after = pg.evaluate("""
              () => ({
                src: (document.getElementById('ilpreviewimg') || {}).src || '',
                count: (document.getElementById('ilpreviewcount') || {}).textContent || '',
                stillOpen: !!document.getElementById('ilpreview'),
                dl: (document.getElementById('ilpreviewdl') || {}).getAttribute
                    ? document.getElementById('ilpreviewdl').getAttribute('onclick') : ''
              })
            """)
            check("  the arrow changed the picture", after["src"] != first_src)
            check("  the viewer stayed open", after["stillOpen"])
            check("  the counter moved", after["count"] != st["count"],
                  "%r -> %r" % (st["count"], after["count"]))
            # The Download button must follow, or it saves the wrong file.
            fname = after["src"].split("/")[-1].split("?")[0]
            check("  Download now points at the CURRENT picture",
                  fname[:12] in (after["dl"] or ""), repr((after["dl"] or "")[:70]))

            # Keyboard.
            pg.keyboard.press("ArrowRight")
            pg.wait_for_timeout(700)
            kb = pg.evaluate("() => (document.getElementById('ilpreviewimg')||{}).src || ''")
            check("  the right arrow key works too", kb != after["src"])
            pg.keyboard.press("ArrowLeft")
            pg.wait_for_timeout(700)
            back = pg.evaluate("() => (document.getElementById('ilpreviewimg')||{}).src || ''")
            check("  and the left arrow goes back", back == after["src"])

            # It must STOP at the start, not wrap.
            for _ in range(30):
                pg.evaluate("() => { const p=document.querySelector('#ilpreview .ilprev'); if(p) p.click(); }")
            pg.wait_for_timeout(600)
            ends = pg.evaluate("""
              () => ({
                count: (document.getElementById('ilpreviewcount')||{}).textContent || '',
                prevOff: document.querySelector('#ilpreview .ilprev').classList.contains('off')
              })
            """)
            check("  it stops at the first picture rather than wrapping",
                  ends["count"].startswith("1 of"), repr(ends["count"]))
            check("  and the back arrow is dimmed there", ends["prevOff"])

            # Escape closes the viewer and nothing else.
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(500)
            check("  Escape closes it",
                  pg.evaluate("() => !document.getElementById('ilpreview')"))
            check("  and the library is still open",
                  pg.evaluate("() => !!document.getElementById('medialib')"))

    print("\n== no javascript errors ==")
    real = [e for e in errs if "favicon" not in e.lower()]
    check("the page threw nothing", not real, real[:3])

    b.close()

print("\n%d failed" % len(FAIL))
for f in FAIL:
    print("  -", f)
raise SystemExit(1 if FAIL else 0)
