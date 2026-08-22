"""The bytes are compressed, the cached files stay cached, and the live logs stream.

WHAT WAS MEASURED before this existed, on a cold load of / with a real browser
(Playwright, 21 Aug 2026, jack_uk):

    load event                 11.4 s
    DOMContentLoaded            4.0 s
    resources                     176
    transferred                10.7 MB
    Content-Encoding             none on every single response
    Cache-Control       "no-cache" on all 83 script files and both stylesheets

AFTER: load 4.9 s, DOMContentLoaded 1.5 s, 115 resources, 2.0 MB.

Nothing about what the app SAYS changed. What changed is that the same bytes
travel compressed, that a file the browser already has is not asked for again,
and that the icon font comes from this server rather than from two CDNs.

THE THREE THINGS THAT WOULD BREAK SILENTLY IF THIS REGRESSED, which is why they
are tested rather than eyeballed:

  a live log that got buffered   text/event-stream is how the run log and the
                                 Miles tail reach the screen. gzip buffers, and
                                 a buffered live log arrives after the run it
                                 was describing -- looking exactly like a run
                                 that produced no output.

  a year-long stale asset        `immutable` on a URL with no version in it
                                 means a fix that cannot reach the browser for
                                 a year, and no way to clear it but a new
                                 machine. Only versioned URLs may be immutable.

  a shared cache serving the     the app already sends `Vary: Cookie`. Setting
  wrong account's page           Vary rather than appending to it would let one
                                 account's page be handed to another.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return open(os.path.join(HERE, *p), encoding="utf-8").read()


from services import http_perf as _hp


class _Resp(object):
    """Just enough of a Flask response to ask _compressible about it."""
    def __init__(self, mimetype="text/html", status=200, passthrough=False,
                 encoding=None, length=None):
        self.mimetype = mimetype
        self.status_code = status
        self.direct_passthrough = passthrough
        self.headers = {}
        if encoding:
            self.headers["Content-Encoding"] = encoding
        if length is not None:
            self.headers["Content-Length"] = str(length)


print("== what is compressed ==")
for mt in ("text/html", "text/css", "application/json", "application/javascript",
           "image/svg+xml", "text/csv"):
    truthy("  %s" % mt, _hp._compressible(_Resp(mt)))

print("\n== and what is deliberately not ==")
falsy("a live log is never buffered (text/event-stream)",
      _hp._compressible(_Resp("text/event-stream")))
falsy("  a streamed file is left streaming", _hp._compressible(_Resp("text/csv", passthrough=True)))
truthy("  unless it is one of our own versioned static files",
       _hp._compressible(_Resp("application/javascript", passthrough=True, length=140000),
                         static=True))
falsy("  and not even then past the size cap",
      _hp._compressible(_Resp("application/javascript", passthrough=True,
                              length=_hp._MAX_PASSTHROUGH + 1), static=True))
falsy("  a passthrough with no length is left alone",
      _hp._compressible(_Resp("application/javascript", passthrough=True), static=True))
falsy("something already encoded is not encoded twice",
      _hp._compressible(_Resp("application/json", encoding="gzip")))
for mt in ("image/png", "image/jpeg", "video/mp4", "application/zip",
           "application/pdf", "font/woff2"):
    falsy("  %s is already compressed" % mt, _hp._compressible(_Resp(mt)))
for code in (204, 206, 304):
    falsy("  a %d has no body to compress" % code,
          _hp._compressible(_Resp("text/html", status=code)))

print("\n== Vary is added, never replaced ==")
r = _Resp()
r.headers["Vary"] = "Cookie"
_hp._add_vary(r, "Accept-Encoding")
check("Cookie survives", r.headers["Vary"], "Cookie, Accept-Encoding")
_hp._add_vary(r, "Accept-Encoding")
check("  and is not added twice", r.headers["Vary"], "Cookie, Accept-Encoding")
r2 = _Resp()
_hp._add_vary(r2, "Accept-Encoding")
check("  with nothing there it is just set", r2.headers["Vary"], "Accept-Encoding")

print("\n== only a versioned URL may be cached for a year ==")
SRC = read("services", "http_perf.py")
truthy("immutable is a year", "max-age=31536000" in _hp._IMMUTABLE
       and "immutable" in _hp._IMMUTABLE)
truthy("  and only with ?v= ...", 'request.args.get("v")' in SRC)
truthy("  ...or under /static/vendor, which is pinned by folder",
       '"/static/vendor/"' in SRC)
truthy("the assets really are versioned in the page",
       "?v={{ ASSET_V }}" in read("templates", "dashboard.html"))
truthy("  and the stamp is the newest mtime under static/",
       "_asset_version" in read("dashboard.py"))

print("\n== the threshold is a real one ==")
truthy("nothing under 1 KB is compressed", _hp._MIN_BYTES >= 1024)
truthy("  and gzip is deterministic across restarts, so ETags are stable",
       "mtime=0" in SRC)
truthy("a compressed body gets a different ETag from the plain one",
       "-gzip" in SRC)

print("\n== the icon font is this server's, and complete ==")
H = read("templates", "dashboard.html")
falsy("no stylesheet comes from jsdelivr any more",
      'rel="stylesheet" href="https://cdn.jsdelivr.net' in H)
falsy("  nor from unpkg", "unpkg.com" in H)
truthy("  it is served from /static/vendor",
       "/static/vendor/tabler-icons/tabler-icons.min.css" in H)
CSS_P = os.path.join(HERE, "static", "vendor", "tabler-icons", "tabler-icons.min.css")
truthy("the stylesheet is on disk", os.path.exists(CSS_P))
W2 = os.path.join(HERE, "static", "vendor", "tabler-icons", "fonts",
                  "tabler-icons.woff2")
truthy("  and so is the font it names", os.path.exists(W2))
if os.path.exists(CSS_P):
    CSS = read("static", "vendor", "tabler-icons", "tabler-icons.min.css")
    truthy("the text of the page never waits for the icons",
           "font-display:swap" in CSS)
    falsy("  no reference is left to a font that is not here",
          ".ttf" in CSS or ".woff\"" in CSS or ".woff?" in CSS)
    truthy("  woff2 is still referenced", "woff2" in CSS)
    # EVERY icon the app asks for must exist in this stylesheet. A missing one
    # renders as an empty box with no error anywhere.
    import glob
    import re
    used = set()
    partial = set()
    for f in (glob.glob(os.path.join(HERE, "templates", "*.html"))
              + glob.glob(os.path.join(HERE, "static", "js", "*.js"))):
        for m in re.finditer(r"\bti-([a-z0-9-]+)",
                             open(f, encoding="utf-8", errors="replace").read()):
            n = m.group(1)
            # A NAME ENDING IN A HYPHEN IS HALF OF ONE. Six places build the
            # class from a condition -- `'ti-chevron-' + (open ? "down" :
            # "right")` -- so the scan sees a prefix, not an icon. Recorded
            # separately and completed by hand below, because a scan cannot
            # know what the other half will be and pretending otherwise is how
            # a subset font ends up missing exactly the icons that move.
            (partial if n.endswith("-") else used).add(n)
    have = set(re.findall(r"\.ti-([a-z0-9-]+):before", CSS))
    missing = sorted(n for n in used if n not in have)
    check("every ti-* the app writes out in full exists", missing, [])
    check("  the scan found the known half-names", sorted(partial),
          ["chevron-"])
    # Both halves of each, read off the source.
    #
    # `layout-sidebar-` used to be here as well: sidebar.js picked a side and
    # appended "-collapse", giving layout-sidebar-<side>-collapse. That icon is
    # gone on purpose -- the fold control is now a fixed ti-menu-2 in both
    # states, because a glyph that flips direction is not read as a menu button
    # and the label had to carry the meaning instead. A CONSTANT NAME NEEDS NO
    # ENTRY HERE: the scan above sees it in full and checks it like any other.
    built = ["chevron-down", "chevron-right"]
    check("  and the names they build exist too",
          sorted(n for n in built if n not in have), [])
    print("     (%d written out, %d built at runtime, %d available)"
          % (len(used), len(built), len(have)))

print("\n== the 269 KB spreadsheet library is off the critical path ==")
truthy("SheetJS is deferred", 'defer src="https://cdn.jsdelivr.net/npm/xlsx' in H)
truthy("  and it is only ever used on a file the user picked",
       'typeof XLSX==="undefined"' in read("static", "js", "miles.js"))

print("\n== it is actually installed ==")
D = read("dashboard.py")
truthy("dashboard.py installs it", "http_perf.install(app)" in D)
truthy("  and says so out loud if it could not",
       "compression/caching not installed" in D)

print("\n== end to end, against a running app ==")
# The only proof that matters: real bytes, over a real socket, decompressing
# back to exactly what was sent.
probe = r'''
import gzip, json, os, socket, sys, threading, time, urllib.request
sys.path.insert(0, %r)
os.chdir(%r)
from flask import Flask, Response
from services import http_perf
app = Flask(__name__, static_folder=os.path.join(%r, "static"))
http_perf.install(app)
BIG = ("hello world " * 4000)
@app.route("/big")
def big(): return BIG
@app.route("/small")
def small(): return "hi"
@app.route("/live")
def live():
    def gen():
        for i in range(3): yield "data: %%d\n\n" %% i
    return Response(gen(), mimetype="text/event-stream")
@app.route("/img")
def img(): return Response(b"\x89PNG" + b"\x00" * 4000, mimetype="image/png")
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
threading.Thread(target=lambda: app.run(port=port, threaded=True), daemon=True).start()
for _ in range(80):
    try:
        urllib.request.urlopen("http://127.0.0.1:%%d/small" %% port, timeout=1); break
    except Exception: time.sleep(.1)
def get(path, enc="gzip"):
    r = urllib.request.Request("http://127.0.0.1:%%d%%s" %% (port, path),
                               headers={"Accept-Encoding": enc})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return resp.read(), dict(resp.headers)
big_gz, h1 = get("/big")
big_pl, _  = get("/big", "identity")
small_b, h2 = get("/small")
live_b, h3 = get("/live")
img_b,  h4 = get("/img")
js_gz,  h5 = get("/static/js/cogs.js?v=1")
js_pl,  _  = get("/static/js/cogs.js?v=1", "identity")
print(json.dumps({
  "big_encoded": h1.get("Content-Encoding"),
  "big_roundtrips": gzip.decompress(big_gz).decode() == BIG,
  "big_smaller": len(big_gz) < len(big_pl) / 4,
  "big_len_header": h1.get("Content-Length") == str(len(big_gz)),
  "big_vary": h1.get("Vary"),
  "small_encoded": h2.get("Content-Encoding"),
  "live_encoded": h3.get("Content-Encoding"),
  "live_body": live_b.decode(),
  "img_encoded": h4.get("Content-Encoding"),
  "js_encoded": h5.get("Content-Encoding"),
  "js_roundtrips": gzip.decompress(js_gz) == js_pl,
  "js_cache": h5.get("Cache-Control"),
}))
''' % (HERE, HERE, HERE)
try:
    fd, path = tempfile.mkstemp(suffix=".py", dir=HERE)
    os.write(fd, probe.encode("utf-8"))
    os.close(fd)
    out = subprocess.run([sys.executable, path], capture_output=True, text=True,
                         cwd=HERE, timeout=180)
    os.unlink(path)
    if out.returncode != 0:
        fails.append("the live probe failed to run")
        print("  FAIL:", (out.stderr or "")[-500:])
    else:
        import json as _j
        g = _j.loads(out.stdout.strip().splitlines()[-1])
        check("a big text response is gzipped", g["big_encoded"], "gzip")
        truthy("  and unzips to exactly what was sent", g["big_roundtrips"])
        truthy("  at less than a quarter the size", g["big_smaller"])
        truthy("  with a Content-Length that matches the compressed body",
               g["big_len_header"])
        truthy("  and Vary names Accept-Encoding",
               "Accept-Encoding" in (g["big_vary"] or ""))
        check("a two-byte response is left alone", g["small_encoded"], None)
        check("a live log is NOT compressed", g["live_encoded"], None)
        check("  and still arrives whole",
              g["live_body"], "data: 0\n\ndata: 1\n\ndata: 2\n\n")
        check("a PNG is not re-compressed", g["img_encoded"], None)
        check("a static script IS compressed", g["js_encoded"], "gzip")
        truthy("  and unzips to the file on disk byte for byte", g["js_roundtrips"])
        check("  and a versioned one is cacheable for a year",
              g["js_cache"], "public, max-age=31536000, immutable")
except Exception as e:
    fails.append("live probe")
    print("  FAIL live probe:", str(e)[:300])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
