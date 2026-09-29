# -*- coding: utf-8 -*-
"""A TEST COPY STARTS SAFELY: with ALTASCRAPER_BACKGROUND=off, booting the whole
app reaches nothing outside this machine and starts no background work.

Master continuation, Priority 7 (29 Sep 2026): "Before parallel server testing,
prove the test deployment can start safely ... startup does not unexpectedly
push Amazon prices, submit listings, dispatch orders, upload tracking, purchase
from suppliers, perform another costly external write, consume unexpected
metered services, post unexpected notifications."

How it is proven, without any real write: every outbound network connection is
intercepted at the socket layer (anything not to this machine is recorded and
refused), the real dashboard.build_app() runs on a throwaway config holding one
account, and the process is watched for a few seconds after boot. Pass means:
  * no connection attempt to any other host (Amazon, Google, Slack, eBay,
    17TRACK, Anthropic, suppliers -- every one is a network call);
  * none of the background starters left a thread running, and the job
    scheduler holds no timers;
  * /healthz answers.

THE TEST CAN FAIL (negative control, measured 29 Sep 2026): the same boot with
the switch removed started APScheduler, alta-backup, asin-monitor and two
live-refresher threads, and reached api.amazon.com within three seconds -- 7
checks failed. With the switch: nothing started, nothing left this machine.
"""
import json
import os
import socket
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
    print("  %-72s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


# ---- a throwaway data folder, and the switch a test copy is started with ----
TMP = tempfile.mkdtemp(prefix="altaboot_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "boot_a", "label": "Boot A", "marketplaces": ["UK"],
                         "default_marketplace": "UK", "seller_id": "A1TEST",
                         "refresh_token": "Atzr|not-a-real-token", "lwa_client_id": "x",
                         "lwa_client_secret": "y"}],
           "repricer_enabled": True, "asin_monitor_enabled": True}, open(CFG, "w"))
os.environ["CONFIG_PATH"] = CFG
os.environ["ALTASCRAPER_BACKGROUND"] = "off"
for k in ("ALTASCRAPER_DB", "PORT", "APP_PASSWORD", "MONITOR_INTERVAL_S"):
    os.environ.pop(k, None)

# ---- every outbound connection is recorded and refused ----------------------
OUTBOUND = []
_LOCAL = ("127.0.0.1", "localhost", "::1", "0.0.0.0", "")


def _host(addr):
    try:
        return str(addr[0])
    except Exception:
        return str(addr)


_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
_orig_create = socket.create_connection


def _guard_connect(self, addr):
    if _host(addr) not in _LOCAL:
        OUTBOUND.append(_host(addr))
        raise OSError("blocked by test_startup_side_effects: %s" % _host(addr))
    return _orig_connect(self, addr)


def _guard_connect_ex(self, addr):
    if _host(addr) not in _LOCAL:
        OUTBOUND.append(_host(addr))
        return 111
    return _orig_connect_ex(self, addr)


def _guard_create(addr, *a, **k):
    if _host(addr) not in _LOCAL:
        OUTBOUND.append(_host(addr))
        raise OSError("blocked by test_startup_side_effects: %s" % _host(addr))
    return _orig_create(addr, *a, **k)


socket.socket.connect = _guard_connect
socket.socket.connect_ex = _guard_connect_ex
socket.create_connection = _guard_create
_orig_gai = socket.getaddrinfo


def _guard_gai(host, *a, **k):
    if str(host) not in _LOCAL:
        OUTBOUND.append(str(host))
        raise socket.gaierror("blocked by test_startup_side_effects: %s" % host)
    return _orig_gai(host, *a, **k)


socket.getaddrinfo = _guard_gai

threads_before = {t.name for t in threading.enumerate()}

print("== boot the whole app as a test copy ==")
import dashboard as D                                   # noqa: E402
app = D.build_app()
app.config["TESTING"] = True
time.sleep(3.0)          # the starters' own threads would be up by now

new_threads = sorted({t.name for t in threading.enumerate()} - threads_before)
print("  threads started by boot: %s" % (new_threads or "none"))
check("nothing tried to reach another machine during boot", OUTBOUND, [])
BACKGROUND = ("alta-backup", "live-refresher", "supplier-repair", "APScheduler",
              "asin-monitor", "monitor")
check("no background worker thread was started",
      [t for t in new_threads if any(b.lower() in t.lower() for b in BACKGROUND)], [])
from data import scheduler as S                        # noqa: E402
check("the job scheduler holds no timers (no price pushes, no Slack, no 17TRACK)",
      bool(S._scheduler and S._scheduler.running), False)
from domain import live_refresher as LR                # noqa: E402
check("the live refresher is not running", bool(LR._STATE.get("running")), False)
from domain import backup as BK                        # noqa: E402
check("the nightly Google backup is not armed", BK.NIGHTLY.running, False)
from monitor import checker as MC                      # noqa: E402
check("the ASIN monitor loop is not running", MC._SCHED_STARTED, False)

print("== and it answers ==")
r = app.test_client().get("/healthz")
check("/healthz answers", (r.status_code, r.get_data(as_text=True).strip()), (200, "ok"))
check("  still without reaching another machine", OUTBOUND, [])

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
sys.stderr.flush()
os._exit(1 if fails else 0)       # do not wait on any thread the app left behind
