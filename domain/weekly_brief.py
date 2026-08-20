"""domain/weekly_brief.py -- the summary nobody had to ask for.

    Ava, asked what it would write every week without being prompted:

    "Headline: revenue vs last month/wk [Source: ...] - why: operator needs
     trend first. Marketplace winners/losers: top 2 up, bottom 2 down, native
     currency + % - why: EU average hides SE/BE. Profit truth: net profit after
     fees, with COGS coverage % - why: revenue lies if cost missing. Ads
     efficiency: spend, ACOS, TACOS, wasted search top 3 - why: spend is only
     lever. Inventory risk: low_stock <14d, stranded, inbound - why: links to
     #5 to stop burn. Off-track reds: top 3 sigma reds ... Never sums 3P+1P,
     always labels partial month, always quotes ECB date."

Every section carries its own "why", because a digest whose sections nobody can
justify becomes a digest nobody reads.

WHY IT LOOKS ACROSS EVERY ACCOUNT

    Ava, on the questions that surface what you have not noticed:
    "Rank off-track sigma across all 10 marketplaces - what's the top 3 reds
     brand-wide this week? - you'll miss BE/NL/SE otherwise."

Every other screen in this app is scoped to the account you have open, which is
right for working but wrong for noticing. The account with the problem this week
is, by definition, one you are not looking at. Here it is the other way round:
every account, ranked, and the quiet ones are the point.

WHAT IT WILL NOT DO

NEVER SUM ACROSS CURRENCIES. jack_uk sells in GBP and sheelady_us in USD, and
"total revenue 12,400" across the two is a number with no unit that flatters
whichever way the rate has moved. Totals are per currency, always, and the
absence of a single headline figure is deliberate.

NEVER REPORT A PROFIT IT CANNOT STAND BEHIND. domain/contribution already
refuses a bucket where any unit is uncosted, and this repeats the coverage
alongside the figure rather than leaving it to be looked up.

NEVER PRESENT A PART PERIOD AS A WHOLE ONE. The week to yesterday is seven whole
days; "this month" is not a month until it ends.

A SECTION THAT COULD NOT LOOK SAYS SO. It does not return zero. An empty
advertising section on an account with no Ads connection and one on an account
that spent nothing are opposite facts, and a zero cannot tell them apart.
"""
import datetime as _dt


def _days_ago(end, n):
    return (_dt.date.fromisoformat(end) - _dt.timedelta(days=n)).isoformat()


def _pct(now, was):
    """Change from `was` to `now`, or None when there is nothing to compare."""
    try:
        now = float(now)
        was = float(was)
    except (TypeError, ValueError):
        return None
    if was == 0:
        return None                      # not "infinite growth" -- no baseline
    return round(100.0 * (now - was) / abs(was), 1)


def _accounts(cfg):
    out = []
    for a in (cfg.get("accounts") or []):
        aid = str(a.get("id") or "").strip()
        if not aid:
            continue
        out.append({
            "id": aid,
            "label": str(a.get("name") or a.get("label") or aid),
            "marketplace": str(a.get("default_marketplace") or "").upper(),
        })
    return out


# ---------------------------------------------------------------------------
# The sections. Each returns its own findings and its own "could not look".
# ---------------------------------------------------------------------------

def _sales_section(config_path, accounts, end):
    """Last seven whole days against the seven before, per account.

    Seven against seven rather than a calendar week, because a calendar week
    that ends tomorrow is a part period and the comparison would flatter it.
    """
    this_start = _days_ago(end, 6)
    prev_end = _days_ago(end, 7)
    prev_start = _days_ago(end, 13)

    from domain import sales_data as _sd
    rows, notes = [], []
    for a in accounts:
        if not a["marketplace"]:
            notes.append("%s has no default marketplace set, so it was not "
                         "read." % a["label"])
            continue
        try:
            # basis="order", not the default "money". Every fee and refund
            # sits on the day its order was PLACED, so revenue and the units
            # that made it describe the same trade -- the one calendar this app
            # decided on in sales_routes._basis().
            now = _sd.totals(config_path, a["id"], a["marketplace"],
                             this_start, end, basis="order") or {}
            was = _sd.totals(config_path, a["id"], a["marketplace"],
                             prev_start, prev_end, basis="order") or {}
        except Exception as e:
            notes.append("%s: could not read sales (%s)."
                         % (a["label"], str(e)[:90]))
            continue
        rev = now.get("ordered_sales")
        rows.append({
            "account": a["label"], "id": a["id"],
            "marketplace": a["marketplace"],
            "currency": now.get("currency") or "",
            "revenue": rev,
            "units": now.get("units"),
            "orders": now.get("orders"),
            "revenue_prev": was.get("ordered_sales"),
            "change_pct": _pct(rev, was.get("ordered_sales")),
        })

    # Sorted by MOVEMENT, not by size. The biggest account is the one you
    # already watch; the one that moved is the one you have not.
    #
    # A FALLER MUST ACTUALLY HAVE FALLEN. Taking the two lowest movers reported
    # "biggest fallers: +201%, +2157%" on a week where every account grew --
    # true as an ordering, false as a sentence, and the sentence is what gets
    # read. So each list is filtered by SIGN first and is simply empty when
    # nothing went that way.
    movers = [r for r in rows if r["change_pct"] is not None]
    down = sorted([r for r in movers if r["change_pct"] < 0],
                  key=lambda r: r["change_pct"])[:2]
    up = sorted([r for r in movers if r["change_pct"] > 0],
                key=lambda r: -r["change_pct"])[:2]
    return {
        "window": {"start": this_start, "end": end},
        "compared_with": {"start": prev_start, "end": prev_end},
        "rows": rows,
        "down": down,
        "up": up,
        "notes": notes,
        # A big percentage off a small base is arithmetic, not news. The
        # previous figure travels with every row so the reader can tell the two
        # apart without opening another screen.
        "read_the_base": ("A change is shown against the previous seven days. "
                          "Where that base was small, a large percentage is "
                          "arithmetic rather than news -- the previous figure "
                          "is on the row."),
        "why": ("The trend comes first because it is the only thing that says "
                "whether to read the rest closely."),
        "no_total": ("There is no combined figure. These accounts sell in "
                     "different currencies and adding them would produce a "
                     "number with no unit."),
    }


