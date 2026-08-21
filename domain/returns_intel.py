"""domain/returns_intel.py -- what the returns MEAN, on top of what they are.

domain/returns_view.py counts returns: reasons, causes, dispositions, per ASIN,
per day. Everything in here is a second layer over that, and it exists because
counting is not the same as knowing what to do:

    by_parent      one row per PARENT, not per child. A shoe in 132 sizes is one
                   product with a sizing problem, not 132 products with one
                   return each -- and the child list is where the signal hides.
                   Measured on a real footwear account: 6,412 returns across 132
                   children of a single parent, none of which reads as a problem
                   on its own.

    monthly        the same rows across months, so "getting worse" is a shape
                   rather than a claim, and sellable against unsellable per
                   month, because a rising return rate that stays sellable is a
                   listing problem and a rising one that does not is a product
                   problem.

    themes         the customer comments, grouped by what they actually say.
                   Four thousand comments are unreadable; seven themes with
                   real quotes under them are a morning's work.

    insights       the findings, each with the action it implies. Generated
                   from the numbers and never written by hand -- an insight
                   nobody can trace back to a figure is an opinion.

NOTHING HERE INVENTS A NUMBER. Every figure is a count or a ratio of counts that
came out of the report. Where a denominator is missing -- units ordered, which
this report does not carry -- the rate is None and the screen says so, rather
than being filled with something plausible.

THE PARENT COMES FROM THE APP, AND FROM ONE PLACE ONLY (rule 12). Amazon's
returns report has no parent column. The grouping key here is
returns_view.line_of(name, family) -- the SAME call, with the SAME
family_by_asin map, that returns_view.summarise already uses to build its
Product Line section. It is not a second opinion about what a family is: a
parent row here and a line row there are the same grouping by construction, and
cannot drift apart. Where the app knows a real variation family for the ASIN,
that is the key; where it does not, the product name cut at its variant marker
is, and the reply says which of the two it was.
"""
import re

from domain import returns_view as _rv

# How many customer quotes to keep per theme. Enough to recognise the pattern,
# few enough to read.
QUOTES_PER_THEME = 6

# The themes, in the order they are tested. A comment can only land in one, so
# the most specific reading comes first -- "too small" beats "size" beats
# "quality". Each is (label, cause it belongs to, the words that mean it).
#
# WORDS, NOT CODES. The reason code is Amazon's; the comment is the customer's,
# and the two disagree often enough to be worth reading separately -- a return
# filed as UNWANTED_ITEM whose comment says "half a size too short" is a sizing
# return, and only the comment says so.
THEMES = (
    ("Too small / runs small", "Sizing & Fit",
     ("too small", "runs small", "run small", "half size up", "size up",
      "too short", "too narrow", "too tight", "small fitting", "size smaller")),
    ("Too large / runs big", "Sizing & Fit",
     ("too big", "too large", "runs big", "run big", "size down", "too long",
      "too wide", "too loose", "size larger")),
    ("Did not fit / fit unclear", "Sizing & Fit",
     ("didn't fit", "did not fit", "doesnt fit", "does not fit", "poor fit",
      "wrong size", "fit issue", "sizing")),
    ("Not as pictured or described", "Listing Content",
     ("not as described", "not as pictured", "different from", "looks different",
      "not what i expected", "misleading", "colour different", "color different",
      "wrong colour", "wrong color", "wrong item",
      # THE PHOTO, in the words people actually use. "Colour is nothing like the
      # photo" matched none of the phrases above and fell through to unplaced --
      # and a comment naming the listing image is the single most actionable
      # kind there is, because the fix is one upload.
      "photo", "picture", "image", "looked better online")),
    ("Quality or durability", "Product Quality",
     ("quality", "cheap", "fell apart", "broke", "broken", "faulty", "defect",
      "stitching", "sole came", "tore", "ripped", "damaged")),
    ("Comfort", "Product Quality",
     ("uncomfortable", "hurt", "painful", "rubbing", "blister", "hard sole",
      "no support", "arch")),
    ("Changed mind / no longer needed", "Customer Preference",
     ("changed my mind", "no longer need", "found cheaper", "better price",
      "ordered by mistake", "duplicate", "don't like", "dont like",
      "didn't like", "didnt like")),
)


