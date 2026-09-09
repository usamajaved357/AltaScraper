"""One store, decided once -- and every reporter tells the truth about it.

The bug: dashboard.py decided from a function argument the deployed app never
set, the generator read ALTA_DATA_BACKEND, and /diag + /users/me reported the
environment variable. So the two halves of the app could read different stores
while the diagnostics confidently reported the wrong one.
"""
import os, sys, json, tempfile, shutil
sys.path.insert(0, r"D:\AltaScraper")
from data import choice
from data import db as ddb

fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))

TMP = tempfile.mkdtemp(prefix="altachoice_")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w").write("{}")
DB = os.path.join(TMP, "altascraper.db")

def clean_env():
    for k in ("ALTA_DATA_BACKEND", "ALTASCRAPER_DB", "CONFIG_PATH"):
        os.environ.pop(k, None)

# ============================================================================
# REWRITTEN 9 Sep 2026 -- THE SPREADSHEET IS UNLINKED, SO THERE IS NO CHOICE.
# ============================================================================
#
#     "i thought the google sheets are permanently removed from the workflow,
#      unlink the google sheets permanently from my app wherever they are"
#
# Everything below used to test a DECISION between two stores, and most of the
# cases were about falling back to the sheet safely. There is nothing to fall
# back to now. What each case was originally protecting is kept in its comment,
# because those were real incidents and the reasoning is why the code looks the
# way it does -- but the expected ANSWER is the database in every one of them.
#
# The request is still parsed, still attributed and still reported. Only the
# answer is fixed. See data/choice.py and test_sheets_unlinked.py.

print("=== there is one store, and it is the database ===")
# ORIGINALLY: "with NO database the sheet is still the default", because a fresh
# install starting on an empty database would look like lost data. That reasoning
# has expired -- data/db.get_db creates the file and the schema on first use, so
# "no database" is a state that lasts until something touches it, and there is no
# sheet to show instead.
clean_env()
check("nothing set, no database -> db", choice.resolve(None, CFG), "db")
check("empty config, no database -> db", choice.resolve({}, CFG), "db")
check("  and it still says where the answer came from",
      choice.decide({}, CFG)["source"], "the default (no database exists yet)")

print("\n=== a database being there changes nothing, but is still reported ===")
# The bug this closed: an account fully migrated, 283 listings in the database,
# and still reading Google Sheets because nobody had written "db" anywhere and
# the default sent it back. Every screen then correctly said "your sheet", which
# looked like the migration had failed when it was the default that had.
open(DB, "wb").write(b"")
clean_env()
check("nothing set, database present -> db", choice.resolve(None, CFG), "db")
check("  and it names the file it found",
      DB in choice.decide({}, CFG)["source"], True)
check("  with no complaint", choice.decide({}, CFG)["note"], "")
# ASKING FOR THE SHEET IS NOW OVERRULED, not obeyed -- and said out loud.
d = choice.decide({"data_backend": "sheets"}, CFG)
check("an explicit 'sheets' is overruled", d["backend"], "db")
check("  and told it is being ignored", "permanently unlinked" in d["note"], True)
check("  while still recording what was asked for", d["requested"], "sheets")
clean_env()
os.environ["ALTA_DATA_BACKEND"] = "sheets"
check("  the environment variable cannot do it either",
      choice.resolve({}, CFG), "db")
clean_env()
os.remove(DB)
check("deleting the database does not bring the sheet back",
      choice.resolve(None, CFG), "db")

print("\n=== the request is still parsed and attributed ===")
clean_env()
os.environ["ALTA_DATA_BACKEND"] = "db"
d = choice.decide({}, CFG)
# ORIGINALLY: "db requested but no file -> falls back to sheets", so a server
# whose database had been wiped by a deploy would not start up showing nothing.
# The fallback is gone with the sheet; get_db creates the file.
check("db requested but no file -> still db", d["backend"], "db")
check("  while still recording what was asked for", d["requested"], "db")
open(DB, "wb").write(b"")            # now it exists
d = choice.decide({}, CFG)
check("db requested and the file exists -> db", d["backend"], "db")
check("  with no complaint", d["note"], "")
check("  attributed to the environment", "ALTA_DATA_BACKEND" in d["source"], True)

