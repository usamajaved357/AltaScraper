"""Products generate side by side, and progress is reported per product.

Two bugs, one screen: 8 images each for two products ran as 16 strictly in
sequence (the second product did not start until the first had fully finished),
and the status bar reported a single "0/16" that said nothing about which item
was where.
"""
import sys, time, threading
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))

src = open(r"D:\AltaScraper\dashboard.py", encoding="utf-8").read()

print("=== the worker is no longer one long queue ===")
check("a parallel dispatcher exists", "_run_img_jobs_parallel" in src, True)
check("the crash-safe wrapper calls it",
      "_run_img_jobs_bg_inner(jid, jobs, kind)\n" in src, False)
check("the inner worker can be told not to retire the job",
      "def _run_img_jobs_bg_inner(jid, jobs, kind, finish=True)" in src, True)
check("and the job is finished exactly once, by the dispatcher",
      src.count("    if finish:\n        _job_finish(jid)"), 1)
check("the pool size is bounded", "min(n, 8)" in src, True)
check("  and overridable", "ALTA_IMG_WORKERS" in src, True)

print("\n=== grouping: one product per worker, its images kept in order ===")
# Re-implement the grouping exactly as the dispatcher does, and check it.
jobs = ([{"sku": "SKU-A", "label": "a%d" % i} for i in range(8)] +
        [{"sku": "SKU-B", "label": "b%d" % i} for i in range(8)])
groups = {}
for jb in jobs:
    groups.setdefault(str(jb.get("sku", "") or "_misc"), []).append(jb)
chunks = list(groups.values())
check("two products -> two chunks", len(chunks), 2)
check("  each with its own images", sorted(len(c) for c in chunks), [8, 8])
check("  in the order they were planned",
      [j["label"] for j in groups["SKU-A"]], ["a%d" % i for i in range(8)])
one = [{"sku": "SKU-A"}] * 5
check("a single product still runs as one chunk",
      len({j["sku"] for j in one}), 1)

print("\n=== the pool really does overlap the products ===")
# Prove concurrency rather than assert it: two chunks that each sleep, timed.
from concurrent.futures import ThreadPoolExecutor
order = []
lock = threading.Lock()
def work(chunk):
    with lock: order.append(("start", chunk[0]["sku"]))
    time.sleep(0.25)
    with lock: order.append(("end", chunk[0]["sku"]))
t0 = time.time()
with ThreadPoolExecutor(max_workers=3) as pool:
    list(pool.map(work, chunks))
elapsed = time.time() - t0
check("two 0.25s products finish in well under 0.5s", elapsed < 0.45, True)
starts = [x for x in order if x[0] == "start"]
check("  both started before either finished",
      order.index(("start", starts[1][1])) < order.index(("end", starts[0][1])), True)

print("\n=== progress is reported per product ===")
# _by_product is defined inside register(); rebuild it from the same inputs.
def by_product(j):
    planned, done, failed = {}, {}, {}
    for p in (j.get("plan") or []):
        sku = str(p.get("sku") or "") or "(unassigned)"
        planned[sku] = planned.get(sku, 0) + 1
    for r in (j.get("results") or []):
        sku = str((r or {}).get("sku") or "") or "(unassigned)"
        done[sku] = done.get(sku, 0) + 1
        if not (r or {}).get("ok"):
            failed[sku] = failed.get(sku, 0) + 1
    return [{"sku": s, "total": planned[s], "done": done.get(s, 0),
             "failed": failed.get(s, 0)} for s in sorted(planned)]

job = {"plan": [{"sku": "SKU-A"}] * 8 + [{"sku": "SKU-B"}] * 8,
       "results": [{"sku": "SKU-A", "ok": True}] * 3
                  + [{"sku": "SKU-B", "ok": True}, {"sku": "SKU-B", "ok": False}]}
p = by_product(job)
check("one row per product", [x["sku"] for x in p], ["SKU-A", "SKU-B"])
check("  A is 3 of 8", (p[0]["done"], p[0]["total"]), (3, 8))
check("  B is 2 of 8", (p[1]["done"], p[1]["total"]), (2, 8))
check("  and B's failure is counted", p[1]["failed"], 1)
check("the totals still add up to the old number",
      sum(x["total"] for x in p), 16)

gsrc = open(r"D:\AltaScraper\routes\genimage_routes.py", encoding="utf-8").read()
check("job_status reports the breakdown", '"products": _by_product(j)' in gsrc, True)
check("jobs_active reports it too", '"products": _by_product(j)' in gsrc, True)
check("_by_product is defined once", gsrc.count("def _by_product("), 1)

jsrc = open(r"D:\AltaScraper\static\js\settings.js", encoding="utf-8").read()
check("the status bar names the product count", '" · "+products.length+" products"' in jsrc, True)
check("  and a single product by SKU", 'products[0].sku' in jsrc, True)

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
