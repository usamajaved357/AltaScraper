"""The small security fixes from the master audit, each pinned by behaviour.

  1. the sign-in redirect only goes to this site's own pages
  2. a URL a user hands the app is fetched only if it is public
  3. an uploaded image's `kind` cannot steer where the file is written
  4. with no sign-in configured, a SERVER fails closed; a laptop does not
  5. one answer to "is this running on a hosting platform?"

None of it reaches the network: the URL checks are given a resolver.
Milestone 2, 28 Sep 2026.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


print("\n1. after signing in, only this site's own pages")
from routes.dash_auth_routes import _safe_next                         # noqa: E402
for raw, want in (("/w/jack_uk/sales", "/w/jack_uk/sales"),
                  ("https://evil.example", ""),
                  ("//evil.example", ""),
                  ("/\\evil.example", ""),          # browsers read \ as /
                  ("/\t/evil.example", ""),         # and drop the tab
                  ("/\n/evil.example", ""),
                  ("\\\\evil.example", ""),
                  ("", "")):
    check("next=%r" % raw, _safe_next(raw), want)

print("\n2. a URL from a user is fetched only if it is public")
from domain import url_policy as UP                                    # noqa: E402
PUBLIC = lambda h: ["93.184.216.34"]                                   # noqa: E731
for url, ips, refused in (
        ("https://images.example/a.jpg", ["93.184.216.34"], False),
        ("file:///etc/passwd", ["93.184.216.34"], True),
        ("ftp://x.example/a", ["93.184.216.34"], True),
        ("http://127.0.0.1:5000/diag", ["127.0.0.1"], True),
        ("http://localhost/", ["127.0.0.1"], True),
        ("http://169.254.169.254/latest/meta-data/", ["169.254.169.254"], True),
        ("http://10.0.0.5/", ["10.0.0.5"], True),
        ("http://192.168.1.1/", ["192.168.1.1"], True),
        ("http://[::1]/", ["::1"], True),
        ("http://mapped.example/", ["::ffff:127.0.0.1"], True),
        # A name that resolves to BOTH a public and a private address is
        # refused: the connection could land on either.
        ("http://split.example/", ["93.184.216.34", "10.1.1.1"], True),
        ("http:///nohost", [], True)):
    why = UP.refuse_reason(url, resolve=(lambda h, _i=ips: _i))
    check("%-44s %s" % (url, "refused" if refused else "allowed"), bool(why), refused)
try:
    UP.urlopen("file:///etc/passwd", timeout=1)
    check("urlopen refuses before sending anything", False, True)
except ValueError:
    check("urlopen refuses before sending anything", True, True)
# Every fetch of a user-supplied address goes through it.
for rel in ("routes/media_routes.py", "domain/source_scrape.py",
            "routes/optimize_routes.py", "domain/brand_listing.py",
            "miles_template.py", "dashboard.py"):
    src = open(os.path.join(HERE, *rel.split("/")), encoding="utf-8").read()
    check("%s fetches through the URL policy" % rel, "_urlp.urlopen(" in src, True)

# A picture handed to the image model is a PICTURE: a local path to anything
# else, or a /media path that climbs out of the media folder, is refused.
from domain import brand_listing as _BL                                # noqa: E402
check("a local non-image path is not read (it would be sent to the model)",
      _BL._img_to_data_url(os.path.join(HERE, "CLAUDE.md")), "")
check("  nor /media/../ climbing out of the media folder",
      _BL._img_to_data_url("/media/../CLAUDE.md"), "")

print("\n3. an image's `kind` cannot steer where it is written")
import re                                                              # noqa: E402
_MR = open(os.path.join(HERE, "routes", "media_routes.py"), encoding="utf-8").read()
_line = [l for l in _MR.splitlines() if "kind = re.sub(" in l]
check("kind is reduced to a safe set before use", len(_line), 1)
_sanitise = lambda k: re.sub(r"[^A-Za-z0-9_-]", "", str(k or ""))[:24] or "ref"  # noqa: E731
check("  ../../evil becomes harmless", "/" in _sanitise("../../evil"), False)
check("  and an empty one is 'ref'", _sanitise(""), "ref")
check("  it happens before the filename is built",
      _MR.index("kind = re.sub(") < _MR.index('fname = f"{kind}_'), True)

print("\n4. with no sign-in configured, a server fails closed")
from auth import guard as G                                            # noqa: E402
check("on a laptop the app stays open, as before",
      G.open_gate_allowed({}), True)
check("on Render it does not", G.open_gate_allowed({"RENDER": "true"}), False)
check("on Railway it does not",
      G.open_gate_allowed({"RAILWAY_ENVIRONMENT": "production"}), False)
check("unless someone says so, on purpose",
      G.open_gate_allowed({"RENDER": "true", "ALTASCRAPER_ALLOW_OPEN": "1"}), True)
check("  and only '1' says so",
      G.open_gate_allowed({"RENDER": "true", "ALTASCRAPER_ALLOW_OPEN": "yes"}), False)

print("\n5. one answer to 'is this hosted?'")
from config import hosting as H                                        # noqa: E402
check("render", H.platform({"RENDER_SERVICE_ID": "x"}), "render")
check("heroku", H.platform({"DYNO": "web.1"}), "heroku")
check("nothing set is not hosted", H.is_hosted({}), False)
_dups = []
for base in ("domain", "routes", "auth", "api", "config", "data"):
    for fn in os.listdir(os.path.join(HERE, base)):
        if fn.endswith(".py") and fn != "hosting.py":
            s = open(os.path.join(HERE, base, fn), encoding="utf-8").read()
            if re.search(r'environ\.get\("(RENDER|DYNO|RAILWAY_ENVIRONMENT)"\)', s):
                _dups.append(base + "/" + fn)
_d = open(os.path.join(HERE, "dashboard.py"), encoding="utf-8").read()
if re.search(r'environ\.get\("(RENDER|DYNO|RAILWAY_ENVIRONMENT)"\)', _d):
    _dups.append("dashboard.py")
check("no module asks it a second way", _dups, [])

print("\n6. a write started by another website is refused")
X = G.cross_site_refusal
check("the app's own fetch (same origin) passes",
      X("POST", "127.0.0.1:5000", "http://127.0.0.1:5000", ""), "")
check("the hosted app's own fetch passes",
      X("POST", "alta.onrender.com", "https://alta.onrender.com", ""), "")
check("a POST from another site is refused",
      bool(X("POST", "alta.onrender.com", "https://evil.example", "")), True)
check("  judged by Referer when there is no Origin",
      bool(X("POST", "alta.onrender.com", "",
             "https://evil.example/page")), True)
check("an opaque 'null' origin is refused, whatever the Referer says",
      bool(X("POST", "alta.onrender.com", "null", "")), True)
check("the browser's own Sec-Fetch-Site: cross-site is refused",
      bool(X("POST", "alta.onrender.com", "", "", "cross-site")), True)
check("  same-origin passes",
      X("POST", "alta.onrender.com", "https://alta.onrender.com", "", "same-origin"), "")
check("a GET that STARTS A RUN, from another site, is refused",
      bool(X("GET", "alta.onrender.com", "", "https://evil.example/",
             "cross-site", "/run/api_submit")), True)
check("  but the app's own stream is not",
      X("GET", "alta.onrender.com", "", "https://alta.onrender.com/w/x/listings",
        "same-origin", "/run/api_submit"), "")
check("  nor a typed address (Sec-Fetch-Site: none)",
      X("GET", "alta.onrender.com", "", "", "none", "/run/generate"), "")
check("/run/plan is a read, not work", G._work_over_get("/run/plan"), False)
check("a lookalike host is still another site",
      bool(X("POST", "alta.onrender.com", "https://alta.onrender.com.evil.example",
             "")), True)
check("reads are not judged (links from anywhere still open)",
      X("GET", "alta.onrender.com", "https://evil.example", ""), "")
check("no Origin and no Referer is left to the sign-in check",
      X("POST", "alta.onrender.com", "", ""), "")
from flask import Flask                                                # noqa: E402
_a = Flask(__name__)
G.harden_session(_a)
check("the session cookie is SameSite=Lax",
      _a.config.get("SESSION_COOKIE_SAMESITE"), "Lax")
check("  and HttpOnly", _a.config.get("SESSION_COOKIE_HTTPONLY"), True)
_d = open(os.path.join(HERE, "dashboard.py"), encoding="utf-8").read()
check("the app applies it", "_harden_session(app)" in _d, True)
_gsrc = open(os.path.join(HERE, "auth", "guard.py"), encoding="utf-8").read()
_door = _gsrc[_gsrc.index("def _require_login"):]
check("the doorman checks it before anything else, public pages included",
      _door.index("cross_site_refusal(") < _door.index("PUBLIC_ENDPOINTS"), True)

print("\n7. all-account lists show only the accounts the caller may open")
from auth import users as U                                            # noqa: E402
_real_get = U.get_user
_people = {"nest": {"id": "nest", "active": True, "workspaces": ["nestwell_goods"]},
           "boss": {"id": "boss", "active": True, "workspaces": ["*"]}}
U.get_user = lambda cp, uid: _people.get(uid)
_ACCTS = [{"id": "jack_uk"}, {"id": "nestwell_goods"}]
_a.secret_key = "test-only-not-a-secret"
try:
    for who, want_ids, sees_all in (("nest", ["nestwell_goods"], False),
                                    ("boss", ["jack_uk", "nestwell_goods"], True),
                                    (None, ["jack_uk", "nestwell_goods"], True)):
        with _a.test_request_context("/"):
            from flask import session
            if who:
                session["uid"] = who
            check("%s: visible_accounts" % (who or "no one signed in"),
                  [a["id"] for a in U.visible_accounts("x", _ACCTS)], want_ids)
            check("%s: sees every account" % (who or "no one signed in"),
                  U.caller_sees_every_account("x"), sees_all)
finally:
    U.get_user = _real_get
for rel, needle in (("routes/backup_routes.py", "visible_accounts(CONFIG_PATH, _accounts())"),
                    ("routes/migrate_routes.py", "visible_accounts(CONFIG_PATH, _accounts())"),
                    ("routes/aiusage_routes.py", "_scope_for_caller(only)")):
    src = open(os.path.join(HERE, *rel.split("/")), encoding="utf-8").read()
    check("%s is scoped to the caller" % rel, needle in src, True)
_ai = open(os.path.join(HERE, "routes", "aiusage_routes.py"), encoding="utf-8").read()
check("  both usage views are", _ai.count("= _scope_for_caller(only)"), 2)

print("\n8. a named account never borrows another account's credentials")
from routes import scope as SC                                         # noqa: E402
_open = {"id": "jack_uk", "marketplaces": ["UK"], "lwa_client_id": "OPEN-ACCT"}
acc, wsid, mkt = SC.resolve(state={}, account=_open, asked_id="ghost_acct",
                            load_account=lambda aid: None)
check("an id that cannot be loaded gets NO record, not the open one's", acc, {})
check("  and the id stays the one asked for", wsid, "ghost_acct")
acc, wsid, mkt = SC.resolve(state={}, account=_open, asked_id="nestwell_goods",
                            load_account=lambda aid: {"id": aid, "marketplaces": ["UK"]})
check("an id that loads gets its OWN record", acc.get("id"), "nestwell_goods")
check("'__all__' selected is not a country",
      SC.marketplace(state={"active_marketplace": "__all__"}, account={}), "")

print("\n%d checks, %d failed" % (len(ran), len(fails)))
print("FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
