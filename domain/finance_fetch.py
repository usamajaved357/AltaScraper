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

WHICH LIST (owner, 30 Sep 2026: "do the newer finance list switch")
Finances 2024-06-19 listTransactions, not v0 listFinancialEvents: the old list
leaves out money Amazon is still holding (delivery + 7 days for a new seller)
and shows a released hold on the RELEASE day. The newer list shows it on the
day it happened. finance_transactions.to_events writes each transaction back
into the old event shape, so finance_data and order_finance parse it with
their existing rules (Rule 12) -- see that module for the measurements.
"""
import datetime as _dt
import threading
import time

from domain import finance_data as _fd
from domain import finance_transactions as _ftx

PAGES_PER_PASS = 12          # a pass is bounded so a backfill cannot hang a request
REVISE_DAYS = 7              # funds settle for about a week; re-pull that window
# listTransactions allows 0.5 requests a second (burst 10); v0 allowed a burst
# of 30, so the 1-second pause that suited it would be throttled on a 40-page
# re-read. Two seconds keeps to Amazon's documented rate.
PAUSE = 2
FINANCES_VERSION = "2024-06-19"
# The Finance screen's "Re-read the last 95 days": the same window the
# background refresher asks for, in ONE pass with a bigger page budget, so the
# pull is complete and can clear leftovers of older pulls (see sync()).
RESYNC_DAYS = 95
RESYNC_PAGES = 40


def _client(marketplace, creds):
    from sp_api.api import Finances
    from sp_api.base import Marketplaces
    mkt = getattr(Marketplaces, str(marketplace).upper(), None) or Marketplaces.US
    # The library's own versioned client (python-amazon-sp-api 2.x dispatches
    # version="2024-06-19" to FinancesV20240619). Without a version it returns
    # v0, which is what this used to read.
    return Finances(credentials=creds, marketplace=mkt, version=FINANCES_VERSION)


def _list_page(fc, after, before, token=None):
    """One listTransactions page -> (transactions, nextToken).

    NO marketplaceId: the old list was the whole account's money, filed under
    its home marketplace by sync(); asking for one marketplace here would drop
    the money of every other one the account sells in."""
    kw = {"postedAfter": after, "postedBefore": before}
    if token:
        kw["nextToken"] = token
    resp = fc.list_transactions(**kw)
    pay = _payload(resp)
    # A REPLY WITHOUT A TRANSACTIONS LIST IS AN ERROR, NOT "NO MONEY".
    # The library raises only when the body carries "errors"; a timeout page,
    # an HTML body or {"message": ...} comes back as an ordinary payload. Read
    # as zero transactions with no next page, it would mark the part COMPLETE
    # and clear_unreturned would delete that half-month (review, 30 Sep 2026).
    if not isinstance(pay, dict) or not isinstance(pay.get("transactions"), list):
        keys = sorted(pay)[:6] if isinstance(pay, dict) else type(pay).__name__
        raise RuntimeError("listTransactions returned no transactions list "
                           "(reply keys: %s) -- nothing stored or cleared" % (keys,))
    # Measured 30 Sep 2026: the reply is {"payload": {"transactions": [...]},
    # "statusCode": 200}, so nextToken sits inside the payload. The library
    # also lifts a top-level nextToken into resp.next_token -- read both.
    nxt = pay.get("nextToken") or getattr(resp, "next_token", None)
    return list(pay["transactions"]), nxt


def _payload(resp):
    return resp.payload if hasattr(resp, "payload") else resp


# Amazon's own words, from a live call on 13 Aug 2026:
#   "Date is not valid, should be no later than 2 minutes from now"
# Asking for a range that ends at 23:59:59 today is therefore rejected outright
# for the whole request -- not trimmed, rejected -- so the end of the window is
# clamped to a few minutes ago. Five rather than two, because the clock here and
# the clock at Amazon are not the same clock.
_FUTURE_MARGIN = _dt.timedelta(minutes=5)


def _utcnow():
    """The one clock this module reads (UTC), so _today and _window agree."""
    return _dt.datetime.utcnow()


def _window(start, end):
    """(PostedAfter, PostedBefore) as ISO, with the end clamped out of the future."""
    after = start + "T00:00:00Z"
    before_dt = _dt.datetime.strptime(end + " 23:59:59", "%Y-%m-%d %H:%M:%S")
    latest = _utcnow() - _FUTURE_MARGIN
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
    return _payload(fc.list_transactions(postedAfter=after, postedBefore=before))


def fetch_range(marketplace, creds, start, end, max_pages=PAGES_PER_PASS,
                next_token=None, log=None):
    """Page through the range. Returns (merged_events, next_token, pages).

    Every page's transactions are gathered first and translated ONCE
    (finance_transactions.to_events), so a transaction on two pages is counted
    once and the parser sees the same FinancialEvents shape whether the range
    took one page or twenty. merged_events["info"] says how many held
    transactions were counted and how many releases were skipped.
    """
    fc = _client(marketplace, creds)
    txs, pages, token = [], 0, next_token
    after, before = _window(start, end)

    while pages < int(max_pages):
        got, token = _list_page(fc, after, before, token)
        txs += got
        pages += 1
        if log:
            log("finance page %d (%d transactions)" % (pages, len(got)))
        if not token:
            break
        time.sleep(PAUSE)

    events, info = _ftx.to_events(txs)
    events["info"] = info
    return events, token, pages


def _today():
    """Today in UTC -- the calendar Amazon's PostedDate and _window() use. The
    machine's local date can be a day ahead of UTC just after midnight."""
    return _utcnow().date()


