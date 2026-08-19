"""domain/tracker_fetch.py -- go and read the numbers the trackers watch.

Split from domain/trackers.py on purpose. That module is the ENGINE: watch list,
history, drift, alerts, and it makes no network calls at all, which is why it can
be tested exhaustively without touching Amazon. This one is the only part that
talks to SP-API, and it is deliberately thin.

NOTHING NEW IS CALLED HERE.

Every number already had a way to be fetched somewhere in this app, and the
temptation with a new screen is to write a fresh call for it. All four reuse
what exists (CLAUDE.md Rule 12):

    buybox, price   monitor/pricing.fetch_offers_batch -- twenty ASINs per call,
                    already normalised, already handles the 429 retry
    bsr             the Catalog Items sales ranks, the same block
                    routes/catalog_routes.py reads
    fee             domain/amazon_fees.quote -- extracted out of the generator
                    for this, because it was the only fee quote in the app and
                    nothing outside the generator could reach it

A FAILED READ IS NOT A READING.

Everything here returns None when Amazon does not answer, and domain/trackers
refuses to store a None. A monitoring screen that turns a failed fetch into a
zero is worse than one that shows nothing, because the zero looks like an answer.
"""
import datetime


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _mid(marketplace):
    try:
        import accounts as _acc
        return _acc.marketplace_id(marketplace) if hasattr(_acc, "marketplace_id") else ""
    except Exception:
        return ""


def fetch_offers(creds, asins, marketplace, seller_id="", log=print):
    """{asin: {"buybox":float|None, "price":float|None, "sellers":int}}.

    TWO NUMBERS FROM ONE CALL. The Buy Box price and your own price come out of
    the same offer set, so asking twice would double the API cost for no extra
    information.

    "Your price" is the offer whose SellerId is this account. When the account's
    seller id is not known, it is None rather than the cheapest offer -- guessing
    which offer is yours is how a Price Tracker ends up watching a competitor.
    """
    out = {}
    asins = [str(a).strip().upper() for a in (asins or []) if str(a).strip()]
    if not asins:
        return out
    try:
        from monitor import pricing as _pricing
    except Exception as e:
        log("tracker_fetch: pricing unavailable: %s" % str(e)[:120])
        return out
    sid = str(seller_id or "").strip()
    # getItemOffersBatch takes twenty at a time; the helper truncates rather
    # than raising, so the chunking is done here.
    for i in range(0, len(asins), 20):
        chunk = asins[i:i + 20]
        reqs = [{"asin": a, "marketplace": marketplace} for a in chunk]
        try:
            res = _pricing.fetch_offers_batch(creds, reqs, log=log) or []
        except Exception as e:
            log("tracker_fetch: offers failed: %s" % str(e)[:120])
            continue
        for r in res:
            a = str(r.get("asin") or "").upper()
            if not a:
                continue
            if not r.get("ok"):
                out[a] = {"buybox": None, "price": None, "sellers": None,
                          "error": str(r.get("error") or "")[:120]}
                continue
            summ = r.get("summary") or {}
            mine = None
            if sid:
                for o in (r.get("offers") or []):
                    if str(o.get("seller_id") or "") == sid:
                        mine = _num(o.get("landed")) or _num(o.get("price"))
                        break
            out[a] = {"buybox": _num(summ.get("buybox_price")),
                      "price": mine,
                      "sellers": summ.get("seller_count"),
                      "error": ""}
    return out


def fetch_bsr(creds, asins, marketplace, log=print):
    """{asin: rank|None} -- the best (lowest) sales rank Amazon reports.

    A thin view over fetch_ranks(), which returns the category as well. Kept as
    its own name because the trackers only ever want the number, and a caller
    that has to reach into a dict for one field is a caller that will get it
    wrong somewhere.
    """
    return {a: (d or {}).get("rank")
            for a, d in (fetch_ranks(creds, asins, marketplace, log) or {}).items()}


