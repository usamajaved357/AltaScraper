"""domain/media_recover.py -- find generated images the library is not showing,
and prove whether the disk they live on actually survives a deploy.

WHY THIS EXISTS
"I generated listing images before the new deployment, now the image library is
empty on the server." That sentence has two completely different causes and they
need opposite responses:

  1. THE FILES ARE STILL THERE, filed under a folder the library never looks in.
     The library lists ONE folder -- the ACTIVE account's -- so an image saved
     while a different workspace (or no workspace) was open is invisible even
     though it is safe on disk. Nothing is lost; it is being looked for in the
     wrong place. Fix: move it to the workspace that owns it.

  2. THE DISK IS NOT PERSISTENT. On Render the container filesystem is wiped on
     every deploy unless a volume is mounted at that path. If CONFIG_PATH points
     somewhere that is not on the volume, every deploy destroys the media folder
     -- and does it silently, because docker-entrypoint.sh reseeds config.json
     from the Secret File on boot, so the app comes back up looking healthy.
     Fix: mount the volume. Nothing on disk is recoverable; only the optional
     Google Drive mirror is.

Guessing between those two costs hours. This module answers it with evidence:
survey() says what is actually on the disk right now, and disk_evidence() says
whether that disk can be trusted to still be there tomorrow.

READ-ONLY BY DEFAULT. survey() and disk_evidence() change nothing. relocate()
moves files and defaults to dry_run.
"""
import json
import os
import time

IMAGE_EXTS = ("png", "jpg", "jpeg", "webp", "gif")

# One marker file, beside config.json, recording every boot this folder has seen.
# If it remembers more than one deploy, the folder demonstrably survived one --
# which is proof, where the path-shape check below is only inference.
MARKER = ".disk_history.json"
MAX_REMEMBERED = 12


# --------------------------------------------------------------------------
# What is actually on the disk
# --------------------------------------------------------------------------

def _images_under(folder):
    """(count, bytes, oldest_mtime, newest_mtime) for every image below `folder`."""
    n = 0
    size = 0
    oldest = None
    newest = None
    for dirpath, _dirs, filenames in os.walk(folder):
        for fn in filenames:
            if fn.lower().rsplit(".", 1)[-1] not in IMAGE_EXTS:
                continue
            fp = os.path.join(dirpath, fn)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            n += 1
            size += st.st_size
            m = st.st_mtime
            if oldest is None or m < oldest:
                oldest = m
            if newest is None or m > newest:
                newest = m
    return n, size, oldest, newest


def _sku_folders(root):
    """The per-SKU folders directly inside `root`, ignoring the account container."""
    out = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return out
    for name in names:
        if name.startswith("_acct"):
            continue
        p = os.path.join(root, name)
        if not os.path.isdir(p):
            continue
        n, size, oldest, newest = _images_under(p)
        if n:
            out.append({"sku": name, "images": n, "bytes": size,
                        "oldest": oldest, "newest": newest})
    return out


def survey(media_root, known_account_ids=None):
    """Every image under `media_root`, grouped by the workspace that can see it.

    Returns one entry per LOCATION. A location is either an account id (the
    library shows it when that workspace is open) or "" for the shared root
    (which NO account workspace lists -- only the default view does). An
    orphaned location is one holding images that no workspace will ever show.
    """
    known = set(str(a) for a in (known_account_ids or []))
    locations = []

    # The shared root: /data/media/<sku>/...  Visible only with no account open.
    shared = _sku_folders(media_root)
    if shared:
        locations.append({
            "account_id": "", "label": "shared root (no workspace)",
            "path": media_root, "known_account": False, "orphaned": True,
            "skus": shared,
            "images": sum(s["images"] for s in shared),
            "bytes": sum(s["bytes"] for s in shared),
        })

    # Per-account: /data/media/_acct/<id>/<sku>/...
    acct_root = os.path.join(media_root, "_acct")
    try:
        acct_names = sorted(os.listdir(acct_root))
    except OSError:
        acct_names = []
    for aid in acct_names:
        p = os.path.join(acct_root, aid)
        if not os.path.isdir(p):
            continue
        skus = _sku_folders(p)
        if not skus:
            continue
        # A folder for an account id that no longer exists in config is orphaned:
        # its images are on disk but no workspace can ever be opened to show them.
        is_known = (aid in known) if known else True
        locations.append({
            "account_id": aid, "label": aid,
            "path": p, "known_account": is_known, "orphaned": not is_known,
            "skus": skus,
            "images": sum(s["images"] for s in skus),
            "bytes": sum(s["bytes"] for s in skus),
        })

    total = sum(l["images"] for l in locations)
    orphaned = sum(l["images"] for l in locations if l["orphaned"])
    newest = None
    oldest = None
    for l in locations:
        for s in l["skus"]:
            if s["newest"] is not None and (newest is None or s["newest"] > newest):
                newest = s["newest"]
            if s["oldest"] is not None and (oldest is None or s["oldest"] < oldest):
                oldest = s["oldest"]
    return {
        "media_root": media_root,
        "root_exists": os.path.isdir(media_root),
        "locations": locations,
        "total_images": total,
        "orphaned_images": orphaned,
        "oldest": oldest, "newest": newest,
    }


