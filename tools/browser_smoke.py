"""tools/browser_smoke.py -- open every screen in a real browser, on fake data.

    py -3.11 tools/browser_smoke.py                 all screens, both accounts
    py -3.11 tools/browser_smoke.py --shots DIR     also save a screenshot of each
    py -3.11 tools/browser_smoke.py --only sales,traffic

WHAT IT PROVES, AND WHAT IT DOES NOT. It loads the real dashboard in headless
Chromium, opens each screen in account A, switches to account B and opens them
again, and records: JavaScript errors, console errors, any reply of 500+, and
whether anything that belongs only to account A is on screen in account B. It
does not judge how a screen looks; screenshots are for a person to look at.

SAFETY, IN THIS ORDER:
  * The data is a TEMPORARY COPY of the credential-free sandox data set
    (claude-environment-devdata\\sandbox): two fake accounts with no keys, so
    nothing here can reach Amazon, Google, eBay or an AI provider.
  * It refuses to start unless the app's own resolver puts the database inside
    that temporary copy.
  * The browser may talk to this server only; every other request is aborted.
  * The server binds 127.0.0.1 on a port of its own, in this process, and
    writes no .app_port. Nothing is left running when it exits.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SANDBOX = os.path.join(os.path.dirname(ROOT), "claude-environment-devdata", "sandbox")

SCREENS = ("listings sales traffic hourly orders returns finance inventory weekly "
           "daily sourcing catalog categories compliance leading sqp kwspy kwasin "
           "kwhistory ranktracker trackers alerts monitor ppc ppcanalytics ppcterms "
           "ppccampaigns ppclive drppc drppcconsole asinstudio imagelib imagerefs "
           "imagestudio uploads variations sellerimport reimbursements brief "
           "aiusage notify permissions setup sync miles").split()

# Requests that name no account ON PURPOSE, each checked against its route
# (28 Sep 2026): none reads the server's open account. Anything else a tab asks
# for without naming its account is answered for whichever tab switched last,
# and fails the run.
GLOBAL_OK = {
    "/accounts/list": "the account list itself (filtered by who may see it)",
    "/users/list": "the user list",
    "/brand/list": "brands across accounts",
    "/sync/capabilities": "one row per visible account",
    "/monitor/overview": "the ASIN monitor is app-wide",
    "/monitor/alerts": "the ASIN monitor is app-wide",
    "/monitor/schedule": "the ASIN monitor is app-wide",
    "/notify/log": "the notification log is app-wide",
    "/preview/jobs": "filtered per job by who may see its account",
    "/miles/run_tail": "Miles runs belong to the Miles feature, not the open account",
    "/miles/results": "Miles feature",
    "/miles/sheet_pref": "Miles feature",
}

# Requests the page makes to the outside world (fonts, icons from a CDN) are
# refused on purpose, so their failures are expected and not the app's.
_EXPECTED = ("net::ERR_FAILED", "ERR_BLOCKED", "Failed to load resource: net::")


def _copy_sandbox(dst):
    """config.json byte for byte (never read or printed here), and the database
    through SQLite's own backup so a live WAL is copied consistently."""
    shutil.copyfile(os.path.join(SANDBOX, "config.json"), os.path.join(dst, "config.json"))
    src_db = os.path.join(SANDBOX, "altascraper.db")
    if os.path.exists(src_db):
        src = sqlite3.connect("file:%s?mode=ro" % src_db.replace("\\", "/"), uri=True)
        out = sqlite3.connect(os.path.join(dst, "altascraper.db"))
        src.backup(out)
        out.close()
        src.close()


# Data that exists in ONE account only, so a screen showing it under the other
# account is a leak that needs no knowledge of the sandbox to spot.
MARK = {"A": ("ZZ-ONLY-A-MARKER", "B0ZZONLYA1"), "B": ("ZZ-ONLY-B-MARKER", "B0ZZONLYB1")}


