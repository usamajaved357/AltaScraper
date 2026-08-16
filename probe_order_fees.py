"""probe_order_fees.py -- do the fees land on the day the ORDER was placed?

The P&L grid had sales on one calendar and fees on another, never overlapping.
This reads Amazon's real financial events, keeps the order id, and shows each
fee against BOTH dates -- the day the money moved, and the day the order was
placed -- so the shift is visible rather than asserted.

Reads Amazon; writes nothing.

    python probe_order_fees.py jack_uk UK
    python probe_order_fees.py jack_uk UK --days 45
"""
import json
import sys
import datetime as dt

sys.path.insert(0, r"D:\AltaScraper")


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    aid, marketplace = args[0], args[1].upper()
    days = 30
    if "--days" in argv:
        try:
            days = int(argv[argv.index("--days") + 1])
        except Exception:
            pass

    cfg = json.load(open("config.json", encoding="utf-8"))
    acc = next((a for a in (cfg.get("accounts") or [])
                if str(a.get("id")) == aid), None)
    if not acc:
        print("no account called %r" % aid)
        return 1

    from domain import accounts as _acc
    from domain import finance_fetch as _ff
    from domain import order_finance as _of
    from data import db as _db
    import dashboard as D

    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    payload = _ff.raw_sample(marketplace, _acc.account_creds(acc),
                             start.isoformat(), end.isoformat())
    rows, skipped = _of.parse_by_order(payload)
    print("account %s (%s)   %s .. %s" % (aid, marketplace, start, end))
    print("%d order-day rows parsed, %d events had no order id\n" % (len(rows), skipped))
    if not rows:
        print("Nothing settled in this window.")
        return 0

    # When was each of those orders actually placed?
    conn = _db.get_db(D.CONFIG_PATH)
    placed = {}
    for r in conn.execute(
            "SELECT DISTINCT order_id, substr(purchase_date,1,10) AS d "
            "FROM order_lines WHERE workspace_id=? AND marketplace=?",
            (aid, marketplace)):
        placed[r["order_id"]] = r["d"]

    print("%-22s %-12s %-12s %9s %9s %9s"
          % ("order", "money moved", "order PLACED", "charged", "fees", "shift"))
    print("-" * 80)
    known = unknown = 0
    tot_fees = 0.0
    for r in sorted(rows, key=lambda x: x["posted_date"]):
        oid = r["order_id"]
        p = placed.get(oid)
        fees = round(r["referral_fees"] + r["fba_fees"] + r["other_fees"], 2)
        tot_fees += fees
        if p:
            known += 1
            shift = (dt.date.fromisoformat(r["posted_date"])
                     - dt.date.fromisoformat(p)).days
            shift_s = "%+dd" % shift
        else:
            unknown += 1
            shift_s = "order not held"
        print("%-22s %-12s %-12s %9.2f %9.2f %9s"
              % (oid[-20:], r["posted_date"], p or "-",
                 r["principal"], fees, shift_s))

    print("-" * 80)
    print("%d order(s) can be dated to when they were placed, %d cannot"
          % (known, unknown))
    print("total fees in this window: %.2f" % tot_fees)
    print()
    if unknown:
        print("The ones that cannot are orders older than this app's own order")
        print("history. They are reported, never guessed onto a date.")
    if known:
        print("Everything else can now be shown on the SAME day as its sale,")
        print("which is what puts the P&L grid on one calendar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
