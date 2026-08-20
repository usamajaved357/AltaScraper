"""domain/keyword_store.py -- where keyword data accumulates, and nothing else.

WHAT THIS IS FOR
Phase 1 of the analytics plan. The app can already ASK Amazon for keyword data
(domain/brand_analytics.py: fetch_search_terms, fetch_sqp_for_asin) and show it.
What it could not do is REMEMBER it, so "which of my keywords moved this week"
had no answer -- every pull replaced the last one and the history was gone.

Every manual search writes here. Nothing else does. There is no scheduler, no
background worker and no cron: history accumulates because somebody used the
tool, which is exactly what was asked for. That means the history is uneven --
weeks nobody searched are simply absent -- and the screens say so rather than
drawing a line through a gap as though it were a measurement.

ITS OWN SCHEMA, ON THE SHARED DATABASE
The connection comes from data/db.py, because there should be one database and
one place that knows how to open it. The TABLES are created here, on first use,
rather than added to data/db.py's SCHEMA -- this is a new tool and the brief was
to add one without editing the existing ones.

TWO WORDS THIS FILE REFUSES TO USE LOOSELY
The plan's schema names `click_share` and `conversion_share`. In Amazon's Brand
Analytics those are specific things: the share of ALL clicks (or purchases) for
a search query that went to one ASIN, across every seller. NEITHER of the two
functions this reads from returns them:

    fetch_search_terms  -> {term, rank, asin1, asin2, asin3}
    fetch_sqp_for_asin  -> {query, impressions, clicks, cart_adds, purchases}

From SQP you can compute clicks/impressions and purchases/clicks, but those are
OUR click-through and conversion rates -- how our own listing performed with the
people who saw it. They are not a share of anything, and a 40% CTR is not 40% of
the market. Storing one under the other's name would make every later comparison
wrong in a way nobody could see.

So the RAW COUNTS are stored, because they are what Amazon actually said, and
the rates are computed for display and labelled CTR and CVR. If Amazon's real
click-share fields ever become available, they get their own columns.
"""
import datetime as _dt

from data import db as _db

SCHEMA = """
-- MARKETPLACE SEARCH TERMS: one row per term per report week.
-- This is the whole-marketplace view -- what people search for and which ASINs
-- they click -- so it is not per-seller data, but it IS pulled with a seller's
-- credentials and cached per account so one account's quota is not spent for
-- another's screen.
CREATE TABLE IF NOT EXISTS keyword_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    keyword TEXT NOT NULL,
    search_frequency_rank INTEGER,       -- 1 = most searched. Amazon's own rank.
    top_asin_1 TEXT,
    top_asin_2 TEXT,
    top_asin_3 TEXT,
    report_start TEXT NOT NULL,          -- YYYY-MM-DD, the report week
    report_end TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'search_terms',   -- which pull produced it
    seed TEXT,                           -- what the user typed to find it
    created_at TEXT NOT NULL
);
-- One row per term per week per account. A repeated search must UPDATE rather
-- than pile up duplicates, or the history doubles every time somebody looks.
CREATE UNIQUE INDEX IF NOT EXISTS idx_kwdata_unique
    ON keyword_data(workspace_id, marketplace, keyword, report_start, source);
CREATE INDEX IF NOT EXISTS idx_kwdata_scope
    ON keyword_data(workspace_id, marketplace, report_start);
CREATE INDEX IF NOT EXISTS idx_kwdata_kw
    ON keyword_data(workspace_id, keyword);

-- SEARCH QUERY PERFORMANCE: one row per query per ASIN per week.
-- RAW COUNTS ONLY -- see the note at the top of this file about why there is no
-- click_share column.
CREATE TABLE IF NOT EXISTS keyword_asin_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    asin TEXT NOT NULL,
    query TEXT NOT NULL,
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    cart_adds INTEGER DEFAULT 0,
    purchases INTEGER DEFAULT 0,
    report_start TEXT NOT NULL,
    report_end TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kwasin_unique
    ON keyword_asin_data(workspace_id, marketplace, asin, query, report_start);
CREATE INDEX IF NOT EXISTS idx_kwasin_scope
    ON keyword_asin_data(workspace_id, marketplace, asin, report_start);

-- THE WATCH LIST: keyword + ASIN pairs somebody chose to follow.
-- Just the list. What was measured for them lives in rank_tracking.
CREATE TABLE IF NOT EXISTS rank_watch (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    keyword TEXT NOT NULL,
    asin TEXT NOT NULL,
    added_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rankwatch_unique
    ON rank_watch(workspace_id, marketplace, keyword, asin);

-- WHAT A CHECK FOUND.
--
-- organic_position IS DELIBERATELY LEFT NULL. Nothing available here can measure
-- it: SP-API has no organic-rank endpoint, and the brief rules out scraping
-- search results (rightly -- it is against Amazon's terms and the accounts at
-- risk are real selling accounts). The column exists so a real rank source can
-- fill it later without a migration, and until then it stays empty rather than
-- being filled with something else wearing its name.
--
-- What IS measured is the SQP signal for that keyword and ASIN in that week --
-- impressions, clicks, purchases. That is search VISIBILITY, not position, and
-- the screen says so.
CREATE TABLE IF NOT EXISTS rank_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    keyword TEXT NOT NULL,
    asin TEXT NOT NULL,
    organic_position INTEGER,            -- always NULL for now; see above
    sponsored_position INTEGER,          -- needs the Ads API; NULL until then
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    purchases INTEGER DEFAULT 0,
    report_start TEXT,                   -- the SQP week the signal came from
    checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ranktrack_scope
    ON rank_tracking(workspace_id, marketplace, keyword, asin, checked_at);
"""

