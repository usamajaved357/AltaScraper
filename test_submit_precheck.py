"""/submit/precheck warns about main images the SUBMIT cannot use -- for this account.

It never worked: it called _records() without the sheet it reads (a TypeError,
swallowed into "no rows") and read keys a row never has. Fixed, it must say
exactly what the submit will do, which depends on the app's public address:
an app image with one is fine; without one, or a borrowed photo, the listing
goes up with no main image; a link to this machine fails. The rule is one
function (domain/image_urls), shared with the generator (Rule 12).
Temp config and database only; no network.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


FIX = tempfile.mkdtemp(prefix="fixt_precheck_")
CFG = os.path.join(FIX, "config.json")
DBP = os.path.join(FIX, "altascraper.db")
with open(CFG, "w", encoding="utf-8") as fh:
    json.dump({"accounts": [{"id": a, "name": a} for a in ("acct_a", "acct_b")]}, fh)
os.environ["CONFIG_PATH"] = CFG
os.environ["ALTASCRAPER_DB"] = DBP
os.environ.pop("PUBLIC_BASE_URL", None)

from data import db as _db                               # noqa: E402
assert os.path.abspath(_db.db_path(CFG)) == os.path.abspath(DBP)
from data.store import ListingStore                      # noqa: E402
from data import backend as BE                           # noqa: E402
from domain import image_urls as IU                      # noqa: E402
from flask import Flask                                  # noqa: E402
from routes import submit_routes as SR                   # noqa: E402


def attrs(url):
    return json.dumps({"main_product_image_locator": [{"media_location": url}]})


ROWS = (("acct_a", "A-APPIMG", "APPROVED", "/media/_acct/acct_a/A-APPIMG/main.jpg"),
        ("acct_a", "A-LOOPBACK", "API_READY", "http://127.0.0.1:5000/media/x.jpg"),
        ("acct_a", "A-BORROWED", "APPROVED", "https://m.media-amazon.com/images/I/x.jpg"),
        ("acct_a", "A-DRAFT", "NEEDS_REVIEW", "/media/draft.jpg"),
        ("acct_b", "B-APPIMG", "APPROVED", "/media/_acct/acct_b/B-APPIMG/main.jpg"))
for ws, sku, status, img in ROWS:
    ListingStore(ws, config_path=CFG).upsert_row(
        {"SKU": sku, "Status": status, "Title": sku, "Attributes JSON": attrs(img)})

STATE = {"active_account_id": "acct_b"}          # another tab has B open
_ws, _records = BE.make(STATE, CFG)
app = Flask("precheck_test")
SR.register(app, _records=_records, _active_account=lambda: {}, _state=STATE,
            _cfg=lambda: {}, _ws=_ws, CONFIG_PATH=CFG)
c = app.test_client()


def flagged(url):
    j = c.get(url).get_json()
    return {r["sku"]: r["why"] for r in j.get("local_image_rows", [])}


print("\n1. with NO public address set (a local install)")
f = flagged("/submit/precheck?account=acct_a")
check("the app's own image is flagged: Amazon cannot reach it", "no public address" in f.get("A-APPIMG", ""), True)
check("a link to this machine is flagged as such", "points at this computer" in f.get("A-LOOPBACK", ""), True)
check("a borrowed photo is flagged: it is not sent", "another seller's photo" in f.get("A-BORROWED", ""), True)
check("a draft that is not being submitted is not looked at", "A-DRAFT" in f, False)
check("only the account the page shows", "B-APPIMG" in f, False)

print("\n2. with a public address (the deployed app)")
os.environ["PUBLIC_BASE_URL"] = "https://app.example.test"
f2 = flagged("/submit/precheck?account=acct_a")
check("the app's own image is NOT flagged -- the submit turns it into a public link",
      "A-APPIMG" in f2, False)
check("  a borrowed photo still is", "A-BORROWED" in f2, True)
os.environ.pop("PUBLIC_BASE_URL", None)

print("\n3. only the listings being submitted")
f3 = flagged("/submit/precheck?account=acct_a&skus=A-BORROWED")
check("?skus= limits the warning to them", sorted(f3), ["A-BORROWED"])

print("\n4. the moved rules answer exactly as the generator's old ones did")


def old_fetchable(u, base):
    u = str(u or "").strip()
    if u.lower().startswith(("http://", "https://")):
        return u
    if u.startswith("/media/"):
        return "SIGNED" if base else ""
    return ""


def old_is_ours(u, base):
    u = str(u or "").strip()
    if not u:
        return False
    if u.startswith("/media/") or u.startswith("data:"):
        return True
    return bool(base) and u.startswith(base.rstrip("/"))


cases = ["", "/media/x/y.jpg", "https://m.media-amazon.com/a.jpg", "http://127.0.0.1/x.jpg",
         "data:image/png;base64,AAAA", "https://app.example.test/img/t/x.jpg", "C:/pics/x.jpg"]
mism = []
for base in ("", "https://app.example.test"):
    if base:
        os.environ["PUBLIC_BASE_URL"] = base
    else:
        os.environ.pop("PUBLIC_BASE_URL", None)
    for u in cases:
        nf = IU.fetchable(CFG, u)
        nf = "SIGNED" if (u.startswith("/media/") and nf) else nf
        if nf != old_fetchable(u, base) or IU.is_ours(CFG, u) != old_is_ours(u, base):
            mism.append((base, u))
os.environ.pop("PUBLIC_BASE_URL", None)
check("fetchable / is_ours match the old behaviour on every case", mism, [])
GEN = open(os.path.join(HERE, "amazon_listing_generator.py"), encoding="utf-8").read()
check("the generator calls the shared rules",
      "_iu.fetchable(CONFIG_PATH, u)" in GEN and "_iu.is_ours(CONFIG_PATH, u, config)" in GEN, True)

print("\nFAILURES: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
