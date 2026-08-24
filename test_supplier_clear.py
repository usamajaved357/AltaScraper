"""Clearing every supplier off the repricer, so a fresh set can go on.

    "I also want to delete all the suppliers from the repricer"
    "so i can add new suppliers"

Suppliers could be added one at a time and by the sheetful, and removed only one
at a time from inside an expanded row. Replacing a whole set meant opening
fifty-five rows and clicking fifty-five times.

WHAT GOES AND WHAT STAYS is the whole design, and it follows from the second
sentence. The links go, and the price readings recorded against them go with
them -- a reading is keyed only by source_id, so once its supplier is deleted
there is no URL and no label to say whose price it was, and an orphan row is not
history, it is a number nobody can attribute. remove_source already deletes a
single supplier's readings for exactly that reason; this matches it.

The ENROLMENT and the pricing RULES stay. The SKUs remain tracked and their
targets remain set, so a new supplier sheet works the moment it is uploaded
instead of needing every SKU re-enrolled first. That is what "so i can add new
suppliers" asks for.

Run against a temporary config. The real repricer holds 55 links and 153
readings that cannot be fetched again, so this test never touches it -- and the
accept path was deliberately NOT clicked against the live data for the same
reason.
"""
import json
import os
import shutil
import sys
import tempfile

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from domain import source_repo as R

TMP = tempfile.mkdtemp(prefix="srcclear_")
CFG = os.path.join(TMP, "config.json")
with open(CFG, "w", encoding="utf-8") as fh:
    json.dump({}, fh)


def seed():
    """Two accounts, two marketplaces, with enrolment, rules and readings."""
    made = {}
    for wsid, mkt, skus in (("jack_uk", "UK", ["A", "B"]),
                            ("jack_uk", "DE", ["A"]),
                            ("nestwell_goods", "UK", ["Z"])):
        for sku in skus:
            R.enrol(CFG, wsid, mkt, sku, mode="dry_run")
            sid, _ = R.ensure_source(CFG, wsid, mkt, sku,
                                     "https://www.ebay.co.uk/itm/%s%s%s" % (wsid, mkt, sku),
                                     kind="ebay", label="s")
            made[(wsid, mkt, sku)] = sid
            R.record_check(CFG, sid, {"status": "ok", "price": 1.0,
                                      "shipping": 0.0, "currency": "GBP",
                                      "in_stock": True})
    return made


seed()

print("=== the count says everything that will go, not just the links ===")
c = R.count_sources(CFG, "jack_uk", "UK")
check("  supplier links", c["sources"], 2)
check("  SKUs they sit on", c["skus"], 2)
# "Delete 55 suppliers" understates it. The readings go too, and they cannot be
# fetched again.
check("  price readings held", c["checks"], 2)
check("an account with none says none",
      R.count_sources(CFG, "selvora_limited", "UK"),
      {"sources": 0, "skus": 0, "checks": 0})


print("\n=== clearing one scope leaves every other alone ===")
got = R.clear_sources(CFG, "jack_uk", "UK")
check("it reports the links it removed", got["sources"], 2)
check("  and the readings that went with them", got["checks"], 2)
check("jack_uk UK is empty", R.count_sources(CFG, "jack_uk", "UK")["sources"], 0)
# THE MARKETPLACE IS PART OF THE SCOPE. A seller sourcing for UK and DE
# separately must not lose Germany by clearing Britain.
check("  jack_uk DE is untouched", R.count_sources(CFG, "jack_uk", "DE")["sources"], 1)
check("  and so is nestwell_goods", R.count_sources(CFG, "nestwell_goods", "UK")["sources"], 1)
check("  their readings survived too",
      R.count_sources(CFG, "jack_uk", "DE")["checks"], 1)


print("\n=== the SKUs stay tracked, which is the point of the request ===")
_enr = R.enrolled(CFG, "jack_uk", "UK")
check("the SKUs are still enrolled", sorted(e["sku"] for e in _enr), ["A", "B"])
truthy("  so a new supplier attaches with no re-enrolling",
       R.ensure_source(CFG, "jack_uk", "UK", "A",
                       "https://www.ebay.co.uk/itm/brand-new", kind="ebay")[1])
check("  and the count sees it", R.count_sources(CFG, "jack_uk", "UK")["sources"], 1)
# A reading recorded against a DELETED supplier must not survive to be counted
# against the new one.
check("  the new supplier starts with no history",
      R.count_sources(CFG, "jack_uk", "UK")["checks"], 0)


print("\n=== a missing scope deletes NOTHING, rather than everything ===")
_before = R.count_sources(CFG, "jack_uk", "DE")["sources"] \
    + R.count_sources(CFG, "nestwell_goods", "UK")["sources"]
check("no account", R.clear_sources(CFG, "", "UK"), {"sources": 0, "checks": 0})
check("  no marketplace", R.clear_sources(CFG, "jack_uk", ""), {"sources": 0, "checks": 0})
check("  neither", R.clear_sources(CFG, None, None), {"sources": 0, "checks": 0})
_after = R.count_sources(CFG, "jack_uk", "DE")["sources"] \
    + R.count_sources(CFG, "nestwell_goods", "UK")["sources"]
