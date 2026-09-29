"""domain/order_scope.py -- which account and marketplace an order WRITE is for.

Shared by the Orders writes (routes/order_purchase_routes.py,
routes/order_ship_routes.py) so they cannot disagree (CLAUDE.md Rule 12).

THE ACCOUNT MUST BE NAMED by the request -- never the server's open account,
which belongs to whichever browser tab switched last (Rule 14). The guard has
already checked the signed-in person may use the account named.

The marketplace is the one asked for if it is one of the account's own, else
the account's default -- the same answer routes/orders_routes._marketplace
gives the rows the Orders page draws, so a record is written under the
marketplace its row carries.
"""


class ScopeError(ValueError):
    """Refused, with a sentence for the screen and an HTTP status."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def account(config, account_id):
    cfg = (config() if callable(config) else config) or {}
    return next((a for a in (cfg.get("accounts") or [])
                 if str(a.get("id") or "") == str(account_id or "")), None)


def marketplace(acc, asked=""):
    """Asked (if the account's own) else the account's default. "" = refused."""
    own = [str(m).strip().upper() for m in ((acc or {}).get("marketplaces") or [])
           if str(m).strip()]
    dflt = str((acc or {}).get("default_marketplace") or "").strip().upper()
    if dflt and dflt not in own:
        own.append(dflt)
    asked = str(asked or "").strip().upper()
    if asked:
        return asked if asked in own else ""
    return dflt or (own[0] if own else "")


def resolve(config, named_account, asked_marketplace, order_id, what):
    """(account dict, marketplace, order id) or raise ScopeError.

    `what` finishes "nothing was ..." in the refusal ("recorded", "sent").
    """
    aid = str(named_account or "").strip()
    oid = str(order_id or "").strip()
    if not aid:
        raise ScopeError("Which account? The request did not name one, so nothing "
                         "was %s. Reload the Orders page and try again." % what)
    acc = account(config, aid)
    if acc is None:
        raise ScopeError("There is no account called %r in this app." % aid, 404)
    mkt = marketplace(acc, asked_marketplace)
    if not mkt:
        raise ScopeError("That marketplace is not one of %s's, so nothing was %s."
                         % (acc.get("label") or aid, what))
    if not oid:
        raise ScopeError("No order number came with the request.")
    return acc, mkt, oid
