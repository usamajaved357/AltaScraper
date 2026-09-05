"""domain/tracking.py -- where each parcel is, and how much of that is knowable.

TWO QUESTIONS, TWO SOURCES, AND ONLY ONE OF THEM IS AMAZON'S.

    "has Amazon marked this shipped?"    Amazon answers. Free, already synced.
    "where is the parcel right now?"     Only the carrier answers, and Amazon
                                         will not tell us the tracking number.

MEASURED, NOT ASSUMED. Amazon does not give back the tracking a seller uploads:

    getOrder              no tracking, no carrier. OrderStatus,
                          NumberOfItemsShipped/Unshipped, ShipServiceLevel only
    getOrderItems         QuantityShipped only
    All Orders report     33 columns, none of them tracking or carrier
    MerchantFulfillment   get_shipment needs a shipmentId and there is no
                          "list my shipments" call, so it cannot discover one

So the number comes from the seller -- a sheet out, a sheet back, the same shape
as the per-order costs. What Amazon DOES give is the shipment state, and that is
worth showing on its own: "Amazon says shipped, 1 of 1" answers most of the
question most of the time, and costs nothing.

THE CARRIER LOOKUP IS PLUGGABLE, AND OFF UNTIL IT IS CONFIGURED.
There is no free universal parcel API. Royal Mail, Evri, DPD and the rest each
want their own credentials -- a seller posting with three of them would have to
obtain three -- so the one that ships is an aggregator, 17TRACK, whose single
key covers all of them (api/track17.py). It is inert until that key is in
settings: a tracking number with no provider configured reports "not checked"
and says why, rather than showing a made-up "In transit".

A GUESSED PARCEL STATUS IS WORSE THAN NO STATUS. "Delivered" is the single most
consequential word on this screen -- it decides whether a refund is argued or
paid -- and inferring it from a ship date would be a guess wearing a fact's
clothes.
"""
import datetime as _dt
import re

from data import db as _db

# The words this app groups by. A carrier's own wording is kept beside them.
#
#     "show me the status of the trackings, is it delivered, out for delivery,
#      dropped off, in transit, whatever is on the website"
#
# THREE OF THESE ARE NOT ABOUT THE PARCEL, and separating them is the point:
#
#   UNKNOWN    nobody has asked the carrier yet
#   NOT_FOUND  the carrier was asked and has no record of that number
#   PRE_TRANSIT a label exists and the carrier has not received the parcel
#
# Folding those into one "no status" hides the only one that needs doing
# something about: NOT_FOUND almost always means the number was mistyped or
# pasted from the wrong row, and it looks identical to "not checked yet" unless
# it is given its own word.
PRE_TRANSIT = "pre_transit"      # label made, carrier has not had it yet
COLLECTED = "collected"          # dropped off / accepted by the carrier
IN_TRANSIT = "in_transit"
OUT_FOR_DELIVERY = "out_for_delivery"
AWAITING_COLLECTION = "awaiting_collection"   # at a pickup point for the buyer
DELIVERED = "delivered"
EXCEPTION = "exception"          # failed delivery, held, returned, lost
NOT_FOUND = "not_found"          # asked, and the carrier does not know it
UNKNOWN = "unknown"              # never asked

STATUS_LABEL = {
    PRE_TRANSIT: "Label made",
    COLLECTED: "Dropped off",
    IN_TRANSIT: "In transit",
    OUT_FOR_DELIVERY: "Out for delivery",
    AWAITING_COLLECTION: "Waiting to be collected",
    DELIVERED: "Delivered",
    EXCEPTION: "Problem",
    NOT_FOUND: "Carrier has no record",
    UNKNOWN: "Not checked",
}

# LEAST FINISHED FIRST. An order in two parcels, one delivered and one still
# out, is NOT delivered -- so the least-finished parcel decides what the row
# says. Saying "Delivered" because one box of two arrived is the failure this
# ordering exists to prevent.
STATUS_ORDER = (EXCEPTION, NOT_FOUND, UNKNOWN, PRE_TRANSIT, COLLECTED,
                IN_TRANSIT, OUT_FOR_DELIVERY, AWAITING_COLLECTION, DELIVERED)

