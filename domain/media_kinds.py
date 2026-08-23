"""domain/media_kinds.py -- what an image is FOR, and where that puts it on disk.

    "the images are arranged inside the sku folder are further seggregated by
     basic aplus content, premium aplus content aplus desktop and aplus mobile,
     also following the dimensions rules. 1 folder should contain all the images
     but seggregated and arranged by the purpose or type"

WHAT IT LOOKED LIKE BEFORE. Every generated image, whatever it was for, was
written into the SKU folder as generated_<unix-timestamp>.jpg -- one flat pile.
Measured on jack_uk: twelve SKU folders, one of them holding sixteen files whose
names differ only by the second they were made in. A main image, a lifestyle
shot, a 970x600 A+ header and a 600x450 phone version of it were
indistinguishable without opening each one.

The READER already understood folders -- routes/media_routes.media_list walks
subfolders and tags each file with the group it came from, and its own comment
names "aplus/basic, aplus/premium, secondary". Only the writer never made any.

ONE FOLDER PER SKU, arranged inside:

    <SKU>/main/                 the white-background hero
    <SKU>/secondary/            lifestyle, benefit, feature, scale shots
    <SKU>/aplus/basic/          Basic A+ modules
    <SKU>/aplus/premium/desktop/  Premium A+, wide
    <SKU>/aplus/premium/mobile/   Premium A+, phone -- a SEPARATE composition,
                                  not the desktop one scaled down
    <SKU>/source/               competitor or supplier reference photos
    <SKU>/                      anything whose purpose was never recorded

THE VOCABULARY LIVES HERE ONLY. The route that writes, the sorter that tidies
what was written before, and the tests all read these tables -- three copies of
"where does an A+ mobile image go" would drift the first time one changed
(CLAUDE.md rule 12).

DIMENSIONS ARE AMAZON'S, NOT OURS. The sizes come from _APLUS_MODULES in
dashboard.py, which is where the generator already reads them, so a module added
there needs no change here.
"""
import os
import re

# kind -> the path under the SKU folder. Kinds are what the studio already calls
# them ("source", "secondary", "aplus"), so nothing has to be translated at the
# call site.
MAIN = "main"
SECONDARY = "secondary"
APLUS_BASIC = "aplus/basic"
APLUS_PREMIUM_DESKTOP = "aplus/premium/desktop"
APLUS_PREMIUM_MOBILE = "aplus/premium/mobile"
SOURCE = "source"

# Every folder this module can produce, for the tests and for anything that
# wants to show the set.
ALL_FOLDERS = (MAIN, SECONDARY, APLUS_BASIC,
               APLUS_PREMIUM_DESKTOP, APLUS_PREMIUM_MOBILE, SOURCE)

# What each folder is called on screen. One place, so the library and the studio
# cannot disagree about what "aplus/premium/mobile" means.
LABELS = {
    MAIN: "Main image",
    SECONDARY: "Secondary images",
    APLUS_BASIC: "A+ content — Basic",
    APLUS_PREMIUM_DESKTOP: "A+ Premium — desktop",
    APLUS_PREMIUM_MOBILE: "A+ Premium — mobile",
    SOURCE: "Reference photos",
    "": "Not sorted yet",
}


def folder_for(kind="", tier="", variant=""):
    """Where an image of this kind belongs, as a relative path. "" if unknown.

    `kind` is what the studio calls it. `tier` and `variant` only matter for A+:
    basic has one size per module, premium has a desktop and a phone version
    that are DIFFERENT COMPOSITIONS rather than one image at two sizes.

    An unknown kind returns "" -- the file goes in the SKU folder itself rather
    than into a folder invented on the spot. A wrong folder is worse than none:
    it says the purpose is known when it is not.
    """
    k = str(kind or "").strip().lower()
    t = str(tier or "").strip().lower()
    v = str(variant or "").strip().lower()
    if k in ("main", "hero", "white", "clean"):
        return MAIN
    if k in ("secondary", "lifestyle", "benefit", "feature", "scale", "infographic"):
        return SECONDARY
    if k in ("source", "reference", "competitor", "supplier"):
        return SOURCE
    if k in ("aplus", "a+", "aplus_module", "module"):
        if t == "premium":
            return APLUS_PREMIUM_MOBILE if v == "mobile" else APLUS_PREMIUM_DESKTOP
        return APLUS_BASIC
    return ""


