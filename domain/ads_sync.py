"""domain/ads_sync.py -- pull Advertising API reports into ads_daily.

WHAT THIS IS
The one writer of the ads_daily table. data/db.py shaped that table in August
for exactly this moment: "Today rows arrive from an uploaded Sponsored Products
report; when the API is connected it fills the SAME table and only `source`
changes." This is that swap. Nothing downstream needed rewriting -- domain/
sales_data.py, domain/contribution.py and the sales screens already read
ads_daily and already say "not connected" when it is empty.

TWO GRAINS, ONE TABLE, NO DOUBLE COUNTING
ads_daily is keyed (workspace_id, marketplace, date, asin) and readers pass the
asin they want:

    asin = '*'      the account-wide total for that day  <- campaign report
    asin = 'B0...'  that one product on that day         <- advertised product

Both are written. They are not added together anywhere: a reader asks for one
grain or the other, which is why the '*' row is a row and not a SUM().

The '*' row comes from the CAMPAIGN report rather than from summing the
per-ASIN rows, because those two are not the same number -- campaign spend
includes clicks that never resolved to an advertised product. Summing the parts
would quietly understate the total.

SPONSORED PRODUCTS ONLY -- SAY SO OUT LOUD
adProduct is SPONSORED_PRODUCTS. Sponsored Brands and Sponsored Display are
separate ad products with their own report types and are NOT in these figures.
If the account runs them, the spend written here is LOWER than the real ad spend
and any ACOS computed from it is flattering. That is a limitation of what is
pulled, not of what is stored, and it is recorded on every row via `source` so a
later Brands/Display pull can be told apart.

NOTHING IS INVENTED
api/amazon_ads.py returns None for a metric Amazon did not send, and None is
written as NULL, never as 0. A day with no spend row and a day with £0 spend are
different claims and only one of them is safe to draw a chart from.

THIS MODULE CANNOT WRITE TO AMAZON. It only calls the read paths of
api/amazon_ads.py, whose POST whitelist refuses anything but /reporting/reports
(CLAUDE.md Rule 8).
"""
import datetime as dt

from api import amazon_ads as _ads
from config import settings as _settings
from data import db as _db

# WHICH ADVERTISING PRODUCTS TO PULL, and why the default is one of the three.
#
#     "i do run sponsor product ads only for now but add the option of other
#      type of ads also the sp display and sp brands"
#
# So Sponsored Products is the default and Brands and Display are a setting, not
# a guess. Turning them on costs a separate report each -- 9-14 minutes of
# Amazon's build time apiece -- and, more importantly, their columns have never
# been checked against a live response (api/amazon_ads.py says so at the
# REPORT_TYPES table). Pulling a product nobody runs would prove nothing and
# would slow every sync.
#
# Per account, in config.json, as a list:
#     "ads_products": ["SPONSORED_PRODUCTS", "SPONSORED_BRANDS"]
# Absent means Sponsored Products alone, which is what every stored row is.
DEFAULT_PRODUCTS = ("SPONSORED_PRODUCTS",)
PRODUCTS_FIELD = "ads_products"


def products_for(cfg, account):
    """Which ad products this account has been told to pull. Never empty.

    An unknown name is dropped rather than sent: Amazon rejects the whole report
    request for one bad adProduct, so a typo in the setting would take Sponsored
    Products down with it.
    """
    raw = (account or {}).get(PRODUCTS_FIELD) or (cfg or {}).get(PRODUCTS_FIELD)
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.replace(",", " ").split()]
    known = [str(p).strip().upper() for p in (raw or [])
             if str(p).strip().upper() in _ads.KINDS_BY_PRODUCT]
    return tuple(known) or DEFAULT_PRODUCTS


def kinds_for(products):
    """The report kinds to pull, in order, for these products."""
    out = []
    for p in products:
        for k in _ads.KINDS_BY_PRODUCT.get(p, ()):
            if k not in out:
                out.append(k)
    return tuple(out)


# The Sponsored Products pair, kept as a name because the manual sync reads
# better for it. The destinations are decided in store_rows(), which is the only
# thing that should know them.
_KINDS = _ads.KINDS_BY_PRODUCT["SPONSORED_PRODUCTS"]
_GRAINS = tuple((k, "*" if k.endswith("campaign") else None) for k in _KINDS)

# A commissioned report that has not arrived after this long is not coming.
# Amazon's own link expires, and a job that retries forever hides a real
# failure behind an ever-growing attempts count.
_JOB_MAX_ATTEMPTS = 40


def _today():
    return dt.date.today()


def window(days=30, end=None):
    """The date range to ask for, as Amazon wants it.

    Ends YESTERDAY by default. Today is always partial -- Amazon is still
    counting it -- and storing a partial day as if it were finished makes the
    most recent point on every chart dip for no reason.
    """
    end = end or (_today() - dt.timedelta(days=1))
    start = end - dt.timedelta(days=int(days) - 1)
    return start.isoformat(), end.isoformat()


def time_unit_for(kind):
    """DAILY for everything. There is no longer a report stored per window.

    THE SEARCH TERM REPORT USED TO BE ASKED FOR AS A SUMMARY, and the note here
    said asking daily "would multiply every term by thirty for a screen that
    adds them straight back up". That was true of the screen it was written for.
    It is not true of the one the spec asks for:

        "The Search Terms page DOES respect the date picker ... store
         ppc_search_terms with a date column (one row per date per
         search-term-campaign-adgroup combo), not just a batch window."

    A summary cannot be split back into days, so the multiplication IS the
    point: it is the only way the day survives. Measured against the live API,
    7 Sep 2026 -- spSearchTerm at DAILY is accepted and returns a `date` column,
    393 rows over 7 days on nestwell_goods, which is about the same volume the
    summary produced for the same window.

    The rows still add straight back up for any screen that wants a window
    total; they can now also be asked what happened on the Tuesday.
    """
    return "DAILY"


