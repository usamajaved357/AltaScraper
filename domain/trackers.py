"""domain/trackers.py -- watch a number on a listing and say when it moves.

    Orbit has four of these in its menu: BSR Tracker, BuyBox Tracker, Price
    Tracker, Fee Tracker, plus "All Trackers" over the top and one Alerts count
    fed by all of them.

FOUR TRACKERS, ONE ENGINE.

Looked at closely, the four are the same thing pointed at different numbers.
Each is a per-ASIN watch list holding: the value now, the value you want, how
far it has drifted, when it was last read, and whether you are watching it at
all. Four modules would be four copies of that logic drifting apart, and the
first thing to drift would be the alert rule -- so there is one engine here and
the metrics are DATA (see METRICS below), not code. CLAUDE.md Rule 12.

Adding a fifth tracker means adding a row to METRICS and a fetcher. It does not
mean touching the store, the drift maths, the alert rule, the route or the
screen.

WHAT IS STORED, AND WHAT IS NOT.

Deliberately NOT stored: the list of products. That already exists in the
account's catalogue, and a second copy would go stale the moment a listing was
added -- the classic symptom being a new product that can never be tracked
because it is not in the tracker's own list. This module stores only what the
catalogue cannot know:

    watch[asin][metric] = {"on": bool, "target": float|None}
    history[asin][metric] = [{"at": iso, "v": float}, ...]   newest last

DRIFT IS AGAINST WHAT YOU ASKED FOR, NOT AGAINST YESTERDAY.

The number that matters is distance from target, because that is the thing you
can act on. Movement since the last reading is also reported (`change`) but it
is not what raises an alert: a rank that has been 40% worse than target for a
month is a problem every day of that month, and an alert that fires only on the
day it moves would have gone quiet after the first one.

A MISSING READING IS NOT A ZERO.

If Amazon does not answer for an ASIN, its value is None and its status is
UNKNOWN. It is never 0, never "improved to nothing", and it never counts towards
the alert total. Reporting a failed fetch as a perfect score is the single
easiest way to make a monitoring screen lie, and this app has already been bitten
by exactly that shape of bug in the stock and buy-box readers.
"""
import datetime
import threading

from domain import jsonstore

_LOCK = threading.Lock()
_FILE = "trackers.json"

# How many readings to keep per ASIN per metric. Enough to draw a trend and to
# survive a week of hourly checks; small enough that the file stays a file.
MAX_HISTORY = 400

# WHICH WAY IS GOOD.
#
# The single most important field here. A sales rank of 900 is BETTER than
# 4,000; a price of 9.99 is worse than 12.99 if you are trying to hold a price.
# Getting this backwards makes every alert exactly wrong, and it is invisible
# from the numbers alone -- which is why it is written down per metric rather
# than inferred anywhere.
LOWER_IS_BETTER = "lower"
HIGHER_IS_BETTER = "higher"

# `kind` drives formatting only: "money" gets the marketplace's currency symbol,
# "rank" gets thousands separators and a #, "percent" gets a %.
METRICS = {
    "bsr": {
        "label": "Sales rank",
        "tracker": "BSR Tracker",
        "kind": "rank",
        "good": LOWER_IS_BETTER,
        # 20% off target is a real move in rank terms; rank is noisy day to day.
        "tolerance": 0.20,
        "blurb": "Where this product sits in its category. Lower is better.",
        "source": "Amazon's catalogue (sales ranks)",
    },
    "buybox": {
        "label": "Buy Box price",
        "tracker": "BuyBox Tracker",
        "kind": "money",
        "good": LOWER_IS_BETTER,
        "tolerance": 0.05,
        "blurb": "What the Buy Box is currently priced at, whoever holds it.",
        "source": "Amazon's live offers",
    },
    "price": {
        "label": "Your price",
        "tracker": "Price Tracker",
        "kind": "money",
        "good": HIGHER_IS_BETTER,
        "tolerance": 0.05,
        "blurb": "What you are charging. Drifts when a repricer moves it.",
        "source": "Amazon's live offers",
    },
    "fee": {
        "label": "Amazon's cut",
        "tracker": "Fee Tracker",
        "kind": "money",
        "good": LOWER_IS_BETTER,
        "tolerance": 0.10,
        "blurb": "The referral fee Amazon quotes on this ASIN at your price.",
        "source": "Amazon's fee estimate",
    },
}