def fetch_ranks(creds, asins, marketplace, log=print):
    """{asin: {rank, category, all}} -- the best rank AND where it is ranked.

    An ASIN can carry several ranks: one in a broad display group and one or
    more in narrower categories. The BEST (lowest) one is taken because that is
    the rank a seller quotes and watches, and mixing "#4 in a niche" with
    "#180,000 overall" across readings would produce a chart of nothing.

    The CATEGORY comes back too, because it is the same call and the Category
    Explorer would otherwise make it a second time. `all` keeps every rank the
    listing carries, so a screen can show the niche as well as the headline.
    """
    out = {}
    asins = [str(a).strip().upper() for a in (asins or []) if str(a).strip()]
    if not asins:
        return out
    try:
        from sp_api.api import CatalogItemsV20220401 as CatalogItems
        from sp_api.base import Marketplaces
    except Exception as e:
        log("tracker_fetch: catalog unavailable: %s" % str(e)[:120])
        return out
    mid = _mid(marketplace)
    mkt = getattr(Marketplaces, str(marketplace).upper(), None) or Marketplaces.UK
    try:
        cat = CatalogItems(credentials=creds, marketplace=mkt, timeout=30)
    except Exception as e:
        log("tracker_fetch: catalog client failed: %s" % str(e)[:120])
        return out
    for a in asins:
        try:
            res = cat.get_catalog_item(asin=a, includedData=["salesRanks"],
                                       marketplaceIds=[mid] if mid else None)
            pay = res.payload if hasattr(res, "payload") else (res or {})
        except Exception as e:
            log("tracker_fetch: bsr %s: %s" % (a, str(e)[:100]))
            out[a] = {"rank": None, "category": "", "all": []}
            continue
        best = None
        best_cat = ""
        every = []
        for block in (pay.get("salesRanks") or []):
            ranks = (block.get("classificationRanks") or []) + \
                    (block.get("displayGroupRanks") or [])
            for r in ranks:
                v = _num(r.get("rank"))
                # The name Amazon uses differs between the two kinds of rank.
                # Both are read rather than one being assumed, because a missing
                # category turns the Category Explorer into a list of blanks.
                cat = (r.get("title") or r.get("classificationName")
                       or r.get("displayGroupName") or "")
                if v is None or v <= 0:
                    continue
                every.append({"rank": v, "category": str(cat)})
                if best is None or v < best:
                    best, best_cat = v, str(cat)
        out[a] = {"rank": best, "category": best_cat, "all": every}
    return out


def fetch_fees(creds, priced, marketplace, log=print):
    """{asin: fee|None} -- Amazon's quoted cut at each ASIN's current price.

    `priced` is {asin: price}. A fee is a fee AT A PRICE, so an ASIN with no
    known price gets None rather than a fee quoted at some default -- a number
    that would look precise and mean nothing.
    """
    out = {}
    try:
        from domain import amazon_fees as _fees
    except Exception as e:
        log("tracker_fetch: fees unavailable: %s" % str(e)[:120])
        return out
    mid = _mid(marketplace)
    for a, price in (priced or {}).items():
        p = _num(price)
        if p is None or p <= 0:
            out[str(a).upper()] = None
            continue
        q = _fees.quote(creds, marketplace, mid, str(a).upper(), p)
        out[str(a).upper()] = q.get("total") if q.get("basis") == _fees.QUOTED else None
    return out


def refresh(config_path, workspace_id, creds, marketplace, seller_id="",
            metrics=None, log=print):
    """Read every tracked number for one account and store the results.

    Returns {"ok", "asins", "read", "stored", "errors", "at"}. `read` counts the
    values Amazon actually gave back and `stored` the ones written -- they are
    reported separately because they differ exactly when something failed, and a
    single "done" count would hide that.

    THE FEE READ IS LAST AND DEPENDS ON THE OFFER READ, because a fee needs a
    price. If the offers call failed there is no price, so no fee is quoted; that
    is a missing reading, not a zero fee.
    """
    from domain import trackers as _t

    want = set(metrics or _t.METRICS.keys())
    watch = _t.tracked(config_path, workspace_id)
    asins = sorted(watch.keys())
    at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    res = {"ok": True, "asins": len(asins), "read": 0, "stored": 0,
           "errors": [], "at": at}
    if not asins:
        return res

    def _wants(asin, metric):
        return metric in want and metric in (watch.get(asin) or {})

    # --- offers: buybox + your price, one batch call ---
    need_offers = [a for a in asins
                   if _wants(a, "buybox") or _wants(a, "price") or _wants(a, "fee")]
    offers = {}
    if need_offers:
        try:
            offers = fetch_offers(creds, need_offers, marketplace, seller_id, log)
        except Exception as e:
            res["errors"].append("offers: %s" % str(e)[:140])
    for a in need_offers:
        row = offers.get(a) or {}
        for metric in ("buybox", "price"):
            if not _wants(a, metric):
                continue
            v = row.get(metric)
            if v is not None:
                res["read"] += 1
                if _t.record(config_path, workspace_id, a, metric, v, at):
                    res["stored"] += 1

    # --- sales rank ---
    need_bsr = [a for a in asins if _wants(a, "bsr")]
    if need_bsr:
        try:
            for a, v in (fetch_bsr(creds, need_bsr, marketplace, log) or {}).items():
                if v is not None:
                    res["read"] += 1
                    if _t.record(config_path, workspace_id, a, "bsr", v, at):
                        res["stored"] += 1
        except Exception as e:
            res["errors"].append("bsr: %s" % str(e)[:140])

    # --- fees, priced from what the offers call just returned ---
    need_fee = [a for a in asins if _wants(a, "fee")]
    if need_fee:
        priced = {}
        for a in need_fee:
            row = offers.get(a) or {}
            # Your own price first; the Buy Box price only as a stand-in, because
            # the fee you pay is on what YOU charge.
            p = row.get("price")
            if p is None:
                p = row.get("buybox")
            if p is not None:
                priced[a] = p
        if priced:
            try:
                for a, v in (fetch_fees(creds, priced, marketplace, log) or {}).items():
                    if v is not None:
                        res["read"] += 1
                        if _t.record(config_path, workspace_id, a, "fee", v, at):
                            res["stored"] += 1
            except Exception as e:
                res["errors"].append("fees: %s" % str(e)[:140])
    return res
