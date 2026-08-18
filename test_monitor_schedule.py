"""The ASIN monitor runs when it is asked to, not always.

    "i dont want the asin monitor to be working always, give 2 options. option 1
     is to recheck the status of the buybox by clicking a button. option two is
     to setup a time of your choice. e.g. every 4 hours. 10 hours etc etc. a
     user should be able to choose time on his choice"

WHAT WAS WRONG
The interval was a constant in the code, in two places, and the monitor ran on a
timer whether or not anybody was looking at it. It was measured as the largest
consumer of this app's Amazon quota: every tracked ASIN, in every marketplace it
sells in, competing with the live-catalogue refresh and with whatever somebody
was actually waiting on.

THE THREE THINGS THIS PINS

  1. OFF IS THE DEFAULT and off really means nothing runs on its own.
  2. "a user should be able to choose time on his choice" -- any whole number of
     hours, not a menu of three. A silly number is put in range, never refused,
     because a settings screen that will not save is worse than one that rounds
     and says what it did.
  3. THE INTERVAL REACHES THE PER-ASIN REST PERIOD. This is the one that would
     have shipped broken: checker.py will not re-read a live marketplace more
     often than _MIN_RECHECK_LIVE, so a sweep set to every 4 hours against a
     24-hour rest period would change nothing at all and the setting would be a
     lie the user could not see through.
"""
import re
import sys

sys.path.insert(0, r"D:\AltaScraper")

from monitor import checker as _chk        # noqa: E402
from monitor import schedule as _sch       # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                  % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


print("\n== off is the default ==")
check("nobody has chosen, so nothing runs on a timer",
      _sch.read({})["mode"], _sch.OFF)
check("  and there is no interval to run on", _sch.interval_seconds({}), 0)
check("  is_on says so plainly", _sch.is_on({}), False)
truthy("  and the screen explains it in words",
       "only looks at Amazon when you press Check now" in _sch.describe({}))

print("\n== any number of hours, the user's choice ==")
cfg = {}
for h in (1, 3, 4, 7, 10, 13, 24, 47, 168):
    _sch.store(cfg, "every", h)
    check("every %d hours is accepted as %d" % (h, h), _sch.read(cfg)["hours"], h)
    check("  and is %d seconds" % (h * 3600), _sch.interval_seconds(cfg), h * 3600)

print("\n== a silly number is put in range, not refused ==")
check("zero hours becomes the floor", _sch.normalise("every", 0)["hours"],
      _sch.MIN_HOURS)
check("  negative too", _sch.normalise("every", -5)["hours"], _sch.MIN_HOURS)
check("a year becomes the ceiling", _sch.normalise("every", 9999)["hours"],
      _sch.MAX_HOURS)
check("text becomes the default", _sch.normalise("every", "banana")["hours"],
      _sch.DEFAULT_HOURS)
check("  and a decimal is truncated, not rejected",
      _sch.normalise("every", "6.7")["hours"], 6)
check("an unknown mode falls to off, which is the safe direction",
      _sch.normalise("banana", 4)["mode"], _sch.OFF)
check("  but 'on' is understood as meaning every",
      _sch.normalise("on", 4)["mode"], _sch.EVERY)

print("\n== a stored value that has been corrupted does not crash a screen ==")
for bad in ({"asin_monitor_schedule": "every 4 hours"},
            {"asin_monitor_schedule": []},
            {"asin_monitor_schedule": None},
            {"asin_monitor_schedule": {"mode": None, "hours": None}}):
    check("%.34r reads as off" % (bad,), _sch.read(bad)["mode"], _sch.OFF)

print("\n== the interval reaches the PER-ASIN rest period ==")
# Without this the setting is decoration: the sweep would run every 4 hours and
# each ASIN would still refuse to be re-read inside 24.
_chk.set_interval(4 * 3600)
check("choosing 4 hours makes the rest period 4 hours",
      _chk._MIN_RECHECK_LIVE, 4 * 3600)
