"""PPC analytics: Orbit's screens, on a report you can download today.

    "dive a detailed harvest of ppc feature in orbit and then develope same
     feature in my app"

The harvest is orbit_ppc_complete.md. What was copied and what was not:

COPIED, because Orbit renders them and the arithmetic is standard and checkable
against its own figures — 1,639/8,569 = 19.1% ACOS and 1,639/18,150 = 9.03%
TACOS both land exactly:

    ACOS = spend/sales   ROAS = sales/spend   CTR = clicks/impressions
    CVR  = orders/clicks CPC  = spend/clicks  CPA  = spend/orders
    TACOS = spend / ALL sales, ad and organic together

COPIED AS AN IDEA, with our own definition stated because Orbit does not state
its own: WASTED SPEND, and the branded / non-branded split.

NOT COPIED: anything that writes. CLAUDE.md Rule 8, and Orbit's own words for
the same rule — "approval gates, reversible actions, and an audit trail before
changes reach Amazon. Nothing changes without the configured controls."

WHY A FILE AND NOT THE ADVERTISING API. Measured 18 Aug 2026: ads_daily 0 rows,
ppc_campaigns 0 rows, and no Advertising credentials on any of the six accounts.
It is a separate OAuth from SP-API. The SP Search Term Report carries everything
except the intraday view and domain/ppc_module.py has always been able to read
one — it simply never kept the rows.
"""
import io
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(l, g):
    check(l, bool(g), True)


def falsy(l, g):
    check(l, bool(g), False)


from domain import ppc_view as PV

# One small report where every figure can be checked by hand.
ROWS = [
    {"search_term": "garden hose", "match_type": "broad", "campaign": "C1",
     "impressions": 1000, "clicks": 100, "spend": 100.0, "sales": 400.0,
     "orders": 10, "units": 10},
    {"search_term": "garden hose", "match_type": "exact", "campaign": "C2",
     "impressions": 500, "clicks": 50, "spend": 50.0, "sales": 300.0,
     "orders": 6, "units": 6},
    {"search_term": "hose reel", "match_type": "broad", "campaign": "C1",
     "impressions": 800, "clicks": 40, "spend": 40.0, "sales": 0.0,
     "orders": 0, "units": 0},
    {"search_term": "barely ran", "match_type": "broad", "campaign": "C1",
     "impressions": 300, "clicks": 3, "spend": 3.0, "sales": 0.0,
     "orders": 0, "units": 0},
    {"search_term": "acme hose", "match_type": "exact", "campaign": "C3",
     "impressions": 200, "clicks": 20, "spend": 10.0, "sales": 200.0,
     "orders": 5, "units": 5},
]

print("=== the standard metrics, checked by hand ===")
t = PV.totals(ROWS)
# spend 203, sales 900, clicks 213, impressions 2800, orders 21
check("spend", t["spend"], 203.0)
check("sales", t["sales"], 900.0)
check("ACOS = spend / sales", t["acos"], round(203.0 / 900.0 * 100, 1))
check("ROAS = sales / spend", t["roas"], round(900.0 / 203.0, 2))
check("CTR = clicks / impressions", t["ctr"], round(213 / 2800.0 * 100, 1))
check("CVR = orders / clicks", t["cvr"], round(21 / 213.0 * 100, 1))
check("CPC = spend / clicks", t["cpc"], round(203.0 / 213, 2))
check("CPA = spend / ORDERS, not clicks", t["cpa"], round(203.0 / 21, 2))

print("\n=== nothing that cannot be worked out is printed as zero ===")
# A term with no clicks has no CTR. Printing 0% invites acting on a number
# nobody measured -- the same rule the cost and velocity code follows.
check("no impressions -> no CTR", PV.rate(0, 0), None)
check("no clicks -> no CVR", PV.rate(5, 0), None)
check("no sales -> no ACOS, not 0%", PV.rate(10, 0), None)
empty = PV.totals([])
check("an empty report has no ACOS", empty["acos"], None)
check("  and no ROAS", empty["roas"], None)
check("  but its spend is honestly zero", empty["spend"], 0.0)

