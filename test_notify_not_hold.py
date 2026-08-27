"""A big price move is applied and reported, not held and forgotten.

    "i dont want the app to hold the change if there is more than the max change
     value, i just want it to send me the notification"

WHY HOLDING WAS NOT THE SAFE OPTION IT LOOKED LIKE. decide() used to set
action="none" and blocked_by whenever a move passed max_change_pct, and wait to
be noticed. The run that produces those decisions happens every four hours,
usually with nobody watching -- so "waiting for a human" meant the listing sat
at the OLD price, which is precisely the number the supplier's move had just
made wrong. The safer-looking branch was the one that left money on the table.

max_change_pct now means "tell me above this". The change goes through, the
decision carries large_move, and domain/source_apply turns that into a message
AFTER the patch succeeds -- not in decide(), because a dry run decides exactly
the same way and must never claim a price changed that did not.

THE TELLING HAS TO BE DURABLE, which is why it is a table and not a toast. A
toast is gone when the page closes; the four-hourly run happens when it is
closed. Slack is the second copy, and only for the things worth interrupting
somebody about -- sixty-seven repricings pinging a channel is a channel nobody
reads, and then nothing is delivered at all.
"""
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-64s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from domain import notify as N
from domain import sourcing as S

NOW = dt.datetime(2026, 8, 14, 12, 0, 0)
FRESH = "2026-08-14 11:00:00"


def src(i=1):
    return {"id": i, "priority": 100, "enabled": 1, "label": "s", "url": "u"}


def chk(price):
    return {"status": S.FETCHED, "price": price, "shipping": 0.0,
            "in_stock": True, "dispatch_days": 3, "checked_at": FRESH,
            "error": None, "gone_streak": 0}


# up_and_down explicitly: these check the ARITHMETIC, and up-only --
# the default since 27 Aug 2026 -- would pin the price instead of
# cutting it, which is a different thing and has its own test.
RULE = {"direction": "up_and_down",
        "target_roi_pct": 20.0, "max_change_pct": 25.0,
        "min_price": 1.0}

print("=== a move past the threshold is APPLIED ===")
d = S.decide({"price": 24.99, "quantity": 5, "lead_days": 3},
             [(src(), chk(12.40))], RULE, NOW)
check("it updates rather than holding", d["action"], "update")
check("  and nothing blocks it", d["blocked_by"], "")
truthy("  it is flagged", d["large_move"])
truthy("  the move is a number, not a sentence", d["move_pct"] > 25.0)
truthy("  and the note names the threshold", "25.0% notify threshold" in
       d["large_move_note"])

print("\n=== a move inside the threshold is not flagged ===")
d2 = S.decide({"price": 21.00, "quantity": 5, "lead_days": 3},
              [(src(), chk(12.40))], RULE, NOW)
check("still applied", d2["action"], "update")
falsy("  but not a large move", d2["large_move"])
truthy("  and the move is still measured", d2["move_pct"] is not None)

print("\n=== the keys exist even when nothing was worked out ===")
# A caller must never have to guess whether a missing key means "small move" or
# "never measured". move_pct is None only when there was no price to measure.
d3 = S.decide({}, [], RULE, NOW)
check("move_pct is None, not 0", d3["move_pct"], None)
check("large_move is False", d3["large_move"], False)
check("the note is empty", d3["large_move_note"], "")

print("\n=== it EXTENDS the module that already sent things ===")
# domain/notify.py already existed and already did outbound delivery properly:
# named channels, an enabled flag, per-account scoping, event filters,
# quiet-hours de-duplication and a delivery log. The in-app bell was the missing
# half, and it belongs in the same module rather than beside it (Rule 12) --
# "tell somebody" must have one answer.
for fn in ("send", "add_channel", "channels", "redact", "log"):
    truthy("the outbound half is still there: %s()" % fn, hasattr(N, fn))
for fn in ("record", "announce", "recent", "unread_count", "mark_read"):
    truthy("  and the in-app half is here too: %s()" % fn, hasattr(N, fn))

print("\n=== notifications are recorded, and only some go outward ===")
CFG = "config.json"
before = N.unread_count(CFG)
r1 = N.announce(CFG, "test_ws", N.PRICE_CHANGE, "an ordinary reprice",
                ["body"], sku="T1")
