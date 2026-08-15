"""probe_sameday.py -- will Amazon give us TODAY's sessions and conversion?

CLAUDE.md Rule 4: do not guess. domain/sales_fetch.py hard-codes yesterday() as
the newest day it will ever request, so this app has never actually asked for
today -- the limit was assumed, not measured. That assumption decides whether the
Sales dashboard can ever show same-day traffic, so it is worth one real request.

Asks for each of the last few days INDIVIDUALLY (which is how sales_fetch asks)
and reports what came back for each. Reads only.

    python probe_sameday.py jack_uk UK
    python probe_sameday.py jack_uk UK --days 4
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
    account_id, marketplace = args[0], args[1].upper()
    days = 4
    if "--days" in argv:
        try:
            days = int(argv[argv.index("--days") + 1])
        except Exception:
            pass

    cfg = json.load(open("config.json", encoding="utf-8"))
    acc = next((a for a in (cfg.get("accounts") or [])
                if str(a.get("id")) == account_id), None)
    if not acc:
        print("no account called %r" % account_id)
        return 1

    from domain import accounts as _acc
    from domain import sales_fetch as _sf
    from sp_api.api import Reports
    from sp_api.base import Marketplaces

    mkt = getattr(Marketplaces, marketplace, None) or Marketplaces.UK
    rc = Reports(credentials=_acc.account_creds(acc), marketplace=mkt)

    today = dt.date.today()
    print("account : %s (%s)   today is %s\n" % (account_id, marketplace, today))
    print("%-12s %-12s %9s %10s %8s %9s  %s"
          % ("date", "when", "sessions", "pageviews", "units", "sales", "result"))

    for i in range(days):
        d = today - dt.timedelta(days=i)
        when = ("TODAY" if i == 0 else
                "yesterday" if i == 1 else "%d days ago" % i)
        try:
            rows = _sf.fetch_day(rc, mkt.marketplace_id, d.isoformat())
        except Exception as e:
            print("%-12s %-12s %9s %10s %8s %9s  REFUSED: %s"
                  % (d, when, "-", "-", "-", "-", str(e)[:70]))
            continue
        if not rows:
            print("%-12s %-12s %9s %10s %8s %9s  no rows returned"
                  % (d, when, "-", "-", "-", "-"))
            continue
        tot = {"sessions": 0, "page_views": 0, "units": 0, "ordered_sales": 0.0}
        for r in rows:
            if str(r.get("asin") or "") != "*":
                continue          # the '*' row is the account total
            for k in ("sessions", "page_views", "units"):
                try:
                    tot[k] += int(r.get(k) or 0)
                except (TypeError, ValueError):
                    pass
            try:
                tot["ordered_sales"] += float(r.get("ordered_sales") or 0.0)
            except (TypeError, ValueError):
                pass
        live = tot["sessions"] or tot["page_views"] or tot["units"]
        print("%-12s %-12s %9d %10d %8d %9.2f  %s"
              % (d, when, tot["sessions"], tot["page_views"], tot["units"],
                 tot["ordered_sales"],
                 "HAS DATA" if live else "returned, but empty"))

    print()
    print("If TODAY has sessions, same-day traffic is possible and sales_fetch's")
    print("yesterday() ceiling is costing a day. If it is empty or refused, the")
    print("ceiling is correct and the screen should say so rather than draw a zero.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
