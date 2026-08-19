"""domain/dr_ppc.py -- read the advertising data and say what is wrong with it.

    Orbit calls this the Dr PPC Console.

IT RECOMMENDS. IT NEVER ACTS.

CLAUDE.md Rule 8: "NEVER change bids or budgets on any campaign unless the user
explicitly specifies in their message the exact new value to set." So every
finding here names the exact figure it would use and stops. Nothing in this
module or the route above it can write to Amazon -- api/amazon_ads.py whitelists
its only POST to the reporting paths, so the guarantee is enforced rather than
promised.

That is not a limitation to work around later. A console that quietly adjusts
bids is one that has to be trusted; one that tells you the number and waits is
one that has to be right, and only the second is checkable.

WHAT IT NEEDS BEFORE IT CAN SAY ANYTHING

Every rule below has a MINIMUM. A keyword with four clicks and no sale is not a
bad keyword -- it is four clicks. Amazon's own guidance is that a term needs
roughly ten clicks before its conversion rate means anything, and this uses that
as a floor rather than firing on the first quiet week. A rule that cannot reach
its floor says "not enough traffic yet", which is a real and useful answer.

ACOS IS THE TARGET, NOT A CONSTANT

There is no universal "good" ACOS. It depends on the margin, and this app knows
the margin only where a cost of goods has been entered (domain/cogs_store). So:

    a target given          use it
    a cost of goods known   break-even ACOS is the margin, and the target is
                            comfortably inside it
    neither                 NO ACOS FINDINGS AT ALL, and it says so

The third case matters. Guessing 30% would produce confident advice about a
number nobody chose, on a product that might make 8% or 60%.

NOTHING HERE IS DATA THIS APP INVENTS. It reads what the Advertising API
returns. Where the API is not connected, the console says exactly that and shows
nothing, because a PPC screen with no ad data and no explanation is the same
screen as one with no ad spend.
"""

# How much traffic a rule needs before it will speak.
#
# Ten clicks is Amazon's own rough floor for a conversion rate meaning anything,
# and it is the number most PPC practice uses. Below it, silence is the honest
# output -- a keyword with four clicks and no sale has told you nothing.
MIN_CLICKS = 10
MIN_IMPRESSIONS = 500

# A campaign within this much of its daily budget is being held back by it.
BUDGET_CAP_FRACTION = 0.95

# A safety margin between break-even ACOS and the target. Advertising at exactly
# break-even makes no money; this leaves a quarter of the margin.
TARGET_MARGIN_OF_BREAKEVEN = 0.75

CRITICAL = "critical"
WARN = "warn"
INFO = "info"

_ORDER = {CRITICAL: 0, WARN: 1, INFO: 2}


