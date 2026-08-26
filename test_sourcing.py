"""Phase A -- the source repricer's decision engine, with nothing plugged in.

Every case here is one the live system will meet: a supplier page that fails to
load, one that has ended, a price that halves overnight because a parser grabbed
the wrong number, a margin rule that cannot be satisfied at any price.

The test that matters most is "every source unreadable". Getting that one wrong
does not produce a wrong number on a screen -- it takes a healthy catalogue out
of stock overnight, or sells it at a loss. Everything else here is arithmetic.
"""
import sys, datetime as dt
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

def truthy(l, g):
    check(l, bool(g), True)

from domain import sourcing as S

NOW    = dt.datetime(2026, 8, 14, 12, 0, 0)
FRESH  = "2026-08-14 11:00:00"          # 1 hour old
STALE  = "2026-08-12 11:00:00"          # 49 hours old


def src(i, priority=100, enabled=1, label=None):
    return {"id": i, "priority": priority, "enabled": enabled,
            "label": label or "source %d" % i, "url": "https://ebay.co.uk/itm/%d" % i}

def chk(status=S.FETCHED, price=10.0, shipping=0.0, in_stock=True,
        dispatch=3, at=FRESH, error=None, gone_streak=None):
    # gone_streak is how many readings in a row have said ENDED. source_repo
    # puts it on every check it hands out; a check built here without one stands
    # for a first sighting, which is deliberately not enough to act on.
    return {"status": status, "price": price, "shipping": shipping,
            "in_stock": in_stock, "dispatch_days": dispatch,
            "checked_at": at, "error": error,
            "gone_streak": (gone_streak if gone_streak is not None
                            else (1 if status == S.GONE else 0))}


print("=== landed cost: postage is part of the cost, and unknown is not free ===")
check("item plus postage", S.landed_cost(chk(price=8.00, shipping=1.50)), 9.5)
check("free postage is a real zero", S.landed_cost(chk(price=8.00, shipping=0.0)), 8.0)
check("UNKNOWN postage costs nothing we can use",
      S.landed_cost(chk(price=8.00, shipping=None)), None)
check("  nor an unknown price", S.landed_cost(chk(price=None)), None)
check("a failed check has no cost", S.landed_cost(chk(status=S.FAILED)), None)
check("an ended listing has no cost", S.landed_cost(chk(status=S.GONE)), None)
check("a negative price is not a bargain", S.landed_cost(chk(price=-5.0)), None)


print("\n=== the price is the user's own rule, not a second one ===")
from listing import pricing as P

# THE ALLOWANCES ARE NO LONGER ASSUMED, SO A TEST OF THE MECHANISM STATES THEM.
#
#     "do not add 3 pounds postage and 2 pounds ad cost and 1 pound profit space
#      on your own, if i added this rule earlier, remove it."
#
# 3.00 / 2.00 / 1.00 used to be the defaults, and every number below was written
# against them. They are now 0.00 and the owner sets them, so the rule is passed
# in explicitly. That is better either way: a test of "does the floor work"
# should not silently change its answer when a default does.
# min_roi_pct 0 as well: the never-sell-at-break-even floor did not exist when
# these numbers were written, and it is a SECOND floor -- with it on, 9.50 asks
# 19.30 rather than 18.24. Switched off here so this block still tests the flat
# rule on its own. The safety floor gets its own tests below.
ALLOW = {"shipping_label": 3.00, "ads_margin": 2.00, "min_profit": 1.00,
         "min_roi_pct": 0}

# cost + 15% fee + 3.00 postage label + 2.00 ads + 1.00 profit, solved for price:
#   (cost + 6.00) / 0.85
check("9.50 landed -> 18.24", S.floor_price(9.50, ALLOW), 18.24)
check("10.00 landed -> 18.83", S.floor_price(10.00, ALLOW), 18.83)
check("15.00 landed -> 24.71", S.floor_price(15.00, ALLOW), 24.71)
check("rounded UP, never down", S.floor_price(9.50, ALLOW) >= 15.50 / 0.85, True)
check("no cost, no floor", S.floor_price(None, ALLOW), None)

print("  -- NOTHING is added that the owner did not ask for --")
check("the postage allowance defaults to nothing", P.PRICING_RULE_SHIPPING_LABEL, 0.00)
check("  the ads allowance too", P.PRICING_RULE_ADS_MARGIN, 0.00)
check("  and the flat profit", P.PRICING_RULE_MIN_PROFIT, 0.00)

print("  -- break-even IS the floor when nothing else is asked for --")
#
#     "Don't set a 20% ROI target by default. Default should be 0% -- meaning
#      the repricer prices at breakeven (no profit, no loss) as the absolute
#      floor. The user sets their own target."   (27 Aug 2026)
#
# min_roi_pct used to default to 20, and this block asserted that a bare rule
# still asked for 20% back. It was doing more than the name suggested: because
# it is a floor among floors it SILENTLY raised the price of every SKU that had
# never set a target, so an account that had deliberately set none was priced to
# 20% anyway while the screen read "Target: none". A default that moves prices
# is not a default; it is a setting nobody chose.
#
# What is left is the real absolute limit. Cost plus Amazon's cut is the price
# below which a sale destroys money, so that is where the floor sits, and
# everything above it is a commercial decision belonging to the owner.
check("no hidden percentage is applied", P.PRICING_RULE_MIN_ROI_PCT, 0.00)
check("a bare rule prices at break-even", S.floor_price(9.50, {}), 11.18)
check("  which is exactly cost plus Amazon's cut",
      S.floor_price(9.50, {}), round(9.50 / 0.85 + 0.005, 2))
