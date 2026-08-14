"""domain/backup.py -- what protects the data once the database is the only store.

WHY THIS HAS TO EXIST BEFORE SHEETS CAN BE SWITCHED OFF

Google Sheets is currently the app's accidental backup. That is a real job it
does, and it is the actual reason turning it off feels risky. The database lives
on a persistent disk, which survives deploys and restarts -- but it is ONE disk
with no snapshot, so removing Sheets without replacing that trades a sync
problem for a single-copy problem, which is worse.

So Sheets changes role rather than disappearing: it stops being the store and
becomes the backup, which is the thing it is genuinely good at. Nothing is ever
read back from a backup, so the sync problem cannot return through this door.

TWO LAYERS, because they fail differently:

  the nightly export   covers routine loss -- a mistake, a bad import, a disk
                       gone. Readable: you can open it and see your listings.
  the snapshot file    covers the moment before something deliberate and
                       risky. Exact, restorable, and taken on demand.

THE TRAP THIS FILE IS CAREFUL ABOUT
An export written into a tab the app READS would come straight back as live
data -- a deleted listing would reappear at the next backup, and the sync
problem would be recreated by the very thing meant to end it. So backups go to
their own tab, named with a prefix the reading side is taught to skip, and the
name is defined here so the two halves cannot drift apart.
"""
import os
import shutil
import sqlite3
import tempfile
import threading
import time

# Tabs whose name starts with this are BACKUPS, never a source. routes/
# listing_routes.py skips them when reading a workbook -- see BACKUP_TAB_PREFIX
# there. Changing this string means changing it in both places, which is why it
# is imported rather than typed twice.
BACKUP_TAB_PREFIX = "backup_"


def backup_tab_name(workspace_id):
    """The tab one workspace's listings are backed up into."""
    safe = "".join(ch for ch in str(workspace_id or "") if ch.isalnum() or ch in "._-")
    return BACKUP_TAB_PREFIX + (safe[:60] or "listings")


def snapshot(config_path, dest_path=None):
    """A consistent copy of the whole database. -> the path written.

    Uses SQLite's own backup API rather than copying the file. The database runs
    in WAL mode, so at any moment the committed data is split between the .db
    and the .db-wal; copying just the file can produce something that is missing
    the most recent writes or is outright unreadable. The backup API takes a
    proper snapshot of a live database while it is being written to.
    """
    from data import db as _db
    src_path = _db.db_path(config_path)
    if not dest_path:
        fd, dest_path = tempfile.mkstemp(prefix="altascraper-", suffix=".db")
        os.close(fd)
    src = sqlite3.connect(src_path)
    try:
        dst = sqlite3.connect(dest_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return dest_path


def export_workspace(gc, config_path, workspace_id, spreadsheet_id):
    """Push ONE workspace's listings into its backup tab. -> a result dict.

    One way only. This never reads the sheet, and never touches the tab the app
    reads from.
    """
    from data.store import ListingStore
    store = ListingStore(workspace_id, config_path=config_path)
    tab = backup_tab_name(workspace_id)
    rows = store.row_count()
    if not rows:
        # Refusing to write an empty backup over a good one is the whole point.
        # A workspace with nothing in it is normal early in the migration, and
        # blanking its backup would destroy the copy that still had something.
        return {"workspace": workspace_id, "tab": tab, "rows": 0,
                "skipped": True,
                "note": "nothing in the database for this workspace, so its "
                        "existing backup was left alone"}
    store.export_to_sheet(gc, spreadsheet_id, tab=tab)
    return {"workspace": workspace_id, "tab": tab, "rows": rows, "skipped": False}


def export_all(gc, config_path, accounts, log=None):
    """Back up every account that has somewhere to back up to."""
    said = log or (lambda m: None)
    out = []
    for a in (accounts or []):
        aid = str(a.get("id") or "").strip()
        sid = str(a.get("output_spreadsheet_id") or "").strip()
        if not aid:
            continue
        if not sid:
            out.append({"workspace": aid, "skipped": True,
                        "note": "no spreadsheet configured to back up to"})
            continue
        try:
            r = export_workspace(gc, config_path, aid, sid)
            said("backed up %s -> %s (%d rows)" % (aid, r["tab"], r["rows"]))
            out.append(r)
        except Exception as e:
            said("backup FAILED for %s: %s" % (aid, str(e)[:160]))
            out.append({"workspace": aid, "error": str(e)[:200]})
    return out


class Nightly(object):
    """Runs export_all once a day, in the background.

    Deliberately simple: a thread that wakes hourly and exports when the last
    successful run was over a day ago. No cron, no scheduler service -- the app
    is one process on one box, and a backup that depends on more moving parts
    than the thing it protects is not a backup.

    It never raises into the app. A failed backup is reported and retried; it
    must not be able to take the site down.
    """

    def __init__(self):
        self.last_ok = 0.0
        self.last_error = ""
        self.last_result = []
        self.running = False
        self._thread = None

    def status(self):
        return {"running": self.running,
                "last_ok": self.last_ok,
                "last_ok_ago_hours": (round((time.time() - self.last_ok) / 3600.0, 1)
                                      if self.last_ok else None),
                "last_error": self.last_error,
                "last_result": self.last_result}

    def run_once(self, gc_factory, config_path, accounts_factory, log=None):
        said = log or (lambda m: None)
        try:
            res = export_all(gc_factory(), config_path, accounts_factory(), log=said)
            self.last_result = res
            self.last_error = ""
            self.last_ok = time.time()
            return res
        except Exception as e:
            self.last_error = str(e)[:300]
            said("nightly backup failed: %s" % self.last_error)
            return []

    def start(self, gc_factory, config_path, accounts_factory, log=None,
              every_hours=24):
        if self.running:
            return
        said = log or (lambda m: None)

        def _loop():
            # A pause before the first run so a restart loop cannot turn into a
            # burst of exports, and so boot is never slowed by one.
            time.sleep(120)
            while True:
                try:
                    if (time.time() - self.last_ok) > every_hours * 3600:
                        self.run_once(gc_factory, config_path, accounts_factory, said)
                except Exception:
                    pass
                time.sleep(3600)

        self.running = True
        self._thread = threading.Thread(target=_loop, name="alta-backup", daemon=True)
        self._thread.start()
        said("nightly backup armed (every %dh)" % every_hours)


NIGHTLY = Nightly()
