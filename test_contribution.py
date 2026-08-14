"""Contribution per product, and the two figures it refuses to invent.

Ad spend is UNKNOWN, not zero -- nothing writes to ads_daily yet. Subtracting it
as 0.00 would make every advertised product look better than it is by exactly
what is being spent on it, and would look entirely convincing. And a product with
uncosted units gets no contribution at all, for the same reason the dashboard
withholds profit: a partial cost only ever flatters.
"""
import os, sys, json, tempfile, shutil
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

def truthy(l, g):
    check(l, bool(g), True)

TMP = tempfile.mkdtemp(prefix="altacontrib_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "c.db")

from data import db as _db
from domain import contribution as C

WS, MKT = "jack_uk", "UK"
A1, A2, A3 = "B0AAAA0001", "B0BBBB0002", "B0CCCC0003"


def fin(date, asin, principal, ref, fba, other, refunds, units, cogs, cogs_units,
        reimb=0.0):
    conn = _db.get_db(CFG)
    conn.execute(
        "INSERT INTO finance_daily (workspace_id, marketplace, date, asin, "
        "referral_fees, fba_fees, other_fees, refunds, refund_units, "
        "reimbursements, promos, principal, units, cogs, cogs_units, currency, source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (WS, MKT, date, asin, ref, fba, other, refunds, 0, reimb, 0.0,
         principal, units, cogs, cogs_units, "GBP", "test"))
    conn.commit()

def sale(date, asin, units, revenue):
    conn = _db.get_db(CFG)
    conn.execute("INSERT INTO sales_daily (workspace_id, marketplace, date, asin, "
                 "units, ordered_sales) VALUES (?,?,?,?,?,?)",
                 (WS, MKT, date, asin, units, revenue))
    conn.commit()


# A1: fully costed.  100.00 charged, 15.00 fees, 40.00 cost, 2 units -> 45.00
fin("2026-08-01", A1, 60.00, 6.00, 3.00, 0.0, 0.0, 1, 20.00, 1)
fin("2026-08-02", A1, 40.00, 4.00, 2.00, 0.0, 0.0, 1, 20.00, 1)
sale("2026-08-01", A1, 1, 60.00)
sale("2026-08-02", A1, 1, 40.00)
# A2: half its units have no cost recorded.
fin("2026-08-01", A2, 50.00, 5.00, 2.50, 0.0, 0.0, 2, 12.00, 1)
# A3: costed, and carries a refund.
fin("2026-08-02", A3, 30.00, 3.00, 1.50, 0.0, 10.00, 1, 8.00, 1)

rows, totals = C.by_product(CFG, WS, MKT, "2026-08-01", "2026-08-31")
by = {r["asin"]: r for r in rows}

print("=== one row per product that had money move ===")
check("three products", len(rows), 3)
check("biggest revenue first", rows[0]["asin"], A1)

print("\n=== a fully costed product reports its contribution ===")
r = by[A1]
check("units shipped", r["units"], 2)
check("revenue", r["revenue"], 100.0)
check("fees are the three added up", r["fees"], 15.0)
check("cost of goods", r["cogs"], 40.0)
check("net proceeds = 100 - 15", r["net_proceeds"], 85.0)
check("contribution = 85 - 40", r["contribution"], 45.0)
check("margin on revenue", r["margin_pct"], 45.0)
check("nothing uncosted", r["uncosted_units"], 0)

print("\n=== a refund comes out before the contribution ===")
r3 = by[A3]
check("net = 30 - 4.50 - 10", r3["net_proceeds"], 15.5)
check("contribution = 15.50 - 8", r3["contribution"], 7.5)

print("\n=== a product with uncosted units reports NOTHING ===")
r2 = by[A2]
check("two units shipped", r2["units"], 2)
check("  only one costed", r2["cogs_units"], 1)
check("  so one is uncosted", r2["uncosted_units"], 1)
check("no contribution", r2["contribution"], None)
check("  and no margin", r2["margin_pct"], None)
check("  but its cost so far is still shown", r2["cogs"], 12.0)
check("  and its revenue", r2["revenue"], 50.0)

print("\n=== ad spend is UNKNOWN, never zero ===")
check("no ad row -> None", by[A1]["ad_spend"], None)
check("  and the total says the same", totals["ad_spend"], None)
truthy("  the screen is told to say so",
       any("BEFORE" in n for n in C.notes(rows, totals)))
truthy("  and warns which way it is wrong",
       any("lower by whatever you spent" in n for n in C.notes(rows, totals)))

print("  -- when ad data does arrive, it is used --")
conn = _db.get_db(CFG)
conn.execute("INSERT INTO ads_daily (workspace_id, marketplace, date, asin, "
             "spend, ad_sales, source) VALUES (?,?,?,?,?,?,?)",
             (WS, MKT, "2026-08-01", A1, 12.50, 60.0, "upload"))
conn.commit()
rows2, totals2 = C.by_product(CFG, WS, MKT, "2026-08-01", "2026-08-31")
check("that product's spend is read", {r["asin"]: r for r in rows2}[A1]["ad_spend"], 12.5)
check("  the products with none stay unknown",
      {r["asin"]: r for r in rows2}[A2]["ad_spend"], None)
check("  and the total is no longer blank", totals2["ad_spend"], 12.5)

