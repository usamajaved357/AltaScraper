"""A scoped user sees only the workspaces they may open.

The bug: /accounts/select refused a workspace someone was not scoped to, but
/accounts/list did not filter at all -- so a VA restricted to one workspace saw
every workspace on the home screen, with each one's label, seller id, brands,
marketplaces, sheet links and LWA client id. Not a cosmetic difference: the whole
shape of the business, handed to someone deliberately scoped away from it.
"""
import os, sys, json, tempfile, shutil
sys.path.insert(0, r"D:\AltaScraper")
from flask import Flask
from auth import users

fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(label)
    print("  %-58s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))

TMP = tempfile.mkdtemp(prefix="altascope_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [
    {"id": "jack_uk", "label": "Jack Reacherd", "seller_id": "A34C", "marketplaces": ["UK"]},
    {"id": "selvora", "label": "Selvora", "seller_id": "A1W1", "marketplaces": ["UK"]},
    {"id": "green_haven", "label": "Green Haven", "seller_id": "AGH1", "marketplaces": ["UK"]},
]}, open(CFG, "w"))

va, _ = users.create_user(CFG, email="va@x.com", name="Aisha", role="lister",
                          permissions=["edit"], workspaces=["selvora"])
boss, _ = users.create_user(CFG, email="boss@x.com", name="Talha", role="owner",
                            permissions=["edit", "manage_users", "manage_accounts"],
                            workspaces=["*"])

print("=== the rule the doorman already enforces ===")
vu = users.get_user(CFG, va["id"])
bu = users.get_user(CFG, boss["id"])
check("the VA may open selvora", users.can_access_workspace(vu, "selvora"), True)
check("  but not green_haven", users.can_access_workspace(vu, "green_haven"), False)
check("  nor jack_uk", users.can_access_workspace(vu, "jack_uk"), False)
check("the owner may open all of them",
      all(users.can_access_workspace(bu, w) for w in ("selvora", "green_haven", "jack_uk")), True)

print("\n=== and the list must give the same answer ===")
# _visible_accounts is defined inside register(); exercise it through the real
# route module so what ships is what is tested.
import routes.accounts_routes as ar

app = Flask(__name__)
app.secret_key = "t"
ar.register(app, _state={}, _cfg=lambda: json.load(open(CFG)), CONFIG_PATH=CFG,
            _LIVE_CACHE={}, live_catalog=lambda: None, OUTPUT_TAB="out",
            ConfigError=Exception, _client=lambda: None)

def ids_for(uid):
    c = app.test_client()
    with c.session_transaction() as s:
        s["authed"] = True
        if uid:
            s["uid"] = uid
    j = c.get("/accounts/list").get_json()
    return sorted(a["id"] for a in (j.get("accounts") or []))

check("the VA sees only their workspace", ids_for(va["id"]), ["selvora"])
check("the owner sees all three", ids_for(boss["id"]),
      ["green_haven", "jack_uk", "selvora"])
check("the shared-password owner sees all three", ids_for(None),
      ["green_haven", "jack_uk", "selvora"])

print("\n=== nothing about the hidden workspaces leaks ===")
c = app.test_client()
with c.session_transaction() as s:
    s["authed"] = True; s["uid"] = va["id"]
body = json.dumps(c.get("/accounts/list").get_json())
for secret in ("Green Haven", "Jack Reacherd", "AGH1", "A34C", "green_haven", "jack_uk"):
    check("  %r is absent" % secret, secret in body, False)
check("  their own workspace is present", "Selvora" in body, True)

print("\n=== an empty selection means NO workspaces, never all of them ===")
# The fail-open this pins down: both create_user and update_user turned an empty
# workspace list into [*]. So unticking every box to lock someone down handed
# them the whole estate instead -- silently, and looking exactly like success.
empty, _tok = users.create_user(CFG, "locked@x.com", "Locked", role="lister",
                                workspaces=[])
check("created with none selected -> none", empty["workspaces"], [])
locked = users.get_user(CFG, empty["id"])
check("  and they can reach nothing",
      any(users.can_access_workspace(locked, w)
          for w in ("jack_uk", "selvora", "dropshipping", "")), False)

two, _t2 = users.create_user(CFG, "two@x.com", "Two", role="lister",
                             workspaces=["jack_uk", "selvora"])
u2 = users.get_user(CFG, two["id"])
check("two workspaces means exactly two",
      [users.can_access_workspace(u2, w) for w in ("jack_uk", "selvora", "nestwell_goods")],
      [True, True, False])

users.update_user(CFG, two["id"], workspaces=[])
check("clearing them on edit does NOT grant everything",
      users.get_user(CFG, two["id"])["workspaces"], [])
check("  and access really is gone",
      users.can_access_workspace(users.get_user(CFG, two["id"]), "jack_uk"), False)

users.update_user(CFG, two["id"], workspaces=["jack_uk"])
check("and it can be put back",
      users.can_access_workspace(users.get_user(CFG, two["id"]), "jack_uk"), True)

nofield, _t3 = users.create_user(CFG, "nofield@x.com", "NoField", role="lister")
check("NOT supplying the field at all still defaults to everything",
      nofield["workspaces"], ["*"])


print("\n=== one implementation, not two (Rule 12) ===")
s = open(r"D:\AltaScraper\routes\accounts_routes.py", encoding="utf-8").read()
check("the list calls the shared rule", "users.can_access_workspace" in s, True)
check("  via a single helper", s.count("def _visible_accounts("), 1)
check("  used by the list route", s.count("_visible_accounts(al)"), 1)

shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
