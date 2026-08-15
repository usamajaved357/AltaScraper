"""domain/returns_view.py -- why things come back, and what it costs.

Built from the Promixx FBA Returns Intelligence report, with the sections that
this app's data can actually support.

WHAT AMAZON GIVES US, MEASURED ON THE LIVE ACCOUNTS (15 Aug 2026)

    GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA      CANCELLED -- no data.
        These accounts are MFN (seller-fulfilled); there are no FBA returns.

    GET_FLAT_FILE_RETURNS_DATA_BY_RETURN_DATE      DONE, 35 columns, real rows.
        Order ID, Order date, Return request date, Return request status,
        ASIN, Merchant SKU, Item Name, Return quantity, Return Reason,
        Resolution, Return type, In policy, Order Amount, Refunded Amount,
        Category, A-to-Z Claim, SafeT claim fields, Label cost, VAT.

    A 90-day window comes back FATAL. Amazon caps this report at 60 days.

SO TWO SECTIONS OF THE ORIGINAL CANNOT BE BUILT FROM A SELLER-FULFILLED ACCOUNT,
and it is worth being exact about why rather than leaving them blank:

    Disposition & recovery (Sellable / Customer damaged / Defective)
    Customer voice (comment themes, verbatim quotes)

Both are FBA-only because Amazon physically receives, inspects and grades an FBA
return in its own warehouse, and records the buyer's comment when it does. An
MFN return goes straight back to the seller -- Amazon never sees it, so it has
nothing to report. Uploading an FBA returns file fills them in; that is what the
manual path is for, not a fallback.

ONE THING HERE IS BETTER THAN THE ORIGINAL. The Promixx page ESTIMATES lost
revenue. The seller-fulfilled report carries Refunded Amount -- the actual money
that went back -- so this reports the real figure and says which it is.
"""
import re

# Amazon's reason codes, grouped into the four things you would actually DO
# about them. The classification is the point of the section: fifty reason codes
# are a list, four causes are a decision.
#
# Deliberately conservative. A reason that does not clearly belong somewhere is
# "Unclassified" rather than being forced into a bucket -- a misfiled return
# points at the wrong fix, which is worse than an unfiled one.
# ORDER MATTERS, and the shipping rules come FIRST on purpose.
# DAMAGED_BY_CARRIER and DAMAGED_BY_FC both contain "DAMAGED", so with Product
# Quality checked first they were filed as a product problem -- which sends you
# to the supplier about something the courier did. A test caught it. The most
# specific cause is checked first.
NATURE_RULES = (
    ("Shipping / Delivery", (
        "DAMAGED_BY_CARRIER", "DAMAGED_BY_FC", "DAMAGED_IN_TRANSIT",
        "UNDELIVERABLE", "NEVER_ARRIVED", "LATE", "MISSING_ITEM", "SHIPPING")),
    ("Product Quality", (
        "DEFECTIVE", "QUALITY_UNACCEPTABLE", "MISSING_PARTS", "DAMAGED",
        "NOT_WORKING", "BROKEN", "PERFORMANCE", "MATERIAL_DIFFERENT")),
    ("Listing Content", (
        "NOT_AS_DESCRIBED", "DIFFERENT_FROM_DESCRIPTION", "WRONG_ITEM",
        "NOT_COMPATIBLE", "INACCURATE_WEBSITE_DESCRIPTION", "MISSED_ESTIMATED",
        "ORDERED_WRONG_ITEM", "NOT_AS_EXPECTED",
        # Seen on a live account as AMZ-PG-BAD-DESC. Anything Amazon calls a
        # description problem is a listing problem, whatever it prefixes it with.
        "BAD_DESC", "DESCRIPTION", "WRONG_SIZE_OR_COLOR")),
    ("Customer Preference", (
        "UNWANTED_ITEM", "NO_LONGER_NEEDED", "FOUND_BETTER_PRICE", "POOR_FIT",
        "APPAREL_TOO_SMALL", "APPAREL_TOO_LARGE", "SWITCHEROO", "CHANGED_MIND",
        "ACCIDENTAL_ORDER", "BOUGHT_BY_MISTAKE", "NO_REASON_GIVEN")),
)

