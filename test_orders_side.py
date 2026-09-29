"""The order opens BESIDE the table on a laptop or wider, and under its row below.

Owner decision, 28 Sep 2026: "Keep the Orders table as the main view. On
laptop/desktop, clicking/selecting an order may open the side detail panel. The
detail panel must not replace the main table workflow."

The behaviour itself (panel where expected, another row swaps it, keyboard,
account switch closes it) is driven in a real browser by tools/browser_smoke.py
("orders_side"). This pins the source so the decision cannot quietly regress
between browser runs.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
JS = open(os.path.join(HERE, "static", "js", "orders.js"), encoding="utf-8").read()
CSS = open(os.path.join(HERE, "static", "css", "orders_panel.css"), encoding="utf-8").read()
SMOKE = open(os.path.join(HERE, "tools", "browser_smoke.py"), encoding="utf-8").read()

fails = []


def truthy(label, cond):
    print("  %-72s %s" % (label, "OK" if cond else "FAIL"))
    if not cond:
        fails.append(label)


truthy("side mode is decided at 1100px", '"(min-width: 1100px)"' in JS)
truthy("  and only when the table keeps its width beside the panel",
       "ORD_SIDE_MIN = 760 + 380" in JS and "b.clientWidth >= ORD_SIDE_MIN" in JS)
truthy("the panel is a second column (.ord-split), not an overlay",
       "ord-split" in JS and re.search(r"\.ord-split\s*\{[^}]*grid-template-columns", CSS))
truthy("the panel has no scrim and is not position:fixed",
       not re.search(r"\.ord-side\s*\{[^}]*position:\s*fixed", CSS) and "ord-scrim" not in CSS)
truthy("inline detail row still drawn when there is no side panel",
       "if(isOpen && !_openRow)" in JS and "orddetail" in JS)
truthy("rows are reachable from the keyboard",
       'tabindex="0"' in JS and "function ordersRowKey" in JS)
truthy("focus survives the redraw", "_ordFocusedOid()" in JS and "function _ordRefocus" in JS)
truthy("a detail reply is filed in the cache it was asked for",
       "const cache = ORD.details;" in JS and "ORD.details === cache" in JS)
truthy("the panel can be closed with a named button",
       'aria-label="Close this order"' in JS)
truthy("the browser harness drives it", 'log["orders_side"]' in SMOKE)

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\nall orders side-panel checks passed")