print("\n=== config.json is still read, and the environment still outranks it ===")
clean_env()
check("data_backend in config -> db", choice.resolve({"data_backend": "db"}, CFG), "db")
check("  attributed to config.json",
      "config.json" in choice.decide({"data_backend": "db"}, CFG)["source"], True)
os.environ["ALTA_DATA_BACKEND"] = "sheets"
# The ANSWER cannot differ any more, so precedence is checked on what was
# REQUESTED -- which is the part that still varies and still has to be right.
d = choice.decide({"data_backend": "db"}, CFG)
check("the environment still outranks config.json", d["requested"], "sheets")
check("  and is named as the source", "ALTA_DATA_BACKEND" in d["source"], True)

print("\n=== a typo is still named, even though it can no longer divert ===")
# This one nearly went missing. The early return would have swallowed it: the
# app does the right thing and says nothing, so the misspelling stays in the
# config for the next person to puzzle over. The answer cannot change; the fact
# that somebody asked for something that is not a store still can.
clean_env()
os.environ["ALTA_DATA_BACKEND"] = "sqlite"
d = choice.decide({}, CFG)
check("an unrecognised value -> db", d["backend"], "db")
check("  and names the mistake", "not a recognised store" in d["note"], True)
clean_env()
check("'DB' in capitals still works", choice.resolve({"data_backend": "DB"}, CFG), "db")
check("whitespace is tolerated", choice.resolve({"data_backend": " db "}, CFG), "db")

print("\n=== the db path is not re-derived (Rule 12) ===")
clean_env()
check("choice agrees with data/db.py", choice.db_path(CFG), ddb.db_path(CFG))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "elsewhere.db")
check("ALTASCRAPER_DB is honoured", choice.db_path(CFG), os.environ["ALTASCRAPER_DB"])
os.environ["ALTA_DATA_BACKEND"] = "db"
d = choice.decide({}, CFG)
# ORIGINALLY: an override pointing at a file that is not there fell back to the
# sheet rather than starting empty. Nothing to fall back to now, and get_db
# creates whatever ALTASCRAPER_DB points at.
check("  an override with no file is still the database", d["backend"], "db")
open(os.environ["ALTASCRAPER_DB"], "wb").write(b"")
check("  ...and once that file exists, unchanged", choice.resolve({}, CFG), "db")

print("\n=== the generator now asks the same question ===")
clean_env()
sys.path.insert(0, r"D:\AltaScraper")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "_alg_probe", r"D:\AltaScraper\amazon_listing_generator.py")
src = open(r"D:\AltaScraper\amazon_listing_generator.py", encoding="utf-8").read()
check("the generator delegates to data/choice",
      "_choice.resolve(config" in src, True)
check("  and no longer reads the variable itself",
      'os.environ.get("ALTA_DATA_BACKEND")' in src, False)

print("\n=== every reporter reads the RESULT, not the request ===")
for f, needle, gone in (
    (r"D:\AltaScraper\routes\users_routes.py",
     'current_app.config.get("DATA_BACKEND")', 'os.environ.get("ALTA_DATA_BACKEND")'),
    (r"D:\AltaScraper\domain\deploy_check.py",
     "_choice.decide", 'os.environ.get("ALTA_DATA_BACKEND")'),
    (r"D:\AltaScraper\dashboard.py",
     'app.config["DATA_BACKEND"]', None),
):
    s = open(f, encoding="utf-8").read()
    name = os.path.basename(f)
    check("%s reports the running store" % name, needle in s, True)
    if gone:
        check("  %s no longer re-reads the environment" % name, gone in s, False)

shutil.rmtree(TMP, ignore_errors=True)
clean_env()
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