# --------------------------------------------------------------------------
# Can this disk be trusted to still be here after the next deploy?
# --------------------------------------------------------------------------

def _nearest_mount(path):
    """The closest mount point at or above `path`.

    A Render volume mounted at /data makes /data itself a mount point, so this
    returns "/data". With no volume, nothing between the path and "/" is a
    mount, so it returns "/" -- which is the container filesystem, and that is
    wiped on every deploy. This is a direct reading of the kernel's mount table
    rather than a guess from the shape of the path.
    """
    p = os.path.abspath(path)
    while True:
        try:
            if os.path.ismount(p):
                return p
        except OSError:
            return None
        parent = os.path.dirname(p)
        if parent == p:
            return p
        p = parent


_RECORDED = {}   # data_dir -> the history as it stood after THIS process recorded


def record_boot(data_dir, build_id=None, force=False):
    """Note this boot in the marker file and return the accumulated history.

    ONCE PER PROCESS, per folder. disk_evidence() calls this, and /diag calls
    disk_evidence() -- so without the guard the count would rise every time
    someone opened the diagnostics page, and "this folder has seen 40 boots"
    would be measuring page views. The number is only worth anything if it
    counts what it claims to count.

    Best-effort: a folder that cannot be written to is exactly the situation
    being diagnosed, so a failure here is reported, never raised.
    """
    path = os.path.join(data_dir, MARKER)
    key = os.path.abspath(data_dir)
    if not force and key in _RECORDED:
        return dict(_RECORDED[key])
    now = time.time()
    build = str(build_id or os.environ.get("RENDER_GIT_COMMIT")
                or os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "")[:12]
    try:
        with open(path, encoding="utf-8") as fh:
            hist = json.load(fh)
        if not isinstance(hist, dict):
            raise ValueError("marker is not an object")
    except Exception:
        hist = {}

    hist.setdefault("first_seen", now)
    hist["boots"] = int(hist.get("boots") or 0) + 1
    hist["last_boot"] = now
    builds = [b for b in (hist.get("builds") or []) if isinstance(b, str)]
    if build and build not in builds:
        builds.append(build)
    hist["builds"] = builds[-MAX_REMEMBERED:]
    hist["current_build"] = build

    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(hist, fh)
        os.replace(tmp, path)
        hist["writable"] = True
    except Exception as e:
        hist["writable"] = False
        hist["write_error"] = str(e)
    _RECORDED[key] = dict(hist)
    return hist


def disk_evidence(data_dir, on_paas=None):
    """Is `data_dir` on a volume that outlives a deploy? With the evidence.

    Two independent readings, because either alone can mislead:
      mount   -- immediate, correct from the very first boot, but says nothing
                 about what happened to the data that was there before.
      history -- proof rather than inference (this folder has seen N boots
                 across M builds), but only after the app has been deployed
                 twice with this file in place.
    """
    data_dir = os.path.abspath(str(data_dir))
    if on_paas is None:
        on_paas = bool(os.environ.get("RENDER") or os.environ.get("RAILWAY_ENVIRONMENT")
                       or os.environ.get("DYNO"))
    mount = _nearest_mount(data_dir)
    # On Windows every path resolves to a drive root, and there is no PaaS to
    # wipe it -- so the mount reading only carries meaning on a hosted Linux box.
    mount_known = bool(on_paas) and os.name != "nt"
    on_volume = None
    if mount_known:
        # A dedicated volume is a mount point that is NOT a filesystem root.
        # Tested that way rather than against the literal string "/", because
        # "is this the root" is the actual question and a root spells itself
        # differently on every platform.
        on_volume = bool(mount) and os.path.dirname(mount) != mount

    hist = record_boot(data_dir)
    builds = hist.get("builds") or []
    survived_deploy = len(builds) >= 2
    age = time.time() - float(hist.get("first_seen") or time.time())

    if on_volume is False:
        verdict = "EPHEMERAL"
        detail = ("%s is on the container filesystem (nearest mount point: %s) -- "
                  "every deploy WIPES it, including the media folder"
                  % (data_dir, mount))
    elif survived_deploy:
        verdict = "PERSISTENT"
        detail = ("%s has survived %d boots across %d builds over %s -- proven persistent"
                  % (data_dir, int(hist.get("boots") or 0), len(builds), _ago(age)))
    elif on_volume is True:
        verdict = "PERSISTENT"
        detail = "%s is a mounted volume (%s)" % (data_dir, mount)
    else:
        verdict = "UNKNOWN"
        detail = ("%s -- not a hosted deployment, or too few boots recorded to "
                  "prove anything yet (%d so far)" % (data_dir, int(hist.get("boots") or 0)))

    return {
        "data_dir": data_dir,
        "verdict": verdict,
        "detail": detail,
        "mount_point": mount,
        "on_volume": on_volume,
        "on_paas": bool(on_paas),
        "boots": int(hist.get("boots") or 0),
        "builds": builds,
        "survived_deploy": survived_deploy,
        "first_seen": hist.get("first_seen"),
        "marker_writable": hist.get("writable", False),
    }