# What each cause tells you to do. Shown beside the count, because a bar chart of
# categories invites "so what" and this is the answer.
NATURE_ACTION = {
    "Product Quality": ("The product itself. Talk to the supplier, or stop "
                        "selling it — every one of these is a refund AND a bad "
                        "review waiting to happen."),
    "Listing Content": ("Your listing set the wrong expectation. This is the "
                        "cheapest kind to fix: the photos, the title, the "
                        "specifics. Fix it once and the returns stop."),
    "Customer Preference": ("Nothing went wrong — they changed their mind. Some "
                           "of this is the cost of doing business; a lot of it "
                           "means you are attracting the wrong buyer."),
    "Shipping / Delivery": ("It broke or went astray on the way. Packaging, or "
                            "the carrier."),
    "Unclassified": ("Amazon gave a reason we have no rule for. Worth reading "
                     "the raw reasons below rather than assuming."),
}


def clean_reason(raw):
    """Amazon prefixes these with CR-, FC-, AMZ-PG- and so on.

    The prefixes are stacked, not single: a live account returned
    "AMZ-PG-BAD-DESC", which one pass leaves as "PG-BAD-DESC" and no rule
    matches. Stripped repeatedly until nothing is left to strip.
    """
    s = str(raw or "").strip().upper().replace(" ", "_")
    for _ in range(4):
        t = re.sub(r"^(CR|FC|MFN|SELLER|AMZ|PG|BUYER)[-_]", "", s)
        if t == s:
            break
        s = t
    return s.replace("-", "_")


def nature_of(reason):
    """Which of the four causes a reason code belongs to."""
    r = clean_reason(reason)
    if not r:
        return "Unclassified"
    for name, keys in NATURE_RULES:
        for k in keys:
            if k in r:
                return name
    return "Unclassified"


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _date(v):
    """Amazon writes 23-Jul-2026 here, not an ISO date."""
    s = str(v or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})", s)
    if m:
        months = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
                  "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
                  "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"}
        mm = months.get(m.group(2).upper())
        if mm:
            return "%s-%s-%02d" % (m.group(3), mm, int(m.group(1)))
    return s[:10]


# The columns this understands, from each report, by their real header names.
# Looked up by NAME rather than position: the two reports order them
# differently, and a seller who exports from Seller Central by hand gets a third
# order again.
MFN_COLS = {
    "date": ("return request date", "return date"),
    "order": ("order id", "order-id"),
    "asin": ("asin",),
    "sku": ("merchant sku", "sku", "seller sku"),
    "name": ("item name", "product name", "title"),
    "qty": ("return quantity", "quantity"),
    "reason": ("return reason", "reason"),
    "status": ("return request status", "status"),
    "resolution": ("resolution",),
    "order_amount": ("order amount",),
    "refunded": ("refunded amount",),
    "category": ("category",),
}
# The FBA report's own names, including the two columns MFN does not have.
FBA_COLS = {
    "date": ("return-date",),
    "order": ("order-id",),
    "asin": ("asin",),
    "sku": ("sku", "merchant-sku"),
    "name": ("product-name",),
    "qty": ("quantity",),
    "reason": ("reason",),
    "status": ("status",),
    "disposition": ("detailed-disposition", "disposition"),
    "comment": ("customer-comments", "customer comments"),
}


def _index(headers, spec):
    """Map our field names onto whichever columns this file actually has."""
    low = [str(h or "").strip().lower() for h in headers]
    out = {}
    for field, names in spec.items():
        for n in names:
            if n in low:
                out[field] = low.index(n)
                break
    return out


def detect(headers):
    """Which report is this? -> ('mfn'|'fba'|'', index_map).

    Told apart by their columns, not by what a file is called: the same report
    downloaded twice gets two different filenames and neither is meaningful.
    """
    low = [str(h or "").strip().lower() for h in headers]
    if "detailed-disposition" in low or "customer-comments" in low:
        return "fba", _index(headers, FBA_COLS)
    idx = _index(headers, MFN_COLS)
    if "asin" in idx and ("reason" in idx or "sku" in idx):
        return "mfn", idx
    # An FBA file whose optional columns are absent still has return-date.
    idx2 = _index(headers, FBA_COLS)
    if "asin" in idx2 and "date" in idx2:
        return "fba", idx2
    return "", {}


