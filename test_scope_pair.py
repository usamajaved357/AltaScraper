"""The marketplace follows the account the PAGE named -- routes/scope.pair.

Ten route files (category, asin_studio, catalog_page, compliance, drppc,
keywords, leading, sqp, tracker, daily) each resolved (account, marketplace)
for themselves, and every copy filled a missing marketplace from the server's
OPEN account. With jack_uk open in one tab, a screen showing sheelady_us asked
?account=sheelady_us and was answered on jack's default -- the United Kingdom,
a country sheelady does not sell in.

No config file, no database, no network: the accounts are a dict in memory.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask

from routes import scope

CFG = {"accounts": [
    {"id": "jack_uk", "default_marketplace": "UK", "marketplaces": ["UK", "DE"]},
    {"id": "sheelady_us", "default_marketplace": "US",
     "marketplaces": ["US", "CA", "MX"]},
    {"id": "bare"},
]}
OPEN = {"id": "jack_uk", "default_marketplace": "UK", "marketplaces": ["UK", "DE"]}

app = Flask(__name__)
fails = 0
ran = 0


def check(label, got, want):
    global fails, ran
    ran += 1
    ok = got == want
    if not ok:
        fails += 1
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def ask(url, state=None, body=None, last_resort="UK"):
    kw = {"json": body} if body is not None else {}
    with app.test_request_context(url, method="POST" if body is not None else "GET", **kw):
        from flask import request
        return scope.pair(request, state=state or {"active_account_id": "jack_uk"},
                          active_account=lambda: OPEN, cfg=lambda: CFG,
                          config_path=None, last_resort=last_resort)


print("\n1. the named account's own marketplace, not the open one's")
check("?account=sheelady_us with jack_uk open", ask("/x?account=sheelady_us"),
      ("sheelady_us", "US"))
check("legacy ?id= spelling", ask("/x?id=sheelady_us"), ("sheelady_us", "US"))
check("body id on a POST", ask("/x", body={"id": "sheelady_us"}), ("sheelady_us", "US"))
check("selected UK is ignored where sheelady does not sell",
      ask("/x?account=sheelady_us",
          state={"active_account_id": "jack_uk", "active_marketplace": "UK"}),
      ("sheelady_us", "US"))

print("\n2. what the page asked for still wins")
check("?marketplace=CA", ask("/x?account=sheelady_us&marketplace=CA"), ("sheelady_us", "CA"))
check("body marketplace on a POST",
      ask("/x", body={"id": "sheelady_us", "marketplace": "MX"}), ("sheelady_us", "MX"))
check("__all__ is not a country",
      ask("/x?account=sheelady_us&marketplace=__all__"), ("sheelady_us", "US"))

print("\n3. nothing named -> the open account, as before")
check("no account, no marketplace", ask("/x"), ("jack_uk", "UK"))
check("selected DE where jack sells",
      ask("/x", state={"active_account_id": "jack_uk", "active_marketplace": "DE"}),
      ("jack_uk", "DE"))

print("\n4. the last resort is the caller's, and visible")
check("unknown named account, nothing else -> the caller's guess",
      ask("/x?account=ghost", state={}), ("ghost", "UK"))
check("unknown account never borrows the open account's default",
      ask("/x?account=ghost", state={}, last_resort=""), ("ghost", ""))
check("account with no marketplace at all, honest caller",
      ask("/x?account=bare", state={}, last_resort=""), ("bare", ""))

print("\n4b. a GET body never names the account (the guard does not read it)")
with app.test_request_context("/x", method="GET", json={"account": "sheelady_us"}):
    from flask import request as _rq
    check("GET body account is ignored",
          scope.pair(_rq, state={"active_account_id": "jack_uk"},
                     active_account=lambda: OPEN, cfg=lambda: CFG,
                     config_path=None, last_resort="UK"),
          ("jack_uk", "UK"))

print("\n4c. the data fallback is asked about the NAMED account, never the open one")
asked_for = []
with app.test_request_context("/x?account=ghost", method="GET"):
    from flask import request as _rq2
    got = scope.for_request(_rq2, state={"active_account_id": "jack_uk"},
                            active_account=lambda: OPEN, cfg=lambda: CFG,
                            config_path=None,
                            with_data=lambda w: (asked_for.append(w), "DE")[1])
check("with_data was asked about 'ghost'", asked_for, ["ghost"])

print("\n5. no copy of the old resolver is left in the ten files")
HERE = os.path.dirname(os.path.abspath(__file__))
left = []
for m in ("category", "asin_studio", "catalog_page", "compliance", "drppc",
          "keywords", "leading", "sqp", "tracker", "daily"):
    src = open(os.path.join(HERE, "routes", m + "_routes.py"), encoding="utf-8").read()
    body = src.split("    def _scope(")[1].split("\n    def ")[0].split("\n    @app")[0]
    if "_scope_mod.pair(" not in body or "active_marketplace" in body:
        left.append(m)
check("every _scope calls scope.pair", left, [])

print("\n6. the Repricer reads the account the page named (it sends ?account=)")
SR = open(os.path.join(HERE, "routes", "sourcing_routes.py"), encoding="utf-8").read()
where = SR.split("    def _where():")[1].split("\n    def ")[0]
check("_where goes through scope.for_request", "_scope_mod.for_request(" in where, True)
check("  and no longer reads only ?id=", 'request.args.get("id")' in where, False)
where_acc = SR.split("    def _where_acc():")[1].split("\n    def ")[0]
check("an unknown named account never borrows the open one's record",
      "or (_active_account() or {})" in where_acc, False)

print("\n%d checks, %d failed" % (ran, fails))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
