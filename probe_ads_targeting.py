"""probe_ads_targeting.py -- can spec sections 17 and 18 be built at all?

Both new sections of PPC_ANALYTICS_BUILD_SPEC rest on data this app does not
hold, and in both cases whether Amazon will supply it is a question for Amazon
rather than for us (CLAUDE.md Rule 4: never guess a schema, read it).

  SECTION 18, Campaign Analytics
    The match-type donut and the daily stacked area are specified as coming
    from "daily targeting-level reports (keyword/target grain), NOT search term
    report". Measured today, match type exists in exactly one place in this app
    -- ppc_search_terms -- which is stored at REPORT-WINDOW grain, has no date
    column, and is privacy-thresholded. So a stacked area BY DAY cannot be
    drawn from anything stored. It needs a targeting report at DAILY grain,
    carrying matchType. Does one exist? Questions 1-3.

  SECTION 17, Search Terms page
    "The Search Terms page DOES respect the date picker ... store
    ppc_search_terms with a date column (one row per date per
    search-term-campaign-adgroup combo), not just a batch window."
    That is only possible if the Search Term Report can be asked for a narrow
    window and returns a per-day date column. Questions 4-5.

A PROBE, not a test: it calls the live Advertising API, is excluded from the
suite by its name, and only REQUESTS reports. It changes no campaign, bid,
budget or state (Rule 8).

Only nestwell_goods has an advertising login, so that is the account asked.

Run:  python probe_ads_targeting.py
"""
import datetime as _dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from config import settings as _cs                # noqa: E402
from api import amazon_ads as _ads                # noqa: E402

CONFIG_PATH = os.path.join(HERE, "config.json")
cfg = _cs.read_raw(CONFIG_PATH)
acc = next((a for a in (cfg.get("accounts") or [])
            if a.get("id") == "nestwell_goods"), None)
if not acc:
    print("nestwell_goods not in config")
    raise SystemExit(1)

creds = _ads.creds_for(cfg, acc)
gaps = _ads.missing(creds)
if gaps:
    print("no advertising login:", gaps)
    raise SystemExit(1)

MKT = "UK"
# Two days back: the last days are attribution-immature, and a report asked for
# today is a report about a day that has not finished.
end = _dt.date.today() - _dt.timedelta(days=2)
start = end - _dt.timedelta(days=6)
S, E = start.isoformat(), end.isoformat()
ONE = end.isoformat()               # a SINGLE day, for question 4
print("account nestwell_goods | %s | %s .. %s" % (MKT, S, E))

ACCEPTED, REFUSED = [], []


def ask(label, body):
    """POST one report configuration and report exactly what Amazon says."""
    print("\n" + "=" * 74)
    print(label)
    print("  window       :", body["startDate"], "..", body["endDate"])
    print("  configuration:", json.dumps(body["configuration"])[:340])
    try:
        got = _ads._post_json("/reporting/reports", creds, MKT, body) or {}
        rid = got.get("reportId") or got.get("reportid")
        if rid:
            print("  ACCEPTED -- report id", rid)
            ACCEPTED.append(label)
            return rid
        print("  no id returned:", json.dumps(got)[:300])
        REFUSED.append(label)
    except Exception as e:
        print("  REFUSED:", str(e)[:460])
        REFUSED.append(label)
    return None


def body(type_id, group_by, columns, s=S, e=E, unit="DAILY",
         product="SPONSORED_PRODUCTS"):
    return {
        "name": "probe %s" % type_id,
        "startDate": s, "endDate": e,
        "configuration": {
            "adProduct": product, "groupBy": group_by, "columns": columns,
            "reportTypeId": type_id, "timeUnit": unit, "format": "GZIP_JSON",
        },
    }


# ---------------------------------------------------------------------------
# SECTION 18 -- is there a targeting report, at a daily grain, with matchType?
# ---------------------------------------------------------------------------
TARGET_COLS = ["date", "campaignId", "campaignName", "adGroupId",
               "keywordId", "keyword", "matchType", "targeting",
               "impressions", "clicks", "cost", "sales30d", "purchases30d"]

ask("1. spTargeting DAILY, grouped by targeting -- what the donut and the "
    "stacked area need",
    body("spTargeting", ["targeting"], TARGET_COLS))

# Amazon has had two names for this over the API's life, and one being refused
# says nothing about the other. Both are asked rather than one assumed.
ask("2. spKeywords DAILY, grouped by keyword -- the older name for the same "
    "question",
    body("spKeywords", ["keyword"],
         ["date", "campaignId", "campaignName", "adGroupId", "keywordId",
          "keywordText", "matchType", "impressions", "clicks", "cost",
          "sales30d", "purchases30d"]))

# The match-type column is the whole point. If targeting reports come back
# WITHOUT it, the donut cannot be split even when the report is accepted.
ask("3. spTargeting DAILY, matchType dropped -- does the report only work "
    "without the column the page needs?",
    body("spTargeting", ["targeting"],
         ["date", "campaignId", "adGroupId", "keywordId", "targeting",
          "impressions", "clicks", "cost", "sales30d", "purchases30d"]))

# ---------------------------------------------------------------------------
# SECTION 17 -- can the Search Term Report be asked for ONE day?
# ---------------------------------------------------------------------------
ST_COLS = ["date", "campaignId", "campaignName", "adGroupId", "adGroupName",
           "keyword", "keywordId", "matchType", "searchTerm",
           "impressions", "clicks", "cost", "sales30d", "purchases30d"]

ask("4. spSearchTerm for a SINGLE day -- the daily grain section 17 wants",
    body("spSearchTerm", ["searchTerm"], ST_COLS, s=ONE, e=ONE))

# If a one-day window is refused, a seven-day one WITH a date column would do
# just as well: the daily rows can be split out on arrival.
ask("5. spSearchTerm over 7 days, asking for a date column -- the other way "
    "to reach daily grain",
    body("spSearchTerm", ["searchTerm"], ST_COLS))

print("\n" + "=" * 74)
print("ACCEPTED (%d):" % len(ACCEPTED))
for a in ACCEPTED:
    print("   + " + a.split(" -- ")[0])
print("REFUSED (%d):" % len(REFUSED))
for r in REFUSED:
    print("   - " + r.split(" -- ")[0])
print()
print("A report being ACCEPTED means the request was valid, not that the rows")
print("carry what is wanted -- collect one and read its columns before")
print("building on it. Anything REFUSED cannot be built, and the screen has to")
print("say so rather than draw a shape with nothing in it.")
