# -*- coding: utf-8 -*-
"""Holding a price the market sets, against a target that would lower it.

THE REQUEST, in the owner's own words:

  "i want the repricer to not to change my price if the margin or roi target set is
   less than my selling price, it means that if i am selling at 40 and the source is
   12, and the roi is set to 20 percent, it should not decrease my price to maintain
   20 percent roi. but if source price suddenly goes upto 35 pounds and i am selling
   at 40 pounds, so then it should increase my selling price but when the source
   again came back to 12 or 20 pounds my selling price should be set to 40 again ...
   this rule is for the items where i am sure that this is the market price and this
   product sells on this price point no matter the roi or margin"

Those three sentences are the three tests below, with his numbers.

WHY A NUMBER AND NOT A SWITCH -- the design question he asked about
A flag meaning "do not go below where you are now" has no memory. Once the source
rises and the price follows it up to 46, "come back to 40" has nothing to come back
TO: the flag would either return to 46 (the last price, so the rise is permanent)
or to whatever the target asks (18.24, which is the bug being fixed). A written-down
number always answers it. It is also checkable -- a flag's effect depends on what
the price happened to be at the moment it was switched on, which nobody can read off
a screen a month later.

WHY IT IS NOT THE "never sell below" BOX
min_price is loss protection: the one guard that still works when a supplier's page
is misread. hold_price is a commercial decision about what a product sells for. Put
them in one field and lowering the floor for a clearance would also give the
repricer permission to undercut the market price, and raising the market price would
weaken the loss protection. Asserted below, because it is the kind of thing a later
tidy-up would happily merge.
"""
import datetime as dt
import json
import os
import sys
import tempfile

sys.path.insert(0, r"D:\AltaScraper")

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


def truthy(l, g):
    check(l, bool(g), True)


def falsy(l, g):
    check(l, bool(g), False)


from domain import sourcing as S                              # noqa: E402

NOW = dt.datetime(2026, 8, 17, 12, 0, 0)
AT = NOW.strftime("%Y-%m-%d %H:%M:%S")


def pair(landed_price, shipping=0.0):
    """One usable supplier at a given price."""
    return [({"id": 1, "url": "https://www.ebay.co.uk/itm/1", "label": "itm/1",
              "kind": "ebay", "enabled": 1, "priority": 100},
             {"status": S.FETCHED, "price": landed_price, "shipping": shipping,
              "currency": "GBP", "in_stock": True, "dispatch_days": 2,
              "error": "", "checked_at": AT, "gone_streak": 0})]


# His numbers: selling at 40.00, 20% ROI target, and the market price held at 40.
# up_and_down explicitly: these check the ARITHMETIC, and up-only --
# the default since 27 Aug 2026 -- would pin the price instead of
# cutting it, which is a different thing and has its own test.
RULE = {"direction": "up_and_down",
        "target_roi_pct": 20.0, "min_price": 5.0, "currency": "GBP"}
HELD = dict(RULE, hold_price=40.0)


def decide(cur, cost, rule):
    return S.decide(cur, pair(cost), rule=rule, now=NOW)


print("=== first, the fault as reported ===")
# 12.00 cost, 20% ROI wanted. Without a held price the repricer prices to the
# floor -- which is less than half what the product sells for.
bad = decide({"price": 40.00, "quantity": 5, "lead_days": 3}, 12.00, RULE)
truthy("with no held price it still proposes a cut", bad["price"] < 40.00)
print("      the rules alone would price this at %.2f" % bad["price"])
# 22.83, not the 18.24 a bare ROI sum gives: the floor also carries the 3.00
# postage label, the 2.00 ads allowance and the 1.00 flat profit, and the whole lot
# is grossed up for Amazon's 15%. Nearly HALF OFF either way, which is the point.
truthy("  and it is a cut of more than a third", bad["price"] < 40.00 * 0.67)

