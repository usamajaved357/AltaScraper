"""Making an image, keeping an image, and publishing one are three different acts.

They used to be two: everything except the Amazon push needed `edit`, which is the
permission for rewriting listing drafts. So "let this person design images and
nothing else" could not be expressed -- granting it handed them the listings too.
"""
# THE TREE THIS TEST LIVES IN. It used to name the main checkout outright, so
# run from any other checkout it silently tested THAT checkout's code
# (Milestone 1, 28 Sep 2026: 141 files did this).
import os as _os_repo
_REPO = _os_repo.path.dirname(_os_repo.path.abspath(__file__))
import os, sys, json, tempfile, shutil
sys.path.insert(0, _REPO)

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-62s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

from auth import guard, users

TMP = tempfile.mkdtemp(prefix="altaperm_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))


def person(perms, features, perms_version=users.PERMS_VERSION):
    # STAMPED, because every arrangement below is a DELIBERATE one -- "images
    # only", "hands off the library" -- and that is what a record configured by
    # the current app carries. Without the stamp these records are treated as
    # predating part of the vocabulary, and a permission their ROLE grants is
    # inferred (see LATER_PERMISSIONS in auth/users.py) -- which is right for a
    # legacy record and wrong for an intended one. The legacy case is asserted
    # on its own below, so both halves are covered here.
    u = {"role": "lister", "permissions": list(perms), "active": True,
         "features": dict(features), "workspaces": ["*"]}
    if perms_version is not None:
        u["perms_version"] = perms_version
    return u

def may(u, path, method="POST"):
    return guard.check(path, method, u, {})[0]


GEN   = "/genimage/from_concept"     # making one
KEEP  = "/genimage/save_to_media"    # keeping one
UP    = "/media/upload"              # uploading your own
DEL   = "/media/delete"
PUSH  = "/listing/push_image"        # sending it to Amazon
DRAFT = "/rows/save"                 # changing a listing

print("=== the arrangement that was impossible: images only ===")
designer = person([], {"images": "edit", "listings": "none", "sales": "none",
                       "ppc": "none", "inventory": "none", "monitor": "none",
                       "accounts": "none"})
check("may generate an image", may(designer, GEN), True)
check("  but NOT save it to the library", may(designer, KEEP), False)
check("  nor upload a file", may(designer, UP), False)
check("  nor delete one", may(designer, DEL), False)
check("  nor push it to Amazon", may(designer, PUSH), False)
check("  nor touch a listing", may(designer, DRAFT), False)
check("  and cannot even see the sales screen", may(designer, "/sales/summary", "GET"), False)

print("\n=== 'design and keep, but never publish or edit listings' ===")
keeper = person(["upload_images"], {"images": "edit", "listings": "none"})
check("may generate", may(keeper, GEN), True)
check("  and save", may(keeper, KEEP), True)
check("  and upload", may(keeper, UP), True)
check("  but not push to Amazon", may(keeper, PUSH), False)
check("  and still not edit listings", may(keeper, DRAFT), False)

print("\n=== 'edit listings, but hands off the image library' ===")
writer = person(["edit"], {"images": "edit", "listings": "edit"})
check("may edit listings", may(writer, DRAFT), True)
check("  may generate images", may(writer, GEN), True)
check("  but may NOT add or remove files", may(writer, UP), False)
check("  nor delete", may(writer, DEL), False)

print("\n=== read-only sight of the studio ===")
looker = person(["upload_images"], {"images": "view"})
check("may look", may(looker, "/media/list", "GET"), True)
check("  but not generate", may(looker, GEN), False)
check("  and not upload, even holding the permission", may(looker, UP), False)

print("\n=== no images access at all ===")
blind = person(["edit", "upload_images", "publish"], {"images": "none", "listings": "edit"})
check("cannot see the library", may(blind, "/media/list", "GET"), False)
check("  cannot generate", may(blind, GEN), False)
check("  cannot upload", may(blind, UP), False)
check("  but listings still work", may(blind, DRAFT), True)

print("\n=== the roles still do what they always did ===")
for role in ("owner", "manager", "lister"):
    u = person(users.ROLES[role], users.ROLE_FEATURES[role])
    check("%s may generate" % role, may(u, GEN), True)
    check("  and keep" % (), may(u, KEEP), True)
check("a viewer may do neither",
      [may(person(users.ROLES["viewer"], users.ROLE_FEATURES["viewer"]), p)
       for p in (GEN, KEEP, UP)], [False, False, False])

print("\n=== a record written BEFORE upload_images existed is not locked out ===")
# "i am trying to upload the images in the drafts ... it gives me an error that
#  you do not have the permissions, altough i am on my admin account"
# His own record, from /users/me: role owner, and a permissions list written on
# 13 Aug 2026 -- the day before upload_images entered the vocabulary. Nothing
# had ever added it, so the owner of the app was refused all three routes.
legacy_owner = person([p for p in users.ROLES["owner"] if p != "upload_images"],
                      users.ROLE_FEATURES["owner"], perms_version=None)
legacy_owner["role"] = "owner"
check("the stored list really lacks it",
      "upload_images" in legacy_owner["permissions"], False)
check("  he may upload anyway, because his ROLE grants it",
      may(legacy_owner, UP), True)
check("  and save", may(legacy_owner, KEEP), True)
check("  and delete", may(legacy_owner, DEL), True)
# The half that must not break: an OLDER permission missing from a legacy record
# is still a decision, because it existed when the record was written.
legacy_stripped = person(["edit"], users.ROLE_FEATURES["owner"], perms_version=None)
legacy_stripped["role"] = "owner"
check("  but an older permission stays removed", may(legacy_stripped, PUSH), False)

print("\n=== the new permission is offered on the Users screen ===")
check("it is in the vocabulary", "upload_images" in users.PERMISSIONS, True)
check("  and described in plain words",
      "upload" in users.PERMISSIONS["upload_images"].lower(), True)
check("  edit no longer claims to cover images",
      "image" in users.PERMISSIONS["edit"].lower(), False)

print("\n=== pushing to Amazon is still the strongest of the three ===")
check("needs publish", guard.required_permission(PUSH, "POST"), "publish")
check("saving needs upload_images", guard.required_permission(KEEP, "POST"), "upload_images")
check("generating needs no action permission",
      guard.required_permission(GEN, "POST"), None)
check("  and the images feature still gates it",
      guard.feature_for(GEN), "images")

shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
