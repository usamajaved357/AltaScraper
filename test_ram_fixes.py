"""The 30 Sep 2026 RAM investigation: memory the server held on to for no reason.

The server itself sat at ~100 MB and flat; the growth was elsewhere. Each check
below fails without its fix:

  1. Dockerfile      MALLOC_ARENA_MAX=2, ALTA_RUNS_TOTAL=3, tini as PID 1
  2. image jobs      a saved image keeps only its link once delivered; finished
                     batches past their hour are dropped on every status read
  3. records cache   expired tabs dropped on each write, at most 8 held
  4. Miles run log   at most 10 finished runs in memory; the stream's chunk
                     copy dropped once the stream is gone
  5. scraping        the browser is closed on timeout, on error, and when the
                     timeout lands while it is still launching
"""
import os as _os_repo
_REPO = _os_repo.path.dirname(_os_repo.path.abspath(__file__))
import ast, asyncio, sys, tempfile, time, types
sys.path.insert(0, _REPO)

fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))

def _src(rel):
    return open(_os_repo.path.join(_REPO, rel), encoding="utf-8").read()


print("=== 1. Dockerfile ===")
df = _src("Dockerfile")
check("MALLOC_ARENA_MAX=2 is set", "ENV MALLOC_ARENA_MAX=2" in df, True)
check("production runs at most 3 listing runs at once", "ENV ALTA_RUNS_TOTAL=3" in df, True)
check("tini is installed by the apt line", "    tini \\\n" in df, True)
check("tini is PID 1 and starts the entrypoint",
      'ENTRYPOINT ["/usr/bin/tini", "--", "./docker-entrypoint.sh"]' in df, True)
check("  and the old bare entrypoint is gone", 'ENTRYPOINT ["./docker-entrypoint.sh"]' in df, False)
check("the code default is still 6 (the ENV only sets production)",
      '_int_env("ALTA_RUNS_TOTAL", 6, 1, 24)' in _src("domain/run_slots.py"), True)


print("\n=== 2. image jobs ===")
from domain import image_jobs as ij
big = "data:image/png;base64," + "A" * 200000
r = {"ok": True, "data_url": big, "saved_url": "/media/_acct/a/SKU1/x.jpg", "_payload": {"kind": "secondary"}}
ij._slim_saved_result(r)
check("a saved result keeps only its link", r["data_url"], "/media/_acct/a/SKU1/x.jpg")
check("  and its _payload (Redo re-sends it)", r["_payload"], {"kind": "secondary"})
r2 = {"ok": True, "data_url": big, "save_error": "disk full"}
ij._slim_saved_result(r2)
check("an UNSAVED result keeps its bytes (the only copy)", r2["data_url"] is big, True)
r3 = {"ok": True, "data_url": "https://cdn.example/x.png", "saved_url": "/media/x.jpg"}
ij._slim_saved_result(r3)
check("a small https link is left alone", r3["data_url"], "https://cdn.example/x.png")
check("_job_push itself does NOT slim (the first poll must carry the bytes)",
      "_slim_saved_result" in ast.get_source_segment(
          _src("domain/image_jobs.py"),
          next(n for n in ast.parse(_src("domain/image_jobs.py")).body
               if isinstance(n, ast.FunctionDef) and n.name == "_job_push")), False)

now = time.time()
ij._IMG_JOBS.clear()
ij._IMG_JOBS.update({
    "old_done":    {"status": "done",    "ts": now - 4000},
    "old_error":   {"status": "error",   "ts": now - 4000},
    "new_done":    {"status": "done",    "ts": now - 60},
    "long_run":    {"status": "running", "ts": now - 4000},
    "stuck_run":   {"status": "running", "ts": now - 3600 * 7},
})
ij._prune_img_jobs(now)
check("finished batches past the hour are dropped; recent and running kept",
      sorted(ij._IMG_JOBS), ["long_run", "new_done"])
ij._IMG_JOBS.clear()

gr = _src("routes/genimage_routes.py")
js = gr[gr.index("def genimage_job_status"):gr.index("def genimage_instructions")]
check("job_status prunes on every read", "_ij._prune_img_jobs()" in js, True)
check("job_status serialises BEFORE it slims",
      0 < js.index("resp = jsonify(") < js.index("_ij._slim_saved_result(_r)"), True)
ja = gr[gr.index("def genimage_jobs_active"):gr.index("def genimage_stop_all")]
check("jobs_active prunes too", "_ij._prune_img_jobs()" in ja, True)


print("\n=== 3. records cache ===")
dsrc = _src("dashboard.py")
fn = next(n for n in ast.parse(dsrc).body
          if isinstance(n, ast.FunctionDef) and n.name == "_records_cache_put")
