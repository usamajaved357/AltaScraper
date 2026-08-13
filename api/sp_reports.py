"""api/sp_reports.py -- ask Amazon for a report, wait for it, download it.

WHY THIS IS ITS OWN MODULE
Every Amazon report follows the same four steps: reuse a recent one if there is
one, otherwise create, then poll until Amazon finishes building it, then download
and decompress the document. That sequence lived inline in live_routes.py, tuned
over several bugs -- the reuse window, the explicit newest-first sort, the three
different shapes the download can come back in.

The Sales dashboard needs the identical sequence for a different report type. A
second copy would have been the same code with the same hard-won details, and it
would have drifted the first time Amazon changed a response shape (Rule 12).

WHAT IT DOES NOT DO
It does not parse. Each report has its own format -- flat file, JSON, tab
separated -- and parsing belongs with the thing that understands the columns.
This hands back text or JSON and stops.
"""
import datetime as _dt
import gzip
import json
import time
import urllib.request

# How old a finished report may be before we ask Amazon to build a fresh one.
# getReports defaults createdSince to 90 DAYS and documents NO sort order, so
# without a bound and an explicit sort this can hand back a report built weeks
# ago and present it as current. That was a real bug; the bound is not optional.
REUSE_MAX_AGE = 30 * 60

POLL_ATTEMPTS = 60          # ~4 minutes: large catalogues genuinely take that long
POLL_FAST = 2               # seconds between the first ten polls
POLL_SLOW = 4               # and after that


class ReportError(Exception):
    """Raised with a message meant to be shown to a person."""


def _payload(resp):
    return resp.payload if hasattr(resp, "payload") else resp


def find_recent(rc, report_type, marketplace_ids=None, max_age=REUSE_MAX_AGE):
    """The newest DONE report of this type inside the age bound, or (None, "").

    Returns (document_id, created_time).
    """
    try:
        since = _dt.datetime.utcnow() - _dt.timedelta(seconds=max_age)
        resp = rc.get_reports(reportTypes=[report_type], processingStatuses=["DONE"],
                              marketplaceIds=marketplace_ids,
                              createdSince=since.strftime("%Y-%m-%dT%H:%M:%SZ"),
                              pageSize=10)
        pay = _payload(resp) or {}
        reps = pay.get("reports", []) if isinstance(pay, dict) else []
        reps = [r for r in reps if r.get("reportDocumentId")]
        # Newest first, EXPLICITLY. Never trust the response order.
        reps.sort(key=lambda r: str(r.get("createdTime") or ""), reverse=True)
        if reps:
            return reps[0].get("reportDocumentId"), str(reps[0].get("createdTime") or "")
    except Exception:
        pass
    return None, ""


def create_and_wait(rc, report_type, marketplace_ids=None, options=None,
                    start_time=None, end_time=None, on_wait=None):
    """Ask for a fresh report and wait for it. Returns the document id.

    on_wait(attempt) is called between polls so a caller can report progress or
    abandon; it is optional and its return value is ignored.
    """
    kw = {"reportType": report_type}
    if marketplace_ids:
        kw["marketplaceIds"] = marketplace_ids
    if options:
        kw["reportOptions"] = options
    if start_time:
        kw["dataStartTime"] = start_time
    if end_time:
        kw["dataEndTime"] = end_time

    cr = _payload(rc.create_report(**kw)) or {}
    rid = cr.get("reportId") if isinstance(cr, dict) else None
    if not rid:
        raise ReportError("Amazon did not return a report id.")

    for attempt in range(POLL_ATTEMPTS):
        pay = _payload(rc.get_report(rid)) or {}
        status = pay.get("processingStatus")
        if status == "DONE":
            return pay.get("reportDocumentId")
        if status in ("CANCELLED", "FATAL"):
            # CANCELLED is Amazon's answer for "there is no data for that range",
            # which is not a failure and must not be reported as one.
            raise ReportError("Amazon returned %s for this report. For a date range "
                              "with no sales that is normal." % status)
        if on_wait:
            try:
                on_wait(attempt)
            except Exception:
                pass
        time.sleep(POLL_FAST if attempt < 10 else POLL_SLOW)

    raise ReportError("Amazon is still generating the report. Large accounts can "
                      "take several minutes -- try again shortly and it will "
                      "usually be ready instantly.")


def download(rc, document_id):
    """The report document as text. Handles all three shapes Amazon returns.

    The library may hand back the decrypted text directly, or an attribute on the
    response, or only a URL to fetch (optionally gzipped). Handling one of the
    three works right up until the day it returns another.
    """
    doc = rc.get_report_document(document_id, download=True)
    pay = _payload(doc)

    text = ""
    if isinstance(pay, dict):
        text = pay.get("document", "") or ""
    if not text:
        text = getattr(doc, "document", "") or ""
    if text:
        return text

    url = pay.get("url") if isinstance(pay, dict) else None
    if not url:
        raise ReportError("Amazon returned no report document and no URL.")
    try:
        raw = urllib.request.urlopen(url, timeout=60).read()
        if (isinstance(pay, dict) and pay.get("compressionAlgorithm") == "GZIP") \
                or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", "replace")
    except ReportError:
        raise
    except Exception as e:
        raise ReportError("Could not download the report document: %s" % str(e)[:160])


def fetch(rc, report_type, marketplace_ids=None, options=None,
          start_time=None, end_time=None, allow_reuse=True, on_wait=None):
    """The whole sequence. Returns (text, source, built_at).

    source is "reused" or "new", so a caller can tell someone how fresh the
    numbers really are rather than implying they were just pulled.
    """
    doc_id, built_at, source = None, "", "new"
    if allow_reuse:
        doc_id, built_at = find_recent(rc, report_type, marketplace_ids)
        if doc_id:
            source = "reused"
    if not doc_id:
        doc_id = create_and_wait(rc, report_type, marketplace_ids, options,
                                 start_time, end_time, on_wait=on_wait)
        built_at = _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    return download(rc, doc_id), source, built_at


def fetch_json(rc, report_type, **kw):
    """Same, for the reports Amazon returns as JSON (Sales & Traffic is one)."""
    text, source, built_at = fetch(rc, report_type, **kw)
    try:
        return json.loads(text), source, built_at
    except Exception as e:
        raise ReportError("Amazon's report was not valid JSON: %s" % str(e)[:120])