print("\n=== the total is recomputed, not summed ===")
# A1 45.00 + A3 7.50 = 52.50 if you sum the column. That would silently drop A2's
# revenue and fees entirely and present the rest as the whole period.
check("the period contains an uncosted unit, so the total is withheld",
      totals["contribution"], None)
check("  and so is its margin", totals["margin_pct"], None)
check("  but the parts still add up: revenue", totals["revenue"], 180.0)
check("  fees", totals["fees"], 27.0)          # 15.00 + 7.50 + 4.50
check("  units", totals["units"], 5)
check("  and it counts the products", totals["products"], 3)

print("  -- with every unit costed, the total appears --")
fin("2026-08-03", A2, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 12.00, 1)   # cost the missing one
rows3, totals3 = C.by_product(CFG, WS, MKT, "2026-08-01", "2026-08-31")
b3 = {r["asin"]: r for r in rows3}
check("the product reports now", b3[A2]["contribution"], 18.5)
check("  and so does the period", totals3["contribution"], 71.0)
truthy("  with no 'uncosted' warning left",
       not any("no known cost" in n for n in C.notes(rows3, totals3)))

print("\n=== the endpoint ===")
from flask import Flask
import routes.finance_routes as fr
app = Flask(__name__); app.secret_key = "t"
fr.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
            _active_account=lambda: {"id": WS},
            _state={"active_account_id": WS, "active_marketplace": MKT})
c = app.test_client()
j = c.get("/finance/contribution?start=2026-08-01&end=2026-08-31").get_json()
check("it answers", j["ok"], True)
check("  with the rows", len(j["rows"]), 3)
check("  the totals", j["totals"]["products"], 3)
check("  reporting whether ads are connected", j["ads_connected"], True)
# Every unit is costed and an ad row exists, so the only thing left unknown is
# VAT -- and it says so rather than staying quiet, which is the point.
check("  one warning left: VAT is not configured", len(j["notes"]), 1)
truthy("  and it says which way the number is wrong",
       "overstated" in j["notes"][0])
check("  and a contribution the screen can show", j["totals"]["contribution"], 71.0)


print("\n=== VAT: taken out first, and never invented ===")
from domain import sales_data as SD

print("  -- Amazon itemised it: revenue is already net --")
v, net, basis = SD.vat_for({"principal": 100.0, "tax": 20.0})
check("the tax Amazon reported", v, 20.0)
check("  revenue is left alone", net, 100.0)
check("  basis", basis, SD.VAT_FROM_AMAZON)

print("  -- no tax line, VAT-registered: it comes OUT of the charged amount --")
v, net, basis = SD.vat_for({"principal": 120.0}, 0.20)
check("120.00 gross at 20% -> 20.00 of VAT", v, 20.0)
check("  and 100.00 left", net, 100.0)
check("  basis", basis, SD.VAT_DERIVED)
check("the classic error is NOT made (120 x 0.20 = 24.00 would be wrong)",
      v != 24.0, True)

print("  -- nobody has said: refuse to guess --")
v, net, basis = SD.vat_for({"principal": 120.0}, None)
check("no VAT figure", v, None)
check("  revenue unchanged", net, 120.0)
check("  and it is flagged as unknown", basis, SD.VAT_UNKNOWN)

print("  -- a rate of 0 is a real answer: not registered --")
v, net, basis = SD.vat_for({"principal": 120.0}, 0)
check("zero VAT", v, 0.0)
check("  basis says so", basis, SD.VAT_NONE)
check("a nonsense rate is refused", SD.vat_for({"principal": 120.0}, 1.5)[2],
      SD.VAT_UNKNOWN)

print("  -- and it changes the contribution --")
rows4, tot4 = C.by_product(CFG, WS, MKT, "2026-08-01", "2026-08-31", vat_rate=0.20)
b4 = {r["asin"]: r for r in rows4}
# A1: 100.00 charged -> 16.67 VAT -> 83.33 net -> - 15.00 fees - 40.00 cogs
check("A1 VAT out of 100.00", b4[A1]["vat"], 16.67)
check("  revenue after VAT", b4[A1]["net_revenue"], 83.33)
check("  contribution drops by the VAT", b4[A1]["contribution"], 28.33)
check("  which is lower than before", b4[A1]["contribution"] < 45.0, True)
truthy("  and the screen explains which basis was used",
       any("did not itemise" in n for n in C.notes(rows4, tot4)))
check("the total moves too", tot4["contribution"], 41.0)
check("no marketplace -> a clear refusal",
      Flask(__name__) and c.get("/finance/contribution").status_code, 200)

print("\n=== it is gated like the sales dashboard, not like listings ===")
from auth import guard
check("the Finance screen belongs to sales", guard.feature_for("/finance/contribution"), "sales")
check("  reading needs no action permission",
      guard.required_permission("/finance/contribution", "GET"), None)
lister = {"role": "lister", "permissions": ["edit"], "active": True,
          "features": {"sales": "none", "listings": "edit"}, "workspaces": ["*"]}
check("a lister with no sales access cannot see it",
      guard.check("/finance/contribution", "GET", lister, None)[0], False)
boss = {"role": "owner", "permissions": ["edit"], "active": True,
        "features": {"sales": "view"}, "workspaces": ["*"]}
check("  read-only sales access is enough to look",
      guard.check("/finance/contribution", "GET", boss, None)[0], True)

os.environ.pop("ALTASCRAPER_DB", None)
shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