def periods(start, end):
    """[(first, last)] half-months (1st-15th, 16th-end) covering start..end.

    The first is aligned DOWN to its half-month's first day, so no pull ever
    cuts a half-month in two; the last is clamped to `end` (today) and only
    ever grows. See finance_data.place_undated for why that makes the count of
    undated charges exact.
    """
    d = start.replace(day=1 if start.day <= 15 else 16)
    out = []
    while d <= end:
        if d.day == 1:
            last = d.replace(day=15)
        else:
            last = (d.replace(day=28) + _dt.timedelta(days=4)).replace(day=1) \
                - _dt.timedelta(days=1)
        out.append((d, min(last, end)))
        d = last + _dt.timedelta(days=1)
    return out


def _askable(a, b):
    """False when the window cannot be asked for yet: on the 1st or 16th just
    after midnight UTC, the end clamped to "a few minutes ago" falls BEFORE the
    start, and Amazon rejects the whole request."""
    after, before = _window(a, b)
    return before >= after


def _iso(d):
    return d.strftime("%Y-%m-%d")


def _read_days(marketplace, creds, a, b, budget, log):
    """A half-month too busy for one read, DAY BY DAY, newest first.

    -> (day parts, pages, first day NOT stored or None). A day counts only when
    its own paging finished; the first one that does not stops the walk, and
    everything from the half-month's start to it is reported as not stored.
    """
    parts, pages = [], 0
    d = b
    while d >= a:
        if pages >= budget:
            return parts, pages, d
        if _askable(_iso(d), _iso(d)):
            time.sleep(PAUSE)
            ev, tok, n = fetch_range(marketplace, creds, _iso(d), _iso(d),
                                     max_pages=budget - pages, log=log)
            pages += n
            if tok:
                return parts, pages, d
            parts.append({"start": _iso(d), "end": _iso(d), "events": ev,
                          "complete": True, "kind": "day"})
        d -= _dt.timedelta(days=1)
    return parts, pages, None


