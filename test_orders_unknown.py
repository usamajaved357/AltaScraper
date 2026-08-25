"""Nothing counted is not nothing sold, and a repr is not an explanation.

FOUND BY LOOKING AT THE ORDERS SCREEN. It showed, at the same time:

    jack_uk - [{'code': 'Unauthorized', 'message': 'Access to requested
    resource is denied.', 'details': ''}]

    Orders  0      last 30 days
    Units   0      0 per order
    No orders in the last 30 days. Accounts asked: jack_uk.

TWO SEPARATE FAULTS IN ONE PANEL.

  A FAILURE RENDERED AS A MEASUREMENT. Amazon declined to answer, and the screen
  reported nought orders and nought units, confidently, with no hedge. A count
  is only a count when somebody was able to count. This is the same defect as
  the weekly pack's silent zeroes and the A+ index's silent emptiness -- unknown
  is not zero, and the app says so everywhere else.

  A PYTHON REPR SHOWN TO A PERSON. A list of dictionaries, printed at somebody
  who wants to know why their orders are missing. CLAUDE.md Rule 5: plain
  English first, every time.

The wording lives in domain/marketplace_health, which already decides what these
errors MEAN -- looks_permanent and PERMANENT_MARKERS have judged Unauthorized,
InvalidInput and their kin since the refresher's backoff was written. Putting
the sentence anywhere else would be a second opinion about the same string
(Rule 12).
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from domain import marketplace_health as mh

print("=== Amazon's refusals, said in English ===")
RAW = ("[{'code': 'Unauthorized', 'message': 'Access to requested resource "
       "is denied.', 'details': ''}]")
said = mh.explain(RAW)
truthy("the repr does not survive into the sentence", "{'code'" not in said)
truthy("  it says Amazon refused", "refused" in said)
# IT NAMES THE CHECK, NOT ONE PERMISSION. This required the words "Seller
# Central", which is where the old sentence sent people to grant "the
# permission" -- singular. Measured on jack_uk/UK: the refresh token works and
# marketplace participation, Catalog Items, Product Pricing and Product
# Definitions all return 403 [ROLE]. Naming one has somebody fix a fraction and
# meet the next refusal. Diagnose SP-API checks each in turn and lists them.
truthy("  and points at the check that names what is missing",
       "Diagnose SP-API" in said)
truthy("  saying there is usually more than one", "more than one" in said)
# THE CAUSE DECIDES THE ADVICE. Rate limiting is not a permission problem and
# telling somebody to go and change a setting for it sends them to the wrong
# place entirely.
truthy("rate limiting is not blamed on a permission",
       "Seller Central" not in mh.explain("QuotaExceeded"))
truthy("  and says it will pass", "shortly" in mh.explain("QuotaExceeded"))
truthy("a timeout says nothing is wrong with the account",
       "Nothing is wrong" in mh.explain("read timed out"))
truthy("InvalidInput is about the marketplace, not the login",
       "registered to sell" in mh.explain("InvalidInput"))
# NOT GUESSED AT. A confident wrong explanation sends somebody to fix the wrong
# thing, so an unrecognised error is handed back as it came.
check("an error it does not know is passed through unchanged",
      mh.explain("something nobody has seen before"),
      "something nobody has seen before")
check("no error is no sentence", mh.explain(""), "")
check("  and None is safe", mh.explain(None), "")
# The classification this borrows from must still agree with it.
truthy("it agrees with looks_permanent about Unauthorized",
       mh.looks_permanent(RAW))
truthy("  and about a timeout not being permanent",
       not mh.looks_permanent("read timed out"))

print("\n=== the route sends the sentence AND keeps the raw text ===")
RT = open("routes/orders_routes.py", encoding="utf-8").read()
truthy("it explains through the shared helper", "_mh.explain(e)" in RT)
truthy("  imported, not reimplemented",
       "from domain import marketplace_health as _mh" in RT)
truthy("  and Amazon's own words are still sent", '"raw": str(e)[:200]' in RT)
truthy("  nothing builds its own wording here",
       "not authorised" not in RT and "Seller Central" not in RT)

print("\n=== the screen: a refused account is not a quiet zero ===")
PROBE = r"""
const fs = require("fs"), vm = require("vm");
globalThis.window = globalThis;
globalThis.addEventListener = function(){};
let HTML = "";
globalThis.document = {
  getElementById: () => ({ set innerHTML(v){ HTML = v; },
                           get innerHTML(){ return HTML; } }),
  querySelectorAll: () => [], addEventListener(){},
  createElement: () => ({innerHTML:"", querySelector: () => null})
};
globalThis.uiStats = function(cards){
  return "<STATS>" + JSON.stringify(cards) + "</STATS>";
};
globalThis.toast = function(){};
// Helpers orders.js shares with the rest of the page. Stubbed rather than
// loading every file, because what is under test is which of three stories the
// panel tells -- not how a row is drawn.
globalThis.jsArg = s => "'" + String(s == null ? "" : s).replace(/'/g, "\\'") + "'";
globalThis.esc = s => String(s == null ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
globalThis.CUR_SYMBOL = "£";
globalThis.curSymbol = () => "£";
vm.runInThisContext(fs.readFileSync("static/js/orders.js","utf8"),
                    {filename:"orders.js"});

const run = function(meta, rows){
  // ordersRender takes no argument and reads ORD.meta and ORD.summary, which
  // are two separate fields -- passing the summary inside meta left it reading
  // an empty one, and the assertion failed on the harness rather than the code.
  ORD.rows = rows; ORD.days = 30; ORD.q = "";
  ORD.meta = meta; ORD.summary = meta.summary || {};
  HTML = "";
  ordersRender();
  const m = /<STATS>([\s\S]*?)<\/STATS>/.exec(HTML);
  return {html: HTML, cards: m ? JSON.parse(m[1]) : null};
};

// 1. Every account asked refused.
// The sentence is a FIXTURE here, not the thing under test -- this file is
// about "unknown is not zero". It is kept in step with the real one anyway
// (marketplace_health.DENIED), because a fixture quoting wording the app no
// longer uses is how a stale copy survives a rename.
const denied = run({accounts_asked: ["jack_uk"],
  errors: [{account: "jack_uk",
            error: "Amazon refused: this app is not authorised for that. Press "
                 + "\"Diagnose SP-API\" on the listings page — it checks each "
                 + "Amazon permission in turn and lists the ones that are "
                 + "missing, which is usually more than one.",
            raw: "[{'code': 'Unauthorized'}]"}],
  summary: {orders: 0, units: 0, revenue_by_currency: {}}}, []);

// 2. Nobody refused, and there genuinely were none.
const empty = run({accounts_asked: ["jack_uk"], errors: [],
  summary: {orders: 0, units: 0, revenue_by_currency: {}}}, []);

// 3. Two accounts, one refused, the other had orders.
const partial = run({accounts_asked: ["jack_uk", "nestwell_goods"],
  errors: [{account: "nestwell_goods", error: "Amazon refused: ...", raw: "x"}],
  summary: {orders: 4, units: 6, revenue_by_currency: {}}},
  [{order_id: "1", profit: null}]);

const card = function(r, label){
  return (r.cards || []).filter(c => c.label === label)[0] || {};
};
console.log(JSON.stringify({
  deniedOrders:  card(denied,  "Orders").value,
  deniedNote:    card(denied,  "Orders").note,
  deniedUnits:   card(denied,  "Units").value,
  deniedSaysNotKnown: /Not known/.test(denied.html),
  deniedNotNoOrders:  !/No orders in the last/.test(denied.html),
  deniedSaysWhy: /not because/.test(denied.html),
  deniedShowsRaw:/Amazon said/.test(denied.html),

  emptyOrders:   card(empty, "Orders").value,
  emptyNote:     card(empty, "Orders").note,
  emptySaysNone: /No orders in the last 30 days/.test(empty.html),
  emptyNoHedge:  !/Not known/.test(empty.html),

  partialOrders: card(partial, "Orders").value,
  partialNote:   card(partial, "Orders").note
}));
"""
try:
    fd, p = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, PROBE.encode("utf-8"))
    os.close(fd)
    # encoding NAMED. Without it Windows decodes node's stdout as cp1252 and an
    # em dash comes back as "â€”", failing an assertion about a character the
    # code got right.
    r = subprocess.run(["node", p], capture_output=True, text=True, cwd=HERE,
                       encoding="utf-8")
    os.unlink(p)
    if r.returncode != 0:
        FAILS.append("orders.js threw")
        print("  FAIL orders.js threw:", (r.stderr or "")[:400])
    else:
        g = json.loads(r.stdout.strip().splitlines()[-1])
        # THE HEADLINE FAULT. "0" was a claim nobody was entitled to make.
        check("a refused account shows an em dash, not 0", g["deniedOrders"], "—")
        check("  and says why", g["deniedNote"], "not known — Amazon refused")
        check("  units likewise", g["deniedUnits"], "—")
        truthy("  the panel says the answer is not known",
               g["deniedSaysNotKnown"])
        truthy("  and does NOT say there were no orders",
               g["deniedNotNoOrders"])
        truthy("  it names the difference out loud", g["deniedSaysWhy"])
        truthy("  with Amazon's own words kept underneath", g["deniedShowsRaw"])

        # AND THE ORDINARY CASE IS UNCHANGED. A real quiet month must still read
        # as a real quiet month -- hedging that would be the same fault
        # reversed.
        check("a genuinely empty period still shows 0", g["emptyOrders"], 0)
        check("  with its ordinary note", g["emptyNote"], "last 30 days")
        truthy("  and still says there were none", g["emptySaysNone"])
        truthy("  without hedging", g["emptyNoHedge"])

        # A PARTIAL TOTAL IS NOT THE TOTAL.
        check("one account of two refusing keeps the count",
              g["partialOrders"], 4)
        truthy("  but marks it partial",
               "did not answer" in (g["partialNote"] or ""))
except FileNotFoundError:
    print("  (node is not on this machine -- the screen was not exercised)")

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
