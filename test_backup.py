"""What protects the data once the database is the only store.

Google Sheets is currently the app's accidental backup, and that is the real
reason switching it off feels risky. The database sits on a persistent disk --
it survives deploys and restarts -- but it is ONE disk with no snapshot. Remove
Sheets without replacing that and a sync problem has been traded for a
single-copy problem, which is worse.

So Sheets changes role: it stops being the store and becomes the backup, which
is the job it is actually good at. Nothing is ever read back from a backup, so
the sync problem cannot return through this door.

THE TRAP THIS FILE EXISTS FOR
An export written into a tab the app READS comes straight back as live data: a
listing deleted in the app would reappear at the next backup, recreated by the
very thing meant to end the problem. So backups go to their own tab, and the
reading side is taught to skip that prefix. Both halves are checked here,
because either one alone is useless.
"""
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from domain import backup as B

print("=== a backup tab is named so it cannot be mistaken for a source ===")
truthy("there is a prefix", B.BACKUP_TAB_PREFIX)
check("the tab for a workspace carries it",
      B.backup_tab_name("jack_uk").startswith(B.BACKUP_TAB_PREFIX), True)
check("a workspace id with awkward characters is made safe",
      B.backup_tab_name("jack uk/2024"), B.BACKUP_TAB_PREFIX + "jackuk2024")

print("\n=== and the reading side skips it ===")
# Either half alone is useless: naming the tab achieves nothing if the reader
# still picks it up, and skipping achieves nothing if the writer picks another
# name. So the reader must import the prefix, not repeat it.
LR = open("routes/listing_routes.py", encoding="utf-8").read()
truthy("the listings route skips backup tabs", "BACKUP_TAB_PREFIX" in LR)
truthy("  by importing the prefix rather than repeating the string",
       "from domain.backup import BACKUP_TAB_PREFIX" in LR)

print("\n=== the snapshot is a real, readable database ===")
# Taken with SQLite's backup API, not a file copy: the database runs in WAL
# mode, so at any moment the committed data is split between the .db and the
# .db-wal and a plain copy can be missing the newest writes or be unreadable.
tmp = tempfile.mkdtemp()
cfg = os.path.join(tmp, "config.json")
open(cfg, "w", encoding="utf-8").write('{"data_backend": "db"}')
from data import db as _db
conn = _db.get_db(cfg)
conn.execute("INSERT INTO listings (workspace_id, sku, title) VALUES (?,?,?)",
             ("t_ws", "SKU-BACKUP-1", "A listing worth keeping"))

dest = os.path.join(tmp, "snap.db")
out = B.snapshot(cfg, dest)
check("it wrote where it was told", out, dest)
truthy("the file exists", os.path.exists(dest))
c2 = sqlite3.connect(dest)
got = c2.execute("SELECT title FROM listings WHERE sku=?", ("SKU-BACKUP-1",)).fetchone()
check("and the row is in it", got[0] if got else None, "A listing worth keeping")
# A write made AFTER the snapshot must not be in it -- that is what makes it a
# snapshot rather than a live view.
conn.execute("INSERT INTO listings (workspace_id, sku, title) VALUES (?,?,?)",
             ("t_ws", "SKU-BACKUP-2", "Added later"))
later = c2.execute("SELECT COUNT(*) FROM listings WHERE sku=?", ("SKU-BACKUP-2",)).fetchone()[0]
check("a later write is not in the snapshot", later, 0)
c2.close()
_db.close_db()

print("\n=== an empty workspace never blanks a good backup ===")
# The failure that would matter most: a workspace that has not been migrated
# yet has nothing in the database, and writing that emptiness over its backup
# would destroy the only remaining copy.
class _FakeGC(object):
    def __init__(self): self.wrote = []
    def open_by_key(self, k): raise AssertionError(
        "export_workspace opened a sheet for an EMPTY workspace -- it must not")

res = B.export_workspace(_FakeGC(), cfg, "workspace_with_nothing", "sheet123")
check("it skips instead of exporting", res["skipped"], True)
check("  and says why", "nothing in the database" in res["note"], True)

print("\n=== the daily job cannot take the app down ===")
n = B.Nightly()
# A backup that raises must be recorded and swallowed, never propagated: a
# failed backup is not a reason for the site to stop working.
def _boom():
    raise RuntimeError("google is having a day")
res = n.run_once(_boom, cfg, lambda: [{"id": "a", "output_spreadsheet_id": "s"}])
check("a failure returns rather than raising", res, [])
truthy("  and is remembered so it can be reported", n.last_error)
check("  and does not count as a successful run", n.last_ok, 0.0)

print("\n=== the routes are wired and guarded ===")
G = open("auth/guard.py", encoding="utf-8").read()
truthy("reading the status is open to any signed-in user",
       '("/backup/status",                  None)' in G)
truthy("checking parity is open too", '("/backup/verify",                  None)' in G)
# The download is every account's listings, costs and prices in one file.
truthy("downloading the whole dataset is not",
       '("/backup/download",                "manage_accounts")' in G)
truthy("nor is writing a backup",
       '("/backup/run",                     "manage_accounts")' in G)

D = open("dashboard.py", encoding="utf-8").read()
truthy("the routes are registered", "backup_routes.register" in D)
truthy("and the daily job is armed at boot", "NIGHTLY.start" in D)

print("\n=== it answers over HTTP ===")
import dashboard as _D
app = _D.build_app()
app.config["TESTING"] = True
with app.test_client() as c:
    with c.session_transaction() as s:
        s["user"] = "owner"; s["role"] = "owner"; s["is_owner"] = True
    j = c.get("/backup/status").get_json() or {}
    truthy("the status answers", j.get("ok"))
    truthy("  in words, not just numbers", j.get("says"))
    v = c.get("/backup/verify").get_json() or {}
    truthy("the parity check answers", v.get("ok"))
    for row in (v.get("accounts") or [])[:4]:
        # The verdict is the line someone acts on, so every account must have
        # one -- including the ones that errored.
        truthy("  %s has a verdict or a reason" % row.get("id"),
               row.get("verdict") or row.get("error"))
    r = c.get("/backup/download")
    check("the download returns a file", r.status_code, 200)
    truthy("  which is actually a SQLite database",
           r.data[:16].startswith(b"SQLite format 3"))

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
