"""The doorman checks EVERY account a request names, wherever it names it.

THE HOLES THIS CLOSES, each proved in the 28 Sep 2026 master audit by calling
the real auth/guard.check() with a user restricted to one account:

  1. The guard read the FIRST of id / account_id / ... / account, while many
     routes read `account` first (domain/request_account.named, /edit, /delete,
     upload files). `?id=<mine>&account=<theirs>` passed the guard and the route
     acted on theirs -- including deleting a live listing on Amazon.
  2. The body was read with get_json(silent=True), which is None unless the
     request says it is JSON. About 100 routes parse with force=True, so a
     text/plain body carried any account straight past the check. Form fields
     (the upload routes) were never read at all.
  3. In a batch, only the FIRST row's account was checked.
  4. The exemption list was matched by prefix and skipped EVERY field: "/listing/"
     covered the live price and image writes, "/notify/channel" also matched
     "/notify/channels", and "/trackers/watch" reads `id` as an account.

The fix is at the one choke point every request passes: every value named in
the query, the body (whatever it says its type is), the form and every row must
be an account the user may open. Only the ambiguous `id` is ever exempt, and
only on the paths where `id` means something else.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from auth import guard as G          # noqa: E402
from auth import users as U          # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-72s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


# A user restricted to ONE account, with every permission inside it, so a
# refusal below can only be about the account.
NEST = {"id": "u1", "email": "n@example.test", "role": "manager", "active": True,
        "workspaces": ["nestwell_goods"],
        "permissions": list(U.PERMISSIONS),
        "features": {f: "edit" for f in U.FEATURES}}
ADMIN = dict(NEST, workspaces=["*"])


def allowed(path, method="GET", args=None, body=None, user=NEST):
    return G.check(path, method, user, body, args)[0]


print("\n1. every account field is checked, not the first one found")
check("?id=mine&account=theirs is refused",
      allowed("/sales/today", args={"id": "nestwell_goods", "account": "jack_uk"}),
      False)
check("?account_id=mine&account=theirs is refused",
      allowed("/orders/list", args={"account_id": "nestwell_goods",
                                    "account": "jack_uk"}), False)
check("POST /delete {id: mine, account: theirs} is refused",
      allowed("/delete", "POST", body={"id": "nestwell_goods", "account": "jack_uk",
                                       "sku": "X"}), False)
check("query names mine, body names theirs: refused",
      allowed("/edit", "POST", args={"id": "nestwell_goods"},
              body={"account": "jack_uk"}), False)
check("my own account, named twice, is allowed",
      allowed("/sales/today", args={"id": "nestwell_goods",
                                    "account": "nestwell_goods"}), True)

print("\n2. a body is read whatever it says it is")
# The doorman hands check() the body it parsed; body_for_check is what it uses.
check("a text/plain JSON body is parsed",
      G.body_for_check("text/plain", b'{"account":"jack_uk"}', {}),
      {"account": "jack_uk"})
check("form fields are read", G.body_for_check(
    "multipart/form-data", b"", {"id": "jack_uk"}), {"id": "jack_uk"})
check("a form-urlencoded body is read the same way", G.body_for_check(
    "application/x-www-form-urlencoded", b"", {"account_id": "jack_uk"}),
    {"account_id": "jack_uk"})
check("so a form upload naming another account is refused",
      allowed("/cogs/upload_sheet", "POST",
              body=G.body_for_check("multipart/form-data", b"", {"id": "jack_uk"})),
      False)
_evil = '{"sku":"X","mode":"api_submit","account":"jack_uk"}'
for _enc, _raw in (("UTF-16", _evil.encode("utf-16")),
                   ("UTF-8 with a BOM", b"\xef\xbb\xbf" + _evil.encode("utf-8")),
                   ("UTF-16-LE", _evil.encode("utf-16-le"))):
    check("a %s body is read like Flask reads it" % _enc,
          G.body_for_check("application/json", _raw, {}).get("account"), "jack_uk")
    check("  so it cannot name another account unseen",
          allowed("/edit", "POST",
                  body=G.body_for_check("application/json", _raw, {})), False)
check("rubbish in the body is not an error, just nothing named",
      G.body_for_check("text/plain", b"not json", {}), {})

print("\n3. every row of a batch is checked")
check("second row names another account: refused",
      allowed("/orders/items", "POST", body={"orders": [
          {"order_id": "1", "account_id": "nestwell_goods"},
          {"order_id": "2", "account_id": "jack_uk"}]}), False)
check("all rows mine: allowed",
      allowed("/orders/items", "POST", body={"orders": [
          {"order_id": "1", "account_id": "nestwell_goods"},
          {"order_id": "2", "account_id": "nestwell_goods"}]}), True)

print("\n4. only `id` is ever exempt, and only where it is not an account")
check("/listing/price/apply naming another account is refused",
      allowed("/listing/price/apply", "POST",
              body={"id": "jack_uk", "sku": "X", "price": 9.99}), False)
check("/listing/push_image naming another account is refused",
      allowed("/listing/push_image", "POST", body={"id": "jack_uk"}), False)
check("/trackers/watch naming another account is refused",
      allowed("/trackers/watch", "POST", body={"account": "jack_uk"}), False)
check("/notify/channels naming another account is refused",
      allowed("/notify/channels", "POST", body={"account": "jack_uk"}), False)
check("/genimage/instructions ?id=another account is refused",
      allowed("/genimage/instructions", args={"id": "jack_uk"}), False)
check("an `account` on an exempt path is still checked",
      allowed("/media/list", args={"account": "jack_uk"}), False)
# ...and the ordinary uses of `id` that are NOT accounts keep working.
check("/notify/channel {id: <channel>} still works",
      allowed("/notify/channel", "POST", body={"id": "ch_123"}), True)
check("/media/delete {id: <file>} still works",
      allowed("/media/delete", "POST", body={"id": "img_77"}), True)
check("/input/update {id: <row>} still works",
      allowed("/input/update", "POST", body={"id": "42"}), True)
check("/genimage/job_status ?id=<job> still works",
      allowed("/genimage/job_status", args={"id": "job9"}), True)
for _p in ("/mediaX", "/usersX", "/genimageX", "/recipesX"):
    check("%s is not an exempt path (prefix boundary)" % _p,
          allowed(_p, "POST", body={"id": "jack_uk"}), False)
check("/trackers/watch ?id=another account is refused (id IS the account there)",
      allowed("/trackers/watch", "POST", args={"id": "jack_uk"}), False)
for _p, _v in (("/notify/test", 7), ("/monitor/remove", 12),
               ("/miles/run_tail", "r1"), ("/miles_template/delete", "t1"),
               ("/drppc/console/rule/delete", "rule9"), ("/expenses/delete", 4),
               ("/charges/delete", 3), ("/recipes/delete", "rc1")):
    check("%s {id: <record>} is not read as an account" % _p,
          allowed(_p, "POST", body={"id": _v}), True)
check("  but an account named beside it still is",
      allowed("/expenses/delete", "POST", body={"id": 4, "account": "jack_uk"}),
      False)
check("/users/update {id: <user>} is not treated as an account",
      "workspace" not in G.check("/users/update", "POST", NEST,
                                 {"id": "u9"}, {})[1], True)

print("\n5. nothing changes for someone allowed every account")
check("the owner may name any account",
      allowed("/delete", "POST", body={"id": "nestwell_goods", "account": "jack_uk"},
              user=ADMIN), True)
check("sentinels are not accounts",
      allowed("/orders/list", args={"account": "__all__"}), True)

print("\n7. work done over GET is work; submitting is publishing")
_perms_no_publish = [p for p in U.PERMISSIONS if p != "publish"]
LISTER = dict(ADMIN, permissions=_perms_no_publish)
VIEWER = dict(ADMIN, permissions=[],
              features={f: "view" for f in U.FEATURES})
check("a view-only user cannot start GET /run/generate",
      allowed("/run/generate", "GET", user=VIEWER), False)
check("  nor GET /run/api_submit",
      allowed("/run/api_submit", "GET", user=VIEWER), False)
check("  but may still read /run/health",
      allowed("/run/health", "GET", user=VIEWER), True)
check("  and may still read a feature screen (view means view)",
      allowed("/sales/today", "GET", user=VIEWER), True)
check("a lister without publish cannot submit via /run/api_submit",
      allowed("/run/api_submit", "GET", user=LISTER), False)
check("  may still generate",
      allowed("/run/generate", "GET", user=LISTER), True)
check("  cannot submit via /preview/enqueue",
      allowed("/preview/enqueue", "POST", body={"sku": "X", "mode": "api_submit"},
              user=LISTER), False)
check("  may still preview via /preview/enqueue",
      allowed("/preview/enqueue", "POST", body={"sku": "X", "mode": "api"},
              user=LISTER), True)
check("someone with publish may submit",
      allowed("/preview/enqueue", "POST", body={"sku": "X", "mode": "api_submit"},
              user=ADMIN), True)
check("/jobs/run needs the operator's permission",
      allowed("/jobs/run/sourcing_apply", "POST", body={},
              user=dict(ADMIN, permissions=[p for p in U.PERMISSIONS
                                            if p != "manage_accounts"])), False)

_NO_MANAGE = dict(ADMIN, permissions=[p for p in U.PERMISSIONS
                                      if p != "manage_accounts"])
check("anyone may read /ai/settings (the model pickers need it)",
      allowed("/ai/settings", "GET", user=_NO_MANAGE), True)
check("  but changing it needs manage_accounts",
      allowed("/ai/settings", "POST", body={}, user=_NO_MANAGE), False)
check("  as does /admin/logic_settings",
      allowed("/admin/logic_settings", "POST", body={}, user=_NO_MANAGE), False)
check("  and the owner still may",
      allowed("/ai/settings", "POST", body={}, user=ADMIN), True)
check("moving pictures between accounts needs manage_accounts",
      allowed("/media/recover/move", "POST",
              body={"from": "jack_uk", "to": "nestwell_goods"}, user=_NO_MANAGE),
      False)

print("\n6. reading the body for the check leaves it intact for the route")
import io                                                              # noqa: E402
from flask import Flask, request                                       # noqa: E402
_app = Flask(__name__)
with _app.test_request_context(
        "/cogs/upload_sheet", method="POST",
        data={"id": "jack_uk", "file": (io.BytesIO(b"sku,cost\nA,1\n"), "c.csv")},
        content_type="multipart/form-data"):
    _b = G.request_body_for_check(request)
    check("a multipart upload's account field is seen", _b.get("id"), "jack_uk")
    _f = request.files.get("file")
    check("  and the route still gets the file, whole",
          _f.read() if _f else None, b"sku,cost\nA,1\n")
with _app.test_request_context("/delete", method="POST",
                               data=b'{"account":"jack_uk","sku":"X"}',
                               content_type="text/plain"):
    check("a text/plain JSON body is seen",
          G.request_body_for_check(request), {"account": "jack_uk", "sku": "X"})
    check("  and the route's own force=True read still works",
          request.get_json(force=True), {"account": "jack_uk", "sku": "X"})
with _app.test_request_context("/sales/today?id=jack_uk", method="GET"):
    check("a GET has no body to read", G.request_body_for_check(request), None)
with _app.test_request_context("/x", method="DELETE",
                               data=b'{"account_id":"jack_uk"}',
                               content_type="application/json"):
    check("a DELETE body is read too",
          G.request_body_for_check(request), {"account_id": "jack_uk"})

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    print("FAILED:")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("all passed")
