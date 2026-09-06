"""domain/drppc_performance.py -- the Dr PPC Console's Performance page.

Built to DR-PPC-PERFORMANCE-BUILD-PROMPT.md. One question runs through all of
it: is today's number NORMAL for this account, or is something happening?

SCORING AGAINST A BASELINE IS A CLAIM, SO THE BASELINE IS STATED.

The spec asks for "scored against the 60-day baseline". Measured on the real
data: this account has TWENTY-EIGHT days of advertising history, 8 Aug to 4 Sep.
A 60-day baseline does not exist and cannot be conjured, so this module reports
the baseline it actually has, with its length on the page, and REFUSES TO SCORE
at all below a stated minimum. A verdict of "off baseline" computed from four
days is not a verdict.

The rule, written down here and printed on the screen rather than buried:

    expected = the mean of the baseline days
    z        = how many standard deviations the day sits from that mean
    |z| <= 1 in line with baseline
    |z| <= 2 drifting from baseline
    |z| >  2 off baseline

Symmetric on purpose. "In line" is a statement about distance from normal, not
about whether the news is good -- ACOS 2 points above expected and 2 points below
are equally normal, and colouring one of them red would be an opinion dressed as
a measurement.

THE DAY BEING SCORED IS NEVER IN ITS OWN BASELINE. It would drag its own
expectation towards itself and make every day look normal.

AND THE ADVERTISING FEED LAGS TWO DAYS. The spec's "Today so far" bar cannot be
filled from advertising, because Amazon has not sent today's advertising figures
and will not for another two days. What IS knowable about today -- the account's
own sales -- is reported, and the rest is named as absent rather than drawn as
nought.

Nothing here writes anything, to Amazon or otherwise (Rule 8).
"""
import datetime as _dt

from domain import ppc_analytics as _pa

# Below this many baseline days, nothing is scored. A mean over a handful of
# days has a standard deviation that says more about the handful than about the
# account, and every day would come out "off baseline".
MIN_BASELINE_DAYS = 14

# What the page scores, in the spec's order. `good` is for the delta arrow only
# -- it never decides the status, which is distance from normal.
METRICS = (
    ("total_sales", "Total sales", "money", "up"),
    ("spend", "Spend", "money", None),
    ("tacos_pct", "TACOS", "points", "down"),
    ("ad_sales", "Ad sales", "money", "up"),
    ("acos_pct", "ACOS", "points", "down"),
    ("cvr_pct", "PPC CVR", "points", "up"),
)


