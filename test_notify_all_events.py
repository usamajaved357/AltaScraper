"""A channel can ask for every repricer event, including the quiet ones.

    "i want to get all the notifications in the slack channel we created every
     notification about repricer should be there"

WHAT WAS STOPPING IT. announce() records in-app always and sends OUT only for
the kinds in OUTBOUND_KINDS -- a large price move, an out-of-stock, a
back-in-stock, a supplier gone, an error. An ordinary reprice (price_change)
and a listing dropping out of the repricer (listing_gone) were deliberately
quiet, for a reason worth keeping: a channel pinged by sixty-seven four-hourly
repricings gets muted, and then the real alert is missed too.

So the list stays as the DEFAULT and stops being the last word. A channel that
NAMES an event, or says "*", has decided for itself, and announce() no longer
overrules it. Three distinct states, all useful:

    events []            the usual alerts (OUTBOUND_KINDS)
    events ["x","y"]     exactly those, quiet kinds included
    events ["*"]         everything this app ever announces

NOTHING IS SENT BY THIS TEST. It runs against its own temporary notify store
and asserts on the ROUTING decision -- wants() and the filter inside send() --
never on a webhook. The one place a post could happen is stubbed.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, r"D:\AltaScraper")

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


TMP = tempfile.mkdtemp(prefix="altantf_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "jack_uk"}]}, open(CFG, "w"))

from domain import notify as N          # noqa: E402

# Nothing leaves the machine: every "post" is recorded and answered OK.
POSTED = []
N._post = lambda url, payload: (POSTED.append((url, payload)) or (True, "stubbed"))

CH = N.add_channel(CFG, kind="slack", url="https://hooks.slack.com/services/T/B/x",
                   label="Repricer alerts", enabled=True)
cid = CH.get("id") or (CH.get("channel") or {}).get("id") or 1

print("=== the default: the usual alerts only ===")
truthy("a large move goes out", N.wants(CFG, N.LARGE_MOVE) or N.LARGE_MOVE in N.OUTBOUND_KINDS)
falsy("an ordinary price change does not", N.wants(CFG, N.PRICE_CHANGE))
falsy("nor a listing leaving the repricer", N.wants(CFG, N.LISTING_GONE))
truthy("  and price_change is still absent from the default list",
       N.PRICE_CHANGE not in N.OUTBOUND_KINDS)

POSTED[:] = []
N.announce(CFG, "jack_uk", N.PRICE_CHANGE, "Repriced", ["19.99 -> 21.49"])
check("so an ordinary reprice is recorded and NOT sent", len(POSTED), 0)
# The in-app row calls it `type`; the kinds are the same strings either way.
truthy("  but it IS in the app", (N.recent(CFG) or [])[0]["type"] == N.PRICE_CHANGE)

print("\n=== the channel asks for everything ===")
N.set_channel(CFG, cid, events=["*"])
truthy("wants() now says yes to a price change", N.wants(CFG, N.PRICE_CHANGE))
truthy("  and to a listing leaving the repricer", N.wants(CFG, N.LISTING_GONE))

POSTED[:] = []
N.announce(CFG, "jack_uk", N.PRICE_CHANGE, "Repriced", ["19.99 -> 21.49"])
check("the reprice is sent", len(POSTED), 1)
truthy("  to the channel's own address", "hooks.slack.com" in POSTED[0][0])

POSTED[:] = []
N.announce(CFG, "jack_uk", N.LISTING_GONE, "1 listing left the repricer",
           ["SKU-DELETED"])
check("and so is a listing leaving the repricer", len(POSTED), 1)

print("\n=== naming ONE event asks for just that one ===")
N.set_channel(CFG, cid, events=[N.PRICE_CHANGE])
truthy("the named one is wanted", N.wants(CFG, N.PRICE_CHANGE))
falsy("  and an unnamed quiet one is not", N.wants(CFG, N.LISTING_GONE))
POSTED[:] = []
N.announce(CFG, "jack_uk", N.LISTING_GONE, "gone", ["x"])
check("  so it is recorded and not sent", len(POSTED), 0)
# A NARROWED CHANNEL GETS ONLY WHAT IT NAMED, including losing alerts it would
# have had by default. That is send()'s existing behaviour, not something this
# change introduced, and it is why the switch writes ["*"] rather than a list of
# today's event names -- a list would quietly drop whatever was not on it.
POSTED[:] = []
N.announce(CFG, "jack_uk", N.OUT_OF_STOCK, "Out of stock", ["x"])
check("naming one event gives up the others, as it always did", len(POSTED), 0)

print("\n=== off puts it back to the default, not to a frozen list ===")
N.set_channel(CFG, cid, events=[])
falsy("a price change is quiet again", N.wants(CFG, N.PRICE_CHANGE))
POSTED[:] = []
N.announce(CFG, "jack_uk", N.OUT_OF_STOCK, "Out of stock", ["x"])
check("  and the usual alerts flow once more", len(POSTED), 1)

print("\n=== a disabled channel asks for nothing ===")
N.set_channel(CFG, cid, events=["*"], enabled=False)
falsy("switched off means off, whatever it subscribed to",
      N.wants(CFG, N.PRICE_CHANGE))

print("\n=== the screen can turn it on ===")
JS = open(os.path.join(r"D:\AltaScraper", "static", "js", "notify.js"),
          encoding="utf-8").read()
truthy("there is a control", "function ntfAll(" in JS)
truthy("  which sends the marker the server reads", '["*"]' in JS)
truthy("  and reads the current state back", "function ntfAllEvents(" in JS)
truthy("  through the route that already sets a channel's events",
       '"/notify/channel"' in JS)
truthy("the column stops calling the default 'everything'",
       "the usual alerts" in JS)
NT = open(os.path.join(r"D:\AltaScraper", "domain", "notify.py"),
          encoding="utf-8").read()
truthy("the volume warning is kept as the reason for the default",
       "applied to volume instead of repetition" in NT
       and "The volume warning on OUTBOUND_KINDS still stands" in NT)

shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
