# -*- coding: utf-8 -*-
"""WHO DID IT: one wording, and no lookup that can only ever answer "".

Found while designing the activity log (29 Sep 2026, docs/known-issues.md):
  * Dr PPC's _who() called auth.guard.current_user(), which does not exist; the
    except hid it, so every plan, rule and event was stored with who="".
  * The repricer's manual price read session["user"], which nothing sets, so
    every manual price said "set by hand".
  * The error log read session["email"], which nothing sets.
All three now use domain/job_owner.label(), the same wording the upload
history uses (email, else name, else the id; "" when nobody is signed in).
"""
import json
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
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def read(*p):
    return open(os.path.join(HERE, *p), encoding="utf-8").read()


TMP = tempfile.mkdtemp(prefix="altawho_")
CFG = os.path.join(TMP, "app.json")
json.dump({"accounts": []}, open(CFG, "w"))

from flask import Flask, session                 # noqa: E402
from auth import users as U                      # noqa: E402
from domain import job_owner as JO, upload_log as UL   # noqa: E402

ali = U.create_user(CFG, "ali@example.test", name="Ali", role="lister")[0]["id"]
noname = U.create_user(CFG, "", name="", role="viewer")
app = Flask(__name__)
app.secret_key = "t"

print("== one wording ==")
with app.test_request_context("/"):
    session["uid"] = ali
    check("a signed-in person is named by email", JO.label(CFG), "ali@example.test")
    check("  the upload history says the same", UL.uploader(CFG), JO.label(CFG))
    session["uid"] = "u_gone"
    check("a deleted person keeps their id", JO.label(CFG), "u_gone")
    session.pop("uid")
    check("nobody signed in (shared password) is empty", JO.label(CFG), "")
check("outside a request (background work) is empty", JO.label(CFG), "")

print("== no lookup that can only answer '' ==")
def code(*p):
    """The file without comment lines (the fixes' comments quote the old calls)."""
    return "\n".join(l for l in read(*p).splitlines() if not l.lstrip().startswith("#"))


drppc = code("routes", "drppc_console_routes.py")
sourcing = code("routes", "sourcing_routes.py")
dash = code("dashboard.py")
check("Dr PPC no longer calls the missing guard.current_user()",
      bool(re.search(r"\bcurrent_user\(\)", drppc)), False)
check("  and names people through job_owner.label", "_jo.label(CONFIG_PATH)" in drppc, True)
check("the manual price no longer reads session['user']",
      bool(re.search(r"""session\w*\.get\(["']user["']\)""", sourcing)), False)
check("  and names people through job_owner.label", "_jo.label(CONFIG_PATH)" in sourcing, True)
check("the error log no longer reads session['email']",
      'session.get("email")' in dash, False)
from auth import guard as G                      # noqa: E402
check("(guard.current_user really does not exist)", hasattr(G, "current_user"), False)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.exit(1 if fails else 0)
