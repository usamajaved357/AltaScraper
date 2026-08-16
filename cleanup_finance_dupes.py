"""Remove the duplicate copies of each account's finances.

WHAT HAPPENED. Amazon's Finances API is not segmented by marketplace --
listFinancialEvents takes no marketplace and returns everything the seller has
settled. The refresher walks (account, marketplace) pairs, so the same events
were pulled and stored once for EVERY marketplace on the account.

Measured before this ran:

    jack_uk           402.39 of principal under UK, and 402.39 again under FR
    selvora_limited  1909.11 under UK, and 1909.11 again under FR
    nestwell_goods    344.90 under UK, and 344.90 again under IT

All 81 settled orders were held twice.

The sales side is genuinely per-marketplace, so opening one of those other
marketplaces showed the whole account's fee bill against no sales at all.

domain/finance_fetch.py now stores these once, under the account's default
marketplace. This clears the copies that were written before it did.

NOTHING IS DELETED FROM THE DEFAULT MARKETPLACE. Only rows under a marketplace
that is not the account's default, and only where an identical row exists under
the default -- so a marketplace that ever held finance data of its own is left
alone. Run with --apply to make the change; without it, it only reports.
"""
import sys
sys.path.insert(0, r"D:\AltaScraper")

from data import db as _db
from config import settings as _settings

APPLY = "--apply" in sys.argv
CFG = "config.json"


def defaults():
    out = {}
    for a in (_settings.load_settings(CFG).accounts or []):
        a = a if isinstance(a, dict) else getattr(a, "__dict__", {}) or {}
        d = str(a.get("default_marketplace") or "").strip().upper()
        if a.get("id") and d:
            out[str(a["id"])] = d
    return out


def main():
    conn = _db.get_db(CFG)
    dflt = defaults()
    total = 0
    # LIKE COMPARED WITH LIKE. finance_daily holds BOTH an account-wide row
    # (asin='*') and a row per product for the same day, so summing the whole
    # table counts the same money twice and every marketplace then looks
    # different from every other. Only the account-wide rows are compared.
    for table, sums, where in (
            ("finance_daily", ("principal", "referral_fees"), " AND asin='*'"),
            ("order_fees", ("principal", "referral_fees"), "")):
        print("\n=== %s ===" % table)
        rows = conn.execute(
            "SELECT workspace_id, marketplace, COUNT(*) n, "
            "       ROUND(SUM(%s),2) a, ROUND(SUM(%s),2) b "
            "FROM %s WHERE 1=1%s GROUP BY workspace_id, marketplace "
            "ORDER BY workspace_id, marketplace" % (sums[0], sums[1], table, where)
        ).fetchall()
        for r in rows:
            ws, mkt = r["workspace_id"], r["marketplace"]
            d = dflt.get(str(ws))
            if not d:
                print("   %-18s %-4s %4s rows  KEPT (no default marketplace set)"
                      % (ws, mkt, r["n"]))
                continue
            if str(mkt).upper() == d:
                print("   %-18s %-4s %4s rows  KEPT (the default)" % (ws, mkt, r["n"]))
                continue
            # Only a copy if the SAME money is present under the default.
            same = conn.execute(
                "SELECT ROUND(SUM(%s),2) FROM %s WHERE workspace_id=? AND marketplace=?%s"
                % (sums[0], table, where), (ws, d)).fetchone()[0]
            if same is None or round(float(same or 0), 2) != round(float(r["a"] or 0), 2):
                print("   %-18s %-4s %4s rows  KEPT -- %s under the default is %s, "
                      "not %s, so this is not a copy"
                      % (ws, mkt, r["n"], sums[0], same, r["a"]))
                continue
            print("   %-18s %-4s %4s rows  %s  (a second copy of %s's %s)"
                  % (ws, mkt, r["n"], "DELETING" if APPLY else "would delete", d, r["a"]))
            total += r["n"]
            if APPLY:
                # The SAME rows that were compared, and no others -- deleting a
                # wider set than was checked is how a cleanup becomes a loss.
                conn.execute("DELETE FROM %s WHERE workspace_id=? AND marketplace=?%s"
                             % (table, where), (ws, mkt))
            left = conn.execute(
                "SELECT COUNT(*) FROM %s WHERE workspace_id=? AND marketplace=?"
                % table, (ws, mkt)).fetchone()[0]
            if left:
                print("        (%d row(s) under %s left in place -- not part of the "
                      "account-wide figures that were compared)" % (left, mkt))
    if APPLY:
        conn.commit()
        print("\n%d duplicate row(s) removed." % total)
    else:
        print("\n%d duplicate row(s) would be removed. Re-run with --apply to do it."
              % total)


if __name__ == "__main__":
    main()
