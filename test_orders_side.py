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
truthy("  and only when the compact list keeps its width beside the panel",
       # 520 + 400, re-pinned 30 Sep 2026 (master-detail): beside an open order
       # the list is compact (.ord-compact, five columns), so it needs ~520px, not
       # the nine-column 980 -- which had pushed every laptop to the inline
       # "dropdown" the owner did not want.
       "ORD_SIDE_MIN = 520 + 400" in JS and "b.clientWidth >= ORD_SIDE_MIN" in JS)
truthy("the list goes compact while the panel is open",
       "(_openRow ? ' ord-compact' : '')" in JS
       and re.search(r"ord-compact \[data-label=\"Due / next\"\]", CSS)
       and re.search(r"ord-compact \[data-label=\"Next step\"\][^{]*\{\s*display:\s*none", CSS))
truthy("  the headings carry the same column names as the cells",
       "'<th data-label=\"' + _oEsc(t) + '\"'" in JS)
truthy("the panel is 400-480px wide", "clamp(400px, 32vw, 480px)" in CSS)
truthy("Escape closes the panel through the one global handler",
       "function ordersCloseSide" in JS
       and "ordersCloseSide" in open(os.path.join(HERE, "static", "js", "escape.js"), encoding="utf-8").read())
truthy("the harness expects the panel on every desktop width",
       'osd["side_on_desktop"]' in SMOKE and '"side_on_desktop"' in SMOKE.split('osd["side_on_desktop"]', 1)[1])
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
