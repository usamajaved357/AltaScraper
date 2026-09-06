"""PPC_ANALYTICS_BUILD_SPEC -- the formulas it is explicit about.

Three of its rules are ones this page got wrong at some point, and each is the
kind that produces a plausible number rather than an obvious error:

  a RATIO moves in percentage POINTS, money moves in per cent. ACOS 24.3% to
    28.4% is +4.1pts; reported as +16.9% it is a true answer to a question
    nobody asked, and it reads as far worse news than it is.

  the efficiency score has THREE parts and is not shown on two. A score built
    from a subset looks identical to a real one.

  anything expressed as a SHARE of spend has to divide two figures covering the
    same days. Wasted spend comes from a fixed-window report; divided by the
    date picker's spend it read 144% -- more than all of it.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from domain import ppc_analytics as _pa           # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-68s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


print("\na ratio moves in POINTS, money moves in per cent")
now = {"spend": 120.0, "sales": 400.0, "clicks": 200.0, "impressions": 10000.0,
       "orders": 10.0, "acos_pct": 28.4, "ctr_pct": 2.0, "tacos_pct": 12.0,
       "cvr_pct": 5.0}
before = {"spend": 100.0, "sales": 320.0, "clicks": 160.0, "impressions": 8000.0,
          "orders": 8.0, "acos_pct": 24.3, "ctr_pct": 2.0, "tacos_pct": 10.0,
          "cvr_pct": 6.0}
ch = _pa.change(now, before)
# THE ONE THE SPEC CALLS OUT BY NAME. 24.3 -> 28.4 is +4.1 POINTS. As a
# percentage change it is +16.9%, and that is what this used to report.
check("ACOS moves 4.1 points", ch["acos_pct"], 4.1)
check("  and NOT 16.9 per cent", ch["acos_pct"] == 16.9, False)
check("TACOS likewise", ch["tacos_pct"], 2.0)
check("CVR likewise, downwards", ch["cvr_pct"], -1.0)
check("a ratio that did not move is 0 points", ch["ctr_pct"], 0.0)
# Money and counts are still percentages, because "spend rose 20 points" is
# meaningless.
check("spend moves 20 per cent", ch["spend"], 20.0)
check("clicks move 25 per cent", ch["clicks"], 25.0)

u = _pa.change_units(now)
check("and each says which unit it is in",
      (u["acos_pct"], u["spend"], u["ctr_pct"], u["clicks"]),
      ("pts", "pct", "pts", "pct"))

print("\na ratio starting at zero still has a move; money starting at zero does not")
# 0% ACOS rising to 30% is +30 POINTS -- a real statement. But spend rising from
# nothing has no percentage change, and +100% would read as one.
ch2 = _pa.change({"acos_pct": 30.0, "spend": 50.0},
                 {"acos_pct": 0.0, "spend": 0.0})
check("a ratio off a zero base is measurable", ch2["acos_pct"], 30.0)
check("money off a zero base is not", ch2["spend"], None)

print("\nthe efficiency score needs all three parts, or it is not shown")
RATES = {"breakeven_acos_pct": 40.0}
WASTED = {"spend": 100.0, "report_spend": 1000.0}
CVRB = {"mean": 5.0, "sd": 1.0, "n": 60}
TOT = {"acos_pct": 20.0, "cvr_pct": 5.0}

s = _pa.efficiency_score(TOT, RATES, WASTED, CVRB)
# acos: 1 - 20/40 = 0.5 -> 50 ; cvr: exactly on the mean -> 100 ;
# wasted: 1 - 100/1000 = 0.9 -> 90.  0.5*50 + 0.3*100 + 0.2*90 = 73.0
check("the three parts combine at 0.50 / 0.30 / 0.20", s["score"], 73.0)
check("  and 73 is 'Average'", s["band"], "Average")
check("  the ACOS part is half of break-even", s["parts"]["acos"]["value"], 50.0)
check("  a CVR sitting on its mean scores full marks",
      s["parts"]["cvr"]["value"], 100.0)
check("  and the waste part is what did NOT go to waste",
      s["parts"]["wasted"]["value"], 90.0)
truthy("every part publishes its reasoning", all(
    p.get("why") for p in s["parts"].values()))

# THE REFUSALS. Each of these used to be a way to get a number that looked real.
check("no break-even means no score",
      _pa.efficiency_score(TOT, {}, WASTED, CVRB)["score"], None)
check("no ACOS means no score",
      _pa.efficiency_score({"cvr_pct": 5.0}, RATES, WASTED, CVRB)["score"], None)
check("no CVR history means no score",
      _pa.efficiency_score(TOT, RATES, WASTED, None)["score"], None)
truthy("  and the refusal names the missing part",
       "history" in _pa.efficiency_score(TOT, RATES, WASTED, None)["why"])

print("\nthe waste share divides two figures covering the SAME days")
# THE BUG THIS PINS. wasted_spend covers the search-term report's fixed window
# (~30 days). Divided by a 14-day spend it produced 144% -- more than all of the
# spend was wasted, which is arithmetic across two periods and not a fact.
# report_spend is the spend over the REPORT's own window.
mismatched = {"spend": 251.56}          # no report_spend at all
check("without a comparable denominator there is no score",
      _pa.efficiency_score(TOT, RATES, mismatched, CVRB)["score"], None)
truthy("  and it says the periods could not be compared",
       "same days" in _pa.efficiency_score(TOT, RATES, mismatched, CVRB)["why"])
# And with one, the share cannot exceed 100%.
s2 = _pa.efficiency_score(TOT, RATES, {"spend": 900.0, "report_spend": 1000.0},
                          CVRB)
check("a 90% waste share scores 10 on that part",
      s2["parts"]["wasted"]["value"], 10.0)

print("\nbands are the spec's: under 50 poor, 50-75 average, over 75 good")
def band_of(acos):
    return _pa.efficiency_score({"acos_pct": acos, "cvr_pct": 5.0}, RATES,
                                {"spend": 0.0, "report_spend": 1000.0},
                                CVRB)["band"]
check("a very efficient account is Good", band_of(4.0), "Good")
# AT break-even the ACOS part scores 0, and with a perfect CVR and no waste the
# other two carry it to exactly 50 -- the boundary, which the spec puts in
# "Average" (50-75), not in "Poor" (< 50). Pinned because a boundary is where an
# off-by-one lives, and because the number reads oddly at first glance:
# advertising that exactly breaks even is not "poor", it is unremarkable.
check("advertising exactly at break-even lands on the 50 boundary",
      _pa.efficiency_score({"acos_pct": 40.0, "cvr_pct": 5.0}, RATES,
                           {"spend": 0.0, "report_spend": 1000.0},
                           CVRB)["score"], 50.0)
check("  which the spec calls Average, not Poor", band_of(40.0), "Average")
# A PROPERTY OF THE SPEC'S WEIGHTING, worth knowing rather than arguing with:
# ACOS carries only half the score, so on its own it cannot drag the total below
# 50. An account at DOUBLE its break-even still scores 50 if it wastes nothing
# and converts normally -- the ACOS part is 0 and the other two are perfect.
check("ACOS alone cannot pull the score below the halfway mark",
      band_of(80.0), "Average")
check("  because its part has bottomed out at zero",
      _pa.efficiency_score({"acos_pct": 80.0, "cvr_pct": 5.0}, RATES,
                           {"spend": 0.0, "report_spend": 1000.0},
                           CVRB)["parts"]["acos"]["value"], 0.0)
# It takes a second failing part to reach Poor, which is the point of a
# composite: one bad number is a symptom, two is a diagnosis.
poor = _pa.efficiency_score({"acos_pct": 80.0, "cvr_pct": 5.0}, RATES,
                            {"spend": 400.0, "report_spend": 1000.0}, CVRB)
check("losing money AND wasting 40% of the spend is Poor", poor["band"], "Poor")
check("  scoring 0 + 30 + 12", poor["score"], 42.0)

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    for f in fails:
        print("  FAILED:", f)
    sys.exit(1)
print("all passed")
