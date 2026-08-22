"""One folder per SKU, arranged inside it by what each image is FOR.

    "the images are arranged inside the sku folder are further seggregated by
     basic aplus content, premium aplus content aplus desktop and aplus mobile,
     also following the dimensions rules. 1 folder should contain all the images
     but seggregated and arranged by the purpose or type"

WHAT IT LOOKED LIKE. Every generated image landed in the SKU folder as
generated_<unix-timestamp>.jpg. Measured on jack_uk: twelve SKU folders, one of
them holding sixteen files whose names differ only by the second they were made
in. A hero, a lifestyle shot, a 970x600 A+ header and the 600x450 phone version
of that header were indistinguishable without opening each one.

THE READER ALREADY UNDERSTOOD FOLDERS -- routes/media_routes.media_list walks
subfolders and tags each file with its group, and static/js/listingimages.js has
had a shelf per folder with a note explaining what Amazon wants in it. Only the
WRITER never made any. So this is the missing half, not a new idea.

AND THE SORTER CLAIMS ONLY WHAT IT CAN PROVE. An earlier version of
folder_from_size said a big square image is the main one; measured against the
real library that would have filed 93 images as "main" when the studio generates
heroes AND lifestyle shots at 4096x4096. Ninety of those would have been wrong.
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-68s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from domain import media_kinds as MK


print("=== every kind has one folder, and it is the one asked for ===")
for kind, tier, variant, want in [
        ("main", "", "", "main"),
        ("secondary", "", "", "secondary"),
        ("aplus", "basic", "", "aplus/basic"),
        ("aplus", "premium", "desktop", "aplus/premium/desktop"),
        ("aplus", "premium", "mobile", "aplus/premium/mobile"),
        ("source", "", "", "source")]:
    check("  %-9s %-8s %-8s" % (kind, tier or "-", variant or "-"),
          MK.folder_for(kind, tier, variant), want)

# BASIC A+ IS NOT SPLIT BY SCREEN, and that is Amazon's rule rather than a
# simplification: one asset per Basic module, which Amazon scales itself. Only
# Premium renders differently on a phone, which is why only Premium splits.
check("  basic A+ ignores a screen it was never given",
      MK.folder_for("aplus", "basic", "mobile"), "aplus/basic")
check("  and premium defaults to desktop when unsaid",
      MK.folder_for("aplus", "premium", ""), "aplus/premium/desktop")

print("\n=== an unknown kind invents nothing ===")
# A file in the wrong folder claims its purpose is known when it is not, which
# is worse than one that is simply unsorted.
for kind in ("", "banner", None, "something_new"):
    check("  %-14r stays at the SKU root" % kind, MK.folder_for(kind), "")


print("\n=== sizes: only what Amazon documents, and nothing else ===")
import dashboard as _d
MODS = getattr(_d, "_APLUS_MODULES", {}) or {}
truthy("the A+ catalogue is readable", bool(MODS.get("basic")))
# Read from the catalogue rather than repeated here, so a module added there is
# recognised without a second edit.
check("  a Basic header is Basic", MK.folder_from_size(970, 600, MODS), "aplus/basic")
check("  a premium banner is premium desktop",
      MK.folder_from_size(1464, 600, MODS), "aplus/premium/desktop")
check("  and its phone version is premium mobile",
      MK.folder_from_size(600, 450, MODS), "aplus/premium/mobile")

# THE ONE THAT WOULD HAVE BEEN WRONG NINETY TIMES.
check("a big square is NOT assumed to be the main image",
      MK.folder_from_size(4096, 4096, MODS), "")
check("  nor is any other size the catalogue does not name",
      MK.folder_from_size(1179, 596, MODS), "")
check("  and nonsense is refused rather than guessed",
      [MK.folder_from_size(0, 0, MODS), MK.folder_from_size(-1, 5, MODS),
       MK.folder_from_size("x", "y", MODS)], ["", "", ""])


print("\n=== the route files by kind, and says where it put it ===")
RT = open("routes/genimage_routes.py", encoding="utf-8").read()
_fn = RT.split("def genimage_save_to_media")[1].split("@app.route")[0]
truthy("it asks the shared module, not its own table",
       "media_kinds" in _fn and "_mk.folder_for(" in _fn)
truthy("  reading kind, tier and variant from the caller",
       'b.get("kind"' in _fn and 'b.get("tier"' in _fn and 'b.get("variant"' in _fn)
truthy("  it creates the folder", "makedirs" in _fn)
truthy("  an unknown kind still writes, at the SKU root",
       "if sub else base" in _fn)
# The folders are the point, so "saved" without saying where would leave you
# opening the library to find out.
truthy("  and it reports the folder back", '"folder": sub' in _fn)
truthy("    with a readable name", "folder_label" in _fn)


print("\n=== the studio tells it what the image is ===")
GI = open("static/js/genimage.js", encoding="utf-8").read()
HW = open("static/js/howworks.js", encoding="utf-8").read()
truthy("A+ results carry their tier", 'tier:(job.tier||j.tier||"basic")' in GI)
truthy("  and which screen they are for",
       'variant:((j&&j.viewport==="mobile")||job.variant==="mobile"' in GI)
truthy("other results carry their kind", 'kind:(job.kind||"main")' in HW)
# EVERY save path, or an image saved by one route lands unsorted while the same
# image saved by another is filed. Counted by looking at each call to the
# endpoint rather than by adding up substrings, which double-counted.
_calls = HW.split("/genimage/save_to_media")[1:]
check("there are four ways to save", len(_calls), 4)
_without = [i for i, c in enumerate(_calls) if "kind:" not in c[:400]]
check("  and every one of them sends the kind", _without, [])
truthy("  including the auto-save after a redo",
       "auto-save the redo too" in HW and "kind:r.kind" in HW)
truthy("  and after a refine", "A REFINED IMAGE IS THE SAME KIND" in HW)


print("\n=== the library has a shelf for every folder the writer can make ===")
IL = open("static/js/listingimages.js", encoding="utf-8").read()
# The ORDER array itself, not the first mention of its name -- which is in the
# comment above it.
_order = IL.split("const _IL_SHELF_ORDER")[1]
_order = _order[:_order.index("];") + 2]
for folder in MK.ALL_FOLDERS:
    truthy("  %-24s has a shelf" % folder, ('"%s":' % folder) in IL)
    truthy("    and is placed in the order", ('"%s"' % folder) in _order)
# A folder made by hand must never make images vanish.
truthy("an unknown folder is still drawn, after the known ones",
       "must never make images disappear" in IL)


print("\n=== the sorter leaves alone what it cannot prove ===")
SS = open("sort_media_folders.py", encoding="utf-8").read()
truthy("it dry-runs by default", '"--apply" in sys.argv' in SS)
truthy("  and never overwrites", "def _unique" in SS)
truthy("  it does not re-judge files already filed",
       "ONLY THE TOP LEVEL" in SS)
# The draft's own record is a fact; a pixel size is only a hint.
truthy("the draft's recorded locator wins over the size",
       "THE DRAFT'S OWN RECORD FIRST" in SS)
truthy("  and it skips the thumbnail cache", "skip_dir" in SS)
truthy("skip_dir really skips it", MK.skip_dir(".thumbs") and MK.skip_dir(".x"))
check("  but not a real folder", MK.skip_dir("main"), False)

print("\n=== already_sorted knows our folders from anything else ===")
for rel, want in [("main/a.jpg", True), ("aplus/premium/mobile/x.png", True),
                  ("source/y.jpg", True), ("a.jpg", False),
                  ("mainly/a.jpg", False), ("", False)]:
    check("  %-28r" % rel, MK.already_sorted(rel), want)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
