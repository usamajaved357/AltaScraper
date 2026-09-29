# -*- coding: utf-8 -*-
"""routes/scope.page_account and ads_account (29 Sep 2026).

Two pairs of route files each carried an identical `_scope` (Sales + Ads;
PPC Analytics + Live Tracker); the architecture guard's duplicate-function
rule found them and they became one function each. Pins the behaviour they
had: the account the page names wins; with none, the open one; advertising
never answers "all marketplaces" but uses the account's own default; and the
four routes call the shared copies (a new copy would fail the guard).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


from routes import scope as S                  # noqa: E402


class Req:
    def __init__(self, args=None, body=None):
        self.args = args or {}
        self._b = body or {}

    def get_json(self, silent=True):
        return self._b


class RA:                                     # a stand-in for domain.request_account
    @staticmethod
    def named(req):
        return req.args.get("account", "")

    @staticmethod
    def for_read(req, state, get_account=None):
        aid = req.args.get("account", "")
        return aid, (get_account(aid) if aid else None)


CFG = {"accounts": [{"id": "a1", "default_marketplace": "DE", "marketplaces": ["DE", "FR"]},
                    {"id": "a2", "marketplaces": ["US"]}]}
state = {"active_account_id": "a2", "active_marketplace": "US"}
open_acc = lambda: {"id": "a2", "marketplaces": ["US"]}          # noqa: E731

print("== ads_account (PPC Analytics, Live Tracker) ==")
check("the named account wins over the open one",
      S.ads_account(Req({"account": "a1", "marketplace": "FR"}), state=state,
                    active_account=open_acc, cfg=lambda: CFG, req_acct=RA), ("a1", "FR"))
check("'all marketplaces' becomes the account's own default",
      S.ads_account(Req({"account": "a1", "marketplace": "__all__"}), state={},
                    active_account=open_acc, cfg=lambda: CFG, req_acct=RA), ("a1", "DE"))
check("  and with no default, its first marketplace",
      S.ads_account(Req({"account": "a2"}), state={}, active_account=open_acc,
                    cfg=lambda: CFG, req_acct=RA), ("a2", "US"))
check("none named -> the open account, as before",
      S.ads_account(Req({}), state=state, active_account=open_acc, cfg=lambda: CFG, req_acct=RA), ("a2", "US"))

print("\n== page_account (Sales, Ads) ==")
get = lambda aid: next((a for a in CFG["accounts"] if a["id"] == aid), None)   # noqa: E731
acc, wsid, mkt = S.page_account(Req({"account": "a1", "marketplace": "FR"}), state=state,
                                active_account=open_acc, get_account=get, req_acct=RA)
check("the named account and asked marketplace", (acc["id"], wsid, mkt), ("a1", "a1", "FR"))
acc, wsid, mkt = S.page_account(Req({}), state={}, active_account=lambda: None, get_account=get, req_acct=RA)
check("nothing named and nothing open -> _no_account", wsid, "_no_account")

print("\n== the four routes use the one copy ==")
for f, fn in (("ads_routes", "page_account"), ("sales_routes", "page_account"),
              ("ppc_analytics_routes", "ads_account"), ("live_tracker_routes", "ads_account")):
    src = open(os.path.join(HERE, "routes", f + ".py"), encoding="utf-8").read()
    check("%s calls scope.%s" % (f, fn), "_scope_mod.%s(request" % fn in src, True)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
