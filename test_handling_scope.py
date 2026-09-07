"""A handling-time change has to be recorded on the account it was made on.

    "i clicked on the handling time changed it to 2 so that the app and amazon
     hold the same number, i did this multiple time in the past with days of
     break in between but still app shows 3, it is not changing to 2"

TWO HALVES OF ONE ACTION WENT TO TWO DIFFERENT PLACES.

/handling/bulk_update does two things: it patches lead_time_to_ship_max_days on
Amazon, and it records the number on the app's own row. The push resolved the
account from the REQUEST -- routes/scope.resolve, added precisely because "the
owner routinely has four browser tabs open ... whichever tab last switched
account owns that variable and every other tab pushes to it". The recording did
not: it called _ws(), the workspace the SERVER has open.

So Amazon could get the new number for the right listing while the local record
went to another company's rows, and the listing on screen kept the old value
however many times the button was pressed.

MEASURED on nestwell_goods, 7 Sep 2026: Amazon holds lead time 2 on all 40 live
listings; the app held 3 on 56 of its 86 rows, and on 4 of the 7 live listings
it has a row for. The store write itself is fine -- writing a value back through
listing.repo.set_field and reading it again returns it -- so the fault was never
the store.
"""
import ast
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
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


print("=== one answer to 'which store belongs to this account' (Rule 12) ===")
from data import backend as B

truthy("data/backend owns it", hasattr(B, "store_for"))
check("no account named -> nothing, rather than a guess",
      B.store_for("", {}, None), None)
check("  and None is not an account either", B.store_for(None, {}, None), None)
# Off the database backend it declines, so a sheets install keeps the behaviour
# it had rather than losing its rows to a helper that cannot help.
check("not on the database -> declines",
      B.store_for("nestwell_goods", {"data_backend": "sheets"}, None), None)

L = open(os.path.join("routes", "listing_routes.py"), encoding="utf-8").read()
truthy("listing_routes asks that one function",
       "_backend.store_for(aid, _cfg(), CONFIG_PATH)" in L)
falsy("  and no longer opens a store itself",
      "SheetLikeStore(ListingStore(aid, config_path=CONFIG_PATH))" in L)

print("\n=== the handling write goes to the account the PAGE named ===")
H = open(os.path.join("routes", "handling_routes.py"), encoding="utf-8").read()
truthy("the writer takes an account", "def _sheet_write_handling(skus_set, days, account_id" in H)
truthy("  and opens that account's store",
       "_backend.store_for(account_id, _cfg(), CONFIG_PATH)" in H)
truthy("  falling back to the active workspace only off the database",
       "or _ws()" in H)
truthy("  the caller resolves it the same way the Amazon push does",
       "_sacc, _swsid, _smkt = _scope()" in H)
truthy("    and passes it in", "_sheet_write_handling(\n                skus_set, days, _said)" in H
       or "skus_set, days, _said)" in H)

# THE POINT: _ws() must not be the thing that decides where a WRITE lands.
_fn = H.split("def _sheet_write_handling(")[1].split("\n    @app.route")[0]
falsy("_ws() is no longer what decides the destination on its own",
      "book = _ws().spreadsheet" in _fn)

print("\n=== the browser names the account, or none of this works ===")
J = open(os.path.join("static", "js", "handling.js"), encoding="utf-8").read()
truthy("the bulk post carries the open account",
       "id: (typeof CUR_ACCOUNT" in J)
R = open(os.path.join("static", "js", "reqscope.js"), encoding="utf-8").read()
truthy("  and the single-row edit does too, via acctBody",
       "{account: id}" in R)

print("\n=== the module still parses ===")
for f in (os.path.join("data", "backend.py"),
          os.path.join("routes", "handling_routes.py")):
    truthy("%s has no syntax error" % f,
           isinstance(ast.parse(open(f, encoding="utf-8").read()), ast.Module))

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
raise SystemExit(1 if fails else 0)
