"""Amazon's field definitions must survive a restart.

THE REPORT: "i saw that the schema fetch takes time, so why do we need to fetch
schema everytime the page loads, can't we do it one time and again when needed
and use cache, to reduce loading times, and prevent quota from exceeding."

Exactly right, and it was not solved. There WAS a cache -- _state["schemas"] in
dashboard.py -- but it is an ordinary dict in the Flask process, so it is thrown
away on every restart. On Render that is every deploy and every idle spin-down.
After each one the app fetched every product type from Amazon again: two calls
each plus a CDN download, 42 distinct types on one live account.

Measured on PORTABLE_ELECTRONIC_DEVICE_MOUNT, UK, in a fresh process each time:

    nothing stored          9,603 ms      (two Amazon calls + a CDN download)
    stored copy on disk        16 ms      600x
    again                       7 ms

Which is about 400 seconds of Amazon calls, and 84 requests against the quota,
saved on every restart of that one account.

Amazon is not called here. What is tested is the storing: what it keeps, what
it refuses to keep, and when it goes back.
"""
import os, sys, json, tempfile, shutil
import datetime as dt

sys.path.insert(0, r"D:\AltaScraper")

from data import db as _db
from domain import schema_cache as sc

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def check_true(label, got):
    check(label, bool(got), True)


TMP = tempfile.mkdtemp(prefix="altaschema_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
conn = _db.get_db(CFG)

REAL = {"attrs": ["brand", "item_name"], "enums": {"colour": ["Red", "Blue"]},
        "required": ["brand"], "subfields": {}, "titles": {"brand": "Brand"}}
EMPTY = {"attrs": [], "enums": {}, "required": [], "subfields": {}, "titles": {}}

print("\n== a real schema is kept, an empty one never is ==")
check("a real schema is stored", sc.write(CFG, "CHAIR", "UK", REAL), True)
check_true("and reads back", sc.read(CFG, "CHAIR", "UK"))
check("the values come back intact",
      sc.read(CFG, "CHAIR", "UK")["enums"]["colour"], ["Red", "Blue"])
# A FAILED FETCH IS NOT AN ANSWER. Storing the empty shell would leave the edit
# drawer with no dropdowns and no required fields until the entry expired, and
# nothing on screen saying why -- it would look like the product type has no
# fields rather than like a call that failed.
check("an empty schema is refused", sc.write(CFG, "LAMP", "UK", EMPTY), False)
check("  so nothing is stored for it", sc.read(CFG, "LAMP", "UK"), None)
check("a schema that recorded an error is refused too",
      sc.write(CFG, "LAMP", "UK", dict(REAL, _error="timeout")), False)

print("\n== the marketplace is part of the key ==")
# The UK and US definitions of one product type are different documents, with
# different required fields and different allowed values.
sc.write(CFG, "CHAIR", "US", dict(REAL, required=["brand", "item_name"]))
check("UK and US are stored separately",
      (sc.read(CFG, "CHAIR", "UK")["required"],
       sc.read(CFG, "CHAIR", "US")["required"]),
      (["brand"], ["brand", "item_name"]))
check("a marketplace never asked about has nothing",
      sc.read(CFG, "CHAIR", "DE"), None)

print("\n== a stored copy is not trusted forever ==")
check("a fresh copy is used", sc.read(CFG, "CHAIR", "UK") is not None, True)
check("  but not past its age", sc.read(CFG, "CHAIR", "UK", max_age_days=0), None)
old = (dt.datetime.utcnow() - dt.timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
conn.execute("UPDATE schema_cache SET fetched_at=? WHERE product_type='CHAIR' "
             "AND marketplace='UK'", (old,))
conn.commit()
check("a copy older than the limit is ignored", sc.read(CFG, "CHAIR", "UK"), None)
check_true("the limit is a fortnight, not a day or a year",
           7 <= sc.TTL_DAYS <= 30)

print("\n== get(): stored, fetched, forced, and what happens when Amazon fails ==")
calls = {"n": 0}


def fetch_ok():
    calls["n"] += 1
    return dict(REAL, attrs=["brand", "item_name", "colour"])


def fetch_fails():
    calls["n"] += 1
    return dict(EMPTY, _error="Amazon said no")


sc.forget(CFG)
calls["n"] = 0
info, how = sc.get(CFG, "DESK", "UK", fetch_ok)
check("the first ask fetches", (how, calls["n"]), ("fetched", 1))
info, how = sc.get(CFG, "DESK", "UK", fetch_ok)
check("the second does not", (how, calls["n"]), ("stored", 1))
info, how = sc.get(CFG, "DESK", "UK", fetch_ok, force=True)
check("a forced refresh does go back to Amazon", (how, calls["n"]), ("fetched", 2))

# AMAZON REFUSING TODAY DOES NOT MAKE YESTERDAY'S DEFINITION WRONG. Returning
# the empty shell would empty every dropdown in the drawer; the older copy is
# far closer to the truth, and the caller is told which it got.
info, how = sc.get(CFG, "DESK", "UK", fetch_fails, force=True)
check("a failed fetch falls back to what we had", how, "stale")
check("  and the fields are still there", info["attrs"],
      ["brand", "item_name", "colour"])
sc.forget(CFG, "DESK", "UK")
info, how = sc.get(CFG, "DESK", "UK", fetch_fails)
check("with nothing to fall back on it says so", how, "failed")

print("\n== the app actually reads and writes it ==")
# Rule 12: one store, and the two places that touch it must be the two named.
dash = open(r"D:\AltaScraper\dashboard.py", encoding="utf-8-sig").read()
check_true("_load_schema reads the stored copy",
           "schema_cache as _sc" in dash and "_sc.read(CONFIG_PATH, pt, _mkt)" in dash)
check_true("  and writes one after a successful fetch",
           "_sc.write(CONFIG_PATH, pt, _mkt, info)" in dash)
routes = open(r"D:\AltaScraper\routes\listing_routes.py", encoding="utf-8-sig").read()
# "Reload Amazon values now" must not be answered from the very cache the person
# pressed it because they did not believe.
check_true("?refresh=1 clears the stored copy as well as the in-memory one",
           "_sc.forget(CONFIG_PATH, pt, _mkt)" in routes)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
