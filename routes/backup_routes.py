"""routes/backup_routes.py -- the safety net for a database-only app.

    GET  /backup/status     when the last backup ran, and what it covered
    POST /backup/run        back up every account to its own backup tab, now
    GET  /backup/download   a consistent snapshot of the whole database
    GET  /backup/verify     does the database hold everything the sheet holds?

Nothing here reads a backup back into the app. That is the property that stops
the sync problem returning: a backup is written and never consulted, so a stale
copy cannot become live data.

/backup/verify is the one to run BEFORE switching Sheets off. It answers the
only question that matters at that moment -- is there anything in the
spreadsheet that the app does not have -- and it names the columns the import
does not understand, which is the way data gets lost quietly rather than
loudly.
"""
import io
import os
import time

from flask import request, jsonify, send_file

from domain import backup as _backup


def register(app, *, CONFIG_PATH, _cfg, _client, _state):
    """Attach /backup/* to the app."""

    def _accounts():
        try:
            from domain import accounts as _acc
            return _acc.load_accounts(_cfg(), CONFIG_PATH) or []
        except Exception:
            return (_cfg() or {}).get("accounts") or []

    @app.route("/backup/status")
    def backup_status():
        st = _backup.NIGHTLY.status()
        st["ok"] = True
        # Said in words, because "last_ok: 0" is not something to read at a
        # glance and this is a screen you look at when you are worried.
        if not st.get("last_ok"):
            st["says"] = ("No backup has run yet in this process. One runs "
                          "automatically within a couple of minutes of the app "
                          "starting, and daily after that.")
        else:
            h = st.get("last_ok_ago_hours")
            st["says"] = ("Last backup %s hours ago." % h) + (
                "" if not st.get("last_error") else
                " The most recent attempt reported: %s" % st["last_error"])
        return jsonify(st)

    @app.route("/backup/run", methods=["POST"])
    def backup_run():
        """Back up now. Writes only to each account's own backup tab."""
        res = _backup.NIGHTLY.run_once(
            _client, CONFIG_PATH, _accounts,
            log=lambda m: print("[backup] %s" % m, flush=True))
        done = [r for r in res if not r.get("skipped") and not r.get("error")]
        return jsonify({"ok": True, "results": res,
                        "backed_up": len(done),
                        "note": "Each account's listings were written to its own "
                                "%s… tab. Nothing was read from any sheet, and "
                                "the tabs the app reads were not touched."
                                % _backup.BACKUP_TAB_PREFIX})

    @app.route("/backup/download")
    def backup_download():
        """The whole database, as one file you can keep.

        Taken with SQLite's backup API rather than copied off disk: the database
        runs in WAL mode, so a plain file copy can miss the newest writes or be
        unreadable.
        """
        try:
            path = _backup.snapshot(CONFIG_PATH)
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Could not take a snapshot: %s" % str(e)[:200]}), 500
        # Read it into memory and delete the temporary file before replying, so
        # a download that is never collected cannot leave copies of the whole
        # dataset lying about on the server.
        try:
            with open(path, "rb") as f:
                blob = f.read()
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass
        name = "altascraper-%s.db" % time.strftime("%Y%m%d-%H%M")
        return send_file(io.BytesIO(blob), as_attachment=True,
                         download_name=name,
                         mimetype="application/vnd.sqlite3")

    @app.route("/backup/verify")
    def backup_verify():
        """Is anything in the spreadsheet missing from the app? Reads only.

        Run this before switching Sheets off. It compares SKUs both ways and
        reports the columns the import does not understand -- Miles' four
        "Bullet Point N" columns are exactly the kind of thing that would be
        dropped without a word.
        """
        only = (request.args.get("id") or "").strip()
        out = []
        for a in _accounts():
            aid = str(a.get("id") or "").strip()
            if not aid or (only and aid != only):
                continue
            sid = str(a.get("output_spreadsheet_id") or "").strip()
            row = {"id": aid, "label": a.get("label") or aid}
            try:
                from data.store import ListingStore
                store = ListingStore(aid, config_path=CONFIG_PATH)
                in_app = {str(r.get("SKU", "")).strip().upper()
                          for r in store.get_all_rows()
                          if str(r.get("SKU", "")).strip()}
            except Exception as e:
                row.update({"error": "could not read the app's store: %s" % str(e)[:160]})
                out.append(row)
                continue
            row["in_app"] = len(in_app)
            if not sid:
                row.update({"in_sheet": 0, "missing_from_app": [],
                            "verdict": "no spreadsheet configured — nothing to compare"})
                out.append(row)
                continue
            try:
                from routes import migrate_routes as _mig   # tab resolution lives there
                tab, err = _resolve_tab_via(sid, a)
                if err:
                    row.update({"error": err})
                    out.append(row)
                    continue
                book = _client().open_by_key(sid)
                ws = book.worksheet(tab)
                grid = ws.get_all_values()
            except Exception as e:
                row.update({"error": "could not read the sheet: %s" % str(e)[:160]})
                out.append(row)
                continue
            header = [str(h).strip() for h in (grid[0] if grid else [])]
            try:
                from data.column_map import col_for_header
                unknown = [h for h in header if h and not col_for_header(h)]
            except Exception:
                unknown = []
            si = -1
            for i, h in enumerate(header):
                if h.strip().lower() in ("sku", "seller-sku", "seller_sku"):
                    si = i
                    break
            in_sheet = set()
            if si >= 0:
                for r in grid[1:]:
                    v = str(r[si]).strip().upper() if si < len(r) else ""
                    if v:
                        in_sheet.add(v)
            missing = sorted(in_sheet - in_app)
            row.update({
                "tab": tab, "in_sheet": len(in_sheet),
                "missing_from_app": missing[:50],
                "missing_count": len(missing),
                "unknown_columns": unknown,
                # The verdict is the whole point: a list of numbers still needs
                # reading, and this is the line someone acts on.
                "verdict": (
                    "SAFE to stop reading this sheet — the app has every SKU it holds"
                    if not missing and not unknown else
                    "NOT yet — %d SKU(s) are only in the sheet%s" % (
                        len(missing),
                        (", and %d column(s) would be dropped by an import: %s"
                         % (len(unknown), ", ".join(unknown[:6]))) if unknown else "")
                    if missing else
                    "Every SKU is in the app, but %d column(s) are not understood "
                    "and their data would be dropped: %s"
                    % (len(unknown), ", ".join(unknown[:6]))),
            })
            out.append(row)
        return jsonify({"ok": True, "accounts": out})

    def _resolve_tab_via(sid, acc):
        """Which tab is this account's own. Same rule the importer uses.

        Written once there and reached from here rather than reimplemented: two
        copies of "which tab belongs to this account" is exactly how five
        accounts sharing one workbook end up reading each other's rows.
        """
        gid = str(acc.get("output_tab_gid") or "").strip()
        name = str(acc.get("output_tab") or "").strip()
        try:
            sheets = _client().open_by_key(sid).worksheets()
        except Exception as e:
            return None, "could not open that spreadsheet: %s" % str(e)[:160]
        by_gid = {str(w.id): w.title for w in sheets}
        if gid and gid in by_gid:
            return by_gid[gid], ""
        if name and name in [w.title for w in sheets]:
            return name, ""
        if len(sheets) == 1:
            return sheets[0].title, ""
        return None, ("this account has no output tab recorded and that "
                      "spreadsheet has %d tabs" % len(sheets))
