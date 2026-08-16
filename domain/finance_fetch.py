"""domain/finance_fetch.py -- pull financial events from Amazon.

WHY THIS IS NOT SHAPED LIKE sales_fetch
Sales come from a REPORT: ask, wait, download a document per day. Finances is a
paged LIST endpoint -- one call returns some events and a NextToken for the rest,
and a busy month can be many pages. So this pages rather than looping over days,
and takes a page budget so a big backfill runs across several passes instead of
holding a request open for minutes.

POSTED DATE, NOT ORDER DATE
Amazon returns these by when the money moved. A sale on the 1st refunded on the
9th appears twice, in two different days, and that is correct -- it is what a
refund IS. It also means a finance pull for a range can legitimately alter days
you already hold, so re-pulling replaces rather than skips.

THE LAST FEW DAYS ARE INCOMPLETE
Funds settle over days. The most recent day always looks light and fills in
later, which is why recent days are re-pulled rather than trusted once.
"""
import datetime as _dt
import time

from domain import finance_data as _fd

PAGES_PER_PASS = 12          # a pass is bounded so a backfill cannot hang a request
REVISE_DAYS = 7              # funds settle for about a week; re-pull that window
PAUSE = 1                    # Finances is rate limited; be a good citizen


def _client(marketplace, creds):
    from sp_api.api import Finances
    from sp_api.base import Marketplaces
    mkt = getattr(Marketplaces, str(marketplace).upper(), None) or Marketplaces.US
    return Finances(credentials=creds, marketplace=mkt)


def _payload(resp):
    return resp.payload if hasattr(resp, "payload") else resp


# Amazon's own words, from a live call on 13 Aug 2026:
#   "Date is not valid, should be no later than 2 minutes from now"
# Asking for a range that ends at 23:59:59 today is therefore rejected outright
# for the whole request -- not trimmed, rejected -- so the end of the window is
# clamped to a few minutes ago. Five rather than two, because the clock here and
# the clock at Amazon are not the same clock.
_FUTURE_MARGIN = _dt.timedelta(minutes=5)


def _window(start, end):
    """(PostedAfter, PostedBefore) as ISO, with the end clamped out of the future."""
    after = start + "T00:00:00Z"
    before_dt = _dt.datetime.strptime(end + " 23:59:59", "%Y-%m-%d %H:%M:%S")
    latest = _dt.datetime.utcnow() - _FUTURE_MARGIN
    if before_dt > latest:
        before_dt = latest
    return after, before_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def raw_sample(marketplace, creds, start, end):
    """ONE page, verbatim, for confirming Amazon's actual field names.

    CLAUDE.md Rule 4: the parser in finance_data.py is written to the documented
    shape, and documented is not the same as observed. This returns exactly what
    Amazon sent so the shape can be read rather than assumed, once, on the first
    live run. It is a diagnostic, not part of the sync path.
    """
    fc = _client(marketplace, creds)
    after, before = _window(start, end)
    resp = fc.list_financial_events(PostedAfter=after, PostedBefore=before)
    return _payload(resp)


def fetch_range(marketplace, creds, start, end, max_pages=PAGES_PER_PASS,
                next_token=None, log=None):
    """Page through the range. Returns (merged_events, next_token, pages).

    The pages are merged into one FinancialEvents shape before parsing, so the
    parser sees the same structure whether the range took one page or twenty and
    there is only one code path to be right.
    """
    fc = _client(marketplace, creds)
    merged, pages, token = {}, 0, next_token
    after, before = _window(start, end)

    while pages < int(max_pages):
        if token:
            resp = fc.list_financial_events(NextToken=token)
        else:
            resp = fc.list_financial_events(PostedAfter=after, PostedBefore=before)
        pay = _payload(resp) or {}
        ev = (pay.get("FinancialEvents") or {}) if isinstance(pay, dict) else {}
        for k, v in ev.items():
            if isinstance(v, list):
                merged.setdefault(k, []).extend(v)
        pages += 1
        token = pay.get("NextToken") if isinstance(pay, dict) else None
        if log:
            log("finance page %d (%d event lists)" % (pages, len(ev)))
        if not token:
            break
        time.sleep(PAUSE)

    return {"FinancialEvents": merged}, token, pages


def sync(config_path, workspace_id, marketplace, creds, account_id=None,
         days_back=30, max_pages=PAGES_PER_PASS, next_token=None, log=None,
         cogs_overrides=None):
    """Pull fees and refunds for a window. Never raises.

    Runs on a timer as well as a button, and a scheduled job that throws kills
    its thread and then never runs again with nothing on screen to say so.
    """
    end = _dt.date.today()
    start = end - _dt.timedelta(days=int(days_back))
    s, e = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    try:
        events, token, pages = fetch_range(marketplace, creds, s, e,
                                           max_pages=max_pages,
                                           next_token=next_token, log=log)
    except Exception as ex:
        return {"ok": False, "error": "Finances API: %s" % str(ex)[:200]}

    smap = _fd.sku_map(config_path, account_id or workspace_id, marketplace)
    from domain import cogs as _cogs
    # Undated charges land on the last day of the window rather than being lost.
    rows, notes = _fd.parse_events(
        events, smap, fallback_date=e,
        cost_lookup=_cogs.lookup(cogs_overrides, account_id or workspace_id))
    written = _fd.store(config_path, workspace_id, marketplace, rows)

    # THE SAME EVENTS, KEPT AGAINST THEIR ORDERS.
    #
    # finance_daily answers "what money moved this week". It cannot answer "what
    # did the orders I took on Tuesday earn", because Tuesday's fee arrives
    # whenever Amazon settles it. Amazon names the order on every shipment and
    # refund event, so keeping that id lets each fee be reported on the day its
    # order was PLACED -- which is the day its sale is already reported on, and
    # the whole reason the P&L grid had two calendars in one column.
    #
    # Best effort and never fatal: the money-basis rows above are already stored,
    # and losing the order-basis copy must not lose them too.
    try:
        from domain import order_finance as _of
        by_order, _skipped = _of.parse_by_order(events)
        out_of = _of.store(config_path, workspace_id, marketplace, by_order)
    except Exception as ex:
        by_order, _skipped, out_of = [], 0, 0
        notes = dict(notes or {})
        notes["order_fees_error"] = str(ex)[:200]

    out = {"ok": True, "pages": pages, "rows": written, "days": len({r["date"] for r in rows}),
           "start": s, "end": e, "more": bool(token), "next_token": token,
           "order_fee_rows": out_of,
           "events_with_no_order": _skipped,
           "sku_map_size": len(smap)}
    out.update(notes)
    if not smap:
        out["note"] = ("No catalogue snapshot for this account, so fees could not be "
                       "attributed to products. The account totals are still correct. "
                       "Sync the live catalogue to break them down per ASIN.")
    return out
