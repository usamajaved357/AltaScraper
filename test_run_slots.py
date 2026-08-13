"""Preview/Submit is per account and per SKU, not one queue for everybody.

Was: a single process-wide flag. One Preview or Submit at a time for the entire
app -- a second person was told "a run is already in progress" however unrelated
their listing was.

Must still hold: the SAME SKU never runs twice at once (two runs would write the
same sheet row and submit the same listing twice), and one Amazon account is
capped because SP-API quota is per selling account.
"""
import os, sys, time, threading
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))

os.environ["ALTA_RUNS_PER_ACCOUNT"] = "2"
os.environ["ALTA_RUNS_TOTAL"] = "6"
import importlib
import domain.run_slots as rs
importlib.reload(rs)

def fresh():
    return rs.RunSlots()

print("=== two people, two accounts: nobody waits ===")
s = fresh()
ok1, k1 = s.acquire("selvora", "SKU-A", owner="u_owner")
ok2, k2 = s.acquire("green_haven", "SKU-B", owner="u_va")
check("the owner starts", ok1, True)
check("the VA starts too", ok2, True)
check("  and both are running", len(s.active()), 2)

print("\n=== same account, different listings: allowed, up to the cap ===")
s = fresh()
check("first", s.acquire("selvora", "SKU-A")[0], True)
check("second", s.acquire("selvora", "SKU-B")[0], True)
ok, why = s.acquire("selvora", "SKU-C")
check("third is held back", ok, False)
check("  and the reason names the real limit", "throttled by Amazon" in why, True)
check("  while ANOTHER account still starts immediately",
      s.acquire("jack_uk", "SKU-C")[0], True)

print("\n=== the same SKU never runs twice (correctness, not throughput) ===")
s = fresh()
check("first run of SKU-A", s.acquire("selvora", "SKU-A", owner="u1")[0], True)
ok, why = s.acquire("selvora", "SKU-A", owner="u1")
check("the same person cannot start it again", ok, False)
check("  and is told why", "already being processed" in why, True)
ok, why = s.acquire("selvora", "SKU-A", owner="u2")
check("nor can anyone else", ok, False)
check("  who is told someone else has it", "by someone else" in why, True)

print("\n=== a whole-sheet run (no SKU) still excludes another of its own ===")
s = fresh()
check("first generate", s.acquire("selvora", "")[0], True)
check("second generate on the same account waits", s.acquire("selvora", "")[0], False)
check("  but a single-SKU run alongside it is fine",
      s.acquire("selvora", "SKU-A")[0], True)

print("\n=== the whole app is capped too ===")
os.environ["ALTA_RUNS_TOTAL"] = "3"
os.environ["ALTA_RUNS_PER_ACCOUNT"] = "8"
s = fresh()
for i in range(3):
    s.acquire("acct%d" % i, "S")
ok, why = s.acquire("acct9", "S")
check("the fourth waits", ok, False)
check("  and says so", "already running 3 listings" in why, True)
os.environ["ALTA_RUNS_TOTAL"] = "6"
os.environ["ALTA_RUNS_PER_ACCOUNT"] = "2"

print("\n=== releasing ===")
s = fresh()
ok, k = s.acquire("selvora", "SKU-A")
s.release(k)
check("the slot is free again", s.acquire("selvora", "SKU-A")[0], True)

print("\n=== a thread releases its own slot, whichever it was ===")
# Fifteen call sites end a run by setting a flag, not by naming a key. The
# thread knows which run it is; those call sites do not.
s = fresh()
results = {}
def run(name, sku):
    ok, _k = s.acquire("selvora", sku, owner=name)
    results[name] = ok
    time.sleep(0.05)
    results[name + "_released"] = s.release_current()
t1 = threading.Thread(target=run, args=("a", "SKU-A"))
t2 = threading.Thread(target=run, args=("b", "SKU-B"))
t1.start(); t2.start(); t1.join(); t2.join()
check("both threads ran", (results["a"], results["b"]), (True, True))
check("each released its own", (results["a_released"], results["b_released"]), (True, True))
check("  leaving nothing behind", s.active(), [])
check("a thread holding nothing releases nothing", s.release_current(), False)

print("\n=== a dead subprocess frees its slot without waiting ===")
class Dead:
    def poll(self): return 1
    def terminate(self): pass
class Alive:
    def poll(self): return None
    def terminate(self): pass
s = fresh()
ok, k = s.acquire("selvora", "SKU-A")
s.attach(k, Dead())
check("the slot is reclaimed", s.acquire("selvora", "SKU-A")[0], True)
s2 = fresh()
ok, k2 = s2.acquire("selvora", "SKU-A")
s2.attach(k2, Alive())
check("a LIVE run is not reclaimed", s2.acquire("selvora", "SKU-A")[0], False)

print("\n=== Stop ends yours, not theirs ===")
s = fresh()
ok, ka = s.acquire("selvora", "SKU-A", owner="u_owner"); s.attach(ka, Alive())
ok, kb = s.acquire("green_haven", "SKU-B", owner="u_va"); s.attach(kb, Alive())
check("the VA stops one run", s.stop(owner="u_va"), 1)
check("  and the owner's survives",
      [x["owner"] for x in s.active()], ["u_owner"])
check("the owner then stops their own", s.stop(owner="u_owner"), 1)
check("  nothing left", s.active(), [])

print("\n=== with no user (shared password), Stop means everything ===")
s = fresh()
s.acquire("a", "1", owner=""); s.acquire("b", "2", owner="")
check("both stopped", s.stop(), 2)

print("\n=== the queue has enough workers to fill the slots ===")
src = open(r"D:\AltaScraper\listing\preview_jobs.py", encoding="utf-8").read()
check("worker count follows the slot limit", "total_limit()" in src, True)
check("  and there is no single-worker flag left", '_WORKER = {"on": False}' in src, False)
check("the job carries its account", '"account_id": str(account_id or "")' in src, True)
check("  and its owner", '"owner": str(owner or "")' in src, True)
check("acquire is called with them",
      'acquire(job.get("account_id", ""),' in src, True)

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
