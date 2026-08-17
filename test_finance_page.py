"""The Finance screen: the three ways it was wrong about money.

    "the finance page is also not correct i suspect check and fix all the bugs"

Each of these was found by adding up the stored figures by hand and comparing
them with what the screen reported. All three are the same class of fault -- the
screen and the money agreed on the easy cases and diverged on the ones that cost
something.

  1. A COUPON WAS COUNTED AS MONEY KEPT.
     Amazon reports the FULL item price and the discount as two separate things.
     The screen subtracted fees and refunds but not the discount, so a funded
     coupon was pure profit. jack_uk, 22 Jul - 16 Aug 2026: 11.60 GBP of coupons,
     contribution reported as 91.71 when it was 80.11.

  2. THE FEE AMAZON GIVES BACK ON A REFUND WAS NOT CREDITED.
     The column was not even selected. So a refunded sale was charged its
     referral fee and never given it back -- understating exactly the products
     with returns. selvora_limited, 5-16 Aug 2026: 9.77 GBP.

  3. MONEY THAT BELONGS TO NO PRODUCT WAS SIMPLY ABSENT.
     Two kinds. Charges with no SKU (the 25/month selling subscription) and sales
     whose SKU is not in the catalogue snapshot. Both are stored correctly on the
     account-total row, and neither appeared anywhere on a screen that lists
     products and totals them up.
       jack_uk:         50.00 of subscription -> page said 80.11 kept, it was 30.11
       selvora_limited: 1578.54 of 1909.11 revenue and 51 of 60 units NOT LISTED,
                        so the page showed one product and 17% of the money

The live audit against the real database is probe_finance_page.py. This is the
same arithmetic on figures made up here, so it runs anywhere and cannot pass by
accident on an account that happens to have no coupons.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, r"D:\AltaScraper")

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-66s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


def truthy(l, g):
    check(l, bool(g), True)


def falsy(l, g):
    check(l, bool(g), False)


TMP = tempfile.mkdtemp(prefix="altafinpage_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "f.db")

from data import db as _db                                    # noqa: E402
from domain import contribution as C                          # noqa: E402
from domain import sales_data as SD                           # noqa: E402

WS, MKT = "acct", "UK"
conn = _db.get_db(CFG)

COLS = ("workspace_id, marketplace, date, asin, principal, referral_fees, "
        "fba_fees, other_fees, refunds, refund_units, refund_fees_returned, "
        "reimbursements, promos, units, cogs, cogs_units, currency, tax")


def put(date, asin, **kw):
    vals = {k: 0 for k in ("principal", "referral_fees", "fba_fees", "other_fees",
                           "refunds", "refund_units", "refund_fees_returned",
                           "reimbursements", "promos", "units", "cogs",
                           "cogs_units")}
    vals.update(kw)
    conn.execute(
        "INSERT INTO finance_daily (%s) VALUES (%s)"
        % (COLS, ",".join("?" * 18)),
        (WS, MKT, date, asin, vals["principal"], vals["referral_fees"],
         vals["fba_fees"], vals["other_fees"], vals["refunds"],
         vals["refund_units"], vals["refund_fees_returned"],
         vals["reimbursements"], vals["promos"], vals["units"], vals["cogs"],
         vals["cogs_units"], "GBP", kw.get("tax", 0)))


print("=== 1. a funded coupon is money you did not keep ===")
# One product, one day. 100 charged, 15 of fees, 10 of coupon, 40 of cost.
# Kept: 100 - 15 - 10 = 75. Contribution: 75 - 40 = 35.
# The bug reported 45, because the 10 was never subtracted.
put("2026-08-01", "*",     principal=100, referral_fees=15, promos=10, units=1)
put("2026-08-01", "B0ONE", principal=100, referral_fees=15, promos=10, units=1,
    cogs=40, cogs_units=1)
rows, tot = C.by_product(CFG, WS, MKT, "2026-08-01", "2026-08-01", vat_rate=0)
check("the coupon is reported", tot["promos"], 10.0)
check("net proceeds is after the coupon", tot["net_proceeds"], 75.0)
check("  so the contribution is 35, not 45", tot["contribution"], 35.0)
check("  and the row agrees with the footer", rows[0]["contribution"], 35.0)
# The margin is on what buyers were charged, which is the same basis the Sales
# screen uses -- so the two screens report the same percentage.
check("margin is over the charged amount", tot["margin_pct"], 35.0)
truthy("the screen says the coupon was taken off",
       any("coupons and deals you funded" in n["text"]
           for n in C.notes(rows, tot)))

print("\n=== 2. the two screens cannot disagree ===")
# THE REAL GUARD. Both screens read finance_daily; the arithmetic used to be
# written out twice and the copies had drifted. This pins them together, so a
# change to one that is not made to the other fails here rather than on a screen.
star = {"principal": 100, "referral_fees": 15, "fba_fees": 0, "other_fees": 0,
        "refunds": 0, "refund_fees_returned": 0, "reimbursements": 0,
        "promos": 10, "tax": 0}
sales_answer = SD.net_proceeds_for(star, 0)
check("the Sales screen's own formula agrees", sales_answer["net_proceeds"], 75.0)
check("  and the Finance screen used that same function", tot["net_proceeds"],
      sales_answer["net_proceeds"])

print("\n=== 3. the fee Amazon returns on a refund is credited back ===")
conn.execute("DELETE FROM finance_daily")
# 200 charged, 30 of fees, then a 50 refund on which Amazon returns 7.50 of the
# fee. Kept: 200 - 30 - 50 + 7.50 = 127.50.
put("2026-08-02", "*",     principal=200, referral_fees=30, refunds=50,
    refund_units=1, refund_fees_returned=7.5, units=2)
put("2026-08-02", "B0TWO", principal=200, referral_fees=30, refunds=50,
    refund_units=1, refund_fees_returned=7.5, units=2, cogs=60, cogs_units=2)
rows, tot = C.by_product(CFG, WS, MKT, "2026-08-02", "2026-08-02", vat_rate=0)
check("the returned fee is reported", tot["refund_fees_returned"], 7.5)
check("net proceeds credits it back", tot["net_proceeds"], 127.5)
check("  so the contribution is 67.50, not 60.00", tot["contribution"], 67.5)
# Without the credit the answer would be 60.00 -- 7.50 light, on exactly the
# products that have returns.
falsy("  the old answer is gone", tot["contribution"] == 60.0)

print("\n=== 4. charges that belong to no product are disclosed ===")
conn.execute("DELETE FROM finance_daily")
# A month's trade plus two 25.00 subscription charges on days with no sales.
# Those cannot be split across products, so they sit on the account row only.
put("2026-08-03", "*",       principal=300, referral_fees=45, units=3)
put("2026-08-03", "B0THREE", principal=300, referral_fees=45, units=3,
    cogs=100, cogs_units=3)
put("2026-08-14", "*", other_fees=25)
put("2026-08-16", "*", other_fees=25)
rows, tot = C.by_product(CFG, WS, MKT, "2026-08-01", "2026-08-31", vat_rate=0)
check("the products contributed", tot["contribution"], 155.0)
check("50.00 is on the account and no product", tot["unattributed_fees"], 50.0)
check("  so what the account kept is also reported",
      tot["account_contribution"], 105.0)
said = [n["text"] for n in C.notes(rows, tot)]
truthy("the screen says the charges exist",
       any("belong to no single product" in s for s in said))
truthy("  and gives both figures, so neither is mistaken for the other",
       any("155.00" in s and "105.00" in s for s in said))
lv = [n["level"] for n in C.notes(rows, tot)
      if "belong to no single product" in n["text"]]
check("  and it is marked serious", lv, ["bad"])

print("\n=== 5. sales with no product are disclosed, loudly ===")
conn.execute("DELETE FROM finance_daily")
# THE SELVORA CASE. The account took 1000 across 20 units; only 200 and 4 units
# could be matched to a product, because the rest were sold on SKUs that are not
# in the catalogue snapshot. The screen listed one product and said nothing.
put("2026-08-04", "*",      principal=1000, referral_fees=150, units=20)
put("2026-08-04", "B0FOUR", principal=200, referral_fees=30, units=4,
    cogs=80, cogs_units=4)
rows, tot = C.by_product(CFG, WS, MKT, "2026-08-04", "2026-08-04", vat_rate=0)
check("only the matched product is listed", len(rows), 1)
check("800.00 of revenue is not in the list", tot["unattributed_revenue"], 800.0)
check("  and 16 units", tot["unattributed_units"], 16)
check("  which is 80% of the money", tot["unattributed_pct"], 80.0)
said = [n["text"] for n in C.notes(rows, tot)]
truthy("the screen says the list is incomplete",
       any("NOT in the list below" in s for s in said))
truthy("  names the amount and the share",
       any("800.00" in s and "80.0%" in s for s in said))
truthy("  says why, in terms of what to do about it",
       any("catalogue snapshot" in s and "Sync" in s for s in said))
notes = C.notes(rows, tot)
check("  and it is the FIRST thing said, not the fifth", notes[0]["level"], "bad")
truthy("  the first note is the one about missing money",
       "NOT in the list below" in notes[0]["text"])

print("\n=== 6. an unattributed figure never flatters ===")
conn.execute("DELETE FROM finance_daily")
# The products carry MORE than the account row does. That cannot come from
# account-level charges -- it would be a storage fault -- and reporting a
# negative "unattributed" would ADD to the contribution. It must report zero.
put("2026-08-05", "*",      principal=100, referral_fees=10, units=1)
put("2026-08-05", "B0FIVE", principal=150, referral_fees=20, units=2,
    cogs=50, cogs_units=2)
rows, tot = C.by_product(CFG, WS, MKT, "2026-08-05", "2026-08-05", vat_rate=0)
check("no negative unattributed revenue", tot["unattributed_revenue"], 0.0)
check("no negative unattributed fees", tot["unattributed_fees"], 0.0)
check("no negative unattributed units", tot["unattributed_units"], 0)
check("  and no account figure invented from one",
      tot["account_contribution"], None)
falsy("  nothing is said about charges that are not there",
      any("belong to no single product" in n["text"] for n in C.notes(rows, tot)))

print("\n=== 7. the footer always equals the rows ===")
conn.execute("DELETE FROM finance_daily")
put("2026-08-06", "*",     principal=90, referral_fees=9, promos=4,
    refund_fees_returned=1, units=3)
put("2026-08-06", "B0SIX", principal=60, referral_fees=6, promos=3,
    refund_fees_returned=1, units=2, cogs=20, cogs_units=2)
put("2026-08-06", "B0SVN", principal=30, referral_fees=3, promos=1,
    units=1, cogs=10, cogs_units=1)
rows, tot = C.by_product(CFG, WS, MKT, "2026-08-06", "2026-08-06", vat_rate=0)
for k in ("revenue", "fees", "promos", "refund_fees_returned", "cogs",
          "net_proceeds", "units"):
    summed = sum(r[k] for r in rows)
    summed = round(summed, 2) if isinstance(summed, float) else summed
    check("footer %s equals the rows" % k, tot[k], summed)
# Contribution is the ONE exception, and deliberately: it is recomputed, never
# summed, so a product whose figure is withheld cannot be silently dropped and
# the remainder presented as the total.
#   B0SIX  60 - 6 fees - 3 coupon + 1 fee back = 52, less 20 cost = 32
#   B0SVN  30 - 3 fees - 1 coupon              = 26, less 10 cost = 16
check("contribution is recomputed from the whole", tot["contribution"], 48.0)
check("  which is the sum of the rows here, since both are known",
      sum(r["contribution"] for r in rows), 48.0)

# AND THE CASE THAT PROVES IT IS NOT A SUM. One product has an uncosted unit, so
# its own contribution is withheld. Summing the rows would report the other
# product's 32.00 as the period's total -- a smaller number wearing the label of
# a complete one, and there is nothing on the screen to reveal it.
conn.execute("DELETE FROM finance_daily")
put("2026-08-07", "*",     principal=90, referral_fees=9, units=3)
put("2026-08-07", "B0SIX", principal=60, referral_fees=6, units=2,
    cogs=20, cogs_units=2)
put("2026-08-07", "B0SVN", principal=30, referral_fees=3, units=1)   # no cost
rows, tot = C.by_product(CFG, WS, MKT, "2026-08-07", "2026-08-07", vat_rate=0)
by = {r["asin"]: r for r in rows}
check("the costed product reports its own figure", by["B0SIX"]["contribution"], 34.0)
check("the uncosted one reports nothing", by["B0SVN"]["contribution"], None)
check("and the period total is withheld, not 34.00", tot["contribution"], None)
truthy("  with the reason on screen",
       any("no known cost" in n["text"] for n in C.notes(rows, tot)))

print("\n" + ("FAILURES: %s" % ", ".join(fails) if fails else "FAILURES: 0"))
sys.exit(1 if fails else 0)
