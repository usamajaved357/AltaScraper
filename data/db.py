"""data/db.py -- the SQLite file, its tables, and how to connect.

WHERE THE DATABASE LIVES -- read this before changing it
Beside config.json, NOT inside data/ next to the code.

The migration brief specified data/altascraper.db. That is fine locally and
destroys your data on Render: the container is rebuilt from the repo on every
deploy, so anything written next to the code is wiped. config.json already lives
on the persistent disk (CONFIG_PATH=/data/...), which is why users.json and
live_snapshots.json are written beside it. The database is far more valuable than
either, so it follows the same rule.

ALTASCRAPER_DB overrides the path outright if you ever need it elsewhere.

CONCURRENCY
WAL (write-ahead logging) so background sync jobs can write while the dashboard
reads, instead of the two blocking each other. busy_timeout means a writer that
finds the file locked waits rather than immediately raising "database is locked".
Connections are per-thread: SQLite connections cannot be shared across threads,
and Flask serves with threaded=True.
"""
import os
import sqlite3
import threading

_LOCAL = threading.local()
_INIT_LOCK = threading.Lock()
_INITIALISED = set()

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    seller_id TEXT,
    marketplace TEXT DEFAULT 'UK',
    account_config TEXT,
    google_spreadsheet_id TEXT,
    sp_api_config TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Products WAITING to be generated: the generator's INPUT.
--
-- This is the last thing that had to be read live from Google Sheets. Reading it
-- live meant no listing could be started without Google being reachable and the
-- sheet being shared correctly. Now the sheet is IMPORTED on demand -- you press
-- a button, the rows land here, and nothing reads Google again until you press it
-- again. The sheet stays exactly as you use it today; it just stops being a
-- dependency.
--
-- `raw` keeps the original row as it arrived. Column names in these sheets vary
-- (ebay_link vs ebay_url, delivery_time vs handling_time) and the normalised
-- columns below are a best reading of them -- keeping the original means a
-- mis-read column can be diagnosed later instead of being lost on import.
CREATE TABLE IF NOT EXISTS input_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    row_index INTEGER,
    amazon_url TEXT,
    competitor_asin TEXT,
    ebay_url TEXT,
    item_name TEXT,
    source_cost TEXT,
    selling_price TEXT,
    handling_time TEXT,
    upc TEXT,
    raw TEXT,
    imported_at TEXT,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_input_ws ON input_products(workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_input_ws_row
    ON input_products(workspace_id, row_index);

CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    competitor_asin TEXT,
    source_url TEXT,
    upc TEXT,
    platform TEXT,
    buy_box_price REAL,
    our_price REAL,
    amazon_fees REAL,
    fee_source TEXT,
    profit REAL,
    margin_pct REAL,
    roi_pct REAL,
    viable TEXT,
    product_type TEXT,
    amazon_category TEXT,
    subcategory TEXT,
    voc_source TEXT,
    voc_review_count TEXT,
    target_demographic TEXT,
    pain_points TEXT,
    purchase_trigger TEXT,
    title TEXT,
    bullet_1 TEXT,
    bullet_2 TEXT,
    bullet_3 TEXT,
    bullet_4 TEXT,
    bullet_5 TEXT,
    description_html TEXT,
    search_terms TEXT,
    autocomplete_keywords TEXT,
    material TEXT,
    colour TEXT,
    size TEXT,
    number_of_items TEXT,
    target_gender TEXT,
    age_range TEXT,
    compliance_notes TEXT,
    handling_time TEXT,
    handling_days TEXT,
    status TEXT DEFAULT 'NEEDS_REVIEW',
    date_processed TEXT,
    brand TEXT,
    model_number TEXT,
    notes TEXT,
    compliance_risk TEXT,
    ip_risk TEXT,
    attributes_json TEXT,
    item_highlights TEXT,
    api_payload_json TEXT,
    listing_marketplace TEXT DEFAULT 'UK',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, sku)
);

CREATE TABLE IF NOT EXISTS sync_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    workspace_id TEXT,
    status TEXT DEFAULT 'pending',
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    result TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitor_asins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    asin TEXT NOT NULL,
    marketplace TEXT DEFAULT 'UK',
    last_checked TIMESTAMP,
    seller_count INTEGER,
    sellers_json TEXT,
    alerts_json TEXT,
    UNIQUE(workspace_id, asin, marketplace)
);

CREATE TABLE IF NOT EXISTS ppc_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    campaign_name TEXT,
    campaign_type TEXT,
    asin TEXT,
    sku TEXT,
    budget REAL,
    bid REAL,
    status TEXT,
    data_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

/* The dashboard's commonest reads: every listing in a workspace, and the
   status counts down the side. Without these SQLite scans the whole table. */
CREATE INDEX IF NOT EXISTS idx_listings_ws        ON listings(workspace_id);
CREATE INDEX IF NOT EXISTS idx_listings_ws_status ON listings(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_listings_sku       ON listings(sku);
CREATE INDEX IF NOT EXISTS idx_listings_asin      ON listings(competitor_asin);
CREATE INDEX IF NOT EXISTS idx_syncjobs_type      ON sync_jobs(job_type, workspace_id);
"""


def db_path(config_path=None):
    """Where the database file lives. Beside config.json unless overridden."""
    env = os.environ.get("ALTASCRAPER_DB")
    if env:
        return env
    cfg = config_path or os.environ.get("CONFIG_PATH", "config.json")
    return os.path.join(os.path.dirname(os.path.abspath(str(cfg))), "altascraper.db")


def get_db(config_path=None):
    """A connection for THIS thread, with the schema guaranteed to exist.

    Per-thread because a SQLite connection object cannot be shared across
    threads, and the app serves with threaded=True plus background jobs.
    """
    path = db_path(config_path)
    conn = getattr(_LOCAL, "conn", None)
    if conn is not None and getattr(_LOCAL, "path", None) == path:
        return conn

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")       # readers never block the writer
    conn.execute("PRAGMA synchronous=NORMAL")     # durable enough, much faster
    conn.execute("PRAGMA busy_timeout=30000")     # wait for a lock, don't raise
    conn.execute("PRAGMA foreign_keys=ON")

    with _INIT_LOCK:
        if path not in _INITIALISED:
            conn.executescript(SCHEMA)
            _INITIALISED.add(path)

    _LOCAL.conn, _LOCAL.path = conn, path
    return conn


def close_db():
    """Close this thread's connection. Used by tests and worker shutdown."""
    conn = getattr(_LOCAL, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    _LOCAL.conn = None
    _LOCAL.path = None


def healthy(config_path=None):
    """Can we actually read the database? For the /health endpoint."""
    try:
        get_db(config_path).execute("SELECT 1 FROM listings LIMIT 1").fetchone()
        return True
    except Exception:
        return False


def stats(config_path=None):
    """Row counts per table, for diagnostics."""
    out = {}
    conn = get_db(config_path)
    for t in ("workspaces", "listings", "sync_jobs", "monitor_asins", "ppc_campaigns"):
        try:
            out[t] = conn.execute("SELECT COUNT(*) AS n FROM %s" % t).fetchone()["n"]
        except Exception:
            out[t] = None
    out["path"] = db_path(config_path)
    return out