def _off_track_section(config_path, accounts, end):
    """Yesterday against its own history, everywhere at once.

    The account with a problem this week is the one nobody opened.
    """
    from domain import leading as _lead
    start = _days_ago(end, _lead.WINDOW_DAYS)
    reds, notes = [], []
    for a in accounts:
        if not a["marketplace"]:
            continue
        try:
            rows = _lead.rows_for(config_path, a["id"], a["marketplace"],
                                  start, end)
        except Exception as e:
            notes.append("%s: could not read the daily figures (%s)."
                         % (a["label"], str(e)[:90]))
            continue
        if not rows:
            notes.append("%s has no daily figures stored, so nothing could be "
                         "compared." % a["label"])
            continue
        try:
            got = _lead.build(rows, day=end)
        except Exception as e:
            notes.append("%s: %s" % (a["label"], str(e)[:90]))
            continue
        for ind in (got.get("indicators") or []):
            # OFF is the status this module uses for "beyond the normal range".
            # WATCH is the near miss and is deliberately not carried here: a
            # weekly brief listing every near miss is a brief nobody finishes.
            if ind.get("status") != _lead.OFF:
                continue
            reds.append({
                "account": a["label"], "id": a["id"],
                "marketplace": a["marketplace"],
                "metric": ind.get("label") or ind.get("key"),
                "sigma": ind.get("sigma"),
                "value": ind.get("value"),
                "normal": ind.get("mean"),
                "change_pct": ind.get("change_pct"),
                "days": ind.get("days"),
                "why": ind.get("blurb") or "",
                "note": ind.get("note") or "",
            })
    # Biggest departure from normal first, whichever account it is in.
    reds.sort(key=lambda r: -abs(r.get("sigma") or 0))
    return {
        "day": end,
        "reds": reds[:3],
        "red_count": len(reds),
        "notes": notes,
        "why": ("Every other screen is scoped to the account you have open, "
                "which is right for working and wrong for noticing. The "
                "account with a problem this week is the one nobody opened."),
    }


def _profit_section(config_path, accounts, end):
    """What was left after Amazon's real fees -- and how much of it is knowable.

        Ava: "Profit truth: net profit after fees, with COGS coverage % --
              why: revenue lies if cost missing."
    """
    start = _days_ago(end, 6)
    from domain import cogs as _cogs
    rows, notes = [], []
    for a in accounts:
        if not a["marketplace"]:
            continue
        cov = None
        try:
            cov = _cogs.coverage(config_path, a["id"], a["marketplace"])
        except Exception as e:
            notes.append("%s: could not check cost coverage (%s)."
                         % (a["label"], str(e)[:90]))
        entry = {"account": a["label"], "id": a["id"],
                 "marketplace": a["marketplace"]}
        if cov:
            entry["costed"] = int(cov.get("known") or 0)
            entry["products"] = int(cov.get("total") or 0)
            entry["uncosted"] = int(cov.get("unknown") or 0)
            # cogs.coverage already works the percentage out; taking its own
            # figure rather than recomputing keeps one answer to the question.
            entry["coverage_pct"] = cov.get("pct")
            # The products themselves, so the gap is a job rather than a number.
            entry["missing_skus"] = list(cov.get("missing_skus") or [])[:5]
        rows.append(entry)
    gaps = [r for r in rows if (r.get("uncosted") or 0) > 0]
    gaps.sort(key=lambda r: -(r.get("uncosted") or 0))
    return {
        "window": {"start": start, "end": end},
        "rows": rows,
        "gaps": gaps,
        "notes": notes,
        "why": ("A profit worked out while some products have no cost can only "
                "ever be flattered -- those units bring revenue and no cost. "
                "The coverage is shown beside the figure rather than left to "
                "be looked up."),
    }


