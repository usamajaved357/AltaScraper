"""Remove day-rows that assert "no sales" for days nothing ever looked at.

WHAT HAPPENED. live_reconcile.from_lines() rewrites the sales side of a window
from the order history, and it wrote a row for EVERY day in the window it was
given -- including days before the order history begins, where it has no
evidence at all. A single year-to-date view therefore created a row for every
day back to January, all of them zero.

A zero written there does not mean "nothing sold that day". It means "we were
not looking". Those are opposite claims, and the second one is not ours to make.

The damage is not the rows themselves but what they made the app believe:
data_availability counts rows, so it reported these accounts as having data from
19 May 2025. Asking for 90 days then drew ninety columns of zeros instead of
saying there is nothing there -- reported as "the sales report and p&l heatmap
do not show data beyond 27th july no matter if i select 30 day, 60d or 90d".

from_lines is now clamped and cannot write outside the order history. This
clears what it wrote before that.

WHAT IS DELETED, AND ONLY THIS

  * account-wide rows (asin='*') only -- per-product rows come from the Sales &
    Traffic report and are left alone
  * written by the order feed (orders_source='orders_api') -- a row the report
    itself delivered is real evidence even when it is a zero
  * completely empty: no sales, no orders, no units, no sessions, no page views
  * dated BEFORE that account and marketplace's order history begins, so a
    genuine quiet day inside the trading period is never touched

Run with --apply to make the change; without it, it only reports.
"""
import sys
sys.path.insert(0, r"D:\AltaScraper")

from data import db as _db
from domain import sales_data as _sd

APPLY = "--apply" in sys.argv
CFG = "config.json"

EMPTY = ("COALESCE(ordered_sales,0)=0 AND COALESCE(orders,0)=0 AND "
         "COALESCE(units,0)=0 AND COALESCE(sessions,0)=0 AND "
         "COALESCE(page_views,0)=0")


def main():
    conn = _db.get_db(CFG)
    pairs = conn.execute(
        "SELECT DISTINCT workspace_id, marketplace FROM sales_daily "
        "ORDER BY workspace_id, marketplace").fetchall()
    total = 0
    for p in pairs:
        ws, mkt = p["workspace_id"], p["marketplace"]
        edge = conn.execute(
            "SELECT MIN(substr(purchase_date,1,10)) FROM order_lines "
            "WHERE workspace_id=? AND marketplace=?", (ws, mkt)).fetchone()[0]
        if not edge:
            # No order history at all for this pair, so there is no horizon to
            # measure against. Left completely alone rather than guessed at.
            n = conn.execute(
                "SELECT COUNT(*) FROM sales_daily WHERE workspace_id=? AND "
                "marketplace=? AND asin='*' AND orders_source='orders_api' AND "
                + EMPTY, (ws, mkt)).fetchone()[0]
            if n:
                print("   %-17s %-4s %5d empty row(s) KEPT -- no order history "
                      "to judge them against" % (ws, mkt, n))
            continue

        rows = conn.execute(
            "SELECT COUNT(*) n, MIN(date) a, MAX(date) b FROM sales_daily "
            "WHERE workspace_id=? AND marketplace=? AND asin='*' "
            "AND orders_source='orders_api' AND date < ? AND " + EMPTY,
            (ws, mkt, edge)).fetchone()
        if not rows["n"]:
            print("   %-17s %-4s nothing to remove (history from %s)"
                  % (ws, mkt, edge))
            continue
        print("   %-17s %-4s %5d empty row(s) %s  %s..%s, all before the order "
              "history starts (%s)"
              % (ws, mkt, rows["n"], "DELETING" if APPLY else "would delete",
                 rows["a"], rows["b"], edge))
        total += rows["n"]
        if APPLY:
            conn.execute(
                "DELETE FROM sales_daily WHERE workspace_id=? AND marketplace=? "
                "AND asin='*' AND orders_source='orders_api' AND date < ? AND "
                + EMPTY, (ws, mkt, edge))

    if APPLY:
        conn.commit()
        # Availability is derived from what is in the table, so it has to be
        # recomputed here or it keeps reporting the range that has just gone.
        for p in pairs:
            _sd._refresh_availability(conn, p["workspace_id"], p["marketplace"],
                                      "sales")
        print("\n%d row(s) removed, and availability recomputed." % total)
    else:
        print("\n%d row(s) would be removed. Re-run with --apply to do it."
              % total)


if __name__ == "__main__":
    print("Empty day-rows written where there was no evidence:\n")
    main()
