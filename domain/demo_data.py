"""domain/demo_data.py -- what the app looks like with data in it, for a
workspace that has none.

    "I have added the test user account for anyone to review but obviously there
     is no data available in the workspace ... so when no data is available i
     want to use the placeholder data which is not real but the user has an idea
     how the app looks like when it has data. use this logic for any workspace
     which do not have a brand or account connected"

WHO GETS IT. Only a workspace that CANNOT have real data -- no Amazon account of
its own, so every seller-scoped route refuses it before it can return anything.
Today that is Headbanger Lures (no credentials at all) and Miles Lubricants
(borrows Sheelady's app, so catalogue lookups work and nothing seller-scoped
does). A connected account with a quiet week gets its real, empty answer, never
this: an empty week is a fact about the business and inventing sales over the
top of it would be the worst thing this file could do.

THE ONE RULE, AND IT IS NOT NEGOTIABLE

    A placeholder must never be mistakable for a real figure.

Every payload here carries `demo: True` and a `demo_reason`, the screens draw
them dimmed and italic behind a bar that says so in the first line, and nothing
here is ever written to the database, a snapshot, a sheet or an export. The
Returns screen has worked this way since it was built -- see the note above
`_riSample` in static/js/returns.js -- and this is that idea made shared rather
than copied, because a second implementation of "pretend data" is how pretend
data eventually gets treated as real.

WHY IT IS DETERMINISTIC. Same workspace, same numbers, every time. A reviewer
comparing two screens has to see figures that agree with each other -- units on
the sales page matching units on the product table -- and a random generator
would make the app look broken rather than populated. Everything below is
derived from a seeded hash of the workspace id, so it is stable across restarts
without storing anything.

NO CLOCK. Dates are built from a date the CALLER passes in. A module that reads
today's date would make the tests depend on when they run, and every figure here
is supposed to be reproducible.
"""
import datetime as _dt
import hashlib


# The made-up catalogue. Deliberately obvious: a reviewer glancing at a screen
# should be able to tell these are not a real business's products, while they
# still look enough like listings to show what the screen is for.
PRODUCTS = (
    ("B0DEMO0001", "SAMPLE-LURE-01", "Demo Deep Diver Fishing Lure 90mm, 3 Pack"),
    ("B0DEMO0002", "SAMPLE-LURE-02", "Demo Surface Popper Lure 75mm, Twin Pack"),
    ("B0DEMO0003", "SAMPLE-LURE-03", "Demo Soft Bait Shad 120mm, 5 Pack"),
    ("B0DEMO0004", "SAMPLE-REEL-01", "Demo Spinning Reel 3000 Series"),
    ("B0DEMO0005", "SAMPLE-ROD-01", "Demo Travel Rod 7ft 4 Piece with Case"),
    ("B0DEMO0006", "SAMPLE-BOX-01", "Demo Tackle Box 3 Tray Waterproof"),
    ("B0DEMO0007", "SAMPLE-LINE-01", "Demo Braided Line 300m 30lb"),
    ("B0DEMO0008", "SAMPLE-NET-01", "Demo Folding Landing Net Rubber Mesh"),
)


def _seed(workspace_id):
    """A stable number from the workspace id. Same id, same catalogue, forever."""
    h = hashlib.sha256(("alta-demo:" + str(workspace_id or "")).encode()).digest()
    return int.from_bytes(h[:8], "big")


def _series(seed, n, lo, hi, wobble=0.35):
    """n numbers between lo and hi that look like a business rather than noise.

    A weekly rhythm and a gentle trend, because a flat line and pure randomness
    both read as "this chart is broken" -- and the point of the whole file is to
    show what a working screen looks like.
    """
    out = []
    span = max(1, hi - lo)
    for i in range(n):
        x = (seed >> (i % 40)) ^ (seed * (i + 7))
        r = ((x % 1000) / 1000.0) - 0.5              # -0.5 .. 0.5
        weekly = 1.0 + 0.28 * (1 if i % 7 in (5, 6) else -0.12)
        trend = 1.0 + (i / max(1, n - 1)) * 0.22
        v = (lo + span * 0.55) * weekly * trend * (1.0 + r * wobble)
        out.append(max(lo, min(hi, int(round(v)))))
    return out


