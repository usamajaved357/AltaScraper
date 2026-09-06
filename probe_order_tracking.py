"""probe_order_tracking.py -- does Amazon hand back the tracking WE uploaded?

    "i have already uploaded the trackings of the fbm orders in seller central
     so dont ask me to provide the tracking of that order again in the app,
     check the tracking details from amazon"

A previous pass concluded SP-API does not return seller-uploaded tracking. That
conclusion was drawn from the Orders API and the FLAT FILE all-orders report, and
it was incomplete: the flat file and the XML version of the same report do NOT
carry the same fields. The XML one has a <FulfillmentData> block, and inside it
<ShipperTrackingNumber>.

So this asks Amazon, rather than reasoning about it. It is a PROBE -- it calls
the live API and is excluded from the test suite by name (probe_*.py). It reads
only: no report is created that changes anything, and nothing is written back to
Amazon.

Run:  python probe_order_tracking.py [account_id] [days]
"""
import datetime as _dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from config import settings as _cs                # noqa: E402
from domain import accounts as _acc               # noqa: E402
from api import sp_reports as _rep                # noqa: E402

CONFIG_PATH = os.path.join(HERE, "config.json")

# In the order worth trying. The first is what the app already knows about and
# is here to prove the negative properly; the second is the real candidate.
CANDIDATES = [
    ("GET_FLAT_FILE_ALL_ORDERS_DATA_BY_LAST_UPDATE_GENERAL",
     "the flat file the app already uses -- believed to carry no tracking"),
    ("GET_XML_ALL_ORDERS_DATA_BY_LAST_UPDATE_GENERAL",
     "the XML of the SAME report -- has a FulfillmentData block the flat file "
     "does not"),
    ("GET_AMAZON_FULFILLED_SHIPMENTS_DATA_GENERAL",
     "FBA shipments -- carries carrier and tracking, but only for FBA"),
    ("GET_FLAT_FILE_ACTIONABLE_ORDER_DATA_SHIPPING",
     "orders still to ship -- by definition not yet tracked, checked for "
     "completeness"),
]

TRACK_HINTS = ("tracking", "shippertrackingnumber", "carrier", "ship-service")


def _client(acc, mkt_code):
    from sp_api.api import Reports
    from sp_api.base import Marketplaces

    creds = _acc.account_creds(acc)
    enum = getattr(Marketplaces, str(mkt_code).upper(), None) or Marketplaces.UK
    return Reports(credentials=creds, marketplace=enum), enum.marketplace_id


def _look(text, kind):
    """Does this report body actually contain tracking numbers? -> dict."""
    out = {"bytes": len(text or ""), "has_field": False, "sample": [],
           "rows": 0, "with_tracking": 0}
    if not text:
        return out
    low = text[:400000].lower()
    out["has_field"] = any(h in low for h in TRACK_HINTS)
    if kind == "xml":
        nums = re.findall(r"<ShipperTrackingNumber>([^<]+)</ShipperTrackingNumber>",
                          text)
        ids = re.findall(r"<AmazonOrderID>([^<]+)</AmazonOrderID>", text)
        out["rows"] = len(ids)
        out["with_tracking"] = len([n for n in nums if n.strip()])
        out["sample"] = nums[:5]
        car = re.findall(r"<CarrierName>([^<]+)</CarrierName>", text)
        out["carriers"] = sorted(set(car))[:8]
    else:
        lines = text.splitlines()
        if not lines:
            return out
        head = lines[0].split("\t")
        out["columns"] = head
        cols = [i for i, h in enumerate(head)
                if any(x in h.lower() for x in TRACK_HINTS)]
        out["tracking_columns"] = [head[i] for i in cols]
        out["rows"] = max(0, len(lines) - 1)
        for ln in lines[1:400]:
            f = ln.split("\t")
            if any(i < len(f) and f[i].strip() for i in cols):
                out["with_tracking"] += 1
                if len(out["sample"]) < 5:
                    out["sample"].append([f[i] for i in cols if i < len(f)])
    return out


def main():
    aid = sys.argv[1] if len(sys.argv) > 1 else ""
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    cfg = _cs.read_raw(CONFIG_PATH)
    accts = cfg.get("accounts") or []
    if not aid:
        print("accounts:", [a.get("id") for a in accts])
        print("\nusage: python probe_order_tracking.py <account_id> [days]")
        return
    acc = next((a for a in accts if str(a.get("id")) == aid), None)
    if not acc:
        print("no such account:", aid)
        return
    mkt = (acc.get("default_marketplace")
           or (acc.get("marketplaces") or ["UK"])[0])
    print("account   :", aid, "| marketplace:", mkt)
    print("seller id :", acc.get("seller_id"))

    try:
        rc, mid = _client(acc, mkt)
    except Exception as e:
        print("could not open Reports:", e)
        return

    end = _dt.datetime.utcnow()
    start = end - _dt.timedelta(days=days)
    st = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    en = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    print("window    :", st, "->", en)

    for rtype, note in CANDIDATES:
        print("\n" + "=" * 72)
        print(rtype)
        print("  ", note)
        try:
            text, src, built = _rep.fetch(
                rc, rtype, marketplace_ids=[mid], start_time=st, end_time=en,
                allow_reuse=False)
        except Exception as e:
            print("   REFUSED:", str(e)[:260])
            continue
        kind = "xml" if "XML" in rtype else "tsv"
        got = _look(text, kind)
        print("   source %s, built %s, %d bytes, %d rows"
              % (src, built, got["bytes"], got["rows"]))
        if kind == "tsv":
            print("   tracking-ish columns:", got.get("tracking_columns"))
        else:
            print("   carriers seen:", got.get("carriers"))
        print("   rows carrying a tracking number: %d" % got["with_tracking"])
        if got["sample"]:
            print("   sample:", json.dumps(got["sample"])[:300])
        # Keep the body so the shape can be read properly rather than guessed
        # at -- CLAUDE.md Rule 4: never infer a schema, read it.
        out = os.path.join(HERE, "probe_out_%s.txt" % rtype.lower()[:40])
        try:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(text[:2000000])
            print("   saved:", os.path.basename(out))
        except Exception as e:
            print("   could not save:", e)


if __name__ == "__main__":
    main()