def _clean(s):
    """Through returns_view, so a quote here and the raw comment list above show
    the same sentence the same way."""
    return _rv.tidy_comment(s)


def theme_of(comment):
    """Which theme a comment belongs to, or "" -- the honest answer for a
    comment that says nothing this app has a rule for."""
    c = _clean(comment).lower()
    if not c:
        return ""
    for label, _nature, words in THEMES:
        for w in words:
            if w in c:
                return label
    return ""


def comment_themes(returns):
    """[{theme, nature, count, share, quotes}] biggest first, plus what was
    read and what could not be placed -- because a theme list that covers a
    third of the comments and does not say so reads as the whole picture."""
    counts, quotes, seen = {}, {}, {}
    read = placed = 0
    for r in returns or []:
        c = _clean(r.get("comment"))
        if not c:
            continue
        read += 1
        t = theme_of(c)
        if not t:
            continue
        placed += 1
        q = int(r.get("qty") or 1)
        counts[t] = counts.get(t, 0) + q
        # DISTINCT quotes. The same sentence appears hundreds of times in a
        # returns file -- "too small" five thousand times over -- and six
        # identical quotes teach nobody anything.
        key = c.lower()[:80]
        if len(quotes.get(t, ())) < QUOTES_PER_THEME and key not in seen:
            seen[key] = 1
            quotes.setdefault(t, []).append(c[:240])
    natures = {label: nat for label, nat, _ in THEMES}
    out = [{"theme": t, "nature": natures.get(t, ""), "count": n,
            "share": (round(n / placed * 100, 1) if placed else None),
            "quotes": quotes.get(t, [])}
           for t, n in counts.items()]
    out.sort(key=lambda x: -x["count"])
    return {"themes": out, "comments_read": read, "placed": placed,
            "unplaced": read - placed}


def by_parent(returns, family_by_asin=None, sold_by_asin=None):
    """One row per parent: returns, children, sellable split, monthly shape.

    THE KEY IS returns_view.line_of, called exactly as summarise calls it, with
    the same family map. That is deliberate and is the whole reason this
    function is safe to add: the Product Line table and this Parent table are
    the same grouping, so a total in one can never contradict a total in the
    other.

    sold_by_asin is {asin: {"units": n}} from this app's own sales, summed to
    the parent. Without it there is no rate, and the row says None rather than
    a number -- a return count with no denominator cannot say whether it is bad.
    """
    sold = sold_by_asin or {}
    fam = family_by_asin or {}
    rows = {}
    for r in returns or []:
        asin = str(r.get("asin") or "")
        family = fam.get(asin) or ""
        label = _rv.line_of(r.get("name"), family)
        key = label.lower()
        q = int(r.get("qty") or 1)
        row = rows.setdefault(key, {
            "grouped_by": ("the variation family this app knows" if family
                           else "the product name, cut at the variant"),
            "label": label, "returns": 0, "children": {},
            "sellable": 0, "unsellable": 0, "monthly": {},
            "monthly_sellable": {}, "monthly_unsellable": {},
            "reasons": {}, "natures": {},
        })
        row["returns"] += q
        row["children"][asin] = row["children"].get(asin, 0) + q
        # ONE definition of sellable, shared with returns_view (rule 12).
        ok = _rv.is_sellable(r.get("disposition"))
        if ok is True:
            row["sellable"] += q
        elif ok is False:
            row["unsellable"] += q
        d = str(r.get("date") or "")
        if len(d) >= 7:
            m = d[:7]
            row["monthly"][m] = row["monthly"].get(m, 0) + q
            if ok is True:
                row["monthly_sellable"][m] = row["monthly_sellable"].get(m, 0) + q
            elif ok is False:
                row["monthly_unsellable"][m] = row["monthly_unsellable"].get(m, 0) + q
        rsn = str(r.get("reason") or "")
        if rsn:
            row["reasons"][rsn] = row["reasons"].get(rsn, 0) + q
            nat = _rv.nature_of(rsn)
            row["natures"][nat] = row["natures"].get(nat, 0) + q

    total = sum(x["returns"] for x in rows.values()) or 0
    out = []
    for key, row in rows.items():
        kids = row.pop("children")
        row["child_count"] = len(kids)
        row["child_asins"] = sorted(kids, key=lambda a: -kids[a])
        ordered = 0
        known = False
        for a in kids:
            got = sold.get(a) or {}
            if got.get("units") is not None:
                ordered += int(got["units"] or 0)
                known = True
        row["ordered"] = ordered if known else None
        row["return_rate"] = (round(row["returns"] / ordered * 100, 2)
                              if known and ordered else None)
        row["share"] = round(row["returns"] / total * 100, 1) if total else None
        row["sellable_pct"] = (round(row["sellable"] /
                                     (row["sellable"] + row["unsellable"]) * 100, 1)
                               if (row["sellable"] + row["unsellable"]) else None)
        out.append(row)
    out.sort(key=lambda x: -x["returns"])
    return out


