"""Sales must arrive without anyone pressing Sync.

THE REPORT: "Total Sales GBP 0" for a week that had sales.

THE CAUSE: domain/sales_fetch.sync() had exactly ONE caller -- the Sync button.
The background refresher kept the catalogue and the images fresh and never
touched sales, so a dashboard nobody had pressed Sync on showed zero for days
Amazon had been holding all along.

MEASURED at the time, on jack_uk: Amazon's Sales & Traffic report had 2026-08-14
ready -- 87 sessions, 150 page views, 3 units, 89.97 of sales -- while the screen
said 0 for that week. Nothing was late at Amazon's end; the app never asked.

Drives the real worker loop with Amazon replaced, because the thing being tested
is WHEN the app decides to ask, not what Amazon says back.
"""
import sys, time, types

sys.path.insert(0, r"D:\AltaScraper")

import domain.live_refresher as lr

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def check_true(label, got):
    check(label, bool(got), True)


print("\n== the refresher knows sales exist at all ==")
check_true("there is a sales step in the worker", hasattr(lr, "_sales_one"))
check_true("and a cheap way to ask if it is behind", hasattr(lr, "_sales_gap"))
check_true("budgeted per pass rather than all at once", lr.SALES_PER_PASS <= 5)

print("\n== a pass does ONE thing, and sales waits for the catalogue ==")
src = open(r"D:\AltaScraper\domain\live_refresher.py", encoding="utf-8").read()
loop = src[src.index("def _loop("):src.index("def _supervisor(")]
i_cat = loop.index("_refresh_one(")
i_sales = loop.index("_sales_one(")
i_img = loop.index("_needs_images(")
check("the catalogue is attempted before sales", i_cat < i_sales, True)
check("and sales before images", i_sales < i_img, True)
check_true("the sales branch ends the pass rather than falling through",
           "continue           # one piece of work per pass" in loop)
check_true("it stands aside for a person's own Sync", "user_busy(account_id)" in loop)

print("\n== the loop actually calls it, with Amazon stood in for ==")
called = {"sales": 0, "args": None, "catalogue": 0}


class _FakeApp(object):
    view_functions = {}

    def test_request_context(self, *a, **k):
        called["args"] = k.get("json")

        class _C(object):
            def __enter__(s):
                return s

            def __exit__(s, *e):
                return False
        return _C()


def _fake_view():
    called["sales"] += 1
    r = types.SimpleNamespace()
    r.json = {"ok": True, "fetched": 3, "rows": 42, "still_missing": 4}
    return r


app = _FakeApp()
app.view_functions = {"sales_sync_now": _fake_view}

note = lr._sales_one(app, "jack_uk", "UK")
check("the sales route was driven once", called["sales"], 1)
check("it named the account, so the server cannot use its global",
      (called["args"] or {}).get("account_id"), "jack_uk")
check("  and the marketplace", (called["args"] or {}).get("marketplace"), "UK")
check("  and asked for a small budget", (called["args"] or {}).get("budget"),
      lr.SALES_PER_PASS)
check_true("what it did is reported in words", "3 day(s), 42 row(s)" in note)
check_true("including how far behind it still is", "4 still behind" in note)

print("\n== a refusal is reported, never raised ==")


def _boom():
    raise RuntimeError("QuotaExceeded")


app.view_functions = {"sales_sync_now": _boom}
n2 = lr._sales_one(app, "jack_uk", "UK")
check_true("an exception comes back as a note", n2.startswith("error:"))
check_true("naming the reason", "QuotaExceeded" in n2)

app.view_functions = {}
n3 = lr._sales_one(app, "jack_uk", "UK")
check("a missing route is reported too", n3, "no sales_sync route")


def _refused():
    r = types.SimpleNamespace()
    r.json = {"ok": False, "error": "no marketplace selected"}
    return r


app.view_functions = {"sales_sync_now": _refused}
n4 = lr._sales_one(app, "jack_uk", "UK")
check_true("a refusal by the route is reported", n4.startswith("failed:"))

print("\n== the gap check never throws, whatever the database says ==")
# It runs inside a worker that must never die, so the property that matters is
# that it always returns a number. An account with no stored days legitimately
# reports the whole window as missing -- that is a backfill waiting to happen,
# not an error -- so the value is not asserted, only that asking is safe.
try:
    g = lr._sales_gap("/nowhere/at/all", "jack_uk", "UK")
    check_true("asking about an unknown database is safe", isinstance(g, int))
except Exception as e:
    check("asking about an unknown database is safe", "raised %s" % e, "no exception")

import tempfile, os
_tmp = tempfile.mkdtemp(prefix="altacatch_")
open(os.path.join(_tmp, "config.json"), "w").write("{}")
g2 = lr._sales_gap(os.path.join(_tmp, "config.json"), "jack_uk", "UK")
check_true("a fresh account reads as behind, so it gets backfilled", g2 > 0)
import shutil
shutil.rmtree(_tmp, ignore_errors=True)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