# NOT A LOSS, which is the whole point of it being a floor at all.
check("  so the sale earns nothing rather than losing",
      P.achieved(S.floor_price(9.50, {}), 9.50, 0.15)["roi_pct"] >= 0.0, True)
check("  it is NOT one of the two profit targets", S.targets_set({}), [])
check("  so a screen can still say 'no target set'", S.target_floor(9.50, {}), None)

print("  -- and any target the owner sets raises it --")
# The floor takes the HIGHEST of all the floors, so setting one can only ever
# push a price up. That is what makes break-even a safe default: it cannot
# quietly undercut a target somebody has actually asked for.
check("20% back on the cash asks for more", S.floor_price(9.50, {"target_roi_pct": 20.0}),
      13.42)
check("  and that price really does return at least 20%",
      P.achieved(S.floor_price(9.50, {"target_roi_pct": 20.0}), 9.50,
                 0.15)["roi_pct"] >= 20.0, True)
check("  a flat pound does too",
      S.floor_price(9.50, {"min_profit": 1.00}) > S.floor_price(9.50, {}), True)
print("  -- and any one of the five switches it back on --")
for k, v in (("min_profit", 1.00), ("shipping_label", 3.00),
             ("ads_margin", 2.00), ("target_roi_pct", 20.0),
             ("min_roi_pct", 5.0)):
    check("  %s makes it a real floor again" % k,
          S.floor_price(9.50, {"min_roi_pct": 0, k: v}) is not None, True)

print("  -- it is the SAME rule the generator prices with --")
# The generator knows the fee in pounds; the repricer only knows the rate. The
# two must land on the same number or a repriced listing would jump away from
# the price it was created at.
r = S.floor_price(9.50, ALLOW)
check("solved from the rate", r, 18.24)
check("  agrees with the generator's own function fed that price's fee",
      P.floor_from_fees(9.50, round(r * 0.15, 3), 3.00, 2.00, 1.00), 18.24)
check("  and the generator still prices as it always did",
      P.compute_selling_price(9.50, 2.736, 0, 3.00, 2.00, 1.00,
                              min_roi_pct=0)["floor"], 18.24)
check("  competitor above the floor still wins THERE (creation only)",
      P.compute_selling_price(9.50, 2.736, 25.00)["selling_price"], 25.00)

print("  -- the generator will not create a listing at break-even --")
# With the allowances gone its floor would be cost + fee exactly, so it carries
# its own percentage minimum. A competitor above it is untouched by any of this.
check("a floor-priced listing still returns something",
      P.compute_selling_price(9.50, 2.736, 0)["floor"] > 9.50 + 2.736, True)
check("  at least the stated ROI on the cash",
      P.achieved(P.compute_selling_price(9.50, 2.736, 0)["floor"], 9.50,
                 0.15)["roi_pct"] >= P.PRICING_RULE_MIN_ROI_PCT, True)

print("  -- and it is NOT the percentage-margin model that was wrong --")
check("the discarded formula would have said 12.67; this does not",
      S.floor_price(9.50, ALLOW) != 12.67, True)
check("  because postage and ads are real money WHEN THEY ARE SET",
      round(S.floor_price(9.50, ALLOW) - (9.50 / 0.75), 2), 5.57)

print("  -- a SKU that posts in a bigger box can say so --")
check("6.00 postage instead of 3.00",
      S.floor_price(9.50, dict(ALLOW, shipping_label=6.00)), 21.77)

print("  -- a rate that cannot be priced against --")
check("a 100% referral rate is refused, not divided by zero",
      S.floor_price(10.00, dict(ALLOW, referral_rate=1.0)), None)
check("  and does NOT come back as a negative price",
      S.floor_price(10.00, dict(ALLOW, referral_rate=1.5)), None)
check("  99% is refused too, not priced at thousands",
      S.floor_price(10.00, dict(ALLOW, referral_rate=0.995)), None)


print("\n=== a source is only usable if we can say why it is ===")
def why(source, c, rule=None):
    return S.usable(source, c, rule or {}, NOW)[1]

check("a good source is usable", S.usable(src(1), chk(), ALLOW, NOW)[0], True)
check("turned off", why(src(1, enabled=0), chk()), "source turned off")
check("never checked", why(src(1), None), "never checked")
truthy("a failed check says so", "last check failed" in why(src(1), chk(status=S.FAILED)))
# Changed deliberately: a single 'gone' used to read as settled fact. It now
# has to be seen twice running, so the reason text has to say which of the two
# this is -- one holds the listing, the other zeroes it.
check("an ended listing, seen twice", why(src(1), chk(status=S.GONE, gone_streak=2)),
      "the supplier's listing has ended")
truthy("an ended listing seen ONCE says it is still waiting",
       "waiting for a second" in why(src(1), chk(status=S.GONE, gone_streak=1)))
truthy("a stale reading is named as stale", "hours old" in why(src(1), chk(at=STALE)))
check("undated readings are not fresh", why(src(1), chk(at=None)),
      "reading has no timestamp")