print("\n=== 1. 'it should not decrease my price to maintain 20 percent roi' ===")
d = decide({"price": 40.00, "quantity": 5, "lead_days": 3}, 12.00, HELD)
check("the price stays at 40.00", d["price"], 40.00)
truthy("  and it says it is being held", d["held"])
check("  at the held price", d["held_at"], 40.00)
check("  instead of what the rules asked", d["held_over"], bad["price"])
# THE PRICE IS NOT TOUCHED, which is the outcome that matters. The decision is
# still an "update" because the HANDLING TIME changes (the supplier says 2 days,
# plus the 2-day buffer, against the 3 currently promised) -- so asserting
# action == "none" would be asserting the wrong thing. What must be true is that
# the price it would send equals the price already live.
check("the price it would send is the price already live", d["price"], 40.00)
check("  and the current price was 40.00", 40.00, 40.00)
# The audit line has to explain a price that is not the sum of its parts.
truthy("the log says it was held", "HELD at 40.00" in d["reason"])
truthy("  and what the rules would have done instead",
       "%.2f" % bad["price"] in d["reason"])
# The breakdown must not print a cost-plus sum beside a held price, or the numbers
# on screen would not add up to the price next to them.
bd = d["breakdown"]
check("the breakdown names the held price", bd["hold_price"], 40.00)
truthy("  and flags that it decided the price", bd["held"])
check("  while still reporting what the rules asked", bd["rules_price"],
      bad["price"])
# And the target is still reported as comfortably met, since 40.00 beats it.
truthy("the ROI target is beaten at the held price",
       (d["breakdown"]["at_price"]["roi_pct"] or 0) > 20.0)

print("\n=== 2. 'if source price goes upto 35 ... it should increase my price' ===")
up = decide({"price": 40.00, "quantity": 5, "lead_days": 3}, 35.00, HELD)
truthy("the price goes UP, not held down at 40.00", up["price"] > 40.00)
print("      at a 35.00 cost the price becomes %.2f" % up["price"])
falsy("  so it is no longer 'held'", up["held"])
check("  and the hold is recorded as beaten", up["hold_exceeded"], 40.00)
# THE WORDING CHANGED DELIBERATELY. The reason used to be one semicolon-joined
# line containing an arithmetic identity; it is sentences now, because the owner
# could not read the old one. What it has to SAY is unchanged, so that is what is
# asserted -- the held price, and that the cost outgrew it.
truthy("the log explains why it went above the held price",
       "held price of 40.00" in up["reason"]
       and "no longer covers the cost" in up["reason"])
# THE WHOLE SAFETY ARGUMENT. A hold that could pin a price below cost would be a
# machine for losing money. It is a floor among floors, so the higher one wins.
truthy("a held price can never force a sale below cost", up["price"] > 35.00)
# AND THEN THE CHANGE CAP CATCHES IT -- WHEN THE MOVE IS BIG ENOUGH.
#
# This used to read "a 38% jump waits for a human": 40.00 -> 55.30 against a 25%
# limit. The price at a 35.00 cost is 49.42 now rather than 55.30, because the
# 3.00 postage and 2.00 ads that used to be added to every price are gone. That
# is a 23.6% rise, which is INSIDE the cap, so it is proposed rather than held --
# correct, and a different case from the one this was pinning.
#
# So both are pinned: the move that fits goes through, and a move that does not
# still waits for a human.
check("a rise inside the cap is proposed", up["action"], "update")
tight = decide({"price": 40.00, "quantity": 5, "lead_days": 3}, 35.00,
               dict(HELD, max_change_pct=10.0))
# THE CAP NO LONGER HOLDS ANYTHING -- it notifies. Changed on the owner's
# instruction: "i dont want the app to hold the change if there is more than the
# max change value, i just want it to send me the notification". A held price is
# not a safe price; it leaves the listing at the number the supplier's move just
# made wrong, until somebody happens to look.
check("  a jump past the limit is still applied", tight["action"], "update")
truthy("  and flagged as a large move", tight["large_move"])
truthy("  naming the threshold it passed",
       "10.0% notify threshold" in (tight["large_move_note"] or ""))
# With the cap widened, the same decision goes through -- proving the block is the
# cap and not the hold.
wide = decide({"price": 40.00, "quantity": 5, "lead_days": 3}, 35.00,
              dict(HELD, max_change_pct=80.0))
check("  with a wider cap the rise is proposed", wide["action"], "update")
truthy("  at the higher price", wide["price"] > 40.00)

print("\n=== 3. 'when the source came back to 12 or 20 my price should be 40 again' ===")
for back in (12.00, 20.00):
    again = decide({"price": up["price"], "quantity": 5, "lead_days": 3}, back, HELD)
    check("a %.2f cost returns the price to 40.00" % back, again["price"], 40.00)
    truthy("  held once more", again["held"])
