"""domain/refund_capability.py -- can this account refund a buyer from here?

MEASURED, 6 SEP 2026: NO.

Amazon publishes no refund endpoint. A seller-initiated refund is a FEEDS
submission -- a POST_PAYMENT_ADJUSTMENT_DATA document -- and the Feeds API is
gated behind a role of its own. Asked directly, with a read-only get_feeds call
that sends nothing and moves no money:

    nestwell_goods   UK   Unauthorized -- "Access to the resource is forbidden"
    selvora_limited  UK   Unauthorized -- "Access to requested resource is denied."
    jack_uk          UK   Unauthorized -- "Access to requested resource is denied."

So a Refund button on the returns screen could not work on any account in this
app, however it were written. Drawing one anyway would be worse than not having
it: a control that always fails teaches somebody the app is broken, and the real
answer -- go to Seller Central, or grant the role -- is nowhere on the screen.

WHY THIS IS A MODULE AND NOT A CONSTANT. The role can be granted; the owner may
do it this afternoon. So the answer is asked of Amazon rather than hard-coded,
cached for the process because a role does not change between two clicks, and
re-asked on demand. The day it is granted, this starts saying yes on its own.

NOTHING HERE REFUNDS ANYTHING. It only reports whether refunding would be
possible. Money moving is not a thing this app should learn to do quietly, and
if it ever does it will be a separate, explicitly confirmed piece of work.
"""
import time

# {(workspace_id, marketplace): (checked_at, dict)}
_CACHE = {}
_TTL = 15 * 60          # a role does not change between two clicks

GRANTED = "granted"
DENIED = "denied"
UNKNOWN = "unknown"


def _probe(cfg, account, marketplace):
    """Ask Amazon whether the Feeds role is held. READ ONLY.

    get_feeds LISTS feeds already submitted. It creates nothing, uploads
    nothing, and 403s when the role is absent -- which is the entire question.
    Deliberately not createFeedDocument: that is the first step of a real
    submission and asking with it would be indistinguishable from starting one.
    """
    try:
        import accounts as _acc
        from sp_api.api import FeedsV20210630 as _Feeds
        from sp_api.base import Marketplaces
    except Exception as e:
        return UNKNOWN, "The Amazon client could not be loaded (%s)." % str(e)[:120]

    mkt = str(marketplace or account.get("default_marketplace") or "UK").upper()
    try:
        f = _Feeds(credentials=_acc.account_creds(account),
                   marketplace=getattr(Marketplaces, mkt, Marketplaces.UK))
        f.get_feeds(feedTypes=["POST_PRODUCT_DATA"], pageSize=1)
        return GRANTED, ""
    except Exception as e:
        msg = str(e)
        low = msg.lower()
        if "unauthorized" in low or "forbidden" in low or "denied" in low:
            return DENIED, msg[:200]
        # A TIMEOUT IS NOT A REFUSAL. Reporting "not allowed" because the
        # network hiccuped would send somebody to request a role they have.
        return UNKNOWN, msg[:200]


def check(cfg, account, marketplace, force=False):
    """-> {state, can_refund, headline, detail, what_to_do}. Never raises."""
    key = (str((account or {}).get("id") or ""), str(marketplace or "").upper())
    now = time.time()
    if not force:
        hit = _CACHE.get(key)
        if hit and (now - hit[0]) < _TTL:
            return hit[1]

    state, why = _probe(cfg, account or {}, marketplace)

    if state == GRANTED:
        out = {
            "state": state, "can_refund": False,
            "headline": "Refunding from here is not built yet.",
            "detail": ("This account DOES hold the Feeds role, which is what a "
                       "seller-initiated refund needs — so it is now possible. "
                       "It is deliberately not wired up: a refund moves real "
                       "money and cannot be undone, so it is its own piece of "
                       "work with its own confirmation, not something added "
                       "quietly alongside a returns list."),
            "what_to_do": ("Issue it in Seller Central for now. Say the word and "
                           "the button can be built."),
        }
    elif state == DENIED:
        out = {
            "state": state, "can_refund": False,
            "headline": "This account cannot refund through the API at all.",
            "detail": ("Amazon publishes no refund endpoint. A seller-initiated "
                       "refund is a Feeds submission, and Amazon refuses this "
                       "account's Feeds calls outright: %s. A Refund button "
                       "here would fail every time it was pressed." % why),
            "what_to_do": ("Refund in Seller Central, or grant this app's SP-API "
                           "application the Feeds role in Seller Central → Apps "
                           "& Services → Manage Your Apps, and press check "
                           "again."),
        }
    else:
        out = {
            "state": state, "can_refund": False,
            "headline": "Could not tell whether refunding is possible.",
            "detail": ("Amazon did not answer clearly: %s. That is not the same "
                       "as being refused — it is usually a timeout." % why),
            "what_to_do": "Try again shortly.",
        }

    _CACHE[key] = (now, out)
    return out