def months_seen(returns):
    """Every YYYY-MM in the data, in order -- the columns a monthly table needs."""
    ms = set()
    for r in returns or []:
        d = str(r.get("date") or "")
        if len(d) >= 7:
            ms.add(d[:7])
    return sorted(ms)


def partial_last_month(returns):
    """Is the newest month in this data incomplete?

    A report pulled on the 21st has three weeks of that month in it, and a
    monthly table that shows that column beside seven full ones makes the newest
    month look like a collapse. The column is marked, and -- more importantly --
    the trend below IGNORES it, because comparing three weeks with a month is
    how a made-up improvement gets reported.

    Worked out from the data itself: the last date present against the last day
    of its own month. No clock is read, so the same file gives the same answer
    forever.
    """
    ds = sorted(str(r.get("date") or "") for r in (returns or [])
                if len(str(r.get("date") or "")) >= 10)
    if not ds:
        return False
    last = ds[-1]
    y, m = int(last[:4]), int(last[5:7])
    if m == 12:
        nxt = "%d-01-01" % (y + 1)
    else:
        nxt = "%04d-%02d-01" % (y, m + 1)
    # The last day of that month, without importing a calendar: the day before
    # the first of the next one.
    import datetime as _dt
    lastday = (_dt.date(int(nxt[:4]), int(nxt[5:7]), 1)
               - _dt.timedelta(days=1)).isoformat()
    return last < lastday


# How many units a product has to have SOLD before its return rate is allowed
# to be called the worst in the catalogue. Twenty is low on purpose -- it is
# there to exclude one-order arithmetic, not to hide small products.
WORST_MIN_ORDERS = 20

# How far a period has to move before it is a TREND rather than noise. A month's
# returns swing by a fifth for no reason at all -- a promotion, a bank holiday,
# a delayed batch -- and an arrow drawn on a 5% change is a decoration.
TREND_BAND = 0.25


def trend_of(monthly, months):
    """"increasing" / "stable" / "decreasing" / "" for one product's months.

    The last three COMPLETE months against the first three, which is a shape
    rather than a pair of points: two months either end cancel out a single odd
    week, and comparing only the newest month with the oldest one turns any
    single bad month into a trend.

    "" -- said, not guessed -- when there are fewer than four complete months.
    Two points are not a direction.
    """
    ms = [m for m in (months or []) if m]
    if len(ms) < 4:
        return ""
    vals = [int((monthly or {}).get(m) or 0) for m in ms]
    first = sum(vals[:3]) or 0
    last = sum(vals[-3:]) or 0
    if not first:
        return "increasing" if last else ""
    change = (last - first) / float(first)
    if change > TREND_BAND:
        return "increasing"
    if change < -TREND_BAND:
        return "decreasing"
    return "stable"