check("  and nothing was lost", _after, _before)
# ensure_source upper-cases nothing, but store paths do; a clear typed in lower
# case must still match or it silently does nothing.
check("a lower-case marketplace still matches",
      R.clear_sources(CFG, "jack_uk", "de")["sources"], 1)
check("clearing an already-empty scope is not an error",
      R.clear_sources(CFG, "jack_uk", "DE"), {"sources": 0, "checks": 0})

shutil.rmtree(TMP, ignore_errors=True)


print("\n=== the route asks before it deletes, and refuses a moved target ===")
RT = open("routes/sourcing_routes.py", encoding="utf-8").read()
truthy("there is a count endpoint", '@app.route("/sourcing/sources/count")' in RT)
truthy("  and it deletes nothing",
       "clear_sources" not in RT.split("def sourcing_sources_count")[1].split("@app.route")[0])
truthy("the clear endpoint exists",
       '@app.route("/sourcing/sources/clear", methods=["POST"])' in RT)
_clear = RT.split("def sourcing_sources_clear")[1].split("@app.route")[0]
truthy("  it goes through the store, not its own SQL",
       "_repo.clear_sources(CONFIG_PATH" in _clear and "DELETE FROM" not in _clear)
truthy("  it refuses without an account and a marketplace",
       "Open an account and pick a marketplace first" in _clear)
truthy("  and refuses when the number moved under the dialog",
       "expect" in _clear and "409" in _clear)
truthy("  reporting the readings that went as well as the links",
       '"checks_deleted"' in _clear)


print("\n=== permission: a bulk delete, not ordinary repricer work ===")
from auth import guard
check("/sourcing/sources/clear needs approve_delete",
      guard.required_permission("/sourcing/sources/clear", "POST"), "approve_delete")
# THE ORDER IS THE WHOLE THING HERE. ("/sourcing", "publish") sits in this table
# and first match wins, so a rule placed after it never fires -- which is what
# happened on the first attempt: everything under /sourcing resolved to publish.
check("  adding one supplier is still ordinary repricer work",
      guard.required_permission("/sourcing/source/add", "POST"), "publish")
check("  removing one likewise",
      guard.required_permission("/sourcing/source/remove", "POST"), "publish")
check("  and counting them is a read",
      guard.required_permission("/sourcing/sources/count", "GET"), None)
G = open("auth/guard.py", encoding="utf-8").read()
truthy("the ordering trap is written down where the rule is",
       "first match wins" in G and "ABOVE the broad /sourcing line" in G)


print("\n=== the screen warns, with the numbers, and says what survives ===")
JS = open("static/js/sourcing.js", encoding="utf-8").read()
_fn = JS.split("async function sourcingClearSuppliers")[1].split("\n// The report is shown")[0]
truthy("the counts come from the server", '"/sourcing/sources/count"' in _fn)
# srcConfirm, NOT the browser's confirm(). This page deliberately has no
# confirm() left in it -- test_repricer_page asserts that, and caught me using
# one -- because a white system dialog in the middle of a dark screen is the one
# thing on the page that does not look like the app.
truthy("nothing is deleted without a confirm", "await srcConfirm({" in _fn)
# Comments stripped first: the note above the call explains the rule using the
# very word it forbids, and a bare search cannot tell an explanation from a call.
_code = "\n".join(l for l in _fn.split("\n")
                  if not l.strip().startswith(("//", "*", "/*")))
truthy("  and it is the page's own dialog, not the browser's",
       "confirm(" not in _code.replace("srcConfirm(", ""))
truthy("  marked as the risk it is", "risk: true" in _fn)
truthy("  it states the number of links", 'Delete all " + n + " supplier link' in _fn)
truthy("  how many SKUs they sit on", "c.skus" in _fn)
truthy("  and how many readings go with them", "c.checks" in _fn)
truthy("  it says the readings cannot be fetched again",
       "cannot be fetched again" in _fn)
# The reason the request was made: a new sheet has to work immediately.
truthy("  and that the SKUs stay tracked",
       "SKUs stay tracked and their profit targets stay set" in _fn)
truthy("  and that other accounts are safe",
       "Other accounts and other marketplaces are not touched" in _fn)
truthy("the agreed number is sent back with the request", "expect: n" in _fn)
truthy("no dialog at all when there is nothing to clear",
       "if(!n){" in _fn and "no supplier links" in _fn)
truthy("the page reloads afterwards", "sourcingLoad()" in _fn)

# The BUTTON, not the bare name -- the name also appears inside the handler's
# own note, which comes earlier in the file and made this compare the wrong two
# positions.
truthy("the button is beside the two that add suppliers",
       'onclick="sourcingClearSuppliers()"' in JS
       and JS.index('onclick="sourcingClearSuppliers()"')
           > JS.index("Suppliers from a sheet"))
truthy("  and after the template it undoes the upload of",
       JS.index('onclick="sourcingClearSuppliers()"') > JS.index("Get the template"))
CSS = open("static/css/dashboard.css", encoding="utf-8").read()
truthy("  and it does not look like them", "srcwipe" in CSS and "var(--red)" in
       CSS[CSS.index("srcwipe"):CSS.index("srcwipe") + 240])

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
