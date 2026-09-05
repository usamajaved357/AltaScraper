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
    from domain import returns_store as _rstore

    def _wrong_account(asked):
        """Refuse a caller naming an account other than the one that is open.

        Asked of domain/account_scope.py rather than compared here, so this
        screen cannot develop its own opinion about what counts as a mismatch
        (CLAUDE.md Rule 12). Returns a ready 409 response, or None to continue.
        """
        from domain import account_scope as _acctscope
        open_id = (_state or {}).get("active_account_id")
        if _acctscope.is_mismatch(asked, open_id):
            return jsonify(_acctscope.refusal(asked, open_id, "returns")), 409
        return None

    def _keep(wsid, mkt, returns, source):
        """Store what was just parsed. NEVER fatal.

        A returns screen that fails because the KEEPING failed would be worse
        than one that forgets -- the figures on it are already correct and
        already in the reply. So a storage problem is swallowed here and the
        screen answers exactly as it did before this existed.
        """
        try:
            return _rstore.store(CONFIG_PATH, wsid, mkt, returns, source)
        except Exception:
            return None

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
        # KEEP THEM. Amazon caps this report at 60 days, so year-to-date is four
        # or five downloads and history is only possible if it is accumulated.
        # Until now the parsed rows lived in a dict in memory and a restart lost
        # them -- the same shape as the search-term bug, where the app could act
        # on a report once and could never show you what it said afterwards.
        # domain/returns_store.py de-duplicates on returns_view.identity(), so
        # overlapping windows correct rather than double count.
        _keep(wsid, mkt, returns, _rstore.SOURCE_REPORT)
        return jsonify(_answer(returns, kind, wsid, mkt, start.isoformat(),
                               end.isoformat(), skipped))

    @app.route("/returns/list")
    def returns_list():
        """Every return this app has KEPT, newest first. Reads only.

        The difference from /returns/report matters: that one asks Amazon and
        answers with an analysis of the last N days. This one answers from what
        has been accumulated, so it can show a return from four months ago that
        no single 60-day report can still reach.

        Nothing here is computed. The counting, the reasons and the causes are
        returns_view's job and already have a screen; this is the operational
        list -- one row per return, with what Amazon says about it.
        """
        acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": _scope_mod.NO_MARKETPLACE}), 400
        start = (request.args.get("start") or "").strip() or None
        end = (request.args.get("end") or "").strip() or None
        order_id = (request.args.get("order_id") or "").strip() or None
        try:
            limit = max(1, min(2000, int(request.args.get("limit") or 500)))
        except (TypeError, ValueError):
            limit = 500

        rows = _rstore.load(CONFIG_PATH, wsid, mkt, start, end, order_id, limit)
        cov = _rstore.coverage(CONFIG_PATH, wsid, mkt)

        # WHAT IS OPEN AND WHAT IS SETTLED, from Amazon's own words rather than
        # from a rule of ours. The report's status column is Amazon's; anything
        # we invented on top would be a second opinion about a state we do not
        # own.
        statuses = {}
        for r in rows:
            s = str(r.get("status") or "").strip() or "(none given)"
            statuses[s] = statuses.get(s, 0) + 1

        return jsonify({
            "ok": True, "workspace": wsid, "marketplace": mkt,
            "start": start, "end": end,
            "rows": rows, "count": len(rows),
            "statuses": statuses,
            "coverage": cov,
            # Said plainly, because a list of 40 returns over a period the
            # reports only covered half of is misleading unless it says so.
            "note": ("" if cov.get("held") else
                     "No returns have been stored for this account yet. Press "
                     "Refresh to pull Amazon's report, or upload a returns "
                     "file — Amazon caps that report at 60 days, so anything "
                     "older has to be uploaded once and is then kept."),
        })

    @app.route("/returns/detail")
    def returns_detail():
        """One return, with the order behind it and what may be done about it.

        THE ACTIONS ARE AMAZON'S TO NAME, NOT OURS TO ASSUME.
        The Messaging API says which messages are permitted FOR THIS ORDER, and
        the list genuinely varies between orders. So it is asked, per return,
        and whatever comes back is what the screen may offer. Nothing is sent
        here -- this endpoint reads, and Phase 2 does the sending.

        A failure to ask is reported, never treated as "no actions available":
        those two look identical on a screen and mean opposite things.
        """
        acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": _scope_mod.NO_MARKETPLACE}), 400
        ident = (request.args.get("identity") or "").strip()
        if not ident:
            return jsonify({"ok": False, "error": "no return named"}), 400

        row = _rstore.one(CONFIG_PATH, wsid, mkt, ident)
        if not row:
            return jsonify({"ok": False,
                            "error": "That return is not stored here."}), 404

        # Every OTHER return on the same order -- a buyer sending back two of
        # three items is one conversation, not two.
        siblings = [r for r in _rstore.load(CONFIG_PATH, wsid, mkt,
                                            order_id=row.get("order_id"))
                    if r.get("identity") != ident] if row.get("order_id") else []

        # TWO DIFFERENT CHECKS, AND THIS ROUTE NEEDS BOTH.
        #
        # (1) IS THE CALLER ALLOWED TO NAME THIS ACCOUNT AT ALL? The page sends
        #     the account id, and this route resolves that account's own Amazon
        #     credentials with it. Multi-tenant OAuth puts OTHER PEOPLE'S
        #     selling accounts in the same config, so "a configured account" no
        #     longer means "one of ours" -- naming another one here would ask
        #     Amazon about a stranger's order. domain/account_scope.py is the
        #     one place that answers it, and test_account_scope_audit.py exists
        #     precisely because "the hole that survives a fix is the one next
        #     door". It caught this route.
        _bad = _wrong_account(request.args.get("id"))
        if _bad:
            return _bad

        # (2) CAN THIS ACCOUNT AUTHENTICATE AS ITSELF? A workspace that BORROWS
        #     its credentials would ask with the lender's login and Amazon would
        #     answer for the lender's orders. miles_lubricants HAS a seller id
        #     and borrows its credentials, so "has a seller id" is not the test.
        #
        # The stored return is local and needs neither check, so it is still
        # shown. Only the Amazon question is refused, and it says why.
        from domain import accounts as _acc_check
        if not _acc_check.seller_scope_allowed(acc or {}):
            return jsonify({
                "ok": True, "workspace": wsid, "marketplace": mkt,
                "return": row, "same_order": siblings,
                "permitted_actions": [], "actions_error": "",
                "actions_note": (
                    "%s has no Amazon developer app of its own, so Amazon "
                    "cannot be asked what may be sent about this order — "
                    "borrowed credentials would answer for the account they "
                    "were borrowed from. Connect this account's own SP-API "
                    "credentials under Account & sheets."
                    % ((acc or {}).get("label") or wsid or "This workspace")),
            })

        # WHAT MAY BE SENT, asked of the one module that knows -- which also
        # carries each action's schema and whether this app has a VERIFIED
        # endpoint for it. Amazon offers an action called "updateFeedback"
        # whose endpoint the client library does not implement under that name;
        # api/amazon_messaging.py refuses to send it through the
        # similarly-named negativeFeedbackRemoval rather than guessing, and
        # says so. One place decides that (Rule 12).
        from api import amazon_messaging as _msg
        perm = {"ok": False, "actions": [], "error": "no order on this return"}
        if row.get("order_id"):
            from domain import accounts as _acc_mod
            perm = _msg.actions_for(_acc_mod.account_creds(acc), mkt,
                                    row["order_id"])
        actions = perm.get("actions") or []

        return jsonify({
            "ok": True, "workspace": wsid, "marketplace": mkt,
            "return": row, "same_order": siblings,
            "actions": actions,
            "sent": _messages_for(wsid, row.get("order_id")),
            "actions_error": ("" if perm.get("ok") else (perm.get("error") or "")),
            "actions_note": (
                "Amazon decides which messages may be sent about an order, and "
                "the list differs between orders. Free-form messages are not "
                "possible through the API — each of these is one of Amazon's "
                "own templates." if actions else
                ("Amazon could not be asked what may be sent about this order."
                 if not perm.get("ok") else
                 "Amazon permits no messages about this order.")),
        })

    def _messages_for(wsid, order_id):
        """What this app has already sent about that order. [] on any failure."""
        if not order_id:
            return []
        try:
            from data import db as _db
            return [dict(r) for r in _db.get_db(CONFIG_PATH).execute(
                "SELECT action, body, ok, error, sent_by, sent_at "
                "FROM buyer_messages WHERE workspace_id=? AND order_id=? "
                "ORDER BY id DESC LIMIT 20", (wsid, str(order_id)))]
        except Exception:
            return []

    @app.route("/returns/message", methods=["POST"])
    def returns_message():
        """Send ONE of Amazon's permitted messages about an order.

        THE ONLY THING IN THIS FILE THAT REACHES A CUSTOMER, and the only write
        anywhere in the returns feature. It cannot be undone, so:

          * the account is checked twice, exactly as /returns/detail is -- a
            caller must not be able to name someone else's account and message
            THEIR buyer;
          * api/amazon_messaging.send re-asks Amazon whether the action is
            permitted at send time rather than trusting what the page was
            holding, because "you may only send this once per order" becomes
            true the moment somebody else sends it;
          * nothing is composed here. The seller's own words are sent, and only
            into the fields Amazon's schema declares;
          * every attempt is written to buyer_messages, refusals included --
            Amazon never gives these messages back, so if this app does not
            record it, nothing does.
        """
        acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": _scope_mod.NO_MARKETPLACE}), 400
        b = request.get_json(silent=True) or {}

        _bad = _wrong_account(request.args.get("id") or b.get("id"))
        if _bad:
            return _bad
        from domain import accounts as _acc_check
        if not _acc_check.seller_scope_allowed(acc or {}):
            return jsonify({"ok": False, "error": (
                "%s cannot message a buyer: it has no Amazon developer app of "
                "its own, and borrowed credentials would write as the account "
                "they were borrowed from."
                % ((acc or {}).get("label") or wsid or "This workspace"))}), 400

        order_id = str(b.get("order_id") or "").strip()
        action = str(b.get("action") or "").strip()
        values = b.get("values") or {}
        if not order_id or not action:
            return jsonify({"ok": False,
                            "error": "an order and a message type are needed"}), 400

        from api import amazon_messaging as _msg
        from domain import accounts as _acc_mod
        res = _msg.send(_acc_mod.account_creds(acc), mkt, order_id, action, values)

        # LOGGED EITHER WAY. A log of successes only would show a customer as
        # contacted when the message was refused.
        try:
            import datetime as _d
            import json as _j
            from data import db as _db
            who = ""
            try:
                from flask import session
                who = str((session or {}).get("user_email") or "")
            except Exception:
                who = ""
            conn = _db.get_db(CONFIG_PATH)
            conn.execute(
                "INSERT INTO buyer_messages (workspace_id, marketplace, "
                "order_id, action, body, ok, error, sent_by, sent_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (wsid, mkt, order_id, action,
                 _j.dumps(res.get("sent") or values)[:4000],
                 1 if res.get("ok") else 0,
                 (res.get("error") or "")[:600], who,
                 _d.datetime.now().isoformat(timespec="seconds")))
            conn.commit()
        except Exception:
            pass

        if not res.get("ok"):
            return jsonify(res), 400
        res["note"] = ("Sent. Amazon does not return the message afterwards, so "
                       "this app's own record below is the only copy.")
        return jsonify(res)

    @app.route("/returns/upload", methods=["POST"])
    def returns_upload():
        """Parse returns files the user supplies, and ADD them to what is loaded.

        Accepts the seller-fulfilled report OR an FBA Customer Returns file, and
        works out which by its columns rather than its name -- the same report
        downloaded twice gets two different filenames and neither means
        anything.

        SEVERAL FILES, AND THEY COMBINE. This used to take one file and REPLACE
        everything, which made the screen unusable for the case it is most
        needed in:

          - Amazon caps a seller-fulfilled report at 60 days, so year-to-date is
            four or five separate downloads. Only the last one survived.
          - An account with both FBA and seller-fulfilled returns has two
            reports that answer different halves of this page. Uploading the
            second one threw away the first -- so adding data removed data.

        Files are now merged into whatever is already loaded and de-duplicated
        on what identifies a return (returns_view.identity), so overlapping
        windows are safe and re-uploading the same file changes nothing. The
        reply says how many rows were new, how many were already there, and
        which report kinds the combined set now holds.
        """
        acc, wsid, mkt = _scope()

        # EVERY file on the request, not files["file"] alone. A multi-select
        # sends them all under the same field name and only the first was read.
        blobs = []
        if request.files:
            for key in request.files:
                for f in request.files.getlist(key):
                    if f is not None:
                        blobs.append((f.filename or "file",
                                      f.read().decode("utf-8", "replace")))
        if not blobs:
            body = request.get_json(silent=True) or {}
            if body.get("text"):
                blobs = [("pasted", str(body["text"]))]
        blobs = [(n, t) for n, t in blobs if str(t or "").strip()]
        if not blobs:
            return jsonify({"ok": False, "error": "no file"}), 400

        # REPLACE ONLY IF ASKED. The default is to add; "Start again" sets this.
        replace = str(request.args.get("replace") or "").lower() in ("1", "true")
        held = [] if replace else list((_LAST.get(wsid) or {}).get("returns") or [])

        read = []          # per file, so a bad one among four is named
        rejected = []
        total_added = total_dupes = total_skipped = 0
        for name, text in blobs:
            headers, rows, err = _split(text)
            if err == "__EMPTY__":
                rejected.append("%s — no rows in it" % name)
                continue
            parsed, kind, skipped = _rv.parse_rows(headers, rows)
            if not kind:
                rejected.append(
                    "%s — those columns are not an Amazon returns report "
                    "(found: %s)" % (name, ", ".join(str(h) for h in headers[:8])))
                continue
            held, added, dupes = _rv.merge(held, parsed)
            total_added += added
            total_dupes += dupes
            total_skipped += skipped
            # An uploaded file is kept for the same reason a pulled report is,
            # and it matters MORE here: an FBA file carries the disposition and
            # the customer's comment, which the seller-fulfilled report has no
            # column for at all. Losing that on a restart loses the only copy.
            _keep(wsid, mkt, parsed, _rstore.SOURCE_UPLOAD)
            read.append({"file": name, "kind": kind, "rows": len(parsed),
                         "added": added, "already_had": dupes})

        if not held:
            return jsonify({"ok": False, "error": (
                "Nothing could be read. " + " ".join(rejected))}), 400

        kinds = sorted({str(r.get("kind") or "") for r in held if r.get("kind")})
        dates = sorted(r["date"] for r in held if r.get("date"))
        start = dates[0] if dates else ""
        end = dates[-1] if dates else ""

        bits = []
        if total_added:
            bits.append("Added %s return%s from %d file%s."
                        % ("{:,}".format(total_added),
                           "" if total_added == 1 else "s",
                           len(read), "" if len(read) == 1 else "s"))
        if total_dupes:
            bits.append("%s row%s were already loaded and were not counted "
                        "twice." % ("{:,}".format(total_dupes),
                                    "" if total_dupes == 1 else "s"))
        bits.append("Now holding %s returns%s%s."
                    % ("{:,}".format(len(held)),
                       (" from " + " and ".join(
                           "FBA" if k == "fba" else "seller-fulfilled"
                           for k in kinds)) if kinds else "",
                       (", %s to %s" % (start, end)) if start else ""))
        if rejected:
            bits.append("Not read: " + "; ".join(rejected))

        # The kind reported to the screen is what the COMBINED set can support.
        # "fba" unlocks the disposition and comment sections, so it may only be
        # claimed when FBA rows are actually present.
        combined_kind = "fba" if "fba" in kinds else (kinds[0] if kinds else "")
        out = _answer(held, combined_kind, wsid, mkt, start, end, total_skipped,
                      note=" ".join(bits))
        out["files_read"] = read
        out["rejected"] = rejected
        out["kinds"] = kinds
        return jsonify(out)

    @app.route("/returns/view")
    def returns_view():
        """Re-answer the loaded returns for a date range. ?from=&to= (ISO days).

        WHY THE SERVER DOES THIS. Dragging a range on the daily chart has to
        change every figure on the page -- the rate, the causes, the parents,
        the themes, the findings -- and all of that is computed in
        domain/returns_view.py and domain/returns_intel.py. Filtering in the
        browser would mean a second implementation of the same arithmetic living
        in JavaScript, and the two would disagree the first time either changed
        (CLAUDE.md rule 12). So the rows are filtered here, by date, and handed
        to exactly the same two functions a fresh upload goes through.

        It costs nothing: the parsed returns are already in memory for this
        workspace -- that is what the Excel export writes from -- so no file is
        re-read and Amazon is not asked for anything.
        """
        _acc, wsid, mkt = _scope()
        got = _LAST.get(wsid) or {}
        rows = got.get("returns")
        if not rows:
            return jsonify({"ok": False, "error": (
                "There is nothing loaded to filter. Upload a returns report "
                "first.")}), 400
        lo = str(request.args.get("from") or "")[:10]
        hi = str(request.args.get("to") or "")[:10]
        span = sorted(r["date"] for r in rows if r.get("date"))
        full_lo = span[0] if span else ""
        full_hi = span[-1] if span else ""
        sel = [r for r in rows
               if (not lo or str(r.get("date") or "") >= lo)
               and (not hi or str(r.get("date") or "") <= hi)]
        # AN EMPTY RANGE IS SAID, NOT DRAWN. Answering with zeros would look
        # like a week in which nothing came back.
        if not sel:
            return jsonify({"ok": False, "error": (
                "No returns between %s and %s. The data runs %s to %s."
                % (lo or "the start", hi or "the end", full_lo, full_hi))}), 400
        kinds = sorted({str(r.get("kind") or "") for r in sel if r.get("kind")})
        out = _answer(sel, "fba" if "fba" in kinds else (kinds[0] if kinds else ""),
                      wsid, mkt, lo or full_lo, hi or full_hi,
                      note=("Showing %s of %s returns, %s to %s."
                            % ("{:,}".format(len(sel)), "{:,}".format(len(rows)),
                               lo or full_lo, hi or full_hi))
                      if len(sel) != len(rows) else "")
        # THE ZOOM MUST NOT EAT THE DATA. _answer re-remembers what it was
        # given, so without this the filtered subset would become the whole set
        # and zooming in twice would be a one-way trip. Only `returns` is put
        # back: `summary` deliberately stays as the zoomed one, because the
        # Excel export writes what you are looking at, and start/end stay as the
        # range on screen so the workbook says which period it covers.
        _remember(wsid, returns=rows)
        out["zoomed"] = bool(lo or hi)
        out["full_start"] = full_lo
        out["full_end"] = full_hi
        return jsonify(out)

    @app.route("/returns/clear", methods=["POST"])
    def returns_clear():
        """Forget the loaded returns for this workspace and start over.

        The counterpart to uploads that ADD: without a way back, a file uploaded
        against the wrong account could only be got rid of by restarting the app.
        """
        _acc, wsid, _mkt = _scope()
        _LAST.pop(wsid, None)
        return jsonify({"ok": True, "cleared": True,
                        "note": "Cleared. Upload a returns report to start again."})

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
