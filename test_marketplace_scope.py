"""A US account must never be answered about the United Kingdom.

WHAT WAS MEASURED, 21 Aug 2026. Each account selected in turn, then the Finance
screen asked for the last 30 days:

    Sheelady (USA)     marketplaces ["MX","CA","BR","US"], default US
                       -> "No finance data has ever been pulled for
                           Sheelady (USA) on UK"
    Miles Lubricants   default US                    -> "...on UK"
    Headbanger Lures   no marketplaces, no default   -> "...on UK"

UK is not one of Sheelady's marketplaces. That was not a judgement call between
several candidates: it named a country the account does not sell in, and then
said "no data" -- which reads as "you have no sales", not as "I looked in the
wrong place". routes/scope.py's own docstring says it: "defaulting to 'UK' gives
a US account a confident answer about the wrong country". The literal default
was not the only way to arrive there.

TWO CAUSES, AND THE SECOND IS THE ONE THAT MATTERED.

  1. static/js/finance.js sent only the dates. The page knows the account and
     the marketplace -- every other money screen says so -- and this page of
     money did not, so the server fell back to its own globals.

  2. _state["active_marketplace"] is ONE VARIABLE FOR THE WHOLE SERVER, and 44
     places across 20 route files fall back to it. /accounts/select kept
     whatever was in it when the page named no marketplace -- and what was in it
     belonged to the account being switched AWAY from. So one stale value
     answered for all 44 at once.

Fixed at the source rather than at 44 call sites: the selected marketplace is
cleared on switching to an account that does not sell there, so each of those
fallbacks reaches the account's OWN default next. A marketplace the account does
sell in is kept exactly as before -- the case that happens when somebody
switches marketplace and then switches account.
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
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return open(os.path.join(HERE, *p), encoding="utf-8").read()


from routes import scope as S

# The real shapes, from config.json as it stands.
JACK = {"id": "jack_uk", "default_marketplace": "UK",
        "marketplaces": ["FR", "NL", "PL", "UK", "DE", "ES", "IE", "SE", "BE", "IT"]}
US = {"id": "sheelady_us", "default_marketplace": "US",
      "marketplaces": ["MX", "CA", "BR", "US"]}
MILES = {"id": "miles_lubricants", "default_marketplace": "US", "marketplaces": []}
BARE = {"id": "headbanger_lures", "marketplaces": []}

print("== the selected marketplace only counts if the account sells there ==")
CASES = [
    ("a US account, with the global stuck on UK", US, "UK", None, "US"),
    ("  the same account on one it DOES sell in", US, "CA", None, "CA"),
    ("a UK account on one it does sell in", JACK, "DE", None, "DE"),
    ("  and on one it does not", JACK, "US", None, "UK"),
    ("what the page asked for always wins", US, "UK", "CA", "CA"),
    ("  even when the page is wrong -- it is the page's screen", JACK, "UK", "JP", "JP"),
    ("no list, but a default of its own", MILES, "UK", None, "US"),
    ("no list and no default: unchanged, the global stands", BARE, "UK", None, "UK"),
    ("nothing known anywhere", BARE, "", None, ""),
    ("no global: the account's default", US, "", None, "US"),
    ("lower case in the state still matches", US, "us", None, "US"),
    ("whitespace does not defeat it", US, "  UK  ", None, "US"),
]
for label, acc, glob, asked, want in CASES:
    check(label, S.marketplace(state={"active_marketplace": glob},
                               account=acc, asked=asked), want)

print("\n== and the workspace id is unaffected ==")
check("the request wins", S.workspace_id(state={"active_account_id": "a"},
                                         account={"id": "b"}, asked="c"), "c")
check("  then the account", S.workspace_id(state={"active_account_id": "a"},
                                           account={"id": "b"}), "b")
check("  then the global", S.workspace_id(state={"active_account_id": "a"}), "a")

print("\n== the last resort is still only used when there is ONE ==")
seen = []


def _one(wsid):
    seen.append(wsid)
    return "PL"


check("with_data is consulted when nothing else knows",
      S.marketplace(state={}, account=BARE, with_data=_one), "PL")
check("  and it was asked about the right workspace", seen, ["headbanger_lures"])
check("it is NOT consulted when the account has a default",
      S.marketplace(state={}, account=US, with_data=lambda w: "PL"), "US")

print("\n== switching account cannot carry a marketplace it does not sell in ==")
A = read("routes", "accounts_routes.py")
_sel = A.split("def accounts_select")[1].split("\n    @app.route")[0]
truthy("the select route checks what the account sells", "marketplaces" in _sel)
truthy("  and clears a marketplace that is not one of them",
       '_state["active_marketplace"] = _kept' in _sel)
truthy("  while an explicitly named one is taken as given",
       '_state["active_marketplace"] = _mkt_asked' in _sel)
falsy("  the old carry-forward is gone",
      'b.get("marketplace", "") or _state.get("active_marketplace", "")' in _sel)
truthy("  and an account that lists none but names a default wins too",
       'if not _sells and str(_a0.get("default_marketplace")' in _sel)

print("\n== the Finance page says whose money it is showing ==")
F = read("static", "js", "finance.js")
_load = F.split("async function financeLoad")[1].split("\nfunction ")[0]
truthy("it sends the account", 'qs.push("id=" + encodeURIComponent(CUR_ACCOUNT.id))' in _load)
truthy("  and the marketplace", '"marketplace=" + encodeURIComponent(WS_MARKET)' in _load)
truthy("  and does not send __all__ as if it were one", 'WS_MARKET !== "__all__"' in _load)
truthy("  guarded, so an unloaded shell does not throw",
       'typeof CUR_ACCOUNT !== "undefined"' in _load
       and 'typeof WS_MARKET !== "undefined"' in _load)

print("\n== against the real config, this is not hypothetical ==")
import json
try:
    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    accs = {str(a.get("id")): a for a in (cfg.get("accounts") or [])}
    us = accs.get("sheelady_us")
    if us:
        mk = {str(m).upper() for m in (us.get("marketplaces") or [])}
        falsy("sheelady_us really does not sell in the UK", "UK" in mk)
        check("  and its own default is US",
              str(us.get("default_marketplace") or "").upper(), "US")
        check("  so with the global on UK it now resolves to US",
              S.marketplace(state={"active_marketplace": "UK"}, account=us), "US")
    # No account may be left resolving to a marketplace it does not sell in.
    wrong = []
    for aid, a in accs.items():
        mk = {str(m).upper() for m in (a.get("marketplaces") or [])}
        if not mk:
            continue
        got = S.marketplace(state={"active_marketplace": "UK"}, account=a)
        if got and got not in mk:
            wrong.append((aid, got))
    check("no configured account resolves outside its own marketplaces",
          sorted(wrong), [])
    print("     (%d accounts checked)" % len(accs))
except FileNotFoundError:
    print("  (no config.json on this machine)")

print("\n== 'no marketplace' is said, not guessed ==")
truthy("there is one sentence for it", "Pick one" in S.NO_MARKETPLACE)
truthy("  naming what to do, not what is missing",
       "default marketplace" in S.NO_MARKETPLACE)
# The account with neither now gets THAT, instead of a confident answer about a
# country it has never sold in.
check("an account with no marketplace and no default resolves to nothing",
      S.marketplace(state={}, account=BARE), "")

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
