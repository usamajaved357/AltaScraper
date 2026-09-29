"""tools/browser_dispatch_check.py -- the Dispatch-to-Amazon flow, in a real browser.

    py -3.11 tools/browser_dispatch_check.py [--shots DIR]

Drives the Orders panel in headless Chromium, desktop (1440x900) and phone
(390x844), and checks, with screenshots:

  preview           Preview shows what Amazon would be told, sends nothing
  switched off      no Send button, the reason is shown; a forced confirm is 409
  switched on       Send appears; the question names what is sent; "Don't send"
                    sends nothing; "Send to Amazon" sends ONCE, exactly as previewed
  changed boxes     editing tracking after the preview refuses to send
  refused           Amazon's words shown; the button is usable again
  not known         "not known -- check Seller Central"; the button stays off
  one per order     a second send for the same order is refused
  keyboard          Tab reaches Preview; Enter previews; Escape cancels the
                    question and focus returns; Tab stays inside the dialog
  layout            nothing wider than the screen, desktop and phone

AMAZON IS NEVER CONTACTED:
  * the data is a temporary copy of the credential-free sandbox (tools/browser_smoke)
  * the two Amazon calls (api/amazon_orders_ship) are replaced IN THIS PROCESS
    by fakes that record each call; the real functions are never reached
  * the order list and order detail come from the browser-side fixtures below
    (the real ones would ask Amazon), everything else is the real app
  * the browser may talk to this local server only; every other request aborts
Exit 0 when every check passed.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import browser_smoke as bs                     # noqa: E402  (sandbox copy + server)

results = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    print("  %-66s %s%s" % (label, "OK" if ok else "FAIL", ("  " + detail) if (detail and not ok) else ""))


def main(argv):
    shots = argv[argv.index("--shots") + 1] if "--shots" in argv else os.path.join(ROOT, "active", "shots-dispatch")
    os.makedirs(shots, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="dispatch_")
    bs._copy_sandbox(tmp)
    os.chdir(tmp)

    # ---- the Amazon calls, faked in-process (never the real ones) ----------
    from api import amazon_orders_ship as AOS
    from domain import accounts as ACC
    from sp_api.base import SellingApiException
    calls = []
    mode = {"v": "ok"}

    def fake_items(creds, enum, oid):
        calls.append(("items", oid))
        return [{"OrderItemId": "OI-1", "QuantityOrdered": 1, "QuantityShipped": 0}]

    def fake_confirm(creds, enum, oid, body):
        calls.append(("confirm", oid, body))
        if mode["v"] == "refuse":
            raise SellingApiException([{"code": "InvalidInput", "message": "carrierName is not valid"}], headers={})
        if mode["v"] == "timeout":
            raise TimeoutError("read timed out")
        return 204

    AOS.order_items, AOS.confirm_shipment = fake_items, fake_confirm
    ACC.can_publish = lambda acc: True
    ACC.account_creds = lambda acc: {"refresh_token": "fake-browser-check-not-a-token"}
    # NO AMAZON CLIENT CAN BE BUILT in this process (security review, 29 Sep
    # 2026): every account is let publish above, so any server call this check
    # does not fake would otherwise be free to try the network. It fails loudly.
    from sp_api.base import Client as _SpClient

    def _no_amazon(self, *a, **k):
        raise RuntimeError("browser_dispatch_check: an Amazon client was built -- blocked")

    _SpClient.__init__ = _no_amazon
    srv, base = bs._serve(tmp)
    cfgp = os.environ["CONFIG_PATH"]

    from domain.jsonstore import write_json_atomic

    def switch(on):
        # The TEMPORARY copy's settings, through the app's one safe writer.
        with open(cfgp, encoding="utf-8") as f:
            d = json.load(f)
        d["ship_confirm_enabled"] = bool(on)
        write_json_atomic(cfgp, d)

    switch(False)
    sent = lambda: [c for c in calls if c[0] == "confirm"]          # noqa: E731

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for vw, vh, tag in ((1440, 900, "desktop"), (390, 844, "phone")):
            print("\n== %s %dx%d ==" % (tag, vw, vh))
            ctx = browser.new_context(viewport={"width": vw, "height": vh})
            state = {"acct": ""}

            def order(oid):
                return {"order_id": oid, "account_id": state["acct"], "account_label": "Test A",
                        "marketplace": "UK", "status": "Unshipped", "fulfilment": "MFN",
                        "unshipped": 1, "shipped": 0, "ship_by": "2099-01-01T12:00:00Z",
                        "purchased": "2026-09-29T10:00:00Z", "total": 19.99, "currency": "GBP",
                        "item": {"title": "Test garden hose", "sku": "ZZ-DISPATCH-1", "asin": "B0ZZTEST01", "qty": 1},
                        "tracking": [], "tracking_status": {}, "purchases": []}

            oids = ["DISPATCH-%s-%d" % (tag, n) for n in range(1, 5)]

            def route(r):
                u = r.request.url
                if not u.startswith(base):
                    return r.abort()
                path = u[len(base):]
                if path.startswith("/orders/list"):
                    return r.fulfill(json={"ok": True, "rows": [order(o) for o in oids], "days": 7,
                                           "accounts_asked": [state["acct"]], "errors": [],
                                           "summary": {}, "profit_note": "", "pii_note": ""})
                if path.startswith("/orders/items"):
                    return r.fulfill(json={"ok": True, "items": {}})
                if path.startswith("/orders/detail"):
                    oid = path.split("order_id=")[1].split("&")[0]
                    o = order(oid)
                    from domain import tracking as TR
                    o["tracking"] = (TR.for_orders(cfgp, state["acct"], "UK", [oid]).get(oid) or [])
                    return r.fulfill(json={"ok": True, "order_id": oid, "order": o,
                                           "items": [{"sku": "ZZ-DISPATCH-1", "title": "Test garden hose",
                                                      "qty": 1, "asin": "B0ZZTEST01", "price": 19.99, "currency": "GBP"}],
                                           "breakdown": {"totals": {"revenue": 19.99, "fees": 3.0, "cogs": None,
                                                                    "profit": None, "cogs_complete": False},
                                                         "lines": [{"sku": "ZZ-DISPATCH-1", "qty": 1}]},
                                           "sources": {}, "pii_note": ""})
                return r.continue_()

            ctx.route("**/*", route)
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)[:200]))
            page.goto(base + "/")
            page.wait_for_load_state("networkidle")
            state["acct"] = page.evaluate("() => (typeof ACTIVE_WS !== 'undefined' && ACTIVE_WS) ? String(ACTIVE_WS.key || '') : ''")
            check("[%s] an account is open (%s)" % (tag, state["acct"]), bool(state["acct"]))
            page.evaluate("() => navTo('orders')")
            page.wait_for_selector("tr.ordrow", timeout=10000)

            def open_order(oid):
                page.evaluate("([o, a]) => { ORD.open = ''; ORD.details = {}; ordersToggle(o, a); }",
                              [oid, state["acct"]])
                page.wait_for_selector("#ordtrk_num", timeout=10000)

            def fill(num, car="Royal Mail"):
                page.fill("#ordtrk_num", num)
                page.fill("#ordtrk_car", car)

            def preview_btn():
                return page.locator("button", has_text="Preview dispatch to Amazon")

            # ---- 1. preview, switched OFF ---------------------------------
            switch(False)
            open_order(oids[0])
            check("[%s] the order panel offers 'Preview dispatch to Amazon'" % tag, preview_btn().count() == 1)
            fill("RM123456789GB")
            n0 = len(calls)
            if tag == "desktop":
                # KEYBOARD: from the carrier box, Tab reaches the Preview button, Enter presses it.
                page.focus("#ordtrk_car")
                for _ in range(4):
                    page.keyboard.press("Tab")
                    if page.evaluate("() => (document.activeElement.textContent || '').includes('Preview dispatch')"):
                        break
                check("[keyboard] Tab reaches the Preview button",
                      page.evaluate("() => (document.activeElement.textContent || '').includes('Preview dispatch')"))
                page.keyboard.press("Enter")
            else:
                preview_btn().click()
            page.wait_for_function("() => /Amazon would be told|Not ready/.test((document.getElementById('ordship_out')||{}).textContent||'')", timeout=10000)
            out = page.inner_text("#ordship_out")
            check("[%s] preview says what Amazon would be told" % tag,
                  "Amazon would be told" in out and "RM123456789GB" in out, out[:160])
            check("[%s]   with a date a person reads (not ISO)" % tag,
                  "UTC" in out and "T0" not in out.split("tracking")[0], out[:160])
            check("[%s] switched off: the reason is shown" % tag, "switched off" in out, out[:160])
            check("[%s] switched off: NO Send button" % tag,
                  page.locator("#ordship_out button", has_text="Send to Amazon").count() == 0)
            check("[%s] preview sent nothing to Amazon" % tag,
                  [c[0] for c in calls[n0:]] == ["items"], str([c[0] for c in calls[n0:]]))
            page.screenshot(path=os.path.join(shots, "%s_1_preview_off.png" % tag))
            forced = page.evaluate("""([o, a]) => fetch('/orders/ship/confirm', {method: 'POST',
                  headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({account: a, marketplace: 'UK', order_id: o,
                                        tracking_number: 'RM123456789GB', carrier: 'Royal Mail'})})
                  .then(r => r.status)""", [oids[0], state["acct"]])
            check("[%s] a forced send while off is refused (409) and reaches nothing" % tag,
                  forced == 409 and not sent(), "status %s" % forced)

            # ---- 2. switched ON: the question, "Don't send", then Send -------
            switch(True)
            preview_btn().click()
            page.wait_for_selector("#ordship_out button:has-text('Send to Amazon')", timeout=10000)
            check("[%s] switched on: a Send button appears" % tag, True)
            page.screenshot(path=os.path.join(shots, "%s_2_preview_on.png" % tag))
            page.click("#ordship_out button:has-text('Send to Amazon')")
            page.wait_for_selector(".uidlg", timeout=5000)
            q = page.inner_text(".uidlg")
            check("[%s] the question names the tracking being sent" % tag, "RM123456789GB" in q, q[:200])
            check("[%s] its buttons say what they do" % tag,
                  "Send to Amazon" in q and "Don't send" in q, q[:200])
            page.screenshot(path=os.path.join(shots, "%s_3_confirm_dialog.png" % tag))
            if tag == "desktop":
                # KEYBOARD in the dialog: Tab stays inside; Escape cancels and focus returns.
                inside = True
                for _ in range(4):
                    page.keyboard.press("Tab")
                    inside = inside and page.evaluate("() => !!document.activeElement.closest('.uidlg')")
                check("[keyboard] Tab stays inside the question", inside)
                page.keyboard.press("Escape")
                page.wait_for_selector(".uidlg", state="detached", timeout=3000)
                check("[keyboard] Escape cancels: nothing sent", not sent())
                check("[keyboard]   and focus returns to the Send button",
                      page.evaluate("() => (document.activeElement.textContent || '').includes('Send to Amazon')"))
            else:
                page.click(".uidlg button:has-text(\"Don't send\")")
                page.wait_for_selector(".uidlg", state="detached", timeout=3000)
                check("[%s] 'Don't send' sends nothing" % tag, not sent())
            # changed boxes after the preview -> refused
            page.fill("#ordtrk_num", "RM999999999GB")
            page.click("#ordship_out button:has-text('Send to Amazon')")
            page.wait_for_timeout(400)
            check("[%s] tracking edited after the preview -> not sent, and said why" % tag,
                  not sent() and "changed since the preview" in page.inner_text("#ordship_out"))
            # the real send, as previewed
            fill("RM123456789GB")
            preview_btn().click()
            page.wait_for_selector("#ordship_out button:has-text('Send to Amazon')", timeout=10000)
            page.click("#ordship_out button:has-text('Send to Amazon')")
            page.wait_for_selector(".uidlg", timeout=5000)
            page.click(".uidlg button:has-text('Send to Amazon')")
            page.wait_for_function("() => !document.querySelector('.uidlg')", timeout=5000)
            page.wait_for_timeout(1200)
            s = sent()
            check("[%s] Send to Amazon: exactly ONE confirmation" % tag, len(s) == 1, str(len(s)))
            check("[%s]   carrying what was previewed" % tag,
                  bool(s) and s[0][2]["packageDetail"]["trackingNumber"] == "RM123456789GB"
                  and s[0][2]["packageDetail"]["carrierCode"] == "Other")
            page.screenshot(path=os.path.join(shots, "%s_4_sent.png" % tag))
            # one per order
            open_order(oids[0])
            fill("RM123456789GB")
            preview_btn().click()
            page.wait_for_function("() => /already told Amazon|Not ready/.test((document.getElementById('ordship_out')||{}).textContent||'')", timeout=10000)
            check("[%s] the same order again: refused, 'already told Amazon'" % tag,
                  "already told Amazon" in page.inner_text("#ordship_out") and len(sent()) == 1)

            # ---- 3. refused by Amazon ---------------------------------------
            mode["v"] = "refuse"
            open_order(oids[1])
            fill("RM222222222GB")
            preview_btn().click()
            page.wait_for_selector("#ordship_out button:has-text('Send to Amazon')", timeout=10000)
            btn = page.locator("#ordship_out button:has-text('Send to Amazon')")
            btn.click()
            page.click(".uidlg button:has-text('Send to Amazon')")
            page.wait_for_timeout(1200)
            toast = page.evaluate("() => Array.from(document.querySelectorAll('.toast, #toast, [class*=toast]')).map(e => e.textContent).join(' | ')")
            check("[%s] refused: Amazon's own words are shown" % tag, "carrierName is not valid" in toast, toast[:200])
            check("[%s]   and the button can be used again" % tag,
                  page.locator("#ordship_out button:has-text('Send to Amazon')").count() == 0
                  or not btn.is_disabled())
            page.screenshot(path=os.path.join(shots, "%s_5_refused.png" % tag))

            # ---- 4. result not known -----------------------------------------
            mode["v"] = "timeout"
            open_order(oids[2])
            fill("RM333333333GB")
            preview_btn().click()
            page.wait_for_selector("#ordship_out button:has-text('Send to Amazon')", timeout=10000)
            btn = page.locator("#ordship_out button:has-text('Send to Amazon')")
            btn.click()
            page.click(".uidlg button:has-text('Send to Amazon')")
            page.wait_for_timeout(1200)
            toast = page.evaluate("() => Array.from(document.querySelectorAll('.toast, #toast, [class*=toast]')).map(e => e.textContent).join(' | ')")
            check("[%s] not known: says so, and to check Seller Central" % tag,
                  "not known" in toast and "Seller Central" in toast, toast[:200])
            check("[%s]   without calling it 'not sent' (it may have been)" % tag,
                  "Not sent" not in toast, toast[:200])
            check("[%s]   and the Send button stays OFF" % tag, btn.count() == 1 and btn.is_disabled())
            page.screenshot(path=os.path.join(shots, "%s_6_not_known.png" % tag))
            mode["v"] = "ok"

            # ---- 5. layout ---------------------------------------------------
            wide = page.evaluate("""() => { const W = document.documentElement.clientWidth;
                const out = []; document.querySelectorAll('#ordship_out, #ordtrk_num, #ordtrk_car, .odp-note button')
                .forEach(e => { const r = e.getBoundingClientRect(); if (r.width && r.right > W + 2) out.push((e.id || e.tagName) + ' +' + Math.round(r.right - W)); });
                return out; }""")
            check("[%s] nothing in the dispatch box runs past the screen edge" % tag, not wide, str(wide))
            # The whole page, not just the box: an over-wide top bar made the page
            # scroll sideways under its clipped overflow when an order opened.
            side = page.evaluate("() => [window.scrollX, document.documentElement.scrollLeft, document.body.scrollLeft, "
                                 "document.body.scrollWidth - document.documentElement.clientWidth]")
            check("[%s] the page is not pushed sideways (scroll and overflow 0)" % tag,
                  all(v <= 1 for v in side), str(side))
            check("[%s] no JavaScript errors" % tag, not errs, "; ".join(errs[:3]))
            calls.clear()
            ctx.close()
        browser.close()
    switch(False)
    srv.shutdown()
    bad = [r for r in results if not r[1]]
    print("\n%d checks, %d failed. Screenshots: %s" % (len(results), len(bad), shots))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