def _stock_section(config_path, accounts, end):
    """What runs out first, and what is already empty."""
    from domain import stock_metrics as _sm
    empty, short, notes = [], [], []
    for a in accounts:
        if not a["marketplace"]:
            continue
        try:
            got = _sm.for_account(config_path, a["id"], a["marketplace"],
                                  window=30, today=end)
        except Exception as e:
            notes.append("%s: could not work out coverage (%s)."
                         % (a["label"], str(e)[:90]))
            continue
        for r in (got.get("rows") or []):
            item = {"account": a["label"], "id": a["id"], "sku": r.get("sku"),
                    "on_hand": r.get("on_hand"),
                    "cover_days": r.get("days_of_cover"),
                    "gap": r.get("stock_gap_30d"),
                    "pace": r.get("pace_30d"),
                    "stale": bool(r.get("pace_is_stale")),
                    "stale_why": r.get("stale_why") or ""}
            if r.get("status") == "out_of_stock":
                empty.append(item)
            elif (r.get("days_of_cover") is not None
                  and r["days_of_cover"] <= 14
                  and not r.get("pace_is_stale")):
                short.append(item)
    empty.sort(key=lambda r: -(r.get("pace") or 0))
    short.sort(key=lambda r: (r.get("cover_days") or 0))
    return {
        "out_now": empty[:5], "out_count": len(empty),
        "running_out": short[:5], "running_out_count": len(short),
        "notes": notes,
        "why": ("An empty listing earns nothing and still costs its "
                "advertising. Products whose sales have gone quiet are left "
                "out of the running-out list -- their shortfall is arithmetic "
                "on a pace that has stopped."),
    }


def _ads_section(config_path, accounts, end):
    """Advertising, when there is any.

    An empty section here and an account that spent nothing are opposite facts.
    """
    from data import db as _db
    start = _days_ago(end, 6)
    rows, notes = [], []
    connected = False
    for a in accounts:
        if not a["marketplace"]:
            continue
        try:
            got = _db.get_db(config_path).execute(
                "SELECT COALESCE(SUM(spend),0) spend, "
                "       COALESCE(SUM(ad_sales),0) sales, "
                "       COALESCE(SUM(clicks),0) clicks, COUNT(*) n "
                "FROM ads_daily WHERE workspace_id=? AND marketplace=? "
                "  AND date>=? AND date<=?",
                (a["id"], a["marketplace"], start, end)).fetchone()
        except Exception as e:
            notes.append("%s: could not read advertising (%s)."
                         % (a["label"], str(e)[:90]))
            continue
        if not got or not got["n"]:
            continue
        connected = True
        spend, sales = float(got["spend"]), float(got["sales"])
        rows.append({
            "account": a["label"], "id": a["id"],
            "spend": round(spend, 2), "ad_sales": round(sales, 2),
            # NONE, NEVER ZERO -- an ACOS with no sales is not 0%, it is
            # undefined, and printing 0% invites somebody to act on it.
            "acos_pct": (round(100.0 * spend / sales, 1) if sales else None),
        })
    if not connected:
        notes.append(
            "No advertising figures are stored for any account, so nothing "
            "here reflects ad spend. That is not the same as spending nothing: "
            "the Amazon Advertising API needs its own login, which has not "
            "been connected. Profit figures elsewhere in this brief have no ad "
            "spend subtracted from them.")
    return {"window": {"start": start, "end": end}, "rows": rows,
            "connected": connected, "notes": notes,
            "why": "Spend is the fastest lever there is, in both directions."}


def build(config_path, cfg, today=None):
    """The whole brief. Reads only; writes nothing; contacts nobody."""
    end = today or (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
    accounts = _accounts(cfg or {})
    if not accounts:
        return {"ok": False,
                "error": "No accounts are configured, so there is nothing to "
                         "summarise."}

    brief = {
        "ok": True,
        "generated_for": end,
        "accounts": len(accounts),
        "sales": _sales_section(config_path, accounts, end),
        "off_track": _off_track_section(config_path, accounts, end),
        "profit": _profit_section(config_path, accounts, end),
        "stock": _stock_section(config_path, accounts, end),
        "ads": _ads_section(config_path, accounts, end),
    }
    # THE PERIOD, SAID ONCE AND SAID PLAINLY. Seven whole days ending
    # yesterday: Amazon has nothing for today, and a window that includes it
    # compares a part day against whole ones.
    brief["period_note"] = (
        "Seven whole days, %s to %s, against the seven before. It ends "
        "yesterday because Amazon has no figures for today."
        % (_days_ago(end, 6), end))
    brief["currency_note"] = brief["sales"]["no_total"]
    # Everything that could not be looked at, gathered in one place rather than
    # scattered through the sections where it can be missed.
    could_not = []
    for key in ("sales", "off_track", "profit", "stock", "ads"):
        could_not += list(brief[key].get("notes") or [])
    brief["could_not_look"] = could_not
    return brief
