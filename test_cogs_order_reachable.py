"""Correcting ONE order's cost has to be reachable from the browser.

    COGS defect 2 of the three deferred on 18 Aug 2026.

    "my typed cogs win but it should be only for that order not all time frames
     and all orders"

/cogs/order has done exactly that since it was written: it writes onto the order
line and marks it 'manual-order', which nothing later overwrites. It was
finished, correct, tested -- and NOTHING IN THE BROWSER CALLED IT. An endpoint
with no way to reach it is a feature nobody has. The order panel's own note used
to end by sending the reader to a spreadsheet to fix the number they were
looking at.

THREE THINGS THIS GUARDS, each of which silently corrupts a different account's
figures if it regresses:

  the sku      set_for_order WITHOUT a sku updates every line of the order to
               the same figure. Right for the single-item orders that are most
               of them; wrong for a two-item order where the products cost
               different amounts, and wrong invisibly.

  per unit     order_lines.cogs is the UNIT cost. The Cost column in the panel
               shows the line -- unit x quantity. Typing the line total into a
               per-unit box on a 3-unit order overstates the cost threefold.

  the account  Orders can be listed across every account. The row's own
               account_id and marketplace are sent, not the open workspace's,
               or a correction lands on a different limited company's order.
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


JS = open(os.path.join(HERE, "static", "js", "orders.js"), encoding="utf-8").read()
RT = open(os.path.join(HERE, "routes", "cogs_mode_routes.py"), encoding="utf-8").read()

# Comments quote the user and describe the bug, so matching them proves nothing.
CODE = "\n".join(l.split("//")[0] for l in JS.splitlines()
                 if not l.strip().startswith(("*", "/*", "//")))

print("== the endpoint is reached from the order panel ==")
truthy("something in the browser calls /cogs/order", '"/cogs/order"' in CODE)
truthy("  from orders.js", "ordSetOrderCogs" in CODE)
truthy("  and the button is drawn", "onclick=\"ordSetOrderCogs(" in CODE
       or "onclick=\\\"ordSetOrderCogs(" in CODE or "ordSetOrderCogs(' +" in CODE)

print("\n== one input per LINE, each carrying its own sku ==")
_fn = CODE.split("function _ordBreakdownHtml")[1].split("\nasync function")[0]
truthy("the control is drawn inside the per-line loop", "bd.lines.forEach" in _fn)
truthy("  and passes that line's sku", "l.sku" in _fn and "ordSetOrderCogs(" in _fn)
truthy("a line with no sku on a multi-line order gets no control",
       "if(!l.sku && bd.lines.length > 1) return;" in _fn)
truthy("the sku reaches the request", "sku: sku" in CODE)
truthy("and the route aims the write with it", "sku=b.get(\"sku\")" in RT)

print("\n== the figure is per UNIT, and the box says so ==")
truthy("the prompt says per unit", "per unit" in JS)
truthy("  and the placeholder is the unit cost, not the line",
       "l.unit_cost" in _fn)
truthy("  falling back to line / qty when there is no unit_cost",
       "Number(l.cogs) / Number(l.qty)" in _fn)

print("\n== the ROW's account, not whichever workspace is open ==")
_save = CODE.split("async function ordSetOrderCogs")[1].split("\nfunction ")[0]
truthy("the save takes an account and a marketplace",
       "ordSetOrderCogs(orderId, sku, inputId, accountId, marketplace)" in CODE)
truthy("  and sends account_id -- the key request_account.named() reads",
       "account_id: accountId" in _save)
falsy("  not 'account', which that function does not look at",
      re.search(r"\baccount:\s*accountId", _save))
truthy("named() really does read account_id",
       'get("account_id")' in open(os.path.join(HERE, "domain",
                                                "request_account.py"),
                                   encoding="utf-8").read())
truthy("the panel passes the row's own account down",
       "r.account_id, r.marketplace" in CODE)
truthy("  and the row's own order id, not the detail payload's",
       "_ordBreakdownHtml(d.breakdown, o.currency, r.order_id," in CODE)

print("\n== after saving, nothing on screen is left stale ==")
# The row's profit, margin and ROI are all worked out from this cost. Redrawing
# only the panel leaves the list showing the profit from before the correction.
truthy("the cached detail is dropped", "delete ORD.details[orderId]" in _save)
truthy("the list is reloaded too", "await ordersLoad()" in _save)
truthy("  and the order is reopened", "ordersToggle(orderId" in _save)
falsy("it does not call a function that does not exist",
      "ordToggle(" in CODE.replace("ordersToggle(", ""))

print("\n== a blank box clears the cost rather than writing a zero ==")
truthy("blank is sent as null", 'raw === "" ? null : raw' in _save)
truthy("  and the route turns null into unknown", "cost = None" in RT)
truthy("  the panel explains that", "back to" in _save and "not known" in JS)
falsy("nothing substitutes 0", re.search(r"cost:\s*[^,]*\|\|\s*0", _save))

print("\n== a typo is caught before it is sent ==")
truthy("non-numeric input is refused in the browser", "isFinite(Number(raw))" in _save)
truthy("  and again by the route", "cost must be a number" in RT)
truthy("  and a negative cost is refused", "cost cannot be negative" in RT)

print("\n== the renderer actually runs, with the shapes it will be given ==")
# node --check only parses. The stray-token bug parsed fine and threw at runtime.
import json
import subprocess
import tempfile

probe = r"""
const fs=require("fs"),vm=require("vm");
globalThis.document={getElementById:()=>({value:""}),addEventListener(){}};
globalThis.addEventListener=function(){}; globalThis.window=globalThis;
vm.runInThisContext(fs.readFileSync("static/js/orders.js","utf8"),{filename:"orders.js"});
vm.runInThisContext(fs.readFileSync("static/js/users.js","utf8"),{filename:"users.js"});
const one={lines:[{sku:"S1",title:"t",qty:1,revenue:29.99,fee:4.5,cogs:15.1,unit_cost:15.1,profit:10.39}],
  totals:{revenue:29.99,fees:4.5,cogs:15.1,cogs_complete:true,profit:10.39,fee_rate:.15,fees_basis:"actual"}};
