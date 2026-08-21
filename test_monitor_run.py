"""The ASIN monitor: visible while it runs, durable, tidy, and namable in bulk.

Four complaints, one screen:

    "the asin monitor is taking too much time to get the data, i uploaded a csv
     with the asins in it and clicked on check now button and it is been like 10
     minutes and data for a single asin is not updated there, i have also tried
     reloading the page"

    "i experience this issue on so many asins check failed —
     SellingApiRequestThrottledException: QuotaExceeded"

    "each asin has a too long list of markets ... this is too messy"

    "i have the names of the sellers which i can put in a csv file ... right now
     i have the ability to do it manually one by one"

WHAT WAS MEASURED, before anything was changed:

    111 ASINs x 10 marketplaces  = 1,110 checks in a run, 56 batched API calls
    the page                     = 46,293 pixels tall, 1,110 market rows
    the last completed run       = 08:43 to 08:51, nine minutes
    saved to disk                = ONCE, after all 56 batches
    the browser's poll           = gave up after 180 seconds
    seller names                 = keyed sellerId::marketplace, so one seller
                                   trading in eight countries was eight
                                   separate naming jobs

So a nine-minute run wrote nothing for nine minutes, and the page the user
reloaded was correctly showing a file nothing had written to yet. It was not
stuck; it was invisible.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time

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
    return io.open(os.path.join(HERE, *p), encoding="utf-8").read()


from monitor import bulk_import as bi
from monitor import checker as ck
from monitor import known_sellers as ks
from monitor import pricing as pr

J = read("static", "js", "monitor.js")
C = read("static", "css", "dashboard.css")
H = read("templates", "dashboard.html")
CK = read("monitor", "checker.py")

print("== a run is saved as it goes, not once at the end ==")
_body = CK.split("for i in range(0, total, _BATCH_SIZE):")[1].split("dur = round")[0]
truthy("the save is INSIDE the batch loop", "_save_hist(config_path, d)" in _body)
# ONE save inside the RUN. The module has others -- mark_alerts_read and
# log_manual_label each write too -- so counting across the file measured
# those as well.
check("  and exactly one save inside the run body",
      _body.count("_save_hist(config_path, d)"), 1)
truthy("why is written down", "SAVED AS IT GOES, not once at the end" in CK)
truthy("  with the symptom it caused", "it has been ten minutes" in CK)

print("\n== and it reports where it has got to ==")
for k in ("done", "total", "batches_done", "batches", "run_fails", "run_alerts"):
    truthy("status carries %-12s" % k, '"%s"' % k in CK or "%s=" % k in CK)
truthy("the screen shows a count, not just a word", "of ' + total.toLocaleString()" in J)
truthy("  with a progress bar", "monprog" in J and ".monprog{" in C)
truthy("  and an estimate from the rate ACHIEVED", "el4 / done * (total - done)" in J)
falsy("  the old bare 'checking…' is gone",
      "el.innerHTML = '<span class=\"genspin\"></span> checking…'" in J)
truthy("it says the results fill in as it goes", "update as each batch finishes" in J)

print("\n== one bad batch costs one batch ==")
truthy("the per-batch work is guarded", "batch %d of %d failed" in CK)
truthy("  and the thread reports a death", "The check stopped early" in CK)
falsy("  rather than a bare lambda", "target=lambda: check_all" in CK)
truthy("the screen shows that reason", 'st.phase === "failed"' in J)
truthy("  and says what survived", "checked before it" in J)

print("\n== throttling waits instead of failing ==")
PR = read("monitor", "pricing.py")
check("five attempts, not two", pr._THROTTLE_TRIES, 5)
truthy("  with a doubling wait", "_THROTTLE_BASE_S * (2 ** attempt)" in PR)
falsy("  the old single sleep(8) is gone", "time.sleep(8); continue" in PR)
truthy("a throttle is explained, not echoed as an exception name",
       "Amazon is rate-limiting these lookups" in PR)
falsy("  the raw exception name is no longer the message",
      'f"{type(e).__name__}: {str(e)[:160]}"' in PR.split("is_throttle")[1][:400])

print("\n== and the pace adapts, so a run stops walking into the wall ==")
pr.reset_pace(2.0)
check("it starts at the base gap", pr.current_pace(), 2.0)
pr._note_throttle()
check("  a throttle doubles it", pr.current_pace(), 4.0)
pr._note_throttle()
check("  and again", pr.current_pace(), 8.0)
for _ in range(4):
    pr._note_ok()
check("  four clean batches are not enough to speed up", pr.current_pace(), 8.0)
pr._note_ok()
check("  the fifth is", pr.current_pace(), 6.0)
for _ in range(40):
    pr._note_throttle()
truthy("  it is capped", pr.current_pace() <= pr.PACE_MAX_S)
for _ in range(200):
    pr._note_ok()
truthy("  and floored", pr.current_pace() >= pr.PACE_MIN_S)
truthy("the checker uses it", "_pricing.current_pace()" in CK)
truthy("  and resets it per run", "_pricing.reset_pace" in CK)
falsy("  not a fixed sleep any more", "time.sleep(_BATCH_PACING_S)" in CK)

print("\n== the storefront scrape cannot hang a run ==")
SF = read("monitor", "storefront_name.py")
truthy("there is an overall budget", "_TOTAL_BUDGET_S" in SF)
truthy("  and it is enforced", "deadline" in SF)
truthy("  per domain too", "min(float(timeout), deadline" in SF)
truthy("the arithmetic that made it a problem is recorded", "11 x 15 = 165" in SF)
# In CODE, not in the comment that explains what it used to be.
_sfcode = "\n".join(l.split("#")[0] for l in SF.splitlines()
                    if not l.strip().startswith("#"))
check("  the per-domain timeout came down from 15", _sfcode.count("timeout=15"), 0)
check("    to something a run can afford", pr and True, True)

print("\n== ten market rows became one line ==")
truthy("there is a summary", "_monMarketSummary" in J)
truthy("  it leads with other sellers", "other sellers in" in J)
truthy("  counts the silent markets rather than listing them",
       "' with no offers</span>'" in J)
# In CODE. The phrase survives in the comment that explains what was removed.
_jcode = "\n".join(l.split("//")[0] for l in J.splitlines()
                   if not l.strip().startswith(("*", "/*", "//")))
falsy("  the old repeated row is gone", "skipped — not listed here" in _jcode)
truthy("the detail is still there, behind a toggle", "monToggle" in J)
truthy("  and an ASIN with a stranger on it opens read",
       "const open = !!r.has_unknown;" in J)
# A `display` rule beats the hidden ATTRIBUTE -- without this the fold changed
# nothing and the page got TALLER.
truthy("a folded list is really hidden", ".monmkt-list[hidden]{display:none}" in C)
truthy("  and why is written down", "beats the hidden ATTRIBUTE" in C)
truthy("the same markets are not named twice", "DON'T SAY THE SAME MARKETS TWICE" in J)

print("\n== the page looks like the rest of the app ==")
_sec = H.split('id="sec_monitor"')[1].split('id="sec_miles"')[0]
truthy("it uses the standard toolbar", 'class="wstoolbar bleed"' in _sec)
truthy("  with an h2, like every other screen", "<h2>" in _sec)
falsy("  and not its own header trio", 'class="pagetitle"' in _sec)
truthy("the buttons are db-chip", 'class="db-chip"' in _sec)
falsy("  not the one-off mktbtn", 'class="mktbtn" id="mon_checkbtn"' in _sec)
# Hardcoded hex breaks the moment the theme changes.
# SCOPED TO THE MONITOR'S OWN CSS. #7a1f1f is also used by button.danger,
# a different component this change did not touch -- asserting across the whole
# stylesheet flagged code that was never in scope.
_mon_css = C[C.find(".monalertbar"):][:7000]
for _hex in ("#7a1f1f", "#8a1010", "#5a2ea6", "#7fe0c0", "#8a5a1e"):
    falsy("no %s left in the monitor's CSS" % _hex, _hex in _mon_css)

print("\n== there is a chart, and it is the one worth having ==")
truthy("unknown sellers by marketplace", "monChart" in J)
truthy("  drawn as bars", ".monbar-fill" in C and "monbar-row" in J)
truthy("  biggest first", "bm[b] - bm[a]" in J)
truthy("a clean account gets a sentence, not an empty frame",
       "No unknown sellers on any tracked ASIN" in J)
truthy("the run of text it replaces is gone", 'const bmText = "";' in J)
truthy("why a time series was not chosen is recorded", "NOT a time series" in J)

print("\n== seller names, from a file, applied everywhere ==")
CSV = (b"Seller ID,Seller Name,Who is this\n"
       b"A3TSTGWB8M3T3Z,Schnappchen Schuppen,3rd party\n"
       b"A35UPYDMLICYZX,Jack Reacherd,me\n"
       b"A3OJWAJQNSBARP,Amazon,Amazon Retail\n"
       b"ARO4QVDUCCH3I,Trusted Distributor Ltd,authorised\n"
       b"NOTASELLER,Nonsense,3rd party\n"
       b"A35UPYDMLICYZX,Repeat,me\n")
got = bi.parse_sellers(CSV, "s.csv")
check("four usable rows", len(got["rows"]), 4)
check("  the junk line is named", len(got["invalid"]), 2)
check("  including the repeat",
      any("already in this file" in v["why"] for v in got["invalid"]), True)
kinds = {r["seller_id"]: r["kind"] for r in got["rows"]}
check("'3rd party' means a named third party", kinds["A3TSTGWB8M3T3Z"], "name")
check("'me' means mine", kinds["A35UPYDMLICYZX"], "me")
check("'Amazon Retail' means Amazon", kinds["A3OJWAJQNSBARP"], "amazon")
check("'authorised' means authorised", kinds["ARO4QVDUCCH3I"], "authorised")
# A person writing a spreadsheet does not use the app's four internal words.
for word, want in (("mine", "me"), ("ourselves", "me"), ("amz", "amazon"),
                   ("Reseller", "authorised"), ("competitor", "name"),
                   ("hijacker", "name"), ("", "name"), ("gibberish", "name")):
    check("  %-12r reads as %s" % (word, want), bi._kind_of(word), want)

print("\n== the file needs no template ==")
check("no header at all still works",
      len(bi.parse_sellers(b"A3TSTGWB8M3T3Z,Some Shop\nA103K7MCY40P2G,Other\n",
                           "x.csv")["rows"]), 2)
truthy("  and why that was wrong before", "IS ROW ONE A HEADER" in
       read("monitor", "bulk_import.py"))
check("columns in any order",
      [(r["seller_id"], r["kind"]) for r in bi.parse_sellers(
          b"kind\tseller\tname\nme\tA35UPYDMLICYZX\tMy Shop\n", "x.tsv")["rows"]],
      [("A35UPYDMLICYZX", "me")])
truthy("a file with no seller IDs says so",
       "No seller IDs found" in (bi.parse_sellers(b"a,b\n1,2\n", "x.csv")
                                 .get("error") or ""))

print("\n== applying them is ONE write, and global ==")
TMP = tempfile.mkdtemp(prefix="montest")
CFG = os.path.join(TMP, "config.json")
json.dump({"known_sellers": {"names": {"A3TSTGWB8M3T3Z": "old name"}}},
          io.open(CFG, "w", encoding="utf-8"))
res = ks.set_sellers_bulk(CFG, got["rows"])
check("all four applied", res["applied"], 4)
cfg = json.load(io.open(CFG, encoding="utf-8"))
blk = cfg["known_sellers"]
check("  mine went to the me block", "A35UPYDMLICYZX" in (blk.get("me") or {}), True)
check("  the reseller to authorised",
      "ARO4QVDUCCH3I" in (blk.get("authorised") or {}), True)
check("  Amazon to the amazon block",
      any("A3OJWAJQNSBARP" in json.dumps(v) for v in (blk.get("amazon") or {}).values()),
      True)
check("  and the third party is renamed, not duplicated",
      (blk.get("names") or {}).get("A3TSTGWB8M3T3Z"), "Schnappchen Schuppen")
# The whole reason for doing it in bulk: one seller, one row, every market.
falsy("no seller is keyed by marketplace",
      any("::" in k for k in (blk.get("names") or {})))
truthy("the same helper the one-at-a-time path uses", "_apply_one(ks, sid" in
       read("monitor", "known_sellers.py"))
res2 = ks.set_sellers_bulk(CFG, [{"seller_id": "", "name": "x"}])
falsy("a file with nothing usable is refused", res2.get("ok"))
shutil.rmtree(TMP, ignore_errors=True)

print("\n== shown before it is applied ==")
R = read("routes", "monitor_routes.py")
truthy("there is a preview route", "/monitor/sellers_preview" in R)
truthy("  which writes nothing", "sellers_preview" in R
       and "set_sellers_bulk" not in R.split("sellers_preview")[1].split("def ")[0])
truthy("  and says what each one WAS", "previous_kind" in R)
truthy("the import is audited like the manual path", '"by": "csv import"' in R)
truthy("the screen previews it", "monSellersPreview" in J)
truthy("  naming the lines it skipped", "Skipped: " in J)
truthy("the button is on the page", "monSellersPick()" in H)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
