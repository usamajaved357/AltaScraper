"""An eBay token is reused only by the keys that fetched it.

api/ebay.token() kept ONE token for the whole process and handed it to any
caller -- one with no keys at all, or keys changed in Settings a minute ago --
for up to two hours. No network: urlopen is replaced with a fake that counts.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import ebay as E

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-60s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


calls = []


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen(req, timeout=None):
    calls.append(req)
    n = len(calls)
    return _Resp(json.dumps({"access_token": "tok%d" % n, "expires_in": 7200}).encode())


E.urllib.request.urlopen = _fake_urlopen
E._TOKEN_CACHE.clear()
E._TOKEN_CACHE.update({"token": None, "expires_at": 0.0})

print("\n1. the same keys reuse their token")
check("first call fetches", E.token("APP_A", "CERT_A"), "tok1")
check("second call with the same keys reuses it", E.token("APP_A", "CERT_A"), "tok1")
check("  one fetch in all", len(calls), 1)

print("\n2. other keys, or none, never get it")
check("different keys fetch their own", E.token("APP_B", "CERT_B"), "tok2")
check("no keys -> no token (not someone else's)", E.token("", ""), "")

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
