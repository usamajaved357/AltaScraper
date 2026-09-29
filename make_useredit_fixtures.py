"""Capture the REAL /users/list response so the JS test uses real data."""
# THE TREE THIS TEST LIVES IN. It used to name the main checkout outright, so
# run from any other checkout it silently tested THAT checkout's code
# (Milestone 1, 28 Sep 2026: 141 files did this).
import os as _os_repo
_REPO = _os_repo.path.dirname(_os_repo.path.abspath(__file__))
import sys, os, json, tempfile
sys.path.insert(0, _REPO)
from flask import Flask
import routes.users_routes as users_routes
from auth import users

TMP = tempfile.mkdtemp(prefix="alta_ul_")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w").write("{}")

app = Flask(__name__)
app.secret_key = "t"
users_routes.register(app, CONFIG_PATH=CFG)

users.create_user(CFG, email="va@example.com", name="Aisha", role="lister",
                  permissions=["edit"], workspaces=["nestwell"])

with app.test_client() as c:
    with c.session_transaction() as s:
        s["authed"] = True
    j = c.get("/users/list").get_json()
    m = c.get("/users/me").get_json()

open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(j, indent=1))
open(sys.argv[2], "w", encoding="utf-8").write(json.dumps(m, indent=1))
print("keys from /users/list:", ", ".join(sorted(j.keys())))
print("keys from /users/me  :", ", ".join(sorted(m.keys())))
print("features on the record:", json.dumps(j["users"][0]["features"]))