def _sizes_from_modules(modules):
    """(w, h) -> folder, built from the A+ module catalogue.

    Read from _APLUS_MODULES rather than repeated here, so a module added to the
    catalogue is recognised by the sorter without a second edit. A premium
    module's `mobile` block is its phone size.
    """
    out = {}
    for m in (modules.get("basic") or []):
        w, h = int(m.get("w") or 0), int(m.get("h") or 0)
        if w and h:
            out.setdefault((w, h), APLUS_BASIC)
    for m in (modules.get("premium") or []):
        w, h = int(m.get("w") or 0), int(m.get("h") or 0)
        if w and h:
            out[(w, h)] = APLUS_PREMIUM_DESKTOP        # premium wins a tie
        mob = m.get("mobile") or {}
        mw, mh = int(mob.get("w") or 0), int(mob.get("h") or 0)
        if mw and mh:
            out[(mw, mh)] = APLUS_PREMIUM_MOBILE
    return out


def folder_from_size(w, h, modules=None):
    """Where an EXISTING file belongs, judged by its pixel size. "" if unsure.

    For tidying images that were written before anything recorded a purpose.
    The A+ modules have exact documented sizes, so a 970x600 really is a Basic
    header and a 1464x600 really is a premium desktop banner -- that is a fact
    about the file rather than a guess.

    A BIG SQUARE IS NOT NECESSARILY THE MAIN IMAGE, and an earlier version of
    this said it was. Measured on the real library: 93 of 98 unsorted files are
    4096x4096, and the studio generates main AND secondary images at that size
    -- a lifestyle shot and a hero are both square. Filing all 93 as "main"
    would have been a confident lie about ninety of them, which is the exact
    thing this module's own note about wrong folders warns against.

    So only the A+ module sizes are used, because those are Amazon's published
    dimensions and a 970x600 really is a Basic header. Everything else returns
    "" and stays where it is; sort_media_folders has a second, narrower signal
    for a handful of them (the draft's own recorded image locator).
    """
    try:
        w, h = int(w), int(h)
    except (TypeError, ValueError):
        return ""
    if w <= 0 or h <= 0:
        return ""
    exact = _sizes_from_modules(modules or {})
    return exact.get((w, h), "")


# Files the app writes that are not product images at all.
_SKIP_DIRS = (".thumbs",)


def is_image(name):
    return str(name or "").lower().rsplit(".", 1)[-1] in (
        "png", "jpg", "jpeg", "webp", "gif")


def skip_dir(name):
    """Directories a walk must not descend into or sort."""
    n = str(name or "")
    return n.startswith(".") or n in _SKIP_DIRS


def already_sorted(relpath):
    """Is this file already inside one of our folders?"""
    rel = str(relpath or "").replace(os.sep, "/").strip("/")
    return any(rel == f or rel.startswith(f + "/") for f in ALL_FOLDERS)


# A name the studio writes. Kept so the sorter can tell a generated file from
# one somebody uploaded -- both are real, but only the generated ones carry a
# timestamp that says when.
GENERATED_RE = re.compile(r"^generated_\d+\.(?:png|jpg|jpeg|webp)$", re.I)


def sniff_ext(raw, fallback="jpg"):
    """The TRUE image extension, read from the file's own first bytes.

    NOT the mime label the model claims, because the label is wrong. Measured
    against the configured image model (bytedance-seed/seedream-4.5 over
    OpenRouter) on a real generation:

        declared mime   image/png
        first 4 bytes   ff d8 ff e0        <- JPEG
        PIL says        JPEG 2048x2048

    so a file saved from that label is called .png and contains a JPEG. Amazon
    fetches listing images by URL and rejects one whose bytes do not match its
    extension, which turns a good image into a rejected listing for a reason
    nothing on screen explains.

    This lived in dashboard.py and was injected into two route modules; the one
    that saves generated images was not among them and used the mime map
    instead. Moved here so there is one definition and anything that writes an
    image file can reach it (rule 12); dashboard.py's version now calls this.
    """
    if not raw or len(raw) < 12:
        return fallback
    b = raw[:12]
    if b[:3] == b"\xff\xd8\xff":                       # JPEG
        return "jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":                  # PNG
        return "png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":        # WebP
        return "webp"
    if b[:6] in (b"GIF87a", b"GIF89a"):                # GIF
        return "gif"
    return fallback