const two={lines:[{sku:"A",title:"a",qty:3,revenue:30,fee:4,cogs:9,unit_cost:3,profit:17},
                  {sku:"B",title:"b",qty:1,revenue:10,fee:1,cogs:null,unit_cost:null,profit:null}],
  totals:{revenue:40,fees:5,cogs:null,cogs_complete:false,profit:null,uncosted_lines:1,fee_rate:.15}};
const noSku={lines:[{sku:"",title:"a",qty:1,revenue:1,fee:0,cogs:null,profit:null},
                    {sku:"",title:"b",qty:1,revenue:1,fee:0,cogs:null,profit:null}],totals:{}};
const n=h=>(String(h).match(/ordSetOrderCogs\(/g)||[]).length;
const h1=_ordBreakdownHtml(one,"GBP","o1","jack_uk","M1");
const h2=_ordBreakdownHtml(two,"GBP","o1","jack_uk","M1");
console.log(JSON.stringify({
  one:n(h1), two:n(h2), noId:n(_ordBreakdownHtml(one,"GBP","")),
  noSku:n(_ordBreakdownHtml(noSku,"GBP","o1","a","M1")),
  unitPlaceholder:(h2.match(/placeholder="([\d.]+)"/)||[])[1],
  quoted:/ordSetOrderCogs\('o1','a&quot;b'/.test(
    _ordBreakdownHtml({lines:[{sku:'a"b',title:"x",qty:1,revenue:1,fee:0,cogs:1,unit_cost:1,profit:0}],
                       totals:{}},"GBP","o1","a","M1")),
}));
"""
try:
    fd, path = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, probe.encode("utf-8"))
    os.close(fd)
    out = subprocess.run(["node", path], capture_output=True, text=True, cwd=HERE)
    os.unlink(path)
    if out.returncode != 0:
        fails.append("the renderer threw")
        print("  FAIL the renderer threw:", (out.stderr or "")[:300])
    else:
        got = json.loads(out.stdout.strip().splitlines()[-1])
        check("a one-line order gets one Save", got["one"], 1)
        check("a two-line order gets two", got["two"], 2)
        check("no order id -> no control at all", got["noId"], 0)
        check("two skuless lines -> none, rather than one that hits both",
              got["noSku"], 0)
        check("the placeholder on a 3-unit line is the UNIT cost",
              got["unitPlaceholder"], "3.00")
        truthy("a quote in a sku cannot break out of the onclick", got["quoted"])
except FileNotFoundError:
    print("  (node not on this machine -- renderer not exercised)")
except Exception as e:
    fails.append("renderer probe")
    print("  FAIL renderer probe:", str(e)[:200])

print("\n== the route still exists and is a POST ==")
tree = ast.parse(RT)
routes = {d.args[0].value
          for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
          for d in n.decorator_list
          if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "route"
          and d.args and isinstance(d.args[0], ast.Constant)}
truthy("/cogs/order is registered", "/cogs/order" in routes)
truthy("  as POST only", 'methods=["POST"]' in RT.split('"/cogs/order"')[1][:60])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
