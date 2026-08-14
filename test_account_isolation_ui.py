"""One account's listings must never appear under another account's name.

THE REPORT: "when i open the jack reacherd account it shows me listings from
other accounts like green heaven and selvora, for some seconds and then loads
back to original jack reacherd listings".

FOUR SEPARATE CAUSES, each enough on its own:

  1. THE BOOT RACE. loadRows() was called at DOMContentLoaded, before any
     account had been chosen. /rows_all carried no account, so the server
     answered from the account it had selected -- which it remembers between
     visits, i.e. the one open LAST time. Those rows were painted, then the
     real request landed and replaced them.

  2. THE STALE GRID. Switching accounts cleared the live-side caches but not
     ROWS or the grid's HTML, and the "Loading listings..." placeholder was
     deliberately suppressed whenever rows already existed -- so the previous
     account's cards stayed on screen for the whole of the new fetch, which on
     a multi-tab account is up to a minute.

  3. THE LATE REPLY. Two switches in quick succession left whichever fetch
     finished last on screen, and the slow one is usually the big account.

  4. enterDropshipping did not wait for its own account switch before asking
     for rows.

The fix is defence in depth, because this is the third cross-account leak found
in this app and each one looked like a one-off: the request now carries the
account, the server REFUSES a disagreement instead of answering, the browser
discards a reply that is no longer current, and the grid is emptied on switch.

An empty grid for a moment is correct. The previous account's listings are not
an approximation of this account's.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


SUBMIT = open("static/js/submit.js", encoding="utf-8").read()
SHELL = open("static/js/shell.js", encoding="utf-8").read()
SETTINGS = open("static/js/settings.js", encoding="utf-8").read()

print("=== 1. nothing is asked for before an account is chosen ===")
boot = [l for l in SETTINGS.splitlines() if "DOMContentLoaded" in l]
truthy("there is a boot handler", boot)
truthy("it no longer loads listings before an account is selected",
       all("loadRows()" not in l for l in boot))
# The paths that DO load rows all run after the switch.
truthy("entering an account still loads them", "loadRows();" in SHELL)

print("\n=== 2. the request says whose listings it wants ===")
truthy("the account travels with the request",
       "/rows_all?account=" in SUBMIT)
truthy("the reply is discarded if the user has moved on", "stillMine()" in SUBMIT)
truthy("  and if a newer request has been issued", "_ROWS_SEQ" in SUBMIT)
truthy("a server refusal is handled rather than painted",
       "account_mismatch" in SUBMIT)

print("\n=== 3. the server refuses rather than answering for the wrong account ===")
LR = open("routes/listing_routes.py", encoding="utf-8").read()
truthy("it reads the account the browser asked about",
       'request.args.get("account")' in LR)
truthy("and refuses on a disagreement", '"account_mismatch": True' in LR)
truthy("  saying which was asked for and which is selected",
       '"asked_for"' in LR and '"selected"' in LR)

print("\n=== 4. switching accounts empties the previous one's listings ===")
i = SHELL.find("async function enterAccount")
j = SHELL.find("function enterDropshipping")
enter = SHELL[i:j] if i >= 0 and j > i else ""
truthy("enterAccount was found", enter)
truthy("it clears the rows", re.search(r"ROWS\s*=\s*\[\]", enter))
truthy("  and the grid's HTML, so nothing is left painted",
       re.search(r'getElementById\("grid"\)[^\n]*innerHTML\s*=\s*""', enter))
truthy("  and the tab list", re.search(r"TABS\s*=\s*\[\]", enter))

print("\n=== 5. the dropshipping workspace waits for its own switch ===")
k = SHELL.find("function enterDropshipping")
drop = SHELL[k:k + 1600]
truthy("it is async so it can wait", "async function enterDropshipping" in SHELL)
truthy("and the account switch is awaited before anything is read",
       re.search(r'await fetch\("/accounts/select"', drop))

print("\n=== it behaves that way over HTTP ===")
import dashboard as D
app = D.build_app()
app.config["TESTING"] = True
with app.test_client() as c:
    with c.session_transaction() as s:
        s["user"] = "owner"; s["role"] = "owner"; s["is_owner"] = True

    accounts = (c.get("/accounts/list").get_json() or {}).get("accounts") or []
    ids = [a.get("id") for a in accounts if a.get("id")]
    if len(ids) >= 2:
        a, b = ids[0], ids[1]
        c.post("/accounts/select", json={"id": a})
        # THE BUG, reproduced: ask as the OTHER account while this one is
        # selected. Before the fix this returned account a's listings.
        j = c.get("/rows_all?account=" + b).get_json() or {}
        truthy("asking as another account is refused", j.get("account_mismatch"))
        check("  and it names who asked", j.get("asked_for"), b)
        check("  and who is actually selected", j.get("selected"), a)
        truthy("  and returns no rows at all", not j.get("rows"))
        # And the honest case still works: no refusal for the selected account.
        j2 = c.get("/rows_all?account=" + a).get_json() or {}
        truthy("asking as the selected account is NOT refused",
               not j2.get("account_mismatch"))
        # Old cached JS, which sends no account, must behave exactly as before.
        j3 = c.get("/rows_all").get_json() or {}
        truthy("a request with no account is not refused",
               not j3.get("account_mismatch"))
    else:
        print("  (fewer than two accounts configured here -- HTTP check skipped)")

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
