"""The weekly KPI pack, checked against the spreadsheet it replaces.

    "i want to make a system where i upload the reports and i get this data, in
     a format like return intelligence. and also an option where i just need to
     connect an account like nestwell goods and all of this data is extracted
     without the need of reports"

WHERE THE EXPECTED NUMBERS COME FROM

The "Naturealm WEEKLY KPI FIXED" sheet, read on 18 Aug 2026, week of 9-15 Aug.
Its Weekly tab is entirely formulas over two source tabs, and those two tabs are
the two reports this feature takes. So the engine must reproduce every figure
the sheet computes, from the same data -- and it does, to the cent.

FIVE DEFECTS IN THAT SHEET, AND THE TEST THAT EACH IS GONE

  1. the current week showed the previous week's figures, because the freeze
     happened and the source tabs were never refreshed
  2. CPA was spend/units in the frozen history and spend/ad-orders in the live
     column -- $7.70 against $27.26, not comparable, nothing said so
  3. new-to-brand orders summed column AD of a tab with SIXTEEN columns, so it
     was 0 every week and looked measured
  4. the branded split did SUMIF(campaign name = "br"), which never matched a
     campaign called "[Laurence] SBV Branded - C", so BR and NB were all 0.00
  5. spend read "Total cost" while sales read "Sales (converted)"

The through-line of all five: a figure that could not be computed came out as
zero and was indistinguishable from a real zero. So the sharpest checks here are
that unknown stays None, and that None never renders as 0.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

from domain import report_reader as _rr      # noqa: E402
from domain import weekly_kpi as _wk         # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                  % (got, want)))


def near(label, got, want, tol=0.01):
    ok = got is not None and abs(float(got) - float(want)) <= tol
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                  % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


# ---------------------------------------------------------------------------
# The two reports, with Amazon's real column names.
# ---------------------------------------------------------------------------
BIZ = {
    "headers": ["(Parent) ASIN", "(Child) ASIN", "Title", "Sessions - Total",
                "Sessions - Total - B2B", "Session Percentage - Total",
                "Page Views - Total", "Units Ordered",
                "Unit Session Percentage", "Ordered Product Sales",
                "Total Order Items"],
    "rows": [
        ["B0GW9CRHX2", "B01BK871DE", "Sacred 7 Organic", "1,791", "35",
         "35.86%", "2,444", "600", "33.50%", "$36,195.02", "577"],
        ["B0GW9CRHX2", "B07NHH7HFL", "Sacred 7 Organic", "1,389", "40",
         "27.81%", "1,781", "343", "24.69%", "$20,000.00", "300"],
        ["B0GW994SRJ", "B0CQKGG8N4", "Lions Mane", "104", "2", "2.08%",
         "120", "34", "32.69%", "$1,000.00", "30"],
    ],
}

PPC = {
    "headers": ["State", "Campaign name", "Country", "Status", "Type",
                "Targeting", "Impressions", "Clicks", "Total cost",
                "Total cost (converted)", "Purchases", "Sales",
                "Sales (converted)", "Purchases (new to brand)",
                "Sales (new to brand) (converted)"],
    "rows": [
        ["ENABLED", "[Laurence] SBV Branded - C", "US", "Delivering", "SB2",
         "MANUAL", "3615", "20", "$108.57", "$108.57", "7", "$278.68",
         "$278.68", "2", "$60.00"],
        ["ENABLED", "[Laurence] B0DP2V7GR2 - Co", "US", "Delivering", "SP",
         "MANUAL", "10000", "80", "$400.00", "$400.00", "13", "$900.00",
         "$900.00", "3", "$105.70"],
    ],
}

print("\n== the reports are identified by their COLUMNS ==")
check("the Business Report is recognised", _wk.detect(BIZ["headers"]),
      _wk.BUSINESS)
check("the Campaign export is recognised", _wk.detect(PPC["headers"]),
      _wk.CAMPAIGN)
# Both carry a "Sales" column, so a tie must not fall to the wrong one.
check("neither is mistaken for the other",
      _wk.detect(PPC["headers"]) != _wk.detect(BIZ["headers"]), True)
check("something else is refused rather than half-read",
      _wk.detect(["Order ID", "Buyer", "Ship city"]), "")
check("  and so is an empty header row", _wk.detect([]), "")

print("\n== the arithmetic the sheet does, done the same way ==")
pack = _wk.build(BIZ, PPC, brand_terms=["branded"], week_start="2026-08-09",
                 week_end="2026-08-15")
k = pack["kpis"]
near("total sales is the sum of ordered product sales", k["total_sales"],
     36195.02 + 20000.00 + 1000.00)
check("sessions", k["sessions"], 1791 + 1389 + 104)
check("units", k["units"], 600 + 343 + 34)
near("ad spend", k["ad_spend"], 508.57)
near("ad sales", k["ad_sales"], 1178.68)
check("impressions", k["ad_impressions"], 13615)
check("clicks", k["ad_clicks"], 100)
check("ad orders", k["ad_orders"], 20)
near("RoAS is ad sales / ad spend", k["roas"], 1178.68 / 508.57, 0.001)
near("CPC is spend / clicks", k["cpc"], 5.0857, 0.001)
near("TACOS is total spend / total sales", k["tacos"],
     508.57 / 57195.02, 0.0001)

print("\n== defect 2: CPA is spend per AD ORDER, not per unit ==")
# The sheet's history had spend/units, which on this data would be 0.53 rather
# than 25.43 -- a 48x difference in the row a client reads first.
near("CPA", k["cpa"], 508.57 / 20, 0.001)
check("  and NOT spend per unit", round(k["cpa"], 2) == round(508.57 / 977, 2),
      False)

print("\n== defect 3: new-to-brand is read, not summed off a missing column ==")
check("NTB orders come from the campaign export", k["ntb_orders"], 5)
near("  and NTB sales with them", k["ntb_sales"], 165.70)

print("\n== defect 4: branded is matched on the campaign NAME ==")
# SUMIF(name = "br") never matched "[Laurence] SBV Branded - C". Containment does.
check("the branded campaign is found", k["br_campaigns"], 1)
near("  its spend", k["br_spend"], 108.57)
check("the rest are non-branded", k["nb_campaigns"], 1)
near("  and their spend", k["nb_spend"], 400.00)
near("  branded RoAS", k["br_roas"], 278.68 / 108.57, 0.001)
check("matching is case-insensitive, because nobody types it twice the same",
      _wk.is_branded("[X] SBV BRANDED - C", ["branded"]), True)
check("  and a term that is not in the name does not match",
      _wk.is_branded("[X] Generic - broad", ["branded"]), False)
# WITH NO TERMS SET everything is non-branded, and that is a SETTING not a
# finding. The screen has to say so, so the engine must make it visible.
none_set = _wk.kpis(_wk.parse_business(BIZ), _wk.parse_campaigns(PPC), [])
check("no brand terms -> everything counts as non-branded",
      none_set["br_campaigns"], 0)
check("  and the terms used are reported so the screen can say why",
      none_set["brand_terms_used"], [])

print("\n== defect 5: spend and sales are both taken converted ==")
# "Total cost (converted)" is preferred over "Total cost", matching
# "Sales (converted)". Identical in USD; different the moment it converts.
CONV = {"headers": ["Campaign name", "Impressions", "Clicks", "Total cost",
                    "Total cost (converted)", "Purchases", "Sales",
                    "Sales (converted)"],
        "rows": [["c", "1", "1", "100.00", "80.00", "1", "500.00", "400.00"]]}
c = _wk.parse_campaigns(CONV)["rows"][0]
check("spend is the converted figure", c["spend"], 80.0)
check("  and so is sales", c["sales"], 400.0)

print("\n== the currency comes from the REPORT, not the open account ==")
# An agency runs a client's US pack with a UK workspace open, and every dollar
# is drawn with a pound sign. Measured: uploading Naturealm's US reports into
# jack_uk showed "£61,843.59" for $61,843.59.
check("dollars in the file are read as USD", pack["currency"], "USD")
check("  from the Business Report's money column", pack["business_currency"],
      "USD")
check("  and the campaign export agrees", pack["campaign_currency"], "USD")
check("  so nothing is flagged as mixed", pack["currency_mixed"], False)
check("pounds are read as GBP", _rr.currency_of(["£1,234.00"]), "GBP")
check("  euros too", _rr.currency_of(["€99,00"]), "EUR")
check("a column with no symbol says nothing rather than guessing",
      _rr.currency_of(["1234.00", "99"]), "")
check("  and an empty column too", _rr.currency_of([]), "")
# Two marketplaces in one pack makes every combined figure meaningless.
GBP_PPC = {"headers": PPC["headers"],
           "rows": [[c.replace("$", "£") for c in PPC["rows"][0]]]}
mixed = _wk.build(BIZ, GBP_PPC, week_start="2026-08-09", week_end="2026-08-15")
check("a dollar report beside a pound one is flagged",
      mixed["currency_mixed"], True)
check("  naming both", (mixed["business_currency"], mixed["campaign_currency"]),
      ("USD", "GBP"))
# THE FIELD MUST SURVIVE STORAGE. It was computed correctly and then dropped by
# weeks(), which rebuilds a subset of the pack by hand -- so the screen still
# drew a pound sign on dollars while the stored pack knew better.
import inspect                                                    # noqa: E402
_weeks_src = inspect.getsource(_wk.weeks)
for f in ("currency", "currency_mixed", "business_currency",
          "campaign_currency"):
    truthy("weeks() passes %s through to the screen" % f,
           ('"%s"' % f) in _weeks_src)

print("\n== unknown is never zero ==")
# The through-line of all five defects.
empty = _wk.build(BIZ, None, week_start="2026-08-09", week_end="2026-08-15")
check("with no campaign report, RoAS is None", empty["kpis"]["roas"], None)
check("  CPA is None", empty["kpis"]["cpa"], None)
check("  CTR is None", empty["kpis"]["ctr"], None)
check("  and the screen is told which half is missing",
      empty["has_campaigns"], False)
check("  while the half that IS there still computes",
      empty["kpis"]["sessions"], 3284)
no_biz = _wk.build(None, PPC, week_start="2026-08-09", week_end="2026-08-15")
check("with no Business Report, TACOS is None", no_biz["kpis"]["tacos"], None)
check("  unit session percentage is None too",
      no_biz["kpis"]["unit_session_pct"], None)
check("  and that half is flagged", no_biz["has_business"], False)
# DSP, giveaway and Meta are not reported by Amazon at all.
check("un-entered DSP spend stays None", k["dsp_spend"], None)
near("  and total spend is the ad spend it could see", k["total_spend"], 508.57)

print("\n== the per-product block ==")
p = pack["products"]
check("one row per child ASIN", len(p), 3)
check("  biggest seller first", p[0]["child_asin"], "B01BK871DE")
near("  conversion is units / sessions", p[0]["conversion"], 600 / 1791, 0.0001)
near("  units a day over a 7-day week", p[0]["units_per_day"], 85.7, 0.05)
# A part week must not be reported as a full one.
half = _wk.products(_wk.parse_business(BIZ), days=3)
near("  a 3-day window divides by 3", half[0]["units_per_day"], 200.0, 0.05)

print("\n== reading the file itself ==")
csv_bytes = b"(Child) ASIN,Sessions - Total,Units Ordered,Ordered Product Sales\n" \
            b"B01,\"1,791\",600,\"$36,195.02\"\n"
t = _rr.read(csv_bytes, "x.csv")
check("a CSV is read", t["format"], "csv")
check("  with its header", t["headers"][0], "(Child) ASIN")
tsv = _rr.read(b"A\tB\n1\t2\n", "x.txt")
check("a tab-separated file is not read as one giant column", tsv["format"], "tsv")
check("  and really splits", tsv["headers"], ["A", "B"])
check("an empty file says so, rather than raising",
      bool(_rr.read(b"", "x.csv")["error"]), True)

print("\n== numbers out of what Amazon actually writes ==")
for raw, want in (("$36,195.02", 36195.02), ("1,791", 1791.0), ("35.86%", 0.3586),
                  ("(108.57)", -108.57), ("", None), (None, None),
                  ("—", None), ("n/a", None), (5, 5.0), (0, 0.0)):
    check("num(%r)" % (raw,), _rr.num(raw), want)
# THE distinction the whole app rests on.
check("a missing figure is None, and None is not zero", _rr.num("") is None, True)
check("  but a real zero is zero", _rr.num("0"), 0.0)

print("\n== columns are found by NAME, never by position ==")
# Defect 3 was a column LETTER pointing past the end of the table.
idx = _rr.index(["(Child) ASIN", "Units Ordered"], _wk.BUSINESS_COLS)
check("the ones present are mapped", sorted(idx), ["child_asin", "units"])
check("  and the ones absent are ABSENT, not mapped to 0",
      "sales" in idx, False)
# Amazon punctuates the same column differently between reports.
for variant in ("Sessions - Total", "Sessions – Total", "Sessions—Total",
                "sessions total"):
    i = _rr.index([variant], {"sessions": ("Sessions - Total",)})
    check("  %r is the same column" % variant, i.get("sessions"), 0)

print("\n== weeks run Sunday to Saturday, like the sheet ==")
import datetime as _dt                                            # noqa: E402
s, e = _wk.week_bounds(_dt.date(2026, 8, 12))     # a Wednesday
check("the week containing Wed 12 Aug starts Sun 9 Aug", s, "2026-08-09")
check("  and ends Sat 15 Aug", e, "2026-08-15")
check("a Sunday is the start of its own week",
      _wk.week_bounds(_dt.date(2026, 8, 9))[0], "2026-08-09")
check("a Saturday is the end of its own week",
      _wk.week_bounds(_dt.date(2026, 8, 15))[0], "2026-08-09")

print("\n== movement says BETTER, not bigger ==")
a = {"kpis": {"roas": 1.5, "acos": 0.30, "cpc": 2.00, "total_sales": 100.0}}
b = {"kpis": {"roas": 2.0, "acos": 0.20, "cpc": 2.50, "total_sales": 120.0}}
ch = _wk.compare(b, a)
check("RoAS rising is better", ch["roas"]["better"], True)
check("ACOS falling is better", ch["acos"]["better"], True)
check("CPC rising is WORSE, though the number went up",
      ch["cpc"]["better"], False)
check("sales rising is better", ch["total_sales"]["better"], True)
near("  and the percentage is against the week before",
     ch["total_sales"]["pct"], 0.20, 0.001)
check("no movement is neither better nor worse",
      _wk.compare({"kpis": {"roas": 2.0}}, {"kpis": {"roas": 2.0}})["roas"]["better"],
      None)
check("a figure that was None is skipped rather than compared to zero",
      "cpa" in _wk.compare({"kpis": {"cpa": 5.0}}, {"kpis": {"cpa": None}}), False)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