# Carrier wording -> our word. Ordered: the first match wins, and the more
# specific phrases come first because "out for delivery" contains "delivery"
# and "delivered" contains "deliver".
_MAP = (
    (r"out for delivery|with (the )?courier|on (the )?van|"
     r"on board for delivery", OUT_FOR_DELIVERY),
    (r"ready (for|to) collect|available for (pick ?up|collection)|"
     r"awaiting collection|at (the )?(collection|pick ?up) point|"
     r"in (your )?locker", AWAITING_COLLECTION),
    (r"delivered|signed for|left with|handed to", DELIVERED),
    (r"failed|refused|held|return(ed|ing) to sender|undeliverable|exception|"
     r"damaged|lost|no access|card left", EXCEPTION),
    (r"not found|no (tracking )?(information|record)|no such|unrecognis",
     NOT_FOUND),
    (r"collected|picked up|dropped off|accepted|received by|in possession",
     COLLECTED),
    (r"in transit|on its way|despatch|dispatch|processed|sorted|at (the )?depot|"
     r"prepared|shipped", IN_TRANSIT),
    # LAST, because "label" and "awaiting" appear inside phrases that mean more
    # than this does -- "awaiting collection" is the buyer's end, not ours.
    (r"label (created|made|printed)|information received|"
     r"awaiting (item|parcel|despatch)|pre-?advice|manifest", PRE_TRANSIT),
)


def normalise(raw):
    """A carrier's own words -> one of ours. UNKNOWN when nothing matches.

    UNKNOWN rather than a nearest guess: a status this app has not been taught
    is a status it does not know, and the carrier's own words are shown beside
    it so nothing is lost while it stays unrecognised.
    """
    s = str(raw or "").strip().lower()
    if not s:
        return UNKNOWN
    for pat, word in _MAP:
        if re.search(pat, s):
            return word
    return UNKNOWN


# ---------------------------------------------------------------------------
# Carrier providers
# ---------------------------------------------------------------------------
#
# A provider is a callable: f(carrier_code, tracking_number) -> dict with
# status, raw_status, last_event, last_event_at -- or raises.
#
# 17TRACK is the one that ships, and it is INERT WITHOUT A KEY: provider_for
# returns (None, why) rather than a lookup, so the honest state until the owner
# supplies one is that nothing is checked and the screen says so.

_PROVIDERS = {}


def register_provider(name, build):
    """Add a carrier lookup.

    `build(cfg)` returns either a callable f(carrier_code, number) or
    (None, why) when that provider is not usable with the settings it was given
    -- a missing key being the ordinary case. The reason is shown to the seller,
    so it has to be a sentence rather than a boolean.
    """
    _PROVIDERS[str(name)] = build


def providers():
    """The lookups this app knows how to call, for the settings screen."""
    return sorted(_PROVIDERS)


NO_PROVIDER = ("No parcel-tracking service is set up, so the carrier has not "
               "been asked where these are. Amazon does not hand back the "
               "tracking a seller uploads and there is no free universal "
               "carrier API, so this needs a 17TRACK key in Settings — one key "
               "covers Royal Mail, Evri, DPD, Yodel and the rest.")


def provider_for(config):
    """The configured lookup, or (None, why). Never raises."""
    cfg = (config() if callable(config) else config) or {}
    name = str(cfg.get("tracking_provider") or "").strip()
    if not name:
        # A KEY ON ITS OWN IS ENOUGH. Making somebody set a provider NAME as
        # well, when exactly one is configured, is a second place for the
        # feature to be silently off.
        if str(cfg.get("track17_key") or "").strip():
            name = "17track"
        else:
            return None, NO_PROVIDER
    build = _PROVIDERS.get(name)
    if not build:
        return None, ("The tracking service %r in your settings is not one this "
                      "app knows how to call. It knows: %s."
                      % (name, ", ".join(providers()) or "none"))
    try:
        got = build(cfg)
    except Exception as e:
        return None, ("The %s tracking service could not be set up: %s"
                      % (name, str(e)[:150]))
    if isinstance(got, tuple):
        return got
    return got, ""


