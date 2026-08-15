"""Whose data a request is about must not depend on WHEN it is handled.

THE REPORT: "i opened nestwell goods and it was displaying right data of sales,
in the live sales graph for today but when i switched the account and came back
to nestwell goods, i was not able to see the same data, the data was totally
changed."

THE CAUSE: _state["active_account_id"] is ONE variable for the whole server
process, read at the moment a request is HANDLED. Switching workspace moves it.
So a read already in flight got answered for whichever account the global had
drifted to, and the browser painted that into the panel of the account still on
screen. Same class of bug as the listings leak in test_account_isolation_ui.py --
which was fixed for listings only, per screen, which is why it came back on Sales.

The rule being tested: the account travels WITH the request. A read resolves to
the account the page named; a write refuses when page and server disagree.
"""
import os, sys, json, tempfile, shutil

sys.path.insert(0, r"D:\AltaScraper")

from flask import Flask, request, jsonify
import domain.request_account as ra

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def check_true(label, got):
    check(label, bool(got), True)


app = Flask(__name__)

print("\n== the page can name its account, on a query or in a body ==")
with app.test_request_context("/sales/today?account_id=nestwell_goods&preset=7d"):
    check("read from the query string", ra.named(request), "nestwell_goods")
with app.test_request_context("/sales/sync", method="POST",
                              json={"account_id": "jack_uk", "marketplace": "UK"}):
    check("read from a JSON body", ra.named(request), "jack_uk")
with app.test_request_context("/sales/today?preset=7d"):
    check("absent is empty, not an error", ra.named(request), "")

print("\n== a READ answers for the account the page named ==")
STATE = {"active_account_id": "jack_uk"}          # the global has drifted here
ACCOUNTS = {"jack_uk": {"id": "jack_uk"}, "nestwell_goods": {"id": "nestwell_goods"}}
with app.test_request_context("/sales/today?account_id=nestwell_goods"):
    aid, acc = ra.for_read(request, STATE, get_account=ACCOUNTS.get)
    check("the PAGE wins over the global", aid, "nestwell_goods")
    check("and the account record is the page's one", (acc or {}).get("id"), "nestwell_goods")
    check("the global is not mutated by a read", STATE["active_account_id"], "jack_uk")

with app.test_request_context("/sales/today"):
    aid, acc = ra.for_read(request, STATE, get_account=ACCOUNTS.get)
    check("with nothing named, the global is the fallback", aid, "jack_uk")

print("\n== a WRITE refuses rather than guessing ==")
with app.test_request_context("/generate?account_id=nestwell_goods"):
    msg = ra.mismatch_for_write(request, {"active_account_id": "jack_uk"})
    check_true("a disagreement is refused", msg.startswith("ACCOUNT_MISMATCH"))
    check_true("and names BOTH accounts", "nestwell_goods" in msg and "jack_uk" in msg)
with app.test_request_context("/generate?account_id=jack_uk"):
    check("agreement is allowed through",
          ra.mismatch_for_write(request, {"active_account_id": "jack_uk"}), "")
with app.test_request_context("/generate"):
    msg = ra.mismatch_for_write(request, {"active_account_id": ""})
    check_true("no account anywhere is explained, not silently run", "No account" in msg)

print("\n== end to end: two accounts, one global, correct answers ==")
TMP = tempfile.mkdtemp(prefix="altareq_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [
    {"id": "jack_uk", "label": "Jack Reacherd", "marketplaces": ["UK"]},
    {"id": "nestwell_goods", "label": "Nestwell Goods", "marketplaces": ["UK"]},
]}, open(CFG, "w"))

app2 = Flask(__name__)
_state = {"active_account_id": "jack_uk", "active_marketplace": "UK"}

# The smallest stand-in for the real thing: one route that reports which
# workspace the SAME scope logic resolved, with the global pinned to jack_uk
# throughout -- so any answer of "nestwell_goods" can only have come from the
# request itself.
import routes.sales_routes as _sr


def _active_account():
    aid = _state.get("active_account_id")
    return {"id": aid} if aid else None


_sr.register(app2, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
             _active_account=_active_account, _state=_state)

c = app2.test_client()
r1 = c.get("/sales/availability?account_id=nestwell_goods&marketplace=UK")
r2 = c.get("/sales/availability?account_id=jack_uk&marketplace=UK")
w1 = (r1.get_json() or {}).get("workspace")
w2 = (r2.get_json() or {}).get("workspace")
check("a request naming nestwell is answered as nestwell", w1, "nestwell_goods")
check("a request naming jack is answered as jack", w2, "jack_uk")
check("the global never moved during either request",
      _state["active_account_id"], "jack_uk")

print("\n== the browser half: named on the way out, dropped on the way back ==")
js = open(os.path.join(r"D:\AltaScraper", "static", "js", "sales.js"),
          encoding="utf-8").read()
check_true("_sQuery attaches the account", "account_id=" in js and "_sAcct()" in js)
check_true("_sFetch exists as the one way this screen talks to the server",
           "async function _sFetch(" in js)
check_true("_sFetch drops a reply whose account has changed",
           "(_sAcct() === acct) ? j : null" in js)

# Every /sales/ call must go through it. A raw fetch here is a call site that
# travels with no account and paints whatever comes back -- the original bug.
import re
raw = [m for m in re.findall(r'await fetch\((.{0,40})', js)
       if "/sales/" in m or "_sQuery" in m]
check("no raw fetch left on any /sales/ call site", raw, [])

check_true("the generator's write guard uses the shared module",
           "request_account" in open(os.path.join(r"D:\AltaScraper", "routes",
                                                  "listing_routes.py"),
                                     encoding="utf-8").read())

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
