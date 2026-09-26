"""A permission added AFTER a user record was written must not read as "denied".

THE REPORT
    "i am trying to upload the images in the drafts from my local computer but it
     gives me an error that you do not have the permissions, altough i am on my
     admin account"

He was right, and so was the app's own answer: /users/me on his account returned

    "role": "owner"
    "permissions": ["approve_delete","edit","manage_accounts",
                    "manage_users","ppc","publish"]

with no upload_images in it. His account was written on 13 Aug 2026 (537c293,
the user system); upload_images entered the vocabulary on 14 Aug (5e39619).
has_permission() reads the stored list and nothing else, so the owner of the app
was refused /media/upload, /media/delete and /genimage/save_to_media.

WHAT MUST NOT REGRESS WHILE FIXING IT
Falling back to the role on every check would hand back a permission an admin
had deliberately taken away from one person. That is a worse bug than the one
being fixed, so the fallback is scoped to permissions that did not exist when
the record was written -- and both halves are asserted here.
"""
import sys

sys.path.insert(0, ".")
from auth import guard, users

FAILS = []


def check(label, got, want):
    ok = got == want
    print(("  %-64s OK" if ok else "  %-64s FAIL") % label)
    if not ok:
        print("      got  %r" % (got,))
        print("      want %r" % (want,))
        FAILS.append(label)


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


# His actual record, as /users/me returned it.
OWNER_13_AUG = {
    "id": "u_2b8adf33adbe9c73", "name": "Talal Ahmad", "role": "owner",
    "permissions": ["approve_delete", "edit", "manage_accounts",
                    "manage_users", "ppc", "publish"],
    "workspaces": ["*"], "active": True,
}

print("=== the owner's own record, written before upload_images existed ===")
falsy("the stored list really does not contain it",
      "upload_images" in OWNER_13_AUG["permissions"])
truthy("but his ROLE grants it", "upload_images" in users.ROLES["owner"])
truthy("so he holds it now", users.has_permission(OWNER_13_AUG, "upload_images"))
check("and the resolved set says so once",
      sorted(users.effective_permissions(OWNER_13_AUG)).count("upload_images"), 1)
truthy("nothing he already held was lost",
       all(users.has_permission(OWNER_13_AUG, p)
           for p in OWNER_13_AUG["permissions"]))

print("\n=== the three routes that were refusing him ===")
for path in ("/media/upload", "/media/delete", "/genimage/save_to_media"):
    check("%s needs upload_images" % path,
          guard.required_permission(path, "POST"), "upload_images")
    ok, why = guard.check(path, "POST", dict(OWNER_13_AUG,
                                             features={"images": "edit"}))
    truthy("  and he is allowed through it%s" % ("" if ok else " -- " + why), ok)

print("\n=== a DELIBERATE removal still holds -- the half that must not break ===")
# publish existed on 13 Aug, so its absence is a decision, not an omission.
demoted = dict(OWNER_13_AUG, role="manager",
               permissions=["edit", "approve_delete", "ppc"])
truthy("publish is in the manager preset", "publish" in users.ROLES["manager"])
falsy("but it was taken off this person, and stays off",
      users.has_permission(demoted, "publish"))
falsy("  upload_images too, once the record is stamped",
      users.has_permission(dict(demoted, perms_version=users.PERMS_VERSION),
                           "upload_images"))
truthy("  an UNSTAMPED manager still gets the later permission its role grants",
       users.has_permission(demoted, "upload_images"))

print("\n=== a viewer is granted nothing by any of this ===")
viewer = {"role": "viewer", "permissions": [], "active": True, "workspaces": ["*"]}
check("the viewer preset is empty", users.ROLES["viewer"], [])
falsy("no upload", users.has_permission(viewer, "upload_images"))
falsy("no publish", users.has_permission(viewer, "publish"))
falsy("no edit", users.has_permission(viewer, "edit"))
falsy("a disabled owner holds nothing either",
      users.has_permission(dict(OWNER_13_AUG, active=False), "upload_images"))

print("\n=== the screen shows what is actually in force ===")
pub = users.public(OWNER_13_AUG)
truthy("the Users screen draws the box TICKED",
       "upload_images" in pub["permissions"])
truthy("  so saving that row writes it for real",
       "upload_images" in [p for p in pub["permissions"] if p in users.PERMISSIONS])

print("\n=== and a stamped record infers nothing at all ===")
stamped = dict(OWNER_13_AUG, perms_version=users.PERMS_VERSION)
falsy("upload_images is not added back once stamped",
      users.has_permission(stamped, "upload_images"))
check("a junk version is treated as the oldest, not the newest",
      users.has_permission(dict(OWNER_13_AUG, perms_version="nonsense"),
                           "upload_images"), True)
check("every later permission is a real one",
      sorted(p for s in users.LATER_PERMISSIONS.values() for p in s
             if p not in users.PERMISSIONS), [])

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - %s" % f)
sys.exit(1 if FAILS else 0)