def _rows_for(creds, marketplace, kind, start, end, wait, on_wait=None):
    """One report, at the grain its table needs. Never raises."""
    try:
        got = _ads.report(creds, marketplace, kind, start, end,
                          wait=wait, on_wait=on_wait,
                          time_unit=time_unit_for(kind))
    except Exception as e:
        return {"ok": False, "kind": kind, "rows": [], "error": str(e)[:400]}
    got["kind"] = kind
    got.setdefault("rows", [])
    return got


_METRICS = ("impressions", "clicks", "spend", "orders", "sales")


def _fold(rows, keys, keep=()):
    """Amazon's rows -> one total per key. THE REPORT GRAIN IS NOT THE TABLE GRAIN.

    Both reports come back finer than ads_daily stores them:

        campaign report            one row per (date, CAMPAIGN)
        advertised product report  one row per (date, CAMPAIGN, asin)

    ads_daily is keyed (date, asin) and has a UNIQUE index on it, so the rows
    have to be added up on the way in. Upserting them one by one instead does
    not error -- it silently keeps whichever campaign happened to be written
    LAST and throws the rest away. Measured on the first real pull: 2,958 report
    rows collapsed to 677 stored, and the biggest per-ASIN spend read as £14.55
    against a true account total of £256.93.

    An ASIN advertised in three campaigns is one ASIN that cost the sum of the
    three, and that is the only reading of it that reconciles with the account
    total.

    Additive metrics only. A key whose every row was None for a metric stays
    None rather than becoming 0 -- see the module docstring.

    `keep` names fields that DESCRIBE the key rather than measuring it -- a
    campaign's name, its status, its budget. Those must not be summed: three
    daily rows for one campaign do not mean a budget of three times the budget.
    The first non-empty value wins, because every row under one key is the same
    campaign describing itself the same way.
    """
    out = {}
    for r in rows:
        k = tuple((r.get(f) or "").strip() for f in keys)
        if not all(k):
            continue
        acc = out.get(k)
        if acc is None:
            acc = out[k] = {m: None for m in _METRICS}
            for f in keep:
                acc[f] = None
        for m in _METRICS:
            v = r.get(m)
            if v is None:
                continue
            acc[m] = v if acc[m] is None else acc[m] + v
        for f in keep:
            if acc.get(f) in (None, "") and r.get(f) not in (None, ""):
                acc[f] = r.get(f)
    return out


def _upsert(conn, workspace_id, marketplace, date, asin, m, fetched_at,
            ad_product="SPONSORED_PRODUCTS"):
    conn.execute(
        "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, "
        "impressions, clicks, spend, ad_orders, ad_sales, source, fetched_at, "
        "ad_product) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(workspace_id, marketplace, date, asin, ad_product) "
        "DO UPDATE SET "
        "impressions=excluded.impressions, clicks=excluded.clicks, "
        "spend=excluded.spend, ad_orders=excluded.ad_orders, "
        "ad_sales=excluded.ad_sales, source=excluded.source, "
        "fetched_at=excluded.fetched_at",
        (workspace_id, marketplace, date, asin,
         _int(m.get("impressions")), _int(m.get("clicks")), m.get("spend"),
         _int(m.get("orders")), m.get("sales"), "ads_api", fetched_at,
         ad_product))


def _upsert_campaign(conn, workspace_id, marketplace, date, cid, m, fetched_at,
                     ad_product="SPONSORED_PRODUCTS"):
    conn.execute(
        "INSERT INTO ads_campaign_daily (workspace_id, marketplace, date, "
        "campaign_id, campaign_name, status, budget, impressions, clicks, "
        "spend, ad_orders, ad_sales, source, fetched_at, ad_product) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(workspace_id, marketplace, date, campaign_id, ad_product) "
        "DO UPDATE SET "
        "campaign_name=excluded.campaign_name, status=excluded.status, "
        "budget=excluded.budget, impressions=excluded.impressions, "
        "clicks=excluded.clicks, spend=excluded.spend, "
        "ad_orders=excluded.ad_orders, ad_sales=excluded.ad_sales, "
        "source=excluded.source, fetched_at=excluded.fetched_at",
        (workspace_id, marketplace, date, str(cid),
         m.get("campaign_name") or "", m.get("state") or "",
         m.get("budget"),
         _int(m.get("impressions")), _int(m.get("clicks")), m.get("spend"),
         _int(m.get("orders")), m.get("sales"), "ads_api", fetched_at,
         ad_product))


