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
# THE PROPERTY, NOT THE MECHANISM. What must hold is that one account's
# customers never appear under another's name. It used to be enforced by
# comparing the request against a process-wide "selected account", which broke
# the moment a second tab was open. It is enforced by auth/guard.py now --
# the named account is checked against the user's own workspace list -- so the
# assertions below check THAT, and check that orders still routes through the
# one shared rule rather than growing its own again.
import auth.guard as _G, auth.users as _U
truthy("a named account is checked against the user's workspaces",
       "account" in _G.WORKSPACE_PARAMS)
truthy("  and a user scoped elsewhere is refused",
       not _U.can_access_workspace({"active": True,
                                    "workspaces": ["nestwell_goods"]},
                                   "jack_uk"))
truthy("  a refusal is still an error, not rows", '"account_mismatch": True' in OR)
truthy("  naming what was asked for", '"asked_for"' in OR)
truthy("  and what is actually open", '"selected"' in OR)
truthy("  and orders still uses the one shared rule",
       "from domain import account_scope" in OR)
truthy("  as a 409, so it cannot be mistaken for an empty account", "), 409" in OR)
# The refusal must say WHY in words somebody can act on.
truthy("  an account this app does not have is still refused",
       "There is no account called" in OR)

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

print("\n== the two routes the first fix missed ==")
# Found by READING the routes after the browser could not reproduce it.
# /orders/list was hardened; /orders/items and /orders/detail were reached by
# the SAME screen one keystroke later and were not. Both took the account from
# the caller and then used THAT account's own Amazon credentials.
truthy("there is one authority for whose orders these are",
       "def _open_account_id():" in OR)
truthy("  and one refusal, shared", "def _refuse_other_account(" in OR)
truthy("the items batch checks every row",
       "_refuse_other_account(w.get(\"account_id\"))" in OR)
truthy("  before any of them is fetched",
       OR.index("_refuse_other_account(w.get(\"account_id\"))")
       < OR.index("items = _items_for(oid, aid,"))
truthy("the detail route checks too", "_bad = _refuse_other_account(aid)" in OR)
# It returns the buyer's town and postcode, so it must refuse BEFORE calling
# Amazon, not after.
truthy("  before Amazon is called at all",
       OR.index("_bad = _refuse_other_account(aid)") < OR.index("oc.get_order_items(oid)"))
# THE WORDING MOVED, THE REFUSAL DID NOT. The comparison and the message now
# live in domain/account_scope.py -- this rule was written out here AND in
# listing_routes.py, from the same defect found twice, and a rule about who may
# see whose data is the worst thing to keep two copies of (rule 12). What is
# asserted here is that this route still refuses and still explains; what the
# explanation says is asserted once, where it now lives.
AS = open(os.path.join(HERE, "domain", "account_scope.py"), encoding="utf-8").read()
truthy("  and it says why it refused", "_scope.refusal(asked," in OR)
truthy("  from the one shared rule", "from domain import account_scope" in OR)
truthy("  which names both accounts", '"asked_for"' in AS and '"selected"' in AS)
truthy("  and says nothing was read or changed",
       "nothing was read or changed" in AS)
truthy("  and why that is the safe answer",
       "under another's name" in AS)
# Silence must not be a mismatch, or adding the guard to a route would break
# every caller that has not been taught to send an account yet.
truthy("a caller that names no account is unaffected",
       "return False" in AS)
truthy("  and the change is explained where the rule lives",
       "WHY DROPPING IT IS SAFE" in AS)

print("\n== and the doorman can now see an account named inside a list ==")
# THE SYSTEMIC ONE. named_workspace read TOP-LEVEL fields only, so a request
# that names its account per-row named nothing as far as the guard was
# concerned and NO workspace check ran -- meaning a user restricted to one
# account could read another's order contents by posting the batch shape.
import sys as _sys
_sys.path.insert(0, HERE)
from auth import guard as _G

check("a top-level query id is still found",
      _G.named_workspace("/trackers", {"id": "jack_uk"}, None), "jack_uk")
check("  and a top-level body id",
      _G.named_workspace("/x", {}, {"account_id": "jack_uk"}), "jack_uk")
check("an account nested in a list of rows is found",
      _G.named_workspace("/orders/items", {},
                         {"orders": [{"order_id": "1", "account_id": "jack_uk"}]}),
      "jack_uk")
check("  wherever in the batch it appears",
      _G.named_workspace("/orders/items", {},
                         {"orders": [{"order_id": "1"},
                                     {"account_id": "nestwell_goods"}]}),
      "nestwell_goods")
# And it must not start seeing accounts that are not there.
check("a batch naming no account still names none",
      _G.named_workspace("/orders/items", {}, {"orders": [{"order_id": "1"}]}), "")
check("  a list of plain strings is not an account",
      _G.named_workspace("/x", {}, {"skus": ["a", "b"]}), "")
check("  and the exempt paths stay exempt",
      _G.named_workspace("/users/save", {"id": "someuser"}, None), "")

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
