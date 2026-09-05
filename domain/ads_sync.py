"""domain/ads_sync.py -- pull Advertising API reports into ads_daily.

WHAT THIS IS
The one writer of the ads_daily table. data/db.py shaped that table in August
for exactly this moment: "Today rows arrive from an uploaded Sponsored Products
report; when the API is connected it fills the SAME table and only `source`
changes." This is that swap. Nothing downstream needed rewriting -- domain/
sales_data.py, domain/contribution.py and the sales screens already read
ads_daily and already say "not connected" when it is empty.

TWO GRAINS, ONE TABLE, NO DOUBLE COUNTING
ads_daily is keyed (workspace_id, marketplace, date, asin) and readers pass the
asin they want:

    asin = '*'      the account-wide total for that day  <- campaign report
    asin = 'B0...'  that one product on that day         <- advertised product

Both are written. They are not added together anywhere: a reader asks for one
grain or the other, which is why the '*' row is a row and not a SUM().

The '*' row comes from the CAMPAIGN report rather than from summing the
per-ASIN rows, because those two are not the same number -- campaign spend
includes clicks that never resolved to an advertised product. Summing the parts
would quietly understate the total.

SPONSORED PRODUCTS ONLY -- SAY SO OUT LOUD
adProduct is SPONSORED_PRODUCTS. Sponsored Brands and Sponsored Display are
separate ad products with their own report types and are NOT in these figures.
If the account runs them, the spend written here is LOWER than the real ad spend
and any ACOS computed from it is flattering. That is a limitation of what is
pulled, not of what is stored, and it is recorded on every row via `source` so a
later Brands/Display pull can be told apart.

NOTHING IS INVENTED
api/amazon_ads.py returns None for a metric Amazon did not send, and None is
written as NULL, never as 0. A day with no spend row and a day with £0 spend are
different claims and only one of them is safe to draw a chart from.

THIS MODULE CANNOT WRITE TO AMAZON. It only calls the read paths of
api/amazon_ads.py, whose POST whitelist refuses anything but /reporting/reports
(CLAUDE.md Rule 8).
"""
import datetime as dt

from api import amazon_ads as _ads
from config import settings as _settings
from data import db as _db

# Which report feeds which grain of ads_daily.
_GRAINS = (
    ("campaign", "*"),              # account-wide day total
    ("advertised_product", None),   # per ASIN per day; None = take it from the row
)


def _today():
    return dt.date.today()


def window(days=30, end=None):
    """The date range to ask for, as Amazon wants it.

    Ends YESTERDAY by default. Today is always partial -- Amazon is still
    counting it -- and storing a partial day as if it were finished makes the
    most recent point on every chart dip for no reason.
    """
    end = end or (_today() - dt.timedelta(days=1))
    start = end - dt.timedelta(days=int(days) - 1)
    return start.isoformat(), end.isoformat()


def _rows_for(creds, marketplace, kind, start, end, wait, on_wait=None):
    """One DAILY report, or an explanation. Never raises."""
    try:
        got = _ads.report(creds, marketplace, kind, start, end,
                          wait=wait, on_wait=on_wait, time_unit="DAILY")
    except Exception as e:
        return {"ok": False, "kind": kind, "rows": [], "error": str(e)[:400]}
    got["kind"] = kind
    got.setdefault("rows", [])
    return got


_METRICS = ("impressions", "clicks", "spend", "orders", "sales")


def _fold(rows, keys):
    """Amazon's rows -> one total per key. THE REPORT GRAIN IS NOT THE TABLE GRAIN.

    Both reports come back finer than ads_daily stores them:

        campaign report            one row per (date, CAMPAIGN)
        advertised product report  one row per (date, CAMPAIGN, asin)

    ads_daily is keyed (date, asin) and has a UNIQUE index on it, so the rows
    have to be added up on the way in. Upserting them one by one instead does
    not error -- it silently keeps whichever campaign happened to be written
    LAST and throws the rest away. Measured on the first real pull: 2,958 report
    rows collapsed to 677 stored, and the biggest per-ASIN spend read as £14.55
    against a true account total of £256.93.

    An ASIN advertised in three campaigns is one ASIN that cost the sum of the
    three, and that is the only reading of it that reconciles with the account
    total.

    Additive metrics only. A key whose every row was None for a metric stays
    None rather than becoming 0 -- see the module docstring.
    """
    out = {}
    for r in rows:
        k = tuple((r.get(f) or "").strip() for f in keys)
        if not all(k):
            continue
        acc = out.setdefault(k, {m: None for m in _METRICS})
        for m in _METRICS:
            v = r.get(m)
            if v is None:
                continue
            acc[m] = v if acc[m] is None else acc[m] + v
    return out


