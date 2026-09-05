"""api/track17.py -- ask 17TRACK where a parcel is. HTTP only.

WHY AN AGGREGATOR AND NOT THE CARRIERS THEMSELVES
Royal Mail, Evri, DPD, Yodel and Parcelforce each publish their own API, each
wants its own business account and its own credentials, and a seller who posts
with three of them would have to obtain three. One aggregator key covers all of
them, and this app already knows which carrier each parcel is with, so the
carrier is passed through when it is known and left to auto-detect when it is
not.

WRITTEN FROM THE PUBLISHED DOCUMENT, NOT FROM MEMORY (CLAUDE.md Rule 4).
    POST https://api.17track.net/track/v2.2/register     start watching a number
    POST https://api.17track.net/track/v2.2/gettrackinfo  read where it is
    header  17token: <key>          Content-Type: application/json
    body    a JSON ARRAY of {number, carrier?} -- an array even for one parcel
    reply   {"code":0,"data":{"accepted":[...],"rejected":[...]}}
            accepted[].track_info.latest_status.status is the documented enum
            accepted[].track_info.providers[].events[] are the scans

REGISTER FIRST, ALWAYS. gettrackinfo answers about numbers 17TRACK is already
watching; a number it has never been given comes back in `rejected` rather than
as an error, which reads exactly like "the carrier has never heard of it". So a
number is registered before it is asked about, and a rejection from register
that says "already registered" is a success, not a failure.

THE STATUS IS READ FROM THE ENUM, NEVER FROM THE PROSE. 17TRACK publishes nine
status values; the event description beside them is free text that varies by
carrier and language. Mapping the enum is exact. The prose is kept and shown,
and is only fallen back on when the enum is absent.
"""
import json
import urllib.error
import urllib.request

BASE = "https://api.17track.net/track/v2.2"
TIMEOUT = 20

# 17TRACK's documented statuses -> this app's words. domain/tracking.py owns the
# words; this file owns only the translation, so a new status here cannot invent
# a new word anywhere else.
STATUS = {
    "InfoReceived": "pre_transit",
    "InTransit": "in_transit",
    "OutForDelivery": "out_for_delivery",
    "AvailableForPickup": "awaiting_collection",
    "Delivered": "delivered",
    "DeliveryFailure": "exception",
    "Exception": "exception",
    "Expired": "exception",
    "NotFound": "not_found",
}


class Track17Error(Exception):
    pass


def _post(path, key, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"17token": str(key), "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        # THE SERVICE'S OWN WORDS, not "HTTP 401". A wrong key and an exhausted
        # quota are both 4xx and need different things doing about them, and the
        # difference is only ever in the body.
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise Track17Error("17TRACK refused (%s) %s" % (e.code, detail))
    except urllib.error.URLError as e:
        raise Track17Error("could not reach 17TRACK: %s" % str(e.reason)[:150])
    except ValueError:
        raise Track17Error("17TRACK sent something that was not JSON")


def register(key, number, carrier=None):
    """Start watching a number. Already-registered counts as success.

    Returns nothing useful; it raises only when the whole call failed. A single
    number being rejected is reported by the caller's gettrackinfo, which has
    the real answer -- failing here would stop a batch because one number in it
    was already known.
    """
    item = {"number": str(number)}
    if carrier:
        item["carrier"] = carrier
    _post("/register", key, [item])


def track(key, number, carrier=None):
    """Where is this parcel? -> {raw_status, last_event, last_event_at, status}.

    `status` is this app's word, mapped from 17TRACK's documented enum.
    Raises Track17Error when the service could not be asked at all -- which is
    different from it answering "I do not know this number", and the caller
    stores those two differently.
    """
    body = [{"number": str(number)}]
    if carrier:
        body[0]["carrier"] = carrier
    got = _post("/gettrackinfo", key, body)

    if int(got.get("code") or 0) not in (0, 200):
        raise Track17Error("17TRACK returned code %s" % got.get("code"))

    data = got.get("data") or {}
    acc = data.get("accepted") or []
    if not acc:
        rej = (data.get("rejected") or [{}])[0]
        err = (rej.get("error") or {}).get("message") or "not accepted"
        # NOT AN EXCEPTION. "17TRACK will not take that number" is an answer
        # about the number, and the seller needs to see it against the parcel
        # rather than as a failed check they are told to retry.
        return {"status": "not_found", "raw_status": "NotFound",
                "last_event": str(err)[:300], "last_event_at": ""}

    info = (acc[0].get("track_info") or {})
    latest = info.get("latest_status") or {}
    raw = str(latest.get("status") or "")
    sub = str(latest.get("sub_status") or "")

    ev = _newest_event(info)
    return {
        # The enum first. The event prose is the fallback and is mapped by
        # domain.tracking.normalise, which the caller applies.
        "status": STATUS.get(raw, ""),
        "raw_status": (raw + (" / " + sub if sub else "")) or ev.get("desc", ""),
        "last_event": ev.get("desc", ""),
        "last_event_at": ev.get("time", ""),
    }


def _newest_event(info):
    """The most recent scan across every provider on the parcel.

    A parcel handed between carriers has one `providers` entry each, and the
    interesting scan is whichever happened last -- not whichever provider the
    document happens to list first.
    """
    best = {"desc": "", "time": ""}
    for p in (info.get("providers") or []):
        for e in (p.get("events") or []):
            t = str(e.get("time_raw") or e.get("time_utc") or "")
            if t >= best["time"]:
                best = {"desc": str(e.get("description") or "")[:300],
                        "time": t}
    return best
