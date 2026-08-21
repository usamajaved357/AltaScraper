"""The "By product" table must say how much of the period it is showing.

MEASURED 21 Aug 2026, last thirty days, comparing the headline figure on the
Sales screen with the sum of its own per-product rows:

    jack_uk           headline GBP  285.66   product rows GBP  162.76   57.0%
    nestwell_goods    headline GBP  946.67   product rows GBP  149.95   15.8%
    selvora_limited   headline GBP 4145.60   product rows GBP    0.00    0.0%

Nestwell's product table showed a sixth of the business. Selvora's showed none
of it, under the words "No per-product sales in this period yet -- press Sync to
pull them from Amazon", which is wrong twice: sales HAVE been synced (that is
where the 4145.60 came from), and pressing Sync will not necessarily fix it
today.

IT IS NOT A FAULT, AND THAT IS THE POINT. Two feeds fill sales_daily:

    the ORDER feed     live_reconcile writes the account total for a day as soon
                       as the orders are known. It does not know which product,
                       because an order row carries no ASIN.

    the REPORT         Amazon's Sales & Traffic report carries the per-ASIN
                       block, and only when asked for ONE DAY at a time -- over
                       a range Amazon aggregates the ASIN block and drops the
                       dates (see domain/sales_fetch.py). It is paced against a
                       quota of roughly one report a minute, across six accounts
                       and eleven marketplaces.

So a day can have a true total and no product detail yet. Every day measured
with money and no product rows had report_delivered = False -- 2 for jack_uk,
9 for nestwell, 19 for selvora.

The defect was that the screen did not SAY so. A table headed "By product" that
silently omits 84% of the money answers "which products sold" with a number
nobody can act on, and there is nothing on screen to show it is a part-answer.
"""
import io
import json
import os
import subprocess
import sys
import tempfile

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


from domain import sales_data as _sd

print("== the coverage figure exists and is arithmetic, not a guess ==")
truthy("there is one function that answers it",
       hasattr(_sd, "breakdown_coverage"))
SRC = read("domain", "sales_data.py")
_fn = SRC.split("def breakdown_coverage")[1].split("\ndef ")[0]
truthy("it reads the account total row", "asin='*'" in _fn)
truthy("  and the per-ASIN rows", "asin<>'*'" in _fn)
truthy("  from the same table and the same window", "sales_daily" in _fn)
truthy("uncovered can never go negative", "max(0.0, total - covered)" in _fn)
truthy("  and why is recorded",
       "revise a day upwards" in _fn)
truthy("a day of genuinely zero sales is not counted as a gap", "t > 0" in _fn)

print("\n== against the real database ==")
try:
    import datetime as _dt
    end = _dt.date.today() - _dt.timedelta(days=1)
    start = end - _dt.timedelta(days=29)
    from data import db as _db
    conn = _db.get_db()
    pairs = conn.execute(
        "SELECT DISTINCT workspace_id, marketplace FROM sales_daily "
        "WHERE date>=? AND date<=?", (start.isoformat(), end.isoformat())).fetchall()
    shown = 0
    for p in pairs:
        c = _sd.breakdown_coverage("config.json", p["workspace_id"],
                                   p["marketplace"], start.isoformat(),
                                   end.isoformat())
        # The arithmetic must hold for every pair, whatever the numbers are.
        if c["total"] >= c["covered"]:
            ok = abs((c["covered"] + c["uncovered"]) - c["total"]) < 0.011
        else:
            ok = c["uncovered"] == 0.0        # the report revised upwards
        if not ok:
            fails.append("coverage arithmetic for %s::%s"
                         % (p["workspace_id"], p["marketplace"]))
            print("  FAIL %s::%s %r" % (p["workspace_id"], p["marketplace"], c))
        elif shown < 8 and c["total"] > 0:
            shown += 1
            print("  %-20s %-3s total=%-9s covered=%-9s uncovered=%-9s %s%% "
                  "gap-days=%s" % (p["workspace_id"], p["marketplace"],
                                   c["total"], c["covered"], c["uncovered"],
                                   c["pct"], c["days_without_products"]))
    check("covered + uncovered = total, on every pair in the database",
          [f for f in fails if f.startswith("coverage arithmetic")], [])
    print("     (%d account/marketplace pairs checked)" % len(pairs))
    # And a pair with no rows at all must not divide by zero.
    z = _sd.breakdown_coverage("config.json", "__nobody__", "ZZ",
                               start.isoformat(), end.isoformat())
    check("an account with nothing gives zeros, not an error",
          (z["total"], z["covered"], z["uncovered"], z["pct"]), (0.0, 0.0, 0.0, None))
except Exception as e:
    fails.append("database probe")
    print("  FAIL database probe:", str(e)[:200])

print("\n== the route hands the figures over, and does not format money ==")
R = read("routes", "sales_routes.py")
_bd = R.split("def sales_breakdown")[1].split("\n    @app.route")[0]
truthy("it asks for the coverage", "_sd.breakdown_coverage(" in _bd)
truthy("  and returns it", '"coverage": cov' in _bd)
falsy("  and does not build a money sentence of its own",
      "_money(" in _bd)