check("unknown postage", why(src(1), chk(shipping=None)), "price or postage unknown")
check("out of stock", why(src(1), chk(in_stock=False)), "out of stock at the supplier")
check("stock unknown is not stock", why(src(1), chk(in_stock=None)), "stock unknown")
check("too slow for the rule",
      why(src(1), chk(dispatch=9), {"max_dispatch_days": 5}),
      "dispatches in 9 days, limit is 5")
check("dispatch unknown when a limit is set",
      why(src(1), chk(dispatch=None), {"max_dispatch_days": 5}),
      "dispatch time unknown")
check("but dispatch may be unknown when no limit is set",
      S.usable(src(1), chk(dispatch=None), ALLOW, NOW)[0], True)


print("\n=== units, not arithmetic: a supplier in the wrong currency ===")
# The quietest way to lose money here. 10.00 USD read as 10.00 GBP looks about a
# fifth cheaper than it is, so the floor comes out a fifth low -- and every other
# guard agrees the number is fine, because the arithmetic IS fine.
GBP = dict(chk(price=10.0, shipping=0.0), currency="GBP")
USD = dict(chk(price=10.0, shipping=0.0), currency="USD")
check("a GBP source for a GBP listing is usable",
      S.usable(src(1), GBP, {"currency": "GBP"}, NOW)[0], True)
check("a USD source for a GBP listing is refused",
      why(src(1), USD, {"currency": "GBP"}),
      "priced in USD, but this listing sells in GBP")
check("  and a source with no currency at all is refused too",
      why(src(1), dict(GBP, currency=""), {"currency": "GBP"}),
      "the supplier's currency is unknown")
check("with no expected currency the check is skipped",
      S.usable(src(1), USD, ALLOW, NOW)[0], True)
check("a USD source for a US listing is fine",
      S.usable(src(1), USD, {"currency": "USD"}, NOW)[0], True)
print("  -- and it is NOT silently converted --")
d = S.decide({"price": 20.00, "quantity": 5, "lead_days": 5},
             [(src(1), USD)], {"currency": "GBP"}, NOW)
check("nothing is priced from it", d["action"], "out_of_stock")
truthy("  saying which currency it was", "USD" in d["reason"])
print("  -- the marketplace decides the currency, not a setting --")
check("UK", S.CURRENCY_FOR["UK"], "GBP")
check("US", S.CURRENCY_FOR["US"], "USD")
check("DE", S.CURRENCY_FOR["DE"], "EUR")


print("\n=== which source wins: your strategy decides, and they disagree ===")
# A cheapest-is-B, fastest-is-C, priority-is-A arrangement, so no two strategies
# can pass by accident.
TRIO = [(src(1, priority=10, label="A"), chk(price=12.0, dispatch=5)),
        (src(2, priority=30, label="B"), chk(price=10.0, dispatch=7)),
        (src(3, priority=20, label="C"), chk(price=11.0, dispatch=2))]
check("cheapest picks the lowest landed cost",
      S.choose(TRIO, {"strategy": "cheapest"}, NOW)[0][0]["label"], "B")
check("fastest picks the shortest dispatch",
      S.choose(TRIO, {"strategy": "fastest"}, NOW)[0][0]["label"], "C")
check("priority picks the one you ranked first",
      S.choose(TRIO, {"strategy": "priority"}, NOW)[0][0]["label"], "A")
check("postage counts when comparing -- cheap item, dear postage loses",
      S.choose([(src(1, label="cheap item"), chk(price=9.0, shipping=6.0)),
                (src(2, label="dearer item"), chk(price=11.0, shipping=1.0))],
               {"strategy": "cheapest"}, NOW)[0][0]["label"], "dearer item")

print("  -- rejections are kept even when something IS chosen --")
ch, rej = S.choose([(src(1, label="A"), chk(price=10.0)),
                    (src(2, label="B"), chk(status=S.FAILED))], ALLOW, NOW)
check("one chosen", ch[0]["label"], "A")
check("  and the other explained", len(rej), 1)
check("  by name", rej[0]["label"], "B")


print("\n=== THE ONE THAT MATTERS: unreadable is not out of stock ===")
CUR = {"price": 20.00, "quantity": 5, "lead_days": 5}

d = S.decide(CUR, [(src(1), chk(status=S.FAILED)),
                   (src(2), chk(status=S.FAILED))], ALLOW, NOW)
check("every source unreadable -> do NOTHING", d["action"], "none")
check("  and say why", d["blocked_by"], "no usable data from 2 of 2 sources")
check("  the listing is NOT taken out of stock", d["quantity"], None)

d = S.decide(CUR, [(src(1), chk(at=STALE)), (src(2), chk(at=STALE))], ALLOW, NOW)
check("stale readings are unreadable too", d["action"], "none")

d = S.decide(CUR, [(src(1), chk(in_stock=False)),
                   (src(2), chk(status=S.FAILED))], ALLOW, NOW)
check("one out of stock, one unreadable -> still do nothing", d["action"], "none")
truthy("  because the unreadable one might have supplied it", d["blocked_by"])

d = S.decide(CUR, [(src(1), chk(in_stock=False)),
                   (src(2), chk(in_stock=False))], ALLOW, NOW)
