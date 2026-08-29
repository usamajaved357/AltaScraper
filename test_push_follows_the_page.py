"""A live push goes to the account on the SCREEN, not the one in a global.

FOUND BY AUDITING THE LAST DAY'S OWN WORK, not by a report.

/stock/bulk_update was added yesterday beside the handling-time push it shares
an Amazon attribute with, and it copied that route's way of deciding whose
listings it was about:

    acc = _active_account()
    mkt = _state["active_marketplace"] or acc["default_marketplace"] or "UK"

Both halves of that are wrong, and the app already knows it.

THE ACCOUNT. _state["active_account_id"] is ONE VARIABLE FOR THE WHOLE SERVER
PROCESS, written when an account is CHOSEN. domain/account_scope.py records the
consequence in the user's own words -- "i switched from headbanger lures
recently but i am on nestwell goods but still i am shown this error" -- from a
screenshot with three tabs open. The screenshot that started today's work has
four. Whichever tab last switched owns that variable, so a stock change typed in
one tab is pushed to whatever the other tab selected. SKUs do not save it:
listing_routes says plainly that they are price_days_ASIN and "two accounts
sourcing the same product at the same price collide".

THE MARKETPLACE. routes/scope.py was written to end exactly the `or "UK"`
default it kept here -- "defaulting to UK gives a US account a confident answer
about the wrong country". On a READ that is a wrong screen; on this route it
aimed a WRITE, so sheelady_us would have had its handling time pushed to the
United Kingdom.

The price endpoints next door were already right: the browser names its account
and scope.resolve follows it. There is one answer to that question in the app
now (Rule 12) instead of two that disagree, and the bar's three buttons can no
longer mean different accounts.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-68s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


RT = open(os.path.join("routes", "handling_routes.py"), encoding="utf-8").read()
PR = open(os.path.join("routes", "price_routes.py"), encoding="utf-8").read()
JS = open(os.path.join("static", "js", "handling.js"), encoding="utf-8").read()
DB = open("dashboard.py", encoding="utf-8").read()

print("=== the resolver is the shared one, not a fourth opinion ===")
truthy("handling_routes resolves through routes/scope",
       "_scope_mod.resolve(" in RT)
truthy("  the same call the price endpoints make",
       "_scope_mod.resolve(" in PR)
truthy("  and it is given the id the request named",
       'asked_id=b.get("id") or b.get("account_id")' in RT)
truthy("  and the marketplace the request named",
       'asked_marketplace=b.get("marketplace")' in RT)
# The account record must FOLLOW the id, or the id says one company and the
# credentials belong to another -- the bug scope.resolve's docstring records.
truthy("  with a loader, so the credentials follow the id",
       "load_account=_load_account" in RT and "def _load_account(" in RT)
truthy("dashboard passes it the config path it needs for that",
       "_handling_routes.register(" in DB and "CONFIG_PATH=CONFIG_PATH" in
       DB.split("_handling_routes.register(")[1][:260])

print("\n=== the two bad defaults are gone from this file ===")
# The push sites must not read the process-wide globals for themselves. One
# mention survives inside _scope() as the FALLBACK BASE, which is what
# price_routes does too -- so this counts uses, it does not ban the name.
falsy("no push falls back to the marketplace global",
      '_state.get("active_marketplace")' in RT)
falsy("  and none defaults to the United Kingdom", 'or "UK"' in RT)
# THE CALL, not the name. The docstring above _scope explains what the pushes
# used to do and names _active_account() while doing so, so counting the bare
# name counts the explanation as a caller.
check("_active_account is read once, as scope.resolve's starting point",
      RT.count("account=_active_account() or {}"), 1)
# Sliced to the NEXT definition rather than a character count -- _scope carries
# a long docstring and any fixed window either cuts the code off or reaches past
# it into the next function.
_scope_body = RT.split("def _scope(")[1].split("    def ")[0]
truthy("  and that one use is inside _scope",
       "_active_account() or {}" in _scope_body)

print("\n=== a push with nothing to aim at is refused, not guessed ===")
_pt = RT.split("def _push_target(")[1].split("@app.route")[0]
truthy("no account -> the app's one sentence for that",
       "_scope_mod.NO_ACCOUNT" in _pt)
truthy("no marketplace -> the app's one sentence for that",
       "_scope_mod.NO_MARKETPLACE" in _pt)
# TWO PUSH SITES, ONE HELPER. Stock, and the handling-time run.
#
# There were three. The middle one was the single-SKU "test" push that ran
# before a bulk change and asked a second time before sending the rest; it was
# removed on request, and it was never the safety net it looked like -- the test
# was a real push, so the value was already on Amazon by the time the second
# dialog appeared. What this file guards is unchanged: every site that reaches
# Amazon resolves its account and marketplace through the one helper, rather
# than writing that resolution out again.
#
# Again the call form: "def _push_target():" contains "_push_target()" too.
check("both push sites go through it",
      RT.count("refuse = _push_target()"), 2)

print("\n=== the browser names its account on all three actions ===")
truthy("there is one scope builder", "function _handlingScope(" in JS)
truthy("  reading the account the page is showing", "CUR_ACCOUNT.id" in JS)
# "__all__" is not a marketplace -- see the all-marketplaces note. Sending it
# would make the server resolve a marketplace from a sentinel.
truthy("  and never sending __all__ as a marketplace",
       'WS_MARKET !== "__all__"' in JS)
truthy("handling time sends it", "_handlingScope(), body" in JS)
truthy("stock sends it", JS.count("Object.assign(_handlingScope(), body)") == 2)
truthy("price sends it", "const body = _handlingScope;" in JS)
# It was written out by hand in bulkPricePercent while the other two sent
# nothing at all. ONE place reads CUR_ACCOUNT.id now, and it is the helper --
# asserting the copy is "gone" by pattern would also match the helper itself,
# which is exactly the line that is supposed to survive.
_reads = len(re.findall(r"id:\s*\(typeof CUR_ACCOUNT", JS))
check("only one place builds that id", _reads, 1)
truthy("  and it is _handlingScope",
       "typeof CUR_ACCOUNT" in JS.split("function _handlingScope(")[1][:400])

print("\n=== validation still runs BEFORE any of this ===")
# A bad number must never reach Amazon, whichever account it would have gone to.
_st = RT.split("def stock_bulk_update")[1].split("@app.route")[0]
i_qty = _st.find("cannot be negative")
i_scope = _st.find("_push_target()")
truthy("the quantity is checked before the account is even resolved",
       0 < i_qty < i_scope)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
