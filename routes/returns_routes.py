"""routes/returns_routes.py -- why things come back, and what it costs.

    GET  /returns/report      pull it from Amazon for the open account
    POST /returns/upload      parse a returns file you supply
    POST /returns/quality     add Amazon's Listing Quality export
    GET  /returns/export.xlsx the whole analysis as a workbook

Reads only. Nothing here changes a listing or an order.

WHY THE LAST TWO NEED A MEMORY. The export has to write the same figures the
screen is showing, and the screen's figures came from a file the browser
uploaded or a report that took two minutes to build. Re-pulling would breach
Amazon's roughly-one-report-a-minute quota and could quietly answer with a
different window; asking the browser to post eleven thousand rows back is worse.
So the parsed returns are kept in memory for the workspace that loaded them,
and the export writes from exactly what the screen was given. If the app has
restarted since, the export says so and asks for the file again rather than
silently exporting something older.

TWO WAYS IN, ON PURPOSE. The automatic pull uses the seller-fulfilled returns
report, which is what these accounts have. The upload accepts EITHER that file
or an FBA Customer Returns file -- and the FBA one carries two columns the API
will not give a seller-fulfilled account: the disposition Amazon graded the
return with, and the customer's own comment. So the upload is not a fallback for
when the API fails; it is how the two richest sections of the page get filled at
all. The reply says which report it read and which sections it can therefore
support.
"""
import csv
import datetime as _dt
import io

from flask import request, jsonify, Response

from domain import returns_intel as _ri
from domain import returns_view as _rv
from routes import scope as _scope_mod

# Amazon refuses a wider window on this report -- measured: 90 days comes back
# FATAL, 60 works.
MAX_DAYS = 60

# The last analysis each workspace loaded, so the export can write exactly what
# the screen was shown. Keyed by workspace id, and capped.
#
# WHAT THIS COSTS, honestly: a big returns file is 11,509 rows, and holding the
# parsed rows plus the summary for one workspace is on the order of twenty
# megabytes. Four is the ceiling because this is a desktop app serving one
# person -- switching between more than four accounts' returns in a single
# session is not a thing anyone does, and the fifth one simply asks you to load
# the report again rather than growing without limit.
_LAST = {}
_LAST_MAX = 4


