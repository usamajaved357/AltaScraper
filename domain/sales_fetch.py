"""domain/sales_fetch.py -- ask Amazon for sales, one day at a time.

WHY ONE DAY AT A TIME
GET_SALES_AND_TRAFFIC_REPORT will happily cover a range, but its per-ASIN block
carries no date when it does -- Amazon aggregates the whole range into one figure
per ASIN. A dashboard that needs "this ASIN, on this day" therefore has to ask
per day. The account TOTAL block does carry dates, so a range request is still
the cheap way to backfill the headline numbers.

So: a range request for the totals, and per-day requests for the ASIN
breakdown, done only for days that are missing. Backfilling ninety days is
ninety calls, which is why it is paced and resumable rather than done in one go.

AMAZON'S LAG
Today never exists. Yesterday is often partial and gets revised for a day or two
after. So recent days are deliberately re-fetched rather than trusted once, and
the request window stops at yesterday.
"""
import datetime as _dt
import time

from api import sp_reports as _rep
from domain import sales_data as _sd

# Days per pass when backfilling. Each is one report, and Amazon builds them
# slowly, so a pass takes a budget and the next one continues.
BACKFILL_PER_PASS = 7
# How many recent days to re-fetch even when we already have them, because
# Amazon revises them.
REVISE_DAYS = 3
PAUSE = 2


def _d(s):
    return _dt.datetime.strptime(s, "%Y-%m-%d").date()


def _s(d):
    return d.strftime("%Y-%m-%d")


def yesterday():
    return _dt.date.today() - _dt.timedelta(days=1)


def _held(config_path, workspace_id, marketplace, start, end):
    """Days the REPORT has actually delivered. A row existing is not enough.

    THE FAULT THIS FIXES. live_reconcile writes a sales_daily row for every day
    it covers, from the order feed. Those rows carry sales, orders and units --
    and no traffic at all, because the order feed does not know about traffic.

    This asked only "is there a row for that day", so every one of those days
    counted as fetched and the report was never asked for it. The result:
    sessions, page views, conversion and buy-box were permanently blank on
    exactly the days the order feed had touched first. Measured on jack_uk:
    9-13 and 15 July have sales and NO traffic, while the days either side of
    them have both. Reported as "the views and traffic data on p&l heatmap dont
    seems to be accurate" -- they were not inaccurate, they were absent.

    The test is any column ONLY THE REPORT FILLS IN. A day Amazon reported as
    having no visitors comes back as 0, which is a delivered figure and counts;
    a day never asked about is NULL in all of them and does not.

    Three of them rather than one, so a day is never re-fetched for ever if
    Amazon leaves one out: sessions and page views are the traffic block, and
    order_items is the sales block's own count of items, which the order feed
    does not write either.
    """
    from data import db as _db
    conn = _db.get_db(config_path)
    return {r["date"] for r in conn.execute(
        "SELECT DISTINCT date FROM sales_daily WHERE workspace_id=? AND marketplace=? "
        "AND date>=? AND date<=? AND asin='*' AND ("
        "  sessions IS NOT NULL OR page_views IS NOT NULL OR order_items IS NOT NULL)",
        (workspace_id, marketplace, start, end)).fetchall()}


def first_trade(config_path, workspace_id, marketplace):
    """The earliest order this app has for a pair, or None.

    THE FLOOR FOR ANY BACKFILL. Chasing report days from before an account was
    trading spends the scarce report quota -- roughly one request a minute -- to
    be told a zero we could already infer. These accounts are registered across
    eleven European marketplaces and trade in one, so a flat "go back 90 days"
    would mean about three thousand requests, nearly all of them for days that
    never had a customer. The refresher would then do nothing else, for hours.

    Bounded by trade instead: fetch every day since the account's first order,
    and nothing before it. That covers the whole period there is anything to
    know about, and grows by itself as the account keeps selling.
    """
    from data import db as _db
    try:
        r = _db.get_db(config_path).execute(
            "SELECT MIN(substr(purchase_date,1,10)) FROM order_lines "
            "WHERE workspace_id=? AND marketplace=?",
            (workspace_id, marketplace)).fetchone()
        return r[0] if r and r[0] else None
    except Exception:
        return None


# How far back to look at a marketplace that has never taken an order. Short on
# purpose: it exists only so that a FIRST sale somewhere new is still noticed.
UNTRADED_DAYS_BACK = 30


def _floor(config_path, workspace_id, marketplace, start, end):
    """`start`, moved forward to the first day this pair ever traded.

    A pair with NO order history keeps the short window it always had. Without
    that it would inherit the long one, and the long one exists for the opposite
    reason -- to cover an account's full trading history. Measured with it
    missing: eleven European marketplaces per account, each asking for 82 days
    of report about a country that has never had a customer, which is roughly
    three thousand requests at about one a minute.
    """
    edge = first_trade(config_path, workspace_id, marketplace)
    if not edge:
        return max(start, end - _dt.timedelta(days=UNTRADED_DAYS_BACK - 1))
    try:
        e = _d(edge)
    except Exception:
        return start
    return max(start, e)