def is_demo_workspace(account):
    """True when this workspace CANNOT have real data of its own.

    Reuses domain/accounts.has_own_creds -- the same function every seller-scoped
    route already gates on -- rather than inventing a second idea of "connected"
    (CLAUDE.md rule 12). If that function ever changes its mind about an account,
    this follows it automatically.
    """
    try:
        from domain import accounts as _acc
        return not _acc.has_own_creds(account or {})
    except Exception:
        # Never guess "yes" on an error. Showing invented figures to a connected
        # account is far worse than showing an empty screen to a demo one.
        return False


def reason(account):
    """Why this workspace is being shown samples, in the user's words."""
    label = str((account or {}).get("label") or "This workspace")
    try:
        from domain import accounts as _acc
        if _acc.is_borrowed(account or {}):
            return ("%s has no Amazon account of its own -- it borrows catalogue "
                    "access from another workspace -- so Amazon has no sales, "
                    "orders or returns to give it." % label)
    except Exception:
        pass
    return ("%s has no Amazon account connected yet, so there is nothing real "
            "to show." % label)


def _envelope(account, **payload):
    """Every demo payload looks the same from the outside, so no screen can
    accidentally treat one as real."""
    out = {"ok": True, "demo": True, "demo_reason": reason(account)}
    out.update(payload)
    return out


def _days(end_day, n):
    """n ISO days ending on end_day. end_day is passed IN -- see the header."""
    if isinstance(end_day, str):
        end_day = _dt.date.fromisoformat(end_day[:10])
    return [(end_day - _dt.timedelta(days=n - 1 - i)).isoformat()
            for i in range(n)]


# =============================================================================
# The payloads, one per screen. Each matches the shape that screen's real route
# returns, so the front end needs no second rendering path -- only a banner and
# the dimming.
# =============================================================================

def maybe(account, kind, has_data=False, **kw):
    """The one call every route makes. -> a payload, or None to carry on.

        _d = _dd.maybe(acc, "listings", has_data=bool(cards),
                       workspace_id=wsid)
        if _d:
            return jsonify(_d)

    TWO CONDITIONS, AND THE SECOND ONE IS THE IMPORTANT ONE.

        no Amazon account   the workspace cannot pull anything from Amazon
        AND no data at all  there is nothing of its own to show either

    `has_data` exists because the first condition alone is WRONG, and it was
    wrong in a way that put invented rows over real work. Headbanger Lures has
    no Amazon credentials -- and 115 real listings in the database, drafts
    somebody actually made. Gating on credentials alone replaced all 115 with
    eight samples. Two tests caught it (test_listings_store, test_store_merge);
    without them it would have shipped.

    So the caller states whether it found anything, because the caller is the
    only one that knows, and this returns None the moment it did. The rule the
    user asked for is "when no data is available", not "when no account is
    connected", and those are different questions.

    Returns None on any error too: a route that cannot tell must fall through to
    the real answer rather than invent one.
    """
    try:
        if has_data:
            return None
        if not is_demo_workspace(account):
            return None
        fn = _KINDS.get(kind)
        if not fn:
            return None
        return fn(account, **kw)
    except Exception:
        return None


# The keys the LISTINGS SCREEN reads, which are not the keys the STORE takes.
#
# This cost a round trip to find and is worth writing down. data/store.py's
# upsert_row takes sheet-header names -- "SKU", "Title", "Our Price (GBP)" --
# because it grew out of a Google Sheet. /rows_all returns something different:
# a flat lower-case CARD, 37 keys, sku/title/asin/price/status/product_type.
#
# Built in the store's shape, these rows arrived intact and the grid hid all
# eight of them behind "8 empty rows hidden", because isEmptyRow() in
# miles_template.js asks for r.sku and r.title and got undefined for both. The
# demo has to speak the reader's language, not the writer's.
PRODUCT_TYPES = ("FISHING_LURE", "FISHING_LURE", "FISHING_BAIT",
                 "FISHING_REEL", "FISHING_ROD", "STORAGE_BOX",
                 "FISHING_LINE", "FISHING_NET")
STATUSES = ("LIVE", "NEEDS_REVIEW", "READY", "LIVE",
            "HOLD_COMPLIANCE", "READY", "LIVE", "NEEDS_REVIEW")


