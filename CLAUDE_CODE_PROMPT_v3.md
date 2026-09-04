## 6. Sales page — Organic vs PPC chart draws dotted/broken lines on zero-sale days

The main Sales chart (Orders + Sales + Profit) draws clean continuous 
lines that go through zero — consistent, no gaps. Good.

The "Organic vs PPC Sales" chart below it draws dotted/broken lines 
that disconnect on days with zero sales. This creates visual gaps 
and inconsistency between the two charts on the same page.

Fix: the Organic vs PPC chart should draw solid continuous lines 
through zero-value days, exactly like the Sales chart above it does. 
A zero-sale day is a data point at y=0, not a missing data point. 
The line should connect through it, not break.

Find where the Organic vs PPC chart is rendered (likely in the sales 
page JS file). The issue is probably one of:
- Missing data points for zero-sale days (the chart library skips 
  them) — fix by ensuring every day in the range has a data point, 
  even if the value is 0
- The chart is configured with `spanGaps: false` or equivalent — 
  change to true, or use solid line style
- The line style is set to dashed/dotted — change to solid, matching 
  the Sales chart's line style

Both charts on the same page should use the same line rendering 
approach: solid, continuous, no gaps on zero days.