check("ALL definitely out of stock -> out of stock", d["action"], "out_of_stock")
check("  quantity zero", d["quantity"], 0)
truthy("  naming the sources", "out of stock at the supplier" in d["reason"])

print("  -- an ended listing is evidence, but not on one reading --")
# A 404 is what an ended item looks like AND what a blip, a rate-limit and a
# marketplace mismatch look like. Acting on the first one zeroes a live listing.
d = S.decide(CUR, [(src(1), chk(status=S.GONE, gone_streak=1))], ALLOW, NOW)
check("seen ended ONCE -> change nothing", d["action"], "none")
check("  quantity untouched", d["quantity"], None)
truthy("  and it says it could not read the source",
       "could not be read" in d["reason"] or "no usable data" in d["blocked_by"])

d = S.decide(CUR, [(src(1), chk(status=S.GONE, gone_streak=2))], ALLOW, NOW)
check("seen ended TWICE -> out of stock", d["action"], "out_of_stock")
check("  quantity zero", d["quantity"], 0)

d = S.decide(CUR, [(src(1), chk(status=S.GONE, gone_streak=1))],
             {"confirm_gone_checks": 1}, NOW)
check("one reading is enough if the rule says so", d["action"], "out_of_stock")

# The count has to come from somewhere real. A check that arrives without one
# has no history behind it, so it cannot be confirmed.
d = S.decide(CUR, [(src(1), {"status": S.GONE, "checked_at": FRESH})], ALLOW, NOW)
check("a reading with no history behind it is not confirmation",
      d["action"], "none")

print("  -- one confirmed-gone source does not blind the others --")
d = S.decide(CUR, [(src(1), chk(status=S.GONE, gone_streak=2)),
                   (src(2), chk(price=9.00, shipping=0.0))], ALLOW, NOW)
check("the readable source still prices it", d["action"], "update")

d = S.decide(CUR, [(src(1), chk(dispatch=9))], {"max_dispatch_days": 5}, NOW)
check("too slow is a decision, not a blind spot", d["action"], "out_of_stock")

check("no sources at all -> nothing",
      S.decide(CUR, [], ALLOW, NOW)["action"], "none")
check("disabled sources do not count as sources",
      S.decide(CUR, [(src(1, enabled=0), chk())], ALLOW, NOW)["action"], "none")


print("\n=== a normal day: the price follows the supplier ===")
d = S.decide(CUR, [(src(1, label="eBay A"), chk(price=8.00, shipping=1.50, dispatch=3))],
             ALLOW, NOW)
check("it updates", d["action"], "update")
check("  8.00 + 1.50 postage = 9.50 landed -> 18.24", d["price"], 18.24)
# THE POSTAGE IS NOT PROMISED TWICE.
#
#     "handling = eBay_dispatch_days - 2 (shipping policy) + buffer"
#
# This used to assert 3 + 2 = 5, and 5 was wrong -- not by a rounding, but by
# the whole postage. Amazon builds the delivery date from TWO numbers: the
# handling time we set plus the transit of the postage service on the listing.
# Setting handling to the supplier's 3 days meant promising 3 days of handling
# AND 2 days of Royal Mail: a 5-day promise for something eBay said would
# arrive in 3, losing the buy box for two days to describe a three-day product.
#
# Now the 2 days already promised as postage come off: 3 - 2 = 1 day handling,
# plus 2 days transit = the 3 days eBay actually promised.
check("  handling is the supplier's 3 days less the 2 we post in", d["lead_days"], 1)
check("  which with the postage is the supplier's own promise",
      d["lead_days"] + S.SHIPPING_POLICY_DAYS, 3)
# Three, not five. The number is "how many Amazon may sell before the next
# check", and nothing is held in a warehouse.
check("  quantity restored to the three we maintain", d["quantity"], 3)
check("  and it names the source it used", d["source_id"], 1)

# THE REASON IS PROSE NOW, NOT A FORMULA.
#
#     "first of all this is very confusing even i am not able to understand
#      what do it means"
#
# It used to be asserted by looking for the substring "+ 3.00 postage + 2.00
# ads", which is precisely the arithmetic identity that made it unreadable. What
# matters is that the sentence answers the questions somebody actually has, so
# that is what is checked -- and that the numbers in it are the ones the decision
# used, which is checked against the structured breakdown rather than by parsing
# the prose back out (CLAUDE.md Rule 4).
print("  -- and the reason reads as English --")
truthy("  says where it is being bought", "Buying from eBay A" in d["reason"])
truthy("  says what it costs delivered", "9.50 delivered" in d["reason"])
truthy("  says what it will sell for", "Selling at 18.24" in d["reason"])
truthy("  says what that leaves", "leaves 1.00 a unit" in d["reason"])
truthy("  names Amazon's cut", "Amazon's 2.74 fee" in d["reason"])
truthy("  says how long it takes, in words",
       "Handling 1 day" in d["reason"])
truthy("    and says where the missing days went",
       "postage already covers" in d["reason"])
truthy("  and no longer reads as an equation",
       "=" not in d["reason"] and " + " not in d["reason"])
check("  the sum is still available in full, structured",
      (round(d["breakdown"]["cost"], 2), d["breakdown"]["price"],
       d["breakdown"]["postage_label"], d["breakdown"]["ads"]),
      (9.50, 18.24, 3.00, 2.00))

