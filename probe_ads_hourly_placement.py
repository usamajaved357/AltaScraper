"""probe_ads_hourly_placement.py -- what the Live Tracker can actually be built on.

LIVE-TRACKER-BUILD-PROMPT.md asks for two things this app does not have:

    hourly advertising    "Last 24 Hours" and "Last 7 Days" plot one point per
                          HOUR. Every row this app stores is one whole day.
    placement breakdown   each ASIN card splits by Top of Search / Product Page
                          / Other on-Amazon / Off Amazon.

Both are questions for Amazon rather than for us, so this asks it. A PROBE: it
calls the live Advertising API, is excluded from the suite by name, and only
REQUESTS reports -- it changes no campaign, bid or budget (Rule 8).

Run:  python probe_ads_hourly_placement.py
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
end = _dt.date.today() - _dt.timedelta(days=2)
start = end - _dt.timedelta(days=2)
S, E = start.isoformat(), end.isoformat()
print("account nestwell_goods | %s | %s .. %s" % (MKT, S, E))


def ask(label, body):
    """POST one report configuration and report exactly what Amazon says."""
    print("\n" + "=" * 72)
    print(label)
    print("  configuration:", json.dumps(body["configuration"])[:320])
    try:
        got = _ads._post_json("/reporting/reports", creds, MKT, body) or {}
        rid = got.get("reportId") or got.get("reportid")
        if rid:
            print("  ACCEPTED -- report id", rid)
            return rid
        print("  no id returned:", json.dumps(got)[:300])
    except Exception as e:
        print("  REFUSED:", str(e)[:400])
    return None


def cfg_for(group_by, columns, unit, product="SPONSORED_PRODUCTS",
            type_id="spCampaigns"):
    return {
        "name": "probe %s %s" % (type_id, unit.lower()),
        "startDate": S, "endDate": E,
        "configuration": {
            "adProduct": product, "groupBy": group_by, "columns": columns,
            "reportTypeId": type_id, "timeUnit": unit, "format": "GZIP_JSON",
        },
    }


BASE = ["date", "campaignId", "campaignName", "impressions", "clicks", "cost",
        "sales30d", "purchases30d"]

# ---- 1. HOURLY, the thing the page is named after --------------------------
ask("1. HOURLY on spCampaigns -- the Live Tracker's whole premise",
    cfg_for(["campaign"], BASE, "HOURLY"))

# Some Amazon report types accept a unit others refuse, so ask more than one.
ask("2. HOURLY on spAdvertisedProduct",
    cfg_for(["advertiser"],
            ["date", "advertisedAsin", "impressions", "clicks", "cost",
             "sales30d", "purchases30d"],
            "HOURLY", type_id="spAdvertisedProduct"))

# ---- 3. PLACEMENT, which the ASIN cards need -------------------------------
ask("3. DAILY with campaignPlacement -- the placement breakdown",
    cfg_for(["campaign", "campaignPlacement"],
            ["date", "campaignId", "campaignName", "placementClassification",
             "impressions", "clicks", "cost", "sales30d", "purchases30d"],
            "DAILY"))

# ---- 4. placement AND hourly together --------------------------------------
ask("4. HOURLY with campaignPlacement -- both at once",
    cfg_for(["campaign", "campaignPlacement"],
            ["date", "campaignId", "campaignName", "placementClassification",
             "impressions", "clicks", "cost"],
            "HOURLY"))

print("\n" + "=" * 72)
print("Anything marked ACCEPTED can be built on. Anything REFUSED cannot, and")
print("the screen has to say so rather than draw a shape with nothing in it.")
