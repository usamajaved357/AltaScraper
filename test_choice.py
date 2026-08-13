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

print("=== the default is unchanged ===")
clean_env()
check("nothing set -> sheets", choice.resolve(None, CFG), "sheets")
check("empty config -> sheets", choice.resolve({}, CFG), "sheets")
check("  and it says why", choice.decide({}, CFG)["source"], "the default")

print("\n=== the environment variable is honoured, once a database exists ===")
clean_env()
os.environ["ALTA_DATA_BACKEND"] = "db"
d = choice.decide({}, CFG)
check("db requested but no file -> falls back to sheets", d["backend"], "sheets")
check("  and says so plainly", "no database exists" in d["note"], True)
check("  while still recording what was asked for", d["requested"], "db")
open(DB, "wb").write(b"")            # now it exists
d = choice.decide({}, CFG)
check("db requested and the file exists -> db", d["backend"], "db")
check("  with no complaint", d["note"], "")
check("  attributed to the environment", "ALTA_DATA_BACKEND" in d["source"], True)

print("\n=== config.json is the fallback source ===")
clean_env()
check("data_backend in config -> db", choice.resolve({"data_backend": "db"}, CFG), "db")
check("  attributed to config.json",
      "config.json" in choice.decide({"data_backend": "db"}, CFG)["source"], True)
os.environ["ALTA_DATA_BACKEND"] = "sheets"
check("the environment outranks config.json",
      choice.resolve({"data_backend": "db"}, CFG), "sheets")

print("\n=== a typo cannot silently divert the app ===")
clean_env()
os.environ["ALTA_DATA_BACKEND"] = "sqlite"
d = choice.decide({}, CFG)
check("an unrecognised value -> sheets", d["backend"], "sheets")
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
check("  and an override with no file still falls back", d["backend"], "sheets")
open(os.environ["ALTASCRAPER_DB"], "wb").write(b"")
check("  ...but is accepted once that file exists", choice.resolve({}, CFG), "db")

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
