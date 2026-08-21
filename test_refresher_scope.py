"""The background rotation must be allowed to refresh accounts nobody has open.

    That is the whole reason it exists, and the account guard was refusing it.

WHAT WAS MEASURED, in the server log, with jack_uk open in the browser:

    [refresher] live refresh jack_uk::IT          -> ok (0 listings)
    [refresher] live refresh selvora_limited::UK  -> failed: ...different account...
    [refresher] live refresh nestwell_goods::DE   -> failed: ...different account...
    [refresher] live refresh sheelady_us::US      -> failed: ...different account...
    [refresher] live refresh selvora_limited::IE  -> failed: ...different account...

Live prices, statuses and stock for five of six accounts never refreshed at all.
And each refusal was written into marketplace_health.json as that pair's
`last_transient` -- putting this application's own sentence in the place a
reader looks for what Amazon said. It did NOT rest those marketplaces:
looks_permanent() does not match this text, so it was never counted towards a
rest. 21 such entries were in the file; they have been scrubbed, and every real
Amazon error, failure count and rest_until was left alone.

HOW IT HAPPENED. routes/live_routes._wrong_account says, in its own docstring,
"Every caller of these routes sends the OPEN account (checked across
static/js)". domain/live_refresher.py is not in static/js. It calls
/live/catalog, /live/images and /live/aplus in-process, naming the account
explicitly, precisely because nobody is looking at it.

WHY NOT THE `_bg` FLAG THE BODY ALREADY CARRIED. `_bg` is JSON from the request
body, so a browser can send it, and a guard a browser can switch off is not a
guard -- the entire point of this one is that other people's selling accounts
now sit in the same config file. A WSGI environ key is set by whoever BUILDS the
request: Werkzeug maps incoming headers to HTTP_* keys, so no HTTP client can
produce one called "alta.background".

That claim is the load-bearing one, so it is not assumed here. It is tried, over
a real socket, with the key spelled six ways.
"""
import io
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return io.open(os.path.join(HERE, *p), encoding="utf-8").read()


from domain import account_scope as _as

print("== the marker exists and is read in one place ==")
check("the key is a WSGI-style name, not a header",
      _as.BACKGROUND_ENVIRON_KEY, "alta.background")
truthy("is_background reads it",
       _as.is_background({_as.BACKGROUND_ENVIRON_KEY: True}))
falsy("  and is false when absent", _as.is_background({}))
falsy("  and survives being handed nothing at all", _as.is_background(None))
falsy("  and a false value is false", _as.is_background({_as.BACKGROUND_ENVIRON_KEY: False}))

print("\n== background_context really marks the request ==")
from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/probe", methods=["GET", "POST"])
def _probe():
    # Every environ key that mentions the word, so a near-miss shows up as a
    # near-miss rather than as silence.
    near = {k: str(v)[:20] for k, v in request.environ.items()
            if "background" in k.lower() or "alta" in k.lower()}
    return jsonify({"background": _as.is_background(request.environ),
                    "near": near})


with _as.background_context(app, "/probe", method="POST", json={"id": "x"}):
    truthy("inside background_context it is set", _as.is_background(request.environ))
    check("  and the body still arrives", (request.get_json() or {}).get("id"), "x")
with app.test_request_context("/probe"):
    falsy("a plain test_request_context is not marked",
          _as.is_background(request.environ))
# environ_base a caller passes must not be thrown away
with _as.background_context(app, "/probe", environ_base={"REMOTE_ADDR": "9.9.9.9"}):
    check("  an environ_base the caller gave is kept",
          request.environ.get("REMOTE_ADDR"), "9.9.9.9")
    truthy("  alongside the marker", _as.is_background(request.environ))

print("\n== and NO http client can forge it ==")
# Over a real socket, because the question is what Werkzeug does with headers.
s = socket.socket()
s.bind(("127.0.0.1", 0))
port = s.getsockname()[1]
s.close()
threading.Thread(target=lambda: app.run(port=port, threaded=True),
                 daemon=True).start()
for _ in range(100):
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/probe" % port, timeout=1)
        break
    except Exception:
        time.sleep(0.1)

FORGERIES = {
    "Alta-Background": "1",
    "alta.background": "1",
    "X-Alta-Background": "true",
    "Alta_Background": "1",
    "HTTP_ALTA_BACKGROUND": "1",
    "Alta-Background-": "1",
}
for name, val in FORGERIES.items():
    try:
        r = urllib.request.Request("http://127.0.0.1:%d/probe" % port,
                                   headers={name: val})
        with urllib.request.urlopen(r, timeout=10) as resp:
            got = json.loads(resp.read())
        falsy("  header %-22s cannot set it" % name, got["background"])
    except (urllib.error.HTTPError, ValueError) as e:
        # A header name the client itself refuses to send is also a pass: it
        # never reached the server, so it certainly did not set anything.
        print("  %-24s refused by the client itself (%s)"
              % (name, type(e).__name__))
