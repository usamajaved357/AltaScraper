# Does a write to "Handling Days" actually persist?
#
#     "i clicked on the handling time changed it to 2 ... i did this multiple
#      time in the past with days of break in between but still app shows 3"
#
# The inline box routes: lrEditBox(field:"handling") -> _lrSaveField ->
# _lrSaveCol(sku, "Handling Days") -> editField -> POST /edit -> _repo.set_field.
# This exercises the server half of that on the REAL store.
#
# SAFE: it writes each value back to ITSELF, so nothing changes. If a
# write-then-read-back does not return what was written, the store is the fault;
# if it does, the fault is above it, in the route or the browser.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCOUNT = "nestwell_goods"
HEADER = "Handling Days"

from data.store import ListingStore, SheetLikeStore
from listing import repo as _repo

ws = SheetLikeStore(ListingStore(ACCOUNT, config_path="config.json"))
headers = _repo.read_headers(ws)
print("=== the sheet this account writes to ===")
print("  headers: %d" % len(headers))
print("  '%s' present: %s" % (HEADER, HEADER in headers))
hits = [h for h in headers if "handl" in h.lower()]
print("  handling-ish headers: %s" % hits)
print("  find_col picks: %s" % _repo.find_col(
    headers, ("Handling Days", "Handling Time", "Handling", "Lead Time")))

grid = _repo.read_grid(ws)
print("  rows in grid: %d" % (len(grid) - 1 if grid else 0))

# Three rows that currently hold something, to write back unchanged.
sample = []
try:
    hidx = headers.index(HEADER)
    sidx = headers.index("SKU")
except ValueError as e:
    print("  cannot locate a column: %s" % e)
    raise SystemExit(1)

for row in (grid[1:] if grid else []):
    if len(row) > max(hidx, sidx) and row[sidx] and row[hidx]:
        sample.append((row[sidx], row[hidx]))
    if len(sample) >= 3:
        break

print("\n=== write-back test (value -> same value) ===")
for sku, val in sample:
    found = _repo.locate(ws, sku, sku_headers=("SKU",))
    if not found:
        print("  %-30s NOT FOUND by locate()" % sku[:30])
        continue
    before = _repo.cell_value(ws, found.row, headers.index(HEADER) + 1)
    ok = _repo.set_field(ws, found.row, HEADER, str(val), headers=found.headers)
    after = _repo.cell_value(ws, found.row, headers.index(HEADER) + 1)
    print("  %-30s row=%-4s before=%-4r set=%s after=%-4r %s"
          % (sku[:30], found.row, before, ok, after,
             "OK" if str(after) == str(val) else "MISMATCH"))

print("\n=== how many rows hold each value ===")
from collections import Counter
c = Counter(str(r[hidx]) if len(r) > hidx else ""
            for r in (grid[1:] if grid else []))
print("  %s" % dict(c))