def _f(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _mean(xs):
    return (sum(xs) / len(xs)) if xs else None


def _sd(xs, mean):
    if not xs or len(xs) < 2 or mean is None:
        return None
    return (sum((x - mean) ** 2 for x in xs) / len(xs)) ** 0.5


def _day_minus(d, n):
    return (_dt.date.fromisoformat(d) - _dt.timedelta(days=int(n))).isoformat()


def _with_cvr(rows):
    """Adds PPC CVR to each day. Orders per CLICK, which is what CVR means here.

    A day with no clicks has no conversion rate -- None, not 0%. Zero would say
    "nobody who clicked bought", and nobody clicked.
    """
    for r in rows:
        c, o = _f(r.get("clicks")), _f(r.get("orders"))
        r["cvr_pct"] = (round(100.0 * o / c, 2) if c else None)
    return rows


# ---------------------------------------------------------------------------
# The baseline, and the day scored against it
# ---------------------------------------------------------------------------


def baseline(config_path, workspace_id, marketplace, end_before, days=60):
    """The account's normal, measured over the days BEFORE the one being scored.

    Returns per metric: mean, standard deviation and how many days went into it,
    plus how many were dropped because the metric could not be worked out for
    them. Both counts matter -- an ACOS baseline built from nine of twenty-eight
    days is a different thing from one built from all of them, and only one of
    those is worth a verdict.
    """
    start = _day_minus(end_before, int(days) - 1)
    rows = _with_cvr(_pa.daily(config_path, workspace_id, marketplace, start,
                               end_before))
    out = {"start": start, "end": end_before, "asked_days": int(days),
           "metrics": {}}
    # How many days Amazon actually sent, as opposed to how many were asked for.
    have = [r for r in rows if r.get("spend") is not None]
    out["days_with_data"] = len(have)
    out["enough"] = len(have) >= MIN_BASELINE_DAYS
    out["why"] = "" if out["enough"] else (
        "Only %d complete advertising days are stored for this account, and "
        "nothing is scored below %d. A mean over a handful of days describes the "
        "handful, not the account, and every day would come out 'off baseline'."
        % (len(have), MIN_BASELINE_DAYS))
    live = {r["date"] for r in have}
    for key, _label, _kind, _good in METRICS:
        xs = [_f(r.get(key)) for r in rows]
        xs = [x for x in xs if x is not None]
        m = _mean(xs)
        # TWO KINDS OF MISSING DAY, AND THEY MEAN OPPOSITE THINGS.
        #
        # A day BEFORE this account started advertising is not a gap in the
        # evidence; it is simply outside the account's history, and reporting it
        # as "could not be worked out" sends somebody looking for data that was
        # never going to exist. A day that HAS advertising rows but still cannot
        # produce this metric -- an ACOS on a day with spend and no sales -- is a
        # real gap and worth naming.
        unmeasurable = sum(1 for r in rows
                           if r["date"] in live and _f(r.get(key)) is None)
        out["metrics"][key] = {
            "mean": (round(m, 4) if m is not None else None),
            "sd": (lambda s: round(s, 4) if s is not None else None)(_sd(xs, m)),
            "n": len(xs),
            "unmeasurable": unmeasurable,
            "outside_history": len(rows) - len(xs) - unmeasurable,
        }
    return out


def _status(actual, mean, sd, n):
    """In line, drifting, or off -- and never a verdict it cannot support."""
    if actual is None:
        return "unknown", ("Not measured for this day, so there is nothing to "
                           "score.")
    if mean is None or n < MIN_BASELINE_DAYS:
        return "unscored", ("Too little history to say what normal looks like "
                            "for this account.")
    if sd is None or sd == 0:
        # Every baseline day identical. Real, and it happens with a fixed daily
        # budget; but it makes any difference at all infinitely many standard
        # deviations, so it is reported rather than scored.
        same = (abs(actual - mean) < 1e-9)
        return ("in_line" if same else "unscored"), (
            "" if same else "Every baseline day held the same value, so there "
            "is no spread to measure this against.")
    z = (actual - mean) / sd
    a = abs(z)
    return (("in_line" if a <= 1 else "drifting" if a <= 2 else "off"),
            "%.1f standard deviations from the %d-day mean" % (z, n))


def scorecard(config_path, workspace_id, marketplace, baseline_days=60):
    """The six cards: the latest COMPLETE advertising day, scored. -> dict."""
    day = _pa.latest_ad_day(config_path, workspace_id, marketplace)
    if not day:
        return {"day": "", "cards": [], "baseline": None, "has_data": False,
                "why": ("No advertising day is stored for this account, so "
                        "there is nothing to score. Advertising figures arrive "
                        "from the Advertising API sync.")}
    rows = _with_cvr(_pa.daily(config_path, workspace_id, marketplace, day, day))
    today = rows[0] if rows else {}
    base = baseline(config_path, workspace_id, marketplace,
                    _day_minus(day, 1), baseline_days)

    cards = []
    for key, label, kind, good in METRICS:
        b = base["metrics"].get(key) or {}
        actual = _f(today.get(key))
        state, why = _status(actual, b.get("mean"), b.get("sd"), b.get("n"))
        delta = (None if (actual is None or b.get("mean") is None)
                 else round(actual - b["mean"], 2))
        cards.append({
            "key": key, "label": label, "kind": kind, "good": good,
            "value": actual,
            "expected": (round(b["mean"], 2) if b.get("mean") is not None
                         else None),
            "delta": delta, "status": state, "why": why,
            "baseline_n": b.get("n"),
            "baseline_unmeasurable": b.get("unmeasurable"),
            "baseline_outside": b.get("outside_history"),
        })

    # How far behind Amazon's advertising feed is, said once and reused.
    lag = (_dt.date.today() - _dt.date.fromisoformat(day)).days
    return {"day": day, "cards": cards, "baseline": base, "has_data": True,
            "lag_days": lag,
            "why": ("The latest COMPLETE advertising day is %s — %d day%s "
                    "behind today. Amazon does not report advertising for the "
                    "current day, so this is the most recent verdict available, "
                    "not a stale one."
                    % (day, lag, "" if lag == 1 else "s"))}


def today_pulse(config_path, workspace_id, marketplace):
    """What is knowable about TODAY, which is less than the spec assumes.

    The spec's bar reads "Today so far -- spend $89, ad sales $258, 173 clicks".
    None of that can be filled: Amazon's advertising feed lags, so there is no
    advertising row for today and there will not be one for two days. Inventing
    a partial from an empty table would put a nought beside the word "spend".

    The account's own SALES are known for today, so those are reported, and the
    advertising half is named as absent with the reason.
    """
    today = _dt.date.today().isoformat()
    rows = _with_cvr(_pa.daily(config_path, workspace_id, marketplace, today,
                               today))
    r = rows[0] if rows else {}
    has_ads = r.get("spend") is not None
    return {
        "date": today,
        "total_sales": _f(r.get("total_sales")),
        "spend": _f(r.get("spend")),
        "ad_sales": _f(r.get("ad_sales")),
        "clicks": _f(r.get("clicks")),
        "orders": _f(r.get("orders")),
        "has_ads": has_ads,
        "why": ("" if has_ads else
                "Amazon has sent no advertising figures for today and will not "
                "for about two days — advertising is reported behind. Today's "
                "sales are this account's own and are known now. The advertising "
                "half is left blank rather than shown as nought."),
    }


# ---------------------------------------------------------------------------
# Seven days against the seven before them
# ---------------------------------------------------------------------------


def trend(config_path, workspace_id, marketplace, span=7):
    """Recent N complete days against the N before. -> dict.

    Ratios are RECOMPUTED over each window rather than averaged across days.
    Averaging daily ACOS gives every day the same weight, so one quiet Sunday
    with a bad ratio moves the week as much as a busy Monday, and the answer
    stops matching what was actually spent and earned.
    """
    end = _pa.latest_ad_day(config_path, workspace_id, marketplace)
    if not end:
        return {"has_data": False, "why": "No advertising days are stored."}
    r_start = _day_minus(end, span - 1)
    p_end = _day_minus(r_start, 1)
    p_start = _day_minus(p_end, span - 1)

    def side(s, e):
        rows = _pa.daily(config_path, workspace_id, marketplace, s, e)
        got = [r for r in rows if r.get("spend") is not None]
        add = lambda k: sum(_f(r.get(k)) or 0.0 for r in got)      # noqa: E731
        spend, ad_sales = add("spend"), add("ad_sales")
        clicks, orders = add("clicks"), add("orders")
        total = sum(_f(r.get("total_sales")) or 0.0 for r in rows)
        return {
            "start": s, "end": e, "days": len(got),
            "spend": round(spend, 2), "ad_sales": round(ad_sales, 2),
            "total_sales": round(total, 2), "orders": int(orders),
            "clicks": int(clicks),
            "acos_pct": (round(100.0 * spend / ad_sales, 1) if ad_sales else None),
            "tacos_pct": (round(100.0 * spend / total, 1) if total else None),
            "cvr_pct": (round(100.0 * orders / clicks, 1) if clicks else None),
        }

    now, before = side(r_start, end), side(p_start, p_end)
    change = {}
    for k in ("spend", "ad_sales", "total_sales", "orders", "clicks"):
        a, b = now[k], before[k]
        # A percentage change from nothing is not infinity and not 0% -- there
        # was no base to change from, and it says so.
        change[k] = (round(100.0 * (a - b) / b, 1) if b else None)
    for k in ("acos_pct", "tacos_pct", "cvr_pct"):
        a, b = now[k], before[k]
        # POINTS, not per cent. "ACOS up 6%" and "ACOS up 6 points" are different
        # statements and only one of them is what moved.
        change[k] = (round(a - b, 1) if (a is not None and b is not None)
                     else None)
    return {"has_data": bool(now["days"]), "recent": now, "prior": before,
            "change": change, "span": span,
            "why": ("Ratios are recomputed over each week rather than averaged "
                    "across its days, so a quiet day cannot weigh as much as a "
                    "busy one. Ratio rows change in POINTS; money and counts "
                    "change in per cent.")}


# ---------------------------------------------------------------------------
# Which campaigns moved, and which are simply big
# ---------------------------------------------------------------------------


def drivers(config_path, workspace_id, marketplace, span=7, limit=12):
    """Campaigns ranked by how much their spend MOVED between the two weeks.

    Movement share is of the total ABSOLUTE movement, not of the net: a week
    where one campaign gained 100 and another lost 100 has a net of nought and
    two campaigns that each did something worth knowing about.
    """
    end = _pa.latest_ad_day(config_path, workspace_id, marketplace)
    if not end:
        return {"has_data": False, "rows": [], "why": "No advertising days."}
    r_start = _day_minus(end, span - 1)
    p_end = _day_minus(r_start, 1)
    p_start = _day_minus(p_end, span - 1)

    # KEYED ON THE CAMPAIGN ID, NOT ITS NAME. A campaign can be renamed between
    # two weeks, and matching on the name would report the old one as stopped
    # and the new one as started -- two large fictitious movements from one
    # rename. The name is carried for display only.
    def by_campaign(s, e):
        out = {}
        for c in _pa.campaigns(config_path, workspace_id, marketplace, s, e):
            out[str(c.get("campaign_id") or "")] = c
        return out

    now, before = by_campaign(r_start, end), by_campaign(p_start, p_end)
    rows = []
    for cid in set(now) | set(before):
        a, b = now.get(cid) or {}, before.get(cid) or {}
        ds = (_f(a.get("spend")) or 0.0) - (_f(b.get("spend")) or 0.0)
        rows.append({
            "campaign_id": cid,
            "campaign": a.get("name") or b.get("name") or "",
            "ad_product": a.get("ad_product") or b.get("ad_product") or "",
            "spend_delta": round(ds, 2),
            "sales_delta": round((_f(a.get("sales")) or 0.0)
                                 - (_f(b.get("sales")) or 0.0), 2),
            "orders_delta": int((_f(a.get("orders")) or 0.0)
                                - (_f(b.get("orders")) or 0.0)),
            "recent_spend": round(_f(a.get("spend")) or 0.0, 2),
            # NEW and GONE are worth knowing and are not the same as a change.
            "state": ("new" if cid not in before else
                      "stopped" if cid not in now else "continuing"),
        })
    total_move = sum(abs(r["spend_delta"]) for r in rows) or 0.0
    for r in rows:
        r["movement_share_pct"] = (round(100.0 * abs(r["spend_delta"])
                                         / total_move, 1)
                                   if total_move else None)
    rows.sort(key=lambda r: -abs(r["spend_delta"]))
    return {"has_data": bool(rows), "rows": rows[:limit],
            "recent": {"start": r_start, "end": end},
            "prior": {"start": p_start, "end": p_end},
            "total_movement": round(total_move, 2),
            "why": ("Share is of the total ABSOLUTE movement between the two "
                    "weeks, so a campaign that went up and one that went down "
                    "by the same amount are both visible — a net figure would "
                    "cancel them and report a quiet week.")}


def largest(config_path, workspace_id, marketplace, span=7, limit=12):
    """The biggest spenders of the recent window, with their share of it."""
    end = _pa.latest_ad_day(config_path, workspace_id, marketplace)
    if not end:
        return {"has_data": False, "rows": [], "why": "No advertising days."}
    start = _day_minus(end, span - 1)
    cs = _pa.campaigns(config_path, workspace_id, marketplace, start, end)
    total = sum(_f(c.get("spend")) or 0.0 for c in cs)
    rows = []
    for c in cs:
        sp = _f(c.get("spend")) or 0.0
        rows.append({
            "campaign_id": str(c.get("campaign_id") or ""),
            "campaign": c.get("name") or "",
            "ad_product": c.get("ad_product") or "",
            "spend": round(sp, 2),
            "share_pct": (round(100.0 * sp / total, 1) if total else None),
            "sales": _f(c.get("sales")),
            "acos_pct": _f(c.get("acos_pct")),
            "orders": c.get("orders"),
        })
    rows.sort(key=lambda r: -r["spend"])
    return {"has_data": bool(rows), "rows": rows[:limit], "total_spend":
            round(total, 2), "start": start, "end": end}


# ---------------------------------------------------------------------------
# The lanes, the plan, and what is simply not knowable yet
# ---------------------------------------------------------------------------


def lanes(config_path, workspace_id, marketplace):
    """The branded / non-branded / unclassified split, from the reviewed rules.

    ASKS drppc_console.classify rather than repeating it (Rule 12), and carries
    that module's caveat forward: the split comes from the STORED Search Term
    Report, whose window was fixed when it was pulled. It is not a 14-day cut,
    and saying it were would put a date on the screen that nothing supports.
    """
    from domain import drppc_console as _dc

    c = _dc.classify(config_path, workspace_id, marketplace)
    return {
        "by_lane": c["by_lane"], "total_spend": c["total_spend"],
        "classified_pct": c["classified_pct"], "rules_active": c["rules_active"],
        "above_bar": c["above_bar"], "confidence_bar": c["confidence_bar"],
        "why": ("From the stored Search Term Report, which covers one fixed "
                "window chosen when it was pulled — not the last 14 days. With "
                "no reviewed rules every term is unclassified, which is a real "
                "answer rather than an empty panel."),
    }


def plan_sections(config_path, workspace_id, marketplace, trend_now=None):
    """Budget pacing, goal progress and rank evidence -- all plan-dependent.

    Each returns a reason rather than an empty box. Budget pacing without a
    planned figure is not a small version of budget pacing; it is arithmetic
    with a number nobody supplied.
    """
    from domain import drppc_console as _dc

    plan = _dc.plan_current(config_path, workspace_id, marketplace)
    active = bool(plan and plan.get("status") == "active")
    body = (plan or {}).get("body") or {}
    out = {"has_plan": active,
           "plan_revision": (plan or {}).get("revision"),
           "plan_status": (plan or {}).get("status") or "",
           "budget": None, "goals": [], "rank": None}

    # RANK IS UNKNOWABLE WHETHER OR NOT THERE IS A PLAN, so its reason is set
    # before the early return rather than after it. Leaving the key out on one
    # path made the caller fall back to a vaguer sentence on exactly the screen
    # where the explanation matters most.
    out["rank_why"] = ("Organic and category rank are not stored by this app. "
                       "A rank goal can be written down; it cannot be measured "
                       "here until rank is being recorded.")
    if not active:
        why = ("No plan is active. Budget pacing and goal progress measure "
               "against an intention somebody recorded, and there is nothing "
               "recorded to measure against."
               + (" Revision %s is saved as a draft — activating it fills these "
                  "panels." % plan["revision"] if plan else ""))
        out["why"] = why
        out["budget_why"] = why
        return out
    out["why"] = ""

    bud = body.get("budget") or {}
    planned = _f(bud.get("total"))
    ident = body.get("identity") or {}
    ps, pe = ident.get("period_start") or "", ident.get("period_end") or ""
    if planned and ps and pe:
        spent = 0.0
        for r in _pa.daily(config_path, workspace_id, marketplace, ps,
                           min(pe, _dt.date.today().isoformat())):
            spent += _f(r.get("spend")) or 0.0
        d0 = _dt.date.fromisoformat(ps)
        d1 = _dt.date.fromisoformat(pe)
        today = _dt.date.today()
        span = (d1 - d0).days + 1
        gone = max(0, min(span, (today - d0).days + 1))
        out["budget"] = {
            "planned": round(planned, 2), "spent": round(spent, 2),
            "period_start": ps, "period_end": pe,
            "days_elapsed": gone, "days_total": span,
            "spent_pct": (round(100.0 * spent / planned, 1) if planned else None),
            "elapsed_pct": (round(100.0 * gone / span, 1) if span else None),
            # Pacing is spend-so-far against time-so-far. Above 100 means the
            # money is going faster than the calendar.
            "pace_pct": (round((spent / planned) / (gone / span) * 100.0, 1)
                         if (planned and span and gone) else None),
        }
    else:
        out["budget"] = None
        out["budget_why"] = ("The active plan carries no total planned spend and "
                             "period, so there is nothing to pace against.")

    # GOALS ARE REPORTED, NOT SCORED -- yet. Each goal names a metric, a window
    # and an aggregation; only some of those combinations can be answered from
    # what is stored, and pretending otherwise would put a tick beside a goal
    # nobody measured.
    tr = trend_now or trend(config_path, workspace_id, marketplace, 7)
    live = (tr.get("recent") or {}) if tr.get("has_data") else {}
    for g in (body.get("goals") or []):
        metric = str(g.get("metric") or "").strip().lower()
        actual = live.get(metric)
        out["goals"].append({
            "title": g.get("title") or "", "metric": metric,
            "operator": g.get("operator") or "", "target": g.get("target"),
            "upper_target": g.get("upper_target"),
            "unit": g.get("unit") or "", "window": g.get("window") or "",
            "priority": g.get("priority") or "",
            "actual": actual,
            "measurable": actual is not None,
            "why": ("" if actual is not None else
                    ("Nothing stored answers '%s' over the last complete week, "
                     "so this goal cannot be scored yet." % (metric or "that")))
        })

    out["rank"] = None
    return out


def gaps(config_path, workspace_id, marketplace, score=None, base=None,
         lane=None, plans=None):
    """What this page could not determine, listed once and derived.

    Derived from the sections themselves rather than written out beside them: a
    hand-kept list goes stale the moment a gap closes, and then tells somebody
    to go and fetch something they already have.
    """
    out = []
    s = score or scorecard(config_path, workspace_id, marketplace)
    b = base or (s.get("baseline") or {})
    if not s.get("has_data"):
        out.append(s.get("why") or "No advertising data is stored.")
        return out
    if not b.get("enough"):
        out.append(b.get("why") or "Not enough history to score against.")
    elif (b.get("days_with_data") or 0) < (b.get("asked_days") or 0):
        out.append("The baseline asked for %d days and found %d — this account "
                   "has been advertising for less than that, so 'normal' is "
                   "measured over a shorter run than the page name implies."
                   % (b["asked_days"], b["days_with_data"]))
    for c in s.get("cards") or []:
        if c["status"] == "unscored" and c.get("why"):
            out.append("%s could not be scored: %s" % (c["label"], c["why"]))
        elif c["status"] == "unknown":
            out.append("%s was not measured on %s." % (c["label"], s["day"]))
        elif c.get("baseline_unmeasurable"):
            # ONLY the days that had advertising and still could not produce the
            # figure. Days before this account started advertising are not a gap
            # in the evidence and listing them sends somebody hunting for data
            # that never existed.
            out.append("%s could not be worked out on %d of the %d advertising "
                       "days in the baseline, so its normal is measured over the "
                       "other %d."
                       % (c["label"], c["baseline_unmeasurable"],
                          c["baseline_unmeasurable"] + (c["baseline_n"] or 0),
                          c["baseline_n"] or 0))
    ln = lane or lanes(config_path, workspace_id, marketplace)
    if not ln.get("rules_active"):
        out.append("No reviewed lane rules exist, so branded and non-branded "
                   "spend cannot be told apart and the lane panel reports "
                   "everything as unclassified.")
    p = plans or plan_sections(config_path, workspace_id, marketplace)
    if not p.get("has_plan"):
        out.append(p.get("why") or "No active plan.")
    if p.get("rank_why"):
        out.append(p["rank_why"])
    return out
