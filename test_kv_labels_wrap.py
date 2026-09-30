# -*- coding: utf-8 -*-
"""A label in a table.kv wraps instead of being clipped (responsive audit, 30 Sep 2026).

Measured at 390px on the brand setup screen: "Competitor ASINs (optional)" was
cut to "Competitor ASINs (optiona" -- the global `td.k{white-space:nowrap}`
(01-shell.css) beat table.kv's own overflow-wrap in a fixed 38% column.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
css = open(os.path.join(HERE, "static", "css", "dashboard", "01-shell.css"), encoding="utf-8").read()
m = re.search(r"table\.kv td\.k\{([^}]*)\}", css)
ok = bool(m) and "white-space:normal" in m.group(1).replace(" ", "")
print("  table.kv td.k sets white-space:normal over the global nowrap   ", "OK" if ok else "FAIL")
brand = open(os.path.join(HERE, "templates", "brand_panel.html"), encoding="utf-8").read()
ok2 = "100550" in brand and "ui-hint" in brand and "Neither does anything else in this app" not in brand
print("  brand setup opens with one line; the explanation is behind an (i)", "OK" if ok2 else "FAIL")
sys.exit(0 if ok and ok2 else 1)
