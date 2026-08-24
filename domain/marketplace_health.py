"""domain/marketplace_health.py -- stop asking Amazon questions it keeps refusing.

WHY THIS EXISTS
The background refresher walks every (account, marketplace) pair in config and
asks Amazon for a report. Some of those pairs Amazon will never answer, and it
said so every time:

    jack_uk::IE          InvalidInput
    nestwell_goods::IE   InvalidInput
    selvora_limited::IE  InvalidInput
    sheelady_us::MX      Unauthorized
    sheelady_us::CA      Unauthorized

Every one of those is a wasted request against a quota that is SHARED with the
sales figures the owner is actually waiting for -- three report requests in quick
succession already earn a QuotaExceeded. So a marketplace that cannot work is not
merely noise in a log; it is the reason real data arrives late.

WHY IT BACKS OFF RATHER THAN GIVING UP
"Amazon refused" is not always permanent. A token gets re-authorised, a
marketplace gets added to the developer profile, a region is enabled. Never
asking again would turn a fixable problem into a silent one, and the owner would
have no way to discover it had been fixed. So a pair that keeps failing is asked
less and less often -- an hour, then six, then a day -- and one success clears
the record completely.

A TRANSIENT ERROR MUST NOT LOOK LIKE A PERMANENT ONE
A timeout or a 503 says nothing about whether the pair is valid, so those do not
count towards the backoff at all. Only Amazon telling us who we are or what we
asked for is wrong -- Unauthorized, Forbidden, InvalidInput and their kin -- is
treated as evidence about the pair itself.
"""
import time

from domain import jsonstore as _js

_FILE = "marketplace_health.json"

# Consecutive refusals before a pair is rested. Two rather than one: a single
# odd reply should not park a marketplace that works.
FAILURES_BEFORE_REST = 2

# How long a rested pair is left alone, by how many times it has now failed.
# Rises, and stops rising at a day -- long enough to stop wasting quota, short
# enough that a fix is noticed the same day.
BACKOFF = [3600, 6 * 3600, 24 * 3600]

# Amazon telling us the request itself is wrong. Anything not in here (a
# timeout, a 500, a quota) says nothing about whether the pair is valid.
PERMANENT_MARKERS = (
    "unauthorized", "forbidden", "accessdenied", "invalidinput",
    "invalid input", "notfound", "not found", "badrequest",
    "invalid marketplace", "unsupported",
)


def _path(config_path):
    return _js.path_beside_config(config_path, _FILE)


def _load(config_path):
    d = _js.read_json(_path(config_path), default={})
    return d if isinstance(d, dict) else {}


def _key(account_id, marketplace):
    return "%s::%s" % (str(account_id or ""), str(marketplace or "").upper())


def looks_permanent(error):
    """Is this Amazon saying the REQUEST is wrong, rather than being busy?"""
    e = str(error or "").lower()
    return any(m in e for m in PERMANENT_MARKERS)


# What Amazon's refusals mean, said the way CLAUDE.md Rule 5 asks for. Ordered
# most specific first, because "unauthorized" appears inside several of them.
_PLAIN = (
    ("quotaexceeded", "Amazon is rate-limiting this account — it will answer "
                      "again shortly."),
    ("throttl",       "Amazon is rate-limiting this account — it will answer "
                      "again shortly."),
    ("unauthorized",  "Amazon refused: this app is not authorised for that. "
                      "The permission is granted in Seller Central, under the "
                      "app's developer settings."),
    ("accessdenied",  "Amazon refused: this app is not authorised for that. "
                      "The permission is granted in Seller Central, under the "
                      "app's developer settings."),
    ("forbidden",     "Amazon refused: this app is not authorised for that. "
                      "The permission is granted in Seller Central, under the "
                      "app's developer settings."),
    ("invalidinput",  "Amazon does not recognise that request for this "
                      "marketplace — usually the account is not registered to "
                      "sell there."),
    ("invalid input", "Amazon does not recognise that request for this "
                      "marketplace — usually the account is not registered to "
                      "sell there."),
    ("notfound",      "Amazon has nothing under that reference."),
    ("not found",     "Amazon has nothing under that reference."),
    ("timeout",       "Amazon did not answer in time. Nothing is wrong with "
                      "the account; try again."),
    ("timed out",     "Amazon did not answer in time. Nothing is wrong with "
                      "the account; try again."),
)