def by_child(summary, family_by_asin=None, listing_summary_rows=None):
    """One row per CHILD ASIN, under the parent it belongs to.

    THIS RE-COUNTS NOTHING. Every figure comes from the per-ASIN rows
    returns_view.summarise has already built -- returns, units ordered, rate,
    the sellable split, the reason counts. All this adds is the parent each row
    sits under (the same line_of call the parent table uses) and, where a
    Listing Quality export has been supplied, the three columns only Amazon can
    answer: the return badge, CX health, and the top NCX reason.
    """
    fam = family_by_asin or {}
    amz = {}
    for r in listing_summary_rows or []:
        low = {str(k or "").strip().lower(): v for k, v in (r or {}).items()}
        a = ""
        for k, v in low.items():
            if "asin" in k:
                a = str(v or "").strip()
                break
        if a and a not in amz:
            amz[a] = low

    def g(low, *names):
        for n in names:
            for k, v in (low or {}).items():
                if n in k:
                    return re.sub(r"\s+", " ", str(v or "")).strip()
        return ""

    out = []
    for a in (summary or {}).get("asins") or []:
        asin = str(a.get("asin") or "")
        low = amz.get(asin) or {}
        rs = a.get("reasons") or {}
        out.append({
            "parent": _rv.line_of(a.get("name"), fam.get(asin) or ""),
            "asin": asin, "sku": a.get("sku"), "name": a.get("name"),
            "returns": a.get("returns"), "ordered": a.get("ordered"),
            "rate": a.get("rate"),
            "sellable": a.get("sellable"), "unsellable": a.get("unsellable"),
            "too_small": int(rs.get("APPAREL_TOO_SMALL") or 0),
            "too_large": int(rs.get("APPAREL_TOO_LARGE") or 0),
            # Amazon's own columns, blank when no Listing Quality file was given
            # -- blank meaning "not supplied", never "fine".
            "badge": g(low, "return badge"),
            "cx_health": g(low, "cx health"),
            "top_reason": g(low, "top ncx reason"),
        })
    out.sort(key=lambda x: (str(x["parent"]).lower(), -(x["returns"] or 0)))
    return out


def at_risk(listing_summary_rows):
    """The listings AMAZON has flagged, from a Listing Quality / Listing Summary
    export.

    THE THRESHOLD IS AMAZON'S, NOT OURS. This reads the "Return Badge Displayed"
    column and nothing else, because that column is the actual consequence: it
    says whether the "frequently returned item" warning is on the listing, or
    about to be. A rule of our own invention -- "flag anything over 15%" --
    produced 470 of 552 rows on a real account, which is a list nobody can act
    on, and it flagged ASINs with ONE order at "100%".

    Amazon writes three values there, measured on that account:

        Yes        54 rows -- the badge is on the listing NOW. Conversion is
                   already being hit; this is the emergency.
        At risk    43 rows -- not showing yet, one bad month away.
        --        455 rows -- fine.

    Both flagged states are returned, with `state` saying which, because they
    call for different urgency and merging them loses that. Empty when no such
    file has been given, and the screen says so rather than showing an empty
    table as though it were an answer.
    """
    out = []
    for r in listing_summary_rows or []:
        low = {str(k or "").strip().lower(): v for k, v in (r or {}).items()}

        def g(*names):
            for n in names:
                for k, v in low.items():
                    if n in k:
                        return re.sub(r"\s+", " ", str(v or "")).strip()
            return ""
        asin = g("asin")
        if not asin:
            continue
        badge = g("return badge")
        b = badge.lower()
        state = ("badge showing" if b in ("yes", "true", "y", "displayed")
                 else "at risk" if b == "at risk" else "")
        if not state:
            continue
        out.append({
            "asin": asin, "sku": g("sku"), "name": g("product name", "title"),
            "state": state, "badge": badge,
            "return_rate": _rv._num(g("return rate").replace("%", "")),
            "ncx_rate": _rv._num(g("ncx rate").replace("%", "")),
            "orders": _rv._num(g("total orders")),
            # "Too Small 80%" -- Amazon puts the reason and its share in one
            # cell, over two lines. Flattened above, kept whole here.
            "top_reason": g("top ncx reason"),
            "cx_health": g("cx health"),
            "star_rating": _rv._num(g("star rating")),
        })
    # ONE ROW PER ASIN, because the badge is on the LISTING, not the SKU.
    #
    # Amazon's export has one row per SKU, and a listing sold under three SKUs
    # appears three times with the same ASIN, the same rate and the same badge.
    # Measured: 552 rows for 360 distinct ASINs, and B0FRH7LVQG filling three
    # consecutive rows of the table with the same 50.82%. Three identical rows
    # do not say anything the first one did not.
    #
    # THE ROW KEPT IS THE ONE WITH THE MOST ORDERS -- the SKU the listing
    # actually sells under -- and nothing is summed across the others: their
    # "Total orders" and "Return rate" are Amazon's per-SKU figures and adding
    # them up would invent a number Amazon never gave. How many rows there were
    # is kept as `sku_rows` so the table can say so instead of hiding it.
    best = {}
    for r in out:
        cur = best.get(r["asin"])
        if cur is None:
            r["sku_rows"] = 1
            best[r["asin"]] = r
            continue
        cur["sku_rows"] += 1
        # Badged beats at risk; within a state, the SKU with the most orders.
        better = ((r["state"] == "badge showing") > (cur["state"] == "badge showing")
                  or (r["state"] == cur["state"]
                      and (r["orders"] or 0) > (cur["orders"] or 0)))
        if better:
            r["sku_rows"] = cur["sku_rows"]
            best[r["asin"]] = r
    out = list(best.values())

    # Badge-showing first -- it is the one costing money today -- then by how
    # much comes back, then by how many orders it comes back OUT OF, so a 100%
    # rate on one order never outranks 30% on nine hundred.
    out.sort(key=lambda x: (0 if x["state"] == "badge showing" else 1,
                            -(x["return_rate"] or 0), -(x["orders"] or 0)))
    return out