# And a body flag, which is what /live/catalog used to carry.
r = urllib.request.Request("http://127.0.0.1:%d/probe" % port,
                           data=json.dumps({"_bg": True}).encode(),
                           headers={"Content-Type": "application/json"})
with urllib.request.urlopen(r, timeout=10) as resp:
    got = json.loads(resp.read())
falsy("  and neither can a _bg flag in the body", got["background"])
truthy("  (the probe would have shown a near miss)", isinstance(got["near"], dict))

print("\n== the guard consults it, before it refuses ==")
LR = read("routes", "live_routes.py")
truthy("live_routes asks account_scope", "_acctscope.is_background(request.environ)" in LR)
_fn = LR.split("def _wrong_account")[1].split("\n    # ")[0]
truthy("  inside _wrong_account", "is_background" in _fn)
# Order matters: checking after the refusal would be checking nothing.
truthy("  BEFORE the mismatch test",
       _fn.index("is_background") < _fn.index("is_mismatch"))
falsy("  and the body flag is still not a way through",
      re.search(r'b\.get\("_bg"\)[^\n]*return None', LR))

print("\n== every in-process caller that names another account uses it ==")
RF = read("domain", "live_refresher.py")
check("no bare test_request_context is left in the refresher",
      RF.count("app.test_request_context"), 0)
check("  all four go through background_context",
      RF.count("_acctscope.background_context("), 4)
for route in ("/live/catalog", "/live/images", "/live/aplus", "/sales/sync"):
    truthy("  %s is one of them" % route, route in RF)
truthy("and it imports the one module that owns the rule",
       "from domain import account_scope as _acctscope" in RF)

print("\n== the guard still refuses a browser asking for another account ==")
# The behaviour this whole mechanism must not weaken. Checked against the rule
# itself rather than a running server, so it holds with nothing else up.
truthy("a named other account is a mismatch", _as.is_mismatch("selvora", "jack_uk"))
falsy("  the same account is not", _as.is_mismatch("jack_uk", "jack_uk"))
falsy("  and silence is not", _as.is_mismatch(None, "jack_uk"))
falsy("  nor is an empty ask", _as.is_mismatch("", "jack_uk"))
falsy("  nor is nothing being open", _as.is_mismatch("selvora", ""))
_ref = _as.refusal("selvora", "jack_uk", "data")
truthy("the refusal names both accounts",
       _ref["asked_for"] == "selvora" and _ref["selected"] == "jack_uk")
truthy("  and is flagged for the browser", _ref["account_mismatch"])

print("\n== a refusal by this app is not evidence about Amazon ==")
truthy("the refusal text says it was this app's decision",
       "nothing was read or changed" in _ref["error"])
truthy("the rotation no longer files one under marketplace health",
       '"different account" not in note' in RF)
from domain import marketplace_health as _mh
falsy("  and it would never have counted towards a rest anyway",
      _mh.looks_permanent(_ref["error"]))
# The file itself is REPORTED, not asserted on. It is live data written by a
# running server, and an app started before this fix goes on writing the old
# records until it is restarted -- which is exactly what happened while this was
# being written: a dashboard.py from 07:13 was still rotating on the old code and
# put one back seconds after the file was cleaned. Failing the suite because
# somebody's app is still up would be a test about the machine, not the code.
# The code assertions above are the ones that hold.
try:
    _health = json.load(io.open(os.path.join(HERE, "marketplace_health.json"),
                                encoding="utf-8"))
    dirty = sorted(k for k, r in _health.items()
                   if isinstance(r, dict) and "different account" in json.dumps(r))
    print("     (%d pairs on record, %d with a real Amazon error)"
          % (len(_health), sum(1 for r in _health.values()
                               if isinstance(r, dict) and r.get("last_error"))))
    if dirty:
        print("     NOTE: %d record(s) still quote this app's refusal -- %s."
              % (len(dirty), ", ".join(dirty[:4])))
        print("           An app started before this fix keeps writing them. "
              "Restart it.")
    else:
        print("     (and none quoting this app's own refusal)")
except FileNotFoundError:
    print("  (no marketplace_health.json on this machine)")

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
