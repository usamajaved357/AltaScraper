"""Making an image, keeping an image, and publishing one are three different acts.

They used to be two: everything except the Amazon push needed `edit`, which is the
permission for rewriting listing drafts. So "let this person design images and
nothing else" could not be expressed -- granting it handed them the listings too.
"""
import os, sys, json, tempfile, shutil
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-62s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

from auth import guard, users

TMP = tempfile.mkdtemp(prefix="altaperm_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))


def person(perms, features):
    return {"role": "lister", "permissions": list(perms), "active": True,
            "features": dict(features), "workspaces": ["*"]}

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
