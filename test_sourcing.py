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
        dispatch=3, at=FRESH, error=None):
    return {"status": status, "price": price, "shipping": shipping,
            "in_stock": in_stock, "dispatch_days": dispatch,
            "checked_at": at, "error": error}


print("=== landed cost: postage is part of the cost, and unknown is not free ===")
check("item plus postage", S.landed_cost(chk(price=8.00, shipping=1.50)), 9.5)
check("free postage is a real zero", S.landed_cost(chk(price=8.00, shipping=0.0)), 8.0)
check("UNKNOWN postage costs nothing we can use",
      S.landed_cost(chk(price=8.00, shipping=None)), None)
check("  nor an unknown price", S.landed_cost(chk(price=None)), None)
check("a failed check has no cost", S.landed_cost(chk(status=S.FAILED)), None)
check("an ended listing has no cost", S.landed_cost(chk(status=S.GONE)), None)
check("a negative price is not a bargain", S.landed_cost(chk(price=-5.0)), None)


print("\n=== the price that leaves the margin we asked for ===")
# 15% referral + 10% min margin -> price = cost / 0.75
check("floor on a 10.00 cost", S.floor_price(10.00), 13.34)
check("  rounded UP, never down (13.333 -> 13.34)", S.floor_price(10.00) >= 10 / 0.75, True)
check("  an exact answer is not inflated a penny", S.floor_price(15.00), 20.0)
# 15% referral + 25% target margin -> price = cost / 0.60
check("target on a 10.00 cost", S.target_price(10.00), 16.67)
check("floor on a 9.50 cost", S.floor_price(9.50), 12.67)
check("target on a 9.50 cost", S.target_price(9.50), 15.84)

print("  -- a margin that cannot exist --")
check("90% margin on a 15% fee is impossible",
      S.floor_price(10.00, {"min_margin_pct": 90.0}), None)
check("  and does NOT come back as a negative price",
      S.floor_price(10.00, {"min_margin_pct": 95.0}), None)
check("  85% is refused too, not priced at thousands",
      S.floor_price(10.00, {"min_margin_pct": 84.5}), None)
check("no cost, no floor", S.floor_price(None), None)


print("\n=== a source is only usable if we can say why it is ===")
def why(source, c, rule=None):
    return S.usable(source, c, rule or {}, NOW)[1]

check("a good source is usable", S.usable(src(1), chk(), {}, NOW)[0], True)
check("turned off", why(src(1, enabled=0), chk()), "source turned off")
check("never checked", why(src(1), None), "never checked")
truthy("a failed check says so", "last check failed" in why(src(1), chk(status=S.FAILED)))
check("an ended listing", why(src(1), chk(status=S.GONE)),
      "the supplier's listing has ended")
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
      S.usable(src(1), chk(dispatch=None), {}, NOW)[0], True)


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
                    (src(2, label="B"), chk(status=S.FAILED))], {}, NOW)
check("one chosen", ch[0]["label"], "A")
check("  and the other explained", len(rej), 1)
check("  by name", rej[0]["label"], "B")


print("\n=== THE ONE THAT MATTERS: unreadable is not out of stock ===")
CUR = {"price": 20.00, "quantity": 5, "lead_days": 5}

d = S.decide(CUR, [(src(1), chk(status=S.FAILED)),
                   (src(2), chk(status=S.FAILED))], {}, NOW)
check("every source unreadable -> do NOTHING", d["action"], "none")
check("  and say why", d["blocked_by"], "no usable data from 2 of 2 sources")
check("  the listing is NOT taken out of stock", d["quantity"], None)

d = S.decide(CUR, [(src(1), chk(at=STALE)), (src(2), chk(at=STALE))], {}, NOW)
check("stale readings are unreadable too", d["action"], "none")

d = S.decide(CUR, [(src(1), chk(in_stock=False)),
                   (src(2), chk(status=S.FAILED))], {}, NOW)
check("one out of stock, one unreadable -> still do nothing", d["action"], "none")
truthy("  because the unreadable one might have supplied it", d["blocked_by"])

d = S.decide(CUR, [(src(1), chk(in_stock=False)),
                   (src(2), chk(in_stock=False))], {}, NOW)
check("ALL definitely out of stock -> out of stock", d["action"], "out_of_stock")
check("  quantity zero", d["quantity"], 0)
truthy("  naming the sources", "out of stock at the supplier" in d["reason"])

d = S.decide(CUR, [(src(1), chk(status=S.GONE))], {}, NOW)
check("an ended listing IS evidence -> out of stock", d["action"], "out_of_stock")

d = S.decide(CUR, [(src(1), chk(dispatch=9))], {"max_dispatch_days": 5}, NOW)
check("too slow is a decision, not a blind spot", d["action"], "out_of_stock")

check("no sources at all -> nothing",
      S.decide(CUR, [], {}, NOW)["action"], "none")
check("disabled sources do not count as sources",
      S.decide(CUR, [(src(1, enabled=0), chk())], {}, NOW)["action"], "none")


print("\n=== a normal day: the price follows the supplier ===")
d = S.decide(CUR, [(src(1, label="eBay A"), chk(price=8.00, shipping=1.50, dispatch=3))],
             {}, NOW)
check("it updates", d["action"], "update")
check("  9.50 landed -> 15.84 at a 25% target", d["price"], 15.84)
check("  handling is the supplier's 3 days plus a 2 day buffer", d["lead_days"], 5)
check("  never the supplier's promise on its own", d["lead_days"] > 3, True)
check("  quantity restored", d["quantity"], 5)
check("  and it names the source it used", d["source_id"], 1)
truthy("  the reason is readable", "landed" in d["reason"])

