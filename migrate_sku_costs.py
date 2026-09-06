"""migrate_sku_costs.py -- turn every SKU-derived cost into a cost you SET.

WHY THIS RUNS ONCE, BEFORE THE PARSE IS REMOVED.

The app used to read a cost out of the SKU itself: `15.10_2Days_B0F7D29MFZ` was
taken to cost 15.10. That is being removed -- a cost should be something the
owner sets, not something inferred from a filename.

But measured first: EVERY cost in the database came from that parse. 50 of 50
costed order lines, and the per-product store held ONE entry. Removing the parse
without this migration would have taken profit, margin, contribution and
break-even ACOS to "not known" on every screen at once.

So the values are copied into the per-product store first, exactly as though
they had been uploaded. They keep working, they are now visible and editable
where every other cost is, and the SKU string is never consulted again.

WHAT IS AND IS NOT WRITTEN
  * only SKUs that actually parse to a number greater than zero
  * never over an existing entry -- a cost somebody typed already wins
  * only SKUs this account has really sold, so the store does not fill with
    products that were generated and never ordered

Safe to run twice: the second pass writes nothing.

    python migrate_sku_costs.py            report only, changes nothing
    python migrate_sku_costs.py --apply    write them
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db                        # noqa: E402
from domain import cogs as _cogs                  # noqa: E402
from domain import cogs_store as _store           # noqa: E402

CONFIG_PATH = os.path.join(HERE, "config.json")
APPLY = "--apply" in sys.argv


def main():
    conn = _db.get_db(CONFIG_PATH)
    before = _store.load(CONFIG_PATH) or {}
    print("per-product cost store holds %d entr%s before this run"
          % (len(before), "y" if len(before) == 1 else "ies"))

    # Every SKU this account has actually sold, with how much it sold.
    rows = conn.execute(
        "SELECT workspace_id, sku, COUNT(*) n, "
        "       SUM(CASE WHEN cogs IS NOT NULL THEN 1 ELSE 0 END) costed "
        "FROM order_lines WHERE COALESCE(sku,'') <> '' "
        "GROUP BY workspace_id, sku ORDER BY workspace_id, sku").fetchall()

    plan, skipped_named, skipped_have = [], 0, 0
    for r in rows:
        ws, sku = r["workspace_id"], r["sku"]
        key = "%s::%s" % (ws, sku)
        if key in before:
            skipped_have += 1
            continue
        cost = _cogs.cost_from_sku(sku)
        if cost is None:
            # A hand-named SKU carries no number, so there is nothing to carry
            # over. It had no cost before this change and has none after it --
            # the migration does not invent one.
            skipped_named += 1
            continue
        plan.append((ws, sku, round(float(cost), 4), r["n"]))

    print("\n%d SKU(s) would be written:" % len(plan))
    by_ws = {}
    for ws, sku, cost, n in plan:
        by_ws.setdefault(ws, []).append((sku, cost, n))
    for ws in sorted(by_ws):
        items = by_ws[ws]
        print("  %-18s %d SKU(s)" % (ws, len(items)))
        for sku, cost, n in items[:6]:
            print("      %-34s %8.2f   (%d order line(s))" % (sku[:34], cost, n))
        if len(items) > 6:
            print("      ... and %d more" % (len(items) - 6))

    print("\n%d hand-named SKU(s) carry no number and are left alone"
          % skipped_named)
    print("%d SKU(s) already have a cost you set, and are not touched"
          % skipped_have)

    if not APPLY:
        print("\nREPORT ONLY. Nothing was written. Run again with --apply.")
        return

    n = 0
    for ws, sku, cost, _cnt in plan:
        _store.set_cost(CONFIG_PATH, ws, sku, cost)
        n += 1
    after = _store.load(CONFIG_PATH) or {}
    print("\nwrote %d cost(s). The store now holds %d." % (n, len(after)))
    print("Every one of them is now a cost you SET, editable on the Listings "
          "COGS column, by cost-sheet upload, or per order on the Orders page.")


if __name__ == "__main__":
    main()