print("\n=== wasted spend, our definition, stated ===")
# Spend on terms with no orders -- but only once a term has had a fair run.
# "hose reel" 40 clicks 0 orders = 40.00. "barely ran" 3 clicks is NOT counted.
check("only terms that failed with enough clicks", t["wasted_spend"], 40.0)
check("  one term, not two", t["wasted_terms"], 1)
check("  the threshold is stated, not hidden", t["min_clicks_to_judge"],
      PV.MIN_CLICKS_TO_JUDGE)
truthy("  and it is a real threshold", PV.MIN_CLICKS_TO_JUDGE >= 5)
check("  as a share of spend", t["wasted_pct"], round(40.0 / 203.0 * 100, 1))

print("\n=== TACOS needs sales the ads did not make ===")
t2 = PV.totals(ROWS, total_sales=2000.0)
check("TACOS = spend / ALL sales", t2["tacos"], round(203.0 / 2000.0 * 100, 1))
check("  organic is what is left", t2["organic_sales"], 1100.0)
check("without total sales it is left out, not guessed", t["tacos"], None)

print("\n--- and a contradiction is said out loud, not published ---")
# Found while testing live: a report showing 1,873 of ad sales against 279 of
# total sales produced a TACOS of 148%. That is not a high TACOS, it is two
# figures describing different trade.
bad = PV.totals(ROWS, total_sales=100.0)      # ad sales 900 > all sales 100
check("no TACOS when ad sales exceed all sales", bad["tacos"], None)
truthy("  and it says why", "cannot be worked out" in bad["tacos_note"])
truthy("  naming both numbers", "900" in bad["tacos_note"]
       and "100" in bad["tacos_note"])
check("  while ACOS is unaffected", bad["acos"], t["acos"])

print("\n=== one row per TERM, aggregated across match types ===")
terms = PV.by_term(ROWS, brands=["acme"])
check("four terms from five rows", len(terms), 4)
gh = [x for x in terms if x["search_term"] == "garden hose"][0]
check("its two match types are summed", gh["spend"], 150.0)
check("  and both are named", gh["match_types"], ["broad", "exact"])
check("  its ACOS is over the combined figures", gh["acos"],
      round(150.0 / 700.0 * 100, 1))
check("biggest spender first", terms[0]["search_term"], "garden hose")
# Sorted by SPEND, not ACOS: a 400% ACOS on 80p is not the problem, and sorting
# by ratio puts it above a term quietly burning 200.
truthy("  sorted by money at stake, not by ratio",
       terms[0]["spend"] >= terms[-1]["spend"])

print("\n=== the opportunity flag says what happened, never what to do ===")
flags = {x["search_term"]: x["opportunity"] for x in terms}
check("a term with clicks and no orders is wasting", flags["hose reel"], "wasting")
check("  one that has barely run is left alone", flags["barely ran"], "")
check("  a cheap converter is worth scaling", flags["acme hose"], "scaling")
losing = PV.opportunity({"clicks": 30, "orders": 2, "spend": 90.0, "sales": 40.0})
check("  and one that sells at a loss says so", losing[0], "losing")
# It reports; the decision is the owner's. Rule 8.
src = io.open(r"D:\AltaScraper\domain\ppc_view.py", encoding="utf-8").read()
truthy("the module says it never applies anything",
       "NOTHING HERE WRITES TO AMAZON" in src)


def _code_only(path):
    """The module with its comments and docstrings removed.

    Needed because the two mentions of "bid" in ppc_view.py are the comments
    promising never to touch one -- asserting on the raw text finds the promise
    and fails the file for keeping it. Same trap as test_price_dialogs.py.
    """
    import io as _io
    import re as _re
    import tokenize as _tok
    s = _io.open(path, encoding="utf-8").read()
    out, prev = [], None
    try:
        toks = list(_tok.generate_tokens(_io.StringIO(s).readline))
    except Exception:
        return s
    for tk in toks:
        if tk.type == _tok.COMMENT:
            continue
        # A docstring follows INDENT or a logical NEWLINE. NOT NL: inside
        # brackets every line break is an NL, so including it threw away the
        # first string of any wrapped call -- which is exactly where the SQL
        # lives, and made this test report that the INSERT was missing.
        if tk.type == _tok.STRING and prev in (None, _tok.INDENT, _tok.NEWLINE):
            prev = tk.type
            continue
        out.append(tk.string)
        prev = tk.type
    return _re.sub(r"\s+", "", " ".join(out))


