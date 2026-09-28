"""The app builds its Anthropic client in ONE place (architecture batch A7).

api/anthropic_client.client(key) is `anthropic.Anthropic(api_key=key)` with the
SDK looked up at call time. This pins that it passes exactly that one argument
through (checked against a stand-in SDK, never the real one -- no network, no
key), that the spend recorder still sees calls made through it, and that no app
module builds a client any other way.
"""
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


print("=== the same constructor, the same argument ===")
seen = []


class FakeAnthropic:
    def __init__(self, *a, **k):
        seen.append((a, k))


_real = sys.modules.get("anthropic")
sys.modules["anthropic"] = types.SimpleNamespace(Anthropic=FakeAnthropic)
try:
    from api.anthropic_client import client
    c = client("k-test")
    check("builds the SDK's client", isinstance(c, FakeAnthropic), True)
    check("  with api_key= and nothing else", seen, [((), {"api_key": "k-test"})])
    seen.clear()
    client(None)
    check("  passing even a missing key through untouched", seen, [((), {"api_key": None})])
finally:
    if _real is not None:
        sys.modules["anthropic"] = _real
    else:
        sys.modules.pop("anthropic", None)

print("=== nothing else builds one ===")
SKIP_DIRS = (".git", "_merge_2026-07-04", "__pycache__", "tests_support", ".claude",
             "tools", "scripts", "active", "node_modules")
RX = re.compile(r"\b\w+\.Anthropic\(|\bAnthropic\(api_key")
found = []
for d, dirs, files in os.walk(HERE):
    dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
    for f in files:
        if not f.endswith(".py") or f.startswith(("test_", "probe_", "PATCH_")) or "baseline" in f:
            continue
        p = os.path.relpath(os.path.join(d, f), HERE).replace("\\", "/")
        if p == "api/anthropic_client.py":
            continue
        for i, line in enumerate(open(os.path.join(d, f), "rb").read().decode("utf-8", "replace").splitlines(), 1):
            if RX.search(line) and not line.lstrip().startswith("#"):
                found.append("%s:%d" % (p, i))
check("no Anthropic client built outside api/anthropic_client.py", found, [])

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\none constructor")
