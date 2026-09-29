"""api/amazon_orders_ship.py -- the two Orders API calls behind "mark dispatched".

    order_items       getOrderItems           READ  -- the order-item ids
    confirm_shipment  confirmShipment (v0)    WRITE -- tells Amazon it shipped

Outside-API calls only (CLAUDE.md Rule 7). Whether a confirmation may be sent
at all, and what is in it, is decided in domain/ship_confirm.py; nothing here
checks the switch, so nothing may call confirm_shipment except that module's
caller, routes/order_ship_routes.py, after it has checked.

The request body is Amazon's ConfirmShipmentRequest, passed through exactly as
built (Rule 4: models/orders-api-model/ordersV0.json, read 29 Sep 2026).
"""


class NotConfirmed(Exception):
    """Amazon's reply did not SAY it was accepted -- which is not the same as a
    refusal. The confirmation may or may not have landed."""


def _client(creds, marketplace_enum):
    from sp_api.api import Orders
    # v0 is the library's default and the version confirmShipment lives on.
    return Orders(credentials=creds, marketplace=marketplace_enum)


def order_items(creds, marketplace_enum, order_id):
    """Amazon's raw OrderItems list for one order (every page) -- the one read,
    api/amazon_orders.order_items_raw."""
    from api import amazon_orders as _ao
    return _ao.order_items_raw(creds, marketplace_enum, order_id, oc=_client(creds, marketplace_enum))


def confirm_shipment(creds, marketplace_enum, order_id, request_body):
    """Send one ConfirmShipmentRequest. -> the HTTP status (2xx) on success.

    SUCCESS ONLY WHEN AMAZON SAYS SO. The library raises only when the reply
    carries an `errors` list; any other failed reply (a gateway page, a 403
    shaped {"message": ...}) comes back as an ordinary response. So the reply's
    status is read -- the library puts it in the payload for a bodiless 2xx,
    which is what confirmShipment's 204 is (sp_api/base/_core.parse_response)
    -- and anything else raises NotConfirmed (review finding, 29 Sep 2026).
    A refusal with Amazon's errors is raised by the library as it was.
    """
    oc = _client(creds, marketplace_enum)
    r = oc.confirm_shipment(order_id, **request_body)
    pay = getattr(r, "payload", None)
    st = pay.get("status_code") if isinstance(pay, dict) else None
    if isinstance(st, int) and 200 <= st < 300:
        return st
    raise NotConfirmed("Amazon's reply did not say it was accepted: %s" % str(pay)[:300])