print("  -- the supplier drops their price, so do we --")
cheaper = S.decide({"price": 15.84, "quantity": 5, "lead_days": 5},
                   [(src(1), chk(price=7.00, shipping=1.50, dispatch=3))], {}, NOW)
check("cheaper source -> lower price", cheaper["price"], 14.17)
check("  which is a real drop", cheaper["price"] < 15.84, True)

print("  -- and when they put it up --")
dearer = S.decide({"price": 15.84, "quantity": 5, "lead_days": 5},
                  [(src(1), chk(price=9.00, shipping=1.50, dispatch=3))], {}, NOW)
check("dearer source -> higher price", dearer["price"], 17.50)

print("  -- a slower supplier stretches the handling time --")
slow = S.decide(CUR, [(src(1), chk(price=8.00, shipping=1.50, dispatch=8))], {}, NOW)
check("8 day dispatch -> 10 day handling", slow["lead_days"], 10)


print("\n=== the guards, and what each one actually catches ===")
print("  -- min_price is the backstop against a MISREAD cost --")
# The floor cannot help here: it is computed from the same wrong cost. 0.50
# 'landed' yields a floor of 0.67 and a price of 0.84, all internally consistent
# and all catastrophic. Only an absolute number the user set stops it.
misread = chk(price=0.50, shipping=0.0, dispatch=3)
d = S.decide({"price": 15.84, "quantity": 5, "lead_days": 5},
             [(src(1), misread)], {"max_change_pct": 100.0}, NOW)
check("without min_price the floor does NOT save you", d["price"], 0.84)
d = S.decide({"price": 15.84, "quantity": 5, "lead_days": 5},
             [(src(1), misread)], {"max_change_pct": 100.0, "min_price": 12.00}, NOW)
check("with min_price the price cannot go under it", d["price"], 12.0)

print("  -- max_change_pct catches the sudden misparse --")
d = S.decide({"price": 15.84, "quantity": 5, "lead_days": 5},
             [(src(1), misread)], {}, NOW)
check("a 95% drop is held, not pushed", d["action"], "none")
truthy("  and says how far out it was", "exceeds" in d["blocked_by"])
check("a move inside the limit goes through",
      S.decide({"price": 15.00, "quantity": 5, "lead_days": 5},
               [(src(1), chk(price=8.00, shipping=1.50))], {}, NOW)["action"], "update")

print("  -- floor_price stops the MARGIN rule being broken --")
d = S.decide(CUR, [(src(1), chk(price=9.50, shipping=0.0, dispatch=3))],
             {"target_margin_pct": 0.0}, NOW)
check("a 0% target still cannot price below the floor", d["price"], 12.67)

print("  -- a ceiling under the floor means we cannot sell it at all --")
d = S.decide(CUR, [(src(1), chk(price=9.50, shipping=0.0))],
             {"max_price": 12.00}, NOW)
check("out of stock rather than at a loss", d["action"], "out_of_stock")
truthy("  explaining the arithmetic", "ceiling" in d["reason"])
d = S.decide(CUR, [(src(1), chk(price=9.50, shipping=0.0))],
             {"max_price": 14.00}, NOW)
check("a ceiling above the floor just caps the price", d["price"], 14.0)

print("  -- an impossible margin rule prices nothing --")
d = S.decide(CUR, [(src(1), chk(price=10.0))], {"min_margin_pct": 90.0}, NOW)
check("held, not guessed", d["action"], "none")
truthy("  and named", "margin" in d["blocked_by"])

print("  -- and we do not push trivia --")
d = S.decide({"price": 15.90, "quantity": 5, "lead_days": 5},
             [(src(1), chk(price=8.00, shipping=1.50, dispatch=3))], {}, NOW)
check("a 6p difference is left alone", d["action"], "none")
truthy("  politely", "already within" in d["reason"])
d = S.decide({"price": 15.90, "quantity": 5, "lead_days": 9},
             [(src(1), chk(price=8.00, shipping=1.50, dispatch=3))], {}, NOW)
check("but a wrong handling time is still worth fixing", d["action"], "update")


print("\n=== rules: unset falls back, set wins ===")
r = S.rule_with_defaults({"min_margin_pct": 20.0})
check("the one you set", r["min_margin_pct"], 20.0)
check("  the rest defaulted", r["referral_rate"], 0.15)
check("a NULL column does not wipe a default",
      S.rule_with_defaults({"min_margin_pct": None})["min_margin_pct"], 10.0)
check("'no limit' is the default anyway",
      S.rule_with_defaults({})["max_dispatch_days"], None)
check("nothing at all is still a complete rule",
      len(S.rule_with_defaults(None)), len(S.DEFAULT_RULE))


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
check("an enrolment round-trips",
      conn.execute("SELECT mode FROM sourcing_enrolment").fetchone()["mode"], "dry_run")
check("a dry-run action is stored as not applied",
      conn.execute("SELECT applied FROM sourcing_actions").fetchone()["applied"], 0)
check("nothing is enrolled by default",
      conn.execute("SELECT COUNT(*) c FROM sourcing_enrolment WHERE workspace_id='other'"
                   ).fetchone()["c"], 0)

os.environ.pop("ALTASCRAPER_DB", None)
try:
    conn.close()
except Exception:
    pass
shutil.rmtree(TMP, ignore_errors=True)

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