print("  -- the supplier drops their price, so do we --")
cheaper = S.decide({"price": 18.24, "quantity": 5, "lead_days": 5},
                   [(src(1), chk(price=7.00, shipping=1.50, dispatch=3))], ALLOW, NOW)
check("cheaper source -> lower price", cheaper["price"], 17.06)
check("  which is a real drop", cheaper["price"] < 18.24, True)

print("  -- and when they put it up --")
dearer = S.decide({"price": 18.24, "quantity": 5, "lead_days": 5},
                  [(src(1), chk(price=9.00, shipping=1.50, dispatch=3))], ALLOW, NOW)
check("dearer source -> higher price", dearer["price"], 19.42)

print("  -- the competitor is NOT consulted (you asked for source-only) --")
check("no competitor field is even accepted", "competitor" in S.DEFAULT_RULE, False)

print("  -- a slower supplier stretches the handling time --")
slow = S.decide(CUR, [(src(1), chk(price=8.00, shipping=1.50, dispatch=8))], ALLOW, NOW)
check("8 day dispatch -> 6 day handling", slow["lead_days"], 6)
check("  which is still the 8 days the supplier promised",
      slow["lead_days"] + S.SHIPPING_POLICY_DAYS, 8)

# A SUPPLIER FASTER THAN THE POSTAGE CANNOT PRODUCE A NEGATIVE PROMISE.
# 1 - 2 = -1, and Amazon refuses a negative handling time outright. Zero means
# "posted the same day", and the postage still carries the transit.
fast = S.decide(CUR, [(src(1), chk(price=8.00, shipping=1.50, dispatch=1))], ALLOW, NOW)
check("1 day dispatch -> 0 day handling, never -1", fast["lead_days"], 0)

# THE BUFFER IS ADDED ON TOP, and it is the ONLY thing that lengthens a promise
# beyond what the supplier said. Zero by default now: padding every SKU by two
# days whether or not anyone asked was the same unrequested "help" the three
# pricing allowances were removed for.
check("no buffer unless it is asked for", S.DEFAULT_RULE["handling_buffer_days"], 0)
buf = S.decide(CUR, [(src(1), chk(price=8.00, shipping=1.50, dispatch=3))],
               dict(ALLOW, handling_buffer_days=2), NOW)
check("  a 2 day buffer on a 3 day supplier -> 3 days handling",
      buf["lead_days"], 3)
truthy("  and the reason says the extra days were asked for",
       "extra day" in buf["reason"])


print("\n=== the guards, and what each one actually catches ===")
print("  -- min_price is the backstop against a MISREAD cost --")
# The floor cannot help here: it is computed from the same wrong cost. A 0.50
# 'landed' reading yields a floor of 7.65, internally consistent and still a
# disaster. Only an absolute number the user set stops it.
misread = chk(price=0.50, shipping=0.0, dispatch=3)
d = S.decide({"price": 18.24, "quantity": 5, "lead_days": 5},
             [(src(1), misread)], dict(ALLOW, max_change_pct=100.0), NOW)
check("without min_price the floor does NOT save you", d["price"], 7.65)
d = S.decide({"price": 18.24, "quantity": 5, "lead_days": 5},
             [(src(1), misread)], dict(ALLOW, max_change_pct=100.0, min_price=12.00), NOW)
check("with min_price the price cannot go under it", d["price"], 12.0)

print("  -- max_change_pct now NOTIFIES about a big move, it does not hold it --")
#
#     "i dont want the app to hold the change if there is more than the max
#      change value, i just want it to send me the notification"
#
# This used to require action="none" and a blocked_by. Holding is not the safe
# option it looks like: while the change waits to be noticed -- and the run that
# produced it happens every four hours with nobody watching -- the listing sits
# at the OLD price, which is the one the supplier's move just made wrong.
# max_change_pct is now a notify threshold. domain/source_apply sends the
# message after the push, so a dry run never claims a price changed.
d = S.decide({"price": 18.24, "quantity": 5, "lead_days": 5},
             [(src(1), misread)], ALLOW, NOW)
check("a 58% drop is applied, not held", d["action"], "update")
check("  and nothing blocks it", d["blocked_by"], "")
truthy("  it is flagged as a large move", d["large_move"])
truthy("  and says how far out it was", "notify threshold" in d["large_move_note"])
truthy("  with the move recorded as a number", d["move_pct"] > 25.0)
check("a move inside the limit goes through",
      S.decide({"price": 15.00, "quantity": 5, "lead_days": 5},
               [(src(1), chk(price=8.00, shipping=1.50))], ALLOW, NOW)["action"], "update")

print("  -- the floor still holds when min_price is BELOW it --")
d = S.decide(CUR, [(src(1), chk(price=9.50, shipping=0.0, dispatch=3))],
             dict(ALLOW, min_price=5.00), NOW)
check("a low min_price cannot drag the price under the rule", d["price"], 18.24)

print("  -- a ceiling under the floor means we cannot sell it at all --")
d = S.decide(CUR, [(src(1), chk(price=9.50, shipping=0.0))],
             dict(ALLOW, max_price=12.00), NOW)