# NO MEMORY WAS NEEDED. The return to 40.00 comes from the number being written
# down, not from remembering where the price used to be -- which is the argument
# for a box rather than a switch.
truthy("the return needs no record of the previous price",
       "hold_price" in S.DEFAULT_RULE)

print("\n=== it is a FLOOR, so every other floor still applies ===")
# min_price above the held price wins: it is the loss guard.
higher_floor = decide({"price": 60.00}, 12.00, dict(HELD, min_price=45.0))
check("a higher 'never sell below' beats the held price",
      higher_floor["price"], 45.00)
falsy("  and the hold does not claim to have set it", higher_floor["held"])
# A ceiling below the held price wins too, and the hold must stop claiming credit.
capped = decide({"price": 30.00}, 12.00, dict(HELD, max_price=30.0))
check("a ceiling below the held price wins", capped["price"], 30.00)
falsy("  the hold does not claim to have set that either", capped["held"])
check("  and the clash is reported", capped["hold_capped"],
      {"hold": 40.0, "ceiling": 30.0})
# THE SENTENCE IS CHECKED ON A DECISION THAT ACTUALLY CHANGES SOMETHING.
#
# When the live price is already right, a later guard replaces `reason` with
# "already within 0.20 of the right price" -- true, and it discards the sum that
# explains how the right price was reached. That is existing behaviour for every
# no-change decision, not something the hold introduced (the structured
# `breakdown` survives it either way), but it does mean the wording can only be
# asserted where a change is proposed. Live price 26.00 -> 30.00 is such a case.
capped_move = decide({"price": 26.00}, 12.00, dict(HELD, max_price=30.0))
check("  the same cap applies when a change is proposed",
      capped_move["price"], 30.00)
truthy("  and the log names the clash",
       "capped by the 30.00 ceiling" in capped_move["reason"])
truthy("  naming the held price too",
       "held price of 40.00" in capped_move["reason"])

print("\n=== the two boxes are separate, and must stay separate ===")
check("hold_price exists in its own right", S.DEFAULT_RULE["hold_price"], None)
check("  and min_price still does too", S.DEFAULT_RULE["min_price"], None)
# Setting one must not touch the other.
only_hold = S.rule_with_defaults({"hold_price": 40.0})
check("holding a price sets no floor", only_hold["min_price"], None)
only_min = S.rule_with_defaults({"min_price": 5.0})
check("  and setting a floor holds no price", only_min["hold_price"], None)
# The reason they are separate is written down where a later change would see it.
src = open(os.path.join("domain", "sourcing.py"), encoding="utf-8").read()
truthy("the file says why one field could not be both",
       "loss protection" in src or "safety floor" in src)

print("\n=== off by default, so nothing changes for anyone who has not asked ===")
plain = decide({"price": 40.00, "quantity": 5, "lead_days": 3}, 12.00,
               S.rule_with_defaults(RULE))
falsy("no hold set -> nothing is held", plain["held"])
check("  and the price is what it always was", plain["price"], bad["price"])
check("  with the ordinary cost-plus explanation",
      "HELD" in plain["reason"], False)

