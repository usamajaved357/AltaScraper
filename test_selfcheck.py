"""Does the app actually diagnose itself?

Drives the real error handler and the real /diag route, then checks that (a) a
crash is recorded, (b) credentials never survive into the record, (c) the boot
banner names a real misconfiguration, (d) the copy-paste block is readable.
"""
import os, sys, json, tempfile
sys.path.insert(0, r"D:\AltaScraper")

from flask import Flask, jsonify, session, request
import domain.selfcheck as sc
import domain.deploy_check as dc
from auth.guard import wants_json

fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(label)
    print("  %-58s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
def check_true(label, got):
    check(label, bool(got), True)

TMP = tempfile.mkdtemp(prefix="altadiag_")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w").write("{}")

app = Flask(__name__)
app.secret_key = "test-only"

@app.route("/boom")
def boom():
    raise RuntimeError("upstream refused: refresh_token=Atzr|IwEBIFAKESECRETVALUE123 and api_key=sk-ant-abc123deadbeef")

@app.route("/gone")
def gone():
    from werkzeug.exceptions import NotFound
    raise NotFound()

@app.errorhandler(500)
@app.errorhandler(Exception)
def _json_errors(e):
    code = getattr(e, "code", 500) or 500
    if code == 500:
        sc.record(request.path, request.method, code, e, user=session.get("email") or "")
    if wants_json():
        return jsonify({"ok": False, "error": str(e)}), (code if isinstance(code, int) else 500)
    if isinstance(code, int) and code != 500:
        return e
    return ("Internal Server Error", 500)

@app.route("/diag")
def diag():
    res = dc.check(CFG)
    res["refresher"] = {"accounts": {"jack_uk": {"age": 300}}}
    res["recent"] = sc.recent(25)
    res["text"] = sc.as_text(res)
    return jsonify({"ok": True, **res})

c = app.test_client()

print("=== a crash is recorded, not just shown ===")
sc.clear()
r = c.get("/boom", headers={"Accept": "application/json"})
check("the caller gets JSON, never an HTML page", r.status_code, 500)
check("  and it IS json", r.get_json() is not None, True)
rec = sc.recent()
check("the error was recorded", rec["total"], 1)
e0 = rec["errors"][0]
check("  with the URL", e0["path"], "/boom")
check("  with the exception type", e0["kind"], "RuntimeError")
check_true("  with a traceback tail", len(e0["trace"]) > 0)
check_true("  naming the real file", any("test_selfcheck" in t for t in e0["trace"]))

print("\n=== credentials never survive into the record ===")
blob = json.dumps(rec)
check("SP-API refresh token gone", "IwEBIFAKESECRETVALUE123" in blob, False)
check("Anthropic key gone", "abc123deadbeef" in blob, False)
check_true("  but the useful part of the message stays",
           "upstream refused" in e0["message"])
check("redact() handles an AWS key",
      "AKIAIOSFODNN7EXAMPLE" in sc.redact("aws AKIAIOSFODNN7EXAMPLE here"), False)
check("redact() handles password=",
      "hunter2xyz" in sc.redact('{"password": "hunter2xyz"}'), False)
check("redact() leaves ordinary text alone",
      sc.redact("could not reach Amazon"), "could not reach Amazon")

print("\n=== a 404 is the app working, not a fault ===")
sc.clear()
c.get("/gone")
check("404s are not recorded as errors", sc.recent()["total"], 0)

print("\n=== the ring buffer cannot grow without bound ===")
sc.clear()
for i in range(sc.MAX_ERRORS + 25):
    sc.record("/x/%d" % i, "GET", 500, ValueError("n%d" % i), trace="line\n")
check("capped at MAX_ERRORS", sc.recent(999)["total"], sc.MAX_ERRORS)
check("newest first", sc.recent(1)["errors"][0]["path"], "/x/%d" % (sc.MAX_ERRORS + 24))
check("repeat counter survives the cap", sc.recent()["repeats"]["GET /x/0"], 1)

print("\n=== /diag returns the whole picture in one call ===")
sc.clear()
c.get("/boom", headers={"Accept": "application/json"})
j = c.get("/diag", headers={"Accept": "application/json"}).get_json()
check_true("configuration checks present", len(j.get("checks") or []) > 0)
check_true("recent errors present", (j.get("recent") or {}).get("total") == 1)
check_true("copy-paste text present", len(j.get("text") or "") > 100)
txt = j["text"]
for want in ("ALTASCRAPER DIAGNOSTICS", "CONFIGURATION", "RECENT SERVER ERRORS",
             "BACKGROUND SYNC", "/boom"):
    check_true("  text mentions %s" % want, want in txt)
check("the pasteable text is scrubbed too", "IwEBIFAKESECRETVALUE123" in txt, False)

print("\n=== the boot banner names real problems ===")
os.environ["RAILWAY_ENVIRONMENT"] = "production"
bad = dc.check(os.path.join(r"D:\AltaScraper", "config.json"))   # inside the app dir
ban = sc.boot_banner(bad)
check_true("banner flags the ephemeral filesystem",
           "State survives a deploy" in ban and "WIPED" in ban)
check_true("banner says the app still starts", "start anyway" in ban)
del os.environ["RAILWAY_ENVIRONMENT"]
good = dc.check(CFG)
good["checks"] = [c2 for c2 in good["checks"] if c2["ok"]]
check_true("banner is quiet when all is well", "all clear" in sc.boot_banner(good))

print("\n=== recording never becomes a second error ===")
class Nasty(Exception):
    def __str__(self): raise ValueError("cannot stringify")
before = sc.recent()["total"]
sc.record("/n", "GET", 500, Nasty())          # must not raise
check("an unprintable exception is survivable", sc.recent()["total"] >= before, True)

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