def _build_17track(cfg):
    """17TRACK, if a key is in settings.

    THE CARRIER IS NOT SENT. 17TRACK identifies carriers by numeric id and this
    app has never seen that list; sending a guessed number would ask the wrong
    carrier about a real parcel and get a confident "not found". Its auto-detect
    is documented and is the honest option until the id list is read from the
    service itself.
    """
    key = str((cfg or {}).get("track17_key") or "").strip()
    if not key:
        return None, NO_PROVIDER

    from api import track17 as _t17

    def look(carrier_code, number):
        # Registered first, every time: gettrackinfo only answers about numbers
        # 17TRACK is already watching, and an unregistered one comes back
        # looking exactly like "the carrier has never heard of it".
        try:
            _t17.register(key, number)
        except _t17.Track17Error:
            # Already registered is the usual reason, and is a success. A real
            # outage will fail again on the next line, where it is reported.
            pass
        got = _t17.track(key, number)
        # The enum won. Only when it is absent does the event prose get a vote.
        if not got.get("status"):
            got["status"] = normalise(got.get("last_event"))
        return got

    return look


register_provider("17track", _build_17track)


# A SHORT CODE IS MATCHED WHOLE, NEVER INSIDE A WORD.
#
# "rm" for Royal Mail is contained in "he-RM-es", so a substring match turned
# Hermes into Royal Mail -- the wrong carrier, on a screen whose whole job is to
# say where a parcel is, and wrong in a way that looks perfectly normal. Caught
# by running the mapping over the carriers actually in use.
#
# So: `exact` is compared to the whole normalised string, `contains` may appear
# anywhere. A two-letter code goes in `exact`; three or more is distinctive
# enough to match inside a longer name, which is what carriers actually write --
# "DPD Local", "AMZL_UK" and "Royal Mail 24" are all the carrier plus a service.
#
# Evri comes before Royal Mail so that even a future short-code slip cannot take
# a Hermes parcel away from it again.
_CARRIERS = (
    ("evri", (), ("evri", "hermes")),
    ("royalmail", ("rm",), ("royalmail",)),
    ("parcelforce", (), ("parcelforce",)),
    ("dpd", (), ("dpd",)),
    ("yodel", (), ("yodel",)),
    ("dhl", (), ("dhl",)),
    ("ups", (), ("ups",)),
    ("fedex", (), ("fedex",)),
    ("amazon", (), ("amazon", "amzl", "buyshipping")),
    ("inpost", (), ("inpost",)),
    ("tuffnells", (), ("tuffnells",)),
    ("ukmail", (), ("ukmail",)),
)


def carrier_code(name):
    """A carrier's name as the seller typed it -> a stable code.

    An unrecognised carrier keeps its own normalised name rather than being
    forced into the nearest match: a provider that does not know it will say so,
    which is recoverable, where a parcel silently tracked against the wrong
    carrier is not.
    """
    s = re.sub(r"[^a-z0-9]+", "", str(name or "").lower())
    if not s:
        return ""
    for code, exact, contains in _CARRIERS:
        if s in exact:
            return code
        if any(w and w in s for w in contains):
            return code
    return s


# ---------------------------------------------------------------------------
# Storing and reading
# ---------------------------------------------------------------------------


def add(config_path, workspace_id, marketplace, order_id, tracking_number,
        carrier="", sku="", source="upload"):
    """Record one tracking number. Re-adding the same one updates the carrier."""
    tn = str(tracking_number or "").strip()
    if not (order_id and tn):
        return 0
    conn = _db.get_db(config_path)
    now = _dt.datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO order_tracking (workspace_id, marketplace, order_id, sku, "
        "carrier, carrier_code, tracking_number, status, source, added_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(workspace_id, marketplace, order_id, tracking_number) "
        "DO UPDATE SET carrier=excluded.carrier, "
        "carrier_code=excluded.carrier_code, sku=excluded.sku",
        (workspace_id, marketplace, str(order_id).strip(), str(sku or "").strip(),
         str(carrier or "").strip(), carrier_code(carrier), tn, UNKNOWN,
         source, now))
    conn.commit()
    return 1


