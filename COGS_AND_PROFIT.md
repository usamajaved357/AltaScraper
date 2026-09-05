# How cost of goods and account profit are worked out

Written 5 Sep 2026, from the code and from this machine's live database.
Every number in here was measured, not assumed. Re-measure before quoting them
later — the code notes are dated for the same reason.

---

## The short answer

**There are two cost systems, and they are not duplicates.** They answer two
different questions:

| | System A | System B |
|---|---|---|
| Question | *What does this product cost?* | *What did **this order** cost?* |
| Lives in | `cogs_overrides.json` + the SKU name | the `order_lines.cogs` column |
| Code | `domain/cogs.py`, `domain/cogs_store.py` | `domain/order_cogs.py` |
| Set from | the Listings cost column, or a cost sheet | frozen automatically, once, when the order is first seen |
| Read by | Listings, Repricer, Orders, Inventory | the Sales profit card, contribution |

System B **freezes** its answer. System A is always live. That is deliberate:
if an order from July were re-costed today it would pick up August's supplier
price, and last month's profit would move every time a supplier changed theirs.

**Account profit today, Nestwell Goods / UK, 6 Aug – 4 Sep: £424.01.**
It is not yet a number to run the business on, and the app says so itself
(`complete: False`). The reasons are in Part 2.

---

# Part 1 — Cost of goods

## Where a cost comes from, in order of trust

`domain/order_cogs.py:100` `resolve()` is the one place that decides. It tries,
in this order, and stops at the first answer:

1. **A correction typed against that one order** → source `manual-order`
   Wins over everything, and applies to that order alone. Asked for in exactly
   those terms: *"my typed cogs win but it should be only for that order not all
   time frames and all orders."*
2. **The supplier price in force when the order arrived** → source `tracked`
   Only in `tracked` mode. The newest reading taken *at or before* the moment
   the order arrived — a later reading describes a price that order never paid.
3. **A cost typed against the product** → source `manual`
   From `cogs_overrides.json`. Applies to every order, past and future.
4. **The cost written into the SKU** → source `sku`

If none of them answer, the cost is `None`. **Never `0`.** A zero cost makes a
product look infinitely profitable, and that is precisely the product somebody
would then order more of.

## The SKU carries the cost

The generator builds SKUs as `{source_cost}_{N}Days_{COMPETITOR_ASIN}` — for
example `13.02_3Days_B0D25XZLMJ`. So the cost is already written on every SKU the
app generated, and does not need entering again.

`domain/cogs.py:35` `cost_from_sku()` reads everything before the first
underscore and accepts it if it is a positive number. Two traps it handles:

- **`0.00` means unknown, not free.** `build_sku` writes `0.00` when it had no
  cost to write, so a zero is rejected rather than believed.
- **The ASIN in that SKU is the *competitor's*, not ours** (CLAUDE.md Rule 1).
  Only the leading cost is ever read from it. Nothing here uses that ASIN to
  identify one of our listings.

Hand-made SKUs — `AltaboltaVoo Ceiling Fan`, `46 pcs wrench` — carry no cost and
never can. Those need a typed one.

## The two modes

Set per account (`cogs_mode`), same as VAT. `domain/order_cogs.py:50`.

- **`sku`** — the cost in the SKU, overridden by a cost typed against the
  product. Simple, and right for stock bought once at a known price.
- **`tracked`** — the repricer checks each supplier every few hours and records
  the price *with the time it was read*. An order is costed at the price that was
  true when it arrived. Falls back to the `sku` rule for orders placed before the
  repricer ever saw that product.

## What is *not* in the cost of goods

The supplier's price already includes their postage — *"the source price is
actual source price including shipping"* — so nothing is added for inbound
carriage.

Everything the seller pays **after** that is a separate layer:
`domain/asin_charges.py`. Postage out, prep and labelling, a hand-allocated
advertising figure. One row per named charge rather than a column per kind,
because the list of things a seller pays for is not fixed. Each charge is
**per unit** and **dated**, so raising today's prep fee does not silently rewrite
what last month earned.

## Measured state, this machine, 5 Sep 2026

**No cost has ever been typed by hand, on any account.**
`cogs_overrides.json` holds **0 entries**. Every cost in the system today was
read out of a SKU name.

| Account | Mode | VAT | SKUs with a readable cost |
|---|---|---|---|
| nestwell_goods | sku | 0 | **86 of 86** |
| jack_uk | tracked | 0.2 | 67 of 88 |
| headbanger_lures | sku | 0 | 32 of 115 |
| selvora_limited | sku | 0 | 3 of 13 |
| sheelady_us | sku | 0 | 1 of 1 |

Frozen per-order costs (System B):

| Account | Order lines | Costed | Sources |
|---|---|---|---|
| nestwell_goods | 61 | 32 (52.5%) | `sku`=32, none=29 |
| jack_uk | 18 | 18 (100%) | `sku`=18 |
| selvora_limited | 126 | **0** | none=126 |