ns = {"_RECORDS_CACHE": {}, "_RECORDS_TTL": 12, "_RECORDS_CACHE_MAX": 8}
exec(ast.get_source_segment(dsrc, fn), ns)
cache = ns["_RECORDS_CACHE"]
cache["stale"] = (time.time() - 60, [1] * 1000)
ns["_records_cache_put"]("fresh", [])
check("an expired tab is dropped on the next write", "stale" in cache, False)
for i in range(12):
    ns["_records_cache_put"]("tab%d" % i, [i])
    time.sleep(0.002)
check("at most 8 tabs are held", len(cache), 8)
check("  the oldest went first", sorted(cache) == sorted("tab%d" % i for i in range(4, 12)), True)
check("both writes in _records use it",
      dsrc.count("_records_cache_put(_key, "), 2)
check("  and none writes the dict directly", "_RECORDS_CACHE[_key] = " in dsrc, False)


print("\n=== 4. Miles run log ===")
from domain import miles_runlog as rl
saved_runs, saved_active = dict(rl._RUNS), dict(rl._ACTIVE)
rl._RUNS.clear(); rl._ACTIVE["id"] = None
for i in range(14):
    rl._RUNS["done%02d" % i] = {"meta": {"state": "done"}}
rl._RUNS["live"] = {"meta": {"state": "running"}}
rl._evict_finished()
check("only the newest 10 finished runs stay", sorted(k for k in rl._RUNS if k.startswith("done")),
      ["done%02d" % i for i in range(4, 14)])
check("  a running run is never evicted", "live" in rl._RUNS, True)

tmp = tempfile.mkdtemp()
def _gen():
    for i in range(3):
        yield "data: line %d\n\n" % i
rid, tail = rl.run_stream(tmp, "t", _gen)
out = list(tail)
check("the stream still delivers every chunk", sum("line" in c for c in out), 3)
e = rl._RUNS[rid]
check("  and its chunk copy is dropped once it has drained", e["chunks"], [])
check("  while the lines (for a reconnect) are kept", len(e["lines"]), 3)

def _slow():
    for i in range(5):
        time.sleep(0.05)
        yield "data: slow %d\n\n" % i
rid2, tail2 = rl.run_stream(tmp, "t2", _slow)
next(tail2); tail2.close()              # the browser went away
for _ in range(100):
    if rl._RUNS[rid2]["done"]: break
    time.sleep(0.05)
check("a closed stream stops collecting chunks", rl._RUNS[rid2]["chunks"], [])
check("  but the run itself finished and logged every line", len(rl._RUNS[rid2]["lines"]), 5)
rl._RUNS.clear(); rl._RUNS.update(saved_runs); rl._ACTIVE.update(saved_active)


print("\n=== 5. scraping closes its browser ===")
closed = []
class _Res:
    markdown = "hello"; cleaned_html = ""
class FakeCrawler:
    mode = "ok"
    def __init__(self, config=None): pass
    async def start(self):
        if FakeCrawler.mode == "hang_start":
            await asyncio.sleep(30)
        return self
    async def arun(self, url=None, config=None):
        if FakeCrawler.mode == "raise": raise RuntimeError("page blew up")
        if FakeCrawler.mode == "hang_run": await asyncio.sleep(30)
        return _Res()
    async def close(self): closed.append(FakeCrawler.mode)
fake = types.ModuleType("crawl4ai")
fake.AsyncWebCrawler = FakeCrawler
fake.CrawlerRunConfig = lambda **k: k
fake.BrowserConfig = lambda **k: k
sys.modules["crawl4ai"] = fake
from listing import scrape_helpers as sh
sh._BROWSER_CFG["cfg"] = {}
# timeout=-7900 -> the hard ceiling is (timeout/1000)+8 = 0.1 s
for mode, want_out in (("ok", "hello"), ("hang_run", ""), ("hang_start", "")):
    FakeCrawler.mode = mode
    got = asyncio.run(sh._scrape("https://x", timeout=-7900))
    check("%-10s returns %r" % (mode, want_out), got, want_out)
    check("%-10s closes the browser" % mode, closed[-1:] == [mode], True)
FakeCrawler.mode = "raise"
try:
    asyncio.run(sh._scrape("https://x", timeout=-7900)); raised = False
except RuntimeError:
    raised = True
check("an error still propagates as before", raised, True)
check("  and the browser was closed first", closed[-1:], ["raise"])


print()
if fails:
    print("FAILED: %d" % len(fails)); sys.exit(1)
print("ALL OK")
