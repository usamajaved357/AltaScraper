""""All marketplaces" now means all marketplaces.

The sidebar has offered it all along, and every screen threw it away.
static/js/scopeq.js drops the parameter; the routes that do receive it turn it
into the account's default:

    routes/traffic_routes.py:65   if not mkt or mkt == "__all__":
    routes/hourly_routes.py:23        mkt = str(acc.get("default_marketplace") or "")

MEASURED 21 Aug 2026 in a real browser. With "All marketplaces" showing in the
sidebar, the Sales screen said "United Kingdom Time", drew a week-to-date chart
in pounds, and the report under it was jack_uk's UK figures. Jack Reacherd sells
in ten marketplaces; one was shown, under a heading that said all.

AND A SECOND FAULT, FOUND WHILE PROVING THE FIRST. Switching marketplace while
looking at a screen made ZERO requests. screenForgetAll() marked every screen
stale, but nothing re-opened the one on the glass, so the previous
marketplace's figures stayed on it until you navigated away and back. That was
true of every screen, not only Sales.

NO TOTAL ACROSS CURRENCIES
    "keep grouping by currency, don't sum across them"      -- the owner, 20 Aug
A subtotal per currency, and nothing anywhere that adds pounds to euros. That
needs a rate and a date, and one number hiding both is worse than none: it
cannot be checked.

IT ASKS AMAZON FOR NOTHING. Every figure comes from sales_daily, which the
background rotation already fills for every marketplace. Measured: 31-96 ms.
"""
import ast
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return io.open(os.path.join(HERE, *p), encoding="utf-8").read()


R = read("routes", "brandview_routes.py")
J = read("static", "js", "brandview.js")
S = read("static", "js", "sales.js")
SH = read("static", "js", "shell.js")
H = read("templates", "dashboard.html")
D = read("dashboard.py")

print("== the route exists and is registered ==")
tree = ast.parse(R)
routes = {d.args[0].value
          for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
          for d in n.decorator_list
          if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "route"
          and d.args and isinstance(d.args[0], ast.Constant)}
check("/brand/marketplaces is the one route", sorted(routes), ["/brand/marketplaces"])
truthy("dashboard.py registers it", "_brandview_routes.register(app" in D)
truthy("the page loads the script", "/static/js/brandview.js" in H)

print("\n== it asks Amazon for nothing ==")
falsy("no SP-API client is opened", "sp_api" in R or "Reports(" in R)
falsy("  nothing is fetched", "urllib" in R or "requests" in R)
truthy("it reads the stored table", "sales_daily" in R)
truthy("  through the same resolver the single-marketplace screen uses",
       "_sd.totals(" in R)
truthy("  with the same basis", 'basis="order"' in R)
truthy("  and the same VAT rate", "_sd.vat_rate_for(" in R)

print("\n== currencies are grouped and never summed ==")
truthy("there is a per-currency subtotal", "by_currency" in R)
falsy("there is no grand total", "grand_total" in R or "total_all" in R)
truthy("  and the reply says why", "exchange rate" in R)
truthy("the screen says it too", "no total across currencies" in J.lower())
falsy("  and the screen adds nothing across them",
      "byCurrency.reduce" in J or "sum(by_currency" in J)

print("\n== a subtotal of profit is only a profit if every SELLING row has one ==")
_blk = R.split("by_cur.setdefault")[1].split("for b in by_cur.values")[0]
truthy("an uncosted row makes it incomplete", 'b["profit_complete"] = False' in _blk)
truthy("  but a marketplace that sold nothing does not",
       'if float(r.get("ordered_sales") or 0) or int(r.get("units") or 0):' in _blk)
truthy("  and the screen says which it is", "not all costed" in J)
truthy("an empty currency gets no card at all",
       'if b["ordered_sales"] or b["units"]' in R)

print("\n== a quiet marketplace is folded away, not dropped ==")
truthy("the screen counts them", "with no sales in this period" in J)
truthy("  and can open them", "brandviewToggleQuiet" in J)
truthy("  because 'are we selling there yet' is a real question",
       "Poland" in J or "answer it wrongly" in J)
truthy("the route lists them rather than filtering them out",
       "quietly" in R or "never been connected" in R
       or "was never connected" in R)

print("\n== the Sales screen puts its own panels away ==")
truthy("it knows when All is chosen", "function salesIsAllMarkets" in S)
truthy("  hides the single-marketplace body", 'getElementById("sales_body")' in S)
truthy("  shows the per-marketplace view", 'getElementById("brandview")' in S)
truthy("  and loads it", "brandviewLoad()" in S)
truthy("the markup has both containers",
       'id="sales_body"' in H and 'id="brandview"' in H)
truthy("  and says why a chart cannot do it",
       "pounds and euros on one axis" in S)

print("\n== changing marketplace reloads the screen you are on ==")
_sw = SH.split("async function switchAccountMarket")[1].split("\nfunction ")[0]
truthy("the current section is re-opened", "navTo(CUR_SEC)" in _sw)
truthy("  through navTo, which owns the gate", "navTo is the one way in" in _sw)
truthy("  and listings is skipped, it has its own two loaders",
       'CUR_SEC !== "listings"' in _sw)
truthy("  guarded on both existing",
       'typeof CUR_SEC !== "undefined"' in _sw and 'typeof navTo === "function"' in _sw)

print("\n== '__all__' is never sent to a query as a country ==")
truthy("scopeq.js still drops it",
       'WS_MARKET !== "__all__"' in read("static", "js", "scopeq.js"))
from routes import scope as _S
check("and the resolver would not accept it for an account with a list",
      _S.marketplace(state={"active_marketplace": "__all__"},
                     account={"id": "x", "default_marketplace": "UK",
                              "marketplaces": ["UK", "DE"]}), "UK")

print("\n== against the real database ==")
try:
    import datetime as _dt
    from domain import sales_data as _sd
    cfg = json.load(io.open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    end = _dt.date.today() - _dt.timedelta(days=1)
    start = end - _dt.timedelta(days=29)
    shown = 0
    for a in cfg.get("accounts", []):
        wsid = str(a.get("id") or "")
        mkts = [str(m).upper() for m in (a.get("marketplaces") or [])]
        if not wsid or not mkts:
            continue
        per = {}
        for m in mkts:
            t = _sd.totals("config.json", wsid, m, start.isoformat(),
                           end.isoformat(), vat_rate=_sd.vat_rate_for(lambda: cfg, wsid),
                           basis="order")
            if t.get("ordered_sales"):
                per[m] = (t.get("currency") or "", t["ordered_sales"])
        if per and shown < 4:
            shown += 1
            print("  %-18s %s" % (wsid, ", ".join(
                "%s %s%s" % (k, v[0], v[1]) for k, v in per.items())))
        # The row for the DEFAULT marketplace must equal what the Sales screen
        # shows with that marketplace open -- same function, same arguments.
        d = str(a.get("default_marketplace") or "").upper()
        if d:
            one = _sd.totals("config.json", wsid, d, start.isoformat(),
                             end.isoformat(),
                             vat_rate=_sd.vat_rate_for(lambda: cfg, wsid),
                             basis="order")
            check("  %s/%s agrees with the single-marketplace figure" % (wsid, d),
                  one.get("ordered_sales"),
                  per.get(d, ("", one.get("ordered_sales")))[1])
except FileNotFoundError:
    print("  (no config.json on this machine)")
except Exception as e:
    fails.append("database probe")
    print("  FAIL database probe:", str(e)[:200])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
