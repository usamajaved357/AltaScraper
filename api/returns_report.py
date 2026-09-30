"""api/returns_report.py -- ask Amazon for the seller-fulfilled returns report.

Outside-API call only (CLAUDE.md Rule 7). Moved unchanged from
routes/returns_routes.py's _fetch (30 Sep 2026); domain/returns_sync.py is the
caller for both the "Pull from Amazon" button and the daily job.
"""
import datetime as _dt

# Amazon refuses a wider window on this report -- measured: 90 days comes back
# FATAL, 60 works.
MAX_DAYS = 60

EMPTY = "__EMPTY__"


def fetch(creds, mkt, marketplace_id, days):
    """The seller-fulfilled returns report. -> (text, "", error).

    On success the error is "" and the first item is the report TEXT;
    domain/returns_sync.fetch splits it. `creds` and `marketplace_id` may be
    callables (api/ may not import domain/): they are then asked at exactly the
    points the original button asked, so a failure keeps its original wording
    -- credentials inside the client build, the marketplace id inside the
    report request."""
    try:
        from sp_api.api import Reports
        from sp_api.base import Marketplaces
    except Exception as e:
        return [], [], "SP-API Reports is unavailable: %s" % str(e)[:120]
    enum = getattr(Marketplaces, str(mkt).upper(), Marketplaces.UK)
    # BUILDING THE CLIENT CAN FAIL, and it was the one call here not guarded.
    # sp_api validates credentials in the constructor and raises
    # MissingCredentials, which escaped as an HTTP 500 with a raw exception
    # string -- on a screen whose whole design is to answer with no data and a
    # reason rather than an error page. Measured on miles_lubricants: "server
    # error: Credentials are missing: lwa_app_id, lwa_client_secret".
    try:
        rc = Reports(credentials=(creds() if callable(creds) else creds),
                     marketplace=enum)
    except Exception as e:
        return [], [], ("This account's Amazon credentials are incomplete, so "
                        "the returns report cannot be requested: %s"
                        % str(e)[:160])
    now = _dt.datetime.now(_dt.timezone.utc)
    start = now - _dt.timedelta(days=days)
    iso = lambda d: d.isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        cr = rc.create_report(
            reportType="GET_FLAT_FILE_RETURNS_DATA_BY_RETURN_DATE",
            dataStartTime=iso(start), dataEndTime=iso(now),
            marketplaceIds=[marketplace_id() if callable(marketplace_id)
                            else marketplace_id])
        rid = (cr.payload if hasattr(cr, "payload") else cr)["reportId"]
    except Exception as e:
        return [], [], "Amazon refused the report request: %s" % str(e)[:200]

    import time as _t
    doc = None
    for _ in range(24):
        _t.sleep(5)
        try:
            g = rc.get_report(rid)
            p = g.payload if hasattr(g, "payload") else g
            st = p.get("processingStatus")
        except Exception as e:
            return [], [], "Could not read the report back: %s" % str(e)[:160]
        if st == "DONE":
            doc = p.get("reportDocumentId")
            break
        if st in ("CANCELLED", "FATAL"):
            # CANCELLED means Amazon had nothing to give, which is not an
            # error and must not read as one.
            return [], [], (EMPTY if st == "CANCELLED" else
                            "Amazon could not build the report (FATAL) — "
                            "usually the window is too wide; this one is "
                            "limited to %d days." % MAX_DAYS)
    if not doc:
        return [], [], ("Amazon is still building the report. Try again in "
                        "a minute — they can be slow.")
    try:
        d = rc.get_report_document(doc, download=True)
        body = (d.payload if hasattr(d, "payload") else d) or {}
        text = str(body.get("document") or "")
    except Exception as e:
        return [], [], "Could not download the report: %s" % str(e)[:160]
    return text, None, ""