truthy("  because the one formatter is on the screen",
       "one money formatter lives" in _bd or "rule 12" in _bd)
truthy("the old 'press Sync' line is kept for a period that really is empty",
       "No per-product sales in this period yet" in _bd)
truthy("  but a period with money gets the true reason instead",
       "has not delivered a product-level report" in _bd)
truthy("  which names how many days", 'cov["days_without_products"]' in _bd)

print("\n== the screen says it, in the currency it is already using ==")
J = read("static", "js", "sales.js")
_draw = J.split("function salesDrawBreakdown")[1].split("\nfunction ")[0]
truthy("the warning is drawn from the coverage", "m.coverage" in _draw)
truthy("  only when something is missing", "cov.uncovered > 0.01" in _draw)
truthy("  using the shared money formatter", "curMoney" in _draw)
truthy("  guarded, so a missing formatter cannot blank the table",
       'typeof curMoney === "function"' in _draw)
truthy("  and it says the totals above DO include it",
       "totals at the top of the screen include it" in _draw)

print("\n== and it renders, with the shapes it will be given ==")
probe = r"""
const fs=require("fs"),vm=require("vm");
const el=()=>({innerHTML:"",value:"",style:{},classList:{add(){},remove(){},toggle(){},contains(){return false}},
  appendChild(){},querySelector(){return null},querySelectorAll(){return[]},addEventListener(){},
  getBoundingClientRect(){return{width:0,height:0,top:0,left:0}},offsetHeight:0});
const store={};
globalThis.document={getElementById:id=>(store[id]=store[id]||el()),querySelector:()=>el(),
  querySelectorAll:()=>[],createElement:()=>el(),addEventListener(){},body:el(),head:el()};
globalThis.window=globalThis; globalThis.addEventListener=()=>{};
globalThis.localStorage={getItem:()=>null,setItem(){},removeItem(){}};
globalThis.location={href:"http://x/",search:"",hash:""};
globalThis.fetch=()=>Promise.resolve({json:()=>Promise.resolve({ok:true})});
globalThis.Chart=function(){return{destroy(){},update(){}}};
globalThis.setTimeout=setTimeout;
for (const f of ["money.js","users.js","listings.js","sales.js"])
  { try{ vm.runInThisContext(fs.readFileSync("static/js/"+f,"utf8"),{filename:f}); }catch(e){} }
const row={k:"B0AAA",title:"A thing",units:3,revenue:149.95,avg_price:49.98,orders:3,sessions:20,conversion:15};
function draw(cov, rows){
  SALES_BD.rows = rows===undefined?[row]:rows;
  SALES_BD.meta = {ok:true,currency:"GBP",rows:SALES_BD.rows,coverage:cov,
                   note:"Amazon has not delivered a product-level report for any of the 19 days"};
  const host = document.getElementById("sales_breakdown");
  host.innerHTML="";
  salesDrawBreakdown();
  return host.innerHTML;
}
const partial = draw({total:946.67,covered:149.95,uncovered:796.72,pct:15.8,days_without_products:9});
const full    = draw({total:149.95,covered:149.95,uncovered:0,pct:100,days_without_products:0});
const none    = draw({total:4145.6,covered:0,uncovered:4145.6,pct:0,days_without_products:19}, []);
const noCov   = draw(undefined);
console.log(JSON.stringify({
  partial: /These products account for/.test(partial),
  hasMoney: /£149\.95/.test(partial) && /£946\.67/.test(partial) && /£796\.72/.test(partial),
  hasPct: /15\.8%/.test(partial),
  hasDays: /9 days/.test(partial),
  full: /These products account for/.test(full),
  noRowsShowsNote: /Amazon has not delivered/.test(none),
  noCoverageIsSafe: noCov.length > 0 && !/These products account for/.test(noCov),
  tableStillDrawn: /<table/.test(partial),
}));
"""
try:
    fd, path = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, probe.encode("utf-8"))
    os.close(fd)
    out = subprocess.run(["node", path], capture_output=True, text=True, cwd=HERE,
                         timeout=120)
    os.unlink(path)
    if out.returncode != 0:
        fails.append("the breakdown renderer threw")
        print("  FAIL:", (out.stderr or "")[:400])
    else:
        g = json.loads(out.stdout.strip().splitlines()[-1])
        truthy("a part-covered period shows the warning", g["partial"])
        truthy("  with all three figures, in the right currency", g["hasMoney"])
        truthy("  the share", g["hasPct"])
        truthy("  and how many days are missing", g["hasDays"])
        truthy("  and the table is still drawn under it", g["tableStillDrawn"])
        falsy("a fully covered period says nothing at all", g["full"])
        truthy("no rows at all shows the reason", g["noRowsShowsNote"])
        truthy("an old reply with no coverage block does not break the table",
               g["noCoverageIsSafe"])
except FileNotFoundError:
    print("  (node not on this machine -- not exercised)")
except Exception as e:
    fails.append("render probe")
    print("  FAIL render probe:", str(e)[:200])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
