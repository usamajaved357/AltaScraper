"""The costs that are not the supplier's price.

ASKED FOR: "give me option to add the additional charges per asin, which can be
sometimes my shipping price, my prep charges, my ads costs which i write
manually".

The supplier price already includes their postage -- "the source price is actual
source price including shipping" -- so what is missing is everything paid after
that. Without it, profit is revenue minus the supplier price and nothing else,
which reads better than the business is doing.

The rules being tested: charges are per unit and named, a SKU beats an ASIN, a
dated change does not rewrite history, and there is no bulk sheet upload
(deliberately -- it would flatten the per-order detail the repricer exists for).
"""
import os, sys, json, tempfile, shutil

sys.path.insert(0, r"D:\AltaScraper")

from flask import Flask
import domain.asin_charges as ac

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def check_true(label, got):
    check(label, bool(got), True)


TMP = tempfile.mkdtemp(prefix="altachg_")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w").write("{}")
WS, MKT, ASIN = "jack_uk", "UK", "B0G1K5B7QS"

print("\n== several named charges add up, per unit ==")
ac.save(CFG, WS, MKT, ASIN, "postage", 2.90)
ac.save(CFG, WS, MKT, ASIN, "prep", 0.75)
ac.save(CFG, WS, MKT, ASIN, "ads", 1.20)
total, parts = ac.per_unit(CFG, WS, MKT, ASIN)
check("the total is the sum", total, 4.85)
check("and every charge is named, not merged", len(parts), 3)
check("named so a thin margin can be explained",
      sorted(p["label"] for p in parts), ["ads", "postage", "prep"])

print("\n== a product with nothing recorded costs nothing extra ==")
t0, p0 = ac.per_unit(CFG, WS, MKT, "B000NOTHING")
check("no charges means zero, not an error", t0, 0)
check("and an empty list", p0, [])

print("\n== raising a fee today does NOT rewrite last month ==")
ac.save(CFG, WS, MKT, ASIN, "prep", 1.50, effective_from="2026-08-01")
back, _ = ac.per_unit(CFG, WS, MKT, ASIN, on_date="2026-07-15")
now, _ = ac.per_unit(CFG, WS, MKT, ASIN, on_date="2026-08-14")
check("an order from July keeps the old prep fee", back, 4.85)
check("an order from August gets the new one", now, round(2.90 + 1.50 + 1.20, 4))
check_true("so putting a price up cannot move a past month's profit", back != now)

print("\n== a charge dated in the future does not apply yet ==")
ac.save(CFG, WS, MKT, ASIN, "storage", 3.00, effective_from="2026-12-01")
soon, _ = ac.per_unit(CFG, WS, MKT, ASIN, on_date="2026-08-14")
check("not counted before it starts", soon, round(2.90 + 1.50 + 1.20, 4))
later, _ = ac.per_unit(CFG, WS, MKT, ASIN, on_date="2026-12-25")
check("counted once it does", later, round(2.90 + 1.50 + 1.20 + 3.00, 4))

print("\n== a charge on the SKU beats one on the ASIN ==")
ac.save(CFG, WS, MKT, ASIN, "postage", 5.00, sku="8.00_3Days_B0G1K5B7QS")
generic, _ = ac.per_unit(CFG, WS, MKT, ASIN)
specific, parts_s = ac.per_unit(CFG, WS, MKT, ASIN, sku="8.00_3Days_B0G1K5B7QS")
check("the ASIN-wide figure is unchanged for other SKUs", generic, round(2.90 + 1.50 + 1.20, 4))
check("the SKU's own postage wins for that SKU", specific, round(5.00 + 1.50 + 1.20, 4))
check_true("and it is still one postage line, not two",
           len([p for p in parts_s if p["label"] == "postage"]) == 1)

print("\n== editing and deleting ==")
cid = ac.save(CFG, WS, MKT, "B000EDIT", "prep", 1.00)
ac.save(CFG, WS, MKT, "B000EDIT", "prep", 2.00, charge_id=cid)
t, _ = ac.per_unit(CFG, WS, MKT, "B000EDIT")
check("an edit replaces rather than adds", t, 2.0)
ac.delete(CFG, WS, MKT, cid)
t2, _ = ac.per_unit(CFG, WS, MKT, "B000EDIT")
check("a deleted charge stops counting", t2, 0)

print("\n== a charge of zero is a real answer and is kept ==")
z = ac.save(CFG, WS, MKT, "B000FREE", "prep", 0)
rows = ac.list_for(CFG, WS, MKT, asin="B000FREE")
check("'prep is free on this one' is recordable", len(rows), 1)
check("and reads as zero, not missing", ac.per_unit(CFG, WS, MKT, "B000FREE")[0], 0)

print("\n== a charge with no name is refused, with a plain reason ==")
try:
    ac.save(CFG, WS, MKT, ASIN, "", 1.0)
    check("an unnamed charge is refused", "accepted", "ValueError")
except ValueError as e:
    check_true("an unnamed charge is refused", "needs a name" in str(e))
try:
    ac.save(CFG, WS, MKT, ASIN, "prep", "not a number")
    check("a non-numeric amount is refused", "accepted", "ValueError")
except ValueError as e:
    check_true("a non-numeric amount is refused", "number" in str(e))

print("\n== the routes answer, and there is NO sheet upload ==")
app = Flask(__name__)
import routes.asin_charges_routes as rr
_state = {"active_account_id": WS, "active_marketplace": MKT}
rr.register(app, CONFIG_PATH=CFG, _cfg=lambda: {}, _state=_state,
            _active_account=lambda: {"id": WS})
c = app.test_client()

j = c.get("/charges/list?account_id=%s&marketplace=%s" % (WS, MKT)).get_json()
check("list answers", j["ok"], True)
check_true("and returns what was saved", len(j["charges"]) > 0)

j2 = c.post("/charges/save", json={"account_id": WS, "marketplace": MKT,
                                   "asin": "B000ROUTE", "label": "prep",
                                   "amount": 0.99}).get_json()
check("save answers with an id", bool(j2.get("id")), True)
j3 = c.get("/charges/preview?account_id=%s&marketplace=%s&asin=B000ROUTE"
           % (WS, MKT)).get_json()
check("preview shows the per-unit cost", j3["per_unit"], 0.99)

j4 = c.post("/charges/save", json={"account_id": WS, "marketplace": MKT,
                                   "asin": "B000BAD", "label": "",
                                   "amount": 1}).get_json()
check("a bad save is a plain 400, not a crash", j4["ok"], False)
check_true("  saying what was wrong", "needs a name" in j4["error"])

src = open(r"D:\AltaScraper\routes\asin_charges_routes.py", encoding="utf-8").read()
# Checked on the ROUTES, not on the prose -- the file explains at length WHY
# there is no upload, and grepping for the word found the explanation.
import re
routes = re.findall(r'@app\.route\("([^"]+)"', src)
check("the routes are exactly the four intended", sorted(routes),
      ["/charges/delete", "/charges/list", "/charges/preview", "/charges/save"])
check("none of them takes a file",
      any(("request.files" in src, "csv.reader" in src, "read_csv" in src)), False)

# Every route must name its account rather than trusting the server-wide global.
check_true("the account comes from the request, not a global",
           "request_account" in src)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
