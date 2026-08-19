"""Dr PPC -- read the advertising data and say what is wrong with it.

Built BEFORE the Advertising API is connected, so this test is the whole
verification of the reasoning. When credentials arrive, the field mapping in
api/amazon_ads.py may need correcting against a real response; the rules below
will not, because they take rows and never touch a network.

Every way a PPC console gives dangerous advice:

  * firing on four clicks, where a keyword has told you nothing
  * inventing an ACOS target, and being confident about a number nobody chose
  * telling somebody to raise the budget on a campaign that loses money
  * treating "spent with no sales" as an infinite ACOS instead of as waste,
    which loses the one finding that needs no target at all
  * changing a bid (CLAUDE.md Rule 8)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from domain import dr_ppc as D  # noqa: E402

FAIL = []


def check(label, got, want):
    ok = got == want
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        FAIL.append(label)


def close(label, got, want, tol=0.005):
    ok = got is not None and abs(got - want) <= tol
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want~%r" % (got, want)))
    if not ok:
        FAIL.append(label)


def truthy(label, got):
    check(label, bool(got), True)


def term(**kw):
    base = {"search_term": "widget", "keyword": "", "campaign_name": "C1",
            "clicks": 20, "impressions": 1000, "spend": 10.0, "sales": 40.0,
            "orders": 2}
    base.update(kw)
    return base


def camp(**kw):
    base = {"campaign_id": "1", "campaign_name": "C1", "state": "enabled",
            "budget": 10.0, "spend": 5.0, "sales": 30.0, "impressions": 900,
            "clicks": 20, "orders": 2}
    base.update(kw)
    return base


print("== ACOS is a ratio, and 'no sales' is not one ==")
close("spend over sales", D.acos(10, 40), 0.25)
# NOT infinity and NOT zero. Spend with no sales has no ACOS -- it has wasted
# spend, which is a different finding with a different action.
check("no sales means no ACOS", D.acos(10, 0), None)
check("  and no spend figure means no ACOS", D.acos(None, 40), None)

print("\n== the target is never guessed ==")
# Guessing 30% produces confident advice about a number nobody chose, on a
# product that might make 8% or 60%.
t, why = D.target_for(None, None)
check("no target and no margin means NO target", t, None)
truthy("  and it says why", "no cost of goods" in why)
t, why = D.target_for(None, 0.25)
close("a given target is used", t, 0.25)
truthy("  and named as yours", "you set" in why)
# A 40% margin breaks even at 40% ACOS; the target leaves a quarter of it.
t, why = D.target_for(0.40, None)
close("a margin gives a target inside break-even", t, 0.30)
truthy("  and explains the arithmetic", "break-even" in why)
truthy("  the target is below break-even, not at it", t < D.breakeven_acos(0.40))

print("\n== nothing fires on four clicks ==")
# A keyword with four clicks and no sale is not a bad keyword. It is four clicks.
check("four clicks, no sales -> nothing",
      len(D.check_wasted_spend([term(clicks=4, sales=0, orders=0)])), 0)
check("  ten clicks, no sales -> a finding",
      len(D.check_wasted_spend([term(clicks=10, sales=0, orders=0)])), 1)
check("  the floor is Amazon's rough rule of thumb", D.MIN_CLICKS, 10)

print("\n== wasted spend needs no target at all ==")
# The clearest finding there is, and the only one that works with no margin and
# no target: enough clicks, zero sales, whatever the product makes.
w = D.check_wasted_spend([term(clicks=30, spend=22.5, sales=0, orders=0)], "£")
check("it fires", len(w), 1)
check("  rated critical", w[0]["severity"], D.CRITICAL)
truthy("  with the money in it", "22.50" in w[0]["what"])
truthy("  and a specific action", "negative exact" in w[0]["do"])
# It must NOT also be reported as a high ACOS -- that would be the same money
# counted twice under two different actions.
check("  and is not also an ACOS finding",
      len(D.check_acos([term(clicks=30, spend=22.5, sales=0, orders=0)], 0.3)), 0)

print("\n== ACOS findings appear only when there is a target ==")
bad = [term(clicks=20, spend=30.0, sales=40.0)]      # 75% ACOS
check("no target -> no ACOS findings", len(D.check_acos(bad, None)), 0)
a = D.check_acos(bad, 0.30)
check("  with a target -> a finding", len(a), 1)
check("  and well over double is critical", a[0]["severity"], D.CRITICAL)
mild = D.check_acos([term(clicks=20, spend=14.0, sales=40.0)], 0.30)  # 35%
check("  a little over is a warning, not a crisis", mild[0]["severity"], D.WARN)
check("  at target exactly -> nothing",
      len(D.check_acos([term(clicks=20, spend=12.0, sales=40.0)], 0.30)), 0)
# It recommends and stops.
truthy("  it says the app will not change the bid",
       "will not change a bid" in a[0]["do"])

print("\n== the one finding that makes money ==")
h = D.check_harvest([term(search_term="blue widget", keyword="", clicks=25,
                          orders=6, spend=10.0, sales=60.0)], 0.30)
check("a converting search term is worth harvesting", len(h), 1)
truthy("  named exactly", "blue widget" in h[0]["do"])
truthy("  and told to negate it where it came from", "negate" in h[0]["do"])
# A term that IS already the keyword is not a discovery.
check("a term identical to its keyword is not a discovery",
      len(D.check_harvest([term(search_term="widget", keyword="widget",
                                clicks=25, orders=6)], 0.30)), 0)
# One order is not a pattern.
check("  one order is not enough",
      len(D.check_harvest([term(search_term="new thing", orders=1, clicks=25)], 0.30)), 0)

print("\n== a losing campaign is PROTECTED by its budget ==")
# Telling somebody to raise the budget on a campaign that loses money is the
# worst advice this page could give.
good = D.check_budget_capped([camp(budget=10.0, spend=10.0, sales=40.0)], "£")
check("a profitable capped campaign is flagged", len(good), 1)
truthy("  as an opportunity", good[0]["severity"] == D.INFO)
truthy("  and says the decision is yours", "decision for you" in good[0]["do"])
losing = D.check_budget_capped([camp(budget=10.0, spend=10.0, sales=12.0)], "£")
check("a LOSING capped campaign is flagged too", len(losing), 1)
truthy("  but as a warning", losing[0]["severity"] == D.WARN)
truthy("  and says the budget may be protecting you",
       "protecting you" in losing[0]["do"])
truthy("  never telling you to raise it", "Raising" not in losing[0]["do"])
# Under budget is not capped.
check("a campaign under its budget is not flagged",
      len(D.check_budget_capped([camp(budget=10.0, spend=2.0)])), 0)
# Unknown sales must not be guessed either way.
unk = D.check_budget_capped([camp(budget=10.0, spend=10.0, sales=None)], "£")
check("capped with unknown sales is its own answer", len(unk), 1)
truthy("  and says the sales are unknown", "unknown" in unk[0]["what"])

print("\n== a live campaign nobody sees ==")
n = D.check_no_impressions([camp(state="enabled", impressions=0)])
check("enabled with no impressions is flagged", len(n), 1)
truthy("  explained as a bid below the floor", "below the floor" in n[0]["why"])
check("  a PAUSED campaign with no impressions is not a problem",
      len(D.check_no_impressions([camp(state="paused", impressions=0)])), 0)

print("\n== the whole console ==")
out = D.run(
    [camp(budget=10.0, spend=10.0, sales=40.0)],
    [term(clicks=30, spend=22.5, sales=0, orders=0, search_term="dud"),
     term(clicks=5, spend=1.0, sales=0, orders=0, search_term="quiet")],
    target=0.30, currency="£")
truthy("it produces findings", out["findings"])
check("  worst first", out["findings"][0]["severity"], D.CRITICAL)
truthy("  counts them", out["counts"]["critical"] >= 1)
close("  and totals the wasted spend", out["totals"]["wasted"], 22.5)
# The thin term is NOT judged, and that is said rather than hidden.
truthy("  terms below the click floor are declared",
       any("fewer than 10 clicks" in n for n in out["notes"]))

print("\n== with no data at all it says so, rather than looking clean ==")
empty = D.run([], [], target=0.30)
check("no findings", len(empty["findings"]), 0)
truthy("  but it says no search-term data was read",
       any("No search-term data" in n for n in empty["notes"]))
truthy("  and no campaign data either",
       any("No campaign data" in n for n in empty["notes"]))
# Without a target, the absence of ACOS advice is explained.
noT = D.run([], [], target=None)
truthy("no target is explained rather than silent",
       any("No ACOS target" in n for n in noT["notes"]))

print("\n== it cannot write to Amazon ==")
# The guarantee is enforced in api/amazon_ads.py, not merely intended here.
from api import amazon_ads as A  # noqa: E402
for path in ("/v2/sp/campaigns", "/v2/sp/keywords", "/v2/sp/adGroups",
             "/sp/campaigns", "/v2/sp/campaigns/12345"):
    try:
        A._post_json(path, {"ads_client_id": "x"}, "UK", {})
        check("a POST to %s is refused" % path, False, True)
    except RuntimeError as e:
        truthy("a POST to %-24s is refused" % path, "not a reporting path" in str(e))
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "domain", "dr_ppc.py"), encoding="utf-8").read()
code = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))
truthy("the advisor makes no requests of its own", "urllib" not in code
       and "requests" not in code)

print("\n%d failed" % len(FAIL))
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