def _upsert_targeting(conn, workspace_id, marketplace, date, cid, ad_group,
                      keyword, match_type, m, fetched_at,
                      ad_product="SPONSORED_PRODUCTS"):
    """One campaign, one day, one targeting. Its own table -- see store_rows.

    The key carries keyword AND match_type because one campaign genuinely runs
    the same word on more than one match type on the same day, and those are
    different buys at different bids. Collapsing them would lose the split the
    whole table exists to provide.

    Match type is kept AS AMAZON SENDS IT, including the mouthful
    TARGETING_EXPRESSION_PREDEFINED that auto campaigns come back with. The spec
    says to expect it -- "this is the literal enum string Amazon returns" -- and
    translating it to something friendlier here would put a word Amazon never
    said into the database. The screen can make it readable; the store keeps
    what arrived.
    """
    conn.execute(
        "INSERT INTO ads_targeting_daily (workspace_id, marketplace, date, "
        "campaign_id, campaign_name, ad_group, keyword, match_type, "
        "impressions, clicks, spend, ad_orders, ad_sales, ad_product, source, "
        "fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(workspace_id, marketplace, date, campaign_id, ad_group, "
        "keyword, match_type, ad_product) DO UPDATE SET "
        "campaign_name=excluded.campaign_name, impressions=excluded.impressions, "
        "clicks=excluded.clicks, spend=excluded.spend, "
        "ad_orders=excluded.ad_orders, ad_sales=excluded.ad_sales, "
        "source=excluded.source, fetched_at=excluded.fetched_at",
        (workspace_id, marketplace, date, str(cid),
         m.get("campaign_name") or "", str(ad_group or ""), str(keyword or ""),
         str(match_type or ""),
         _int(m.get("impressions")), _int(m.get("clicks")), m.get("spend"),
         _int(m.get("orders")), m.get("sales"), ad_product, "ads_api",
         fetched_at))


def _upsert_placement(conn, workspace_id, marketplace, date, cid, placement, m,
                      fetched_at, ad_product="SPONSORED_PRODUCTS"):
    """One campaign, one day, one placement. Its own table -- see store_rows."""
    conn.execute(
        "INSERT INTO ads_placement_daily (workspace_id, marketplace, date, "
        "campaign_id, campaign_name, placement, impressions, clicks, spend, "
        "ad_orders, ad_sales, ad_product, source, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(workspace_id, marketplace, date, campaign_id, placement, "
        "ad_product) DO UPDATE SET "
        "campaign_name=excluded.campaign_name, impressions=excluded.impressions, "
        "clicks=excluded.clicks, spend=excluded.spend, "
        "ad_orders=excluded.ad_orders, ad_sales=excluded.ad_sales, "
        "source=excluded.source, fetched_at=excluded.fetched_at",
        (workspace_id, marketplace, date, str(cid),
         m.get("campaign_name") or "", str(placement),
         _int(m.get("impressions")), _int(m.get("clicks")), m.get("spend"),
         _int(m.get("orders")), m.get("sales"), ad_product, "ads_api",
         fetched_at))


def _int(v):
    return None if v is None else int(round(v))


