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
    from data import db as _db
    conn = _db.get_db(config_path)
    return {r["date"] for r in conn.execute(
        "SELECT DISTINCT date FROM sales_daily WHERE workspace_id=? AND marketplace=? "
        "AND date>=? AND date<=? AND asin='*'",
        (workspace_id, marketplace, start, end)).fetchall()}


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