def parse_rows(headers, rows):
    """Report lines -> one dict per return. -> (returns, kind, skipped)."""
    kind, idx = detect(headers)
    if not kind:
        return [], "", len(rows or [])
    out, skipped = [], 0
    for r in rows or []:
        get = lambda f: (r[idx[f]].strip()
                         if f in idx and idx[f] < len(r) and r[idx[f]] is not None
                         else "")
        asin, sku = get("asin"), get("sku")
        if not (asin or sku):
            skipped += 1
            continue
        reason = get("reason")
        out.append({
            "date": _date(get("date")),
            "order_id": get("order"),
            "asin": asin,
            "sku": sku,
            "name": get("name"),
            "qty": int(_num(get("qty")) or 1),
            "reason": clean_reason(reason) or "NO_REASON_GIVEN",
            "reason_raw": reason,
            "nature": nature_of(reason),
            "status": get("status"),
            "resolution": get("resolution"),
            # REAL money, where the report carries it. The original report
            # estimated this; the seller-fulfilled one states it.
            "refunded": _num(get("refunded")),
            "order_amount": _num(get("order_amount")),
            "category": get("category"),
            # FBA only, and absent rather than blank so the screen can tell the
            # difference between "nothing was damaged" and "nobody graded it".
            "disposition": get("disposition") or None,
            "comment": get("comment") or None,
        })
    return out, kind, skipped


"""A PRODUCT LINE, worked out from the product name.

The report this screen is built to has a "Product Line Performance" section --
"Pursuit PE (Plastic)", "Pro Electric", "FORM Water Bottle" -- which answers the
question a per-SKU table cannot: is it THIS COLOUR that comes back, or is the
whole family bad? A 12.56% return rate across every Pro Electric is a product
problem; one colour at 12% among nine at 3% is a listing problem.

Amazon sends no such field, so it is derived, and the screen says so. The line is
the product name with its variant tail removed:

    "Promixx Pro Electric Shaker - SS (Silver/Gray)"  ->  "Promixx Pro Electric Shaker"
    "Pursuit PE 24oz - Glacier Gray"                  ->  "Pursuit PE 24oz"

which is where sellers put the variant: after a dash, an en dash, or a comma.
Where the app knows a real variation family for the ASIN, that is used instead --
a family IS the product line, and a derived one is only a guess at it.
"""
_LINE_SPLIT = re.compile(r"\s+[–—-]\s+|,\s+")


def line_of(name, family=None):
    if family:
        return str(family)
    s = str(name or "").strip()
    if not s:
        return "Unknown"
    head = _LINE_SPLIT.split(s)[0].strip()
    # A name with no separator at all is its own line rather than being cut at
    # an arbitrary word count -- guessing where a title stops being the product
    # is how two unrelated things end up in one row.
    return head or s