def listings(account, workspace_id):
    """Draft rows in the CARD shape /rows_all returns -- see the note above."""
    seed = _seed(workspace_id)
    prices = _series(seed, len(PRODUCTS), 799, 3499)
    cogs = _series(seed + 11, len(PRODUCTS), 300, 1400)
    rows = []
    for i, (asin, sku, title) in enumerate(PRODUCTS):
        price = round(prices[i] / 100.0, 2)
        cost = round(min(cogs[i] / 100.0, price * 0.55), 2)
        rows.append({
            "sku": "%.2f_3Days_%s" % (price, asin),
            "title": title,
            "asin": asin,
            "brand": "Demo Brand",
            "status": STATUSES[i],
            "price": price,
            "cogs": cost,
            "cogs_source": "sample",
            "profit": round(price - cost - price * 0.15, 2),
            "handling_days": 3,
            "product_type": PRODUCT_TYPES[i],
            "bullets": ["This is sample copy, so the layout can be judged.",
                        "Nothing here came from Amazon.",
                        "Connect an account and these become your listings."],
            "description": "Sample description. Not a real product.",
            "search_terms": "sample demo placeholder",
            "notes": "Sample row — not a real product.",
            "barcode": "", "model_number": "",
            "attributes": {}, "attrs": {}, "item_highlights": [],
            "restricted": False, "viable": True,
            "ip_risk": "", "comp_risk": "", "comp_notes": "",
            "claim_flags": [], "claim_level": "", "claim_summary": "",
            "row": i + 2, "tab": "sample", "tab_gid": "",
            "store": "sample", "source": "sample",
        })
    return _envelope(account, rows=rows, count=len(rows))


def sales(account, workspace_id, end_day, days=30):
    """The Sales screen's daily series and totals."""
    seed = _seed(workspace_id)
    ds = _days(end_day, days)
    units = _series(seed, days, 4, 60)
    sessions = [max(u * 9, 20) for u in units]
    price = 18.5
    daily = []
    for i, d in enumerate(ds):
        daily.append({
            "date": d,
            "units": units[i],
            "ordered_sales": round(units[i] * price, 2),
            "sessions": sessions[i],
            "page_views": int(sessions[i] * 1.3),
            "orders": max(1, int(units[i] * 0.82)),
        })
    tot_units = sum(units)
    tot_sales = round(sum(x["ordered_sales"] for x in daily), 2)
    tot_sess = sum(sessions)
    return _envelope(
        account, daily=daily, start=ds[0], end=ds[-1],
        totals={"units": tot_units, "ordered_sales": tot_sales,
                "sessions": tot_sess,
                "orders": sum(x["orders"] for x in daily),
                "avg_selling_price": round(tot_sales / tot_units, 2)
                if tot_units else None,
                "unit_session_pct": round(tot_units / tot_sess * 100, 2)
                if tot_sess else None},
        products=_products_block(seed, tot_units, tot_sales))


def _products_block(seed, tot_units, tot_sales):
    """Per-ASIN rows whose totals ADD UP to the account totals above.

    A reviewer who adds the product column up and gets a different number than
    the headline learns that the app cannot count -- which is the opposite of
    what a demo is for. The largest row absorbs the rounding.
    """
    n = len(PRODUCTS)
    share = _series(seed, n, 5, 40)
    total_share = sum(share) or 1
    rows, used_u, used_s = [], 0, 0.0
    for i, (asin, sku, title) in enumerate(PRODUCTS):
        if i == 0:
            rows.append({"asin": asin, "sku": sku, "title": title})
            continue
        u = int(tot_units * share[i] / total_share)
        s = round(tot_sales * share[i] / total_share, 2)
        used_u += u
        used_s += s
        rows.append({"asin": asin, "sku": sku, "title": title,
                     "units": u, "ordered_sales": s,
                     "sessions": max(u * 9, 12)})
    rows[0].update({"units": tot_units - used_u,
                    "ordered_sales": round(tot_sales - used_s, 2),
                    "sessions": max((tot_units - used_u) * 9, 12)})
    rows.sort(key=lambda r: -(r.get("ordered_sales") or 0))
    return rows


def inventory(account, workspace_id):
    """Stock rows, with a couple of deliberate problems so the screen's warnings
    are visible -- a demo where everything is fine shows none of the app's job."""
    seed = _seed(workspace_id)
    qty = _series(seed, len(PRODUCTS), 0, 220)
    vel = _series(seed, len(PRODUCTS), 1, 9)
    rows = []
    for i, (asin, sku, title) in enumerate(PRODUCTS):
        q = qty[i] if i not in (2, 5) else (0 if i == 2 else 4)
        v = max(0.4, vel[i] / 2.0)
        rows.append({"asin": asin, "sku": sku, "title": title,
                     "qty": q, "velocity": round(v, 1),
                     "days_cover": (round(q / v, 1) if v else None),
                     "status": ("OUT OF STOCK" if q == 0
                                else "LOW" if q / v < 14 else "OK")})
    return _envelope(account, rows=rows, count=len(rows))