def _remember(wsid, **fields):
    """Keep this workspace's analysis, dropping the oldest if we are over."""
    if not wsid:
        return
    cur = _LAST.setdefault(wsid, {})
    cur.update(fields)
    while len(_LAST) > _LAST_MAX:
        for k in list(_LAST):
            if k != wsid:
                _LAST.pop(k, None)
                break
        else:
            break


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach /returns/* to the app."""

    def _scope():
        return _scope_mod.resolve(
            state=_state, account=_active_account() or {},
            asked_id=request.args.get("id"),
            asked_marketplace=request.args.get("marketplace"),
            # WITHOUT THIS, THE ID AND THE CREDENTIALS DISAGREE.
            #
            # resolve() only replaces the account RECORD when it is given a way to
            # load one; otherwise it hands back the id the page asked for and the
            # record from the server's process-wide global. This screen then builds
            # its Amazon client from that record -- so asking for jack_uk's returns
            # would fetch them with whichever account the global happened to hold.
            # Measured: /returns/report?id=jack_uk answered about Miles Lubricants.
            # routes/scope.py's own docstring warns about exactly this; the price
            # screen passes it and three other callers did not.
            load_account=_load_account)

    def _load_account(aid):
        """The account record for an id the PAGE named -- credentials included."""
        try:
            from domain import accounts as _acc_mod
            return _acc_mod.get_account(
                _cfg() if callable(_cfg) else (_cfg or {}), aid, CONFIG_PATH)
        except Exception:
            return None

    def _sold(wsid, mkt, start, end):
        """Units and sales per ASIN, so a return count can become a RATE.

        From the app's own sales data -- already pulled, already per ASIN. A
        count of returns says nothing on its own; twelve is excellent on four
        thousand orders and a catastrophe on twenty.

        THROUGH sales_data.products, NOT ITS OWN QUERY. This used to hold a
        second hand-written SELECT over sales_daily that did the same job as
        domain/sales_data.py's -- two places deciding what "units sold in a
        period" means, which is exactly the shape CLAUDE.md rule 12 exists to
        stop. The reshape below is all that is left of it.
        """
        try:
            from domain import sales_data as _sd
            return {str(r["asin"]): {"units": int(r.get("units") or 0),
                                     "sales": float(r.get("revenue") or 0)}
                    for r in _sd.products(CONFIG_PATH, wsid, mkt, start, end)}
        except Exception:
            return {}

    def _families(aid, mkt):
        """{asin: family name}, from the one place that map is made."""
        try:
            from domain import families as _fam
            return _fam.by_asin(CONFIG_PATH, aid, mkt)
        except Exception:
            return {}

    def _fetch(acc, mkt, days):
        """The seller-fulfilled returns report. -> (headers, rows, error)."""
        from domain import accounts as _acc_mod
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
            rc = Reports(credentials=_acc_mod.account_creds(acc), marketplace=enum)
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
                marketplaceIds=[_acc_mod.marketplace_id(mkt)])
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
                return [], [], ("__EMPTY__" if st == "CANCELLED" else
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
        return _split(text)

    def _split(text):
        """A tab- or comma-separated report -> (headers, rows, error)."""
        lines = [l for l in str(text or "").splitlines() if l.strip()]
        if not lines:
            return [], [], "__EMPTY__"
        delim = "\t" if lines[0].count("\t") >= lines[0].count(",") else ","
        rdr = csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)
        rows = list(rdr)
        if not rows:
            return [], [], "__EMPTY__"
        return rows[0], rows[1:], ""

    def _answer(returns, kind, wsid, mkt, start, end, skipped=0, note="",
                no_report=""):
        sold = _sold(wsid, mkt, start, end)
        # wsid IS the account id -- the same value routes/variations_routes.py
        # passes to families.for_account. There is no separate workspace key.
        fams = _families(wsid, mkt)
        s = _rv.summarise(returns, sold, fams)
        # THE SECOND LAYER, built from the first. Everything under "intel" is
        # derived from the returns that have just been counted above, never
        # re-counted -- so a parent total here and a product-line total there
        # are the same arithmetic.
        quality = (_LAST.get(wsid) or {}).get("quality") or []
        s["intel"] = _ri.build(returns, s, fams, sold, quality)
        _remember(wsid, returns=returns, summary=s, kind=kind,
                  start=start, end=end, marketplace=mkt)
        s.update({
            "ok": True, "source": kind, "workspace": wsid, "marketplace": mkt,
            "start": start, "end": end, "skipped": skipped, "note": note,
            # WHY there is no report, when there is none. A separate field from
            # `unavailable` below, which lists the SECTIONS a report cannot
            # support: one is "this whole thing did not arrive", the other is
            # "it arrived and cannot answer these parts".
            "no_report": no_report,
            # WHICH SECTIONS THIS DATA CAN SUPPORT, said plainly, so a section
            # that is missing never looks like a fault.
            "unavailable": ([] if kind == "fba" else [
                {"section": "Disposition & recovery",
                 "why": ("Amazon grades a return's condition only when it "
                         "receives it — which happens with FBA. A "
                         "seller-fulfilled return goes straight back to you, so "
                         "Amazon never sees it and has nothing to report. "
                         "Upload an FBA Customer Returns file to fill this in.")},
                {"section": "Customer voice",
                 "why": ("The buyer's comment is recorded when Amazon processes "
                         "the return in its own warehouse. Seller-fulfilled "
                         "returns carry no comment field at all. An FBA returns "
                         "file has them.")},
            ]),
        })
        return s

    @app.route("/returns/report")
    def returns_report():
        """Pull the returns report for the open account."""
        acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": _scope_mod.NO_MARKETPLACE}), 400
        # A RETURNS REPORT IS SELLER-SCOPED, so it must not be asked for with
        # borrowed credentials -- a borrowed token answers for the LENDER, and this
        # screen would then show one business's returns under another's name. The
        # same rule the live-orders endpoints already apply.
        #
        # It used to check `seller_id` alone. miles_lubricants HAS a seller id and
        # BORROWS its credentials from sheelady_us, so it passed the check and then
        # failed inside sp_api with an HTTP 500. Having an account of your own and
        # being able to authenticate as it are two different things.
        from domain import accounts as _acc_check
        if not _acc_check.seller_scope_allowed(acc or {}):
            return jsonify({"ok": False, "error": (
                "%s cannot be asked for its returns: it has no Amazon developer "
                "app of its own. Returns are specific to one seller account, and "
                "borrowed credentials would answer for the account they were "
                "borrowed from. Connect this account's own SP-API credentials "
                "under Account & sheets."
                % ((acc or {}).get("label") or wsid or "This workspace"))}), 400
        try:
            days = max(1, min(MAX_DAYS, int(request.args.get("days") or 30)))
        except (TypeError, ValueError):
            days = 30
        end = _dt.date.today()
        start = end - _dt.timedelta(days=days - 1)

        headers, rows, err = _fetch(acc, mkt, days)
        if err == "__EMPTY__":
            return jsonify(_answer([], "mfn", wsid, mkt, start.isoformat(),
                                   end.isoformat(),
                                   note=("Amazon returned nothing for the last "
                                         "%d days — which for returns is good "
                                         "news, not a failure." % days)))
        if err:
            # NOT AN ERROR PAGE. Amazon being slow, or an account that is
            # seller-fulfilled and has no FBA report to give, are ordinary
            # states -- and a red message where the screen should be tells you
            # nothing about returns and hides the layout entirely.
            #
            # So the page is still answered, with no data and the reason. The
            # screen draws its own placeholders and marks every one of them;
            # nothing is invented here, and the moment a real report lands the
            # same answer carries real figures.
            return jsonify(_answer([], "", wsid, mkt, start.isoformat(),
                                   end.isoformat(), no_report=err))
        returns, kind, skipped = _rv.parse_rows(headers, rows)
        if not kind:
            return jsonify(_answer(
                [], "", wsid, mkt, start.isoformat(), end.isoformat(),
                no_report=("That report's columns were not recognised. "
                           "Found: %s"
                           % ", ".join(str(h) for h in headers[:12]))))
        return jsonify(_answer(returns, kind, wsid, mkt, start.isoformat(),
                               end.isoformat(), skipped))

    @app.route("/returns/upload", methods=["POST"])
    def returns_upload():
        """Parse a returns file the user supplies.

        Accepts the seller-fulfilled report OR an FBA Customer Returns file, and
        works out which by its columns rather than its name -- the same report
        downloaded twice gets two different filenames and neither means
        anything.
        """
        acc, wsid, mkt = _scope()
        text = ""
        f = (request.files or {}).get("file")
        if f is not None:
            text = f.read().decode("utf-8", "replace")
        else:
            text = str((request.get_json(silent=True) or {}).get("text") or "")
        if not text.strip():
            return jsonify({"ok": False, "error": "no file"}), 400

        headers, rows, err = _split(text)
        if err == "__EMPTY__":
            return jsonify({"ok": False, "error": "that file has no rows"}), 400
        returns, kind, skipped = _rv.parse_rows(headers, rows)
        if not kind:
            return jsonify({"ok": False, "error": (
                "Those columns were not recognised as an Amazon returns report. "
                "It needs at least an ASIN or SKU and a reason. Found: %s"
                % ", ".join(str(h) for h in headers[:12]))}), 400

        dates = sorted(r["date"] for r in returns if r.get("date"))
        start = dates[0] if dates else ""
        end = dates[-1] if dates else ""
        out = _answer(returns, kind, wsid, mkt, start, end, skipped,
                      note=("Read %d rows from your file as %s data."
                            % (len(returns),
                               "FBA" if kind == "fba" else "seller-fulfilled")))
        return jsonify(out)

    # ---- Amazon's own verdict on the listings -------------------------------

    @app.route("/returns/quality", methods=["POST"])
    def returns_quality():
        """Take a Listing Quality (Listing Summary) export.

        A SECOND FILE, DELIBERATELY. Three things on this screen can only come
        from Amazon's own assessment and appear in no returns report and in no
        API this app has: whether the "frequently returned item" badge is
        showing on a listing, Amazon's CX Health grade, and the reason Amazon
        itself puts at the top. Seller Central > Voice of the Customer >
        Download.

        It is kept against the analysis already loaded and the screen is told to
        ask for it again -- it does not re-request the returns report, which is
        rate-limited to about one a minute.
        """
        _acc, wsid, _mkt = _scope()
        f = (request.files or {}).get("file")
        text = (f.read().decode("utf-8-sig", "replace") if f is not None
                else str((request.get_json(silent=True) or {}).get("text") or ""))
        if not text.strip():
            return jsonify({"ok": False, "error": "no file"}), 400
        rows = list(csv.DictReader(io.StringIO(text)))
        # RECOGNISED BY ITS COLUMNS, not its name -- the same rule the returns
        # upload uses, and for the same reason.
        cols = {str(k or "").strip().lower() for k in (rows[0].keys() if rows
                                                       else [])}
        if not rows or not ({"asin"} & cols) or not any(
                "return badge" in c or "cx health" in c or "ncx" in c
                for c in cols):
            return jsonify({"ok": False, "error": (
                "That does not look like a Listing Quality export. It needs an "
                "ASIN column and at least one of NCX rate, CX Health or Return "
                "Badge Displayed. Found: %s"
                % ", ".join(sorted(cols)[:10]))}), 400
        _remember(wsid, quality=rows)
        risky = _ri.at_risk(rows)
        counts = {
            "rows": len(rows),
            "badge_showing": sum(1 for a in risky
                                 if a["state"] == "badge showing"),
            "at_risk_count": sum(1 for a in risky if a["state"] == "at risk"),
        }
        # THE WHOLE ANSWER BACK, REBUILT, not just the counts.
        #
        # This used to reply with the counts and let the screen call
        # returnsLoad() to fold them in -- and returnsLoad() pulls from AMAZON.
        # On an account whose returns had been UPLOADED rather than pulled, that
        # threw the uploaded file away and left an empty page: adding a file
        # deleted the data. Measured in a browser: 13 panels before the quality
        # upload, 12 and no tables after it.
        #
        # The returns are already held for this workspace, so the analysis is
        # simply built again with the quality file in it and sent back whole.
        # Nothing is re-pulled and nothing is re-uploaded.
        got = _LAST.get(wsid) or {}
        if got.get("returns") is not None:
            out = _answer(got["returns"], got.get("kind") or "", wsid,
                          got.get("marketplace") or "", got.get("start") or "",
                          got.get("end") or "",
                          note=("Read %d listings from your Listing Quality "
                                "file — %d already carry Amazon's returns badge "
                                "and %d are at risk of it."
                                % (counts["rows"], counts["badge_showing"],
                                   counts["at_risk_count"])))
            out.update(counts)
            return jsonify(out)
        counts.update({
            "ok": True, "at_risk": risky,
            "note": ("Read %d listings. Load a returns report and this folds "
                     "into the tables." % len(rows)),
        })
        return jsonify(counts)

    # ---- the whole thing as a workbook --------------------------------------

    @app.route("/returns/export.xlsx")
    def returns_export():
        """Every table on this screen, as an eight-sheet workbook.

        Writes from what the screen was last given, not from a fresh pull --
        see the note at the top of this file. If nothing has been loaded, it
        says so in plain English rather than sending an empty spreadsheet,
        which would look like an account with no returns.
        """
        acc, wsid, mkt = _scope()
        got = _LAST.get(wsid) or {}
        if not got.get("summary"):
            return jsonify({"ok": False, "error": (
                "There is nothing to export yet. Load the returns report on "
                "this screen first — the export writes exactly what you are "
                "looking at, so it needs you to be looking at something. (If "
                "the app has restarted since, load it again.)")}), 400
        s = got["summary"]
        try:
            from domain import returns_excel as _rx
            data = _rx.to_bytes(s, s.get("intel") or {}, {
                "account": (acc or {}).get("label") or wsid,
                "start": got.get("start"), "end": got.get("end"),
                "source_note": ("Built from %s, %s rows, %s to %s."
                                % ("an FBA Customer Returns report"
                                   if got.get("kind") == "fba"
                                   else "a seller-fulfilled returns report",
                                   "{:,}".format(len(got.get("returns") or [])),
                                   got.get("start") or "?",
                                   got.get("end") or "?")),
            })
        except ImportError:
            return jsonify({"ok": False, "error": (
                "The spreadsheet library (openpyxl) is not installed, so the "
                "workbook cannot be built. Everything on the screen is "
                "unaffected.")}), 500
        name = "returns-analysis-%s-%s.xlsx" % (
            (wsid or "account"), (got.get("end") or "")[:10] or "latest")
        return Response(data, mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"), headers={
                "Content-Disposition": 'attachment; filename="%s"' % name,
                "Content-Length": str(len(data)),
                # NEVER CACHED. The same URL answers with a different workbook
                # the moment a different report is loaded, and a browser that
                # kept the first one would hand back last week's figures under
                # this week's filename.
                "Cache-Control": "no-store"})
