"""Exercise every screen through the running app, the way a person would.

    "i want you to test each feature if it actually works ... make sure all the
     logics of the orbit are properly adopted by our app"

Unit tests prove the arithmetic. This proves the WIRING: that each screen loads,
draws something, calls the endpoint it is supposed to, and throws no JavaScript.
Those are different failures and only this catches the second kind -- a route
that works perfectly and a screen that never calls it look identical from a unit
test.

Run against a server on 5055 with a real account open:

    python tools/live_smoke.py
"""
import json
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5055"

# section, the element that must have content, and what "drawn" means for it.
SCREENS = [
    ("overview", "ovw_body", "business overview"),
    ("catalog", "catp_body", "product catalog"),
    ("categories", "cats_body", "category explorer"),
    ("drppc", "drp_body", "dr ppc"),
    ("imagelib", "imgp_picker", "image library page"),
    ("trackers", "trk_body", "trackers"),
    ("alerts", "alr_body", "alerts"),
    ("leading", "ld_body", "leading indicators"),
    ("notify", "ntf_body", "notifications"),
    ("compliance", "cmp_body", "compliance checker"),
    # SQP deliberately does not fetch on open -- Amazon builds the report on
    # request and rations it. But it must still SAY so: a screen that draws
    # nothing and explains nothing is indistinguishable from a broken one, and
    # this test is what found it drawing nothing at all.
    ("sqp", "sqp_body", "keywords (sqp)"),
    ("listings", "sec_listings", "listings"),
    ("inventory", "sec_inventory", "inventory"),
    ("orders", "sec_orders", "orders"),
    ("returns", "sec_returns", "returns"),
    ("daily", "dy_body", "daily round"),
    ("weekly", "wk_body", "weekly kpis"),
    ("sales", "sec_sales", "sales"),
    ("traffic", "sec_traffic", "traffic"),
    ("hourly", "sec_hourly", "hourly sales"),
    ("finance", "sec_finance", "finance"),
    ("variations", "sec_variations", "variations"),
    ("monitor", "sec_monitor", "asin monitor"),
    ("imagerefs", "imagerefsbody", "image refs"),
    ("imagestudio", "sec_imagestudio", "image studio"),
    ("ppc", "sec_ppc", "ppc"),
    ("sourcing", "sec_sourcing", "repricer"),
    ("aiusage", "sec_aiusage", "ai spend"),
    ("sync", "sec_sync", "compare with amazon"),
]

FAIL = []


def check(label, ok, extra=""):
    print("  %-46s %s%s" % (label, "OK" if ok else "FAIL",
                            ("  " + str(extra)) if extra else ""))
    if not ok:
        FAIL.append(label)


with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    requests = []
    pg.on("pageerror", lambda e: errors.append(("pageerror", str(e)[:160])))
    pg.on("console", lambda m: errors.append(("console", m.text[:160]))
          if m.type == "error" else None)
    pg.on("requestfailed",
          lambda r: requests.append(("failed", r.url[:110])))
    pg.on("response", lambda r: requests.append((r.status, r.url[:110]))
          if r.status >= 500 else None)

    pg.goto(BASE + "/", wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(5000)
    print("open at:", pg.url)
    print("account :", pg.evaluate(
        "() => (typeof CUR_ACCOUNT!=='undefined' && CUR_ACCOUNT) ? CUR_ACCOUNT.id : '(none)'"))
    print()

    print("== every screen draws ==")
    for sec, elid, name in SCREENS:
        before = len(errors)
        try:
            pg.evaluate("(s) => { if (typeof navTo === 'function') navTo(s); }", sec)
            pg.wait_for_timeout(3200)
            info = pg.evaluate("""
              (id) => {
                const el = document.getElementById(id);
                if (!el) return { missing: true };
                const t = (el.innerText || '').trim();
                return {
                  missing: false,
                  chars: t.length,
                  // A screen showing only a spinner has not finished.
                  loading: /^(loading|reading|asking)/i.test(t),
                  head: t.slice(0, 60).replace(/\\s+/g, ' ')
                };
              }
            """, elid)
        except Exception as e:
            check(name, False, str(e)[:70])
            continue
        new_errs = errors[before:]
        if info.get("missing"):
            check(name, False, "#%s not in the page" % elid)
        elif new_errs:
            check(name, False, "threw: %s" % new_errs[0][1][:60])
        elif info["chars"] < 8:
            check(name, False, "drew nothing")
        elif info["loading"]:
            check(name, False, "still loading after 3.2s")
        else:
            check(name, True, "%d chars" % info["chars"])

    print("\n== the new screens call their endpoints ==")
    # A route that works and a screen that never calls it look identical from a
    # unit test, so this watches the network.
    #
    # ON A FRESH PAGE EACH TIME, and that matters. The app deliberately does NOT
    # re-fetch a screen it has already drawn -- screenNeedsLoad() exists so that
    # going Sales -> Orders -> Sales does not make you wait for Sales twice. So
    # checking after the loop above proves nothing: every one of these would
    # report "endpoint never called" purely because it had already been called.
    # The first version of this test did exactly that and reported seven false
    # failures.
    for sec, want in (("overview", "/overview"),
                      ("catalog", "/catalog/products"),
                      ("trackers", "/trackers"),
                      ("alerts", "/trackers/alerts"),
                      ("leading", "/leading"),
                      ("notify", "/notify/channels"),
                      ("compliance", "/compliance/scans"),
                      ("categories", "/categories"),
                      # Checks the CONNECTION on open, never the reports --
                      # those are two Amazon report builds behind a button.
                      ("drppc", "/drppc/status"),
                      ("imagelib", "/catalog/products")):
        p2 = b.new_page(viewport={"width": 1280, "height": 800})
        seen = []
        p2.on("request", lambda r, s=seen: s.append(r.url))
        try:
            p2.goto(BASE + "/", wait_until="networkidle", timeout=60000)
            p2.wait_for_timeout(3500)
            p2.evaluate("(s) => { if (typeof navTo === 'function') navTo(s); }", sec)
            p2.wait_for_timeout(3000)
            hit = any(want in u for u in seen)
        except Exception as e:
            hit = False
            print("      (%s)" % str(e)[:70])
        check("%s -> %s" % (sec, want), hit,
              "" if hit else "endpoint never called")
        p2.close()

    print("\n== no server errors, no failed requests ==")
    bad = [r for r in requests if r[0] == "failed" or (isinstance(r[0], int) and r[0] >= 500)]
    check("nothing returned 5xx or failed", not bad, bad[:3])

    print("\n== no javascript errors anywhere ==")
    real = [e for e in errors if "favicon" not in e[1].lower()]
    check("the app threw nothing", not real, real[:3])

    b.close()

print("\n%d failed" % len(FAIL))
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
