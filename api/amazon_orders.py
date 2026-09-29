"""api/amazon_orders.py -- reading what was in an order, from the Orders API.

    order_items_raw   getOrderItems, every page -> Amazon's own OrderItems list

THE ONE READ (architecture 4E leftover, 29 Sep 2026). Four places wrote this
call out by hand -- domain/orders_live, routes/orders_routes (twice),
domain/inventory_module -- plus the dispatch module; only that last one followed
Amazon's NextToken, so a long order was read in part everywhere else. Each
caller still shapes the lines its own way (orders_view.to_item, the Sales
lines, unit counts); only the read is shared. Outside-API calls only (Rule 7).
"""


def client(creds, marketplace_enum):
    """An Orders API client (v0, the library's default) for one account."""
    from sp_api.api import Orders
    return Orders(credentials=creds, marketplace=marketplace_enum)


def order_items_raw(creds, marketplace_enum, order_id, oc=None, max_pages=20):
    """Amazon's raw OrderItems for one order, every page. Raises what the
    library raises; each caller already decides what a failed read means.

    `oc` is a client the caller already holds (a loop over many orders, or a
    route that also reads the order head), so no extra client is built.
    """
    oc = oc or client(creds, marketplace_enum)
    out, token = [], None
    for _ in range(int(max_pages)):
        r = oc.get_order_items(order_id, NextToken=token) if token else oc.get_order_items(order_id)
        pay = r.payload if hasattr(r, "payload") else r
        out.extend((pay or {}).get("OrderItems") or [])
        token = (pay or {}).get("NextToken")
        if not token:
            break
    return out