**Every frozen cost in the system is marked `sku`.** Not one `tracked`, not one
`manual`. jack_uk is on tracked mode and still has none, because the repricer's
readings all post-date its orders and tracked mode only uses a reading taken
*before* the order.

## The one thing worth fixing first

Nestwell has a readable cost on **all 86** of its SKUs, yet only **52.5%** of its
order lines are costed. That looks contradictory. It is not:

> **All 29 uncosted lines are a single SKU — `AltaboltaVoo Ceiling Fan`.**
> It is hand-named, so no cost can be read from it, and it is not in the listings
> table either, so there is nothing to read one from.

Typing one cost against that SKU takes Nestwell from 52.5% costed to 100%, and
takes its profit figure from "overstated by an unknown amount" to "as good as the
fee estimate underneath it".

Selvora is a bigger job: 126 lines, none costed, and only 3 of 13 SKUs carry a
readable cost.

---

# Part 2 — Account-level profit

## Two calendars, and why profit lives on the order one

Amazon dates its two feeds differently, and this caused a row of cards to
contradict itself — *"Total Sales £0"* beside *"Profit £80"*:

- **Orders API / Sales & Traffic report** — dated when the order was **placed**
- **Finance records** — dated when the **money moved**

An order placed yesterday is a sale yesterday and a profit whenever Amazon
settles it, which can be weeks later. Amazon cannot answer *"what did I make on
yesterday's orders"* — it reports no profit against an unsettled order. The
seller can, because they know what the stock cost.

So `domain/order_profit.py` works profit out on the **order** calendar, from the
seller's own costs. The Sales page states which calendar it is on.

## The formula

```
  revenue          item price + the postage the buyer paid
                   (everything the buyer handed over)
- VAT              only where the company is registered — per account, never assumed
- Amazon fees      revenue x the rate THIS account actually pays
- cost of goods    frozen onto the order (Part 1)
- promotions       coupons and deals you funded
- charges          postage out, prep, hand-allocated ads (asin_charges)
- ad spend         ONLY when the Advertising API is connected
                   ─────────────
                   = profit
```

Ad spend was the missing line until this week. *"When the api is not there do not
subtract anything"* — so nothing was subtracted, and the figure said so.

**The effect of connecting it, measured on Nestwell / UK, 6 Aug – 4 Sep:**

| | |
|---|---|
| Profit before the Ads API | £680.94 |
| Profit with ad spend subtracted | **£424.01** |
| The difference | £256.93 of advertising |

That money was always leaving the account. The app simply could not see it.

## The fee rate is measured, not assumed

`domain/order_profit.py:80` `fee_rate()`. Every fee Amazon has actually taken,
over everything buyers were actually charged, across the recent settled past.
That is this seller's own products in their own categories — which a flat 15% is
not.

Measured today:

| Account | Rate | Basis | Measured over |
|---|---|---|---|
| nestwell_goods | **18.01%** | measured | £344.90 of settled sales |
| jack_uk | 17.50% | measured | £402.39 |
| selvora_limited | 18.04% | measured | £1,909.11 |

Two safeguards worth knowing about:

- Below `MIN_PRINCIPAL_FOR_RATE` (£50 of settled sales) the measurement is not
  trusted and Amazon's usual referral rate is used instead, labelled `assumed`.
- **Fixed charges are excluded from the rate.** The £25/month Professional
  selling subscription does not scale with revenue. Including it once turned a
  real 17.5% into 24.1% on jack_uk, which then came off every estimated profit as
  though the subscription grew with sales.

Those ~18% rates are not an error. Amazon charges **VAT on its own fees** for
these accounts, so the true rate is around 18% where a fee *estimate* would
suggest ~15%.

## What Amazon actually settles

`finance_daily` stores it, one row per day (`asin='*'` is the account roll-up;
there are per-ASIN rows beside it, so summing the whole table double counts):

`referral_fees`, `fba_fees`, `other_fees`, `refunds`, `refund_units`,
`refund_fees_returned`, `reimbursements`, `promos`, `principal`, `tax`,
`refund_tax`, `units`, `cogs`, `cogs_units`.

Settled to date on this machine:

| Account | Days | Principal | Referral | FBA | Other |
|---|---|---|---|---|---|
| selvora_limited | 10 | £1,909.11 | £344.34 | £0.00 | £68.94 |
| jack_uk | 11 | £402.39 | £70.40 | £0.00 | £51.43 |
| nestwell_goods | 5 | £344.90 | £62.10 | £0.00 | £61.28 |

FBA fees are £0.00 across the board because these are seller-fulfilled accounts.

---

# The gaps — why the number is not yet accurate

In the order they cost you accuracy.

### 1. Uncosted units — the biggest, and it only ever flatters

An uncosted unit contributes its revenue and no cost. Asked for deliberately:

> *"if no cogs are added show profit as wrong i agree do not subtract cogs this
> is the standard way, the user should know he needs to add cogs otherwise the
> profit numbers wont be accurate."*