def _seed_markers(dbp, ids):
    """Fake orders, daily sales and ad rows for each account, in the TEMPORARY
    copy only. Each account's rows carry its own marker title and ASIN."""
    import datetime
    con = sqlite3.connect(dbp)
    today = datetime.date.today()
    now = datetime.datetime.utcnow().isoformat() + "Z"
    for tag, wsid in ids.items():
        title, asin = MARK[tag]
        for d in range(1, 21):
            day = today - datetime.timedelta(days=d)
            ins = [
                ("order_lines", dict(workspace_id=wsid, marketplace="UK",
                    order_id="ZZ-%s-%02d" % (tag, d), purchase_date=day.isoformat() + "T10:00:00Z",
                    asin=asin, sku="ZZ-%s-SKU" % tag, title=title, units=1, revenue=19.99,
                    currency="GBP", status="Shipped", fetched_at=now)),
                ("sales_daily", dict(workspace_id=wsid, marketplace="UK", date=day.isoformat(),
                    asin=asin, parent_asin=asin, units=1, orders=1, ordered_sales=19.99,
                    sessions=40, page_views=55, currency="GBP", fetched_at=now)),
                ("ads_daily", dict(workspace_id=wsid, marketplace="UK", date=day.isoformat(),
                    asin=asin, impressions=900, clicks=12, spend=3.5, ad_orders=1,
                    ad_sales=19.99, source="seed", fetched_at=now)),
            ]
            # One row per match type, so Campaign Analytics has a match-type
            # split to draw (its ring, table and spend-per-day chart).
            for n, mt in enumerate(("EXACT", "PHRASE", "BROAD", "TARGETING_EXPRESSION",
                                    "TARGETING_EXPRESSION_PREDEFINED")):
                ins.append(("ads_targeting_daily", dict(workspace_id=wsid, marketplace="UK",
                    date=day.isoformat(), campaign_id="ZZ-%s-C%d" % (tag, n),
                    campaign_name="ZZ %s %s" % (tag, mt), keyword=title, match_type=mt,
                    impressions=300, clicks=4 + n, spend=round(0.6 + 0.4 * n + (d % 5) * 0.2, 2),
                    ad_orders=1, ad_sales=6.5, source="seed", fetched_at=now)))
            for table, row in ins:
                try:
                    cols = {r[1] for r in con.execute("pragma table_info(%s)" % table)}
                    row = {k: v for k, v in row.items() if k in cols}
                    con.execute("insert into %s (%s) values (%s)" % (
                        table, ",".join(row), ",".join("?" * len(row))), list(row.values()))
                except Exception:
                    pass
    # THE SAME SKU IN BOTH ACCOUNTS gets each account's own marker as its
    # title, so the product page for that SKU can be checked across a switch.
    try:
        for tag, wsid in ids.items():
            con.execute("update listings set title=? where workspace_id=? and sku in "
                        "(select sku from listings group by sku having count(distinct workspace_id) > 1)",
                        (MARK[tag][0], wsid))
    except Exception:
        pass
    con.commit()
    con.close()


def _marks_on(page, tag):
    """Which of `tag`'s markers are VISIBLE on the page now -- each with the id
    of the nearest element that holds it, so a leak says WHERE it is drawn."""
    try:
        text = page.inner_text("body")
    except Exception:
        return []
    out = []
    for m in MARK[tag]:
        if m in text:
            try:
                where = page.evaluate("""m => {
                    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    let n; while ((n = w.nextNode())) {
                      if (n.nodeValue.indexOf(m) >= 0) {
                        let e = n.parentElement;
                        while (e && !e.id) e = e.parentElement;
                        return e ? '#' + e.id : '?';
                      }
                    } return '?'; }""", m)
            except Exception:
                where = "?"
            out.append("%s in %s" % (m, where))
    return out


