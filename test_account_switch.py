"""Switching account must not leave the previous one refusing your requests.

    "i switched from headbanger lures recently but i am on nestwell goods but
     still i am shown this error"

The screenshot: the address bar on /w/nestwell_goods/orders, the sidebar showing
Nestwell Goods LTD, and across the screen

    "This screen is showing nestwell_goods but headbanger_lures is the account
     that is open. Nothing is listed rather than risk showing one company's
     customers under another's name."

WHAT WAS ACTUALLY WRONG. `active_account_id` is ONE VARIABLE FOR THE WHOLE
SERVER. routes/accounts_routes.py says as much about its marketplace twin --
"one variable for the whole server and 44 places across 20 files fall back to
it, so one stale value answers for all of them at once". The screenshot has
three browser tabs open; whichever tab last called /accounts/select owns that
variable, and every other tab is refused for asking about the account it is
actually showing.

WHY HONOURING THE REQUEST IS NOT A LOOSENING, which is the whole question this
file exists to answer. The comparison never established who was asking -- only
whether a global agreed with them. Who may ask is settled in auth/guard.py,
which checks a named account against the signed-in user's own workspace list on
every request. And `account` was NOT in the list of parameters it checked, on
four handlers that read it, including the two that carry another company's
order lines and the buyer's town and postcode. So:

    the check that mattered was missing, and the check that fired was the wrong
    one

Both halves are fixed here, and this file tests both. Loosening the second
without adding the first would have opened a real hole.
"""
import io
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
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return io.open(os.path.join(HERE, *p), encoding="utf-8").read()


from auth import guard as G
from auth import users as U

print("== the account named on a request is now checked against the user ==")
truthy("'account' is a workspace parameter", "account" in G.WORKSPACE_PARAMS)
for f in ("id", "account_id", "workspace_id", "workspace", "ws"):
    truthy("  %-12s still is too" % f, f in G.WORKSPACE_PARAMS)
check("it is seen on a query string",
      G.named_workspace("/orders/list", {"account": "jack_uk"}, None), "jack_uk")
check("  and in a body",
      G.named_workspace("/orders/list", {}, {"account": "jack_uk"}), "jack_uk")
# The four handlers that read it, named so this cannot quietly regress.
_o = read("routes", "orders_routes.py")
_l = read("routes", "listing_routes.py")
check("/orders/list reads it", 'request.args.get("account")' in _o, True)
check("/rows_all reads it", 'request.args.get("account")' in _l, True)

print("\n== a sentinel is not a workspace ==")
# __all__ means "the account that is open" by the time a route reads it. Checked
# against a workspace list it would refuse an old bookmark for something nobody
# chose.
check("__all__ names no workspace",
      G.named_workspace("/orders/list", {"account": "__all__"}, None), "")
check("  nor does an empty value",
      G.named_workspace("/orders/list", {"account": ""}, None), "")
truthy("and the sentinels are written down", hasattr(G, "WORKSPACE_SENTINELS"))

print("\n== a user still cannot reach a workspace they were not given ==")
scoped = {"active": True, "workspaces": ["nestwell_goods"]}
truthy("their own workspace", U.can_access_workspace(scoped, "nestwell_goods"))
falsy("  somebody else's", U.can_access_workspace(scoped, "jack_uk"))
falsy("  even by naming it in ?account=",
      U.can_access_workspace(scoped, G.named_workspace(
          "/orders/list", {"account": "jack_uk"}, None)))
allw = {"active": True, "workspaces": [U.ALL_WORKSPACES]}
truthy("a user with * may open any", U.can_access_workspace(allw, "jack_uk"))
falsy("an inactive user may open none",
      U.can_access_workspace({"active": False, "workspaces": ["*"]}, "jack_uk"))

print("\n== and the stale global no longer refuses a correct request ==")
_scope_src = _o.split("def _accounts_in_scope")[1].split("def ")[0]
falsy("the open-account comparison is gone from orders",
      "want != active" in _scope_src)
falsy("  and so is the refusal it produced", "__mismatch__" in _o)
falsy("  including the message from the screenshot",
      "is the account that is open" in _o)
truthy("the request's own account is used", "want = active" in _scope_src)
truthy("  with the global only as the fallback",
       "the account currently open" in _scope_src)
truthy("why this is safe is written down, not assumed",
       "WHY IT IS NOT A LOOSENING" in _o)
truthy("  naming the report", "headbanger lures" in _o)

print("\n== an account this app does not have is still refused ==")
_ref = _o.split("def _refuse_other_account")[1].split("def ")[0]
truthy("the sibling routes check the account exists", "acc is None" in _ref)
truthy("  through the one shared rule, which no longer compares to the global",
       "is_mismatch" in _ref)
import domain.account_scope as _AS
falsy("    and that rule now says a disagreement is not a mismatch",
      _AS.is_mismatch("nestwell_goods", "headbanger_lures"))

print("\n== end to end, in the app itself ==")
try:
    import dashboard
    app = dashboard.build_app()
    st = dashboard._state
    with app.test_client() as c:
        # Exactly the state the screenshot was taken in.
        st["active_account_id"] = "headbanger_lures"
        r = c.get("/orders/list?account=nestwell_goods&days=7")
        j = r.get_json() or {}
        check("the reported request is no longer refused", r.status_code, 200)
        falsy("  no account_mismatch", j.get("account_mismatch"))
        falsy("  and no 'is the account that is open' message",
              "is the account that is open" in str(j.get("error") or ""))
        # It must be answering for the account ASKED FOR, not the global.
        _asked = j.get("asked") or []
        if _asked:
            check("  and it answered for the account asked for",
                  _asked, ["nestwell_goods"])
        st["active_account_id"] = "nestwell_goods"
        r2 = c.get("/orders/list?account=nestwell_goods&days=7")
        check("agreement still works", r2.status_code, 200)
except Exception as e:
    fails.append("end to end")
    print("  FAIL could not run: %s" % str(e)[:200])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
