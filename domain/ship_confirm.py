"""domain/ship_confirm.py -- telling Amazon an order was posted, with its tracking.

ONE CALL, NOT TWO. "Mark dispatched" and "upload tracking" are the same Amazon
request: confirmShipment REQUIRES the tracking number, the carrier, the ship
date and every line with its quantity (Amazon's schema, read 29 Sep 2026 --
models/orders-api-model/ordersV0.json, ConfirmShipmentRequest/PackageDetail).

OFF UNTIL THE OWNER SWITCHES IT ON. It is a real, visible change on a real
order: the buyer is told it is on its way and Amazon's late-dispatch and
valid-tracking metrics count it. So the switch is a setting the owner turns on
himself (config "ship_confirm_enabled": true); while it is off the app can
show exactly what WOULD be sent and sends nothing.

WHAT IS NOT GUESSED (Rule 4)
- Carrier codes. Amazon's model does not list the codes it accepts, and a
  wrong code is a refused or mis-tracked confirmation. So every carrier goes as
  carrierCode "Other" with its name in carrierName -- which the schema defines
  -- until a code has been seen accepted. VERIFIED_CARRIER_CODES is where one
  goes then, with the date it was verified.
- Order-item ids. The app does not keep them; they are read from Amazon at the
  moment of sending, so a line Amazon has split or cancelled is not guessed at.
"""
import datetime as _dt

SWITCH_KEY = "ship_confirm_enabled"

# carrier_code (domain/tracking.carrier_code) -> Amazon carrierCode, ONLY after
# Amazon has been seen accepting it. Empty on purpose: see the module note.
# arch-ok: module-mutable-global -- a read-only table, filled by editing this file once Amazon has accepted a code
VERIFIED_CARRIER_CODES = {}

PACKAGE_REFERENCE = "1"      # one parcel per confirmation; "positive numeric values"

OFF_REASON = ("Sending dispatch confirmations to Amazon is switched off. It tells "
              "the buyer the order is on its way and counts towards Amazon's "
              "dispatch metrics, so it stays off until the owner turns it on.")


def is_on(config):
    """True only when the owner has set the switch to exactly true."""
    cfg = (config() if callable(config) else config) or {}
    return cfg.get(SWITCH_KEY) is True


def is_on_now(config_path):
    """The switch as the settings file says it is NOW, not as it was at start.

    The app reads its settings once and keeps them; for this switch that meant
    turning it OFF did nothing until a restart (review finding). Read fresh,
    and any trouble reading counts as off.
    """
    import json
    try:
        with open(str(config_path), encoding="utf-8") as f:
            return is_on(json.load(f))
    except Exception:
        return False


# Sources a tracking row carries when it came from this app telling Amazon.
SENT = "amazon"              # Amazon said it was accepted
UNSURE = "amazon_unsure"     # sent, and the answer never said either way


def already_sent(config_path, workspace_id, marketplace, order_id):
    """The tracking row of an earlier confirmation from this app, or None.

    Amazon's own "shipped" count can lag behind a confirmation for a while, so
    it cannot be what stops a second one. This app's own record does: one
    confirmation per order from here. Removing that tracking number on the
    order (the Remove button) is how a person clears it after checking Seller
    Central.
    """
    from domain import tracking as _tr
    got = _tr.for_orders(config_path, workspace_id, marketplace, [order_id]).get(str(order_id)) or []
    return next((t for t in got if t.get("source") in (SENT, UNSURE)), None)


def carrier_fields(carrier):
    """{carrierCode, carrierName} for what the seller typed. Never a guessed code."""
    from domain import tracking as _tr
    name = str(carrier or "").strip()
    code = VERIFIED_CARRIER_CODES.get(_tr.carrier_code(name))
    if code:
        return {"carrierCode": code, "carrierName": name or code}
    return {"carrierCode": "Other", "carrierName": name}