def store_rows(conn, workspace_id, marketplace, kind, rows, fetched_at,
               window=None, config_path=None):
    """Put one report's rows where they belong. THE ONE PLACE THAT DECIDES THAT.

    Both the blocking sync and the two-pass collector come through here, so a
    report stored by a background job and the same report stored by a manual
    refresh cannot land differently (CLAUDE.md Rule 12).

    The campaign report feeds TWO tables from one download:
        ads_daily          folded to the day, asin='*'  -- the account total
        ads_campaign_daily folded to day+campaign       -- the breakdown
    That is not double counting. They are different grains and every reader asks
    for one or the other; nothing anywhere adds them together.
    """
    prod = _ads.ad_product_of(kind)
    out = {"ad_product": prod}
    # THE SEARCH TERM REPORT GOES WHERE THE UPLOADED ONE ALREADY GOES.
    #
    # ppc_search_terms has had exactly one writer since it was created --
    # domain/ppc_view.store_rows -- and every PPC screen reads what that writer
    # put there. An API pull is a new SOURCE for those rows, not a new kind of
    # row, so it is handed to the same function in the same canonical shape
    # rather than given a second INSERT of its own (CLAUDE.md Rule 12).
    #
    # data/db.py's own note on that table says the Advertising API "is not
    # connected on any account (measured 18 Aug 2026)" and that the report has
    # to be downloaded from Seller Central by hand. That is what changes here.
    #
    # The report_id is the WINDOW, not the moment of the pull: store_rows
    # replaces a report id wholesale, so re-syncing the same thirty days
    # corrects those rows instead of doubling every figure.
    if kind == "search_term":
        from domain import ppc_view as _pv
        canon = []
        for r in rows:
            canon.append({
                "search_term": r.get("search_term"),
                "keyword": r.get("keyword"),
                "match_type": r.get("match_type"),
                "campaign": r.get("campaign_name"),
                "ad_group": r.get("ad_group"),
                # THE DAY, carried through. Without this the report is asked at
                # daily grain and then flattened on the way in, which is the
                # worst of both: thirty times the rows and none of the dates.
                "date": r.get("date"),
                "impressions": r.get("impressions"), "clicks": r.get("clicks"),
                "spend": r.get("spend"), "sales": r.get("sales"),
                "orders": r.get("orders"), "units": r.get("units"),
            })
        w = window or ("", "")
        rid = ("ads_api_%s_%s" % (w[0], w[1])) if w[0] else "ads_api"
        _rid, n = _pv.store_rows(config_path, workspace_id, marketplace, canon,
                                 report_id=rid,
                                 date_from=w[0], date_to=w[1])
        out["ppc_search_terms"] = n
        out["report_id"] = _rid
        return out
    # THE PLACEMENT REPORT GOES NOWHERE NEAR ads_daily.
    #
    # It is the SAME spend as the campaign report, cut a second way: one campaign
    # on one day appears once per placement, and those rows add up to the
    # campaign's day. Folding them into ads_daily or ads_campaign_daily would
    # mean every existing screen counted the same money three or four times -- the
    # two-grain mistake this app has already paid for once, where the account
    # total sits at asin='*' beside the per-product rows and summing both returns
    # exactly twice the truth. Its own table cannot be summed by accident.
    if kind == "placement":
        n = 0
        folded = _fold(rows, ("date", "campaign_id", "placement"),
                       keep=("campaign_name",))
        for (date, cid, place), m in sorted(folded.items()):
            if not place:
                # A row Amazon sent with no placement cannot be attributed to
                # one, and filing it under a made-up "unknown" placement would
                # put spend in a bucket that does not exist on Amazon.
                continue
            _upsert_placement(conn, workspace_id, marketplace, date, cid, place,
                              m, fetched_at, prod)
            n += 1
        out["ads_placement_daily"] = n
        return out

    # THE TARGETING REPORT IS A FIFTH GRAIN, and gets a fifth table.
    #
    # Same money as the campaign report, cut by what was targeted: one campaign
    # on one day appears once per keyword and match type, and those rows add up
    # to the campaign's day. Folding it anywhere existing would make every
    # current screen count the same spend several times over -- the two-grain
    # mistake this app has already paid for once. Its own table cannot be summed
    # by accident.
    if kind == "targeting":
        n = 0
        # THE KEY IS (day, campaign, targeting, match type) AND NOT THE AD GROUP.
        #
        # _fold drops any row whose every key part is not filled -- deliberately,
        # so a blank never becomes a bucket. The ad group is blank on this
        # report: it is asked for as adGroupId, and _ROW_MAP fills `ad_group`
        # from adGroupName. Keyed on it, EVERY row was dropped -- 23,634 rows
        # from Amazon and nothing stored, silently, because dropping is what
        # that guard is for.
        #
        # It is carried as a DESCRIBING field instead of a keying one, which is
        # also the honest grain: what the charts need is spend per match type
        # per day, and two ad groups running the same keyword on the same match
        # type in the same campaign are the same buy for that purpose.
        folded = _fold(rows, ("date", "campaign_id", "keyword", "match_type"),
                       keep=("campaign_name", "ad_group"))
        for (date, cid, kw, mt), m in sorted(folded.items()):
            _upsert_targeting(conn, workspace_id, marketplace, date, cid,
                              m.get("ad_group") or "", kw, mt, m, fetched_at,
                              prod)
            n += 1
        out["ads_targeting_daily"] = n
        return out

    if kind.endswith("campaign"):
        n = 0
        for (date,), m in sorted(_fold(rows, ("date",)).items()):
            _upsert(conn, workspace_id, marketplace, date, "*", m, fetched_at,
                    prod)
            n += 1
        out["ads_daily"] = n
        c = 0
        folded = _fold(rows, ("date", "campaign_id"),
                       keep=("campaign_name", "state", "budget"))
        for (date, cid), m in sorted(folded.items()):
            _upsert_campaign(conn, workspace_id, marketplace, date, cid, m,
                             fetched_at, prod)
            c += 1
        out["ads_campaign_daily"] = c
    else:
        n = 0
        for (date, asin), m in sorted(_fold(rows, ("date", "asin")).items()):
            _upsert(conn, workspace_id, marketplace, date, asin, m, fetched_at,
                    prod)
            n += 1
        out["ads_daily"] = n
    return out


# ---------------------------------------------------------------------------
# READING BACK WHAT WAS STORED
# ---------------------------------------------------------------------------
#
# A screen must never commission its own report. Amazon takes 9-14 minutes to
# build one, which is longer than any web request should live, and Dr PPC did
# exactly that with a 90-second wait -- so it timed out and showed errors on an
# account whose figures were already in the database.
#
# These return the shape api/amazon_ads._row() produces, because that is what
# domain/dr_ppc.py was written against. One shape, whether the rows came from a
# live report or from the tables (CLAUDE.md Rule 12).


ACCOUNT_TOTAL = "*"          # the asin value the day's account-wide row uses


def marketplace_for(config_path, account):
    """The ONE marketplace this account's advertising profile covers.

    AN ADVERTISING PROFILE IS ONE ADVERTISER IN ONE MARKETPLACE. Its id is what
    every report call is scoped to, so a report fetched with it describes that
    marketplace and no other -- whatever marketplace name the caller happened to
    pass alongside it.

    The scheduler was looping over every marketplace on the account and
    commissioning a report for each, with the same profile id each time. So one
    profile's figures were filed once per marketplace, under a different name
    every time. MEASURED on nestwell_goods, whose account lists eleven
    marketplaces: ads_daily and ads_campaign_daily each held two byte-identical
    copies, UK and IT -- 705 of 705 rows and 5019 of 5019 rows the same, same
    campaign names ("SP_AUTO_BugZapper_DISC"), different fetched_at. Nine more
    copies were still to come. An account-wide read that spanned marketplaces
    would have reported eleven times the real spend.

    The profile itself says which marketplace it is: /v2/profiles returns
    marketplaceStringId, which reverse-maps exactly onto this app's own codes.
    No country-code guessing -- a UK profile reports countryCode "GB", and this
    app calls that marketplace "UK".

    -> (marketplace, note). The note is empty when Amazon answered; when it did
    not, the account's default marketplace is used and the note says so. Even a
    wrong single marketplace writes ONE set of rows, which is recoverable; the
    loop wrote eleven, which is not distinguishable from real data afterwards.
    """
    from domain import accounts as _accts

    acc = account or {}
    default = str(acc.get("default_marketplace") or "").strip().upper()
    if not default:
        ms = [str(m or "").strip().upper() for m in (acc.get("marketplaces") or [])]
        ms = [m for m in ms if m and m != "__ALL__"]
        default = ms[0] if ms else "UK"

    want = str(acc.get("ads_profile_id") or "").strip()
    try:
        from api import amazon_ads as _ads
        cfg = _settings_cfg(config_path)
        creds = _ads.creds_for(cfg, acc)
        if not want:
            want = str(creds.get("ads_profile_id") or "").strip()
        if not want:
            return default, ("No advertising profile id is set, so the account's "
                             "default marketplace was used.")
        # Asked against the default only to reach an endpoint; /v2/profiles is
        # not scoped to a profile and returns every one this login can see.
        found = _ads.profiles(creds, default) or []
    except Exception as e:
        return default, ("Could not ask Amazon which marketplace this "
                         "advertising profile is for (%s), so the account's "
                         "default was used." % str(e)[:120])

    p = next((x for x in found if str(x.get("profile_id")) == want), None)
    if not p:
        return default, ("The configured advertising profile is not one this "
                         "login can see, so the account's default marketplace "
                         "was used. Reports would come back empty.")
    mid = str(p.get("marketplace_id") or "")
    for code, val in (_accts.MARKETPLACE_IDS or {}).items():
        if val == mid:
            return code, ""
    return default, ("Amazon reports this advertising profile in marketplace %s, "
                     "which this app has no code for, so the account's default "
                     "was used." % (mid or p.get("country") or "?"))