def _serve(tmp):
    os.environ["CONFIG_PATH"] = os.path.join(tmp, "config.json")
    for k in ("PORT", "APP_PASSWORD", "ALTASCRAPER_DB"):
        os.environ.pop(k, None)
    sys.path.insert(0, ROOT)
    from data.db import db_path
    dbp = os.path.abspath(db_path())
    if not dbp.lower().startswith(os.path.abspath(tmp).lower()):
        raise SystemExit("STOP: the database would be %s, not the temporary copy" % dbp)
    if dbp.lower().startswith("d:\\altascraper\\"):
        raise SystemExit("STOP: that is the original checkout")
    import dashboard
    app = dashboard.build_app()
    from werkzeug.serving import make_server
    srv = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.db_path = dbp
    return srv, "http://127.0.0.1:%d" % srv.server_port


# ACCESSIBILITY BASICS, counted on what is VISIBLE on a screen: a control a
# screen reader cannot name, a picture with no text, a field with no label.
# A measurement to fix against, not a pass/fail.
_A11Y_JS = """() => {
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const name = e => (e.getAttribute('aria-label') || e.getAttribute('title') ||
                     e.getAttribute('aria-labelledby') || e.textContent || '').trim();
  const out = {unnamed_buttons: 0, images_no_alt: 0, fields_no_label: 0, examples: []};
  document.querySelectorAll('button, [role=button], a[onclick]').forEach(e => {
    if (vis(e) && !name(e)) { out.unnamed_buttons++;
      if (out.examples.length < 3) out.examples.push(e.outerHTML.slice(0, 120)); }
  });
  document.querySelectorAll('img').forEach(e => { if (vis(e) && !e.hasAttribute('alt')) out.images_no_alt++; });
  document.querySelectorAll('input:not([type=hidden]), select, textarea').forEach(e => {
    if (!vis(e)) return;
    const lab = (e.id && document.querySelector('label[for="' + CSS.escape(e.id) + '"]')) ||
                e.closest('label') || e.getAttribute('aria-label') || e.getAttribute('title') ||
                e.getAttribute('placeholder');
    if (!lab) { out.fields_no_label++;
      if (out.examples.length < 12) out.examples.push(e.outerHTML.slice(0, 160)); }
  });
  return out;
}"""


def _visit(page, sec, log, shots, tag):
    page.evaluate("s => { try { navTo(s); } catch (e) { console.error('navTo threw: ' + e); } }", sec)
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        log["slow"].append("%s:%s" % (tag, sec))
    page.wait_for_timeout(400)
    if tag == "A" and "a11y" in log:
        try:
            r = page.evaluate(_A11Y_JS)
            if r["unnamed_buttons"] or r["images_no_alt"] or r["fields_no_label"]:
                log["a11y"][sec] = r
        except Exception:
            pass
    if shots:
        page.screenshot(path=os.path.join(shots, "%s_%s.png" % (tag, sec)), full_page=False)


