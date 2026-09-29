"""What advertising COST the account, for a window or by day -- the one rule
every profit screen uses (Rule 12; owner, 30 Sep 2026: "we also pay in ads").

TWO MEASUREMENTS OF THE SAME MONEY, NEVER ADDED TOGETHER
  ads_daily        what the Amazon Ads API reports spent, by the day the clicks
                   happened, ex-VAT. Only accounts with an Ads login have it.
  finance_daily    what Amazon INVOICED the account for ads
  .ads_charged     (ProductAdsPaymentEventList), ex-VAT, with the VAT on it in
  .ads_charged_tax ads_charged_tax -- dated by the invoice, a few days to weeks
                   after the clicks. Every account with the Finances role has it.

THE RULE
  * A window the Ads API covers (ads_daily has the account row) uses ads_daily:
    the right DAY, and per product.
  * Otherwise the invoices: the right TOTAL, dated by the invoice.
  * VAT on ads is a cost only to an account that is NOT VAT-registered (it
    cannot reclaim it). For ads_daily it is added at the rate MEASURED on the
    account's own invoices (tax / base, last 365 days) -- 20.0% on nestwell,
    30 Sep 2026 -- and left out, with a note, when no invoice has been seen.

Measured, nestwell_goods, 90 days to 30 Sep 2026: three invoices, 423.49 +
84.70 VAT = 508.19; the account is not VAT-registered, so 84.70 of real cost
no screen had shown.
"""
import datetime as _dt

from data import db as _db


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def vat_ratio(config_path, workspace_id, marketplace, end=None):
    """VAT charged on ads / the ads it was charged on, over the 365 days to
    `end`, from the account's own invoices. None when there are none."""
    end = str(end or _dt.date.today().isoformat())[:10]
    start = (_dt.date.fromisoformat(end) - _dt.timedelta(days=365)).isoformat()
    r = _db.get_db(config_path).execute(
        "SELECT SUM(COALESCE(ads_charged,0)) b, SUM(COALESCE(ads_charged_tax,0)) t "
        "FROM finance_daily WHERE workspace_id=? AND marketplace=? AND asin='*' "
        "AND date>=? AND date<=?", (workspace_id, marketplace, start, end)).fetchone()
    base = _f(r["b"] if r else 0)
    tax = _f(r["t"] if r else 0)
    if base <= 0:
        return None
    return round(tax / base, 4)


def vat_registered(vat_rate):
    """The account's VAT setting -> True (registered: VAT is reclaimed), False
    (set to 0: it is a cost), None (never set: UNKNOWN -- the app's rule for a
    missing rate, docs/decisions.md). The one test every profit screen uses
    (Rule 12; it was written out five times, 30 Sep 2026 review)."""
    if vat_rate is None or str(vat_rate).strip() == "":
        return None
    try:
        return float(vat_rate) > 0
    except (TypeError, ValueError):
        return None


def product_ratio(config_path, workspace_id, marketplace, end, vat_rate):
    """The VAT ratio to put on per-PRODUCT Ads API spend -> float or None.
    Only an account set as NOT registered (rate 0) pays it; unset adds none."""
    if vat_registered(vat_rate) is not False:
        return None
    return vat_ratio(config_path, workspace_id, marketplace, end)


def uplift(spend_by_key, ratio):
    """Ads API spend per product/day plus the VAT at `ratio` -> a new dict of
    floats. `spend_by_key` values may be numbers or {"spend": n} rows (then
    the row is copied with its spend raised)."""
    out = {}
    for k, v in (spend_by_key or {}).items():
        if isinstance(v, dict):
            row = dict(v)
            row["spend"] = round(_f(v.get("spend")) * (1 + (ratio or 0)), 4)
            out[k] = row
        else:
            out[k] = round(_f(v) * (1 + (ratio or 0)), 4)
    return out