def _settings_cfg(config_path):
    from config import settings as _s
    return _s.read_raw(config_path)


def stray_marketplaces(config_path, workspace_id, keep):
    """Advertising rows filed under a marketplace this account does not advertise in.

    The counterpart to marketplace_for: that stops NEW copies being written,
    this reports the ones already stored. Read-only, and deliberately separate
    from the delete -- what to do about somebody's stored figures is their
    decision, not a side effect of fixing the writer.

    `keep` is the marketplace the profile actually covers. Everything else in
    these two tables came from the loop and is a copy of it.
    """
    conn = _db.get_db(config_path)
    keep = str(keep or "").strip().upper()
    out = []
    # EVERY table the sync files by marketplace, not just the first one.
    #
    # This scanned ads_daily alone, so a marketplace that had copies ONLY in the
    # search-term table was invisible to it -- which is exactly what happened:
    # the daily tables were cleaned of their Italian copies and eleven
    # marketplaces' worth of duplicated search terms stayed, unreported, because
    # nothing looked there.
    seen = set()
    for t in _MARKETPLACE_TABLES:
        try:
            for mkt, in conn.execute(
                    "SELECT DISTINCT marketplace FROM %s WHERE workspace_id=?"
                    % t, (workspace_id,)):
                m = str(mkt or "").upper()
                if m and m != keep:
                    seen.add(m)
        except Exception:
            pass
    for m in sorted(seen):
        d = conn.execute(
            "SELECT COUNT(*) n, ROUND(SUM(spend),2) s FROM ads_daily "
            "WHERE workspace_id=? AND marketplace=?", (workspace_id, m)).fetchone()
        c = conn.execute(
            "SELECT COUNT(*) n, ROUND(SUM(spend),2) s FROM ads_campaign_daily "
            "WHERE workspace_id=? AND marketplace=?", (workspace_id, m)).fetchone()
        try:
            tm = conn.execute(
                "SELECT COUNT(*) n, ROUND(SUM(spend),2) s FROM ppc_search_terms "
                "WHERE workspace_id=? AND marketplace=?",
                (workspace_id, m)).fetchone()
        except Exception:
            tm = None
        # IS IT ACTUALLY A COPY? Said as a measurement rather than assumed. A
        # marketplace this account really does advertise in separately would
        # NOT match the kept one row for row, and must not be swept up.
        same = conn.execute(
            "SELECT COUNT(*) FROM ads_daily a JOIN ads_daily b "
            "ON a.date=b.date AND a.asin=b.asin AND a.spend IS b.spend "
            "WHERE a.workspace_id=? AND b.workspace_id=? "
            "AND a.marketplace=? AND b.marketplace=?",
            (workspace_id, workspace_id, keep, m)).fetchone()[0]
        term_rows = int((tm["n"] if tm else 0) or 0)
        out.append({
            "marketplace": m,
            "ads_daily_rows": d["n"], "ads_daily_spend": d["s"],
            "campaign_rows": c["n"], "campaign_spend": c["s"],
            "search_term_rows": term_rows,
            "search_term_spend": (tm["s"] if tm else None),
            "rows_identical_to_%s" % keep.lower(): same,
            # A marketplace with nothing in the daily tables but rows in the
            # search-term one is still a copy -- it is simply a copy the daily
            # clean-up already took half of.
            "looks_like_a_copy": bool((d["n"] and same >= d["n"])
                                      or (not d["n"] and term_rows)),
        })
    return out


# Every table the advertising sync files by marketplace, and therefore every
# table a wrongly-scoped profile could have written copies into.
#
# ppc_search_terms belongs here and was missed the first time. The loop wrote
# the SAME search-term report to eleven marketplaces -- IT, FR, IE, ES, PL, AE,
# BE, NL, SE, DE and UK, 774 identical rows and 256.93 of identical spend in each
# -- and a clean-up that tidied the two daily tables left all of it behind.
_MARKETPLACE_TABLES = ("ads_daily", "ads_campaign_daily", "ads_placement_daily",
                       "ppc_search_terms")