truthy("an ordinary price change is recorded", r1["id"])
check("  and is NOT sent outward", r1["sent"], 0)
# The things that need a decision or a look DO interrupt.
for kind in (N.LARGE_MOVE, N.OUT_OF_STOCK, N.BACK_IN_STOCK, N.SUPPLIER_ENDED,
             N.ERROR):
    truthy("%s goes outward" % kind, kind in N.OUTBOUND_KINDS)
falsy("an ordinary price change does not", N.PRICE_CHANGE in N.OUTBOUND_KINDS)

r2 = N.announce(CFG, "test_ws", N.LARGE_MOVE, "forced in-app only", ["b"],
                sku="T2", outbound=False)
truthy("  it is still recorded", r2["id"])
check("  outbound=False keeps it in the app", r2["sent"], 0)

check("both were counted as unread", N.unread_count(CFG) - before, 2)
rows = N.recent(CFG, workspace_id="test_ws", limit=5)
truthy("they come back newest first",
       rows and rows[0]["title"] == "forced in-app only")
n = N.mark_read(CFG, ids=[r1["id"], r2["id"]])
check("marking read changes exactly those", n, 2)
check("  and the unread count returns", N.unread_count(CFG), before)

print("\n=== the wording is built once, not at each call site ===")
SRC = open(os.path.join("domain", "notify.py"), encoding="utf-8").read()
truthy("there is one price-move message builder", "def price_move(" in SRC)
truthy("  one for going out of stock", "def went_out_of_stock(" in SRC)
truthy("  and one for coming back", "def came_back_in_stock(" in SRC)
# The Slack text and the in-app row are the SAME message. Built twice they
# eventually disagree about a number, and a notification whose figures do not
# match the screen is worse than none.
truthy("announce is the single entry point", "def announce(" in SRC)
truthy("  it records BEFORE it sends", SRC.index("out[\"id\"] = record(") <
       SRC.index("r = send(config_path, title"))
truthy("it never raises", "never raises" in SRC.lower())
# A webhook URL is a bearer credential -- anyone holding it can post into that
# channel for ever. It lives in notify.json via add_channel, and the module
# redacts it before any screen sees it.
falsy("no webhook URL is hardcoded in the source",
      "hooks.slack.com/services/T" in SRC)
truthy("  the module redacts one before showing it", "def redact(" in SRC)

print("\n=== the push tells somebody, and only after it succeeded ===")
AP = open(os.path.join("domain", "source_apply.py"), encoding="utf-8").read()
truthy("apply_one notifies", "_notify_push(" in AP)
_after = AP.split('return {"sku": sku, "applied": -1')[1]
truthy("  after the patch, not before", "_notify_push(" in _after)
truthy("  and a failed notify cannot undo the push",
       "except Exception:" in AP.split("_notify_push(config_path")[1][:200])
_fn = AP.split("def _notify_push(")[1]
# The gate now admits out_of_stock as well as update, because going out of
# stock is also a real change that was really pushed and is worth being told
# about. What it must still refuse is EVERY other action -- a dry run decides
# identically to a live run, so "none" reaching this function would announce a
# price change that never happened.
truthy("  a dry run never claims anything changed",
       'act not in ("update", "out_of_stock")' in _fn)
truthy("    and an update with no price is still refused",
       'act == "update" and decision.get("price") is None' in _fn)
truthy("  going out of stock is announced",
       "went_out_of_stock(" in _fn)
truthy("    and so is coming back",
       "came_back_in_stock(" in _fn)
truthy("  and only a large move is escalated",
       'large=bool(decision.get("large_move"))' in _fn)

print("\n=== the table is real ===")
from data import db as _db
got = [r[0] for r in _db.get_db(CFG).execute(
    "select name from sqlite_master where type='table' and name='notifications'")]
check("notifications exists", got, ["notifications"])
cols = [r[1] for r in _db.get_db(CFG).execute("pragma table_info(notifications)")]
for c in ("workspace_id", "type", "sku", "title", "body", "is_read", "created_at"):
    truthy("  it has %s" % c, c in cols)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