def _ago(seconds):
    s = int(seconds or 0)
    if s < 90:
        return "%ds" % s
    if s < 5400:
        return "%dm" % (s // 60)
    if s < 172800:
        return "%dh" % (s // 3600)
    return "%dd" % (s // 86400)


# --------------------------------------------------------------------------
# Putting images back where the library will find them
# --------------------------------------------------------------------------

def _free_name(dest_dir, fn):
    """A path in `dest_dir` for `fn` that does not already exist.

    Never overwrite. Two accounts can hold a same-named file for the same SKU
    (generated_1723...jpg is a timestamp, and a restored folder can collide with
    a regenerated one), and losing the newer to a move meant to RECOVER the
    older would be the worst possible outcome here.
    """
    target = os.path.join(dest_dir, fn)
    if not os.path.exists(target):
        return target, False
    stem, dot, ext = fn.rpartition(".")
    if not dot:
        stem, ext = fn, ""
    for i in range(1, 1000):
        alt = "%s_recovered%d%s%s" % (stem, i, "." if ext else "", ext)
        target = os.path.join(dest_dir, alt)
        if not os.path.exists(target):
            return target, True
    raise RuntimeError("could not find a free name for %s" % fn)


def relocate(media_root, src_account_id, dst_account_id, skus=None, dry_run=True):
    """Move SKU folders from one media location to another.

    src/dst of "" mean the shared root. `skus` limits it to named folders;
    None moves every SKU folder in the source. Returns a manifest of exactly
    which files moved, so a dry run can be shown before anything is touched.
    """
    if str(src_account_id or "") == str(dst_account_id or ""):
        raise ValueError("source and destination are the same location")

    def loc(aid):
        aid = str(aid or "")
        return os.path.join(media_root, "_acct", aid) if aid else media_root

    src = loc(src_account_id)
    dst = loc(dst_account_id)
    if not os.path.isdir(src):
        return {"ok": False, "error": "no such media location: %s" % src}

    wanted = set(skus) if skus else None
    moved = []
    renamed = 0
    failed = []
    for entry in _sku_folders(src):
        sku = entry["sku"]
        if wanted is not None and sku not in wanted:
            continue
        sku_src = os.path.join(src, sku)
        for dirpath, _dirs, filenames in os.walk(sku_src):
            rel = os.path.relpath(dirpath, sku_src)
            for fn in sorted(filenames):
                if fn.lower().rsplit(".", 1)[-1] not in IMAGE_EXTS:
                    continue
                sub = os.path.join(dst, sku) if rel == "." else os.path.join(dst, sku, rel)
                frm = os.path.join(dirpath, fn)
                try:
                    if dry_run:
                        # _free_name only reads the filesystem, so it gives the
                        # dry run the same answer the real move would produce --
                        # including the renamed-to-avoid-a-clash name, which is
                        # the part worth seeing before agreeing to it.
                        to, clash = _free_name(sub, fn)
                    else:
                        os.makedirs(sub, exist_ok=True)
                        to, clash = _free_name(sub, fn)
                        os.replace(frm, to)
                    if clash:
                        renamed += 1
                    moved.append({"sku": sku, "name": fn,
                                  "from": frm, "to": to, "renamed": bool(clash)})
                except Exception as e:
                    failed.append({"sku": sku, "name": fn, "error": str(e)})

    if not dry_run:
        # Tidy up the folders the files came out of, but only when genuinely
        # empty -- a leftover non-image file must never be deleted to make a
        # directory listing look neat.
        for dirpath, _dirs, _files in sorted(os.walk(src, topdown=False)):
            if dirpath == src:
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except OSError:
                pass

    return {"ok": True, "dry_run": bool(dry_run),
            "from": src_account_id or "", "to": dst_account_id or "",
            "from_path": src, "to_path": dst,
            "moved": len(moved), "renamed": renamed,
            "files": moved[:500], "failed": failed}