check("out of stock rather than at a loss", d["action"], "out_of_stock")
truthy("  explaining the arithmetic", "ceiling" in d["reason"])
d = S.decide(CUR, [(src(1), chk(price=9.50, shipping=0.0))],
             dict(ALLOW, min_price=25.00, max_price=20.00), NOW)
check("a ceiling above the floor caps a raised price", d["price"], 20.0)

print("  -- a rate the rule cannot price against stops everything --")
d = S.decide(CUR, [(src(1), chk(price=10.0))], {"referral_rate": 1.0}, NOW)
check("held, not guessed", d["action"], "none")
truthy("  and named", "pricing rule" in d["blocked_by"])

print("  -- and we do not push trivia --")
# The listing here already carries what the rule would set -- 3 units and 1 day
# of handling -- so the only difference left is 6p of price, and that is below
# min_change. The quantity and handling MUST match for this to be a test about
# price: a listing showing 5 units when the rule maintains 3 is a listing that
# needs a push, and it would pass this test for the wrong reason.
d = S.decide({"price": 18.30, "quantity": 3, "lead_days": 1},
             [(src(1), chk(price=8.00, shipping=1.50, dispatch=3))], ALLOW, NOW)
check("a 6p difference is left alone", d["action"], "none")
truthy("  politely", "already within" in d["reason"])

# STOCK THAT HAS SOLD DOWN IS PUT BACK, on its own, without needing a price
# move as an excuse. "if i have only 1 unit left in stock but the supplier is
# still in stock restock my qty to 3 maintain it until the supplier is out of
# stock" -- two sales off a stock of three leave 1, and the next check restores
# it even though the right price has not moved a penny.
low = S.decide({"price": 18.30, "quantity": 1, "lead_days": 1},
               [(src(1), chk(price=8.00, shipping=1.50, dispatch=3))], ALLOW, NOW)
check("1 unit left with the supplier in stock -> restock", low["action"], "update")
check("  back to three", low["quantity"], 3)

d = S.decide({"price": 18.30, "quantity": 3, "lead_days": 9},
             [(src(1), chk(price=8.00, shipping=1.50, dispatch=3))], ALLOW, NOW)
check("but a wrong handling time is still worth fixing", d["action"], "update")


print("\n=== rules: unset falls back, set wins ===")
r = S.rule_with_defaults({"shipping_label": 6.0})
check("the one you set", r["shipping_label"], 6.0)
check("  the rest defaulted", r["referral_rate"], 0.15)
check("a NULL column does not wipe a default",
      S.rule_with_defaults({"shipping_label": None})["shipping_label"],
      P.PRICING_RULE_SHIPPING_LABEL)
check("the per-unit costs default to the shared pricing rule",
      (r["ads_margin"], r["min_profit"]),
      (P.PRICING_RULE_ADS_MARGIN, P.PRICING_RULE_MIN_PROFIT))
check("'no limit' is the default anyway",
      S.rule_with_defaults({})["max_dispatch_days"], None)
check("nothing at all is still a complete rule",
      len(S.rule_with_defaults(None)), len(S.DEFAULT_RULE))


print("\n=== a PERCENTAGE profit target, on top of the flat one ===")
# "i want an option in which i can enroll an option to maintain atleast 20
#  percent margin or roi, a user should be able to set. and if some items are
#  less than that flag it"
#
# The flat min_profit is a fixed number of pounds: right on a cheap unit, nearly
# meaningless on an expensive one. £1 on £11.95 of stock is 8% back.
from listing import pricing as _P

COST = 11.95
def _price(kind, pct):
    # ALLOW, because every number in this block was written when the three
    # per-unit allowances were the defaults. They are 0.00 now and the owner
    # sets them; stating them keeps this a test of the TARGET mechanism rather
    # than of what a default happens to be.
    return S.floor_price(COST, dict(ALLOW, profit_target_kind=kind,
                                    profit_target_pct=pct))

# Checked by running the price back through the INVERSE, not by re-deriving it
# with the same formula that produced it -- that would only prove it is
# self-consistent.
for kind, pct in (("margin", 20.0), ("margin", 35.0), ("roi", 20.0), ("roi", 35.0)):
    # The inverse must be given the SAME allowances the price was built with,
    # or it is measuring a different question and will always read high.
    got = _P.achieved(_price(kind, pct), COST, 0.15,
                      ALLOW["shipping_label"], ALLOW["ads_margin"])
    hit = got["margin_pct"] if kind == "margin" else got["roi_pct"]
    check("%s of %.0f%% actually returns %s%%" % (kind, pct, pct), abs(hit - pct) < 0.15, True)

# Margin and ROI are not the same question and must not give the same answer.
check("margin asks more than ROI for the same number",
      _price("margin", 20.0) > _price("roi", 20.0), True)

# A target ADDS a floor; it never removes the one already there.
flat = S.floor_price(COST, ALLOW)
check("a tiny target cannot drag the price below the flat rule",
      _price("roi", 1.0), flat)
truthy("  even though the target alone would ask less",
       _P.floor_from_target(COST, 0.15, "roi", 1.0) < flat)

print("  -- a margin target competes with Amazon for the same pound --")
# p(1-r) - extras = p*t  =>  p = extras/(1-r-t). At r=0.15 there is no solution
# at t>=0.85, and just under it the price runs away.
check("85% margin has no price", _P.floor_from_target(COST, 0.15, "margin", 85.0), None)
check("  nor 90%", _P.floor_from_target(COST, 0.15, "margin", 90.0), None)
truthy("500% ROI does, because ROI is measured against the cost",
       _P.floor_from_target(COST, 0.15, "roi", 500.0) is not None)
