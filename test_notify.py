"""Sending an alert somewhere other than this app's own screen.

Everything this app produces has been in-app only, which means it is only seen
by someone who has already opened the app to look.

Delivery is OUTWARD-FACING and cannot be taken back: a message posted into a
channel is read by whoever is in it, and a webhook URL handed to the wrong place
is a small permanent leak. So most of this test is about the module staying
silent unless it has been explicitly told not to be, and about the two ways a
notification system betrays the person relying on it:

    it repeats itself until the channel is muted
    it fails silently, turning "nobody told me" into "the app said it was fine"
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from domain import notify as N  # noqa: E402

FAIL = []


def check(label, got, want):
    ok = got == want
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        FAIL.append(label)


def truthy(label, got):
    check(label, bool(got), True)


TMP = tempfile.mkdtemp(prefix="ntf")
CFG = os.path.join(TMP, "config.json")

# Every send is intercepted. Nothing in this test may reach the network -- a
# test suite that posts to a real webhook is a test suite that spams somebody.
POSTS = []
_OK = [True]


def fake_post(url, payload, timeout=12):
    POSTS.append({"url": url, "payload": payload})
    return (_OK[0], "HTTP 200 ok" if _OK[0] else "HTTP 500 boom")


N._post = fake_post

print("== nothing is configured, so nothing is sent ==")
check("no channels to begin with", N.channels(CFG), [])
r = N.send(CFG, "Something happened", ["a line"])
check("sending with nothing set up is not an error", r["ok"], True)
check("  nothing went out", r["sent"], 0)
truthy("  and it says why", "No enabled channel" in (r.get("note") or ""))
check("  nothing was posted", len(POSTS), 0)

print("\n== adding an address is not the same as switching it on ==")
# Conflating the two means a mistyped URL starts receiving immediately.
a = N.add_channel(CFG, "slack", "https://hooks.slack.com/services/T/B/xxxx",
                  label="Ops room")
truthy("a channel can be added", a["ok"])
check("  it is NOT enabled by default", a["channel"]["enabled"], False)
r = N.send(CFG, "Still quiet", ["nope"])
check("  so a send still goes nowhere", r["sent"], 0)
check("  and nothing was posted", len(POSTS), 0)

print("\n== bad addresses are refused ==")
truthy("an unknown channel type is refused",
       not N.add_channel(CFG, "carrier-pigeon", "https://x.example")["ok"])
# http:// would put the payload -- and on Slack the credential itself -- in
# clear text across the network.
truthy("plain http is refused",
       not N.add_channel(CFG, "webhook", "http://x.example")["ok"])
truthy("a slack channel that is not a slack webhook is refused",
       not N.add_channel(CFG, "slack", "https://example.com/hook")["ok"])
truthy("  but a generic webhook may be any https address",
       N.add_channel(CFG, "webhook", "https://example.com/hook",
                     label="Bridge")["ok"])

print("\n== the URL is a credential and is never shown in full ==")
# A Slack Incoming Webhook is a bearer token: whoever holds it can post to that
# channel forever. Rendering it puts it in screenshots and support threads.
shown = N.channels(CFG)[0]
truthy("the listing has no url field at all", "url" not in shown)
truthy("  only a redacted one", shown["url_shown"].endswith("xxxx"))
truthy("  with the middle removed", "…" in shown["url_shown"])
truthy("  and the secret is still retrievable when asked for explicitly",
       N.channels(CFG, include_secret=True)[0]["url"].endswith("xxxx"))

print("\n== switched on, it sends ==")
cid = N.channels(CFG)[0]["id"]
N.set_channel(CFG, cid, enabled=True)
r = N.send(CFG, "Rank slipped", ["B00X is #4,200, target #1,000"], event="tracker")
check("it went out", r["sent"], 1)
check("  nothing failed", r["failed"], 0)
check("  one post was made", len(POSTS), 1)
# Slack takes {"text": ...} with no app, no scopes and no OAuth.
truthy("  slack gets a text payload", "text" in POSTS[0]["payload"])
truthy("  carrying the subject", "Rank slipped" in POSTS[0]["payload"]["text"])
truthy("  and the detail lines", "B00X" in POSTS[0]["payload"]["text"])

print("\n== repeating an alert is how a channel gets muted ==")
# These alerts are STATES, not events: a rank that is off target is off target
# every time anything checks. Sent every check, that is a message an hour saying
# the same thing, and the human response is to mute -- so the real one is missed.
POSTS.clear()
r1 = N.send(CFG, "Rank slipped", ["same"], event="tracker", key="bsr:B00X")
check("the first one goes", r1["sent"], 1)
r2 = N.send(CFG, "Rank slipped", ["same"], event="tracker", key="bsr:B00X")
check("  the second is skipped", r2["skipped"], 1)
check("  and not sent", r2["sent"], 0)
check("  only one post in total", len(POSTS), 1)
truthy("  the skip is explained", "not repeating" in (r2.get("note") or ""))
# Skipped is RECORDED, not silently dropped: a log that goes blank looks like a
# system that has stopped working.
lg = N.log(CFG, 5)
truthy("  and written to the log as skipped",
       any(e["result"] == N.SKIPPED for e in lg))
r3 = N.send(CFG, "Rank slipped", ["same"], event="tracker", key="bsr:B00X",
            force=True)
check("  force overrides the quiet window", r3["sent"], 1)
# A different alert must not be silenced by an unrelated one.
r4 = N.send(CFG, "Other thing", ["x"], event="tracker", key="bsr:B00Y")
check("  a different key is unaffected", r4["sent"], 1)

print("\n== a failed send is loud ==")
POSTS.clear()
_OK[0] = False
r = N.send(CFG, "Will fail", ["x"], event="tracker", key="fails")
check("failure is reported", r["failed"], 1)
check("  and ok is False", r["ok"], False)
lg = N.log(CFG, 5)
truthy("  the log records the failure",
       any(e["result"] == N.FAILED for e in lg))
truthy("  with the reason", any("500" in (e.get("detail") or "") for e in lg))
# A failed send must NOT count as delivered, or the quiet window would suppress
# the retry and the alert would be lost entirely.
r = N.send(CFG, "Will fail", ["x"], event="tracker", key="fails")
check("  a failure does not start the quiet window", r["failed"], 1)
_OK[0] = True

print("\n== events can be narrowed ==")
POSTS.clear()
b = N.add_channel(CFG, "webhook", "https://example.com/only-stock",
                  label="Stock only", events=["stock"], enabled=True)
bid = b["channel"]["id"]
r = N.send(CFG, "A stock thing", ["x"], event="stock")
truthy("the narrowed channel gets its event", r["sent"] >= 1)
POSTS.clear()
N.set_channel(CFG, cid, enabled=False)   # leave only the narrowed one
r = N.send(CFG, "A tracker thing", ["x"], event="tracker")
check("  and not one it did not ask for", r["sent"], 0)
# An empty events list means everything, so a channel added without thinking
# about events still works.
N.set_channel(CFG, bid, events=[])
r = N.send(CFG, "Anything", ["x"], event="tracker")
check("  an empty event list means everything", r["sent"], 1)

print("\n== the generic webhook gets parts, not a rendered string ==")
POSTS.clear()
N.send(CFG, "Subject here", ["one", "two"], event="daily", account="jack_uk")
p = POSTS[0]["payload"]
check("the subject is its own field", p["subject"], "Subject here")
check("  the lines are a list", p["lines"], ["one", "two"])
check("  the event is named", p["event"], "daily")
check("  and the account is named", p["account"], "jack_uk")

print("\n== testing a channel does not require enabling it ==")
# The point of a test is to check an address BEFORE trusting it. Requiring it to
# be on first means the first real message is also the first message ever sent.
POSTS.clear()
N.set_channel(CFG, cid, enabled=False)
t = N.test(CFG, cid)
truthy("a disabled channel can still be tested", t["ok"])
check("  and it posted", len(POSTS), 1)
truthy("  saying plainly that it is a test",
       "test" in str(POSTS[0]["payload"]).lower())

print("\n== removing ==")
check("a channel can be removed", N.remove_channel(CFG, cid)["removed"], 1)
truthy("  and is gone",
       all(str(c["id"]) != str(cid) for c in N.channels(CFG)))

print("\n== a corrupt file reads as empty ==")
with open(N._path(CFG), "w", encoding="utf-8") as fh:
    fh.write("not json at all")
check("it loads as blank", N.load(CFG), {"channels": [], "log": [], "sent_keys": {}})
check("  and sending is a no-op, not a crash", N.send(CFG, "x")["sent"], 0)

shutil.rmtree(TMP, ignore_errors=True)

print("\n%d failed" % len(FAIL))
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