CODE = _code_only(r"D:\AltaScraper\domain\ppc_view.py")
falsy("  and no line of code mentions a bid", "bid" in CODE.lower())
falsy("  nor a budget", "budget" in CODE.lower())
truthy("  the only write is storing the uploaded report",
       "INSERTINTOppc_search_terms" in CODE.replace(" ", ""))

print("\n=== branded vs non-branded ===")
# Amazon does not report this. The seller says which words are theirs.
check("a term containing a brand word is branded",
      PV.is_branded("acme hose 50ft", ["acme"]), True)
check("  substring, so 'acmehose' counts too",
      PV.is_branded("acmehose", ["acme"]), True)
check("  and one that does not is not", PV.is_branded("garden hose", ["acme"]), False)
# NOT FALSE when nothing is configured: "this is not branded" would be a claim.
check("with no brand terms set the answer is unknown, not 'no'",
      PV.is_branded("anything", []), None)
check("  and the whole split is withheld", PV.branded_split(ROWS, []), None)
split = PV.branded_split(ROWS, ["acme"])
check("branded spend", split["branded"]["spend"], 10.0)
check("  and its ACOS", split["branded"]["acos"], 5.0)
check("non-branded spend", split["non_branded"]["spend"], 193.0)
# THE WHOLE POINT: blended, this account looks like 22.6%. Split, the money
# actually chasing new customers is running at 27.6% and the cheap number was
# defending its own name.
truthy("  and the split is worse than the blend, which is the point",
       split["non_branded"]["acos"] > t["acos"])

print("\n=== match type, with share of spend against share of profit ===")
mt = PV.by_match_type(ROWS)
by = {m["match_type"]: m for m in mt}
check("broad and exact", sorted(by.keys()), ["broad", "exact"])
check("broad spend", by["broad"]["spend"], 143.0)
check("  as a share", by["broad"]["pct_spend"], round(143.0 / 203.0 * 100, 1))
check("broad profit", by["broad"]["profit"], round(400.0 - 143.0, 2))
truthy("  and its share of profit is lower than its share of spend",
       by["broad"]["pct_profit"] < by["broad"]["pct_spend"])
# A share of a negative total is meaningless.
neg = PV.by_match_type([{"search_term": "x", "match_type": "broad",
                         "clicks": 20, "impressions": 100, "orders": 0,
                         "spend": 50.0, "sales": 0.0}])
check("no share-of-profit when the advertising lost money overall",
      neg[0]["pct_profit"], None)

print("\n=== the route surface ===")
R = io.open(r"D:\AltaScraper\routes\ppc_routes.py", encoding="utf-8").read()
truthy("analytics is a GET", '@app.route("/ppc/analytics")' in R)
truthy("the report is stored through the SAME ingester the harvester uses",
       "_PPC.ingest_csv_bytes" in R)
truthy("  and a wrong report names what it actually was",
       "not an SP Search Term Report" in R)
truthy("no report is a setup step, not an error",
       '"report": None' in R and '"ok": True' in R)
truthy("  and it explains where to get one",
       "Measurement & Reporting" in R)
# Uploading the same file twice is the normal accident.
truthy("re-uploading a report id REPLACES it rather than doubling everything",
       "DELETE FROM ppc_search_terms WHERE workspace_id=?" in src)

print("\n=== the account is never guessed from server state ===")
# Found live: /ppc/brand_terms is posted as JSON, so with no args and no form
# the account fell back to whichever workspace the server had open. A brand
# term added while looking at one account was saved against another, and the
# save reported success.
truthy("the scope reads the JSON body too", 'body.get("id")' in R)
J = io.open(r"D:\AltaScraper\static\js\ppcview.js", encoding="utf-8").read()
truthy("  and the screen always sends it", "body.id = CUR_ACCOUNT.id" in J)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
