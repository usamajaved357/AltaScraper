"""The Finance screen's questions about its own tables (architecture batch A6).

The four places routes/finance_routes.py asked the database directly -- which
marketplace has data, what the account has when a window is empty, how much of a
window settled, and whether anything sold after the last settled day -- moved,
statement for statement, into domain/finance_coverage.py. This drives the
endpoint through every branch those answers feed, on a fixture database, and
pins the exact JSON. Run against the pre-A6 route it gives the same answers.
"""
import os as _os_repo
_REPO = _os_repo.path.dirname(_os_repo.path.abspath(__file__))
import os, sys, json, tempfile
sys.path.insert(0, _REPO)

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


TMP = tempfile.mkdtemp(prefix="altafincov_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "c.db")

from data import db as _db


def fin(ws, mkt, date, asin, principal=10.0, units=1):
    conn = _db.get_db(CFG)
    conn.execute(
        "INSERT INTO finance_daily (workspace_id, marketplace, date, asin, "
        "referral_fees, fba_fees, other_fees, refunds, refund_units, "
        "reimbursements, promos, principal, units, cogs, cogs_units, currency, source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ws, mkt, date, asin, 1.0, 1.0, 0.0, 0.0, 0, 0.0, 0.0,
         principal, units, 4.0, units, "GBP", "test"))
    conn.commit()


def sale(ws, mkt, date, asin, units, revenue):
    conn = _db.get_db(CFG)
    conn.execute("INSERT INTO sales_daily (workspace_id, marketplace, date, asin, "
                 "units, ordered_sales) VALUES (?,?,?,?,?,?)",
                 (ws, mkt, date, asin, units, revenue))
    conn.commit()


# ws_one: finance only on DE -> marketplace worked out from its data (no state).
fin("ws_one", "DE", "2026-08-05", "B0ONE00001")
# ws_old: data in June only -> an August window is empty "outside the dates".
fin("ws_old", "UK", "2026-06-01", "B0OLD00001")
fin("ws_old", "UK", "2026-06-03", "B0OLD00001")
# ws_else: data only on US, asked about UK -> "switch marketplace".
fin("ws_else", "US", "2026-08-02", "B0ELS00001")
# ws_part: 1 of 2 sold products settled -> the "settled N of M" warning.
fin("ws_part", "UK", "2026-08-02", "B0PRT00001")
sale("ws_part", "UK", "2026-08-02", "B0PRT00001", 1, 10.0)
sale("ws_part", "UK", "2026-08-03", "B0PRT00002", 1, 12.0)
# ws_gap: everything that sold settled, but sales after the last settled day.
fin("ws_gap", "UK", "2026-08-02", "B0GAP00001")
sale("ws_gap", "UK", "2026-08-02", "B0GAP00001", 1, 10.0)
sale("ws_gap", "UK", "2026-08-10", "*", 3, 30.0)

from flask import Flask
import routes.finance_routes as fr
app = Flask(__name__); app.secret_key = "t"
STATE = {}
fr.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
            _active_account=lambda: {}, _state=STATE)
c = app.test_client()
W = "start=2026-08-01&end=2026-08-31&basis=settlement"


def ask(q):
    return c.get("/finance/contribution?%s&%s" % (W, q)).get_json() or {}


def texts(j):
    return [n.get("text") for n in (j.get("notes") or [])]


print("=== the marketplace, from the only one with data ===")
j = ask("account=ws_one")
check("answers on DE", (j.get("ok"), j.get("marketplace")), (True, "DE"))

print("=== empty, and why ===")
j = ask("account=ws_old&marketplace=UK")
check("outside the dates", j.get("empty_note"),
      "This account has 2 days of finance data, from 2026-06-01 to 2026-06-03 — "
      "but none between 2026-08-01 and 2026-08-31. Change the dates above to look "
      "at a period that has data; syncing again will not add days Amazon has no "
      "money movements for.")
j = ask("account=ws_else&marketplace=UK")
check("another marketplace", j.get("empty_note"),
      "Nothing for UK, but this account does have finance data for US. Switch "
      "marketplace at the top of the screen.")
j = ask("account=ws_never&marketplace=UK")
check("never pulled", (j.get("empty_note") or "")[:52],
      "No finance data has ever been pulled for ws_never on")

print("=== how much of the window settled ===")
j = ask("account=ws_part&marketplace=UK")
check("settled 1 of 2", any((t or "").startswith(
    "Amazon has settled 1 of the 2 products that sold in this period, and "
    "nothing after 2026-08-02.") for t in texts(j)), True)
j = ask("account=ws_gap&marketplace=UK")
check("sold after the last settled day", any((t or "").startswith(
    "Nothing has settled after 2026-08-02 yet") for t in texts(j)), True)

print("=== the route asks the database nothing itself ===")
src = open(os.path.join(_REPO, "routes", "finance_routes.py"), "rb").read().decode("utf-8")
check("no SQL left in routes/finance_routes.py",
      any(k in src for k in (".execute(", "SELECT ", "FROM finance_daily")), False)

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\nthe Finance screen's coverage answers are unchanged")