def missing_days(config_path, workspace_id, marketplace, days_back=30):
    """Dates in the window we genuinely do not hold, newest first.

    Newest first on purpose: if a backfill is interrupted, what survives is the
    recent data someone is actually looking at, not the oldest.

    Days due for REVISION are deliberately not counted here. They used to be, and
    because the last few days are always due for revision the count never fell
    below three -- so a fully synced account was told for ever that it had days
    left to fetch, and pressing Sync never cleared it. A backlog that cannot
    reach zero is not a backlog, it is a nag.
    """
    end = yesterday()
    start = end - _dt.timedelta(days=int(days_back) - 1)
    # Never before the account's first order -- see first_trade().
    start = _floor(config_path, workspace_id, marketplace, start, end)
    if start > end:
        return []
    have = _held(config_path, workspace_id, marketplace, _s(start), _s(end))
    out = []
    d = end
    while d >= start:
        if _s(d) not in have:
            out.append(_s(d))
        d -= _dt.timedelta(days=1)
    return out


def revisable_days(config_path, workspace_id, marketplace, days_back=30):
    """Recent days we DO hold but should re-ask for, newest first.

    Amazon revises the last few days as returns and cancellations settle, so a
    number read once and kept is a number Amazon itself no longer agrees with.
    """
    end = yesterday()
    start = end - _dt.timedelta(days=int(days_back) - 1)
    start = _floor(config_path, workspace_id, marketplace, start, end)
    have = _held(config_path, workspace_id, marketplace, _s(start), _s(end))
    out = []
    for i in range(REVISE_DAYS):
        d = end - _dt.timedelta(days=i)
        if d >= start and _s(d) in have:
            out.append(_s(d))
    return out


def fetch_day(rc, marketplace_id, date_str):
    """One day, with the per-ASIN breakdown. Returns rows for sales_daily."""
    doc, _src, _built = _rep.fetch_json(
        rc, _sd.REPORT_TYPE,
        marketplace_ids=[marketplace_id] if marketplace_id else None,
        options={"dateGranularity": "DAY", "asinGranularity": "CHILD"},
        start_time=date_str + "T00:00:00Z",
        end_time=date_str + "T23:59:59Z",
        # Never reuse: two different days are two different reports of the same
        # TYPE, and reuse matches on type. Reusing here would hand back another
        # day's numbers filed under this date -- silently, and wrongly.
        allow_reuse=False)
    if isinstance(doc, dict):
        doc["_date"] = date_str
    return _sd.parse_report(doc)


def sync(config_path, workspace_id, marketplace, marketplace_id, creds,
         days_back=30, budget=BACKFILL_PER_PASS, log=None):
    """Fetch what is missing, up to a budget. Returns a short report.

    Never raises: this runs on a timer, and a scheduled job that throws kills its
    thread and stops running for ever with nothing on screen to say so.
    """
    try:
        from sp_api.api import Reports
        from sp_api.base import Marketplaces
        mkt_enum = getattr(Marketplaces, str(marketplace).upper(), None) or Marketplaces.US
        rc = Reports(credentials=creds, marketplace=mkt_enum)
    except Exception as e:
        return {"ok": False, "error": "could not open SP-API Reports: %s" % str(e)[:160]}

    # Missing days first -- a day with no data at all matters more than refining a
    # day that already has some. Revisions use whatever budget is left over.
    todo = missing_days(config_path, workspace_id, marketplace, days_back)[:int(budget)]
    spare = int(budget) - len(todo)
    if spare > 0:
        todo += revisable_days(config_path, workspace_id, marketplace, days_back)[:spare]
    if not todo:
        return {"ok": True, "fetched": 0, "rows": 0, "failed": [],
                "still_missing": 0, "note": "already up to date",
                **_sd.availability(config_path, workspace_id, marketplace)["sales"]}

    written = 0
    failed = []
    for ds in todo:
        try:
            rows = fetch_day(rc, marketplace_id, ds)
            written += _sd.store(config_path, workspace_id, marketplace, rows)
            if log:
                log("sales %s %s %s -> %d rows" % (workspace_id, marketplace, ds, len(rows)))
        except _rep.ReportError as e:
            # A day with no sales legitimately produces CANCELLED. Recording it as
            # a failure would make an ordinary quiet day look like a fault.
            failed.append({"date": ds, "error": str(e)[:140]})
        except Exception as e:
            failed.append({"date": ds, "error": str(e)[:140]})
        time.sleep(PAUSE)

    left = max(0, len(missing_days(config_path, workspace_id, marketplace, days_back)))
    return {"ok": True, "fetched": len(todo) - len(failed), "rows": written,
            "failed": failed, "still_missing": left}