check("an unknown kind is not a target", _P.floor_from_target(COST, 0.15, "gross", 20.0), None)
check("no target set -> no target floor", S.target_floor(COST, {}), None)

print("  -- the flag reads the CURRENT price, not the proposed one --")
st = S.target_status(21.99, COST, dict(ALLOW, profit_target_kind="roi", profit_target_pct=20.0))
check("a listing under the target says so", st["meets"], False)
check("  and how far under", st["short_by"], 5.4)
check("  in the units that were asked for", st["kind"], "roi")
st = S.target_status(30.00, COST, dict(ALLOW, profit_target_kind="roi", profit_target_pct=20.0))
check("a listing over it is not flagged", st["meets"], True)
check("no target set -> nothing to say", S.target_status(21.99, COST, {}), None)
# "cannot tell" and "fails" are different, and only one is worth a red chip.
check("an unknown price cannot be judged",
      S.target_status(None, COST, {"profit_target_kind": "roi",
                                   "profit_target_pct": 20.0})["meets"], None)

print("  -- and the decision carries it --")
d = S.decide({"price": 21.99, "quantity": 5, "lead_days": 4},
             [(src(1), chk(price=COST, shipping=0.0))],
             dict(ALLOW, profit_target_kind="roi", profit_target_pct=20.0), NOW)
check("the target travels with the decision", (d["target"] or {})["meets"], False)
truthy("  the price it would set clears the target",
       _P.achieved(d["price"], COST, 0.15)["roi_pct"] >= 20.0)
truthy("  and the breakdown says which floor decided it",
       d["breakdown"]["targets"] == [{"kind": "roi", "pct": 20.0}]
       and d["breakdown"]["target_floor"] is not None)
d2 = S.decide({"price": 21.99, "quantity": 5, "lead_days": 4},
              [(src(1), chk(price=COST, shipping=0.0))], ALLOW, NOW)
check("with no target the decision says so, rather than passing", d2["target"], None)


print("\n=== TWO targets, set independently, and both apply ===")
# "give me 2 different boxes for setting the roi or margin target on repricer"
#
# They are not alternatives. Choosing margin used to throw away whatever ROI you
# wanted, and on this £11.95 unit the two ask for very different prices -- so
# neither implies the other and both have to be honoured.
BOTH = {"target_margin_pct": 20.0, "target_roi_pct": 30.0}
check("both are recognised", S.targets_set(BOTH),
      [("margin", 20.0), ("roi", 30.0)])
check("  margin alone", S.targets_set({"target_margin_pct": 20.0}),
      [("margin", 20.0)])
check("  roi alone", S.targets_set({"target_roi_pct": 30.0}), [("roi", 30.0)])
check("  neither", S.targets_set({}), [])
check("  and zero is off, not a target of nothing",
      S.targets_set({"target_margin_pct": 0}), [])

m_floor = S.target_floor(COST, {"target_margin_pct": 20.0})
r_floor = S.target_floor(COST, {"target_roi_pct": 30.0})
truthy("the two floors are genuinely different numbers", m_floor != r_floor)
check("the price has to clear BOTH, so it is the higher of them",
      S.target_floor(COST, BOTH), max(m_floor, r_floor))

print("\n--- the flag follows whichever one FAILS ---")
# Meeting one target while missing the other is not "on target". Priced at the
# LOWER of the two floors, so exactly one of them is satisfied -- which is the
# whole case a single-target repricer could not represent.
lower, higher = min(m_floor, r_floor), max(m_floor, r_floor)
kind_low = "margin" if lower == m_floor else "roi"
kind_high = "margin" if higher == m_floor else "roi"
st = S.target_status(lower, COST, BOTH)
check("a price that clears one but not the other is still flagged",
      st["meets"], False)
check("  and the chip names the one that failed", st["kind"], kind_high)
check("  while both are reported underneath", len(st["parts"]), 2)
check("  the other having passed",
      [p["meets"] for p in st["parts"] if p["kind"] == kind_low], [True])

st2 = S.target_status(S.target_floor(COST, BOTH), COST, BOTH)
check("a price that clears both is not flagged", st2["meets"], True)
check("  and both parts say so",
      sorted(p["meets"] for p in st2["parts"]), [True, True])

print("\n--- an unreadable price is still 'cannot tell', not 'fails' ---")
st3 = S.target_status(None, COST, BOTH)
check("nothing is claimed", st3["meets"], None)
check("  for either of them", [p["meets"] for p in st3["parts"]], [None, None])

print("\n--- the old single setting still works, untouched ---")
# An account that set '20% roi' before there were two boxes must not silently
# lose its floor. rule_with_defaults folds it into the ROI box.
old = S.rule_with_defaults(dict(ALLOW, profit_target_kind="roi", profit_target_pct=20.0))
check("it becomes the ROI target", old["target_roi_pct"], 20.0)
check("  and does not invent a margin one", old["target_margin_pct"], None)
check("the margin form too",
      S.rule_with_defaults({"profit_target_kind": "margin",
                            "profit_target_pct": 25.0})["target_margin_pct"], 25.0)
