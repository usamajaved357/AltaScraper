"""probe_ads_targeting_columns.py -- what the accepted reports ACTUALLY contain.

probe_ads_targeting.py established that Amazon ACCEPTS two report shapes this
app has never asked for:

    spTargeting  DAILY, grouped by targeting, WITH matchType
    spSearchTerm DAILY, with a date column

Accepted means the request was valid. It does not mean the rows carry what the
spec wants, and building on the assumption that they do is exactly what
CLAUDE.md Rule 4 forbids: "Add a temporary diagnostic that prints the RAW
schema Amazon returns ... Build the fix from what the schema literally says."

So this collects the reports and prints their real column names and a real row.

A PROBE: live API, excluded from the suite by name, requests and reads only --
no campaign, bid, budget or state is touched (Rule 8).

Run:  python probe_ads_targeting_columns.py
"""
import datetime as _dt
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from config import settings as _cs                # noqa: E402
from api import amazon_ads as _ads                # noqa: E402

cfg = _cs.read_raw(os.path.join(HERE, "config.json"))
acc = next((a for a in (cfg.get("accounts") or [])
            if a.get("id") == "nestwell_goods"), None)
creds = _ads.creds_for(cfg, acc)
MKT = "UK"

end = _dt.date.today() - _dt.timedelta(days=2)
start = end - _dt.timedelta(days=6)
S, E = start.isoformat(), end.isoformat()


def body(type_id, group_by, columns):
    return {"name": "probe %s cols" % type_id,
            "startDate": S, "endDate": E,
            "configuration": {
                "adProduct": "SPONSORED_PRODUCTS", "groupBy": group_by,
                "columns": columns, "reportTypeId": type_id,
                "timeUnit": "DAILY", "format": "GZIP_JSON"}}


WANT = [
    ("spTargeting -- the match-type donut and stacked area (section 18)",
     body("spTargeting", ["targeting"],
          ["date", "campaignId", "campaignName", "adGroupId", "keywordId",
           "keyword", "matchType", "targeting", "impressions", "clicks",
           "cost", "sales30d", "purchases30d"])),
    ("spSearchTerm -- daily grain for the date picker (section 17)",
     body("spSearchTerm", ["searchTerm"],
          ["date", "campaignId", "campaignName", "adGroupId", "adGroupName",
           "keyword", "keywordId", "matchType", "searchTerm", "impressions",
           "clicks", "cost", "sales30d", "purchases30d"])),
]

for label, req in WANT:
    print("\n" + "=" * 74)
    print(label)
    try:
        got = _ads._post_json("/reporting/reports", creds, MKT, req) or {}
        rid = got.get("reportId")
        if not rid:
            print("  no report id:", json.dumps(got)[:300])
            continue
        print("  requested:", rid, "-- waiting for Amazon to build it")
        url, status = None, ""
        for _ in range(40):
            time.sleep(15)
            st = _ads.report_status(creds, MKT, rid) or {}
            status = str(st.get("status") or "")
            url = st.get("url") or st.get("location")
            print("     %s%s" % (status, " (ready)" if url else ""))
            if url or status.upper() in ("FAILURE", "CANCELLED"):
                break
        if not url:
            print("  gave up waiting; last status %r" % status)
            continue
        rows = _ads.report_download(url) or []
        print("  rows returned: %d" % len(rows))
        if not rows:
            print("  EMPTY -- valid request, no data in this window.")
            continue
        keys = sorted(rows[0].keys())
        print("\n  THE COLUMNS AMAZON ACTUALLY SENT (%d):" % len(keys))
        for k in keys:
            print("     %-28s e.g. %r" % (k, rows[0].get(k)))
        # The two fields everything above rests on.
        print("\n  matchType present : %s" % ("matchType" in rows[0]))
        print("  date present      : %s" % ("date" in rows[0]))
        if "matchType" in rows[0]:
            seen = {}
            for r in rows:
                m = str(r.get("matchType") or "?")
                seen[m] = seen.get(m, 0) + 1
            print("  match types seen  : %s" % json.dumps(seen))
        if "date" in rows[0]:
            days = sorted({str(r.get("date")) for r in rows})
            print("  distinct dates    : %d  %s" % (len(days), days[:8]))
    except Exception as e:
        print("  FAILED:", str(e)[:400])