_READY = set()


def _conn(config_path=None):
    """The shared connection, with THIS tool's tables guaranteed to exist."""
    c = _db.get_db(config_path)
    key = id(c)
    if key not in _READY:
        c.executescript(SCHEMA)
        _READY.add(key)
    return c


def _now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- writes
def save_search_terms(ws, mkt, rows, start, end, seed="", config_path=None):
    """Store a Keyword Spy pull. Returns how many rows were written.

    UPSERT, not insert. Searching the same seed twice in a week is normal and
    must not double the history -- the second pull is the same week's truth,
    possibly refreshed, so it replaces rather than accumulates.
    """
    if not rows:
        return 0
    c = _conn(config_path)
    now = _now()
    n = 0
    for r in rows:
        kw = str(r.get("term") or "").strip()
        if not kw:
            continue
        c.execute("""
            INSERT INTO keyword_data
                (workspace_id, marketplace, keyword, search_frequency_rank,
                 top_asin_1, top_asin_2, top_asin_3,
                 report_start, report_end, source, seed, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,'search_terms',?,?)
            ON CONFLICT(workspace_id, marketplace, keyword, report_start, source)
            DO UPDATE SET
                search_frequency_rank = excluded.search_frequency_rank,
                top_asin_1 = excluded.top_asin_1,
                top_asin_2 = excluded.top_asin_2,
                top_asin_3 = excluded.top_asin_3,
                report_end = excluded.report_end,
                seed       = excluded.seed
        """, (ws, mkt, kw, int(r.get("rank") or 0) or None,
              r.get("asin1") or "", r.get("asin2") or "", r.get("asin3") or "",
              start, end, seed, now))
        n += 1
    return n


def save_sqp(ws, mkt, asin, rows, start, end, config_path=None):
    """Store an ASIN Insights pull. Raw counts only -- see the header."""
    if not rows:
        return 0
    c = _conn(config_path)
    now = _now()
    n = 0
    for r in rows:
        q = str(r.get("query") or "").strip()
        if not q:
            continue
        c.execute("""
            INSERT INTO keyword_asin_data
                (workspace_id, marketplace, asin, query, impressions, clicks,
                 cart_adds, purchases, report_start, report_end, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(workspace_id, marketplace, asin, query, report_start)
            DO UPDATE SET
                impressions = excluded.impressions,
                clicks      = excluded.clicks,
                cart_adds   = excluded.cart_adds,
                purchases   = excluded.purchases,
                report_end  = excluded.report_end
        """, (ws, mkt, asin, q, int(r.get("impressions") or 0),
              int(r.get("clicks") or 0), int(r.get("cart_adds") or 0),
              int(r.get("purchases") or 0), start, end, now))
        n += 1
    return n


# ---------------------------------------------------------------- watch list
def watch_add(ws, mkt, keyword, asin, config_path=None):
    c = _conn(config_path)
    c.execute("""INSERT OR IGNORE INTO rank_watch
                 (workspace_id, marketplace, keyword, asin, added_at)
                 VALUES (?,?,?,?,?)""",
              (ws, mkt, keyword.strip(), asin.strip().upper(), _now()))
    return True


def watch_remove(ws, mkt, keyword, asin, config_path=None):
    c = _conn(config_path)
    c.execute("""DELETE FROM rank_watch WHERE workspace_id=? AND marketplace=?
                 AND keyword=? AND asin=?""",
              (ws, mkt, keyword.strip(), asin.strip().upper()))
    return True


def watch_list(ws, mkt, config_path=None):
    c = _conn(config_path)
    rows = c.execute("""SELECT keyword, asin, added_at FROM rank_watch
                        WHERE workspace_id=? AND marketplace=?
                        ORDER BY keyword, asin""", (ws, mkt)).fetchall()
    return [dict(r) for r in rows]


def save_rank_check(ws, mkt, keyword, asin, sig, start=None, config_path=None):
    """Record what a manual check found for one keyword+ASIN.

    organic_position is not passed and not written: see the schema note.
    """
    c = _conn(config_path)
    c.execute("""INSERT INTO rank_tracking
                 (workspace_id, marketplace, keyword, asin,
                  impressions, clicks, purchases, report_start, checked_at)
                 VALUES (?,?,?,?,?,?,?,?,?)""",
              (ws, mkt, keyword, asin,
               int((sig or {}).get("impressions") or 0),
               int((sig or {}).get("clicks") or 0),
               int((sig or {}).get("purchases") or 0),
               start, _now()))
    return True