def remove(config_path, workspace_id, marketplace, order_id, tracking_number):
    """Forget one tracking number. One number, named explicitly.

    Deliberately NOT "clear this order": a split shipment has two numbers and
    only one of them is usually wrong, and a removal that takes both is not
    recoverable from the screen that offered it.
    """
    tn = str(tracking_number or "").strip()
    if not (order_id and tn):
        return 0
    conn = _db.get_db(config_path)
    cur = conn.execute(
        "DELETE FROM order_tracking WHERE workspace_id=? AND marketplace=? "
        "AND order_id=? AND tracking_number=?",
        (workspace_id, marketplace, str(order_id).strip(), tn))
    conn.commit()
    return cur.rowcount or 0


def for_orders(config_path, workspace_id, marketplace, order_ids=None):
    """{order_id: [rows]} for the orders a screen is showing."""
    conn = _db.get_db(config_path)
    sql = ("SELECT * FROM order_tracking WHERE workspace_id=? AND marketplace=?")
    args = [workspace_id, marketplace]
    ids = [str(o).strip() for o in (order_ids or []) if str(o).strip()]
    if ids:
        ids = ids[:900]
        sql += " AND order_id IN (%s)" % ",".join("?" * len(ids))
        args += ids
    out = {}
    for r in conn.execute(sql + " ORDER BY added_at DESC", args):
        d = dict(r)
        d["status_label"] = STATUS_LABEL.get(d.get("status") or UNKNOWN,
                                             STATUS_LABEL[UNKNOWN])
        # STALENESS IS PART OF THE STATUS. "Delivered, checked 6 days ago" and
        # "Delivered, checked an hour ago" are different claims about now.
        d["stale"] = _is_stale(d.get("checked_at"))
        out.setdefault(d["order_id"], []).append(d)
    return out


def attach(config_path, rows, order_key="order_id", account_key="account_id",
           marketplace_key="marketplace"):
    """Put the tracking onto order rows, in place. -> the same rows.

    THE ORDERS LIST SPANS ACCOUNTS, so this groups by (account, marketplace)
    and asks once per group rather than once per row. A row whose account or
    marketplace is missing is left untouched: tracking belongs to one order of
    one account, and guessing which would attach another account's parcel.

    The ONE place order rows learn about tracking, so the list and the detail
    can never disagree about where a parcel is (CLAUDE.md Rule 12).
    """
    groups = {}
    for r in rows or []:
        a = str((r or {}).get(account_key) or "").strip()
        m = str((r or {}).get(marketplace_key) or "").strip().upper()
        o = str((r or {}).get(order_key) or "").strip()
        if a and m and o:
            groups.setdefault((a, m), []).append(o)

    found = {}
    for (a, m), ids in groups.items():
        try:
            got = for_orders(config_path, a, m, ids)
        except Exception:
            # A tracking table that cannot be read must not empty the orders
            # screen. The rows come back with no tracking, which is what they
            # had before this feature existed.
            continue
        for oid, lst in got.items():
            found[(a, m, str(oid))] = lst

    for r in rows or []:
        a = str((r or {}).get(account_key) or "").strip()
        m = str((r or {}).get(marketplace_key) or "").strip().upper()
        o = str((r or {}).get(order_key) or "").strip()
        got = found.get((a, m, o)) or []
        r["tracking"] = got
        r["tracking_status"] = summarise_rows(got)
    return rows


