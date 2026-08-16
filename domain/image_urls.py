"""domain/image_urls.py -- the key that signs public image URLs, kept for good.

WHY THIS EXISTS

Amazon does not store the image you send it as a file. It stores the ADDRESS
and fetches it -- at submission, and again later when it reprocesses a listing,
regenerates thumbnails, or revalidates the catalogue. So the address has to keep
working for as long as the listing does.

The app serves those images itself at

    /img/<token>/<path>

where the token is an HMAC so the media tree cannot be enumerated by guessing
paths. That token was signed with app.secret_key -- and APP_SECRET_KEY is not
set on this deployment, so Flask generates a random one on every boot. Every
image URL already given to Amazon therefore stopped working at the next deploy,
and the images would drop off the listings some time afterwards with nothing to
connect the two events.

That is the same fault as the image library emptying itself after a deploy: a
thing that must outlive a restart, kept somewhere that does not.

THE KEY IS ITS OWN, not the session secret. Two reasons:

  it works whether or not APP_SECRET_KEY has been set, which is the state this
  deployment is actually in;

  rotating the session secret is a sensible thing to do -- it signs out every
  user -- and it must not also break every image on every live listing.

Stored beside config.json, which is the persistent disk on the server, in the
same place users.json and the database live.
"""
import hashlib
import hmac
import os
import secrets

FILENAME = "image_url_key"
_CACHE = {}


def _path(config_path):
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), FILENAME)


def key(config_path):
    """The signing key, created once and then read for ever.

    Never raises: an image URL that cannot be signed is better handled by the
    caller (which falls back and says so) than by a crash on a page load.
    """
    p = _path(config_path)
    hit = _CACHE.get(p)
    if hit:
        return hit
    try:
        if os.path.exists(p):
            raw = open(p, "rb").read().strip()
            if len(raw) >= 32:
                _CACHE[p] = raw
                return raw
    except Exception:
        pass
    raw = secrets.token_hex(32).encode()
    try:
        # Written with the same care as any other secret on the disk: created
        # once, and not world-readable where the platform honours that.
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
    except Exception:
        # Could not persist it. The URLs still work for THIS process, which is
        # the old behaviour, so nothing gets worse -- but they will not survive
        # a restart, and diag() below says so rather than leaving it to be
        # discovered when the pictures vanish.
        pass
    _CACHE[p] = raw
    return raw


def token(config_path, relpath):
    """The signature for one media path."""
    return hmac.new(key(config_path),
                    ("pubimg:" + str(relpath)).encode("utf-8"),
                    hashlib.sha256).hexdigest()[:24]


def base_url(config_path=None):
    """Where this app is reachable from the open internet, or "".

    PUBLIC_BASE_URL wins; otherwise public_base_url in config.json, which is the
    one a person can set without touching the deployment. Empty means we do not
    know -- and an image URL built on a guess is worse than no image, because
    Amazon accepts it, fetches nothing, and the listing goes up without pictures.
    """
    v = (os.environ.get("PUBLIC_BASE_URL", "") or "").strip()
    if not v and config_path:
        try:
            import json
            with open(config_path, encoding="utf-8") as fh:
                v = str((json.load(fh) or {}).get("public_base_url") or "").strip()
        except Exception:
            v = ""
    v = v.rstrip("/")
    # Amazon requires https for an image locator, and the host in front of this
    # app terminates TLS.
    if v.startswith("http://"):
        v = "https://" + v[len("http://"):]
    return v


def public_url(config_path, media_path):
    """'/media/x/y.jpg' -> a full signed URL Amazon can fetch, or "".

    The SAME address the image library hands out, built in one place so a picture
    that works when pushed to a live listing cannot fail when the same draft is
    submitted -- those were two different code paths reaching two different
    answers, and the submit one quietly dropped the image.
    """
    p = str(media_path or "").strip()
    if p.startswith("http://") or p.startswith("https://"):
        return p                          # already public; nothing to do
    if not p.startswith("/media/"):
        return ""
    rel = p[len("/media/"):]
    if not rel or ".." in rel:
        return ""
    base = base_url(config_path)
    if not base:
        return ""
    # The path is quoted but the TOKEN is signed over the raw path, because that
    # is what the route re-signs when it checks: Flask hands the handler the
    # decoded path, so signing the encoded form would never match.
    from urllib.parse import quote as _q
    return "%s/img/%s/%s" % (base, token(config_path, rel), _q(rel))


def diag(config_path):
    """For /diag: is the key persistent, and since when."""
    p = _path(config_path)
    try:
        if os.path.exists(p):
            import datetime as _dt
            when = _dt.datetime.fromtimestamp(os.path.getmtime(p))
            return {"persistent": True, "path": p,
                    "since": when.strftime("%Y-%m-%d %H:%M"),
                    "note": "Image links given to Amazon survive a restart."}
        return {"persistent": False, "path": p,
                "note": ("The image signing key could not be written, so links "
                         "already given to Amazon will stop working when this "
                         "app restarts and the pictures will drop off the "
                         "listings. Check the disk at %s is writable." % p)}
    except Exception as e:
        return {"persistent": False, "error": str(e)[:200]}
