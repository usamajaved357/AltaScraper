# -*- coding: utf-8 -*-
"""The processes the app STARTS find the data disk, not the code folder.

The listing generator and the SP-API diagnosis run as their own processes,
from the code folder (/app on the server) -- while the data lives on the disk
at CONFIG_PATH (/data). Found in the deployment audit (29 Sep 2026):
  * the generator recorded its AI spend against the literal "config.json", so
    every listing run's spend went to a throwaway /app/altascraper.db, lost on
    each deploy and never on the AI spend screen; its account lookup too;
  * sp_diagnose.py never read CONFIG_PATH, so on the server it looked for
    /app/config.json.
This pins that both use CONFIG_PATH, and proves the database a relative name
would have used is NOT the data disk's.
"""
import os
import re
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
    print("  %-72s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def code(name):
    return "\n".join(l for l in open(os.path.join(HERE, name), encoding="utf-8").read().splitlines()
                     if not l.lstrip().startswith("#"))


gen = code("amazon_listing_generator.py")
check("generator: AI spend recorder uses CONFIG_PATH",
      "install_anthropic_recorder(str(CONFIG_PATH))" in gen, True)
check("generator: AI spend context uses CONFIG_PATH", "config_path=str(CONFIG_PATH)" in gen, True)
check("generator: account lookup uses CONFIG_PATH",
      "get_account(config, _cli_account_id, str(CONFIG_PATH))" in gen, True)
check("generator: no call passes the bare literal \"config.json\"",
      re.findall(r'\(\s*"config\.json"\s*\)|,\s*"config\.json"\s*\)|config_path\s*=\s*"config\.json"', gen), [])

# Why it mattered: the database a relative "config.json" resolves to follows the
# WORKING folder, not CONFIG_PATH.
from data import db as D                       # noqa: E402
old = os.environ.pop("ALTASCRAPER_DB", None)
os.environ["CONFIG_PATH"] = os.path.join(tempfile.gettempdir(), "datadisk", "config.json")
try:
    check("a relative name misses the data disk (the bug, measured)",
          os.path.dirname(D.db_path("config.json")) == os.path.dirname(os.environ["CONFIG_PATH"]), False)
    check("CONFIG_PATH reaches it",
          os.path.dirname(D.db_path(os.environ["CONFIG_PATH"])) == os.path.dirname(os.environ["CONFIG_PATH"]), True)
finally:
    os.environ.pop("CONFIG_PATH", None)
    if old is not None:
        os.environ["ALTASCRAPER_DB"] = old

spd = code("sp_diagnose.py")
check("sp_diagnose reads CONFIG_PATH first", 'os.environ.get("CONFIG_PATH")' in spd, True)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.exit(1 if fails else 0)