def drop_marketplace(config_path, workspace_id, marketplace, dry_run=True):
    """Delete one marketplace's advertising rows for one account.

    DRY RUN BY DEFAULT. Deleting stored figures is not reversible from inside
    the app, so the caller has to ask for it in as many words. The rows are
    re-fetchable -- the sync pulls a thirty-day window each pass -- but only for
    a marketplace the profile actually covers, which is exactly what these are
    not.
    """
    conn = _db.get_db(config_path)
    mkt = str(marketplace or "").strip().upper()
    counts = {}
    # ads_placement_daily is here because it is the same family: written by the
    # same sync, from the same profile, and therefore capable of the same
    # duplication. Left out, a later clean-up would tidy two tables and leave
    # the third holding copies nobody remembers are there.
    for t in _MARKETPLACE_TABLES:
        try:
            counts[t] = conn.execute(
                "SELECT COUNT(*) FROM %s WHERE workspace_id=? AND marketplace=?"
                % t, (workspace_id, mkt)).fetchone()[0]
        except Exception:
            counts[t] = 0
    if dry_run:
        return {"dry_run": True, "marketplace": mkt, "would_delete": counts}
    for t in _MARKETPLACE_TABLES:
        try:
            conn.execute(
                "DELETE FROM %s WHERE workspace_id=? AND marketplace=?" % t,
                (workspace_id, mkt))
        except Exception:
            pass
    conn.commit()
    return {"dry_run": False, "marketplace": mkt, "deleted": counts}


def totals(config_path, workspace_id, marketplace, start, end):
    """This account's advertising for a window. THE ONE READER OF THE TOTAL.

    ads_daily deliberately holds TWO GRAINS in one table -- the day's
    account-wide figure at asin='*', and the same money broken out per product --
    and the module docstring says they are never added together. A reader that
    sums the table without naming a grain gets EXACTLY DOUBLE, and nothing about
    the number looks wrong: it is plausible, it moves the right way day to day,
    and it is twice the truth.

    MEASURED on nestwell_goods/UK, 2026-08-08..09-04: the '*' rows come to
    256.93 and the per-ASIN rows to 256.93, and an unfiltered SUM returns
    513.86 -- against a campaign-grain total of 256.93. All 28 of 28 days
    carried both grains, so the doubling was total rather than occasional.
    domain/weekly_brief.py and routes/daily_routes.py were both summing the
    table that way, so the weekly brief's ad spend and the daily check's
    "yesterday" were both twice what was actually spent.

    So the grain stops being something each caller has to remember. Callers that
    want the per-product breakdown ask contribution.py or ads_routes, which have
    always said asin<>'*' explicitly.

    Returns None for a metric when there is no row at all -- a window with no
    advertising data is not a window with zero spend, and only one of those is
    safe to put in a P&L.
    """
    conn = _db.get_db(config_path)
    r = conn.execute(
        "SELECT COUNT(*) n, SUM(spend) spend, SUM(ad_sales) sales, "
        "       SUM(clicks) clicks, SUM(impressions) impressions, "
        "       SUM(ad_orders) orders "
        "FROM ads_daily WHERE workspace_id=? AND marketplace=? "
        "AND date>=? AND date<=? AND asin=?",
        (workspace_id, marketplace, start, end, ACCOUNT_TOTAL)).fetchone()
    days = conn.execute(
        "SELECT COUNT(DISTINCT date) d FROM ads_daily WHERE workspace_id=? "
        "AND marketplace=? AND date>=? AND date<=? AND asin=?",
        (workspace_id, marketplace, start, end, ACCOUNT_TOTAL)).fetchone()
    n = int((r["n"] if r else 0) or 0)
    if not n:
        return {"has_data": False, "days": 0, "spend": None, "sales": None,
                "clicks": None, "impressions": None, "orders": None,
                "acos_pct": None, "roas": None}
    spend = _num(r["spend"])
    sales = _num(r["sales"])
    return {
        "has_data": True,
        "days": int((days["d"] if days else 0) or 0),
        "spend": spend, "sales": sales,
        "clicks": _num(r["clicks"]), "impressions": _num(r["impressions"]),
        "orders": _num(r["orders"]),
        # NONE, NEVER ZERO. An ACOS with no sales is undefined, not 0%, and a
        # printed 0% invites somebody to act on it.
        "acos_pct": (round(100.0 * spend / sales, 1)
                     if (spend is not None and sales) else None),
        "roas": (round(sales / spend, 2)
                 if (sales is not None and spend) else None),
    }


