"""Seed the stock history from the snapshots already stored.

domain/stock_history.py records a quantity every time the live catalogue
refreshes, which means the history starts empty and fills a day at a time. But
the app is ALREADY holding one live snapshot per account, each with the
timestamp it was taken at -- and a snapshot is exactly the reading the recorder
would have written.

So this seeds those readings under THEIR OWN dates. It does not invent a past:
one snapshot gives one day, the day it was taken, and nothing before it.

Preview (writes nothing):   python tools/seed_stock_history.py
Apply:                      python tools/seed_stock_history.py --apply
"""
import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain import live_snapshots as _ls
from domain import stock_history as _sh

CFG = "config.json"


def main(apply_it):
    summary = _ls.summary(CFG) or {}
    recs = summary if isinstance(summary, dict) else {}
    # summary() shape varies; read the store directly for the items.
    store = _ls._read_all(CFG) or {}
    total = 0
    print("%-34s %-10s %6s  %s" % ("snapshot", "date", "items", "action"))
    for k, rec in sorted(store.items()):
        items = (rec or {}).get("items") or []
        # ts is a Unix epoch, not an ISO string -- reading it as text gave
        # "1787146771" as the date and skipped every snapshot.
        raw = (rec or {}).get("ts")
        day = ""
        try:
            day = _dt.datetime.fromtimestamp(float(raw)).date().isoformat()
        except (TypeError, ValueError):
            day = str(raw or "")[:10]
        if not items or len(day) != 10:
            print("%-34s %-10s %6d  skipped (no items or no timestamp)"
                  % (k[:34], day or "?", len(items)))
            continue
        # key() is "<account>::<marketplace>"
        acct, _, mkt = k.partition("::")
        if apply_it:
            n = _sh.record(CFG, acct, mkt, items, when=day)
        else:
            n = len([i for i in items if str((i or {}).get("sku") or "").strip()])
        total += n
        print("%-34s %-10s %6d  %s" % (k[:34], day, n,
                                       "recorded" if apply_it else "would record"))

    print("\n%s %d reading(s)" % ("wrote" if apply_it else "would write", total))
    if not apply_it:
        print("PREVIEW ONLY -- re-run with --apply to write.")
    else:
        cov = {}
        for k in store:
            acct, _, mkt = k.partition("::")
            cov[k] = _sh.coverage(CFG, acct, mkt)
        print("\nhistory now held:")
        for k, c in sorted(cov.items()):
            print("   %-34s %d day(s)  %s..%s  %d sku(s)"
                  % (k[:34], c["days"], c["first"] or "-", c["last"] or "-", c["skus"]))
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