def returns(account, workspace_id, end_day, days=60):
    """Matches what domain/returns_view.summarise produces, so the Returns
    screen draws it with no special case."""
    seed = _seed(workspace_id)
    ds = _days(end_day, days)
    per = _series(seed, days, 0, 7)
    daily = {d: per[i] for i, d in enumerate(ds) if per[i]}
    units = sum(daily.values())
    reasons = {"APPAREL_TOO_SMALL": int(units * 0.34),
               "NOT_AS_DESCRIBED": int(units * 0.19),
               "UNWANTED_ITEM": int(units * 0.16),
               "APPAREL_TOO_LARGE": int(units * 0.12),
               "DEFECTIVE": int(units * 0.10)}
    counted = sum(reasons.values())
    if units - counted:
        reasons["NO_REASON_GIVEN"] = units - counted
    natures = {}
    try:
        from domain import returns_view as _rv
        for r, n in reasons.items():
            k = _rv.nature_of(r)
            natures[k] = natures.get(k, 0) + n
    except Exception:
        natures = {"Unclassified": units}
    return _envelope(
        account, total_returns=units, units_returned=units,
        unique_skus=len(PRODUCTS), total_ordered=int(units * 11) or None,
        return_rate=round(units / (units * 11) * 100, 2) if units else None,
        refunded=round(units * 17.4, 2), refunded_is_actual=False,
        daily=daily, reasons=dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        natures=dict(sorted(natures.items(), key=lambda kv: -kv[1])),
        dispositions={}, statuses={"Completed": units},
        sellable_pct=None, graded=0,
        asins=[], comments=[], lines=[],
        has_disposition=False, has_comments=False,
        start=ds[0], end=ds[-1])


def sales_summary(account, workspace_id, end_day, days=30):
    """The Sales stat cards. Built from the same series as sales(), so the cards
    and the chart under them cannot disagree."""
    s = sales(account, workspace_id, end_day, days)
    t = s["totals"]
    return _envelope(
        account, start=s["start"], end=s["end"],
        totals=t,
        # NO PRIOR PERIOD. The screen already knows how to say "there was no
        # before" and that is the truthful answer here -- inventing a previous
        # month as well would put a made-up percentage change on every card.
        prev=None, prev_exists=False,
        cards={"ordered_sales": t["ordered_sales"], "units": t["units"],
               "sessions": t["sessions"], "orders": t["orders"],
               "avg_selling_price": t["avg_selling_price"],
               "unit_session_pct": t["unit_session_pct"]})


def sales_series(account, workspace_id, end_day, days=30):
    """The daily chart, in the shape /sales/series returns."""
    s = sales(account, workspace_id, end_day, days)
    return _envelope(account, start=s["start"], end=s["end"],
                     series=s["daily"], rows=s["daily"])


def orders(account, workspace_id, end_day, days=14):
    """Recent orders, newest first."""
    seed = _seed(workspace_id)
    ds = _days(end_day, days)
    counts = _series(seed, days, 1, 6)
    out = []
    n = 0
    for i, d in enumerate(reversed(ds)):
        for j in range(counts[len(ds) - 1 - i]):
            p = PRODUCTS[(i + j) % len(PRODUCTS)]
            n += 1
            out.append({"order_id": "DEMO-%03d-%07d" % (i + 1, 1000000 + n),
                        "date": d, "asin": p[0], "sku": p[1], "title": p[2],
                        "qty": 1 + (j % 2),
                        "total": round(18.5 * (1 + (j % 2)), 2),
                        "status": "Shipped" if i > 1 else "Pending"})
    return _envelope(account, orders=out, count=len(out),
                     start=ds[0], end=ds[-1])

# The dispatch table for maybe(). Defined last, because every function it names
# has to exist first.
_KINDS = {
    "listings": listings,
    "sales": sales,
    "sales_summary": sales_summary,
    "sales_series": sales_series,
    "inventory": inventory,
    "returns": returns,
    "orders": orders,
}