def explain(error):
    """Amazon's error, in a sentence a person can act on. "" for no error.

    WHY THIS IS HERE AND NOT SPELLED OUT AT EACH SCREEN

    What the app actually showed on the Orders page was this, verbatim:

        jack_uk - [{'code': 'Unauthorized', 'message': 'Access to requested
        resource is denied.', 'details': ''}]

    which is a Python list of dictionaries printed at somebody who wants to know
    why their orders are missing. CLAUDE.md Rule 5 says the plain English comes
    first, and Rule 12 says it is written once -- this module already decides
    what these errors MEAN (see looks_permanent and PERMANENT_MARKERS), so the
    wording belongs beside that judgement rather than in each screen.

    The raw text is never thrown away: callers show this sentence and keep
    Amazon's own words underneath, because the exact string is what makes a
    problem searchable when the sentence turns out not to cover it.
    """
    raw = str(error or "").strip()
    if not raw:
        return ""
    low = raw.lower()
    for marker, said in _PLAIN:
        if marker in low:
            return said
    # NOT GUESSED AT. An error this does not recognise is handed back as it came
    # rather than described with a sentence that might be wrong -- a confident
    # wrong explanation sends somebody to fix the wrong thing.
    return raw[:300]


def record(config_path, account_id, marketplace, ok, error=""):
    """Note how an attempt went. Returns the pair's record after the update."""
    data = _load(config_path)
    k = _key(account_id, marketplace)
    rec = data.get(k) if isinstance(data.get(k), dict) else {}

    if ok:
        # Cleared entirely rather than decremented: the pair demonstrably works
        # now, and carrying a grudge from before it was fixed would rest it again
        # on the next single hiccup.
        if k in data:
            data.pop(k, None)
            _js.write_json_atomic(_path(config_path), data)
        return {}

    if not looks_permanent(error):
        # A transient failure is not evidence about this pair. Recorded for the
        # diagnostics page, but it does not count towards resting it.
        rec["last_transient"] = str(error or "")[:200]
        rec["last_seen"] = time.time()
        data[k] = rec
        _js.write_json_atomic(_path(config_path), data)
        return rec

    rec["failures"] = int(rec.get("failures") or 0) + 1
    rec["last_error"] = str(error or "")[:200]
    rec["last_seen"] = time.time()
    if rec["failures"] >= FAILURES_BEFORE_REST:
        step = min(rec["failures"] - FAILURES_BEFORE_REST, len(BACKOFF) - 1)
        rec["rest_until"] = time.time() + BACKOFF[step]
    data[k] = rec
    _js.write_json_atomic(_path(config_path), data)
    return rec


def skip_reason(config_path, account_id, marketplace, now=None):
    """Why this pair should be left alone right now, or "" to go ahead."""
    rec = _load(config_path).get(_key(account_id, marketplace))
    if not isinstance(rec, dict):
        return ""
    until = rec.get("rest_until")
    if not until:
        return ""
    now = time.time() if now is None else now
    if now >= float(until):
        return ""
    mins = int((float(until) - now) / 60)
    return ("Amazon refused this %d times (%s) -- not asking again for %dm"
            % (int(rec.get("failures") or 0),
               str(rec.get("last_error") or "")[:60], max(1, mins)))


def filter_targets(config_path, pairs, now=None):
    """(pairs worth asking, [(pair, why it was skipped), ...])."""
    keep, skipped = [], []
    for aid, mkt in pairs or []:
        why = skip_reason(config_path, aid, mkt, now=now)
        if why:
            skipped.append(((aid, mkt), why))
        else:
            keep.append((aid, mkt))
    return keep, skipped


def status(config_path):
    """Every pair currently being rested, for the diagnostics page.

    Surfaced rather than only logged: a marketplace quietly not being refreshed
    is exactly the kind of thing that is never noticed until someone asks why a
    country has no data.
    """
    now = time.time()
    out = []
    for k, rec in sorted(_load(config_path).items()):
        if not isinstance(rec, dict):
            continue
        until = rec.get("rest_until")
        out.append({
            "pair": k,
            "failures": int(rec.get("failures") or 0),
            "last_error": rec.get("last_error") or rec.get("last_transient") or "",
            "resting": bool(until and now < float(until)),
            "resumes_in_minutes": (int((float(until) - now) / 60)
                                   if until and now < float(until) else 0),
        })
    return out
