"""A workspace with no Amazon account shows what the app looks like WITH data.

    "I have added the test user account for anyone to review but obviously there
     is no data available in the workspace i am using the headbanger workspace
     forexample. so when no data is available i want to use the placeholder data
     which is not real but the user has an idea how the app looks like when it
     has data. use this logic for any workspace which do not have a brand or
     account connected like miles lubricants and headbanger lures."

THE ONE RULE THIS FILE GUARDS:

    a placeholder must never be mistakable for a real figure.

Every assertion below is ultimately about that. A sample must be flagged in the
payload, announced on screen, visually distinct, never written anywhere, and
never shown to an account that has real data of its own -- because the failure
mode is not "the demo looks bad", it is somebody acting on an invented number.

WHO QUALIFIES, and it is not "the screen is empty". A connected account having a
quiet week gets its real, empty answer. Only a workspace that CANNOT have data
-- no Amazon account of its own -- sees samples. Measured against the live
config: headbanger_lures (no credentials at all) and miles_lubricants (borrows
Sheelady's app) qualify; jack_uk, sheelady_us, selvora_limited and
nestwell_goods do not.

AND IT SPEAKS THE READER'S LANGUAGE. The rows are built in the shape /rows_all
RETURNS -- flat, lower-case, sku/title/asin/price -- not the shape data/store.py
TAKES ("SKU", "Title", "Our Price (GBP)"). Built in the store's shape they
arrived intact and the grid hid all eight behind "8 empty rows hidden", because
isEmptyRow() asks for r.sku and got undefined.
"""
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
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return io.open(os.path.join(HERE, *p), encoding="utf-8").read()


from domain import demo_data as dd

J = read("static", "js", "demobanner.js")
C = read("static", "css", "dashboard.css")
S = read("static", "js", "submit.js")
LR = read("routes", "listing_routes.py")
DAY = "2026-08-21"          # passed IN -- the module never reads a clock

CONNECTED = {"id": "real", "label": "Real Co", "refresh_token": "Atzr|REALTOKEN",
             "lwa_app_id": "amzn1.application-oa2-client.x",
             "lwa_client_secret": "secret", "seller_id": "A1REAL"}
EMPTY = {"id": "headbanger_lures", "label": "Headbanger Lures"}

print("== only a workspace that CANNOT have data gets samples ==")
truthy("an account with no credentials qualifies", dd.is_demo_workspace(EMPTY))
falsy("  an empty dict is not automatically real", not dd.is_demo_workspace({}))
# The gate is domain/accounts.has_own_creds -- the same function every
# seller-scoped route already uses. Not a second opinion (rule 12).
truthy("it asks accounts.has_own_creds", "has_own_creds" in
       read("domain", "demo_data.py"))
falsy("  and has no credential rule of its own",
      "refresh_token" in read("domain", "demo_data.py"))

print("\n== against the real config, which accounts qualify ==")
try:
    from domain import accounts as _acc
    cfg = json.load(io.open("config.json", encoding="utf-8"))
    accs = _acc.load_accounts(cfg, "config.json", persist=False)
    demo = sorted(a.get("id") for a in accs if dd.is_demo_workspace(a))
    real = sorted(a.get("id") for a in accs if not dd.is_demo_workspace(a))
    print("     samples: %s" % demo)
    print("     real:    %s" % real)
    truthy("headbanger_lures gets samples", "headbanger_lures" in demo)
    truthy("miles_lubricants gets samples", "miles_lubricants" in demo)
    for aid in ("jack_uk", "sheelady_us", "selvora_limited", "nestwell_goods"):
        falsy("  %s never does" % aid, aid in demo)
except FileNotFoundError:
    print("     (no config.json here -- the rest still stands)")

print("\n== maybe() is the only gate, and it fails safe ==")
check("a connected account gets nothing",
      dd.maybe(CONNECTED, "listings", workspace_id="real"), None)
truthy("an unconnected one gets a payload",
       dd.maybe(EMPTY, "listings", workspace_id="headbanger_lures"))
check("an unknown kind gets nothing",
      dd.maybe(EMPTY, "not_a_screen", workspace_id="x"), None)
# A route that cannot tell must fall through to the real answer, never invent.
check("a broken call gets nothing, not a guess",
      dd.maybe(EMPTY, "sales", workspace_id="x", end_day="not-a-date"), None)

print("\n== every payload says what it is ==")
for kind, kw in (("listings", {"workspace_id": "hb"}),
                 ("sales", {"workspace_id": "hb", "end_day": DAY}),
                 ("sales_summary", {"workspace_id": "hb", "end_day": DAY}),
                 ("sales_series", {"workspace_id": "hb", "end_day": DAY}),
                 ("inventory", {"workspace_id": "hb"}),
                 ("returns", {"workspace_id": "hb", "end_day": DAY}),
                 ("orders", {"workspace_id": "hb", "end_day": DAY})):
    p = dd.maybe(EMPTY, kind, **kw)
    truthy("%-14s is flagged demo" % kind, p and p.get("demo") is True)
    truthy("  %-12s says why" % "", p and len(p.get("demo_reason") or "") > 30)

print("\n== the numbers agree with each other ==")
s = dd.sales(EMPTY, "hb", DAY, 30)
t = s["totals"]
check("thirty days of them", len(s["daily"]), 30)
check("  ending on the day asked for", s["end"], DAY)
check("  starting 29 days before", s["start"], "2026-07-23")
pu = sum(p["units"] for p in s["products"])
ps = round(sum(p["ordered_sales"] for p in s["products"]), 2)
check("the product rows add up to the headline units", pu, t["units"])
check("  and to the headline sales", ps, t["ordered_sales"])
# A reviewer who adds a column up and gets a different number learns the app
# cannot count, which is the opposite of what a demo is for.
truthy("the daily series adds up too",
       sum(d["units"] for d in s["daily"]) == t["units"])