def rank_history(ws, mkt, keyword=None, asin=None, limit=500, config_path=None):
    c = _conn(config_path)
    q = """SELECT keyword, asin, impressions, clicks, purchases,
                  organic_position, report_start, checked_at
           FROM rank_tracking WHERE workspace_id=? AND marketplace=?"""
    args = [ws, mkt]
    if keyword:
        q += " AND keyword=?"; args.append(keyword)
    if asin:
        q += " AND asin=?"; args.append(asin.upper())
    q += " ORDER BY checked_at DESC LIMIT ?"
    args.append(int(limit))
    return [dict(r) for r in c.execute(q, args).fetchall()]


# ---------------------------------------------------------------- reads
def weeks_available(ws, mkt, config_path=None):
    """Which report weeks this account actually has, newest first.

    The screens need this because the history is uneven by design -- it only
    holds weeks somebody searched in. Offering a date picker that spans weeks
    with no data would invite comparisons against nothing.
    """
    c = _conn(config_path)
    rows = c.execute("""SELECT report_start, report_end, COUNT(*) AS n
                        FROM keyword_data WHERE workspace_id=? AND marketplace=?
                        GROUP BY report_start, report_end
                        ORDER BY report_start DESC""", (ws, mkt)).fetchall()
    return [dict(r) for r in rows]


def keywords_for_week(ws, mkt, start, q="", limit=500, config_path=None):
    c = _conn(config_path)
    sql = """SELECT keyword, search_frequency_rank, top_asin_1, top_asin_2,
                    top_asin_3, report_start, report_end, seed
             FROM keyword_data
             WHERE workspace_id=? AND marketplace=? AND report_start=?"""
    args = [ws, mkt, start]
    if q:
        sql += " AND keyword LIKE ?"
        args.append("%" + q.strip().lower() + "%")
    sql += " ORDER BY COALESCE(search_frequency_rank, 999999999) ASC LIMIT ?"
    args.append(int(limit))
    return [dict(r) for r in c.execute(sql, args).fetchall()]


def compare_weeks(ws, mkt, this_start, prev_start, q="", limit=400,
                  config_path=None):
    """Week over week, by search frequency rank.

    RANK IS BACKWARDS AND THAT IS THE WHOLE TRAP: 1 is the most searched term,
    so a rank that FALLS is a keyword that ROSE. `moved` is therefore
    prev - now, so a positive number means "more searched than last time" --
    which is what a person means by "up" and is not what the raw numbers say.

    A keyword present in only one of the two weeks is returned with the other
    side None and is NOT counted as a movement. With manual-only collection, an
    absent week usually means nobody searched that week, not that the keyword
    vanished -- calling that a 100% drop would be inventing a finding.
    """
    now_rows = {r["keyword"]: r for r in
                keywords_for_week(ws, mkt, this_start, q, limit, config_path)}
    prev_rows = {r["keyword"]: r for r in
                 keywords_for_week(ws, mkt, prev_start, q, limit, config_path)}
    out = []
    for kw in sorted(set(now_rows) | set(prev_rows)):
        a = now_rows.get(kw)
        b = prev_rows.get(kw)
        ra = (a or {}).get("search_frequency_rank")
        rb = (b or {}).get("search_frequency_rank")
        moved = (rb - ra) if (ra and rb) else None
        out.append({
            "keyword": kw,
            "rank_now": ra, "rank_prev": rb,
            "moved": moved,
            "only_in": None if (a and b) else ("now" if a else "prev"),
            "top_asin_1": (a or b or {}).get("top_asin_1") or "",
        })
    # Biggest real movers first; keywords present in only one week sink to the
    # bottom rather than topping a chart they cannot be compared on.
    out.sort(key=lambda r: (r["moved"] is None, -abs(r["moved"] or 0)))
    return out


def stored_counts(ws, mkt, config_path=None):
    """What this account has accumulated, for the empty states to be honest."""
    c = _conn(config_path)

    def _one(sql):
        r = c.execute(sql, (ws, mkt)).fetchone()
        return (r[0] if r else 0) or 0

    return {
        "keywords": _one("SELECT COUNT(*) FROM keyword_data "
                         "WHERE workspace_id=? AND marketplace=?"),
        "weeks": _one("SELECT COUNT(DISTINCT report_start) FROM keyword_data "
                      "WHERE workspace_id=? AND marketplace=?"),
        "asin_queries": _one("SELECT COUNT(*) FROM keyword_asin_data "
                             "WHERE workspace_id=? AND marketplace=?"),
        "watched": _one("SELECT COUNT(*) FROM rank_watch "
                        "WHERE workspace_id=? AND marketplace=?"),
        "checks": _one("SELECT COUNT(*) FROM rank_tracking "
                       "WHERE workspace_id=? AND marketplace=?"),
    }