def iso_ship_date(value=None, now=None):
    """ISO 8601 in UTC ("2026-09-30T10:00:00Z"). Blank = now.

    A date alone ("2026-09-30") is taken as noon UTC that day, so it cannot
    fall on the previous day in any European marketplace. Anything else that is
    not ISO is refused with None -- Amazon's own example of a 400 is a
    "02/21/2022" ship date.
    """
    s = str(value or "").strip()
    if not s:
        t = now or _dt.datetime.now(_dt.timezone.utc)
        return t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        if len(s) == 10:
            d = _dt.datetime.strptime(s, "%Y-%m-%d").replace(hour=12, tzinfo=_dt.timezone.utc)
        else:
            d = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            if d.tzinfo is None:
                return None          # a time with no zone is a guess about which zone
    except ValueError:
        return None
    return d.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lines_to_ship(raw_items):
    """[{orderItemId, quantity}] for what is still to send, from Amazon's own lines.

    quantity = ordered - already shipped. A line with nothing left is left out
    rather than sent as 0.
    """
    out = []
    for it in raw_items or []:
        oid = str((it or {}).get("OrderItemId") or "").strip()
        try:
            left = int(it.get("QuantityOrdered") or 0) - int(it.get("QuantityShipped") or 0)
        except (TypeError, ValueError):
            continue
        if oid and left > 0:
            out.append({"orderItemId": oid, "quantity": left})
    return out


def _item_problems(raw_items):
    """Lines this app will not confirm yet, in words. [] when all is plain."""
    from domain import amazon_flags as _flags
    out = []
    for it in raw_items or []:
        it = it or {}
        try:
            int(it.get("QuantityOrdered") or 0)
            shipped = int(it.get("QuantityShipped") or 0)
        except (TypeError, ValueError):
            # Amazon's schema says integers. A line that is not is refused,
            # not skipped: skipping it would confirm the order only in part.
            out.append("Amazon returned a line of this order in a shape this app "
                       "does not recognise, so nothing was prepared.")
            continue
        if shipped > 0:
            # A second confirmation needs its own package number, and how Amazon
            # treats one has not been seen yet (packageReferenceId is unique per
            # order in its schema). Whole, unshipped orders only for now.
            out.append("Part of this order is already shipped. Confirm the rest in "
                       "Seller Central; this app only confirms orders nothing has "
                       "been shipped from yet.")
        if _flags.truth(it.get("IsTransparency")):
            out.append("This order has a Transparency item, which needs its codes "
                       "sent with it. Confirm it in Seller Central.")
    return sorted(set(out), key=out.index)


def build_payload(marketplace_id, raw_items, tracking_number, carrier, ship_date=None):
    """(ConfirmShipmentRequest or None, [problems in plain words]).

    Every required field of Amazon's schema is checked here, so a request that
    Amazon would refuse for a missing or malformed field is never sent.
    """
    from domain import tracking_sheet as _ts
    problems = _item_problems(raw_items)
    mid = str(marketplace_id or "").strip()
    if not mid:
        problems.append("No Amazon marketplace for this account.")
    tn = str(tracking_number or "").strip()
    if not tn:
        problems.append("Type the tracking number first.")
    elif not _ts.looks_like_tracking(tn):
        problems.append("That does not look like a tracking number.")
    car = carrier_fields(carrier)
    if not car["carrierName"]:
        problems.append("Type the carrier (for example Royal Mail).")
    when = iso_ship_date(ship_date)
    if not when:
        problems.append("The ship date must be a date like 2026-09-30.")
    lines = lines_to_ship(raw_items)
    if not lines and not problems:
        problems.append("Amazon shows nothing left to send on this order.")
    if problems:
        return None, problems
    detail = {"packageReferenceId": PACKAGE_REFERENCE, "trackingNumber": tn,
              "shipDate": when, "orderItems": lines}
    detail.update(car)
    return {"marketplaceId": mid, "packageDetail": detail}, []


def describe(payload):
    """The request in words, for the preview."""
    d = (payload or {}).get("packageDetail") or {}
    n = sum(int(x.get("quantity") or 0) for x in d.get("orderItems") or [])
    when = str(d.get("shipDate", ""))
    try:
        # Read by a person: "29 Sep 2026, 08:26 UTC", not the ISO the request carries.
        when = _dt.datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ").strftime("%d %b %Y, %H:%M UTC").lstrip("0")
    except ValueError:
        pass
    return ("Amazon would be told: shipped %s, %d item%s, %s tracking %s."
            % (when, n, "" if n == 1 else "s",
               d.get("carrierName") or d.get("carrierCode", ""), d.get("trackingNumber", "")))
