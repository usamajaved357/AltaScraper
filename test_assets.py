import sys, os, re
sys.path.insert(0, r"D:\AltaScraper")
os.chdir(r"D:\AltaScraper")
fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(label)
    print("  %-56s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))

print("=== every local asset carries a version stamp ===")
for name in ("dashboard.html", "dash_login.html", "invite.html"):
    s = open(os.path.join("templates", name), encoding="utf-8").read()
    bare = re.findall(r'(?:src|href)="/static/[^"?]+"', s)
    check("%s has no unstamped asset" % name, bare, [])
    n = len(re.findall(r'/static/[^"]*\?v=\{\{ ASSET_V \}\}', s))
    print("     (%d stamped in %s)" % (n, name))

print("\n=== the stamp changes only when an asset changes ===")
import dashboard as D
app = D.app
with app.test_request_context("/"):
    pass
# Recompute the way build_app does.
def version():
    newest = 0.0
    for root, _d, files in os.walk("static"):
        for fn in files:
            try: newest = max(newest, os.path.getmtime(os.path.join(root, fn)))
            except OSError: pass
    return str(int(newest))
v1 = version()
check("it is a number", v1.isdigit(), True)
check("  and not zero", v1 != "0", True)
check("stable across calls", version(), v1)
p = os.path.join("static", "js", "users.js")
orig = os.path.getmtime(p)
# Push it past the CURRENT maximum, not merely past its own mtime -- the stamp
# is the newest file in the tree, and users.js was not the newest.
os.utime(p, (os.path.getatime(p), int(v1) + 60))
check("changes when a file is touched", version() != v1, True)
os.utime(p, (os.path.getatime(p), orig))
check("  and back again", version(), v1)

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)

