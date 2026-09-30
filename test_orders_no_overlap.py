# -*- coding: utf-8 -*-
"""The Orders board must not overprint its cells when an order is open (30 Sep 2026).

Owner's roadmap: "the Orders screen issue where selecting an order causes the
main area to shrink and content to overlap is a REAL BUG".

Root cause (measured at 1024/1366/1920): the board is a `table.kv`, which is
`table-layout:fixed` (01-shell.css), so the columns never widened for their
content and never scrolled -- the text ran into the next cell. And the side
panel opened beside the table on the assumption the table needs 760px when its
nine columns need ~960px.

Fix: the board lays out by content (`table-layout:auto`), beside an open order
the list goes compact (.ord-compact, five columns) so 520 + 400 + gutter is
enough (every desktop window; was 980 + 380, which sent laptops inline), and
641-900px uses the phone's card rows. tools/browser_smoke.py measures the real thing ("no_overprint").
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(label, ok):
    if not ok:
        fails.append(label)
    print("  %-72s %s" % (label, "OK" if ok else "FAIL"))


def read(p):
    return open(os.path.join(HERE, p), encoding="utf-8").read()


css = read("static/css/orders_panel.css")
js = read("static/js/orders.js")
smoke = read("tools/browser_smoke.py")

check("the board lays out by content, not table.kv's fixed layout",
      re.search(r"table\.ordtable\.ord-board-table\s*\{\s*table-layout\s*:\s*auto", css) is not None)
check("641-900px uses card rows",
      "@media (min-width: 641px) and (max-width: 900px)" in css)
check("the countdown stays on one line",
      re.search(r"\.ord-due\s*\{\s*white-space\s*:\s*nowrap", css) is not None)
m = re.search(r"const ORD_SIDE_MIN\s*=\s*([^;]+);", js)
# Re-pinned 30 Sep 2026 (master-detail): beside the panel the list is compact
# (.ord-compact: tick, order, item, state, profit), which fits in ~520px, so the
# panel is used on every desktop window again. The full nine columns only ever
# show with no panel beside them.
check("the side panel opens beside the list only when 520px of compact list fits",
      bool(m) and m.group(1).replace(" ", "").startswith("520+400"))
check("  and beside the panel the list hides the columns that do not fit",
      "table.ord-board-table.ord-compact{ min-width: 0 !important; }" in css
      and all('ord-compact [data-label="%s"]' % c in css
              for c in ("Account", "Channel", "Due / next", "Cost", "Next step")))
check("browser smoke measures overprinting cells, not only the scroller",
      'osd["no_overprint"]' in smoke and '"no_overprint"' in smoke.split('osd["no_overprint"]', 1)[1])

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