def _fetch_periods(marketplace, creds, start, end, max_pages, next_token, log):
    """Read the window half-month by half-month, NEWEST FIRST, within one page
    budget. -> (parts, pages, token, not_stored ranges).

    Each part is {start, end, events, complete, kind}: kind "half" is a whole
    half-month, "day" one day of a half-month too busy to read whole. A
    half-month is tried with at most HALF the budget left, so a busy one cannot
    eat the lot; if Amazon has more, it is read again day by day (_read_days),
    and the walk then carries on to older half-months with what remains.
    Only complete parts are stored; the rest is named in not_stored.
    A caller-supplied continuation token is the old single-window pass: one
    INCOMPLETE part, nothing stored from it.
    """
    budget = int(max_pages)
    if next_token:
        ev, tok, pages = fetch_range(marketplace, creds, _iso(start), _iso(end),
                                     max_pages=budget, next_token=next_token, log=log)
        return ([{"start": _iso(start), "end": _iso(end), "events": ev,
                  "complete": False, "kind": "half"}], pages, tok,
                ["%s to %s" % (_iso(start), _iso(end))])
    parts, pages, tok, gaps = [], 0, None, []
    for a, b in reversed(periods(start, end)):
        if not _askable(_iso(a), _iso(b)):
            continue
        if pages >= budget:
            gaps.append("%s to %s" % (_iso(a), _iso(b)))
            continue
        if pages:
            time.sleep(PAUSE)
        share = max(1, (budget - pages) // 2)
        ev, tok, n = fetch_range(marketplace, creds, _iso(a), _iso(b),
                                 max_pages=share, log=log)
        pages += n
        if not tok:
            parts.append({"start": _iso(a), "end": _iso(b), "events": ev,
                          "complete": True, "kind": "half"})
            continue
        days, n, stopped = _read_days(marketplace, creds, a, b, budget - pages, log)
        pages += n
        parts += days
        if stopped is not None:
            gaps.append("%s to %s" % (_iso(a), _iso(stopped)))
    return parts, pages, tok, gaps


def _merge_events(payloads):
    merged = {}
    for pay in payloads:
        for k, v in ((pay or {}).get("FinancialEvents") or {}).items():
            if isinstance(v, list):
                merged.setdefault(k, []).extend(v)
    return {"FinancialEvents": merged}


def _parse_periods(parts, smap, cost, config_path, workspace_id, marketplace):
    """Parse each COMPLETE part on its own (their days do not overlap) and join.
    -> (rows, notes).

    A part Amazon still had pages for is NOT stored: store() replaces a day row
    whole, and a part-read day -- its fees on this page, its refunds on the
    next -- would overwrite a complete one with part of it.

    NO UNDATED CHARGES ANY MORE. The old list sent the monthly subscription
    with no date, hence finance_undated and its half-month counting; the newer
    list dates it (measured 30 Sep 2026: "Subscription", -30.00, posted
    2026-09-19). Anything that did still arrive undated is kept on the part's
    last day and reported in `unattributed` -- never dropped.
    """
    rows, notes = [], {}
    for p in parts:
        if not p["complete"]:
            continue
        r, n = _fd.parse_events(p["events"], smap, cost_lookup=cost,
                                fallback_date=p["end"])
        rows += r
        _merge_notes(notes, n)
        for k, v in ((p["events"] or {}).get("info") or {}).items():
            notes[k] = notes.get(k, 0) + int(v or 0)
    tot, kno = notes.get("units", 0), notes.get("cogs_units", 0)
    notes["cogs_coverage_pct"] = round(kno / tot * 100, 1) if tot else None
    notes["unmapped_skus"] = sorted(notes.get("unmapped_skus", []))[:50]
    notes["unattributed_note"] = " ".join(notes.pop("_und_notes", []))
    return rows, notes


def _merge_notes(into, n):
    for k in ("units", "cogs_units", "unattributed"):
        into[k] = round(into.get(k, 0) + (n.get(k) or 0), 2)
    for k in ("unknown_fee_types", "other_event_lists", "unmapped_skus"):
        into[k] = sorted(set(into.get(k, [])) | set(n.get(k) or []))
    into["unmapped_sku_count"] = len(into.get("unmapped_skus", []))
    if n.get("unattributed_note"):
        into.setdefault("_und_notes", []).append(n["unattributed_note"])


def sync(config_path, workspace_id, marketplace, creds, account_id=None,
         days_back=30, max_pages=PAGES_PER_PASS, next_token=None, log=None,
         cogs_overrides=None):
    """Pull fees and refunds for a window. Never raises.

    Runs on a timer as well as a button, and a scheduled job that throws kills
    its thread and then never runs again with nothing on screen to say so.
    """
    # ONE ACCOUNT'S FINANCES ARE PULLED ONCE, NOT ONCE PER MARKETPLACE.
    #
    # Amazon's Finances API is not segmented by marketplace: listFinancialEvents
    # took no marketplace, and listTransactions is asked for none (_list_page),
    # so it returns everything the seller has settled. The
    # refresher walks (account, marketplace) pairs, so this ran once for each of
    # the account's marketplaces and stored the SAME events again under each.
    #
    # Measured: every one of the 81 settled orders was held twice, and both
    # finance_daily and order_fees carried identical totals under two
    # marketplaces -- jack_uk 402.39 under UK and 402.39 again under FR,
    # selvora_limited 1909.11 under UK and under FR, nestwell_goods 344.90
    # under UK and under IT. The sales side is genuinely per-marketplace, so
    # opening one of those other marketplaces showed the account's whole fee
    # bill against no sales at all.
    #
    # It also spent a Finances call per marketplace -- ten or eleven per account
    # per rotation -- on quota the sales figures were queueing behind.
    #
    # Stored against the account's DEFAULT marketplace, which is where its
    # trade is. Amazon has not told us how to split these between marketplaces
    # and this does not guess: it keeps them in one place rather than copying
    # them into several.
    #
    # IF THAT MARKETPLACE CANNOT BE READ, NOTHING IS PULLED. This used to read
    # it through load_settings(), which refuses to load when an unrelated key is
    # missing; the failure was swallowed and the pull stored the account's money
    # under whatever marketplace it had been asked about. On 28 Sep 2026 that
    # filed nestwell_goods' refunds, fees and ad invoices under IT, and the UK
    # Finance page stopped at 7 Sep. A refused pull is visible and harmless;
    # money under a guessed marketplace looks exactly like real money.
    from domain import accounts as _accounts
    _default, _why = _accounts.home_marketplace(config_path,
                                                account_id or workspace_id)
    if not _default:
        return {"ok": False, "refused": True, "rows": 0, "order_fee_rows": 0,
                "error": ("Finances not pulled: could not tell which marketplace "
                          "this account's money is kept under (%s). Nothing was "
                          "stored, rather than filing it under %s by guess. Set "
                          "the account's default marketplace and sync again."
                          % (_why, str(marketplace or "?").upper()))}
    if str(marketplace or "").strip().upper() != _default:
        return {"ok": True, "skipped": True, "rows": 0, "order_fee_rows": 0,
                "note": ("This account's finances are kept under %s, its default "
                         "marketplace. Amazon reports them for the whole account "
                         "rather than per marketplace, so pulling them again here "
                         "would store a second copy of the same money."
                         % _default)}

    # ONE PULL OF AN ACCOUNT AT A TIME. The refresher, Sales Sync and the
    # Re-read job can overlap, and a pull that deletes what it did not return
    # must not run beside one that has read but not yet stored (review, 30 Sep
    # 2026). A pull that cannot get the account within LOCK_WAIT stores nothing.
    lock = _account_lock(account_id or workspace_id)
    if not lock.acquire(timeout=LOCK_WAIT):
        return {"ok": False, "busy": True, "rows": 0, "order_fee_rows": 0,
                "error": ("Finances not pulled: another finance pull of this "
                          "account is still running. Nothing was changed; try "
                          "again when it finishes.")}
    try:
        return _pull(config_path, workspace_id, marketplace, creds, account_id,
                     days_back, max_pages, next_token, log, cogs_overrides)
    finally:
        lock.release()


LOCK_WAIT = 180              # seconds; a 95-day re-read takes about two minutes
_LOCKS = {}  # arch-ok: module-mutable-global -- per-account pull locks must be process-wide; guarded by _LOCKS_GUARD
_LOCKS_GUARD = threading.Lock()


def _account_lock(account):
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(str(account or ""), threading.Lock())


def _pull(config_path, workspace_id, marketplace, creds, account_id, days_back,
          max_pages, next_token, log, cogs_overrides):
    """sync()'s read + store + clear, run under the account's lock."""
    end = _today()
    start = end - _dt.timedelta(days=int(days_back))
    try:
        parts, pages, token, gaps = _fetch_periods(marketplace, creds, start, end,
                                                   max_pages, next_token, log)
    except Exception as ex:
        return {"ok": False, "error": "Finances API: %s" % str(ex)[:200]}
    # The window actually read: aligned DOWN to a half-month boundary.
    s = min(p["start"] for p in parts) if parts else start.strftime("%Y-%m-%d")
    e = end.strftime("%Y-%m-%d")
    # Only what was read whole goes anywhere (see _parse_periods).
    events = _merge_events(p["events"] for p in parts if p["complete"])

    smap = _fd.sku_map(config_path, account_id or workspace_id, marketplace)
    _aid = account_id or workspace_id

    # A COST TYPED AGAINST ONE ORDER WINS HERE TOO, as it does everywhere else.
    #
    # This used cogs.lookup -- the product cost and nothing above it -- so an
    # order the owner had corrected by hand kept its corrected profit on the
    # Orders screen and lost it in the Sales daily figures, the same order
    # reporting two different numbers with nothing to say which was right.
    #
    #     "yes make the finance path honour per-order costs too same logic
    #      should exist as for sales bar we prioritize per order costs"
    #
    # order_cogs.line_cost_fn is the resolver the Orders screen already uses,
    # asked here in the same words (Rule 12). NOT filtered by marketplace: these
    # rows are stored under the account's DEFAULT marketplace while an order
    # line carries the one it sold in, and filtering would find no cost at all.
    # Every frozen cost for the account is loaded ONCE rather than per line.
    from domain import order_cogs as _oc
    try:
        _cost = _oc.line_cost_fn(config_path, _aid, None,
                                 overrides=cogs_overrides)
    except Exception:
        # Never lose a finance pull over the cost side of it. The fees are the
        # thing being fetched; falling back to product costs is the behaviour
        # this had before, which is a smaller loss than no pull at all.
        from domain import cogs as _cogs
        _cost = _cogs.lookup(cogs_overrides, _aid)

    rows, notes = _parse_periods(parts, smap, _cost, config_path,
                                 workspace_id, marketplace)
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
    order_keys = None
    try:
        from domain import order_finance as _of
        by_order, _skipped = _of.parse_by_order(events)
        out_of = _of.store(config_path, workspace_id, marketplace, by_order)
        order_keys = {(r["order_id"], r["posted_date"]) for r in by_order}
    except Exception as ex:
        by_order, _skipped, out_of = [], 0, 0
        notes = dict(notes or {})
        notes["order_fees_error"] = str(ex)[:200]

    # A PART READ WHOLE IS AMAZON'S WHOLE ANSWER FOR IT, so whatever an older
    # pull stored there and this one did not return is gone: an undated charge
    # an old pull filed on its own last day (and its finance_undated
    # placement), or -- after the switch to the newer list -- a held sale or
    # refund the old list showed on its RELEASE day, now counted on the day it
    # happened. Left in place, those would be counted twice.
    #
    # TWO RAILS (review, 30 Sep 2026). A read that returned NO transactions at
    # all for a part that already holds rows deletes nothing -- that is far
    # likelier a bad reply than a half-month with no money -- and is reported.
    # With no SKU map, product rows are left alone: this read could not have
    # written any, so their absence says nothing.
    removed, not_cleared = [], []
    day_keys = {(r["date"], r.get("asin") or "*") for r in rows}
    for p in parts:
        if not p["complete"]:
            continue
        n_tx = ((p["events"] or {}).get("info") or {}).get("transactions")
        if n_tx == 0 and _fd.has_rows(config_path, workspace_id, marketplace,
                                      p["start"], p["end"]):
            not_cleared.append("%s to %s" % (p["start"], p["end"]))
            continue
        removed += _fd.clear_unreturned(
            config_path, workspace_id, marketplace, p["start"], p["end"],
            day_keys, order_keys, products=bool(smap))
    notes["stale_days_removed"] = sorted(set(removed))
    if not_cleared:
        notes["empty_reads_not_cleared"] = not_cleared
        notes["empty_reads_note"] = (
            "Amazon returned no transactions at all for %s, where the app already "
            "holds figures -- nothing was deleted there. Re-read later to confirm."
            % "; ".join(not_cleared))

    out = {"ok": True, "pages": pages, "rows": written, "days": len({r["date"] for r in rows}),
           "start": s, "end": e,
           "more": bool(gaps),
           "next_token": token, "periods_not_stored": gaps,
           "order_fee_rows": out_of,
           "events_with_no_order": _skipped,
           "sku_map_size": len(smap)}
    # A PULL THAT LEFT DAYS UNREAD IS A PROBLEM TO SAY, not ok-and-quiet: on a
    # busy account every sync could leave the same days behind. The Sales toast
    # and the refresher both print this sentence (review, 30 Sep 2026).
    if gaps:
        out["not_updated"] = (
            "Fees and refunds NOT updated for %s: Amazon had more pages than one "
            "sync reads -- use Finance > Re-read 95 days." % "; ".join(gaps))
    out.update(notes)
    if not smap:
        out["note"] = ("No catalogue snapshot for this account, so fees could not be "
                       "attributed to products. The account totals are still correct. "
                       "Sync the live catalogue to break them down per ASIN.")
    return out
