"""Which way a price may move, and setting one by hand.

ITEM 13 -- THE DIRECTION RULE.

    "Up only (DEFAULT) -- price can only increase. Never decreases even if
     supplier gets cheaper. Protects your market price. Only changes when costs
     force it higher."

WHY THIS IS THE ANSWER TO THE 0% FLOOR, and not merely a nice option. The
repricer prices AT its floor, not towards it: the price follows the supplier
and nothing pulls it up. So a SKU with no profit target is priced at
break-even, and measured on jack_uk the moment the default became 0%, 22 SKUs
would have been cut -- the deepest by 71.5%, from 16.99 to 4.84.

Up-only makes that safe by construction. A floor below what a listing sells for
today is simply not acted on, so the floor can only ever push a price UP, which
is what a floor is for. A cheaper supplier becomes margin instead of a
discount.

THE PRICE IS PINNED, NOT THE DECISION. Stock and handling are decided by the
same pass and have nothing to do with which way a price may move -- a supplier
who has slowed down still needs the promise lengthening. So up-only refuses the
CUT, not the check.

ITEM 17 -- A PRICE SET BY HAND.

The one control on this screen that changes a live price on demand. It is
therefore NOT gated by the master switch or by whether the SKU is armed --
those exist to control what the app does unwatched, and somebody typing into a
price box is watching. It IS gated by the floor, because that guard is not
about supervision: it is the number that says "never below this whatever
happens", and a typo in a price box is exactly the accident it was put there
for.
"""
import datetime as dt
import io
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
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from domain import sourcing as S

NOW = dt.datetime(2026, 8, 27, 12, 0, 0)


def src(i=1):
    return {"id": i, "priority": 100, "enabled": 1, "label": "eBay A", "url": "u"}


def chk(price, dispatch=3):
    return {"status": S.FETCHED, "price": price, "shipping": 0.0,
            "in_stock": True, "dispatch_days": dispatch,
            "checked_at": "2026-08-27 11:00:00", "error": None,
            "gone_streak": 0}


CUR = {"price": 19.97, "quantity": 3, "lead_days": 1}

print("=== up only is the DEFAULT, and it has to be ===")
check("the default direction", S.DEFAULT_RULE["direction"], "up_only")
# Every SKU tracked before this setting existed reads NULL, and NULL must mean
# the protective one -- otherwise adding a column would have quietly switched
# a whole account to a mode that can cut prices.
check("  a rule with no direction reads as up_only",
      S.rule_with_defaults({}).get("direction"), "up_only")
check("  and so does one storing NULL",
      S.rule_with_defaults({"direction": None}).get("direction"), "up_only")

print("\n=== a cheaper supplier does NOT cut an up-only price ===")
d = S.decide(CUR, [(src(), chk(8.00))], {"direction": "up_only"}, NOW)
check("nothing is changed", d["action"], "none")
check("  the price stays where Amazon has it", d["price"], 19.97)
truthy("  and it says WHY, not just 'unchanged'", d["direction_held"])
truthy("    naming the price the rules asked for", d["direction_floor"] < 19.97)
truthy("    in words", "up-only" in d["reason"])
truthy("    that name the number being refused",
       ("%.2f" % d["direction_floor"]) in d["reason"])

print("\n=== but a DEARER supplier still pushes it up ===")
# This is the half that makes up-only safe rather than merely inert: it is a
# floor, so a cost that rises past the price still forces the price with it.
up = S.decide(CUR, [(src(), chk(22.00))], {"direction": "up_only"}, NOW)
check("it updates", up["action"], "update")
truthy("  to a HIGHER price", up["price"] > 19.97)
falsy("  and nothing was held back", up["direction_held"])

print("\n=== up and down follows the supplier both ways ===")
dn = S.decide(CUR, [(src(), chk(8.00))], {"direction": "up_and_down"}, NOW)
check("a cheaper supplier lowers it", dn["action"], "update")
truthy("  really lower", dn["price"] < 19.97)
up2 = S.decide(CUR, [(src(), chk(22.00))], {"direction": "up_and_down"}, NOW)
truthy("  and a dearer one still raises it", up2["price"] > 19.97)

print("\n=== match floor sits on the floor, and ignores a hold ===")
# "Always sits at exact calculated floor" and "never below the price you hold
# it at" are different instructions, and a hold is BY CONSTRUCTION a floor
# above the computed one -- so both cannot be honoured. The per-SKU direction
# is the more specific setting, so it wins.
mf = S.decide(CUR, [(src(), chk(8.00))],
              {"direction": "match_floor", "hold_price": 40.00}, NOW)
truthy("the hold is ignored", mf["price"] < 40.00)
falsy("  and nothing claims to be held", mf.get("held"))
# The other two DO honour it.
hp = S.decide(CUR, [(src(), chk(8.00))],
              {"direction": "up_only", "hold_price": 40.00}, NOW)
check("up_only still honours a hold", hp["price"], 40.00)
truthy("  and says it is held", hp.get("held"))