def api_start(conn, workspace_id, marketplace):
    """The first day the Ads API has an account row for -> 'YYYY-MM-DD' or None.
    From that day on the Ads API measures ads; before it, only the invoices can
    (a window straddling the connection used to count the early days as 0)."""
    r = conn.execute(
        "SELECT MIN(date) d FROM ads_daily WHERE workspace_id=? AND marketplace=? "
        "AND asin='*'", (workspace_id, marketplace)).fetchone()
    return (r["d"] if r else None) or None


def by_day(config_path, workspace_id, marketplace, start, end, vat_registered):
    """{date: cost} for the window, and a dict saying how it was measured.

    Day by day: the Ads API from the first day it reports, Amazon's ad
    invoices before that. `vat_registered` is vat_registered()'s answer; None
    (not set) adds no VAT and says so.

    -> (days, info) where info = {source: "ads_api" | "invoices" | "both" |
       None, vat_added: float, vat_ratio: float|None, note: str}"""
    conn = _db.get_db(config_path)
    days, info = {}, {"source": None, "vat_added": 0.0, "vat_ratio": None, "note": ""}
    notes, used = [], set()
    first = api_start(conn, workspace_id, marketplace)
    add_vat = vat_registered is False
    if first and first <= end:
        ratio = vat_ratio(config_path, workspace_id, marketplace, end) if add_vat else None
        info["vat_ratio"] = ratio
        for r in conn.execute(
                "SELECT date, SUM(COALESCE(spend,0)) s FROM ads_daily WHERE workspace_id=? "
                "AND marketplace=? AND asin='*' AND date>=? AND date<=? GROUP BY date",
                (workspace_id, marketplace, max(start, first), end)):
            base = _f(r["s"])
            vat = round(base * ratio, 4) if ratio else 0.0
            days[r["date"]] = round(base + vat, 4)
            info["vat_added"] += vat
            used.add("ads_api")
        if add_vat and ratio is None and "ads_api" in used:
            notes.append("VAT on ad spend is not included: no Amazon Ads invoice has "
                         "been seen yet for this account to measure it from.")
    inv_end = end if not first else min(end, _day_before(first))
    if start <= inv_end:
        for r in conn.execute(
                "SELECT date, SUM(COALESCE(ads_charged,0)) b, SUM(COALESCE(ads_charged_tax,0)) t "
                "FROM finance_daily WHERE workspace_id=? AND marketplace=? AND asin='*' "
                "AND date>=? AND date<=? GROUP BY date",
                (workspace_id, marketplace, start, inv_end)):
            base, tax = _f(r["b"]), _f(r["t"])
            if not base and not tax:
                continue
            used.add("invoices")
            days[r["date"]] = round(base + (tax if add_vat else 0.0), 4)
            if add_vat:
                info["vat_added"] += tax
        if "invoices" in used:
            notes.append("Advertising %s from Amazon's ad invoices, dated by the "
                         "invoice (the Ads API has no figures for %s)."
                         % ("before %s" % first if first else "on this account",
                            "those days" if first else "this account"))
    if first and start < first <= end and "invoices" in used:
        # THE SEAM, SAID. An invoice posted after the API's first day can bill
        # clicks from before it; that part is in neither measurement here
        # (review, 30 Sep 2026). Small and once per account, but not hidden.
        notes.append("The first ad invoice after %s may also bill clicks from "
                     "before it; that part is not counted." % first)
    if vat_registered is None and used:
        notes.append("This account's VAT rate is not set, so VAT on ads is not "
                     "included -- set it in the account's settings.")
    info["source"] = ("both" if len(used) == 2 else (next(iter(used)) if used else None))
    info["note"] = " ".join(notes)
    info["vat_added"] = round(info["vat_added"], 2)
    return days, info


def _day_before(d):
    return (_dt.date.fromisoformat(str(d)[:10]) - _dt.timedelta(days=1)).isoformat()


def for_window(config_path, workspace_id, marketplace, start, end, vat_registered):
    """-> {cost: float|None, source, vat_added, vat_ratio, note}. None when
    neither measurement has anything for the window (unknown, not zero)."""
    days, info = by_day(config_path, workspace_id, marketplace, start, end, vat_registered)
    out = dict(info)
    out["cost"] = round(sum(days.values()), 2) if info["source"] else None
    return out
