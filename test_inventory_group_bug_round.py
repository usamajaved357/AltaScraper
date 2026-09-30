"""test_inventory_group_bug_round.py -- the 30 Sep 2026 bug round on the
Inventory, Returns, Reimbursements, Catalog, Categories, Compliance, Leading and
SQP screens.

Plain script, exits non-zero on failure. Each block fails on the code as it was
before the round:

  * the stock ledger put SAFE products first (sorted on the healthy->urgent
    index) -- urgent first now, unknown last
  * the sales-per-day window ran today-30..today: 31 days incl. a partial today
  * money_back swallowed every database error into "nothing owed"
  * the catalogue called unsynced products dead, and missed costs typed in a
    different case
  * a live listing's Catalog attributes (lists of dicts) were scanned as their
    Python repr; the scan history was capped across ALL accounts and not
    filtered by marketplace
  * SQP counted "went elsewhere" per own ASIN and took unknown purchases as 0
  * Leading mixed live-feed distinct orders with report order items, and
    skipped quiet days on accounts with no '*' rollup
  * source-level: inventory run no longer defaults to "US", the shared scope
    resolver is used, returns text sort direction, the detail race, mojibake
"""
import datetime as _dt
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

fails = []


def check(name, got, want):
    ok = got == want
    print("  %-66s %s" % (name[:66], "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        fails.append(name)


def truthy(name, cond):
    check(name, bool(cond), True)


def read(*p):
    return io.open(os.path.join(HERE, *p), encoding="utf-8").read()


tmp = tempfile.mkdtemp()
CFG = os.path.join(tmp, "config.json")
io.open(CFG, "w", encoding="utf-8").write(json.dumps({"accounts": []}))

try:
    # ------------------------------------------------------------------
    print("== INVENTORY 1: most urgent first, unknown last ==")
    from domain import inventory_view as IV
    from domain import live_snapshots as _ls
    _orig = (IV.velocity_map, IV.lead_times, _ls.get)
    try:
        _ls.get = lambda *a, **k: {"items": [
            {"sku": "SAFE", "qty": 300, "price": 10},
            {"sku": "OUT", "qty": 1, "price": 10},
            {"sku": "UNK", "qty": 5, "price": 10},
            {"sku": "SOON", "qty": 11, "price": 10},
        ]}
        IV.velocity_map = lambda *a, **k: {
            "SAFE": {"velocity": 1.0}, "OUT": {"velocity": 1.0},
            "SOON": {"velocity": 1.0}}
        IV.lead_times = lambda *a, **k: {}
        order = [r["sku"] for r in IV.rows(CFG, "w", "UK", catalogue={})]
    finally:
        IV.velocity_map, IV.lead_times, _ls.get = _orig
    check("stockout first, then order soon, safe, unknown last",
          order, ["OUT", "SOON", "SAFE", "UNK"])
    js = read("static", "js", "stock.js")
    truthy("the ledger's status order runs most urgent first",
           'const ORDER = ["stockout likely", "order now", "order soon", "watch", "safe"];' in js)

    # ------------------------------------------------------------------
    print("\n== INVENTORY 6: the window is N whole days ending yesterday ==")
    from data import db as _db
    conn = _db.get_db(CFG)
    conn.execute("CREATE TABLE IF NOT EXISTS order_lines (workspace_id TEXT, "
                 "marketplace TEXT, order_id TEXT, sku TEXT, units INT, "
                 "status TEXT, purchase_date TEXT)")
    today = _dt.date(2026, 9, 30)
    for i, days_ago in enumerate((0, 1, 30, 31)):
        conn.execute("INSERT INTO order_lines (workspace_id,marketplace,order_id,"
                     "sku,units,status,purchase_date) VALUES (?,?,?,?,?,?,?)",
                     ("w", "UK", "o%d" % i, "S", 1, "Shipped",
                      (today - _dt.timedelta(days=days_ago)).isoformat()))
    conn.commit()
    v = IV.velocity_map(CFG, "w", "UK", 30, today)
    check("today's partial day and day 31 are both outside", v["S"]["units"], 2)
    check("  and the rate is over 30 days", v["S"]["velocity"], round(2 / 30.0, 4))

    # ------------------------------------------------------------------
    print("\n== REIMBURSEMENTS 2: a failed read is not 'nothing owed' ==")
    from domain import money_back as MB
    conn.execute("DROP TABLE IF EXISTS order_fees")
    conn.commit()
    check("no table yet is honestly empty", MB.find(CFG, "w")["orders_checked"], 0)
    conn.execute("CREATE TABLE order_fees (workspace_id TEXT, order_id TEXT)")
    conn.commit()
    try:
        MB.find(CFG, "w")
        raised = False
    except Exception:
        raised = True
    truthy("a broken table raises, so the route answers ok:false", raised)
    conn.execute("DROP TABLE order_fees")
    conn.commit()

    # ------------------------------------------------------------------
    print("\n== CATALOG 1 + 2: costs by any case; not synced is not dead ==")
    from domain import product_catalog as PC
    names = {"B0AAA": {"asin": "B0AAA", "sku": "10.99_3Days_B0AAA", "title": "A"},
             "B0BBB": {"asin": "B0BBB", "sku": "x", "title": "B"}}
    rows = [{"date": "2026-09-01", "asin": "B0AAA", "units": 2, "ordered_sales": 20}]
    out = PC.build(rows, names=names, costs={"10.99_3DAYS_B0AAA": 4.0},
                   extra_asins=["B0BBB"], sales_cover=False)
    a = [r for r in out["rows"] if r["asin"] == "B0AAA"][0]
    check("a cost stored in the other case is found", a["cogs"], 4.0)
    check("unsynced window: 'dead' makes no count", out["findings"]["dead"]["n"], None)
    truthy("  and says why", out["findings"]["dead"].get("unknown"))
    out2 = PC.build(rows, names=names, costs={}, extra_asins=["B0BBB"])
    check("synced window: the dead product is counted", out2["findings"]["dead"]["n"], 1)
    src = read("routes", "catalog_page_routes.py")
    truthy("the route looks costs up through cogs_store.find", "_cogs.find(" in src)
    cjs = read("static", "js", "catalogpage.js")
    truthy("catalog: newest request wins", "mine !== _CATP_SEQ" in cjs)
    truthy("catalog: search box focus is restored", "box.setSelectionRange(" in cjs)
    truthy("catalog: margin is labelled before fees", "Gross margin" in cjs)
    truthy("catalog: currency comes from the reply", "CATP.data.currency" in cjs)

    # ------------------------------------------------------------------
    print("\n== COMPLIANCE 1, 5, 6 ==")
    from domain import compliance_scan as CS
    lst = CS.listing_from({"title": "T", "attributes": {
        "bullet_point": [{"value": "First bullet", "language_tag": "en_GB"},
                         {"value": "Second", "language_tag": "en_GB"}],
        "product_description": [{"value": "Desc", "language_tag": "en_GB"}]}})
    check("a Catalog bullet is its value, not a dict", lst["bullet_1"], "First bullet")
    check("  and the description too", lst["description"], "Desc")
    old_max = CS.MAX_SCANS
    try:
        CS.MAX_SCANS = 3
        CS.store(CFG, "other", {"asin": "B0KEEP", "at": "2026-01-01 00:00",
                                "marketplace": "UK"})
        for i in range(5):
            CS.store(CFG, "busy", {"asin": "B0%03d" % i, "at": "2026-01-0%d 00:00" % (i + 1),
                                   "marketplace": "DE" if i % 2 else "UK"})
    finally:
        CS.MAX_SCANS = old_max
    check("one busy account does not delete another's history",
          len(CS.scans(CFG, "other")), 1)
    check("  the busy one keeps its own cap", len(CS.scans(CFG, "busy")), 3)
    check("history can be narrowed to one marketplace",
          sorted(s["marketplace"] for s in CS.scans(CFG, "busy", marketplace="UK")),
          ["UK", "UK"])
    cmp_js = read("static", "js", "compliance.js")
    truthy("compliance: a failed history load is shown", "CMP.histError" in cmp_js)
    truthy("compliance: summary uses the latest scan per listing", "latest.forEach" in cmp_js)

    # ------------------------------------------------------------------
    print("\n== SQP 3 + 5 ==")
    from domain import search_query as SQ
    built = SQ.build([
        {"query": "q", "asin": "A1", "purchases": 3, "purchases_total": 10,
         "impressions_total": 1000, "impressions": 100},
        {"query": "q", "asin": "A2", "purchases": 2, "purchases_total": 10,
         "impressions_total": 1000, "impressions": 100},
        {"query": "u", "asin": "A1", "purchases": None, "purchases_total": 8,
         "impressions_total": 1000, "impressions": 100},
    ])
    miss = {(r["query"], r["asin"]): r["missed"] for r in built}
    check("went elsewhere is per search: 10 - (3+2)", miss[("q", "A1")], 5.0)
    check("  the same on the other ASIN's row", miss[("q", "A2")], 5.0)
    check("unknown own purchases leave it unknown", miss[("u", "A1")], None)
    summ = SQ.summary(built)
    total_missed = sum(v["missed"] for v in summ.values())
    check("the summary counts each search once", total_missed, 5.0)
    truthy("the default week is brand_analytics' one",
           "_ba._last_complete_week()" in read("routes", "sqp_routes.py"))

    # ------------------------------------------------------------------
    print("\n== LEADING 1, 2, 3 ==")
    from domain import leading as LD
    filled = LD.fill_quiet_days([
        {"date": "2026-09-01", "asin": "X", "units": 2, "sessions": 5},
        {"date": "2026-09-03", "asin": "X", "units": 1, "sessions": 4}])
    s = LD.series(filled, LD.INDEX["units"])
    check("a quiet day inside the synced span is a zero", s.get("2026-09-02"), 0.0)
    s2 = LD.series([
        {"date": "2026-09-01", "orders": 4, "orders_source": None},
        {"date": "2026-09-02", "orders": 2, "orders_source": "orders_api"}],
        LD.INDEX["orders"])
    check("report order items are kept", s2.get("2026-09-01"), 4.0)
    check("  live-feed distinct orders are left out", "2026-09-02" in s2, False)
    y = LD.yesterday(marketplace="US")
    truthy("yesterday on the marketplace's clock is a date", len(y) == 10 and y[4] == "-")
    check("  an explicit 'today' still wins", LD.yesterday(today="2026-09-30"), "2026-09-29")

    # ------------------------------------------------------------------
    print("\n== source-level fixes ==")
    inv = read("static", "js", "inventory.js")
    truthy("inventory run never defaults to US",
           'fd.append("marketplace", WS_MARKET || "US")' not in inv
           and 'fd.append("marketplace", mkt)' in inv)
    truthy("  and drops a late reply", "screenStillIn(_sc)" in inv)
    ir = read("routes", "inventory_routes.py")
    truthy("the route refuses __all__ / empty",
           'if not marketplace or marketplace == "__ALL__":' in ir)
    truthy("  no 'US' default left", '(request.form.get("marketplace") or "US")' not in ir)
    truthy("the shared scope resolver is used", "_rscope.pair(" in ir)
    truthy("the badge is keyed by account and marketplace", '"%s|%s" % (account_id, marketplace)' in ir)
    rl = read("static", "js", "returnslist.js")
    truthy("returns text sort follows its arrow", "dir * (x < y ? -1 : x > y ? 1 : 0)" in rl)
    truthy("a late detail reply for another return is dropped",
           "if(RETL.open !== identity) return;" in rl)
    rj = read("static", "js", "returns.js")
    truthy("a day chip pressed while busy still asks", "returnsLoad(true)" in rj)
    truthy("upload / Start again empty the stored list", "_retListForget();" in rj)
    rr = read("routes", "returns_routes.py")
    truthy("no mojibake dashes left in returns_routes", "â€" not in rr)
    cr = read("routes", "category_routes.py")
    truthy("categories: refused calls are not marked read", "if a in failed:" in cr)
    truthy("  and Populate rotates by oldest read", "sorted(known, key=_age)" in cr)
    tf = read("domain", "tracker_fetch.py")
    truthy("tracker_fetch keeps Amazon errors apart from no rank",
           '"error": _why(e)' in tf)
    cj = read("static", "js", "categories.js")
    truthy("categories: an error keeps the Populate button", "uiToolbar(btn" in cj)
    rb = read("static", "js", "reimbursements.js")
    truthy("reimbursements: a dropped reply clears loading",
           "{ RB.loading = false; return; }" in rb)
except Exception as e:
    import traceback
    traceback.print_exc()
    fails.append("the test itself: %s" % str(e)[:200])
finally:
    try:
        _db.get_db(CFG).close()
    except Exception:
        pass
    shutil.rmtree(tmp, ignore_errors=True)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
