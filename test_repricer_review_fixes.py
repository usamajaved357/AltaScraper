"""Repricer bug round (owner, 30 Sep 2026): "when a listing has 3 variations but
2 of them are out of stock then the url of ebay do not have variation id ... there
is an error in accepting that link. also look for other bugs in the repricer
including the profit calculations".

Each block fails on the code before the fix.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


TMP = tempfile.mkdtemp(prefix="altarepr_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "ws1", "label": "One"}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "r.db")

from domain import ebay_variation as EV   # noqa: E402
from domain import source_repo as R       # noqa: E402
from domain import sourcing as S          # noqa: E402


def child(var, stock, colour, price):
    avail = ({"estimatedAvailabilityStatus": "IN_STOCK"} if stock is True else
             {"estimatedAvailabilityStatus": "OUT_OF_STOCK"} if stock is False else {})
    return {"itemId": "v1|123456789012|%s" % var, "legacyItemId": "123456789012",
            "itemWebUrl": "https://www.ebay.co.uk/itm/123456789012",
            "price": {"value": str(price), "currency": "GBP"},
            "localizedAspects": [{"name": "Colour", "value": colour}],
            "estimatedAvailabilities": [avail] if avail else []}


print("== 1. a variation link with no ?var= ==")
fam = {"items": [child("111", True, "Black", 9.99), child("222", False, "Red", 9.99),
                 child("333", False, "Blue", 10.49)]}
kids = EV.variations(fam, "https://www.ebay.co.uk/itm/123456789012")
check("three children, each with its own ?var= link",
      [k["url"] for k in kids],
      ["https://www.ebay.co.uk/itm/123456789012?var=111",
       "https://www.ebay.co.uk/itm/123456789012?var=222",
       "https://www.ebay.co.uk/itm/123456789012?var=333"])
check("one in stock, two out: that one is the only one it can mean",
      (EV.pick(kids) or {}).get("var_id"), "111")
two = EV.variations({"items": [child("111", True, "Black", 9.99), child("222", True, "Red", 9.99)]})
check("two in stock: the owner chooses", EV.pick(two), None)
unk = EV.variations({"items": [child("111", True, "Black", 9.99), child("222", None, "Red", 9.99)]})
check("one in stock, one UNKNOWN: unknown is never out of stock -> choose", EV.pick(unk), None)
check("the label tells them apart", kids[0]["label"], "Black")

print("\n== 2. re-enrolling never disarms ==")
R.enrol(CFG, "ws1", "UK", "SKU1", mode="live")
R.enrol(CFG, "ws1", "UK", "SKU1")          # the supplier sheet, bulk enrol, single enrol
mode = [r["mode"] for r in R.enrolled(CFG, "ws1", "UK") if r["sku"] == "SKU1"]
check("an armed SKU stays armed when enrolled again", mode, ["live"])
R.set_mode(CFG, "ws1", "UK", "SKU1", "dry_run")
mode = [r["mode"] for r in R.enrolled(CFG, "ws1", "UK") if r["sku"] == "SKU1"]
check("  disarming is its own deliberate act", mode, ["dry_run"])

print("\n== 3. suppliers answer to their own account ==")
sid, _c = R.ensure_source(CFG, "ws1", "UK", "SKU1", "https://www.ebay.co.uk/itm/1?var=2")
check("its own account", R.source_belongs(CFG, sid, "ws1", "UK"), True)
check("another account's id is not accepted", R.source_belongs(CFG, sid, "ws2", "UK"), False)

print("\n== 4. the price rules ==")
SRC = open(os.path.join(HERE, "domain", "sourcing.py"), "rb").read().decode("utf-8")
check("a minimum above the maximum holds it off sale",
      "your minimum price %.2f is above your maximum %.2f" in SRC, True)
check("a small move off BELOW the floor is not skipped",
      "_below = cur_price < need - 0.005" in SRC and "and not _below" in SRC, True)
RT = open(os.path.join(HERE, "routes", "sourcing_routes.py"), "rb").read().decode("utf-8")
check("min above max is refused when the rules are saved",
      "no price \"\n                \"keeps both" in RT.replace("\r\n", "\n") or "keeps both\" % (float(_mn)" in RT, True)
check("supplier edit/remove check the account",
      RT.count("_repo.source_belongs(CONFIG_PATH") >= 2, True)
check("add supplier resolves a variation family instead of refusing",
      "_ev.resolve(url, app_id, cert_id" in RT and '"choose": True' in RT, True)

print("\n== 5. one reading of eBay, one currency, errors said ==")
VR = open(os.path.join(HERE, "routes", "variant_routes.py"), "rb").read().decode("utf-8")
check("add-variant reads price and postage through the repricer's reader",
      "_sf.from_ebay_item(item)" in VR, True)
SR = open(os.path.join(HERE, "domain", "source_run.py"), "rb").read().decode("utf-8")
check("the fee panel is in the marketplace's currency",
      "_sourcing.CURRENCY_FOR.get(str(marketplace" in SR, True)
SJ = open(os.path.join(HERE, "static", "js", "sourcing.js"), "rb").read().decode("utf-8")
check("a failed supplier-alert check is said, not blank",
      "Could not check supplier alerts" in SJ, True)
SB = open(os.path.join(HERE, "domain", "source_bulk.py"), "rb").read().decode("utf-8")
check("the supplier sheet resolves family links too", "_resolve_variations(config_path, marketplace, good)" in SB, True)

print("\nFAILURES: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
