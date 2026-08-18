"""monitor/schedule.py -- when the ASIN monitor runs, decided in ONE place.

    "i dont want the asin monitor to be working always, give 2 options. option 1
     is to recheck the status of the buybox by clicking a button. option two is
     to setup a time of your choice. e.g. every 4 hours. 10 hours etc etc. a
     user should be able to choose time on his choice"

TWO WAYS TO RUN IT, AND THAT IS THE WHOLE MODEL

    ON DEMAND   the Check now button. Always available, whatever this setting
                says, and it ignores every rest period -- pressing it means
                "answer me now", so it answers now.

    ON A CLOCK  every N hours, N chosen here. Off by default.

OFF IS THE DEFAULT, ON PURPOSE
The monitor was the single largest consumer of this app's Amazon quota: every
tracked ASIN, in every marketplace it sells in, on a timer, competing with the
live catalogue refresh and with whatever someone was actually waiting on. It ran
whether or not anybody was looking at it. So it now runs when it is asked to,
and turning the clock on is a decision somebody makes rather than one they
inherit.

WHY N IS NOT A DROP-DOWN OF THREE OPTIONS
"a user should be able to choose time on his choice" -- so any whole number of
hours from 1 to 168 is accepted. The UI offers common ones as shortcuts; it does
not limit what can be typed.

WHY THIS IS A MODULE AND NOT A CONSTANT
Two separate things schedule this monitor: its own daemon loop in
monitor/checker.py, and an APScheduler job in data/scheduler.py. Both must obey
the same choice, and a number written in two files is a number that will
disagree with itself (CLAUDE.md Rule 12). Both read it from here.

The interval also has to reach the PER-ASIN rest period. checker.py will not
re-check a live marketplace more often than that period, so a sweep set to every
4 hours against a 24-hour rest period would change nothing at all and the
setting would be a lie. interval_seconds() is what both are derived from.
"""

# The config.json key. One key holding one object, so mode and hours cannot be
# saved half-applied.
KEY = "asin_monitor_schedule"

OFF = "off"
EVERY = "every"

# Chosen when nobody has chosen: no clock, button only. See the header.
DEFAULT_MODE = OFF
DEFAULT_HOURS = 4

# The floor is quota protection, not taste. Below an hour this stops being a
# monitor and becomes a way to exhaust the SP-API budget for every other screen.
MIN_HOURS = 1
MAX_HOURS = 168          # a week

# Offered in the UI as one-tap choices. NOT a restriction -- any whole number
# between MIN_HOURS and MAX_HOURS is accepted, because that is what was asked
# for. Kept here so the screen and the server suggest the same things.
SUGGESTED_HOURS = (1, 2, 4, 6, 8, 10, 12, 24, 48)


def normalise(mode, hours=None):
    """Whatever came in -> a stored value that is always valid.

    Never raises and never rejects: a schedule screen that refuses to save is
    worse than one that rounds a silly number into range and says so.
    """
    mode = str(mode or "").strip().lower()
    if mode not in (OFF, EVERY):
        # "0", "", "none", False all read as off, which is what someone typing
        # any of them means.
        mode = EVERY if mode in ("on", "true", "1", "yes") else OFF
    try:
        hours = int(float(hours))
    except (TypeError, ValueError):
        hours = DEFAULT_HOURS
    hours = max(MIN_HOURS, min(MAX_HOURS, hours))
    return {"mode": mode, "hours": hours}


def read(cfg):
    """The stored choice. `cfg` may be a dict or a callable returning one."""
    cfg = cfg() if callable(cfg) else (cfg or {})
    raw = cfg.get(KEY)
    if not isinstance(raw, dict):
        return normalise(DEFAULT_MODE, DEFAULT_HOURS)
    return normalise(raw.get("mode"), raw.get("hours"))


def store(cfg_dict, mode, hours=None):
    """Write the choice into a config dict. Returns what was stored.

    Takes the raw dict rather than a path: writing config.json is the caller's
    job and there is exactly one writer for it.
    """
    plan = normalise(mode, hours)
    cfg_dict[KEY] = dict(plan)
    return plan


def is_on(cfg):
    """Does the clock run at all? The button works either way."""
    return read(cfg)["mode"] == EVERY


def interval_seconds(cfg):
    """Seconds between automatic sweeps, or 0 when there are none.

    0 is the honest answer for "off" and every caller treats it as such: no
    timer, no next-run estimate, no overload warning about a cycle that does
    not exist.
    """
    plan = read(cfg)
    return plan["hours"] * 3600 if plan["mode"] == EVERY else 0


def describe(cfg):
    """One sentence for the screen. Says what happens, not what is configured."""
    plan = read(cfg)
    if plan["mode"] != EVERY:
        return ("Automatic checking is off. The monitor only looks at Amazon "
                "when you press Check now.")
    h = plan["hours"]
    if h == 1:
        every = "every hour"
    elif h == 24:
        every = "once a day"
    elif h % 24 == 0:
        every = "every %d days" % (h // 24)
    else:
        every = "every %d hours" % h
    return ("Every tracked ASIN is checked %s. Check now still works whenever "
            "you want an answer sooner." % every)