OK = "ok"
OFF = "off"
UNKNOWN = "unknown"


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _num(v):
    """A float, or None. None and 'not a number' are the same answer: unknown."""
    if v is None or v is True or v is False:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # NaN fails this comparison with itself, which is the cheapest way to catch it.
    return f if f == f else None


def _path(config_path):
    return jsonstore.path_beside_config(config_path, _FILE)


def _blank():
    return {"watch": {}, "history": {}}


def load(config_path):
    d = jsonstore.read_json(_path(config_path), None)
    if not isinstance(d, dict):
        return _blank()
    if not isinstance(d.get("watch"), dict):
        d["watch"] = {}
    if not isinstance(d.get("history"), dict):
        d["history"] = {}
    return d


def _save(config_path, data):
    return jsonstore.write_json_atomic(_path(config_path), data, indent=2)


def _wskey(workspace_id, asin):
    """One key per account per ASIN.

    The account is part of the key because the same ASIN can be listed by two of
    these accounts at different prices, and one shared row would have them
    overwriting each other's readings -- which reads as a price that flaps
    between two values for no reason.
    """
    return "%s::%s" % (str(workspace_id or "").strip(), str(asin or "").strip().upper())


# --------------------------------------------------------------------------
# the watch list
# --------------------------------------------------------------------------

def watch_get(config_path, workspace_id, asin, metric):
    """{"on":bool, "target":float|None} for one ASIN and one metric."""
    row = (load(config_path).get("watch") or {}).get(_wskey(workspace_id, asin)) or {}
    e = row.get(metric) or {}
    return {"on": bool(e.get("on")), "target": _num(e.get("target"))}


def watch_set(config_path, workspace_id, asin, metric, on=None, target=None):
    """Turn a tracker on or off for one ASIN, and/or set its target.

    `on` and `target` are both optional so a screen can change one without
    having to know the other -- passing None for `target` would otherwise be
    indistinguishable from asking to clear it. To clear a target, pass the
    string "" (which _num turns into None) rather than omitting it.
    """
    if metric not in METRICS:
        return {"ok": False, "error": "Unknown tracker: %s" % metric}
    k = _wskey(workspace_id, asin)
    with _LOCK:
        data = load(config_path)
        row = data.setdefault("watch", {}).setdefault(k, {})
        e = row.setdefault(metric, {"on": False, "target": None})
        if on is not None:
            e["on"] = bool(on)
        if target is not None:
            e["target"] = _num(target)
        _save(config_path, data)
        return {"ok": True, "watch": {"on": bool(e.get("on")),
                                      "target": _num(e.get("target"))}}


def tracked(config_path, workspace_id, metric=None):
    """The ASINs being watched, as {asin: {metric: {...}}}.

    Only rows with at least one metric switched ON, because an ASIN whose target
    was set and then untracked should not be fetched. Fetching costs an API call
    per ASIN and this is the list that decides how many.
    """
    out = {}
    prefix = "%s::" % str(workspace_id or "").strip()
    for k, row in (load(config_path).get("watch") or {}).items():
        if not k.startswith(prefix):
            continue
        asin = k[len(prefix):]
        keep = {}
        for m, e in (row or {}).items():
            if m in METRICS and (e or {}).get("on"):
                if metric and m != metric:
                    continue
                keep[m] = {"on": True, "target": _num(e.get("target"))}
        if keep:
            out[asin] = keep
    return out


# --------------------------------------------------------------------------
# readings
# --------------------------------------------------------------------------

def record(config_path, workspace_id, asin, metric, value, at=None):
    """Append one reading. A value that is not a number is NOT stored.

    Refusing to store the unknown is what keeps a failed fetch from becoming a
    data point. If Amazon does not answer, the last real reading stays the last
    real reading and its age is visible, which is the honest picture; writing a
    None into the history would instead show a line dropping to the floor.
    """
    v = _num(value)
    if metric not in METRICS or v is None:
        return False
    k = _wskey(workspace_id, asin)
    with _LOCK:
        data = load(config_path)
        hist = data.setdefault("history", {}).setdefault(k, {}).setdefault(metric, [])
        hist.append({"at": at or _now(), "v": v})
        if len(hist) > MAX_HISTORY:
            del hist[:len(hist) - MAX_HISTORY]
        _save(config_path, data)
    return True


