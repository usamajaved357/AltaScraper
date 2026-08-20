"""Enumerate the account-scoped routes; do not sample them.

The principle that keeps producing these: THE HOLE THAT SURVIVES A FIX IS THE
ONE NEXT DOOR. /orders/list was guarded and /orders/items was not. /rows_all was
guarded and /row was not. Both pairs are reached from the same screen, one
keystroke apart.

So this test does what a person reading route-by-route cannot reliably do: it
walks every @app.route in the app and fails if a NEW one appears with the hole
shape. That shape is precise, and it is narrower than "mentions an account":

    the route takes an account id FROM THE CALLER
      AND resolves THAT account's own Amazon credentials with it
      AND never checks it against the account that is open

A route that reads the OPEN account from server state is a weaker case -- it can
be stale, but a caller cannot choose the target. A route whose PURPOSE is to act
on another account (the /accounts/* setup screens) is not a hole at all, and is
listed as a deliberate exception rather than silently skipped.

WHY IT MATTERS MORE NOW THAN IT DID. While every configured account belonged to
one owner this was a correctness bug about stale state. Multi-tenant OAuth puts
OTHER PEOPLE'S selling accounts in the same config, so "any configured account"
stops meaning "one of ours". /optimize/push calls patchListingsItem; naming
another account there edits their live listings.
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
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


ROUTE_RE = re.compile(r'@app\.route\(\s*"([^"]+)"(?:\s*,\s*methods\s*=\s*(\[[^\]]*\]))?')

CALLER_SAYS = ('b.get("id"', "b.get('id'", 'b.get("account', "b.get('account",
               'request.args.get("account', 'request.args.get("id',
               'get("account_id"', "get('account_id'")
USES_IT = ("get_account(", "account_creds(", "resolve_catalog_creds(",
           "_seller_creds(", "_sp_creds(")
GUARDED = ("_wrong_account(", "_refuse_other_account(", "is_mismatch(",
           "_acctscope.is_mismatch", "account_mismatch")

# DELIBERATE EXCEPTIONS, each with the reason it is not a hole.
EXEMPT = {
    # Account setup legitimately targets an account that is NOT open -- that is
    # the entire point of the screen where you configure a new one.
    "/accounts/select": "its job is to change which account is open",
    "/accounts/list": "lists all accounts by design",
    "/accounts/save": "account setup",
    "/accounts/delete": "account setup",
    "/accounts/add": "account setup",
    "/accounts/test": "account setup",
    "/accounts/detect_marketplaces": "account setup, before the account is open",
    "/accounts/detect_brands": "account setup, before the account is open",
    "/accounts/set_default_marketplace": "account setup",
    "/accounts/remove_brand": "account setup",
    "/accounts/brands": "account setup",
    # The signed token IS the authorisation: it is an HMAC over the path, so a
    # caller cannot ask for a file it was not given a token for.
    "/img/<token>/<path:relpath>": "HMAC token in the URL is the guard",
}

files = []
for d in (".", "routes"):
    for f in sorted(os.listdir(os.path.join(HERE, d))):
        if f.endswith(".py") and not f.startswith(("test_", "probe_")) \
           and "baseline" not in f:
            files.append(os.path.join(d, f))

holes, guarded_count, exempt_seen = [], 0, set()
for path in files:
    try:
        src = open(os.path.join(HERE, path), encoding="utf-8").read()
    except Exception:
        continue
    lines = src.splitlines()
    marks = [(i, m.group(1), m.group(2) or "[GET]")
             for i, l in enumerate(lines) for m in [ROUTE_RE.search(l)] if m]
    for n, (i, rule, methods) in enumerate(marks):
        end = marks[n + 1][0] if n + 1 < len(marks) else len(lines)
        body = "\n".join(lines[i:end])
        if not any(c in body for c in CALLER_SAYS):
            continue
        if not any(u in body for u in USES_IT):
            continue
        if any(g in body for g in GUARDED):
            guarded_count += 1
            continue
        if rule in EXEMPT:
            exempt_seen.add(rule)
            continue
        holes.append((rule, methods.strip(), path))

print("== every route that takes an account from the caller is accounted for ==")
print("  guarded: %d   deliberately exempt: %d   unguarded: %d"
      % (guarded_count, len(exempt_seen), len(holes)))
if holes:
    print("\n  UNGUARDED:")
    for rule, methods, path in sorted(holes):
        print("    %-34s %-14s %s" % (rule, methods[:14], path))
check("no route takes an account from the caller without checking it", holes, [])

print("\n== the routes that write to Amazon are guarded by name ==")
# Named individually because these are the ones where being wrong is not a
# display bug: they change somebody's live shopfront.
OPT = open(os.path.join(HERE, "routes", "optimize_routes.py"), encoding="utf-8").read()
LR = open(os.path.join(HERE, "routes", "listing_routes.py"), encoding="utf-8").read()
LIVE = open(os.path.join(HERE, "routes", "live_routes.py"), encoding="utf-8").read()
truthy("optimize has one guard", "def _wrong_account(" in OPT)
check("  applied to all four of its routes",
      OPT.count('_bad = _wrong_account(b.get("id"))'), 4)
truthy("  and it says why push is the worst of them",
       "EDITS THEIR" in OPT and "LIVE LISTINGS" in OPT)
truthy("push_image is guarded", '_bad = _wrong_account(b.get("id"), "listing")' in LR)
truthy("live has one guard", "def _wrong_account(" in LIVE)
truthy("  applied across its routes",
       LIVE.count('_bad = _wrong_account(b.get("id"))') >= 5)

print("\n== all of them go through the one shared rule ==")
# Four route files now ask this question. If each had its own comparison there
# would be four chances for them to disagree about who may see whose data.
for f in ("routes/optimize_routes.py", "routes/live_routes.py",
          "routes/listing_routes.py", "routes/orders_routes.py",
          "routes/inventory_routes.py"):
    s = open(os.path.join(HERE, f), encoding="utf-8").read()
    truthy("%s uses domain/account_scope" % os.path.basename(f),
           "from domain import account_scope" in s)

print("\n== and silence is still not a mismatch ==")
# Every one of these guards had to be safe to add ahead of its callers.
AS = open(os.path.join(HERE, "domain", "account_scope.py"), encoding="utf-8").read()
truthy("a caller that names no account is served", "if asked is None:" in AS)
truthy("  and that is deliberate, not incidental",
       "SILENCE IS NOT A MISMATCH" in AS)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