truthy("average selling price is consistent",
       abs(t["avg_selling_price"] - t["ordered_sales"] / t["units"]) < 0.01)

print("\n== the same workspace always sees the same figures ==")
check("twice in a row", dd.sales(EMPTY, "hb", DAY, 30)["totals"], t)
truthy("a different workspace differs",
       dd.sales(EMPTY, "miles_lubricants", DAY, 30)["totals"]["units"]
       != t["units"])
# No clock: a module that read today's date would make this file's answers
# depend on when it runs.
falsy("it never reads the clock",
      "date.today()" in read("domain", "demo_data.py")
      or "datetime.now()" in read("domain", "demo_data.py"))

print("\n== the rows are in the shape the SCREEN reads ==")
rows = dd.listings(EMPTY, "hb")["rows"]
check("eight of them", len(rows), 8)
for k in ("sku", "title", "asin", "price", "status", "product_type"):
    truthy("every row has %-14s" % k, all(k in r for r in rows))
falsy("  and none uses the store's header names",
      any("SKU" in r or "Our Price (GBP)" in r for r in rows))
# isEmptyRow() in miles_template.js is what hid them; this is that rule.
_empty = [r for r in rows if not (str(r.get("sku") or "").strip()
                                  or str(r.get("title") or "").strip())]
check("none would be hidden as an empty row", len(_empty), 0)
truthy("the trap is written down", "8 empty rows hidden" in
       read("domain", "demo_data.py"))
truthy("they are obviously not real products",
       all("Demo" in r["title"] for r in rows))
truthy("  and their ASINs say so too",
       all(r["asin"].startswith("B0DEMO") for r in rows))

print("\n== the demo shows the app DOING something ==")
inv = dd.inventory(EMPTY, "hb")["rows"]
truthy("something is out of stock",
       any(r["status"] == "OUT OF STOCK" for r in inv))
truthy("  and something is low", any(r["status"] == "LOW" for r in inv))
st = {r["Status"] if "Status" in r else r["status"] for r in rows}
truthy("the listings are not all in one state", len(st) >= 3)
ret = dd.returns(EMPTY, "hb", DAY, 60)
truthy("returns have a reason mix", len(ret["reasons"]) >= 4)
truthy("  grouped into causes", len(ret["natures"]) >= 2)
# Returns from a workspace with no FBA file must not claim a disposition.
check("nothing is graded, because nothing was received",
      ret["sellable_pct"], None)
falsy("  and it says so", ret["has_disposition"])

print("\n== nothing is ever written ==")
src = read("domain", "demo_data.py")
# CODE ONLY. The comments explain the store's upsert_row and why the rows are
# NOT built in its shape -- asserting across the prose flagged the explanation
# of the very thing being avoided.
code = "\n".join(l.split("#")[0] for l in src.splitlines()
                 if not l.strip().startswith("#"))
code = code.replace('"""', "\n")
for bad in ("INSERT", "UPDATE ", "upsert", "commit()", "open("):
    falsy("no %s anywhere in the code" % bad.strip(), bad in code)
falsy("  it does not import the database", "from data import db" in code
      or "import db" in code)
truthy("and the file says so", "is ever written to the database" in src)

print("\n== the screen says so, loudly, in one shared place ==")
truthy("there is one banner implementation", "function demoBanner" in J)
truthy("  driven by the server's flag", "j.demo" in J)
truthy("  and it leads with the point",
       "These are sample figures, not your data." in J)
truthy("the page loads it", "/static/js/demobanner.js" in read(
    "templates", "dashboard.html"))
# THE SCRIPT TAGS, not the word. "shell.js" appears in four explanatory
# comments from line 1882 on, so comparing raw string positions measured the
# prose and failed on correct markup -- the third time that trap has caught an
# assertion in this repo.
_H = read("templates", "dashboard.html")
truthy("  before the screens that use it",
       _H.index('src="/static/js/demobanner.js')
       < _H.index('src="/static/js/shell.js'))
truthy("the listings screen shows it", "demoBanner(j)" in S)
truthy("  and dims the grid", "demoMark(document.getElementById(\"grid\"), j)" in S)
truthy("the banner has a style", ".demobar{" in C)
truthy("  and the dimming does too", ".demo-dim{" in C)
# A greyed-out button reads as disabled, and the whole point is that a reviewer
# can click things.
truthy("controls are never dimmed", ".demo-dim button" in C)

print("\n== the route hands it over unchanged ==")
truthy("/rows_all can answer with samples", 'demo_data' in LR)
truthy("  in the same shape as the real answer", '"rows": d["rows"]' in LR)
truthy("  carrying the flag", '"demo": True' in LR)
truthy("  and never breaking the real path",
       "never let the sample path break the real one" in LR)

print("\n== and samples NEVER cover real work ==")
# The bug this section exists for: Headbanger Lures has no Amazon credentials
# AND 115 real drafts. Gating on credentials alone replaced all 115 with eight
# samples. Two existing tests caught it before it shipped.
check("a workspace with rows of its own gets nothing",
      dd.maybe(EMPTY, "listings", has_data=True, workspace_id="hb"), None)
truthy("  and one with none gets samples",
       dd.maybe(EMPTY, "listings", has_data=False, workspace_id="hb"))
truthy("the route asks AFTER it has read the real store",
       LR.index("db_cards") < LR.rindex("_demo_rows(_aid, db_cards)"))
truthy("  and passes what it found", "has_data=bool(found)" in LR)
truthy("why is written down", "115 real" in read("domain", "demo_data.py"))

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