def _upsert(conn, workspace_id, marketplace, date, asin, m, fetched_at):
    conn.execute(
        "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, "
        "impressions, clicks, spend, ad_orders, ad_sales, source, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(workspace_id, marketplace, date, asin) DO UPDATE SET "
        "impressions=excluded.impressions, clicks=excluded.clicks, "
        "spend=excluded.spend, ad_orders=excluded.ad_orders, "
        "ad_sales=excluded.ad_sales, source=excluded.source, "
        "fetched_at=excluded.fetched_at",
        (workspace_id, marketplace, date, asin,
         _int(m.get("impressions")), _int(m.get("clicks")), m.get("spend"),
         _int(m.get("orders")), m.get("sales"), "ads_api", fetched_at))


def _int(v):
    return None if v is None else int(round(v))


def sync(workspace_id, marketplace="UK", days=30, wait=300, config_path=None,
         on_wait=None):
    """Pull both DAILY reports for this account and store them in ads_daily.

    Returns a dict a screen or a log can render directly. Never raises: a failed
    sync has to be able to say WHY, and "not connected" and "connected but the
    report failed" need different answers.
    """
    cfg = _settings.read_raw(config_path) if config_path else _settings.read_raw()
    acc = next((a for a in cfg.get("accounts", [])
                if a.get("id") == workspace_id), None)
    if acc is None:
        return {"ok": False, "error": "No such account: %s" % workspace_id}

    creds = _ads.creds_for(cfg, acc)
    gaps = _ads.missing(creds)
    if gaps:
        return {"ok": False, "connected": False, "missing": gaps,
                "error": "%s is not connected to the Advertising API. Still "
                         "needed: %s" % (workspace_id, ", ".join(gaps))}

    start, end = window(days)
    fetched_at = dt.datetime.now().isoformat(timespec="seconds")
    conn = _db.get_db(config_path)
    out = {"ok": True, "workspace_id": workspace_id, "marketplace": marketplace,
           "profile_id": creds["ads_profile_id"], "start": start, "end": end,
           "written": {}, "errors": [], "ad_product": "SPONSORED_PRODUCTS"}

    for kind, fixed_asin in _GRAINS:
        got = _rows_for(creds, marketplace, kind, start, end, wait, on_wait)
        if not got.get("ok"):
            out["errors"].append({"kind": kind,
                                  "error": got.get("error") or "unknown",
                                  "report_id": got.get("report_id"),
                                  "pending": bool(got.get("pending"))})
            out["ok"] = False
            continue

        rows = got.get("rows") or []
        n = 0
        if fixed_asin == "*":
            for (date,), m in sorted(_fold(rows, ("date",)).items()):
                _upsert(conn, workspace_id, marketplace, date, "*", m,
                        fetched_at)
                n += 1
        else:
            for (date, asin), m in sorted(_fold(rows, ("date", "asin")).items()):
                _upsert(conn, workspace_id, marketplace, date, asin, m,
                        fetched_at)
                n += 1
        out["written"][kind] = {"report_rows": len(rows), "stored": n,
                                "report_id": got.get("report_id")}
    conn.commit()

    # TELL THE APP THE DATA IS THERE. Every ad figure on every screen is gated
    # on data_availability, which is a CACHED row, not a count of this table --
    # so storing rows without this leaves the whole app saying "not connected"
    # while 705 rows of real spend sit in the database. Measured exactly that
    # way on the first live pull.
    from domain import sales_data as _sd
    _sd.refresh_availability(conn, workspace_id, marketplace, "ads")
    out["availability"] = _sd.availability(config_path, workspace_id,
                                           marketplace).get("ads")
    return out
