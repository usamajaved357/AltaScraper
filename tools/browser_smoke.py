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
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
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
                    page.evaluate("s => pdpOpen(s)", shared)
                    if mode == "settled":
                        page.wait_for_load_state("networkidle")
                        page.wait_for_timeout(600)
                        if _marks_on(page, "A"):
                            log["marker_seen_in_own_account"].append(cur["where"])
                        for m in _marks_on(page, "B"):
                            log["marker_leaks"].append("%s shows %s" % (cur["where"], m))
                    cur["where"] = "pdp %s B" % mode
                    page.evaluate("id => enterAccount(id)", b)
                    if mode == "settled":
                        page.wait_for_load_state("networkidle")
                    page.evaluate("s => pdpOpen(s)", shared)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        log["slow"].append(cur["where"])
                    page.wait_for_timeout(800)
                    if _marks_on(page, "B"):
                        log["marker_seen_in_own_account"].append(cur["where"])
                    for m in _marks_on(page, "A"):
                        log["marker_leaks"].append("%s shows %s" % (cur["where"], m))
                    page.evaluate("() => { try { pdpClose(); } catch (e) {} }")

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
           or log.get("two_tab_unnamed_requests"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