print("\n=== up-only refuses the CUT, not the CHECK ===")
# A supplier who has slowed down still needs the handling time lengthening, and
# stock still needs putting back -- neither has anything to do with which way a
# price may move.
slow = S.decide({"price": 19.97, "quantity": 1, "lead_days": 1},
                [(src(), chk(8.00, dispatch=9))], {"direction": "up_only"}, NOW)
check("it still acts", slow["action"], "update")
check("  the price is untouched", slow["price"], 19.97)
check("  the handling time is fixed", slow["lead_days"], 7)
check("  and the stock is put back", slow["quantity"], 3)
truthy("  while still recording that a cut was refused", slow["direction_held"])

print("\n=== the floor still binds, whichever direction is set ===")
for dr in ("up_only", "up_and_down", "match_floor"):
    r = S.decide(CUR, [(src(), chk(8.00))],
                 {"direction": dr, "min_price": 15.00}, NOW)
    truthy("%-12s never goes below the minimum price" % dr,
           r["price"] is None or r["price"] >= 15.00)

print("\n=== a price that did not move is not announced as one ===")
AP = io.open(os.path.join("domain", "source_apply.py"), encoding="utf-8").read()
_fn = AP.split("def _notify_push(")[1]
truthy("the notifier checks the price actually changed",
       "abs(float(_was) - float(decision[\"price\"])) < 0.005" in _fn)
truthy("  and says why that case exists", "did not move is not a price move"
       in _fn.lower() or "10.06 -> 10.06" in _fn)

print("\n=== it is stored, validated and offered ===")
from domain import source_repo as REPO
truthy("the column is written", "direction" in REPO._RULE_COLS)
DB = io.open(os.path.join("data", "db.py"), encoding="utf-8").read()
truthy("  and migrated onto existing databases",
       '("sourcing_rules", "direction", "TEXT")' in DB)
RT = io.open(os.path.join("routes", "sourcing_routes.py"),
             encoding="utf-8").read()
# A TYPO MUST NOT TURN THE PROTECTION OFF. An unrecognised value stored here
# would read back as "not up_only" and quietly allow cuts on that SKU.
truthy("only the three known values are accepted",
       '("up_only", "up_and_down", "match_floor")' in RT)
truthy("  there is a global default for new SKUs",
       '"/sourcing/default_direction"' in RT)
truthy("  written onto the SKU at enrolment, not read live",
       "sourcing_default_direction" in RT
       and 'if not existing.get("direction")' in RT)
truthy("  the sheet carries it out", '"Direction"' in RT)
truthy("  and reads it back in", '"direction"' in RT.split(
    "def sourcing_minprice_upload")[1][:4000])

JS = io.open(os.path.join("static", "js", "sourcing.js"), encoding="utf-8").read()
truthy("there is a Direction pill", "pill('Direction'" in JS)
truthy("  a bulk action", "function sourcingBulkDirection(" in JS)
truthy("  and it is a chooser, not a cycle",
       "input type=\"radio\" name=\"src_dir\"" in JS)

print("\n=== a price set by hand ===")
_mp = RT.split("def sourcing_manual_price(")[1].split("@app.route")[0]
truthy("there is a route", '"/sourcing/manual_price"' in RT)
# NOT gated by supervision controls -- those govern what runs unwatched.
falsy("  it does NOT require the master switch", "is_enabled" in _mp)
falsy("  nor that the SKU is armed", '"live"' in _mp)
# IS gated by the floor, which is not about supervision.
truthy("  but it refuses to go below the floor",
       "below the %.2f you set as this SKU" in _mp
       or "below the" in _mp and "floor" in _mp)
truthy("  it pushes through the SAME patch builder the repricer uses",
       "_apply.build_patches(" in _mp)
truthy("  sending ONLY the price, not stock or handling",
       '{"price": round(price, 2)}' in _mp)
truthy("  it records the change as a manual one",
       '"manual": True' in _mp and "record_action" in _mp)
truthy("    naming who did it", '"manual_by"' in _mp)
# THE REPRICER MUST RESPECT IT. Without updating the snapshot, the next
# decision compares the supplier against the OLD price -- so a hand RAISE would
# immediately read as "too dear, cut it".
truthy("  and it corrects what the app thinks the price is",
       "_ls.set_price(" in _mp)
from domain import live_snapshots as LS
truthy("    that writer exists", hasattr(LS, "set_price"))
truthy("    and stamps the field as hand-set",
       "price_set_by_hand_at" in io.open(
           os.path.join("domain", "live_snapshots.py"),
           encoding="utf-8").read())

from auth import guard
check("setting a live price needs the publish right",
      guard.required_permission("/sourcing/manual_price", "POST"), "publish")

truthy("the row carries a pencil", 'class="rp-pen"' in JS)
truthy("  and the panel an Edit price button", "Edit price" in JS)
truthy("  both opening the same editor",
       JS.count("sourcingManualPrice(") >= 3)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
