"""routes/returns_routes.py -- why things come back, and what it costs.

    GET  /returns/report    pull it from Amazon for the open account
    POST /returns/upload    parse a returns file you supply

Reads only. Nothing here changes a listing or an order.

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

from flask import request, jsonify

from domain import returns_view as _rv
from routes import scope as _scope_mod

# Amazon refuses a wider window on this report -- measured: 90 days comes back
# FATAL, 60 works.
MAX_DAYS = 60


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach /returns/* to the app."""

    def _scope():
        return _scope_mod.resolve(
            state=_state, account=_active_account() or {},
            asked_id=request.args.get("id"),
            asked_marketplace=request.args.get("marketplace"))

    def _sold(wsid, mkt, start, end):
        """Units and sales per ASIN, so a return count can become a RATE.

        From the app's own sales data -- already pulled, already per ASIN. A
        count of returns says nothing on its own; twelve is excellent on four
        thousand orders and a catastrophe on twenty.
        """
        out = {}
        try:
            from data import db as _db
            for r in _db.get_db(CONFIG_PATH).execute(
                    "SELECT asin, SUM(COALESCE(units,0)) units, "
                    "       SUM(COALESCE(ordered_sales,0)) sales "
                    "FROM sales_daily WHERE workspace_id=? AND marketplace=? "
                    "  AND date>=? AND date<=? AND asin<>'*' GROUP BY asin",
                    (wsid, mkt, start, end)):
                out[str(r["asin"])] = {"units": int(r["units"] or 0),
                                       "sales": float(r["sales"] or 0)}
        except Exception:
            return {}
        return out

    def _fetch(acc, mkt, days):
        """The seller-fulfilled returns report. -> (headers, rows, error)."""
        from domain import accounts as _acc_mod
        try:
            from sp_api.api import Reports
            from sp_api.base import Marketplaces
        except Exception as e:
            return [], [], "SP-API Reports is unavailable: %s" % str(e)[:120]
        enum = getattr(Marketplaces, str(mkt).upper(), Marketplaces.UK)
        rc = Reports(credentials=_acc_mod.account_creds(acc), marketplace=enum)
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

    def _answer(returns, kind, wsid, mkt, start, end, skipped=0, note=""):
        s = _rv.summarise(returns, _sold(wsid, mkt, start, end))
        s.update({
            "ok": True, "source": kind, "workspace": wsid, "marketplace": mkt,
            "start": start, "end": end, "skipped": skipped, "note": note,
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
        if not (acc or {}).get("seller_id"):
            return jsonify({"ok": False, "error": (
                "%s has no Amazon account of its own, so it has no returns."
                % ((acc or {}).get("label") or wsid))}), 400
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
            return jsonify({"ok": False, "error": err}), 502
        returns, kind, skipped = _rv.parse_rows(headers, rows)
        if not kind:
            return jsonify({"ok": False, "error": (
                "That report's columns were not recognised. Found: %s"
                % ", ".join(str(h) for h in headers[:12]))}), 502
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