check("  and the next-run estimate agrees", _chk._SCHED_INTERVAL, 4 * 3600)
_chk.set_interval(10 * 3600)
check("choosing 10 hours makes it 10 hours", _chk._MIN_RECHECK_LIVE, 10 * 3600)
# The floor is quota protection: this is the app's largest SP-API consumer.
_chk.set_interval(60)
check("a one-minute interval is still held at an hour per ASIN",
      _chk._MIN_RECHECK_LIVE, 3600)
check("  though the sweep interval itself is honoured", _chk._SCHED_INTERVAL, 60)
_chk.set_interval(0)
check("off leaves no sweep interval", _chk._SCHED_INTERVAL, 0)
check("  and does not drop the per-ASIN floor to zero",
      _chk._MIN_RECHECK_LIVE >= 3600, True)

print("\n== the button is unconditional ==")
SRC = open(r"D:\AltaScraper\monitor\checker.py", encoding="utf-8-sig").read()
BODY = re.sub(r'"""[\s\S]*?"""', "", SRC)
BODY = "\n".join(re.sub(r"#.*$", "", ln) for ln in BODY.split("\n"))
# check_now_async must not consult the schedule -- pressing the button means
# "answer me now", whatever the clock is set to.
m = re.search(r"def check_now_async\([\s\S]*?(?=\ndef )", BODY)
truthy("check_now_async exists", m)
check("  and never asks the schedule whether it may run",
      bool(m and "_sched." in m.group(0)), False)

print("\n== the loop re-reads the choice instead of baking it in ==")
loop = re.search(r"def start_scheduler\([\s\S]*", BODY)
truthy("the loop asks the schedule module", "_sched.interval_seconds" in loop.group(0))
truthy("  inside the loop, not once at boot",
       re.search(r"while True:[\s\S]{0,400}_sched\.interval_seconds", loop.group(0)))
truthy("  and does nothing at all when it is off",
       re.search(r"gap <= 0", loop.group(0)))
# A setting that needs a restart is a setting nobody trusts.
truthy("  waking often enough that a change takes effect quickly",
       re.search(r"_TICK_S\s*=\s*(\d+)", BODY)
       and int(re.search(r"_TICK_S\s*=\s*(\d+)", BODY).group(1)) <= 300)

print("\n== both schedulers read the same choice (Rule 12) ==")
DASH = open(r"D:\AltaScraper\dashboard.py", encoding="utf-8-sig").read()
check("dashboard.py no longer hardcodes 24 hours",
      bool(re.search(r"MONITOR_INTERVAL_S[^)]*24 \* 3600", DASH)), False)
ROUTES = open(r"D:\AltaScraper\routes\monitor_routes.py", encoding="utf-8-sig").read()
truthy("there is a route to read and set it", "/monitor/schedule" in ROUTES)
truthy("  and saving tells the checker immediately", "_chk.set_interval(" in ROUTES)
JS = open(r"D:\AltaScraper\static\js\monitor.js", encoding="utf-8-sig").read()
truthy("the screen loads it when the monitor opens", "monSchedLoad()" in JS)
truthy("  offers the common intervals as shortcuts", "suggested_hours" in JS)
truthy("  and still lets any number be typed",
       # The input is assembled by concatenation, so min/max/value sit between
       # the type and the handler -- a tight window here fails on formatting
       # rather than on behaviour.
       re.search(r'type="number"[\s\S]{0,400}monSchedSet', JS))
truthy("  redrawing from what the server stored, not what was clicked",
       re.search(r"MON_SCHED\.hours = j\.hours", JS))

print("\n== config.json is read and written in one place (Rule 12) ==")
for path in ("routes/monitor_routes.py", "routes/sourcing_routes.py"):
    src = open(r"D:\AltaScraper\%s" % path, encoding="utf-8-sig").read()
    body = "\n".join(re.sub(r"#.*$", "", ln) for ln in src.split("\n"))
    check("%s does not open config.json by hand" % path,
          bool(re.search(r'open\(CONFIG_PATH,\s*["\']w', body)), False)
    truthy("  it goes through config/settings", "_settings." in body)
SET = open(r"D:\AltaScraper\config\settings.py", encoding="utf-8-sig").read()
truthy("and that writer is atomic, for the file holding every credential",
       "write_json_atomic" in SET)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