def summarise_rows(rows):
    """Several parcels on one order -> the one line the list shows.

    An order shipped in two parcels, one delivered and one still out, is NOT
    delivered -- so the least-finished parcel decides. Saying "Delivered"
    because one box arrived is the failure this ordering exists to prevent.
    """
    rows = list(rows or [])
    if not rows:
        return {"status": "", "label": "", "count": 0, "stale": False}
    # A status this app has not been taught sorts where UNKNOWN does -- it is
    # not evidence the parcel has got anywhere.
    worst = min([(r.get("status") or UNKNOWN) for r in rows],
                key=lambda s: (STATUS_ORDER.index(s) if s in STATUS_ORDER
                               else STATUS_ORDER.index(UNKNOWN)))
    # AND IT LEAVES AS ONE OF OUR WORDS. Sorting an unrecognised status where
    # UNKNOWN sits is not enough on its own: returning the raw token gives it a
    # bucket of its own in anything that counts or filters by status, and it
    # renders as "Not checked" while being counted as something else. The
    # carrier's own wording is kept on the parcel row, which is where it belongs.
    if worst not in STATUS_LABEL:
        worst = UNKNOWN
    return {
        "status": worst,
        "label": STATUS_LABEL.get(worst, STATUS_LABEL[UNKNOWN]),
        "count": len(rows),
        # Any parcel checked too long ago makes the whole line stale: the
        # summary is only as current as its least current part.
        "stale": any(r.get("stale") for r in rows),
        "checked_at": max((str(r.get("checked_at") or "") for r in rows),
                          default=""),
    }


def _is_stale(checked_at, hours=12):
    if not checked_at:
        return True
    try:
        t = _dt.datetime.fromisoformat(str(checked_at)[:19])
    except ValueError:
        return True
    return (_dt.datetime.now() - t).total_seconds() > hours * 3600


def summary(config_path, workspace_id, marketplace):
    """How many parcels are in each state, and how many were never asked about."""
    conn = _db.get_db(config_path)
    out = {}
    for r in conn.execute(
            "SELECT COALESCE(NULLIF(status,''),'unknown') s, COUNT(*) n "
            "FROM order_tracking WHERE workspace_id=? AND marketplace=? "
            "GROUP BY s", (workspace_id, marketplace)):
        out[r["s"]] = r["n"]
    never = conn.execute(
        "SELECT COUNT(*) FROM order_tracking WHERE workspace_id=? AND "
        "marketplace=? AND COALESCE(checked_at,'')=''",
        (workspace_id, marketplace)).fetchone()[0]
    return {"by_status": out, "never_checked": never,
            "total": sum(out.values())}


def refresh(config_path, config, workspace_id, marketplace, limit=50):
    """Ask the carrier where each parcel is. -> a report. Never raises.

    Does nothing at all when no provider is configured, and says so -- rather
    than leaving every parcel showing a status nobody asked for.
    """
    fn, why = provider_for(config)
    if not fn:
        return {"ok": False, "checked": 0, "error": why}

    conn = _db.get_db(config_path)
    rows = conn.execute(
        "SELECT * FROM order_tracking WHERE workspace_id=? AND marketplace=? "
        "AND COALESCE(status,'') <> ? ORDER BY COALESCE(checked_at,'') LIMIT ?",
        (workspace_id, marketplace, DELIVERED, int(limit))).fetchall()

    now = _dt.datetime.now().isoformat(timespec="seconds")
    done = failed = 0
    for r in rows:
        try:
            got = fn(r["carrier_code"], r["tracking_number"]) or {}
        except Exception as e:
            conn.execute("UPDATE order_tracking SET checked_at=?, check_error=? "
                         "WHERE id=?", (now, str(e)[:300], r["id"]))
            failed += 1
            continue
        raw = str(got.get("raw_status") or "")
        # THE PROVIDER'S OWN MAPPING WINS. It read a documented enum; normalise
        # reads prose and is the fallback for a provider that has no enum to
        # give. Re-deriving from the text here would throw away the better
        # answer the provider already had.
        status = str(got.get("status") or "") or normalise(raw)
        if status not in STATUS_LABEL:
            status = UNKNOWN
        conn.execute(
            "UPDATE order_tracking SET status=?, raw_status=?, last_event=?, "
            "last_event_at=?, checked_at=?, check_error=NULL WHERE id=?",
            (status, raw, str(got.get("last_event") or "")[:300],
             str(got.get("last_event_at") or ""), now, r["id"]))
        done += 1
    conn.commit()
    return {"ok": True, "checked": done, "failed": failed,
            "left": max(0, len(rows) - done - failed)}