# And a new box set on top wins, so changing it in the app actually changes it.
check("a new value overrides the old field",
      S.rule_with_defaults({"profit_target_kind": "roi", "profit_target_pct": 20.0,
                            "target_roi_pct": 35.0})["target_roi_pct"], 35.0)

print("\n--- only MARGIN can be impossible, and only margin is blamed ---")
# Amazon's cut comes out of the same price as a margin target, so the two compete
# for the same pound. ROI is measured against the cost and has no such ceiling.
imp = S.decide({"price": 21.99, "quantity": 5, "lead_days": 4},
               [(src(1), chk(price=COST, shipping=0.0))],
               {"target_margin_pct": 95.0}, NOW)
truthy("an unreachable margin target blocks the SKU", imp.get("blocked_by"))
truthy("  and the reason names margin", "margin target" in (imp.get("reason") or ""))
check("a huge ROI target is ambitious, not impossible",
      S.unreachable_targets(COST, {"target_roi_pct": 500.0}), [])
truthy("  and it does have a floor, however high",
       S.target_floor(COST, {"target_roi_pct": 500.0}) is not None)
check("an unreachable one is named, not silently dropped",
      S.unreachable_targets(COST, {"target_margin_pct": 95.0}),
      [("margin", 95.0)])
check("  and no floor is offered for it, so nothing prices to the flat minimum",
      S.floor_price(COST, {"target_margin_pct": 95.0}), None)
# Before this, an impossible target produced no floor of its own and the unit
# was priced to the flat £1 while the screen said a 95% floor was in force.
check("a reachable one is unaffected",
      S.unreachable_targets(COST, {"target_margin_pct": 20.0}), [])


print("\n=== the tables exist and take a decision ===")
import os, json, tempfile, shutil
TMP = tempfile.mkdtemp(prefix="altasrc_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "s.db")
from data import db as _db
conn = _db.get_db(CFG)
have = {r["name"] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")}
for t in ("sourcing_enrolment", "sourcing_sources", "sourcing_checks",
          "sourcing_rules", "sourcing_actions"):
    check("table %s" % t, t in have, True)

conn.execute("INSERT INTO sourcing_enrolment (workspace_id, marketplace, sku, "
             "enrolled, mode, added_at) VALUES (?,?,?,?,?,?)",
             ("jack_uk", "UK", "8.00_3Days_B0G1K5B7QS", 1, "dry_run", "2026-08-14"))
conn.execute("INSERT INTO sourcing_actions (workspace_id, marketplace, sku, at, "
             "action, to_price, reason, applied) VALUES (?,?,?,?,?,?,?,?)",
             ("jack_uk", "UK", "8.00_3Days_B0G1K5B7QS", "2026-08-14 12:00:00",
              "update", 15.84, "dry run", 0))
conn.commit()
check("an enrollment round-trips",
      conn.execute("SELECT mode FROM sourcing_enrolment").fetchone()["mode"], "dry_run")
check("a dry-run action is stored as not applied",
      conn.execute("SELECT applied FROM sourcing_actions").fetchone()["applied"], 0)
check("nothing is enrolled by default",
      conn.execute("SELECT COUNT(*) c FROM sourcing_enrolment WHERE workspace_id='other'"
                   ).fetchone()["c"], 0)

print("\n=== the gone streak is CONSECUTIVE, and it resets ===")
# The whole guard rests on this count. If it counted 'gone' readings in total
# rather than in a row, a source that 404'd once a month would eventually zero
# a listing that had been fine the entire time.
from domain import source_repo as _repo

conn.execute("INSERT INTO sourcing_sources (id, workspace_id, marketplace, sku, "
             "kind, url, label, priority, enabled, added_at) "
             "VALUES (?,?,?,?,?,?,?,?,?,?)",
             (91, "jack_uk", "UK", "8.00_3Days_B0G1K5B7QS", "ebay",
              "https://www.ebay.co.uk/itm/1", "src", 100, 1, "2026-08-14"))
conn.commit()

def _streak_after(statuses):
    conn.execute("DELETE FROM sourcing_checks WHERE source_id=91")
    for st in statuses:
        _repo.record_check(CFG, 91, {"status": st, "price": 10.0, "shipping": 0.0,
                                     "in_stock": True, "dispatch_days": 2,
                                     "checked_at": "2026-08-14 11:00:00"})
    conn.commit()
    return _repo.latest_checks(CFG, [91])[91].get("gone_streak")

check("one ended reading", _streak_after([S.GONE]), 1)
check("two in a row", _streak_after([S.GONE, S.GONE]), 2)
check("three in a row", _streak_after([S.GONE, S.GONE, S.GONE]), 3)
check("a good reading in between RESETS it",
      _streak_after([S.GONE, S.FETCHED, S.GONE]), 1)
check("a failed reading in between also resets it",
      _streak_after([S.GONE, S.GONE, S.FAILED, S.GONE]), 1)
check("a source reading fine has no streak", _streak_after([S.FETCHED]), 0)
check("counted from the LATEST end, not the oldest",
      _streak_after([S.GONE, S.GONE, S.FETCHED]), 0)

os.environ.pop("ALTASCRAPER_DB", None)
try:
    conn.close()
except Exception:
    pass
shutil.rmtree(TMP, ignore_errors=True)

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
