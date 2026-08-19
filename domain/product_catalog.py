"""domain/product_catalog.py -- every product, ranked, with the four things
that are actually worth knowing about a catalogue.

    Orbit calls this ASINs, and the page is headed "Product Catalog". It is a
    table of every ASIN with units, revenue and COGS -- and above it, four
    statements:

        REVENUE CONCENTRATION   top N products (X%) generate 80% of revenue
        TOP PERFORMER           your #1 product is X% of total revenue
        DEAD INVENTORY          N products with content but no sales
        REVENUE LOSERS          bottom N products (X%) generate only Y%

WHY THOSE FOUR AND NOT A CHART.

A catalogue of eighty products is a list nobody reads. Each of those four is a
sentence that changes a decision:

    concentration   how exposed you are. "Four products are 80% of revenue" is
                    a risk; "forty products are" is a different business.
    top performer   what one suspension would cost you.
    dead inventory  products you have paid to create and list, earning nothing.
                    THE ONLY ONE THAT NAMES WORK TO DO.
    revenue losers  the tail, sized -- worth knowing before spending another
                    week on it.

THE PARETO IS COMPUTED, NOT ASSUMED. "80/20" is a slogan; the actual split for
one catalogue might be 80/28 or 80/6, and which it is happens to be the whole
point of the card. So the products are sorted by revenue and counted until 80%
is reached, and the real percentage is reported.

DEAD IS NOT THE SAME AS UNKNOWN.

"With content but no sales" is a specific claim: the product EXISTS in the
catalogue and sold nothing in the period. A product that simply has no sales row
because the account has not synced that far back has not been shown to be dead,
and counting it would turn a reporting gap into an accusation. So a product is
only dead if the catalogue knows it AND the sales window is real.

NOTHING HERE CALLS AMAZON. Rows come from sales_daily, names and pictures from
domain/catalogue, costs from domain/cogs_store -- all of it already in the app.
"""


