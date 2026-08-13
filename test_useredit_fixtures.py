"""Capture the REAL /users/list response so the JS test uses real data."""
import sys, os, json, tempfile
sys.path.insert(0, r"D:\AltaScraper")
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
