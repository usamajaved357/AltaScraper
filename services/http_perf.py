"""services/http_perf.py -- how the app's bytes reach the browser.

NOTHING HERE CHANGES A SINGLE FIGURE. It changes how the same bytes travel:
whether they are compressed, and whether a file the browser already has must be
asked for again. Both are settings on the response, not on the answer.

WHAT WAS MEASURED, on a cold load of / with a real browser (Playwright,
21 Aug 2026, jack_uk):

    load event                 11.4 s
    DOMContentLoaded            4.0 s
    resources                     176
    transferred                10.7 MB
    Content-Encoding             none on every single response
    Cache-Control       "no-cache" on all 83 script files and both stylesheets

TWO THINGS, AND THEY ARE BOTH ONE LINE OF HTTP.

1. NOTHING WAS COMPRESSED. Not the 1.3 MB of listing rows, not the 142 KB page,
   not the 230 KB stylesheet, not any of the 1.8 MB of JavaScript. JSON and
   JavaScript compress by roughly four to eight times, so most of that 10.7 MB
   was never information -- it was repetition being sent over the wire at full
   price. On a phone, or on Talha's connection to a server in another country,
   that is the whole of the wait.

2. NOTHING WAS CACHEABLE, although everything was already versioned.
   Flask's default for static files is `no-cache`, which does not mean "do not
   store it" -- it means "ask me every time". So every reload made 85 round
   trips to be told 85 times that nothing had changed. The URLs ALREADY carry
   `?v=<newest mtime under static/>` (see _asset_version in dashboard.py), which
   is exactly the condition under which a file may be cached for ever: when it
   changes, its URL changes, so the browser asks for a different thing rather
   than asking again about the same thing. The versioning was there and the
   header that makes it worth anything was not.

WHAT IS DELIBERATELY NOT COMPRESSED
    text/event-stream   the run log and the Miles tail. Compression buffers, and
                        a buffered live log is a log that arrives after the run
                        it was describing.
    direct_passthrough  send_file responses. The body is a file handle, not
                        bytes; reading it here to compress it would load whole
                        media files into memory.
    already encoded     anything that set Content-Encoding itself.
    images, video, zip  already compressed. Re-compressing costs CPU and adds
                        bytes.
    under 1 KB          the header costs more than the saving.
    206 / 304           a range or a not-modified. There is no body to compress
                        and rewriting the length breaks both.

VARY: ACCEPT-ENCODING is added rather than set. The app already sends
`Vary: Cookie`; replacing it would let a shared cache serve one account's page
to another, which is a far worse bug than a slow one.
"""
import gzip
import io

# Compressed only if the type is one that compresses. Checked by prefix on the
# mimetype, so "application/json; charset=utf-8" matches "application/json".
_COMPRESSIBLE = (
    "text/",
    "application/json",
    "application/javascript",
    "application/manifest+json",
    "application/xml",
    "application/xhtml+xml",
    "image/svg+xml",
)

# Below this, gzip's own header and trailer eat the saving.
_MIN_BYTES = 1024

# A year. The URL carries ?v=, so a changed file is a changed URL.
_IMMUTABLE = "public, max-age=31536000, immutable"


def _wants_gzip(request):
    return "gzip" in (request.headers.get("Accept-Encoding") or "").lower()


# A static file big enough to be worth reading into memory to compress, and
# small enough that doing so is not itself the problem. The 1.8 MB of JavaScript
# this app ships is all well under this; a video in static/ would not be, and
# would not compress anyway (see _COMPRESSIBLE).
_MAX_PASSTHROUGH = 8 * 1024 * 1024


def _compressible(resp, static=False):
    if resp.direct_passthrough:
        # send_file: the body is an open file handle, not bytes. Reading it here
        # is right for a 140 KB script and wrong for a 300 MB video, so it is
        # allowed only for the app's own versioned static text files, and only
        # up to a size. Everything else -- uploaded media, generated images,
        # exports -- streams as before.
        if not static:
            return False
        # A LENGTH IS REQUIRED, not merely respected. Without one there is no
        # way to know what reading the body would cost, and `or 0` would have
        # read an unbounded stream into memory to compress it -- the one case
        # the size cap exists to prevent.
        try:
            n = int(resp.headers.get("Content-Length"))
        except (TypeError, ValueError):
            return False
        if n <= 0 or n > _MAX_PASSTHROUGH:
            return False
    if resp.headers.get("Content-Encoding"):  # somebody already encoded it
        return False
    if resp.status_code in (204, 206, 304) or resp.status_code < 200:
        return False
    mt = (resp.mimetype or "").lower()
    if mt == "text/event-stream":             # a live log must not be buffered
        return False
    if not any(mt.startswith(p) for p in _COMPRESSIBLE):
        return False
    return True


def _add_vary(resp, value):
    """Append to Vary without dropping what is already there."""
    have = [v.strip() for v in (resp.headers.get("Vary") or "").split(",")
            if v.strip()]
    if value.lower() not in [v.lower() for v in have]:
        have.append(value)
        resp.headers["Vary"] = ", ".join(have)


def install(app):
    """Attach the compression and caching headers. Returns the app."""

    @app.after_request
    def _perf_headers(resp):
        try:
            from flask import request
        except Exception:
            return resp

        # ---- a versioned static file may be kept for ever ------------------
        # ONLY when ?v= is present. Without it the URL does not change when the
        # file does, and a year-long cache would be a year-long stale asset with
        # no way to clear it but a new browser.
        try:
            static = request.path.startswith("/static/")
        except Exception:
            return resp
        try:
            # /static/vendor/ holds third-party files at a pinned version --
            # tabler-icons 3.5.0 and its woff2. They never change without the
            # folder changing, and the font is referenced from inside the
            # stylesheet as "?v3.5.0", which is the library's own stamp and not
            # a "v" parameter this app can read.
            if static and (request.args.get("v")
                           or request.path.startswith("/static/vendor/")):
                if resp.status_code in (200, 304):
                    resp.headers["Cache-Control"] = _IMMUTABLE
        except Exception:
            pass

        # ---- and the bytes themselves ---------------------------------------
        try:
            if not _wants_gzip(request) or not _compressible(resp, static):
                return resp
            _add_vary(resp, "Accept-Encoding")
            # A passthrough response refuses get_data() outright -- the body is
            # a file wrapper, and Werkzeug will not silently read it. Turning
            # passthrough off first lets it join the iterable, which reads the
            # file. Guarded above to the app's own static text files.
            if resp.direct_passthrough:
                resp.direct_passthrough = False
            data = resp.get_data()
            if len(data) < _MIN_BYTES:
                return resp
            buf = io.BytesIO()
            # mtime=0 so the same body gives the same bytes every time, which
            # keeps ETags stable across restarts.
            with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6,
                               mtime=0) as gz:
                gz.write(data)
            packed = buf.getvalue()
            if len(packed) >= len(data):     # already-compressed content
                return resp
            resp.set_data(packed)
            resp.headers["Content-Encoding"] = "gzip"
            resp.headers["Content-Length"] = str(len(packed))
            # The ETag was computed from the uncompressed body. Left as it is it
            # would claim two different bodies are the same thing.
            if resp.headers.get("ETag"):
                et = resp.headers["ETag"]
                if not et.endswith('-gzip"'):
                    resp.headers["ETag"] = et.rstrip('"') + '-gzip"'
        except Exception:
            # A response that could not be compressed is still a response. This
            # must never be the reason a screen fails to load.
            return resp
        return resp

    return app