def history(config_path, workspace_id, asin, metric, limit=0):
    h = ((load(config_path).get("history") or {})
         .get(_wskey(workspace_id, asin)) or {}).get(metric) or []
    return h[-limit:] if limit and limit > 0 else list(h)


def latest(config_path, workspace_id, asin, metric):
    h = history(config_path, workspace_id, asin, metric)
    return h[-1] if h else None


# --------------------------------------------------------------------------
# the judgement
# --------------------------------------------------------------------------

def drift(value, target, good):
    """How far off target, as a signed fraction. None when it cannot be known.

    Positive means WORSE than target, negative means better, whichever direction
    "better" happens to be for this metric. Every caller can then use one rule --
    positive is bad -- instead of each remembering which way round its metric is,
    which is precisely the thing that would get it backwards somewhere.
    """
    v, t = _num(value), _num(target)
    if v is None or t is None or t == 0:
        return None
    raw = (v - t) / abs(t)
    return raw if good == LOWER_IS_BETTER else -raw


def status_for(value, target, good, tolerance):
    """OK / OFF / UNKNOWN for one reading.

    UNKNOWN covers two different situations on purpose: no reading, and no
    target. Neither is a pass and neither is a failure -- an ASIN you have not
    given a target cannot be off track, and saying OK would claim a judgement
    that was never made.
    """
    d = drift(value, target, good)
    if d is None:
        return UNKNOWN
    return OFF if d > (tolerance if tolerance is not None else 0) else OK


def rows(config_path, workspace_id, metric=None, names=None):
    """One row per tracked ASIN per metric -- what the screen draws.

    `names` is an optional {asin: title} so the screen can show a product name
    without this module having to know how to look one up. Kept as a parameter
    rather than a lookup because domain/catalogue.py already owns that job.
    """
    out = []
    watch = tracked(config_path, workspace_id, metric)
    for asin, metrics in sorted(watch.items()):
        for m, e in sorted(metrics.items()):
            spec = METRICS[m]
            last = latest(config_path, workspace_id, asin, m)
            h = history(config_path, workspace_id, asin, m, limit=2)
            prev = h[0]["v"] if len(h) > 1 else None
            v = last["v"] if last else None
            tgt = e.get("target")
            d = drift(v, tgt, spec["good"])
            out.append({
                "asin": asin,
                "name": (names or {}).get(asin, ""),
                "metric": m,
                "label": spec["label"],
                "tracker": spec["tracker"],
                "kind": spec["kind"],
                "good": spec["good"],
                "value": v,
                "target": tgt,
                "drift": d,
                # Movement since the previous reading. Reported, but never the
                # thing that raises an alert -- see the module docstring.
                "change": (None if (v is None or prev is None) else round(v - prev, 4)),
                "last_at": last["at"] if last else "",
                "points": len(history(config_path, workspace_id, asin, m)),
                "status": status_for(v, tgt, spec["good"], spec["tolerance"]),
            })
    return out


def alerts(config_path, workspace_id, names=None):
    """Every row that is OFF target, worst first, plus the count.

    ONE count across all four trackers, as Orbit has it. A per-tracker count
    would mean four badges to check, which is four chances to miss the one that
    mattered.
    """
    bad = [r for r in rows(config_path, workspace_id, None, names)
           if r["status"] == OFF]
    bad.sort(key=lambda r: (-(r["drift"] or 0), r["asin"]))
    return {"count": len(bad), "rows": bad}


def summary(config_path, workspace_id, names=None):
    """Counts per tracker for the All Trackers screen."""
    all_rows = rows(config_path, workspace_id, None, names)
    out = {}
    for m, spec in METRICS.items():
        mine = [r for r in all_rows if r["metric"] == m]
        out[m] = {
            "metric": m,
            "tracker": spec["tracker"],
            "label": spec["label"],
            "blurb": spec["blurb"],
            "source": spec["source"],
            "tracked": len(mine),
            "off": len([r for r in mine if r["status"] == OFF]),
            "ok": len([r for r in mine if r["status"] == OK]),
            "unknown": len([r for r in mine if r["status"] == UNKNOWN]),
        }
    return out
