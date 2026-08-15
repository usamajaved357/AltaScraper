"""archive_sheets.py -- take a copy of everything in Google Sheets, then stop needing it.

WHY
"i dont need google sheets in my workflow ... make the backup of data what
google sheets have in database yourself and make it detached from my app".

The database already holds the listings -- a dry run of /migrate/import reports
0 rows that exist only in Sheets, across every account. But "the importer says
there is nothing left" and "there is nothing left" are not the same sentence, and
the difference is only discovered after the spreadsheets are gone. So this writes
a plain, complete copy of every listing-shaped tab to a file first.

WHAT IT WRITES
sheets_archive_<date>.json beside config.json -- so it lands on the persistent
disk in production, not in the container that the next deploy replaces. Every
tab, every row, exactly as Google returned it, with no interpretation applied.
An archive that has been tidied up is not an archive.

READS ONLY. Nothing is written to any spreadsheet and nothing in one is changed.

    python archive_sheets.py                 archive every account
    python archive_sheets.py --account jack_uk
    python archive_sheets.py --list          say what would be archived, write nothing
"""
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, r"D:\AltaScraper")

SKU_ALIASES = ("SKU", "Sku", "sku")


def main(argv):
    only = None
    if "--account" in argv:
        try:
            only = argv[argv.index("--account") + 1]
        except IndexError:
            pass
    listing_only = "--list" in argv

    import dashboard as D
    from domain import jsonstore as _js

    cfg = D._cfg()
    accounts = (cfg.get("accounts") or [])
    if only:
        accounts = [a for a in accounts if str(a.get("id")) == only]
        if not accounts:
            print("no account called %r" % only)
            return 1

    # ONE PASS PER WORKBOOK, not per account. Five of these accounts share a
    # single spreadsheet, so archiving per account read the same fifteen tabs six
    # times over and earned a 429 from Google half way through -- leaving an
    # archive with holes in it, which is worse than no archive because it looks
    # finished. Books are keyed by id and each is read once; the accounts that
    # share one all point at the same copy.
    out = {"taken_at": dt.datetime.now().isoformat(timespec="seconds"),
           "books": {}, "accounts": {}}
    total_rows = 0

    by_book = {}
    for a in accounts:
        aid = str(a.get("id") or "")
        sid = str(a.get("output_spreadsheet_id") or "").strip()
        out["accounts"][aid] = {"label": a.get("label") or aid,
                                "spreadsheet_id": sid,
                                "output_tab_gid": str(a.get("output_tab_gid") or "")}
        if sid:
            by_book.setdefault(sid, []).append(aid)
        else:
            out["accounts"][aid]["note"] = "no output spreadsheet configured"
            print("%-20s (no spreadsheet)" % aid)

    for sid, owners in by_book.items():
        rec = {"spreadsheet_id": sid, "used_by": owners, "tabs": {}}
        out["books"][sid] = rec
        try:
            book = D._client().open_by_key(sid)
            tabs = book.worksheets()
        except Exception as e:
            rec["error"] = str(e)[:200]
            print("%-24s COULD NOT OPEN: %s" % (sid[:24], str(e)[:60]))
            continue

        print("\n%s  %d tabs   used by: %s"
              % (sid[:24], len(tabs), ", ".join(owners)))
        for ws in tabs:
            title = str(ws.title or "")
            values = None
            # Google's per-minute read quota is easy to reach on a workbook this
            # size. A 429 is a "come back shortly", not a failure, so it waits
            # and tries again rather than leaving a hole in the archive.
            for attempt in range(4):
                try:
                    values = ws.get_all_values()
                    break
                except Exception as e:
                    msg = str(e)
                    if "429" in msg or "Quota exceeded" in msg:
                        wait = 20 * (attempt + 1)
                        print("     %-30s quota -- waiting %ds" % (title[:30], wait))
                        time.sleep(wait)
                        continue
                    rec["tabs"][title] = {"error": msg[:160]}
                    print("     %-30s ERROR %s" % (title[:30], msg[:50]))
                    break
            if values is None:
                if title not in rec["tabs"]:
                    rec["tabs"][title] = {"error": "quota exceeded after retries"}
                    print("     %-30s GAVE UP (quota)" % title[:30])
                continue
            header = values[0] if values else []
            is_listing = (any(s in header for s in SKU_ALIASES)
                          and "Title" in header)
            body = values[1:] if len(values) > 1 else []
            rec["tabs"][title] = {
                "gid": str(ws.id),
                "listing_shaped": bool(is_listing),
                "header": header,
                "rows": [] if listing_only else body,
                "row_count": len(body),
            }
            total_rows += len(body)
            print("     %-30s %5d rows%s"
                  % (title[:30], len(body), "  (listings)" if is_listing else ""))

    out["total_rows"] = total_rows
    if listing_only:
        print("\n--list: %d rows would be archived. Nothing written." % total_rows)
        return 0

    # A HOLE IN AN ARCHIVE IS WORSE THAN NO ARCHIVE, because it looks finished.
    # Every failure is counted and said out loud, and the exit code carries it,
    # so nothing downstream can treat a partial copy as a complete one.
    holes = [(sid, t) for sid, b in out["books"].items()
             for t, v in (b.get("tabs") or {}).items() if v.get("error")]
    holes += [(sid, "(whole book)") for sid, b in out["books"].items()
              if b.get("error")]

    name = "sheets_archive_%s.json" % dt.date.today().isoformat()
    path = _js.path_beside_config(D.CONFIG_PATH, name)
    _js.write_json_atomic(path, out, indent=1)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    print("\nwrote %s" % path)
    print("  %d rows from %d workbook(s), %.1f MB"
          % (total_rows, len(out["books"]), size / 1048576.0))
    print("\nThe spreadsheets were only read. Nothing in them was changed.")

    if holes:
        print("\nINCOMPLETE -- %d tab(s) could not be read:" % len(holes))
        for sid, t in holes[:20]:
            print("   %s :: %s" % (sid[:16], t))
        print("\nDo NOT treat this as a full backup. Run it again.")
        return 2
    print("\nComplete: every tab in every workbook was read.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