So the figure is shown with a loud warning rather than hidden. On Nestwell:
**21 of 52 units have no cost**, cost coverage is **34.9%** of revenue
(£451.87 of £1,294.97), and profit is therefore **higher than the truth**.

Real profit is **lower than £424.01**. By how much is unknown until that one SKU
is costed.

### 2. VAT is set to zero on five of six accounts

Only jack_uk has `vat_rate: 0.2`. Nestwell, Selvora, Sheelady, Headbanger and
Miles are all `0`. If any of those companies is VAT-registered, its profit is
**overstated by roughly a fifth**, because Amazon reports order values with VAT
already inside them and that portion is HMRC's, not the seller's.

This is a question about the businesses, not about the code. It cannot be
answered from here and must never be guessed.

### 3. Fixed charges are excluded from profit, not just from the rate

Excluding the subscription from the **rate** is correct. But nothing then
subtracts it from **account-level** profit, and it is real money:
**£61.28** on Nestwell, £51.43 on jack_uk, £68.94 on Selvora over the settled
window.

`domain/contribution.py:241` `unattributed()` already identifies charges with no
SKU for the per-product screen. The account-level profit figure does not use it.

### 4. The fee rate rests on a thin sample

Nestwell's 18.01% comes from **£344.90 of settled sales over 5 days**. That is
above the £50 floor, so it is used — but a handful of orders in unusual
categories would move it, and the fee rate moves profit more than anything else
in the formula. It tightens on its own as more orders settle.

### 5. Orders and Sales can disagree about the same order

`/orders/detail` and `/orders/list` read **System A** (live, product-level).
The Sales profit card goes through `order_profit.for_period` → `order_lines.cogs`
— **System B** (frozen).

They agree today only by coincidence: every frozen cost is marked `sku`, which is
what System A returns too. The day a tracked supplier price lands, or anyone
corrects a single order, **the same order will show one profit on Orders and a
different one inside Sales.**

Correcting one order (`/cogs/order`) is now wired up in `static/js/orders.js` —
that part of the older note is out of date — which makes this divergence
reachable rather than theoretical.

### 6. Two upload paths for the same store

Listings' "COGS CSV" → `/cogs/upload_sheet` (server-side, reads spreadsheets,
per-row report). The Sales bar's "Upload a cost sheet" → `/cogs/upload`
(browser-side, CSV only). Same destination, so nothing is lost — but its column
matcher accepts a column named `price`, which on a listings export is the
**selling** price, not the cost. A Rule 12 duplication with a real trap in it.

### 7. One stale claim in the code

`domain/contribution.py` still says in its docstring: *"Nothing writes to
ads_daily — there is no Advertising API client and no upload route — so ad spend
is UNKNOWN."* That is no longer true; the module already reads `ads_daily` at
lines 108–111 and fills `ad_spend` from it. Its own instruction — *"Rename it the
moment ad spend arrives, and not before"* — is now due: the figure is still
labelled **"contribution before advertising"** when advertising is in it.

---

# What to do, in order

| # | Action | Effect |
|---|---|---|
| 1 | Type a cost for `AltaboltaVoo Ceiling Fan` | Nestwell 52.5% → 100% costed |
| 2 | Confirm the VAT position of each company | removes a possible 20% overstatement |
| 3 | Cost Selvora's 126 uncosted lines | it currently has no profit figure at all |
| 4 | Subtract fixed charges at account level | ~£61 a month per account, currently missed |
| 5 | Make Orders and Sales read one system | stops two screens disagreeing about one order |
| 6 | Merge the two cost-sheet uploaders | removes the `price`-means-selling-price trap |
| 7 | Rename "contribution before advertising" | it is no longer before advertising |

Items 1–3 are yours. Items 4–7 are code.

---

## Where everything lives

| File | Holds |
|---|---|
| `domain/cogs.py` | the RULES — which cost wins, how one is read from a SKU |
| `domain/cogs_store.py` | the STORE — `cogs_overrides.json`, loaded once, never rebound |
| `domain/order_cogs.py` | per-order cost, frozen; tracked vs sku modes |
| `domain/asin_charges.py` | per-unit charges on top of the supplier price |
| `domain/order_profit.py` | profit on the ORDER calendar; the measured fee rate |
| `domain/finance_data.py` | what Amazon actually settled |
| `domain/contribution.py` | per-product contribution, on the MONEY calendar |
| `routes/cogs_routes.py` | template, upload, set, count, clear |
| `routes/cogs_mode_routes.py` | mode, single-order correction, re-freeze |

`cogs_store.py` exists because of a real bug worth remembering: the overrides
used to live in `dashboard.py`, and other modules reached them with
`import dashboard`. `dashboard.py` is the file that is *run*, so its module name
is `__main__` — `import dashboard` loaded the file a **second** time, with its own
empty dict that nothing ever filled. Every consumer that did this read a
permanently empty set of overrides. Sales and Orders ignored every manual cost
that had ever been set. Nobody imports `dashboard` for this any more.
