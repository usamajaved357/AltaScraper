"""An AI call is billed to the step that made it, however long the reply takes.

    OWNER, 12 Oct 2026: "I see there is a lot of AI spend." $34.59 of his $49.24
    was filed as "call from /", so nobody could see which step cost what.

Why: the step's name lived in ONE process-wide slot (ai_usage.CONTEXT), every
web request cleared it on the way in, and the recorder read it only after the
provider replied -- 30-90 s later for an image, while the page polled the
batch's progress every two seconds. And the batch worker ran inside a request
context with no path, so the fallback label was "/".

Now a step's name is also kept on its own thread (ai_usage.set_step /
current), read when the call STARTS, and the workers have real paths.
Throwaway database; no network (urlopen is replaced).
"""
import io
import json
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

TMP = tempfile.mkdtemp(prefix="ailabels_")
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "t.db")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w", encoding="utf-8").write('{"accounts": [{"id": "acct"}]}')

from data import db as _db                       # noqa: E402
from domain import ai_providers as P             # noqa: E402
from domain import ai_usage as U                 # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


U.set_context(config_path=CFG, workspace_id="acct")


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def slow_reply(req, timeout=0):
    # WHILE THE PROVIDER IS THINKING, a page request comes in on ANOTHER thread
    # and clears the shared slot -- what dashboard's before_request does.
    t = threading.Thread(target=lambda: U.set_context(feature="", sku=""))
    t.start()
    t.join()
    return _Resp(json.dumps({"usage": {"prompt_tokens": 10,
                                       "completion_tokens": 5}}).encode())


P.urllib.request.urlopen = slow_reply

print("== a step keeps its name through a slow reply ==")
P._feature("image: write the prompt")
P._post("https://openrouter.ai/api/v1/chat/completions", {},
        {"model": "openai/gpt-4o-mini", "messages": []})
row = _db.get_db(CFG).execute(
    "SELECT feature FROM ai_usage ORDER BY id DESC LIMIT 1").fetchone()
check("billed to the step, not to 'call from /'", row["feature"],
      "image: write the prompt")

print("== another thread's name does not leak in ==")
seen = {}


def worker():
    P._feature("image: generate")
    seen["w"] = U.current("feature")


th = threading.Thread(target=worker)
th.start()
th.join()
U.set_context(feature="listing: write the copy")
check("this thread sees its own step", U.current("feature"),
      "listing: write the copy")
check("the worker saw its own", seen.get("w"), "image: generate")

print("== the workers say where they are ==")
J = open(os.path.join(HERE, "domain", "image_jobs.py"), encoding="utf-8").read()
check("image jobs run under /genimage/job/<kind>",
      '"/genimage/job/%s"' in J and "test_request_context(_job_path" in J, True)
A = open(os.path.join(HERE, "domain", "autofix_jobs.py"), encoding="utf-8").read()
check("auto-fix suggestions run under /autofix/suggest",
      'test_request_context("/autofix/suggest"' in A, True)

print()
if fails:
    print("FAILED: %d" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL PASSED")
