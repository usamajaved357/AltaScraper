"""One company's customers must never appear under another's name.

    "i see the orders of nestwell goods are shown in the jack reacherd account,
     and i am not able to see the jack reacherds orders, i was not able to see
     the jacks orders until i switched to nestwell goods and then again
     switched back"

WHAT THE MEASUREMENT ACTUALLY SHOWED. Selecting each account in turn and
fetching /orders/list returned only that account's rows, repeatably:

    nestwell_goods  23 rows, all Nestwell
    jack_uk          5 rows, all Jack
    nestwell_goods  23 rows, all Nestwell
    jack_uk          5 rows, all Jack

So the server was right, and every client guard was in place too. The hole was
subtler and worse: the browser sent an EMPTY account and let the server decide.
With nothing named, the two could never disagree OUT LOUD -- and if they ever
did, the server quietly won and the screen drew another company's customers
under the open account's name with nothing to indicate it.

A screen cannot be trusted to notice a mistake it is not told about. So the
account now travels with the request, a disagreement is a 409 rather than a
silent decision, and the answer is checked again in the browser before it is
drawn. Three chances to notice instead of none.

This matters more than an ordinary bug: these are separate limited companies,
and the rows carry real customers' names, towns and postcodes.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


OR = open(os.path.join(HERE, "routes", "orders_routes.py"), encoding="utf-8").read()
JS = open(os.path.join(HERE, "static", "js", "orders.js"), encoding="utf-8").read()

print("== the browser names the account it is drawing ==")
truthy("it no longer sends an empty account",
       "const askedFor = ORD.account" in JS)
truthy("  falling back to the open workspace, not to blank",
       "ACTIVE_WS.key" in JS and "askedFor" in JS)
truthy("  and sends it", "&account=\" + encodeURIComponent(askedFor)" in JS)

print("\n== and the server refuses to answer for a different one ==")
truthy("a mismatch is detected", "want != active" in OR)
truthy("  and returned as an error, not as rows", '"account_mismatch": True' in OR)
truthy("  naming what was asked for", '"asked_for"' in OR)
truthy("  and what is actually open", '"selected"' in OR)
truthy("  with no rows at all", '"rows": [],' in OR)
truthy("  as a 409, so it cannot be mistaken for an empty account", "), 409" in OR)
# The refusal must say WHY in words somebody can act on.
truthy("  and it explains rather than just failing",
       "one company's customers under another's" in OR)

print("\n== the browser checks the answer as well ==")
truthy("a mismatch reply is shown, never rendered as rows",
       "j.account_mismatch" in JS)
# The load ticket catches a newer LOAD. An account can change without one --
# the fetch takes the best part of a minute.
truthy("the workspace is re-checked after the wait",
       "askedFor !== nowWs" in JS)
truthy("  and the rows are stamped with whose they are",
       "ORD.rowsFor = nowWs || askedFor" in JS)

print("\n== the escape hatch stays shut ==")
# Honouring an explicit account would BE the leak. The only account accepted is
# the one already open; anything else is refused rather than served.
truthy("__all__ still means the open account", 'want == "__all__"' in OR)
truthy("  an unresolvable account returns none, not all",
       "MEANS NONE, NOT ALL" in OR)
falsy("  and there is still no account picker",
       "ord_account_picker" in JS)

print("\n== what the measurement found, recorded where the fix is ==")
truthy("the report is quoted beside the code",
       "orders of nestwell goods are shown in the jack reacherd" in OR)
truthy("  and so is what was actually measured",
       "only its own rows, repeatably" in OR)

print("\n== and a foreign row is never painted, whatever put it there ==")
# The only guard that does not depend on any of the others being right. Measured
# on this build across four account switches in a real browser: every row
# already belonged to the open account, so it drops nothing today. It is here so
# that it keeps dropping nothing tomorrow.
truthy("the render drops rows from another account", "rid !== _openWs" in JS)
truthy("  and says so rather than tidying up quietly",
       "belonging to another account" in JS)
truthy("  asking for it to be reported", "should not happen" in JS)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
