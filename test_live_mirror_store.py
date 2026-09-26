"""domain/live_mirror_store.py: Sync's copy of each live listing survives a restart.

The mirror was a dict in server memory (_MIRROR_CACHE in routes/live_routes.py),
so every restart and deploy emptied the PDP's "Actual on Amazon" panel and the
listings row's condition until the next Sync (the owner's PDP redesign, 26 Sep
2026). Run on a throwaway database -- nothing real is touched.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
_tmp = tempfile.mkdtemp()
os.environ["ALTASCRAPER_DB"] = os.path.join(_tmp, "t.db")
CFG = os.path.join(_tmp, "config.json")
open(CFG, "w").write("{}")

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


from domain import live_mirror_store as S

print("=== stored, read back, with when it was read ===")
check("a write succeeds", S.save(CFG, "jack_uk", "uk", "SKU-1",
                                 {"title": "Brush", "condition": "new_new"}, 1000.0), True)
got = S.load(CFG, "jack_uk", "UK", ["SKU-1", "SKU-2"])
check("it comes back, marketplace case aside", sorted(got), ["SKU-1"])
check("  with its contents", got["SKU-1"]["condition"], "new_new")
check("  and the time Amazon was read", got["SKU-1"]["_synced_at"], 1000.0)

print("\n=== a later Sync replaces it; it never duplicates ===")
S.save(CFG, "jack_uk", "UK", "SKU-1", {"title": "Brush v2"}, 2000.0)
got = S.load(CFG, "jack_uk", "UK", ["SKU-1"])
check("the newer read wins", (got["SKU-1"]["title"], got["SKU-1"]["_synced_at"]), ("Brush v2", 2000.0))

print("\n=== one account's copy is not another's ===")
check("the same SKU on another account reads nothing",
      S.load(CFG, "nestwell_goods", "UK", ["SKU-1"]), {})

print("\n=== bad input is refused, not raised ===")
check("no account -> not written", S.save(CFG, "", "UK", "X", {}), False)
check("not a dict -> not written", S.save(CFG, "jack_uk", "UK", "X", "nope"), False)
check("asking for nothing -> nothing", S.load(CFG, "jack_uk", "UK", []), {})

print("\n=== wired where Sync writes and where the page reads ===")
LR = open(os.path.join(HERE, "routes", "live_routes.py"), encoding="utf-8").read()
check("Sync's pull saves each entry", "_lms.save(CONFIG_PATH, aid, mkt, sku, entry, _now)" in LR, True)
check("/live/mirror falls back to it", "_lms.load(CONFIG_PATH, aid, mkt, missing)" in LR, True)
MT = open(os.path.join(HERE, "static", "js", "miles_template.js"), encoding="utf-8").read()
check("the page asks for it when the catalogue loads", "loadSavedMirror();" in MT, True)

print("\nFAILURES: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