def _num(v):
    """A stored metric, or None. NULL means Amazon did not send it."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 2)


def campaign_rows(config_path, workspace_id, marketplace, start, end):
    """Stored campaign performance, summed over the window, in _row() shape."""
    conn = _db.get_db(config_path)
    out = []
    for r in conn.execute(
            "SELECT campaign_id, MAX(campaign_name) campaign_name, "
            "MAX(status) state, MAX(budget) budget, SUM(impressions) impressions, "
            "SUM(clicks) clicks, SUM(spend) spend, SUM(ad_orders) orders, "
            "SUM(ad_sales) sales FROM ads_campaign_daily "
            "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=? "
            "GROUP BY campaign_id",
            (workspace_id, marketplace, start, end)):
        out.append(dict(r))
    return out


def term_rows(config_path, workspace_id, marketplace):
    """Stored search terms, in _row() shape.

    ppc_search_terms calls the campaign `campaign`; dr_ppc reads
    `campaign_name`. Renamed here rather than in either of them, because the
    table's column and the checker's key are both already right for their own
    side and neither should be bent to suit the other.
    """
    from domain import ppc_view as _pv
    out = []
    for r in _pv.load_rows(config_path, workspace_id, marketplace):
        d = dict(r)
        d["campaign_name"] = d.get("campaign") or ""
        out.append(d)
    return out


def creds_or_why(workspace_id, config_path=None):
    """(creds, None) when this account can call the API, (None, reason) when not.

    One place, because sync(), request_reports() and collect_pending() all ask
    the same question and three copies of it would drift.
    """
    cfg = _settings.read_raw(config_path) if config_path else _settings.read_raw()
    acc = next((a for a in cfg.get("accounts", [])
                if a.get("id") == workspace_id), None)
    if acc is None:
        return None, {"ok": False, "error": "No such account: %s" % workspace_id}
    creds = _ads.creds_for(cfg, acc)
    gaps = _ads.missing(creds)
    if gaps:
        return None, {"ok": False, "connected": False, "missing": gaps,
                      "error": "%s is not connected to the Advertising API. "
                               "Still needed: %s"
                               % (workspace_id, ", ".join(gaps))}
    return creds, None


def sync(workspace_id, marketplace="UK", days=30, wait=300, config_path=None,
         on_wait=None):
    """Pull both DAILY reports for this account and store them, WAITING for them.

    This is the by-hand path -- someone pressed Refresh and is watching. The
    background job uses request_reports()/collect_pending() instead, because
    Amazon takes 9-14 minutes to build a daily report and nothing scheduled
    should sit still that long.

    A report that has not arrived by `wait` is NOT lost: its id is written to
    ads_report_jobs and the next collect picks it up. That is the difference
    between a slow refresh and a wasted one.

    Returns a dict a screen or a log can render directly. Never raises: a failed
    sync has to be able to say WHY, and "not connected" and "connected but the
    report failed" need different answers.
    """
    creds, why = creds_or_why(workspace_id, config_path)
    if why:
        return why

    cfg = _settings.read_raw(config_path) if config_path else _settings.read_raw()
    acc = next((a for a in cfg.get("accounts", [])
                if a.get("id") == workspace_id), {})
    products = products_for(cfg, acc)

    start, end = window(days)
    fetched_at = dt.datetime.now().isoformat(timespec="seconds")
    conn = _db.get_db(config_path)
    out = {"ok": True, "workspace_id": workspace_id, "marketplace": marketplace,
           "profile_id": creds["ads_profile_id"], "start": start, "end": end,
           "written": {}, "errors": [], "ad_products": list(products)}

    for kind in kinds_for(products):
        got = _rows_for(creds, marketplace, kind, start, end, wait, on_wait)
        if not got.get("ok"):
            # STILL BUILDING IS NOT A FAILURE. Hand the id to the collector so
            # the work Amazon has already done is not thrown away because a
            # person stopped watching.
            if got.get("pending") and got.get("report_id"):
                _job_add(conn, workspace_id, marketplace, kind,
                         got["report_id"], start, end)
                conn.commit()
            out["errors"].append({"kind": kind,
                                  "error": got.get("error") or "unknown",
                                  "report_id": got.get("report_id"),
                                  "pending": bool(got.get("pending"))})
            out["ok"] = False
            continue

        rows = got.get("rows") or []
        stored = store_rows(conn, workspace_id, marketplace, kind, rows,
                            fetched_at, window=(start, end),
                            config_path=config_path)
        out["written"][kind] = {"report_rows": len(rows), "stored": stored,
                                "report_id": got.get("report_id")}
    conn.commit()

    # TELL THE APP THE DATA IS THERE. Every ad figure on every screen is gated
    # on data_availability, which is a CACHED row, not a count of this table --
    # so storing rows without this leaves the whole app saying "not connected"
    # while 705 rows of real spend sit in the database. Measured exactly that
    # way on the first live pull.
    _mark_available(conn, config_path, workspace_id, marketplace, out)
    return out


def _mark_available(conn, config_path, workspace_id, marketplace, out=None):
    """TELL THE APP THE DATA IS THERE.

    Every ad figure on every screen is gated on data_availability, which is a
    CACHED row and not a count of the table -- so storing rows without this
    leaves the whole app saying "not connected" while hundreds of rows of real
    spend sit in the database. Measured exactly that way on the first live pull.
    """
    from domain import sales_data as _sd
    _sd.refresh_availability(conn, workspace_id, marketplace, "ads")
    av = _sd.availability(config_path, workspace_id, marketplace).get("ads")
    if out is not None:
        out["availability"] = av
    return av


# ---------------------------------------------------------------------------
# THE BACKGROUND PATH: ask now, collect later
# ---------------------------------------------------------------------------
#
# A daily report took between 9 and 14 minutes to build on the first live pull,
# and both of the first two attempts timed out at 7 minutes with the report
# still PENDING. Nothing on a schedule can hold still for that, so the work is
# split in two and the report id is the handoff:
#
#     request_reports()   asks Amazon, writes the ids, returns in seconds
#     collect_pending()   picks up whatever has finished since
#
# The scheduler calls collect first and then request, so one pass always banks
# the previous pass's work before commissioning more. Nothing is lost if a pass
# is missed, the process restarts, or the machine reboots: the ids are on disk.


def _job_add(conn, workspace_id, marketplace, kind, report_id, start, end):
    conn.execute(
        "INSERT OR IGNORE INTO ads_report_jobs (workspace_id, marketplace, "
        "kind, report_id, start_date, end_date, status, attempts, requested_at) "
        "VALUES (?,?,?,?,?,?,'pending',0,?)",
        (workspace_id, marketplace, kind, str(report_id), start, end,
         dt.datetime.now().isoformat(timespec="seconds")))


def _job_finish(conn, row_id, status, error=None):
    conn.execute(
        "UPDATE ads_report_jobs SET status=?, error=?, collected_at=? "
        "WHERE id=?",
        (status, (str(error)[:400] if error else None),
         dt.datetime.now().isoformat(timespec="seconds"), row_id))


def pending_jobs(config_path=None, workspace_id=None):
    """Reports Amazon is still building, oldest first."""
    conn = _db.get_db(config_path)
    sql = ("SELECT * FROM ads_report_jobs WHERE status='pending'")
    args = []
    if workspace_id:
        sql += " AND workspace_id=?"
        args.append(workspace_id)
    return [dict(r) for r in conn.execute(sql + " ORDER BY id", args)]


def request_reports(workspace_id, marketplace="UK", days=30, config_path=None):
    """Commission the reports and return at once. Stores nothing but the ids.

    This is the half a scheduled job can afford to run.
    """
    creds, why = creds_or_why(workspace_id, config_path)
    if why:
        return why
    cfg = _settings.read_raw(config_path) if config_path else _settings.read_raw()
    acc = next((a for a in cfg.get("accounts", [])
                if a.get("id") == workspace_id), {})
    products = products_for(cfg, acc)

    start, end = window(days)
    conn = _db.get_db(config_path)
    out = {"ok": True, "workspace_id": workspace_id, "marketplace": marketplace,
           "start": start, "end": end, "ad_products": list(products),
           "requested": [], "errors": []}
    for kind in kinds_for(products):
        try:
            rid = _ads.report_request(creds, marketplace, kind, start, end,
                                      time_unit_for(kind))
        except Exception as e:
            # A report product that Amazon rejects must be VISIBLE, not skipped.
            # Sponsored Brands and Display columns have never been verified
            # against a live response, so this is the most likely thing to fail
            # and the least useful thing to swallow.
            out["errors"].append({"kind": kind,
                                  "ad_product": _ads.ad_product_of(kind),
                                  "error": str(e)[:400]})
            out["ok"] = False
            continue
        _job_add(conn, workspace_id, marketplace, kind, rid, start, end)
        out["requested"].append({"kind": kind, "report_id": rid,
                                 "ad_product": _ads.ad_product_of(kind)})
    conn.commit()
    return out


def collect_pending(config_path=None, workspace_id=None, limit=12):
    """Download and store every commissioned report that has finished.

    Never waits. A report still building is left exactly as it was for the next
    pass; only its attempt count moves. One that has been asked about
    _JOB_MAX_ATTEMPTS times is marked expired rather than retried forever,
    because a report that has not arrived after that many passes is not coming
    and an ever-growing attempts count hides the failure.
    """
    conn = _db.get_db(config_path)
    jobs = pending_jobs(config_path, workspace_id)[:limit]
    out = {"ok": True, "checked": len(jobs), "collected": [], "still_building": 0,
           "failed": [], "errors": []}
    if not jobs:
        return out

    fetched_at = dt.datetime.now().isoformat(timespec="seconds")
    touched = set()
    creds_cache = {}
    for j in jobs:
        ws, mkt = j["workspace_id"], j["marketplace"]
        if ws not in creds_cache:
            creds_cache[ws] = creds_or_why(ws, config_path)
        creds, why = creds_cache[ws]
        if why:
            _job_finish(conn, j["id"], "failed", why.get("error"))
            out["failed"].append({"report_id": j["report_id"],
                                  "error": why.get("error")})
            continue

        conn.execute("UPDATE ads_report_jobs SET attempts=attempts+1 WHERE id=?",
                     (j["id"],))
        try:
            st = _ads.report_status(creds, mkt, j["report_id"])
        except Exception as e:
            out["errors"].append({"report_id": j["report_id"], "error": str(e)[:300]})
            continue

        s = (st.get("status") or "").upper()
        if s in ("FAILURE", "FAILED", "CANCELLED"):
            _job_finish(conn, j["id"], "failed", st.get("failure") or s)
            out["failed"].append({"report_id": j["report_id"], "kind": j["kind"],
                                  "error": st.get("failure") or s})
            continue
        if s not in ("COMPLETED", "SUCCESS") or not st.get("url"):
            if (j["attempts"] or 0) + 1 >= _JOB_MAX_ATTEMPTS:
                _job_finish(conn, j["id"], "expired",
                            "still %s after %d checks" % (s or "pending",
                                                          _JOB_MAX_ATTEMPTS))
                out["failed"].append({"report_id": j["report_id"],
                                      "kind": j["kind"], "error": "expired"})
            else:
                out["still_building"] += 1
            continue

        try:
            rows = _ads.report_download(st["url"])
        except Exception as e:
            out["errors"].append({"report_id": j["report_id"], "error": str(e)[:300]})
            continue

        stored = store_rows(conn, ws, mkt, j["kind"], rows, fetched_at,
                            window=(j.get("start_date") or "",
                                    j.get("end_date") or ""),
                            config_path=config_path)
        _job_finish(conn, j["id"], "done")
        touched.add((ws, mkt))
        out["collected"].append({"report_id": j["report_id"], "kind": j["kind"],
                                 "workspace_id": ws, "marketplace": mkt,
                                 "report_rows": len(rows), "stored": stored})
    conn.commit()

    for ws, mkt in touched:
        _mark_available(conn, config_path, ws, mkt)
    out["refreshed"] = [{"workspace_id": w, "marketplace": m} for w, m in touched]
    return out
