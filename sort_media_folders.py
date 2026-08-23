"""sort_media_folders.py -- file the images that were saved before anything
recorded what they were for.

PLAIN ENGLISH
Every generated image used to land in the SKU's folder with a name like
generated_1784116893321.jpg. A main product photo, a lifestyle shot, an A+
banner and the phone version of that banner all looked the same from the
outside, so the only way to find one was to open them one at a time.

New images are now filed by purpose as they are saved. This sorts the ones
already on disk into the same folders, and it does it by PIXEL SIZE rather than
by guessing from the name: Amazon publishes an exact size for every A+ module,
so a 970x600 image really is a Basic header and a 1464x600 really is a Premium
desktop banner. Anything whose size does not identify it is LEFT WHERE IT IS --
a file in the wrong folder claims its purpose is known when it is not, which is
worse than one that has not been sorted.

USAGE
    python sort_media_folders.py                 # dry run -- shows every move
    python sort_media_folders.py --apply         # do it
    python sort_media_folders.py --apply --account jack_uk
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from domain import media_kinds as MK

try:
    from PIL import Image as _PImg
except Exception:
    _PImg = None


def _modules():
    """The A+ catalogue, from the one place that defines it."""
    import dashboard as _d
    return getattr(_d, "_APLUS_MODULES", {}) or {}


def _size(path):
    if _PImg is None:
        return (0, 0)
    try:
        with _PImg.open(path) as im:
            return im.size
    except Exception:
        return (0, 0)


def _unique(dest_dir, name):
    """A free name in the destination. Never overwrites: two files can genuinely
    have the same name if one was uploaded and one generated."""
    base, ext = os.path.splitext(name)
    cand = name
    n = 2
    while os.path.exists(os.path.join(dest_dir, cand)):
        cand = "%s_%d%s" % (base, n, ext)
        n += 1
    return cand


def _locator_kinds():
    """{absolute file path -> folder} from what the DRAFTS actually recorded.

    A second, narrower signal than pixel size, and a stronger one: if a listing
    says a file IS its main_product_image_locator, that is a fact rather than an
    inference. Only a handful qualify -- measured, 2 of 1,061 recorded locators
    point at our own media files and the rest are supplier URLs -- but two files
    correctly placed beats ninety confidently misplaced.
    """
    out = {}
    try:
        import json
        from data import db as _db
        root = os.path.join(os.path.dirname(os.path.abspath("config.json")), "media")
        conn = _db.get_db("config.json")
        for r in conn.execute("SELECT workspace_id, sku, attributes_json FROM listings "
                              "WHERE IFNULL(attributes_json,'')<>''"):
            try:
                a = json.loads(r["attributes_json"] or "{}") or {}
            except Exception:
                continue
            src = a.get("attributes") if isinstance(a.get("attributes"), dict) else a
            for k, v in (src or {}).items():
                if "image_locator" not in k:
                    continue
                if isinstance(v, list) and v:
                    v = v[0]
                if isinstance(v, dict):
                    v = v.get("media_location") or v.get("value") or ""
                v = str(v or "")
                i = v.find("/media/")
                if i < 0:
                    continue
                rel = v[i + len("/media/"):].split("?")[0]
                p = os.path.normpath(os.path.join(root, rel.replace("/", os.sep)))
                out[p] = MK.MAIN if k.startswith("main_") else MK.SECONDARY
    except Exception:
        pass
    return out


def plan(account=None):
    """[(sku_dir, filename, folder, w, h)] for everything that can be filed."""
    root = os.path.join(os.path.dirname(os.path.abspath("config.json")), "media")
    acct_root = os.path.join(root, "_acct")
    mods = _modules()
    by_locator = _locator_kinds()
    out, unsorted_ = [], []
    if not os.path.isdir(acct_root):
        return out, unsorted_
    for acct in sorted(os.listdir(acct_root)):
        if account and acct != account:
            continue
        adir = os.path.join(acct_root, acct)
        if not os.path.isdir(adir):
            continue
        for sku in sorted(os.listdir(adir)):
            sdir = os.path.join(adir, sku)
            if not os.path.isdir(sdir) or MK.skip_dir(sku):
                continue
            # ONLY THE TOP LEVEL. A file already inside main/ or aplus/ has been
            # filed -- by the app when it was saved, or by an earlier run of
            # this -- and re-judging it by size would move a hero that happens
            # to be 970x600 out of the folder somebody deliberately put it in.
            for fn in sorted(os.listdir(sdir)):
                fp = os.path.join(sdir, fn)
                if os.path.isdir(fp) or not MK.is_image(fn):
                    continue
                w, h = _size(fp)
                # THE DRAFT'S OWN RECORD FIRST. It says what the file IS; the
                # size only says what it could be.
                folder = by_locator.get(os.path.normpath(fp)) \
                    or MK.folder_from_size(w, h, mods)
                if folder:
                    out.append((sdir, fn, folder, w, h))
                else:
                    unsorted_.append((sdir, fn, w, h))
    return out, unsorted_


def main(apply_it, account=None):
    moves, left = plan(account)
    by_folder = {}
    for _sd, _fn, folder, _w, _h in moves:
        by_folder[folder] = by_folder.get(folder, 0) + 1

    print("%d image(s) can be filed by their size, %d cannot.\n"
          % (len(moves), len(left)))
    for f in MK.ALL_FOLDERS:
        if by_folder.get(f):
            print("   %-28s %-34s %d" % (f, MK.LABELS.get(f, ""), by_folder[f]))
    print()

    done = 0
    for sdir, fn, folder, w, h in moves:
        dest = os.path.join(sdir, *folder.split("/"))
        name = fn
        if apply_it:
            os.makedirs(dest, exist_ok=True)
            name = _unique(dest, fn)
            shutil.move(os.path.join(sdir, fn), os.path.join(dest, name))
        done += 1
        if done <= 20:
            print("   %-42s %4dx%-4d -> %s%s"
                  % (fn[:42], w, h, folder, "" if name == fn else "  (as %s)" % name))
    if done > 20:
        print("   ... and %d more" % (done - 20))

    if left:
        print("\n%d left where they are, because their size does not say what they "
              "are:" % len(left))
        sizes = {}
        for _sd, _fn, w, h in left:
            sizes[(w, h)] = sizes.get((w, h), 0) + 1
        for (w, h), n in sorted(sizes.items(), key=lambda x: -x[1])[:10]:
            print("   %4dx%-4d  %d file(s)" % (w, h, n))
        print("   These are mostly main and secondary images, which have no fixed "
              "size to recognise them by. Newly generated ones are filed as they "
              "are saved; these predate that.")

    print("\n%s" % ("APPLIED." if apply_it
                    else "DRY RUN -- nothing moved. Re-run with --apply."))


if __name__ == "__main__":
    _acct = None
    if "--account" in sys.argv:
        i = sys.argv.index("--account")
        if i + 1 < len(sys.argv):
            _acct = sys.argv[i + 1]
    main("--apply" in sys.argv, _acct)