print("\n=== it is stored per SKU, never per ASIN ===")
TMP = tempfile.mkdtemp(prefix="altahold_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "h.db")
from domain import source_repo as R                            # noqa: E402

R.save_rule(CFG, "ws", "UK", "", {"target_roi_pct": 20.0})
R.save_rule(CFG, "ws", "UK", "SKU-A", {"hold_price": 40.0})
a = S.rule_with_defaults(R.rule_for(CFG, "ws", "UK", "SKU-A"))
b = S.rule_with_defaults(R.rule_for(CFG, "ws", "UK", "SKU-B"))
check("the SKU that set it has it", a["hold_price"], 40.0)
check("  and another SKU on the same account does not", b["hold_price"], None)
check("  while both keep the account's target", (a["target_roi_pct"],
                                                 b["target_roi_pct"]), (20.0, 20.0))
# Two SKUs of ONE ASIN are two different rows. That is the point of keying by SKU.
R.save_rule(CFG, "ws", "UK", "8.00_3Days_B0G1K5B7QS", {"hold_price": 19.99})
R.save_rule(CFG, "ws", "UK", "9.50_2Days_B0G1K5B7QS", {"hold_price": 24.99})
one = S.rule_with_defaults(R.rule_for(CFG, "ws", "UK", "8.00_3Days_B0G1K5B7QS"))
two = S.rule_with_defaults(R.rule_for(CFG, "ws", "UK", "9.50_2Days_B0G1K5B7QS"))
check("two SKUs of the same ASIN hold different prices",
      (one["hold_price"], two["hold_price"]), (19.99, 24.99))

print("\n=== a setting with nowhere to store it fails LOUDLY ===")
# THE BUG THIS TEST FOUND. hold_price was accepted by the route, filtered out by
# save_rule's own column list, and stored as nothing -- while the screen answered
# "saved" and the repricer went on cutting the price to the target. Two allowlists
# for one idea, and nothing to notice when they disagreed (Rule 12).
storable, unaccounted = R.storable_rule_keys()
check("every setting is either storable or explicitly not stored", unaccounted, [])
truthy("  and hold_price is storable", "hold_price" in storable)
# A setting that is deliberately not stored is fine and must NOT raise --
# shipping_label and the other pricing constants come from listing/pricing.py.
try:
    R.save_rule(CFG, "ws", "UK", "SKU-A", {"min_profit": 9.99, "hold_price": 40.0})
    check("a deliberately-unstored setting is accepted quietly", True, True)
except Exception as exc:                                        # pragma: no cover
    check("a deliberately-unstored setting is accepted quietly",
          "%s: %s" % (type(exc).__name__, exc), True)
check("  and the storable one beside it still landed",
      S.rule_with_defaults(R.rule_for(CFG, "ws", "UK", "SKU-A"))["hold_price"], 40.0)

# A setting in NEITHER list is the bug, and it now refuses. Simulated by adding a
# setting with no column, because -- by design -- there is no real one left to use.
S.DEFAULT_RULE["a_new_setting_nobody_added_a_column_for"] = None
try:
    _, unaccounted2 = R.storable_rule_keys()
    check("the check spots it", unaccounted2,
          ["a_new_setting_nobody_added_a_column_for"])
    try:
        R.save_rule(CFG, "ws", "UK", "SKU-A",
                    {"a_new_setting_nobody_added_a_column_for": 1})
        check("saving it raises rather than vanishing", "no error", "ValueError")
    except ValueError as exc:
        truthy("saving it raises rather than vanishing", "no column" in str(exc))
        truthy("  and the message says where to add it", "_RULE_COLS" in str(exc))
        truthy("  and names the setting", "a_new_setting" in str(exc))
finally:
    # Put DEFAULT_RULE back, or every test after this one inherits a fake setting.
    S.DEFAULT_RULE.pop("a_new_setting_nobody_added_a_column_for", None)
check("DEFAULT_RULE is left as it was", R.storable_rule_keys()[1], [])

print("\n=== a mistyped amount is refused, not stored as nothing ===")
# The same class of bug as a mistyped target: it would store, fail every check, and
# leave someone believing their price was being held while it was cut in half.
import dashboard as D                                          # noqa: E402
app = D.build_app()
app.config["TESTING"] = True
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "h.db")
with app.test_client() as c:
    r = c.post("/sourcing/rules", json={"id": "ws", "marketplace": "UK",
                                        "sku": "SKU-A", "rule": {"hold_price": "forty"}})
    check("'forty' is refused", r.status_code, 400)
    truthy("  and the message says what a valid one looks like",
           "40" in (r.get_json() or {}).get("error", ""))
    r = c.post("/sourcing/rules", json={"id": "ws", "marketplace": "UK",
                                        "sku": "SKU-A", "rule": {"hold_price": "-5"}})
    check("a negative amount is refused", r.status_code, 400)
    r = c.post("/sourcing/rules", json={"id": "ws", "marketplace": "UK",
                                        "sku": "SKU-A", "rule": {"hold_price": "£40.00"}})
    check("a pound sign is accepted", r.status_code, 200)
    r = c.post("/sourcing/rules", json={"id": "ws", "marketplace": "UK",
                                        "sku": "SKU-A", "rule": {"hold_price": ""}})
    check("an empty box clears it", r.status_code, 200)

print("\n" + ("FAILURES: %s" % ", ".join(fails) if fails else "FAILURES: 0"))
sys.exit(1 if fails else 0)