def summarise(returns, sold_by_asin=None, family_by_asin=None):
    """Everything the screen shows, from the parsed returns.

    `sold_by_asin` is {asin: {"units": n, "sales": x}} from the app's own sales
    data. Without it there is no return RATE -- and a rate is the only figure
    that says whether a number of returns is bad, so its absence is reported
    rather than filled with a plausible denominator.
    """
    sold = sold_by_asin or {}
    daily, reasons, natures, dispositions, statuses = {}, {}, {}, {}, {}
    by_asin, comments = {}, []
    units = refunded = 0.0
    have_refunds = False

    for r in returns or []:
        q = int(r.get("qty") or 1)
        units += q
        if r.get("date"):
            daily[r["date"]] = daily.get(r["date"], 0) + q
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + q
        natures[r["nature"]] = natures.get(r["nature"], 0) + q
        if r.get("status"):
            statuses[r["status"]] = statuses.get(r["status"], 0) + q
        if r.get("disposition"):
            dispositions[r["disposition"]] = dispositions.get(r["disposition"], 0) + q
        if r.get("refunded") is not None:
            refunded += float(r["refunded"])
            have_refunds = True
        if r.get("comment"):
            comments.append({"asin": r.get("asin"), "sku": r.get("sku"),
                             "reason": r.get("reason"), "text": r["comment"]})

        key = r.get("asin") or r.get("sku")
        a = by_asin.setdefault(key, {
            "asin": r.get("asin"), "sku": r.get("sku"), "name": r.get("name"),
            "returns": 0, "refunded": 0.0, "reasons": {}, "natures": {}})
        a["returns"] += q
        if r.get("refunded") is not None:
            a["refunded"] = round(a["refunded"] + float(r["refunded"]), 2)
        a["reasons"][r["reason"]] = a["reasons"].get(r["reason"], 0) + q
        a["natures"][r["nature"]] = a["natures"].get(r["nature"], 0) + q
        if not a["name"] and r.get("name"):
            a["name"] = r["name"]

    # Return RATE, per product and overall, but only where units sold is known.
    ordered_total = 0
    for key, a in by_asin.items():
        s = sold.get(a.get("asin") or "") or sold.get(key) or {}
        u = int(s.get("units") or 0)
        a["ordered"] = u or None
        a["sales"] = s.get("sales")
        a["rate"] = (round(a["returns"] / u * 100, 2) if u else None)
        ordered_total += u

    rows = sorted(by_asin.values(),
                  key=lambda x: (-(x["returns"] or 0), str(x.get("asin") or "")))

    # ---- PRODUCT LINE PERFORMANCE ------------------------------------------
    # The section the report has and this screen did not. Built from the rows
    # above, so a line total can never disagree with the SKUs inside it.
    fam = family_by_asin or {}
    lines = {}
    for a in rows:
        key = line_of(a.get("name"), fam.get(a.get("asin") or ""))
        L = lines.setdefault(key, {"line": key, "returns": 0, "ordered": 0,
                                   "sales": 0.0, "lost": 0.0, "skus": 0,
                                   "natures": {}, "estimated": False})
        L["returns"] += int(a.get("returns") or 0)
        L["ordered"] += int(a.get("ordered") or 0)
        L["sales"] += float(a.get("sales") or 0)
        L["skus"] += 1
        for n, c in (a.get("natures") or {}).items():
            L["natures"][n] = L["natures"].get(n, 0) + c
        # LOST REVENUE: the refunded figure where the report carried one, and an
        # estimate from this line's own average selling price where it did not.
        # Never a blended guess across lines -- a cheap line and an expensive one
        # do not lose the same money per unit, and that is the whole point of
        # splitting them.
        if a.get("refunded"):
            L["lost"] += float(a["refunded"])
        elif a.get("sales") and a.get("ordered"):
            L["lost"] += (float(a["sales"]) / int(a["ordered"])) * int(a["returns"] or 0)
            L["estimated"] = True

    line_rows = []
    for L in lines.values():
        L["rate"] = (round(L["returns"] / L["ordered"] * 100, 2)
                     if L["ordered"] else None)
        L["lost"] = round(L["lost"], 2)
        L["sales"] = round(L["sales"], 2)
        if not L["ordered"]:
            L["ordered"] = None
        line_rows.append(L)
    line_rows.sort(key=lambda x: (-(x["returns"] or 0), x["line"]))

    return {
        "lines": line_rows,
        # Said out loud, because a derived grouping presented as a fact is worse
        # than no grouping: the screen shows which SKUs are in each line so the
        # split can be checked.
        "lines_from": ("the variation families this app knows"
                       if fam else "the product names, cut at the variant"),
        "total_returns": len(returns or []),
        "units_returned": int(units),
        "unique_skus": len(by_asin),
        "total_ordered": ordered_total or None,
        # None, not 0 -- without units sold there IS no rate, and 0% would read
        # as "nothing comes back".
        "return_rate": (round(units / ordered_total * 100, 2)
                        if ordered_total else None),
        # The real figure where the report gives it; None where it does not.
        "refunded": (round(refunded, 2) if have_refunds else None),
        "refunded_is_actual": have_refunds,
        "daily": dict(sorted(daily.items())),
        "reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "natures": dict(sorted(natures.items(), key=lambda kv: -kv[1])),
        "dispositions": dict(sorted(dispositions.items(), key=lambda kv: -kv[1])),
        "statuses": dict(sorted(statuses.items(), key=lambda kv: -kv[1])),
        "asins": rows,
        "comments": comments,
        "nature_actions": NATURE_ACTION,
        # What this data set cannot answer, so the screen never leaves a blank
        # section looking like a fault.
        "has_disposition": bool(dispositions),
        "has_comments": bool(comments),
    }