def main(argv):
    shots = argv[argv.index("--shots") + 1] if "--shots" in argv else ""
    only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
    # Viewport, for the design system's test widths (390/768/1024/1366/1920).
    vw = int(argv[argv.index("--width") + 1]) if "--width" in argv else 1440
    vh = int(argv[argv.index("--height") + 1]) if "--height" in argv else 900
    screens = [s for s in SCREENS if not only or s in only]
    if shots:
        os.makedirs(shots, exist_ok=True)
    if not os.path.exists(os.path.join(SANDBOX, "config.json")):
        print("STOP: no sandbox data set at " + SANDBOX)
        return 2

    tmp = tempfile.mkdtemp(prefix="smoke_")
    cwd = os.getcwd()
    try:
        _copy_sandbox(tmp)
        os.chdir(tmp)      # anything written relative to the cwd lands in the copy
        srv, base = _serve(tmp)
        log = {"page_errors": [], "console_errors": [], "server_5xx": [], "client_4xx": {},
               "slow": [], "leaks": [], "screens": len(screens), "a11y": {}}
        cur = {"where": "boot"}
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": vw, "height": vh})
            ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base)
                      else r.abort())
            page = ctx.new_page()
            page.on("pageerror", lambda e: log["page_errors"].append(
                "%s: %s" % (cur["where"], str(e).splitlines()[0][:300])))
            page.on("console", lambda m: (m.type == "error" and not any(
                x in m.text for x in _EXPECTED) and "status of 4" not in m.text)
                and log["console_errors"].append(
                "%s: %s" % (cur["where"], m.text[:300])))
            page.on("response", lambda r: r.status >= 500 and r.url.startswith(base)
                    and log["server_5xx"].append("%s: %d %s" % (
                        cur["where"], r.status, r.url[len(base):][:160])))

            def _4xx(r):
                # A refusal is often the RIGHT answer (these accounts have no
                # Amazon connection), so it is recorded with its reason and
                # judged by a person, not counted as a failure.
                if 400 <= r.status < 500 and r.url.startswith(base):
                    path = r.url[len(base):].split("?")[0]
                    try:
                        why = (r.json() or {}).get("error", "")
                    except Exception:
                        why = ""
                    log["client_4xx"].setdefault("%d %s" % (r.status, path), str(why)[:200])
            page.on("response", _4xx)

            # HOW LONG EACH SERVER CALL TOOK, measured by the browser. On fake
            # data this is the app's own overhead, not Amazon's -- a baseline to
            # compare against, not a verdict.
            timings = {}

            def _time(req):
                if not req.url.startswith(base) or "/static/" in req.url:
                    return
                try:
                    ms = req.timing.get("responseEnd", -1)
                except Exception:
                    ms = -1
                if ms and ms > 0:
                    key = req.method + " " + req.url[len(base):].split("?")[0]
                    timings.setdefault(key, []).append(ms)
            page.on("requestfinished", _time)
            page.goto(base + "/", wait_until="networkidle")
            ids = page.evaluate("() => (ACCOUNTS || []).map(a => a.id)")
            if len(ids) < 2:
                print("STOP: the sandbox needs two accounts, found %d" % len(ids))
                return 2
            a, b = ids[0], ids[1]
            _seed_markers(srv.db_path, {"A": a, "B": b})
            log["marker_seen_in_own_account"] = []
            log["marker_leaks"] = []
            for acct, tag in ((a, "A"), (b, "B")):
                other = "B" if tag == "A" else "A"
                cur["where"] = "enter " + tag
                page.evaluate("id => enterAccount(id)", acct)
                page.wait_for_load_state("networkidle")
                for sec in screens:
                    cur["where"] = "%s:%s" % (tag, sec)
                    _visit(page, sec, log, shots, tag)
                    if _marks_on(page, tag):
                        log["marker_seen_in_own_account"].append(cur["where"])
                    for m in _marks_on(page, other):
                        log["marker_leaks"].append("%s shows %s" % (cur["where"], m))

            # SWITCH WHILE LOADING. Open each screen in A and switch to B at
            # once, before A's replies land: a late reply painted over B is the
            # bug class screenstate.js exists for.
            for sec in screens:
                cur["where"] = "fast A->B:%s" % sec
                page.evaluate("id => enterAccount(id)", a)
                page.evaluate("s => { try { navTo(s); } catch (e) {} }", sec)
                page.evaluate("id => enterAccount(id)", b)
                page.evaluate("s => { try { navTo(s); } catch (e) {} }", sec)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    log["slow"].append(cur["where"])
                page.wait_for_timeout(600)
                for m in _marks_on(page, "A"):
                    log["marker_leaks"].append("%s shows %s" % (cur["where"], m))
            # A LEAK CHECK THAT NEEDS NO KNOWLEDGE OF THE DATA: the SKUs the
            # server says belong to A and not to B must not be on B's listings.
            cur["where"] = "leak check"
            only_a = page.evaluate("""async ([a, b]) => {
                const g = async id => ((await (await fetch('/rows_all?account=' +
                    encodeURIComponent(id))).json()).rows || []).map(r => String(r.sku || ''));
                const sa = await g(a), sb = new Set(await g(b));
                return sa.filter(s => s && !sb.has(s));
            }""", [a, b])
            page.evaluate("s => navTo(s)", "listings")
            page.wait_for_timeout(1500)
            shown = page.inner_text("body")
            log["leaks"] = [s for s in only_a if s in shown]
            log["only_a_skus_checked"] = len(only_a)

            # THE PRODUCT PAGE, for a SKU both accounts have: opened in A, then
            # in B -- normally, and before A's page has finished loading.
            shared = page.evaluate("""async ([a, b]) => {
                const g = async id => ((await (await fetch('/rows_all?account=' +
                    encodeURIComponent(id))).json()).rows || []).map(r => String(r.sku || ''));
                const sb = new Set(await g(b));
                return (await g(a)).filter(s => s && sb.has(s))[0] || '';
            }""", [a, b])
            log["pdp_shared_sku"] = shared
            if shared:
                for mode in ("settled", "fast"):
                    cur["where"] = "pdp %s A" % mode
                    page.evaluate("id => enterAccount(id)", a)
                    page.wait_for_load_state("networkidle")
                    # From Listings, as a person opens it: the PDP reads the
                    # listing rows, which another screen has not loaded.
                    page.evaluate("() => navTo('listings')")
                    page.wait_for_load_state("networkidle")
                    page.evaluate("s => pdpOpen(s)", shared)
                    if mode == "settled":
                        page.wait_for_load_state("networkidle")
                        page.wait_for_timeout(600)
                        # KEYBOARD (design system, accessibility): focus starts
                        # on "Back to listings", Tab never leaves the PDP, Esc
                        # closes it.
                        kb = {"role": page.evaluate("() => (document.getElementById('pdp')||{}).getAttribute && document.getElementById('pdp').getAttribute('role')"),
                              "focus_on_open": page.evaluate("() => !!(document.activeElement && document.activeElement.classList.contains('pdp-back'))")}
                        escaped = 0
                        for _ in range(40):
                            page.keyboard.press("Tab")
                            if not page.evaluate("() => { const h=document.getElementById('pdp'); return !!(h && h.contains(document.activeElement)); }"):
                                escaped += 1
                        kb["tab_left_pdp"] = escaped
                        # Tab OUT of an editable area inside the page moves on,
                        # it does not jump to "Back" (D3 review).
                        kb["contenteditable_tab_ok"] = page.evaluate("""() => {
                            const ce = document.querySelector('#pdp [contenteditable]:not([contenteditable="false"])');
                            if (!ce) return 'none';
                            ce.focus();
                            const ev = new KeyboardEvent('keydown', {key: 'Tab', bubbles: true, cancelable: true});
                            ce.dispatchEvent(ev);
                            return !ev.defaultPrevented; }""")
                        # A modal opened OVER the page keeps the keyboard.
                        page.evaluate("() => { try { openUsers(); } catch (e) {} }")
                        page.wait_for_timeout(300)
                        over = 0
                        for _ in range(12):
                            page.keyboard.press("Tab")
                            if not page.evaluate("() => { const m=document.getElementById('usersmodal'); return !!(m && m.contains(document.activeElement)); }"):
                                over += 1
                        kb["modal_over_pdp_left"] = over
                        page.evaluate("() => { try { closeUsers(); } catch (e) {} }")
                        page.wait_for_timeout(200)
                        log["pdp_keyboard"] = kb
                        if _marks_on(page, "A"):
                            log["marker_seen_in_own_account"].append(cur["where"])
                        for m in _marks_on(page, "B"):
                            log["marker_leaks"].append("%s shows %s" % (cur["where"], m))
                    cur["where"] = "pdp %s B" % mode
                    page.evaluate("id => enterAccount(id)", b)
                    if mode == "settled":
                        page.wait_for_load_state("networkidle")
                        page.evaluate("() => navTo('listings')")
                        page.wait_for_load_state("networkidle")
                    page.evaluate("s => pdpOpen(s)", shared)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        log["slow"].append(cur["where"])
                    page.wait_for_timeout(800)
                    if shots and mode == "settled":
                        page.screenshot(path=os.path.join(shots, "B_pdp.png"), full_page=False)
                    if _marks_on(page, "B"):
                        log["marker_seen_in_own_account"].append(cur["where"])
                    for m in _marks_on(page, "A"):
                        log["marker_leaks"].append("%s shows %s" % (cur["where"], m))
                    if mode == "settled":
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(300)
                        log.setdefault("pdp_keyboard", {})["esc_closes"] = page.evaluate(
                            "() => !document.body.classList.contains('pdp-on')")
                        # ENTER on "Back to listings" closes it too (D3 review).
                        page.evaluate("s => pdpOpen(s)", shared)
                        page.wait_for_timeout(500)
                        page.evaluate("() => { const b=document.querySelector('#pdp .pdp-back'); if(b) b.focus(); }")
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(300)
                        log["pdp_keyboard"]["enter_on_back_closes"] = page.evaluate(
                            "() => !document.body.classList.contains('pdp-on')")
                    page.evaluate("() => { try { pdpClose(); } catch (e) {} }")

            # THE OLDER MODALS (.modalwrap), via the Users dialog: named a
            # dialog, focus moves in, Tab stays in, focus returns on close.
            cur["where"] = "modal keyboard"
            try:
                page.evaluate("() => { const b=document.querySelector('.skiplink'); if(b) b.focus(); }")
                page.evaluate("() => { try { openUsers(); } catch (e) {} }")
                page.wait_for_timeout(400)
                mk = {"role": page.evaluate("() => { const m=document.querySelector('#usersmodal .modal')||document.getElementById('usersmodal'); return m && m.getAttribute('role'); }"),
                      "focus_inside": page.evaluate("() => { const m=document.getElementById('usersmodal'); return !!(m && m.contains(document.activeElement)); }")}
                left = 0
                for _ in range(25):
                    page.keyboard.press("Tab")
                    if not page.evaluate("() => { const m=document.getElementById('usersmodal'); return !!(m && m.contains(document.activeElement)); }"):
                        left += 1
                mk["tab_left_modal"] = left
                page.evaluate("() => { try { closeUsers(); } catch (e) {} }")
                page.wait_for_timeout(300)
                mk["focus_returned"] = page.evaluate("() => !!(document.activeElement && document.activeElement.classList.contains('skiplink'))")
                log["modal_keyboard"] = mk
            except Exception as _e:
                log["modal_keyboard"] = {"error": str(_e)[:200]}

            # THE BOTTOM-RIGHT CORNER. The assistant, the product chat and the
            # runs badge are each placed by a different file; each must be the
            # element actually hit at its own centre (not covered by another).
            cur["where"] = "floating corner"
            try:
                page.evaluate("() => { try { asBuild(); } catch (e) {} const r = rqBadgeEl && rqBadgeEl(); if (r) { window.__rqSaved = [r.innerHTML, r.style.display]; r.textContent = 'Runs'; r.style.display = 'inline-flex'; } }")
                page.wait_for_timeout(200)
                log["floating"] = page.evaluate("""() => {
                  const out = {covered: [], missing: []};
                  // Every corner and the centre, so a partial overlap fails too.
                  const check = (sel, when) => {
                    const e = document.querySelector(sel);
                    if (!e || !e.getClientRects().length) { out.missing.push(sel + when); return; }
                    const r = e.getBoundingClientRect();
                    for (const [fx, fy] of [[.5, .5], [.15, .2], [.85, .2], [.15, .8], [.85, .8]]) {
                      const hit = document.elementFromPoint(r.left + r.width * fx, r.top + r.height * fy);
                      if (!hit || !(hit === e || e.contains(hit))) {
                        out.covered.push(sel + when + ' under ' + (hit ? (hit.id || hit.className || hit.tagName) : 'nothing'));
                        return;
                      }
                    }
                  };
                  for (const sel of ['#asfab', '#fab', '#rqbadge']) check(sel, '');
                  // With the assistant panel open, the badge must still show.
                  const w = document.getElementById('aswrap');
                  if (w) { w.style.display = 'flex'; check('#rqbadge', ' (assistant open)'); w.style.display = 'none'; }
                  const r = document.getElementById('rqbadge');
                  if (r && window.__rqSaved) { r.innerHTML = window.__rqSaved[0]; r.style.display = window.__rqSaved[1]; }
                  return out; }""")
            except Exception as _e:
                log["floating"] = {"error": str(_e)[:200]}

            # ORDERS: THE ORDER BESIDE THE TABLE (owner decision, 28 Sep 2026).
            # /orders/list is a live Amazon call the sandbox cannot make, so the
            # two order routes are answered here with shaped rows, on this page
            # only, and removed afterwards. Checks: the panel opens beside the
            # table at >=1100px (inline below that), another row swaps it, the
            # keyboard reaches and keeps the row, and a switch closes it.
            cur["where"] = "orders side panel"
            try:
                def _ofake(route):
                    u = route.request.url
                    acc = u.split("account=")[1].split("&")[0] if "account=" in u else ""
                    tg = "A" if acc == a else "B"
                    if "/orders/list" in u:
                        route.fulfill(json={"ok": True, "summary": {"orders": 3}, "pii_note": "",
                            "rows": [{"order_id": "ZZ-%s-%d" % (tg, i), "account_id": acc,
                                      "account": tg, "status": "Unshipped", "currency": "GBP",
                                      "purchased": "2026-09-2%dT10:00:00Z" % i, "total": 9.99,
                                      "units": 1, "fulfilment": "MFN"} for i in (1, 2, 3)]})
                    else:
                        route.fulfill(json={"ok": True, "items": [], "orders": {}})
                page.route("**/orders/list*", _ofake)
                page.route("**/orders/detail*", _ofake)
                page.route("**/orders/items*", _ofake)   # else fake ids reach the server
                page.evaluate("id => enterAccount(id)", a)
                page.wait_for_load_state("networkidle")
                page.evaluate("() => { ORD.rows = []; ORD.rowsFor = '__reload__'; navTo('orders'); }")
                page.wait_for_timeout(1500)
                osd = {"rows": page.evaluate("() => document.querySelectorAll('tr.ordrow').length")}
                if osd["rows"]:
                    page.click("tr.ordrow >> nth=0")
                    page.wait_for_timeout(700)
                    wide = vw >= 1100
                    # Side panel exactly when the screen says there is room.
                    osd["panel_where_expected"] = page.evaluate(
                        "() => _ordSideMode() ? (!!document.querySelector('.ord-side') && !document.querySelector('tr.orddetail'))"
                        "       : (!document.querySelector('.ord-side') && !!document.querySelector('tr.orddetail'))")
                    osd["side_mode"] = page.evaluate("() => _ordSideMode()")
                    # And beside the panel the table never scrolls sideways.
                    osd["table_fits"] = page.evaluate(
                        "() => { const s = document.querySelector('.ord-main div[style*=overflow-x]');"
                        " return !s || s.scrollWidth <= s.clientWidth + 1; }")
                    osd["focus_kept"] = page.evaluate("() => !!(document.activeElement && document.activeElement.classList.contains('ordrow'))")
                    page.click("tr.ordrow >> nth=1")
                    page.wait_for_timeout(500)
                    osd["swaps"] = page.evaluate("() => ORD.open === document.querySelectorAll('tr.ordrow')[1].dataset.oid")
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(300)
                    osd["enter_closes"] = page.evaluate("() => ORD.open === ''")
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(300)
                    page.evaluate("id => enterAccount(id)", b)
                    page.wait_for_timeout(1200)
                    osd["switch_closes"] = page.evaluate("() => ORD.open === ''")
                    page.evaluate("id => enterAccount(id)", a)
                    page.wait_for_load_state("networkidle")
                log["orders_side"] = osd
            except Exception as _e:
                log["orders_side"] = {"error": str(_e)[:200]}
            finally:
                try:
                    page.unroute("**/orders/list*")
                    page.unroute("**/orders/detail*")
                    page.unroute("**/orders/items*")
                    # The fake rows must not be what later visits redraw.
                    page.evaluate("() => { ORD.rows = []; ORD.details = {}; ORD.open = ''; ORD.rowsFor = '__reload__'; }")
                except Exception:
                    pass

            # TWO TABS. The server keeps ONE "open account" for everybody, and
            # the last tab to switch owns it. Tab 1 goes back to A; tab 2 then
            # opens B. Everything tab 1 asks for afterwards must still be A's:
            # a request that does not NAME its account is answered for B.
            cur["where"] = "two tabs"
            page.evaluate("id => enterAccount(id)", a)
            page.wait_for_load_state("networkidle")
            tab2 = ctx.new_page()
            tab2.goto(base + "/", wait_until="networkidle")
            tab2.evaluate("id => enterAccount(id)", b)
            tab2.wait_for_load_state("networkidle")
            unnamed = {}

            def _unnamed(req):
                u = req.url
                if not u.startswith(base) or "/static/" in u:
                    return
                path, _, q = u[len(base):].partition("?")
                named = any(k + "=" in ("&" + q) for k in ("&account", "&account_id", "&id"))
                if not named and req.method == "POST":
                    try:
                        body = req.post_data_json or {}
                    except Exception:
                        body = {}
                    named = isinstance(body, dict) and any(
                        body.get(k) for k in ("account", "account_id", "id"))
                if not named:
                    unnamed.setdefault("%s %s" % (req.method, path), cur["where"])
            page.on("request", _unnamed)
            for sec in screens:
                cur["where"] = "tab1(A):%s" % sec
                _visit(page, sec, log, None, "T")
                for m in _marks_on(page, "B"):
                    log["marker_leaks"].append("%s shows %s" % (cur["where"], m))
            page.remove_listener("request", _unnamed)
            only_b = page.evaluate("""async ([a, b]) => {
                const g = async id => ((await (await fetch('/rows_all?account=' +
                    encodeURIComponent(id))).json()).rows || []).map(r => String(r.sku || ''));
                const sb = await g(b), sa = new Set(await g(a));
                return sb.filter(s => s && !sa.has(s));
            }""", [a, b])
            page.evaluate("s => navTo(s)", "listings")
            page.wait_for_timeout(1500)
            shown = page.inner_text("body")
            log["two_tab_leaks"] = [s for s in only_b if s in shown]
            # Unnamed and NOT known to be app-wide: a failure until judged.
            log["two_tab_unnamed_requests"] = {k: v for k, v in unnamed.items()
                                               if k.split(" ", 1)[1] not in GLOBAL_OK}
            browser.close()
        slow = sorted(((max(v), sorted(v)[len(v) // 2], k, len(v))
                       for k, v in timings.items()), reverse=True)
        log["slowest_ms"] = ["%6.0f ms max, %5.0f median  %s  (x%d)" % t for t in slow[:12]]
        srv.shutdown()
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps(log, indent=1))
    bad = (log["page_errors"] or log["console_errors"] or log["server_5xx"]
           or log["leaks"] or log.get("two_tab_leaks") or log.get("marker_leaks")
           or (log.get("pdp_keyboard") and (log["pdp_keyboard"].get("tab_left_pdp")
               or not log["pdp_keyboard"].get("focus_on_open")
               or log["pdp_keyboard"].get("esc_closes") is False
               or log["pdp_keyboard"].get("enter_on_back_closes") is False
               or log["pdp_keyboard"].get("contenteditable_tab_ok") is False
               or log["pdp_keyboard"].get("modal_over_pdp_left")))
           or (log.get("modal_keyboard") and (log["modal_keyboard"].get("tab_left_modal")
               or log["modal_keyboard"].get("role") != "dialog"
               or not log["modal_keyboard"].get("focus_inside")))
           or (log.get("orders_side") and (log["orders_side"].get("error")
               or (log["orders_side"].get("rows") and not all(log["orders_side"].get(k)
                   for k in ("panel_where_expected", "table_fits", "focus_kept", "swaps",
                             "enter_closes", "switch_closes")))))
           or (log.get("floating") and (log["floating"].get("covered")
               or log["floating"].get("missing") or log["floating"].get("error")))
           or log.get("two_tab_unnamed_requests"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