def _n(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def acos(spend, sales):
    """Advertising cost of sale. None when it cannot be known.

    NOT infinity when there are no sales, and not zero. Spend with no sales has
    no ACOS -- it has wasted spend, which is a different finding with a
    different action, and collapsing the two loses the one that matters.
    """
    s, v = _n(spend), _n(sales)
    if s is None or v is None or v <= 0:
        return None
    return s / v


def breakeven_acos(margin):
    """The ACOS at which advertising exactly cancels the profit.

    If a product makes 30% margin, spending 30% of revenue on ads breaks even.
    Above that every sale loses money.
    """
    m = _n(margin)
    if m is None or m <= 0:
        return None
    return m


def target_for(product_margin=None, given=None):
    """(target_acos, why). None means NO ACOS ADVICE, and that is deliberate.

    Guessing a target would produce confident advice about a number nobody
    chose, on a product that might make 8% or 60%.
    """
    g = _n(given)
    if g is not None and g > 0:
        return g, "the target you set"
    be = breakeven_acos(product_margin)
    if be is not None:
        return be * TARGET_MARGIN_OF_BREAKEVEN, (
            "%.0f%% — three quarters of this product's %.0f%% break-even, so "
            "advertising still leaves a quarter of the margin"
            % (be * TARGET_MARGIN_OF_BREAKEVEN * 100, be * 100))
    return None, ("no ACOS target and no cost of goods for this product, so "
                  "nothing here can say whether its ACOS is good or bad")


def _f(sev, kind, subject, what, why, do, numbers=None):
    return {"severity": sev, "kind": kind, "subject": subject, "what": what,
            "why": why, "do": do, "numbers": numbers or {}}


def check_wasted_spend(rows, currency=""):
    """Money spent on terms that have never converted.

    THE CLEAREST FINDING THERE IS, and the only one that needs no target: a
    search term with enough clicks and zero sales is spending money for nothing,
    whatever the margin.
    """
    out = []
    for r in rows:
        clicks = _n(r.get("clicks")) or 0
        spend = _n(r.get("spend"))
        sales = _n(r.get("sales"))
        if spend is None or sales is None:
            continue
        if clicks < MIN_CLICKS or sales > 0 or spend <= 0:
            continue
        term = r.get("search_term") or r.get("keyword") or r.get("campaign_name") or "?"
        out.append(_f(
            CRITICAL, "wasted-spend", term,
            "%s%.2f spent over %d clicks, no sales" % (currency, spend, clicks),
            "Enough clicks to judge it, and not one of them bought. This is the "
            "money leaving with nothing coming back.",
            "Add \"%s\" as a negative exact keyword in %s."
            % (term, r.get("campaign_name") or "that campaign"),
            {"spend": spend, "clicks": clicks, "sales": 0}))
    out.sort(key=lambda f: -(f["numbers"].get("spend") or 0))
    return out


def check_acos(rows, target, currency=""):
    """Terms converting, but not profitably enough.

    Returns nothing at all when there is no target -- see target_for.
    """
    out = []
    if target is None:
        return out
    for r in rows:
        clicks = _n(r.get("clicks")) or 0
        a = acos(r.get("spend"), r.get("sales"))
        if a is None or clicks < MIN_CLICKS:
            continue
        if a <= target:
            continue
        term = r.get("search_term") or r.get("keyword") or r.get("campaign_name") or "?"
        sev = CRITICAL if a > target * 2 else WARN
        out.append(_f(
            sev, "high-acos", term,
            "ACOS %.0f%% against a target of %.0f%%" % (a * 100, target * 100),
            "It converts, so it is not waste — it is just costing more per sale "
            "than the product can carry.",
            "Lower the bid until the ACOS comes to target, or leave it if you "
            "are buying the rank deliberately. This app will not change a bid "
            "for you.",
            {"acos": a, "target": target, "spend": _n(r.get("spend")),
             "sales": _n(r.get("sales")), "clicks": clicks}))
    out.sort(key=lambda f: -(f["numbers"].get("spend") or 0))
    return out


def check_harvest(rows, target, currency=""):
    """Search terms performing well enough to deserve their own keyword.

    The one finding that MAKES money rather than saving it, which is why it is
    reported even though a console full of problems is easier to write.
    """
    out = []
    for r in rows:
        clicks = _n(r.get("clicks")) or 0
        orders = _n(r.get("orders")) or 0
        a = acos(r.get("spend"), r.get("sales"))
        if clicks < MIN_CLICKS or orders < 2 or a is None:
            continue
        if target is not None and a > target:
            continue
        term = r.get("search_term") or ""
        # A term that IS already the keyword is not a discovery.
        if not term or term.strip().lower() == str(r.get("keyword") or "").strip().lower():
            continue
        out.append(_f(
            INFO, "harvest", term,
            "%d orders at %.0f%% ACOS, from a broad or auto match"
            % (int(orders), a * 100),
            "This exact phrase is already selling. As its own exact-match "
            "keyword you control its bid instead of paying whatever the broad "
            "match decides.",
            "Add \"%s\" as an exact-match keyword and negate it in the campaign "
            "it came from, so the two do not bid against each other." % term,
            {"orders": orders, "acos": a, "clicks": clicks}))
    out.sort(key=lambda f: -(f["numbers"].get("orders") or 0))
    return out


def check_budget_capped(campaigns, currency=""):
    """Campaigns whose spend is pressed against the daily budget.

    Only worth raising when the campaign is PROFITABLE -- a losing campaign held
    back by its budget is being protected by it, and telling somebody to raise
    that is the worst advice on this page.
    """
    out = []
    for c in campaigns:
        budget = _n(c.get("budget"))
        spend = _n(c.get("spend"))
        if budget is None or spend is None or budget <= 0:
            continue
        if spend < budget * BUDGET_CAP_FRACTION:
            continue
        a = acos(spend, c.get("sales"))
        name = c.get("campaign_name") or c.get("campaign_id") or "?"
        if a is None:
            out.append(_f(
                WARN, "budget-capped-unknown", name,
                "Spending its whole %s%.2f budget, and its sales are unknown"
                % (currency, budget),
                "It is being held back by the budget, but without sales figures "
                "there is no way to say whether that is costing you or saving "
                "you.",
                "Check this campaign's sales before changing the budget.",
                {"budget": budget, "spend": spend}))
            continue
        out.append(_f(
            INFO if a < 0.5 else WARN, "budget-capped", name,
            "Spending its whole %s%.2f budget at %.0f%% ACOS"
            % (currency, budget, a * 100),
            "The budget, not the market, is deciding how much this campaign "
            "sells.",
            ("It is profitable, so the budget is the thing stopping it. Raising "
             "it is a decision for you — this app will not."
             if a < 0.5 else
             "Its ACOS is high, so the budget may be protecting you. Fix the "
             "ACOS before raising it."),
            {"budget": budget, "spend": spend, "acos": a}))
    out.sort(key=lambda f: -(f["numbers"].get("spend") or 0))
    return out


def check_no_impressions(campaigns):
    """Enabled campaigns nobody is seeing.

    A campaign that is running and getting no impressions is usually a bid below
    the floor for its terms -- it is switched on and doing nothing, which is
    easy to miss precisely because it costs nothing.
    """
    out = []
    for c in campaigns:
        state = str(c.get("state") or "").lower()
        if state not in ("enabled", "running", "delivering"):
            continue
        imps = _n(c.get("impressions"))
        if imps is None or imps > 0:
            continue
        name = c.get("campaign_name") or c.get("campaign_id") or "?"
        out.append(_f(
            WARN, "no-impressions", name,
            "Enabled, and nobody has seen it",
            "A live campaign with no impressions is usually bidding below the "
            "floor for its terms. It costs nothing, which is why it can sit "
            "like this for months.",
            "Check the bid against the suggested bid for its keywords.",
            {"impressions": 0}))
    return out


def run(campaign_rows, term_rows, target=None, product_margin=None, currency=""):
    """The whole console: every finding, worst first, and what was NOT checked.

    `target` is an ACOS target if one was given. Without it, and without a cost
    of goods, the ACOS rules produce NOTHING and say so -- see target_for.
    """
    tgt, why = target_for(product_margin, target)
    findings = []
    findings += check_wasted_spend(term_rows or [], currency)
    findings += check_acos(term_rows or [], tgt, currency)
    findings += check_harvest(term_rows or [], tgt, currency)
    findings += check_budget_capped(campaign_rows or [], currency)
    findings += check_no_impressions(campaign_rows or [])
    findings.sort(key=lambda f: (_ORDER.get(f["severity"], 3),
                                 -(f["numbers"].get("spend") or 0)))

    notes = []
    if tgt is None:
        notes.append(
            "No ACOS target and no cost of goods, so nothing on this page "
            "judges whether an ACOS is good or bad — %s. Set a target, or enter "
            "a cost of goods, and the ACOS findings appear." % why)
    thin = len([r for r in (term_rows or [])
                if (_n(r.get("clicks")) or 0) < MIN_CLICKS])
    if thin:
        notes.append(
            "%d search terms have fewer than %d clicks and were not judged. A "
            "keyword with four clicks and no sale has not told you anything "
            "yet." % (thin, MIN_CLICKS))
    if not term_rows:
        notes.append("No search-term data was read, so nothing about keywords "
                     "could be checked at all.")
    if not campaign_rows:
        notes.append("No campaign data was read, so budgets and delivery could "
                     "not be checked at all.")

    spend = sum((_n(r.get("spend")) or 0) for r in (campaign_rows or []))
    sales = sum((_n(r.get("sales")) or 0) for r in (campaign_rows or []))
    return {
        "findings": findings,
        "notes": notes,
        "target": tgt,
        "target_why": why,
        "counts": {
            "critical": len([f for f in findings if f["severity"] == CRITICAL]),
            "warn": len([f for f in findings if f["severity"] == WARN]),
            "info": len([f for f in findings if f["severity"] == INFO]),
        },
        "totals": {
            "spend": spend, "sales": sales,
            "acos": acos(spend, sales),
            "wasted": sum((f["numbers"].get("spend") or 0) for f in findings
                          if f["kind"] == "wasted-spend"),
        },
    }