def insights(summary, parents, themes, at_risk_rows=None):
    """The findings, each with the action it implies.

    Every one is derived from a figure that is on the screen, and carries that
    figure in its own words -- an insight nobody can trace back to a number is
    an opinion, and this screen has no room for those. Ordered by how much of
    the problem each one accounts for, so the top of the list is the top of the
    problem.
    """
    out = []
    total = int(summary.get("units_returned") or 0)
    if not total:
        return out
    nat = summary.get("natures") or {}
    if isinstance(nat, list):
        nat = {x.get("nature") or x.get("key"): x.get("units") or x.get("count")
               for x in nat}
    rsn = summary.get("reasons") or {}
    if isinstance(rsn, list):
        rsn = {x.get("reason") or x.get("key"): x.get("units") or x.get("count")
               for x in rsn}

    def pct(n):
        return round((n or 0) / total * 100, 1)

    # --- sizing, and which way it runs -------------------------------------
    sizing = int(nat.get("Sizing & Fit") or 0)
    if sizing:
        small = int(rsn.get("APPAREL_TOO_SMALL") or 0)
        large = int(rsn.get("APPAREL_TOO_LARGE") or 0)
        ratio = (round(small / large, 1) if large else None)
        way = ("runs small" if small > large * 1.2
               else "runs large" if large > small * 1.2 else "is inconsistent")
        body = ("%d of the %d returns are about fit -- %s%% of everything that "
                "came back." % (sizing, total, pct(sizing)))
        if small and large:
            body += (" Too small %d against too large %d%s, so the sizing %s."
                     % (small, large,
                        (", a ratio of %s to 1" % ratio) if ratio else "", way))
        sell = summary.get("sellable_pct")
        if sell is not None:
            body += (" %s%% of returns come back sellable, which says the product "
                     "is fine and the guidance is not." % sell)
        out.append({
            "severity": "high" if pct(sizing) >= 30 else "medium",
            "share": pct(sizing),
            "title": "Fit is %s%% of all returns" % pct(sizing),
            "body": body,
            "action": ("Put the direction on the listing: a size chart, a line "
                       "saying which way it runs, and a photo worn. This is the "
                       "cheapest return to remove because nothing about the "
                       "product has to change."),
        })

    # --- the listing setting the wrong expectation --------------------------
    listing = int(nat.get("Listing Content") or 0)
    if listing:
        out.append({
            "severity": "high" if pct(listing) >= 15 else "medium",
            "share": pct(listing),
            "title": "The listing set the wrong expectation on %s%% of returns"
                     % pct(listing),
            "body": ("%d returns are 'not as described', the wrong item, or not "
                     "compatible. Nothing was faulty -- the page promised "
                     "something the parcel did not contain." % listing),
            "action": ("Read the top comments below and change the photo, title "
                       "or bullet each one is arguing with. Fixed once, these "
                       "stop."),
        })

    # --- something actually wrong with the product --------------------------
    quality = int(nat.get("Product Quality") or 0)
    if quality:
        out.append({
            "severity": "high" if pct(quality) >= 10 else "medium",
            "share": pct(quality),
            "title": "%s%% came back faulty or poor quality" % pct(quality),
            "body": ("%d returns name the product itself. Every one is a refund "
                     "AND a review waiting to happen, which is the part that "
                     "costs more than the refund." % quality),
            "action": ("Take it to the supplier with the comments attached. If "
                       "it does not move, stop selling the variant rather than "
                       "keep paying for it twice."),
        })

    # --- the worst product line --------------------------------------------
    #
    # WITH TWO FLOORS ON HOW BIG IT HAS TO BE. Without them this picked a
    # twelve-ASIN sliver at 67% on 135 orders and put it above a real product
    # line at 41% on eighteen hundred -- arithmetically true and useless, since
    # nobody's week should start with the smallest thing in the catalogue.
    #
    #   share    at least a fortieth of everything that came back
    #   ordered  at least WORST_MIN_ORDERS sold, because a "rate" out of one
    #            order is not a rate. This is the same mistake the at_risk
    #            reader above used to make with a 15% threshold, where a single
    #            order and a single return read as a 100% emergency.
    rated = [p for p in (parents or [])
             if p.get("return_rate") is not None
             and (p.get("share") or 0) >= 2.5
             and (p.get("ordered") or 0) >= WORST_MIN_ORDERS]
    if rated:
        worst = max(rated, key=lambda p: p["return_rate"])
        if worst["return_rate"] >= 20:
            out.append({
                "severity": "high",
                "share": worst.get("share"),
                "scope": worst["label"],
                "title": "%s returns at %s%%" % (worst["label"][:60],
                                                 worst["return_rate"]),
                "body": ("%d of %d units ordered came back, across %d child "
                         "ASINs. It is %s%% of everything returned."
                         % (worst["returns"], worst["ordered"],
                            worst["child_count"], worst.get("share") or 0)),
                "action": ("Start here. One product line at this rate is worth "
                           "more than every small fix elsewhere put together."),
            })

    # --- returns that came back saleable ------------------------------------
    sell = summary.get("sellable_pct")
    if sell is not None and sell >= 80:
        out.append({
            "severity": "info",
            "share": sell,
            "title": "%s%% of returns are still sellable" % sell,
            "body": ("The stock is coming back fine. That means almost none of "
                     "this is a manufacturing problem -- it is people ordering "
                     "the wrong thing, which is a page problem."),
            "action": ("Check the returned units are actually being relisted. "
                       "Sellable stock sitting in a returns bin is paid for "
                       "twice."),
        })

    # --- a product line getting worse ---------------------------------------
    rising = [p for p in (parents or []) if p.get("trend") == "increasing"]
    rising.sort(key=lambda p: -(p.get("returns") or 0))
    if rising:
        r0 = rising[0]
        names = ", ".join(p["label"][:40] for p in rising[:3])
        out.append({
            "severity": "high" if (r0.get("share") or 0) >= 10 else "medium",
            "share": r0.get("share"),
            "scope": r0["label"],
            "title": "%s is getting worse, not better" % r0["label"][:60],
            "body": ("Its last three complete months are more than a quarter "
                     "above its first three. %d product line%s moving the wrong "
                     "way: %s."
                     % (len(rising), "" if len(rising) == 1 else "s are", names)),
            "action": ("Look at what changed -- a new batch, a new size added, a "
                       "listing edit. A rising line is the one worth catching now, "
                       "while it is still small."),
        })

    # --- Amazon's own warning -----------------------------------------------
    shown = [a for a in (at_risk_rows or []) if a.get("state") == "badge showing"]
    soon = [a for a in (at_risk_rows or []) if a.get("state") == "at risk"]
    if shown or soon:
        out.append({
            "severity": "high" if shown else "medium",
            "share": None,
            "scope": "%d ASINs" % (len(shown) + len(soon)),
            "title": ("%d listings already carry the returns badge"
                      % len(shown)) if shown else
                     ("%d listings are one bad month from the returns badge"
                      % len(soon)),
            "body": ("Amazon shows a 'frequently returned item' warning on a "
                     "listing once its return rate stays high, and it costs "
                     "conversion on every visit from then on. %d are showing it "
                     "now and %d are flagged at risk."
                     % (len(shown), len(soon))),
            "action": ("Fix the ones already badged first -- they are losing "
                       "sales today. The at-risk list is the cheaper half: the "
                       "badge has not appeared yet."),
        })

    # --- what the customers said, where it disagrees -------------------------
    t = (themes or {}).get("themes") or []
    if t:
        top = t[0]
        out.append({
            "severity": "info",
            "share": top.get("share"),
            "title": "The commonest thing customers wrote: %s" % top["theme"],
            "body": ("%d of the %d comments this app could place say the same "
                     "thing. %d comments say something there is no rule for and "
                     "are worth reading raw."
                     % (top["count"], (themes or {}).get("placed") or 0,
                        (themes or {}).get("unplaced") or 0)),
            "action": ("Quotes are below. They are the exact words to answer on "
                       "the listing."),
        })

    for x in out:
        x.setdefault("scope", "Whole account")
    out.sort(key=lambda x: (0 if x["severity"] == "high" else
                            1 if x["severity"] == "medium" else 2,
                            -(x.get("share") or 0)))
    return out