def _f(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def _n(v):
    """A number for arithmetic: unknown counts as nothing SOLD, which is true.

    Distinct from _f, and both are needed. A missing revenue figure is not a
    number to report, but it is genuinely zero revenue for the purpose of
    ranking -- what it is not is evidence that the product is dead.
    """
    x = _f(v)
    return 0.0 if x is None else x


def totals(rows):
    """Fold per-day-per-ASIN rows into one row per ASIN."""
    by = {}
    for r in rows:
        a = str((r.get("asin") if isinstance(r, dict) else r["asin"]) or "").strip().upper()
        if not a or a == "*":
            continue
        g = r if isinstance(r, dict) else dict(r)
        t = by.setdefault(a, {"asin": a, "units": 0.0, "revenue": 0.0,
                              "orders": 0.0, "sessions": 0.0,
                              "parent_asin": "", "days": 0,
                              "first": "", "last": "", "currency": ""})
        t["units"] += _n(g.get("units"))
        t["revenue"] += _n(g.get("ordered_sales"))
        t["orders"] += _n(g.get("orders"))
        t["sessions"] += _n(g.get("sessions"))
        t["days"] += 1
        p = str(g.get("parent_asin") or "").strip().upper()
        if p and not t["parent_asin"]:
            t["parent_asin"] = p
        d = str(g.get("date") or "")
        if d:
            if not t["first"] or d < t["first"]:
                t["first"] = d
            if not t["last"] or d > t["last"]:
                t["last"] = d
        cur = str(g.get("currency") or "")
        if cur and not t["currency"]:
            t["currency"] = cur
    return by


def build(rows, names=None, costs=None, extra_asins=None):
    """Every product with its figures, plus the four headline findings.

    `names`  {asin -> {title, img, asin, sku}} from domain/catalogue
    `costs`  {asin or sku -> unit cost}
    `extra_asins` products the catalogue knows that have NO sales rows at all.
             Passed in rather than inferred, because "not in the sales table" is
             exactly the ambiguity this module refuses to guess at: it is either
             a dead product or an unsynced one, and only the caller knows which
             window it asked for.
    """
    names = names or {}
    costs = costs or {}
    by = totals(rows)

    # Products with content but no sales in the window. Added at zero rather
    # than left out, because a catalogue page that silently omits the products
    # earning nothing is the one page where they most need to appear.
    for a in (extra_asins or []):
        a = str(a or "").strip().upper()
        if a and a not in by:
            by[a] = {"asin": a, "units": 0.0, "revenue": 0.0, "orders": 0.0,
                     "sessions": 0.0, "parent_asin": "", "days": 0,
                     "first": "", "last": "", "currency": "", "no_sales_row": True}

    out = []
    for a, t in by.items():
        rec = names.get(a) or {}
        cost = _f(costs.get(a))
        if cost is None:
            cost = _f(costs.get(rec.get("sku") or ""))
        row = dict(t)
        row.update({
            "title": rec.get("title") or "",
            "img": rec.get("img") or "",
            "sku": rec.get("sku") or "",
            "cogs": cost,
            # Only when BOTH are known. A margin computed against a missing cost
            # would read as "this product makes 100%".
            "cogs_total": (cost * t["units"]) if (cost is not None and t["units"]) else None,
            "margin": None,
        })
        if row["cogs_total"] is not None and t["revenue"]:
            row["margin"] = (t["revenue"] - row["cogs_total"]) / t["revenue"]
        out.append(row)

    out.sort(key=lambda r: (-r["revenue"], -r["units"], r["asin"]))
    total_rev = sum(r["revenue"] for r in out)
    for i, r in enumerate(out, 1):
        r["rank"] = i
        r["share"] = (r["revenue"] / total_rev) if total_rev else None

    return {"rows": out, "total_revenue": total_rev,
            "total_units": sum(r["units"] for r in out),
            "products": len(out),
            "findings": findings(out, total_rev),
            "counts": counts(out)}


def findings(rows, total_rev=None):
    """The four sentences above the table.

    Each returns None when it cannot honestly be said, rather than a zero -- a
    card reading "Top 0 products generate 80% of revenue" is worse than no card.
    """
    total = total_rev if total_rev is not None else sum(r["revenue"] for r in rows)
    selling = [r for r in rows if r["revenue"] > 0]
    out = {"concentration": None, "top": None, "dead": None, "losers": None}
    if not rows:
        return out

    # --- concentration: how many products make up 80% -----------------------
    # COUNTED, not assumed. "80/20" is a slogan; this catalogue's real split is
    # the point of the card.
    if total > 0 and selling:
        run = 0.0
        need = total * 0.80
        n = 0
        for r in selling:
            run += r["revenue"]
            n += 1
            if run >= need:
                break
        out["concentration"] = {
            "n": n, "of": len(rows),
            "pct_of_catalogue": n / len(rows),
            # "Top 1 product ... make 80%" reads as a typo and undermines a card
            # whose whole job is to be a plain readable sentence.
            "label": "Top %d product%s (%.0f%% of the catalogue) %s 80%% of revenue"
                     % (n, "" if n == 1 else "s", n / len(rows) * 100,
                        "makes" if n == 1 else "make"),
        }
        top = selling[0]
        out["top"] = {
            "asin": top["asin"], "title": top["title"],
            "share": top["revenue"] / total,
            "label": "Your best product is %.0f%% of all revenue"
                     % (top["revenue"] / total * 100),
        }
        # --- the tail, sized -------------------------------------------------
        n_tail = max(1, int(len(rows) * 0.20))
        tail = rows[-n_tail:]
        tail_rev = sum(r["revenue"] for r in tail)
        out["losers"] = {
            "n": n_tail, "revenue": tail_rev,
            "share": tail_rev / total if total else None,
            "label": "The bottom %d (%.0f%% of the catalogue) %s %.0f%% of revenue"
                     % (n_tail, n_tail / len(rows) * 100,
                        "makes" if n_tail == 1 else "make",
                        tail_rev / total * 100),
        }

    # --- dead: exists, earned nothing ---------------------------------------
    dead = [r for r in rows if r["revenue"] <= 0 and r["units"] <= 0]
    if dead:
        out["dead"] = {
            "n": len(dead),
            "asins": [r["asin"] for r in dead[:50]],
            "label": "%d product%s listed and earning nothing"
                     % (len(dead), "" if len(dead) == 1 else "s"),
        }
    return out


def counts(rows):
    """Parents, variations and standalones.

    A variation is a row with a parent that is NOT itself; a parent is any ASIN
    named as one. Counted from what the rows say rather than assumed from the
    catalogue, so the number always matches the table underneath it.
    """
    parents = set()
    kids = 0
    for r in rows:
        p = str(r.get("parent_asin") or "").strip().upper()
        if p and p != r["asin"]:
            parents.add(p)
            kids += 1
    return {"products": len(rows), "parents": len(parents), "variations": kids,
            "standalone": len(rows) - kids}
