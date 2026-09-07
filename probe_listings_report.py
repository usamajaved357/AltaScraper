# Is the new listing in the reports Sync is built from?
#
# Sync does not read the Listings API. routes/live_routes.py:770 builds the
# catalogue from GET_MERCHANT_LISTINGS_ALL_DATA and merges
# GET_MERCHANT_LISTINGS_INACTIVE_DATA (:929). If the SKU is in neither, no
# amount of clicking Sync can ever show it, and the fault is not in the app's
# parsing or its cache.
#
# Costs report quota (roughly one request a minute per account), which is why
# this is a probe and not a test.
import gzip
import json
import time
import urllib.request
import urllib.parse
import urllib.error

ACCOUNT = "nestwell_goods"
SKU = "9.99_2Days_B0BP1HNW8G"
ASIN = "B0HJ2W3XZ1"
mid = "A1F83G8C2ARO7P"
endpoint = "https://sellingpartnerapi-eu.amazon.com"

c = json.load(open("config.json", encoding="utf-8"))
a = [x for x in c["accounts"] if x.get("id") == ACCOUNT][0]

body = urllib.parse.urlencode({
    "grant_type": "refresh_token",
    "refresh_token": a["refresh_token"],
    "client_id": a["lwa_client_id"],
    "client_secret": a["lwa_client_secret"],
}).encode()
req = urllib.request.Request(
    "https://api.amazon.com/auth/o2/token", data=body,
    headers={"Content-Type": "application/x-www-form-urlencoded"})
access = json.loads(urllib.request.urlopen(req, timeout=30).read())["access_token"]
H = {"x-amz-access-token": access, "Accept": "application/json"}


def get(path, params=None, tries=8):
    url = endpoint + path + (("?" + urllib.parse.urlencode(params, doseq=True))
                             if params else "")
    # 429 IS THE NORMAL ANSWER HERE, not a failure: the owner's own Sync clicks
    # share this quota. Back off and ask again rather than reporting "cannot
    # check" -- an unanswered question would leave the actual fault unproven.
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=H)
            return json.loads(urllib.request.urlopen(r, timeout=60).read())
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1:
                raise
            wait = 15 * (i + 1)
            print("    throttled, waiting %ds" % wait)
            time.sleep(wait)


def post(path, payload):
    r = urllib.request.Request(
        endpoint + path, data=json.dumps(payload).encode(),
        headers=dict(H, **{"Content-Type": "application/json"}), method="POST")
    return json.loads(urllib.request.urlopen(r, timeout=60).read())


def fetch(report_type):
    print("\n" + "=" * 70)
    print(report_type)
    print("=" * 70)
    # THE NEWEST REPORT AMAZON ALREADY HOLDS. Creating one costs quota that the
    # owner's own Sync clicks have already spent, and this is the very document
    # a Sync would reuse -- so it answers the question without competing for the
    # quota the sales figures also need.
    doc = None
    try:
        lst = get("/reports/2021-06-30/reports",
                  {"reportTypes": report_type, "processingStatuses": "DONE",
                   "marketplaceIds": mid, "pageSize": 10})
        reps = [r for r in (lst.get("reports") or []) if r.get("reportDocumentId")]
        reps.sort(key=lambda r: str(r.get("createdTime") or ""), reverse=True)
        print("  DONE reports Amazon still holds: %d" % len(reps))
        for r in reps[:5]:
            print("    built %s  id %s" % (r.get("createdTime"), r.get("reportId")))
        if reps:
            doc = reps[0].get("reportDocumentId")
            print("  reading the newest, built %s" % reps[0].get("createdTime"))
    except urllib.error.HTTPError as e:
        print("  list refused: HTTP %s %s" % (e.code, e.read().decode()[:200]))
        return
    if not doc:
        print("  Amazon holds no DONE report of this type")
        return
    d = get("/reports/2021-06-30/documents/%s" % doc)
    raw = urllib.request.urlopen(d["url"], timeout=120).read()
    if d.get("compressionAlgorithm") == "GZIP" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    text = raw.decode("utf-8", "replace")
    lines = [l for l in text.splitlines() if l.strip()]
    print("  rows (incl. header): %d" % len(lines))
    if lines:
        print("  columns: %s" % lines[0][:220])
    hit = [l for l in lines if SKU in l or ASIN in l]
    print("  THIS SKU/ASIN PRESENT: %s" % ("YES" if hit else "NO"))
    for l in hit[:3]:
        print("    " + l[:300])
    # What the report DOES carry, so "39 items" can be compared against it.
    print("  first 3 data rows:")
    for l in lines[1:4]:
        print("    " + l[:200])


fetch("GET_MERCHANT_LISTINGS_ALL_DATA")
fetch("GET_MERCHANT_LISTINGS_INACTIVE_DATA")
