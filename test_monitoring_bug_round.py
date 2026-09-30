"""Bug round, 30 Sep 2026 -- notifications, the bell, trackers, the ASIN monitor
and the rank tracker. Each check below fails on the code before the fix.

    1. send(): a channel with NO events list gets the usual alerts (and the
       tracker round-up) -- not every ordinary repricer price change.
    2. send()/channels()/log(): a channel belongs to an account. Another
       account's alerts do not reach it; a legacy channel (no account) still
       does, and is shown flagged so the owner can assign it.
    3. guard: the bell (/notify/inbox, /notify/read) is open to any signed-in
       user; the channel settings are still manage_accounts.
    4. trackers: the same ASIN in two marketplaces is two rows, and a row
       written before the marketplace was part of the key is adopted into the
       account's default marketplace.
    5. monitor: a save during a run keeps read marks made meanwhile; a second
       run is refused while one is going; Off is not overridden by the env var;
       NEW means exactly zero feedback.
    6. rank tracker: the week posted as JSON is the week used.

Nothing is sent anywhere: _post is stubbed, and no Amazon call is made.
"""
import os as _os_repo
_REPO = _os_repo.path.dirname(_os_repo.path.abspath(__file__))
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, _REPO)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


TMP = tempfile.mkdtemp(prefix="altamon_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "jack_uk"}, {"id": "nestwell_goods"}]}, open(CFG, "w"))

from domain import notify as N          # noqa: E402

POSTED = []
N._post = lambda url, payload, timeout=12: (POSTED.append((url, payload)) or (True, "stubbed"))

print("=== 1. an empty events list is the usual alerts, not everything ===")
a = N.add_channel(CFG, "slack", "https://hooks.slack.com/services/T/B/jack",
                  label="Jack", account="jack_uk", enabled=True)["channel"]["id"]
POSTED[:] = []
N.send(CFG, "Repriced", ["x"], event=N.PRICE_CHANGE, account="jack_uk")
check("an ordinary price change is not sent to a default channel", len(POSTED), 0)
POSTED[:] = []
N.send(CFG, "Out of stock", ["x"], event=N.OUT_OF_STOCK, account="jack_uk")
check("an out-of-stock is", len(POSTED), 1)
POSTED[:] = []
N.send(CFG, "2 trackers off target", ["x"], event="tracker", account="jack_uk")
check("the tracker round-up is", len(POSTED), 1)
# The route the price-change leak came through: another channel ASKS for
# price_change, so announce() sends -- and the default channel must not get it.
b = N.add_channel(CFG, "slack", "https://hooks.slack.com/services/T/B/all",
                  label="All", account="jack_uk", enabled=True)["channel"]["id"]
N.set_channel(CFG, b, events=["*"])
POSTED[:] = []
N.announce(CFG, "jack_uk", N.PRICE_CHANGE, "Repriced", ["x"])
check("with one channel on '*', a reprice reaches only that one", len(POSTED), 1)
truthy("  and it is the '*' channel", POSTED and POSTED[0][0].endswith("/all"))
N.remove_channel(CFG, b)

print("\n=== 2. a channel belongs to its account ===")
POSTED[:] = []
N.send(CFG, "Out of stock", ["x"], event=N.OUT_OF_STOCK, account="nestwell_goods")
check("nestwell's alert does not reach jack's channel", len(POSTED), 0)
ids = [c["id"] for c in N.channels(CFG, account="nestwell_goods")]
falsy("jack's channel is not listed for nestwell", a in ids)
truthy("  but is for jack", a in [c["id"] for c in N.channels(CFG, account="jack_uk")])
# A legacy channel, stored before channels had an account.
data = N.load(CFG)
data["channels"].append({"id": 99, "kind": "slack", "url": "https://hooks.slack.com/services/T/B/old",
                         "label": "Old", "account": "", "events": [], "enabled": True})
N._save(CFG, data)
POSTED[:] = []
N.send(CFG, "Out of stock", ["x"], event=N.OUT_OF_STOCK, account="nestwell_goods")
check("a legacy channel still receives every account's alerts", len(POSTED), 1)
truthy("  and is listed for any account (flagged on screen)",
       99 in [c["id"] for c in N.channels(CFG, account="nestwell_goods")])
N.set_channel(CFG, 99, account="jack_uk")
check("assigning files it under one account", N.channel_for(CFG, 99)["account"], "jack_uk")
N.set_channel(CFG, 99, account="nestwell_goods")
check("  and cannot then move it to another", N.channel_for(CFG, 99)["account"], "jack_uk")
nest_log = N.log(CFG, 50, account="nestwell_goods")
falsy("nestwell's log holds nothing sent to jack's channel",
      any(str(e.get("channel_id")) == str(a) for e in nest_log))
truthy("log entries carry a UTC time for the screen",
       all("at_utc" in e for e in N.log(CFG, 5, account="jack_uk")))
NR = open(os.path.join(_REPO, "routes", "notify_routes.py"), encoding="utf-8").read()
truthy("GET /notify/channels filters by the request's account",
       "_n.channels(CONFIG_PATH, account=_acct())" in NR)
truthy("GET /notify/log filters by the request's account",
       "_n.log(CONFIG_PATH, limit, account=_acct())" in NR)
NJ = open(os.path.join(_REPO, "static", "js", "notify.js"), encoding="utf-8").read()
truthy("adding a channel names the account (acctBody)", "_ntfBody({ kind: kind" in NJ)
truthy("a failed load is drawn with uiError", "uiError(\"The notification settings" in NJ)

print("\n=== 3. the bell is open to every signed-in user ===")
from auth import guard as G          # noqa: E402
from auth import users as U          # noqa: E402
VIEWER = {"id": "u9", "email": "v@example.test", "role": "viewer", "active": True,
          "workspaces": ["jack_uk"], "permissions": [],
          "features": {f: "none" for f in U.FEATURES}}
check("/notify/inbox needs no permission", G.required_permission("/notify/inbox", "GET"), None)
check("/notify/read needs no permission", G.required_permission("/notify/read", "POST"), None)
check("  and belongs to no feature", G.feature_for("/notify/inbox"), None)
truthy("a user without manage_accounts may read the bell",
       G.check("/notify/inbox", "GET", VIEWER, None, {"account": "jack_uk"})[0])
falsy("  but not for an account they cannot open",
      G.check("/notify/inbox", "GET", VIEWER, None, {"account": "nestwell_goods"})[0])
falsy("  and still may not open the channel settings",
      G.check("/notify/channels", "GET", VIEWER, None, {"account": "jack_uk"})[0])

print("\n=== 4. trackers are kept per account AND marketplace ===")
from domain import trackers as T      # noqa: E402
T.watch_set(CFG, "jack_uk", "B0AAAAAAAA", "price", on=True, target=10, marketplace="UK")
T.watch_set(CFG, "jack_uk", "B0AAAAAAAA", "price", on=True, target=20, marketplace="DE")
check("UK's target is UK's", T.watch_get(CFG, "jack_uk", "B0AAAAAAAA", "price", "UK")["target"], 10.0)
check("DE's target is DE's", T.watch_get(CFG, "jack_uk", "B0AAAAAAAA", "price", "DE")["target"], 20.0)
T.record(CFG, "jack_uk", "B0AAAAAAAA", "price", 9.5, "2026-09-30 10:00", marketplace="UK")
check("a UK reading is not in DE's history",
      len(T.history(CFG, "jack_uk", "B0AAAAAAAA", "price", marketplace="DE")), 0)
# A row written before the key had a marketplace.
d = T.load(CFG)
d["watch"]["jack_uk::B0LEGACY01"] = {"bsr": {"on": True, "target": 500}}
d["history"]["jack_uk::B0LEGACY01"] = {"bsr": [{"at": "2026-09-01 09:00", "v": 700}]}
T._save(CFG, d)
check("adopting moves the legacy watch row and its history", T.adopt_legacy(CFG, "jack_uk", "UK"), 2)
truthy("  into the default marketplace", "B0LEGACY01" in T.tracked(CFG, "jack_uk", marketplace="UK"))
check("  with its history", len(T.history(CFG, "jack_uk", "B0LEGACY01", "bsr", marketplace="UK")), 1)
check("  and a second run moves nothing", T.adopt_legacy(CFG, "jack_uk", "UK"), 0)
TR = open(os.path.join(_REPO, "routes", "tracker_routes.py"), encoding="utf-8").read()
truthy("/trackers/watch refuses a malformed ASIN", '_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")' in TR)
TJ = open(os.path.join(_REPO, "static", "js", "trackers.js"), encoding="utf-8").read()
truthy("the target box's handler goes through jsArg",
       "trkSetTarget(' + jsArg(r.asin)" in TJ)

print("\n=== 5. the ASIN monitor ===")
from monitor import checker as C      # noqa: E402
C._save_hist(CFG, {"baselines": {}, "snapshots": {}, "seller_names": {},
                   "alerts": [{"id": 1, "read": False, "type": "new_seller"}]})
run_copy = C._load_hist(CFG)               # what a run loaded at its start
C.mark_alerts_read(CFG, ids=[1])            # the owner reads it mid-run
run_copy["alerts"].append({"id": 2, "read": False, "type": "buybox_change"})
run_copy["baselines"]["B0X::UK"] = {"offers": []}
C._merge_save(CFG, run_copy, {"B0X::UK"}, 1)
after = {a["id"]: a for a in C._load_hist(CFG)["alerts"]}
truthy("a read mark made during the run survives the run's save", after[1].get("read"))
truthy("  and the run's new alert is saved", 2 in after)
truthy("  and its baseline", "B0X::UK" in C._load_hist(CFG)["baselines"])
C._RUN_LOCK.acquire()
try:
    r = C.check_all({}, CFG, log=lambda m: None)
finally:
    C._RUN_LOCK.release()
check("a second run is refused while one is going", r.get("error"), "a check is already running")
CK = open(os.path.join(_REPO, "monitor", "checker.py"), encoding="utf-8").read()
truthy("MONITOR_INTERVAL_S no longer switches the clock on",
       "if _sched.is_on(cfg) else 0" in CK)
truthy("NEW means exactly zero feedback", "new_acct = (fc is not None and fc == 0)" in CK)
MJ = open(os.path.join(_REPO, "static", "js", "monitor.js"), encoding="utf-8").read()
falsy("no 'see terminal' on the screen", "see terminal" in MJ)
falsy("no 'runs hourly' on the screen", "runs hourly" in MJ)
truthy("the label modal ignores a reply for another seller",
       'String(j.seller_id||"") !== String(id)' in MJ)
SC = open(os.path.join(_REPO, "data", "scheduler.py"), encoding="utf-8").read()
truthy("the APScheduler job stands aside for the monitor's own loop",
       '_checker, "_SCHED_STARTED"' in SC)

print("\n=== 6. the rank tracker's week, posted as JSON ===")
from flask import Flask               # noqa: E402
from routes import keywords_routes as KR   # noqa: E402
app = Flask("t")
KR.register(app, CONFIG_PATH=CFG, _cfg=lambda: {}, _state={},
            _active_account=lambda: {"id": "jack_uk"})
with app.test_client() as cl:
    rv = cl.post("/keywords/rank-tracker/check", json={"start": "not-a-date",
                                                        "end": "2026-09-26"})
    check("a JSON start date is read (and a bad one refused)",
          (rv.get_json() or {}).get("error"), "Bad dates.")
RJ = open(os.path.join(_REPO, "static", "js", "ranktracker.js"), encoding="utf-8").read()
truthy("Remove goes through jsArg", "jsArg(w.keyword)" in RJ)

shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
