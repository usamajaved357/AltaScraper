"""/sales/campaigns and the Sales currency, after their SQL moved (architecture batch A6).

routes/sales_routes.py asked the database itself for the per-campaign sums and
for the account's currency; both statements moved, word for word, into
domain/sales_queries.py. Nothing called /sales/campaigns in the suite, so this
pins its whole answer on a fixture database: the sums, the ordering, the rates
worked out from the sums (and None where there is nothing to divide by), the
totals, the currency, the advertising products and the freshest fetch.
"""
import os as _os_repo
_REPO = _os_repo.path.dirname(_os_repo.path.abspath(__file__))
import os, sys, json, tempfile
sys.path.insert(0, _REPO)

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


TMP = tempfile.mkdtemp(prefix="altasalesq_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "s.db")

from data import db as _db

conn = _db.get_db(CFG)
ROWS = [
    # campaign, date, name, status, budget, impr, clicks, spend, orders, sales, fetched, product
    ("C1", "2026-08-01", "Alpha", "ENABLED", 10.0, 100, 10, 5.0, 1, 20.0, "2026-08-02T01", "SPONSORED_PRODUCTS"),
    ("C1", "2026-08-02", "Alpha", "PAUSED", 12.0, 50, 5, 3.0, 0, 0.0, "2026-08-03T01", "SPONSORED_PRODUCTS"),
    ("C2", "2026-08-01", "Beta", "ENABLED", 5.0, 80, 4, 9.0, 0, 0.0, "2026-08-02T02", "SPONSORED_BRANDS"),
    ("C3", "2026-08-01", "Gamma", "ENABLED", 5.0, 10, 0, 0.0, 0, 0.0, "2026-08-02T03", "SPONSORED_PRODUCTS"),
    ("C9", "2026-07-01", "Outside", "ENABLED", 5.0, 10, 3, 50.0, 2, 90.0, "2026-07-02", "SPONSORED_PRODUCTS"),
]
for c, d, n, st, b, im, cl, sp, o, sa, f, p in ROWS:
    conn.execute("INSERT INTO ads_campaign_daily (workspace_id, marketplace, date, campaign_id, "
                 "campaign_name, status, budget, impressions, clicks, spend, ad_orders, ad_sales, "
                 "source, fetched_at, ad_product) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 ("ws1", "UK", d, c, n, st, b, im, cl, sp, o, sa, "test", f, p))
conn.execute("INSERT INTO sales_daily (workspace_id, marketplace, date, asin, units, "
             "ordered_sales, currency) VALUES (?,?,?,?,?,?,?)",
             ("ws1", "UK", "2026-08-01", "*", 1, 10.0, ""))
conn.execute("INSERT INTO sales_daily (workspace_id, marketplace, date, asin, units, "
             "ordered_sales, currency) VALUES (?,?,?,?,?,?,?)",
             ("ws1", "UK", "2026-08-02", "*", 1, 10.0, "GBP"))
conn.commit()

from flask import Flask
import routes.sales_routes as sr
app = Flask(__name__); app.secret_key = "t"
sr.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
            _active_account=lambda: {}, _state={})
c = app.test_client()

j = c.get("/sales/campaigns?account=ws1&marketplace=UK&start=2026-08-01&end=2026-08-31").get_json() or {}
check("answers", (j.get("ok"), j.get("workspace"), j.get("marketplace")), (True, "ws1", "UK"))
rows = j.get("rows") or []
check("three campaigns in the window, biggest spend first",
      [r["campaign_id"] for r in rows], ["C2", "C1", "C3"])
a = {r["campaign_id"]: r for r in rows}
check("C1 summed", (a["C1"]["impressions"], a["C1"]["clicks"], a["C1"]["spend"],
                    a["C1"]["ad_orders"], a["C1"]["ad_sales"], a["C1"]["days"]),
      (150, 15, 8.0, 1, 20.0, 2))
check("  MAX of the text columns", (a["C1"]["status"], a["C1"]["budget"], a["C1"]["fetched_at"]),
      ("PAUSED", 12.0, "2026-08-03T01"))
check("  rates from the sums", (a["C1"]["acos"], a["C1"]["roas"], round(a["C1"]["cpc"], 6),
                                round(a["C1"]["cvr"], 6)),
      (40.0, 2.5, round(8.0 / 15, 6), round(100.0 / 15, 6)))
check("spend and no sales: no ACOS", (a["C2"]["acos"], a["C2"]["roas"]), (None, 0.0))
check("no clicks: no CPC or CVR", (a["C3"]["cpc"], a["C3"]["cvr"]), (None, None))
check("totals", j.get("totals"), {"impressions": 240, "clicks": 19, "spend": 17.0,
                                  "ad_orders": 1, "ad_sales": 20.0})
check("the currency from the first row that has one", j.get("currency"), "GBP")
check("advertising products covered", j.get("ad_products"),
      ["SPONSORED_BRANDS", "SPONSORED_PRODUCTS"])
check("freshest fetch", j.get("fetched_at"), "2026-08-03T01")

e = c.get("/sales/campaigns?account=ws_none&marketplace=UK&start=2026-08-01&end=2026-08-31").get_json() or {}
check("an account with nothing", (e.get("rows"), e.get("currency"), e.get("ad_products")),
      ([], "", ["SPONSORED_PRODUCTS"]))

src = open(os.path.join(_REPO, "routes", "sales_routes.py"), "rb").read().decode("utf-8")
check("no SQL left in routes/sales_routes.py", any(k in src for k in (".execute(", "SELECT ")), False)

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\n/sales/campaigns answers exactly as before")
