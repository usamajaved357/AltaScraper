# Questions for Orbit's agent — how the Sales dashboard figures are calculated

Paste the block below into Orbit's agent. If it truncates or answers vaguely,
send it one lettered section at a time — the sections are independent.

Why each question is here is noted in `>` comments for our side only. **Do not
paste the `>` lines** — they are notes to us, not questions for Orbit.

---

## THE PROMPT (copy from here)

I'm a seller using Orbit and I want to reconcile your Sales dashboard against my
own Seller Central figures and my accountant's numbers. To do that I need to know
exactly how each figure is calculated, not just what it's called.

Please answer concretely — name the Amazon data source, the exact field, and the
formula where there is one. **If you don't know something, say "I don't know"
rather than giving a plausible answer.** A wrong explanation is worse than none,
because I'll reconcile against it and the difference will look like my mistake.

### A. Where each number comes from

1. For each of these, which Amazon source do you use — the Orders API, the Sales
   & Traffic report, the Finances/settlement API, or something else?
   Total Sales · Total Orders · Total Units · Sessions · Page Views ·
   Conversion · Buy Box % · Profit · Margin · Refunds · Ad Spend · TACOS
2. When two of those sources disagree about the same day, which one wins, and why?
3. Do you ever combine two sources into one displayed figure? If so, which ones?

> A1 tells us the field→feed map. A2/A3 is the exact mistake our app made
> (£0 sales beside £80 profit). If Orbit blends, we want to know how it avoids that.

### B. What "a sale" means

4. Is Total Sales the **item price only**, or does it include shipping charged to
   the buyer?
5. Does it include or exclude VAT/sales tax?
6. Are **refunds** subtracted from Total Sales? If yes, on the date of the
   original order or the date of the refund?
7. Are **cancelled** and **pending** orders included?
8. Is a multi-item order counted as one order or several?

> B4 is our £89.97 vs £102.21. B6 decides whether a past day's figure can move.

### C. Dates and freshness

9. Is a sale dated by when the **order was placed** or when the **money settled**?
10. Which timezone — the marketplace's, UTC, or my browser's?
11. How soon after an order is placed does it appear on the dashboard?
12. Do you show **today's** figures? If so, which of today's metrics are
    available and which are not?
13. Amazon's Sales & Traffic report runs about a day behind. What do you display
    for a day the report hasn't delivered — the live figure, a blank, or a zero?
14. Do you **revise** past days when Amazon revises them? How far back, and how
    often? Does a number I saw last week ever change?

> C13 is the core design question. C14 decides whether we store or recompute.

### D. Profit and fees — the important one

15. Is Profit an **estimate** or Amazon's **settled** figure? If it changes from
    one to the other, when, and do you show me that it changed?
16. What exactly is subtracted to get Profit? Please give the formula
    (e.g. sales − referral fee − FBA fee − COGS − ads − ...).
17. Where does the **cost of goods** come from — do I enter it, is it imported,
    or is it inferred?
18. If some products in a period have **no cost recorded**, what do you show —
    profit for the costed ones, a blank, or profit treating the cost as zero?
19. For an order Amazon hasn't settled, how do you estimate the **fees**? A flat
    percentage, a per-category rate, or measured from my own past settlements?
20. Are **refunds** and **returns** allowed for in estimated profit, given a
    refund can arrive weeks later?
21. Is **ad spend** included in Profit, or shown separately?
22. Is **VAT** handled in profit? Is my profit figure before or after VAT?

> D15/D19 is exactly the model Talha described. D18 is the open decision on our
> side (show partial + label, vs blank). D20 is the systematic-overstatement risk.

### E. Traffic and conversion

23. How is Conversion defined — units ÷ sessions, orders ÷ sessions, or something
    else? Which sessions figure (browser, mobile, or both)?
24. Sessions aren't available for today. What does the dashboard show for
    today's conversion?
25. How do you split **Organic vs PPC** sales? Which API, and is any of it
    estimated or apportioned?

> E25 matters — our app currently shows a 70/30 placeholder and says so.

### F. Presentation

26. Does the dashboard tell me which figures are provisional vs final, and how?
27. When a figure can't be calculated, do you show a zero, a blank, or a message?
28. What exactly is the comparison period ("vs previous")? The same number of
    days immediately before, the same dates last month, or last year?
29. If I sell in more than one marketplace or currency, are figures combined or
    kept separate? If combined, at what exchange rate and on what date?

> F27 is the "0 sessions today reads as a collapse" trap. F28 we already match.

### G. The other screens

30. **Hourly Sales** — which source, which timezone, and is it available for the
    current day?
31. **P&L / heatmap** — which basis is each row on, and are any rows on a
    different basis from the others?
32. **Traffic & Conversions** — same question as A1 for each column on that page.

## (copy to here)

---

## What we do with the answers

| Their answer to | Settles for us |
|---|---|
| A1, A2, A3 | the field→feed map, and their rule for conflicts |
| B4 | confirms item-price (we already measured £89.97 both ways) |
| B6, C14 | whether stored figures may be revised — storage design |
| C13, F27 | what to draw for a day Amazon hasn't delivered |
| D15, D16, D19 | the estimated-profit formula and fee model |
| D18 | the partial-COGS decision that is currently open |
| D20 | whether to subtract an expected-refund rate |
| E25 | whether a real organic/PPC split is possible for us |
| C10, G30 | timezone handling, which we currently do per marketplace |