# Severity -> what the Action Plan calls it, and when it should be done. One
# table, so the screen's badge and the workbook's Priority column cannot say
# different things about the same finding.
PRIORITY = {
    "high":   ("CRITICAL", "Week 1-2"),
    "medium": ("HIGH",     "Week 2-4"),
    "info":   ("MONITOR",  "Ongoing"),
}


def action_plan(found):
    """The insights as a plan: priority, action, detail, scope, timeline.

    EVERY ROW COMES FROM A FINDING. There is no list of good advice here waiting
    to be printed whatever the data says -- an account with no sizing problem
    gets no sizing row. That is the difference between a report and a template.
    """
    out = []
    for x in found or []:
        prio, when = PRIORITY.get(x.get("severity") or "info",
                                  ("MONITOR", "Ongoing"))
        out.append({
            "priority": prio,
            "action": x.get("title") or "",
            "details": ((x.get("body") or "") + " " + (x.get("action") or "")).strip(),
            "scope": x.get("scope") or "Whole account",
            "timeline": when,
        })
    return out


def build(returns, summary, family_by_asin=None, sold_by_asin=None,
          listing_summary_rows=None):
    """Everything the intelligence view needs, in one call."""
    months = months_seen(returns)
    partial = partial_last_month(returns)
    # THE TREND IGNORES AN INCOMPLETE MONTH. Three weeks of August against seven
    # full months reads as a collapse, and an arrow drawn on that is a lie.
    complete = months[:-1] if (partial and months) else months
    parents = by_parent(returns, family_by_asin, sold_by_asin)
    for p in parents:
        p["trend"] = trend_of(p.get("monthly"), complete)
    themes = comment_themes(returns)
    risky = at_risk(listing_summary_rows)
    found = insights(summary, parents, themes, risky)
    return {
        "parents": parents,
        "children": by_child(summary, family_by_asin, listing_summary_rows),
        "months": months,
        "months_complete": complete,
        "partial_last_month": partial,
        "themes": themes,
        "at_risk": risky,
        "has_amazon_quality": bool(listing_summary_rows),
        "insights": found,
        "action_plan": action_plan(found),
    }
