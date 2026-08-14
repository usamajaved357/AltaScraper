"""Pressing Generate must not sit in silence while the program loads.

THE COMPLAINT: "hitting the generate button takes a lot of time to verify which
item is already created", and later "still the generate button is taking too
long to check which listing is already generated".

WHAT IT ACTUALLY WAS. Measured on the owner's machine, 15 Aug 2026:

    reading the existing listings   50 ms   (55 rows)
    the duplicate check itself     ~500 ms
    getting to the first line       8.2 s   <-- all of it here

Every press launches a FRESH PROCESS, so every import is paid again, every
time: crawl4ai 2.1s (which drags in numpy, aiohttp and two copies of
Playwright), anthropic 2.1s, gspread 1.2s, the rule files ~1.0s. None of it
printed anything, so the last thing on screen stayed the line about checking
existing listings -- and the wait was blamed on the check, which was in fact
the fastest part of the whole run.

THE FIX, in two halves:
  1. say something immediately, so the run is visibly alive
  2. load each heavy library inside the function that needs it -- a generate
     against the database never touches gspread, a run that scrapes no reviews
     never needs a browser engine, and export never calls Claude

Startup went 8.2s -> ~2.5s. This test guards both halves, and checks the move
changed nothing: the browser settings it builds must still be the ones that
make amazon.co.uk show prices to a non-UK visitor.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-58s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


print("=== the heavy libraries are NOT loaded just by starting ===")
# The real measurement: a fresh process, exactly as the run is launched.
code = ("import sys, amazon_listing_generator; "
        "print('HEAVY=' + ','.join(m for m in ('crawl4ai','anthropic',"
        "'gspread','openpyxl','unified_export') if m in sys.modules))")
t0 = time.time()
p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
startup_ms = int((time.time() - t0) * 1000)
lines = (p.stdout or "").replace("\r", "").splitlines()
truthy("the process ran", p.returncode == 0 or lines)

# Half one: the run announces itself before doing anything slow.
check("it says something before the slow part",
      (lines or [""])[0].strip(), "Starting up...")

# Half two: nothing expensive came along for the ride.
heavy = [l for l in lines if l.startswith("HEAVY=")]
truthy("the probe reported", heavy)
loaded = (heavy or ["HEAVY=?"])[0][len("HEAVY="):]
check("none of the heavy libraries load at startup", loaded, "")

# A ceiling, not a benchmark: generous enough not to fail on a slow or busy
# machine, tight enough to catch someone moving an import back to the top.
# It was 8.2s before; anything near that is the regression this guards.
print("  (measured startup: %d ms)" % startup_ms)
truthy("startup is well under the 8.2s it was (ceiling 6s)", startup_ms < 6000)

print("\n=== the deferred imports still produce the same things ===")
import amazon_listing_generator as G

cfg = G._browser_cfg()
check("browser stays headless", cfg.headless, True)
hdr = cfg.headers or {}
check("UK language header kept", hdr.get("Accept-Language"), "en-GB,en;q=0.9")
truthy("browser user-agent kept", "Chrome/120.0.0.0" in (hdr.get("User-Agent") or ""))
ck = {c["name"]: c["value"] for c in (cfg.cookies or [])}
# These three are the reason UK pages show prices at all from outside the UK.
# Losing them in a refactor would look like Amazon "returning thin data".
check("lc-main cookie", ck.get("lc-main"), "en_GB")
check("i18n-prefs cookie", ck.get("i18n-prefs"), "GBP")
check("sp-cdn UK location cookie", ck.get("sp-cdn"), "L5Z9:GB")
check("cookies still scoped to amazon.co.uk",
      sorted({c["domain"] for c in (cfg.cookies or [])}), [".amazon.co.uk"])
check("built once and reused", G._browser_cfg() is cfg, True)

c = G._claude({"anthropic_api_key": "sk-ant-test-not-a-real-key"})
check("the Claude client is built from config", c.api_key,
      "sk-ant-test-not-a-real-key")

print("\n=== the duplicate check is not the slow part ===")
# Stated plainly because the complaint named the wrong thing twice. If this
# ever stops being true, the message on screen becomes misleading again.
import json
try:
    conf = json.load(open("config.json", encoding="utf-8"))
    conf["_config_path"] = "config.json"
    accts = [a.get("id") for a in (conf.get("accounts") or []) if a.get("id")]
except Exception:
    accts = []
if accts:
    from data.store import ListingStore, SheetLikeStore
    conf["_account_id"] = accts[0]
    ws = SheetLikeStore(ListingStore(accts[0], config_path="config.json"))
    t0 = time.time()
    skus, asins = G.load_existing_skus_and_asins(ws, conf)
    dup_ms = int((time.time() - t0) * 1000)
    print("  (%s: %d SKUs known, checked in %d ms)" % (accts[0], len(skus), dup_ms))
    truthy("checking what already exists takes under 2s", dup_ms < 2000)
else:
    print("  (no accounts configured here -- skipped)")

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
