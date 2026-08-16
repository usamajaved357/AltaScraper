"""A run belongs to the account that launched it.

THE INCIDENT THIS COMES FROM (15 Aug 2026, production).
Generate was pressed while the screen showed Jack Reacherd. The log said:

    --account-id nestwell_goods
    Account-scoped creds: Nestwell Goods LTD (seller A8YN8LJZAAYT4)
    Output -> SQLite (workspace 'dropshipping') -- no output sheet opened
    Input  -> imported queue is EMPTY -- press Import in the app
    Reading input sheet... No products found in input sheet.

Three separate faults in five lines:

  1. The wrong ACCOUNT ran. The browser sent none, so the server used one
     process-wide variable that is shared by every tab and restored from disk
     after a restart.
  2. The wrong WORKSPACE was written. config["_account_id"] was only ever set
     inside the Miles-specific config block, so an ordinary generate fell back
     to the literal string "dropshipping" -- for BOTH the output store and the
     input queue.
  3. Hence the empty queue: products imported under the account's own workspace
     were invisible to a run looking in "dropshipping".

Nothing was published and nothing was overwritten -- it stopped at the empty
queue -- but the next fault of this shape would not stop there.
"""
import re
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

GEN = open(r"D:\AltaScraper\amazon_listing_generator.py", encoding="utf-8").read()
RUN = open(r"D:\AltaScraper\routes\listing_routes.py", encoding="utf-8").read()
INV = open(r"D:\AltaScraper\static\js\inventory.js", encoding="utf-8").read()

print("=== the workspace comes from --account-id, for every mode ===")
truthy("the CLI argument is written onto the config",
       'config["_account_id"] = _cli_account_id' in GEN)
# It must be set OUTSIDE the Miles block. Miles is one mode of several and the
# assignment living only there is precisely what caused this.
_set_at = GEN.find('config["_account_id"] = _cli_account_id')
_parse_at = GEN.find('_cli_account_id = _early_argval("--account-id")')
truthy("  and NOT only inside the Miles-specific config", _set_at >= 0)
# It has to happen at STARTUP argument parsing, which every mode goes through --
# not in some mode's own config builder, which is exactly where it used to live.
# Source position alone proves nothing (the Miles block is a function body that
# runs later), so this pins it to the startup parse it must sit beside.
truthy("  it is set at startup parsing, which every mode runs",
       0 <= _parse_at < _set_at < _parse_at + 1400)
# The Miles copy may stay -- it is harmless once the startup one exists -- but
# it must not be the ONLY one.
check("there is more than one assignment only if startup has its own",
      GEN.count('"_account_id":') <= 1 or _set_at >= 0, True)

# Both fallbacks still exist -- they are correct for a genuinely unscoped run --
# but they must no longer be what an account-scoped run lands on.
# COUNTED AS "at least the two", not "exactly two". A third arrived with
# output_ws(), which resolves the same workspace for Preview and Submit and
# needs the same fallback for the same reason. Pinning the exact number makes
# the test fail on a correct addition, which teaches people to edit the number
# rather than think about it. What matters is that the fallback still exists and
# that every one of them is spelled the same way.
_fallbacks = re.findall(r'\S+\s+or "dropshipping"', GEN)
check("the unscoped fallback still exists everywhere it is needed",
      len(_fallbacks) >= 2, True)
check("  and every one of them resolves the same way",
      len(set(f.strip() for f in _fallbacks)) == 1, True)

print("\n=== the output store writes to the app's OWN database ===")
truthy("the listing store is given the config path, not left to the environment",
       "config_path=str(config.get(\"_config_path\") or \"\") or None" in GEN)

print("\n=== the run is scoped by the page, not by a process-wide variable ===")
truthy("the browser sends the account it is displaying",
       '_runParams.set("account_id", CUR_ACCOUNT.id)' in INV)
truthy("  and the marketplace with it", '_runParams.set("marketplace", WS_MARKET)' in INV)
# The reading and comparing now live in domain/request_account.py, shared with
# the Sales screen's read path -- the two need OPPOSITE answers (a read resolves
# to the page's account, a write refuses), and settling them in one module is
# what stops them drifting apart. The behaviour asserted below is unchanged; only
# its address is. See test_request_account.py for the module's own tests.
import domain.request_account as _ra
from flask import Flask as _Flask, request as _flask_request
_flask_app = _Flask(__name__)
truthy("the server reads it", 'request_account' in RUN)
truthy("  through the one module that answers this for reads and writes",
       "mismatch_for_write" in RUN)
truthy("  which compares it with the server's own idea",
       'active_account_id' in open("domain/request_account.py", encoding="utf-8").read())
# The important part: a disagreement STOPS the run. A run writes listings and a
# submit reaches Amazon; picking either side silently is how one account's
# products end up in another's catalogue.
with _flask_app.test_request_context("/run?account_id=nestwell_goods"):
    _msg = _ra.mismatch_for_write(_flask_request, {"active_account_id": "jack_uk"},
                                  what="run")
truthy("  and REFUSES when they disagree", "ACCOUNT_MISMATCH" in _msg)
truthy("  refusing with nothing run", "nothing was run" in _msg)
with _flask_app.test_request_context("/run"):
    _msg0 = _ra.mismatch_for_write(_flask_request, {"active_account_id": ""})
truthy("no account at all is also refused, not defaulted",
       "No account is selected" in _msg0)

print("\n=== and the page puts it right instead of leaving you stuck ===")
truthy("the mismatch triggers a reselect", 'ACCOUNT_MISMATCH' in INV)
# Via /accounts/select, not by setting the id: that route also resets the sheet,
# tab and marketplace, which is the other half of the same bug.
truthy("  through the account picker's own route, so the sheet follows",
       '"/accounts/select"' in INV)
truthy("  retried exactly once per press", "runMode._retried" in INV)

print("\n=== the account really is on the command line ===")
truthy("the run passes --account-id", '"--account-id", _acc_id' in RUN)

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
