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

-- SALES AND TRAFFIC, one row per day per ASIN.
--
-- asin '*' is the account+marketplace TOTAL for that day. Amazon reports the
-- total separately from the per-ASIN breakdown and the two do not always add up
-- (ASINs delisted mid-period, orders with no ASIN attribution), so the total is
-- stored as Amazon gives it rather than summed on read. A dashboard that quietly
-- disagrees with Seller Central by two percent is worse than no dashboard.
--
-- Daily grain ONLY. Weekly and monthly are rolled up when read. Storing three
-- grains means three things to keep in step, and they drift.
CREATE TABLE IF NOT EXISTS sales_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    date TEXT NOT NULL,                 -- YYYY-MM-DD
    asin TEXT NOT NULL DEFAULT '*',     -- the CHILD asin: the thing that sells
    parent_asin TEXT,                   -- kept so variations can be grouped later
    units INTEGER,
    units_b2b INTEGER,
    orders INTEGER,
    order_items INTEGER,
    ordered_sales REAL,
    ordered_sales_b2b REAL,
    sessions INTEGER,
    sessions_mobile INTEGER,
    sessions_browser INTEGER,
    page_views INTEGER,
    buy_box_pct REAL,
    unit_session_pct REAL,             -- Amazon's conversion rate
    avg_selling_price REAL,
    currency TEXT,
    fetched_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_key
    ON sales_daily(workspace_id, marketplace, date, asin);
CREATE INDEX IF NOT EXISTS idx_sales_range ON sales_daily(workspace_id, marketplace, date);

-- ADVERTISING, same shape, deliberately separate.
--
-- Ad data does NOT come from SP-API -- it is the Amazon Advertising API, a
-- different API with its own authorisation, and this app has no connection to
-- it. Today rows arrive from an uploaded Sponsored Products report; when the API
-- is connected it fills the SAME table and only `source` changes. Shaping it now
-- means connecting the API later is a data-source swap, not a rebuild.
CREATE TABLE IF NOT EXISTS ads_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    date TEXT NOT NULL,
    asin TEXT NOT NULL DEFAULT '*',
    impressions INTEGER,
    clicks INTEGER,
    spend REAL,
    ad_orders INTEGER,
    ad_sales REAL,
    source TEXT,                        -- 'upload' now, 'ads_api' later
    fetched_at TEXT,
    -- WHICH KIND OF ADVERTISING. Amazon sells three and they are separate
    -- products with separate reports: SPONSORED_PRODUCTS, SPONSORED_BRANDS,
    -- SPONSORED_DISPLAY. Without this column they share a key, so pulling
    -- Brands would OVERWRITE the day's Sponsored Products figures instead of
    -- adding to them -- the same silent-overwrite the campaign fold already had
    -- to fix once. It is part of the unique key for that reason.
    ad_product TEXT NOT NULL DEFAULT 'SPONSORED_PRODUCTS'
);
/* The unique key is created by _migrate, NOT here. This script runs against
   databases that already have ads_daily WITHOUT ad_product -- CREATE TABLE IF
   NOT EXISTS leaves them alone -- and an index naming a column that does not
   exist yet fails the whole script. _migrate adds the column first, then builds
   the key, and does the same thing on a brand new database. See
   _REPLACED_INDEXES. */

/* WHAT EACH CAMPAIGN SPENT, PER DAY.
   -----------------------------------------------------------------------
   ads_daily answers "what did advertising cost this account, and which
   PRODUCTS did it sell". It cannot answer "which CAMPAIGN is wasting money",
   because a campaign is not a product: one campaign advertises many ASINs and
   one ASIN is advertised by many campaigns. Folding campaigns into ads_daily
   would destroy exactly the breakdown a campaign table is for.

   So this is the campaign grain, kept beside it rather than inside it, in the
   same shape for the same reasons: one row per campaign per day, a unique key
   so a re-sync corrects rather than doubles, and `source` so an API pull can be
   told from an uploaded report.

   ppc_campaigns is NOT this table and is not being extended into it. That one
   holds the campaign BUILDER's output -- a campaign someone is composing, with
   its bid and its target ASIN -- and has no date and no metrics. Two different
   questions, and merging them would leave a table where half the rows are
   proposals and half are history.

   status and budget come from the report, not from a campaign-list call:
   Amazon retired the v2 campaign endpoints (HTTP 404) and the v3 replacement is
   a POST that api/amazon_ads.py refuses by design (Rule 8, no campaign writes).
   The spCampaigns report carries campaignStatus and campaignBudgetAmount, so
   nothing is lost by reading them there. */
CREATE TABLE IF NOT EXISTS ads_campaign_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    date TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    campaign_name TEXT,
    status TEXT,
    budget REAL,
    impressions INTEGER,
    clicks INTEGER,
    spend REAL,
    ad_orders INTEGER,
    ad_sales REAL,
    source TEXT,
    fetched_at TEXT,
    ad_product TEXT NOT NULL DEFAULT 'SPONSORED_PRODUCTS'
);
/* Unique key built by _migrate, for the same reason as ads_daily's. */
CREATE INDEX IF NOT EXISTS idx_adscamp_ws
    ON ads_campaign_daily(workspace_id, marketplace, date);

/* WHERE THE AD APPEARED, per campaign per day.
   -----------------------------------------------------------------------
   Top of search, a product page, or the rest of Amazon. Two campaigns spending
   the same amount are not making the same buy if one sits at the top of search
   and the other on a competitor's product page, and nothing here could tell
   them apart.

   ITS OWN TABLE, NOT A COLUMN ON ads_campaign_daily. Adding `placement` there
   would multiply every existing row by four and silently double, triple or
   quadruple every figure any current screen reads from it -- the two-grain
   mistake that already cost this app once, where the account total sits at
   asin='*' beside the per-product rows and summing both returns exactly twice
   the truth. A separate table cannot be summed by accident.

   NO HOURLY EQUIVALENT EXISTS. Amazon refuses timeUnit HOURLY for this report
   type and for spCampaigns and spAdvertisedProduct -- asked on 6 Sep 2026 and
   refused with "configuration timeUnit is not supported for this report type".
   The daily grain is not a simplification; it is the finest grain there is. */
CREATE TABLE IF NOT EXISTS ads_placement_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace  TEXT NOT NULL,
    date         TEXT NOT NULL,
    campaign_id  TEXT NOT NULL,
    campaign_name TEXT,
    placement    TEXT NOT NULL,      -- Amazon's placementClassification, as sent
    impressions  INTEGER,
    clicks       INTEGER,
    spend        REAL,
    ad_orders    INTEGER,
    ad_sales     REAL,
    ad_product   TEXT NOT NULL DEFAULT 'SPONSORED_PRODUCTS',
    source       TEXT,
    fetched_at   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_adsplace_key
    ON ads_placement_daily(workspace_id, marketplace, date, campaign_id,
                           placement, ad_product);
CREATE INDEX IF NOT EXISTS idx_adsplace_ws
    ON ads_placement_daily(workspace_id, marketplace, date);

/* WHAT WAS TARGETED, per targeting per campaign per day.
   -----------------------------------------------------------------------
   The keyword or product target that won the auction, and its MATCH TYPE.

   THIS IS THE ONLY PLACE MATCH TYPE EXISTS AT A DAILY GRAIN, and that is the
   whole reason for the table. The Campaign Analytics page draws spend split by
   match type as a donut and as a stacked area BY DAY, and the spec is explicit
   about where that comes from: "Data from daily targeting-level reports
   (keyword/target grain), NOT search term report".

   The distinction matters and is not pedantry. ppc_search_terms also carries a
   match_type, but it is the SEARCH TERM report -- privacy-thresholded, so
   low-volume queries are suppressed and its spend is short of the billed
   ledger. Measured on the same account, the spec's own reconciliation: campaign
   reports 11,768, search terms 11,703. Splitting a donut by a source that is
   missing spend Amazon actually charged would draw a chart whose slices do not
   add up to the total printed beside them.

   ITS OWN TABLE, for the same reason ads_placement_daily has one: a targeting
   column on ads_campaign_daily would multiply every existing row and silently
   double every figure the current screens read. Four grains -- account,
   per-ASIN, per-campaign, per-placement -- already hold the SAME money cut four
   ways, and this is a fifth. Nothing may ever add two of them together.

   ASKED FOR AND MEASURED, 7 Sep 2026: spTargeting at timeUnit DAILY is accepted
   and returns match_type and date -- 8,505 rows over 7 days on nestwell_goods.
   Auto campaigns come back with match_type TARGETING_EXPRESSION_PREDEFINED and
   the predicate (close-match, loose-match, substitutes, complements) in the
   keyword column, exactly as the spec says they do. */
CREATE TABLE IF NOT EXISTS ads_targeting_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace  TEXT NOT NULL,
    date         TEXT NOT NULL,
    campaign_id  TEXT NOT NULL,
    campaign_name TEXT,
    ad_group     TEXT,
    keyword      TEXT,               -- keywordText, or the auto predicate
    match_type   TEXT,               -- EXACT | PHRASE | BROAD |
                                     -- TARGETING_EXPRESSION[_PREDEFINED]
    impressions  INTEGER,
    clicks       INTEGER,
    spend        REAL,
    ad_orders    INTEGER,
    ad_sales     REAL,
    ad_product   TEXT NOT NULL DEFAULT 'SPONSORED_PRODUCTS',
    source       TEXT,
    fetched_at   TEXT
);
/* The key includes keyword AND match_type: one campaign runs the same word on
   more than one match type on the same day, and they are different buys. */
CREATE UNIQUE INDEX IF NOT EXISTS idx_adstarget_key
    ON ads_targeting_daily(workspace_id, marketplace, date, campaign_id,
                           ad_group, keyword, match_type, ad_product);
CREATE INDEX IF NOT EXISTS idx_adstarget_ws
    ON ads_targeting_daily(workspace_id, marketplace, date);

/* REPORTS AMAZON IS STILL BUILDING.
   -----------------------------------------------------------------------
   An advertising report is not fetched, it is COMMISSIONED: you ask, Amazon
   builds it, and you come back for it. Measured on the first live pull, a DAILY
   report took between 9 and 14 minutes to become available.

   That is far too long to hold a background job open, and much too long to hold
   a web request. So the sync is two passes: one asks and writes the report id
   here, a later one collects whatever has finished. Nothing blocks, and a job
   that dies between the two loses nothing -- the id is on disk and the next
   pass finds it.

   A row is deleted once collected. What stays is a row that failed or expired,
   because a report that never arrived is a thing someone has to be told about,
   and a silently vanishing job is how "the PPC numbers are stale" becomes
   nobody's problem. */
CREATE TABLE IF NOT EXISTS ads_report_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    kind TEXT NOT NULL,              -- 'campaign' | 'advertised_product'
    report_id TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    status TEXT DEFAULT 'pending',   -- pending | done | failed | expired
    attempts INTEGER DEFAULT 0,
    error TEXT,
    requested_at TEXT,
    collected_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_adsjob_report
    ON ads_report_jobs(report_id);
CREATE INDEX IF NOT EXISTS idx_adsjob_pending
    ON ads_report_jobs(status, workspace_id);

/* EVERY SEARCH TERM AMAZON CHARGED FOR, KEPT.
   -----------------------------------------------------------------------
   domain/ppc_module.py has ingested SP Search Term Reports since it was
   written -- it detects the family, normalises the columns and hands back
   canonical rows. What it never did was KEEP them: /ppc/harvest turned an
   upload into three CSVs and threw the rows away, so the app could act on a
   report once and could never show you what it said.

   That is the whole reason the PPC screens had nothing to draw. The
   Advertising API is a separate OAuth from SP-API, and on 18 Aug 2026 it was
   connected on NO account (measured: ads_daily 0 rows, ppc_campaigns 0 rows, no
   credentials anywhere) -- but the Search Term Report is downloadable from
   Seller Central by hand, and every metric on Orbit's PPC screens except the
   intraday tracker is computable from it alone.

   THAT CHANGED, AND PER ACCOUNT. Measured 6 Sep 2026: nestwell_goods has an
   advertising login, 1,410 rows in ads_daily and 8,514 stored search terms,
   pulled by the API rather than uploaded; the other five accounts have neither
   credentials nor rows. So this table is still the right home for an uploaded
   report, and it is no longer the ONLY way figures get in. Nothing here reads
   differently -- `source` records which -- but a reader should not be told the
   API is unconnected when for one account it is.

   ONE ROW PER (report, search term, match type, campaign, ad group). The same
   term appears many times across a report -- once per targeting that triggered
   it -- and collapsing them on the way in would throw away the match-type
   breakdown, which is most of what the screen is for.

   `report_id` groups an upload so a later one can replace it wholesale rather
   than double every figure. */
/* EVERY RETURN, KEPT.
   -----------------------------------------------------------------------
   domain/returns_view.py has parsed returns since it was written -- it detects
   which report a file is, normalises the columns and de-duplicates overlapping
   windows. What it never did was KEEP them: routes/returns_routes.py holds the
   parsed rows in a per-workspace dict in MEMORY, so a restart loses them and the
   export says "load the file again". Exactly the shape of the search-term bug --
   the app could act on a report once and could never show you what it said
   afterwards.

   AND AMAZON CAPS THE REPORT AT 60 DAYS. Year-to-date is four or five downloads
   whose windows overlap, so history is only possible if it is accumulated. That
   is the whole reason for a table rather than a longer cache.

   THE KEY IS returns_view.identity(), NOT A NEW ONE.
   That function already decides what makes two rows the same return, and it was
   measured against a real 11,509-row file: keying on Amazon's licence plate
   alone silently deleted 467 genuine returns because Amazon recycles them. The
   key it settled on is stored here as `identity` -- one string, built by that
   function -- so the table cannot disagree with the merge that feeds it
   (CLAUDE.md Rule 12).

   `kind` is part of that identity. An FBA return and a seller-fulfilled return
   are never the same event -- Amazon either handled it or you did.

   disposition and comment are FBA-only and stay NULL on a seller-fulfilled
   return. NULL, not "": Amazon never graded it and never recorded a comment,
   which is a different fact from "it came back undamaged with nothing said". */
CREATE TABLE IF NOT EXISTS returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id  TEXT NOT NULL,
    marketplace   TEXT NOT NULL,
    identity      TEXT NOT NULL,       -- returns_view.identity(), joined
    kind          TEXT,                -- 'mfn' | 'fba'
    date          TEXT,                -- return request date
    order_id      TEXT,
    license_plate TEXT,
    asin          TEXT,
    sku           TEXT,
    name          TEXT,
    qty           INTEGER,
    reason        TEXT,                -- normalised
    reason_raw    TEXT,                -- exactly what Amazon wrote
    nature        TEXT,
    status        TEXT,                -- Amazon's return request status
    resolution    TEXT,
    refunded      REAL,
    order_amount  REAL,
    category      TEXT,
    disposition   TEXT,                -- FBA only
    comment       TEXT,                -- FBA only
    source        TEXT,                -- 'report' | 'upload'
    first_seen    TEXT,
    fetched_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_returns_identity
    ON returns(workspace_id, marketplace, identity);
CREATE INDEX IF NOT EXISTS idx_returns_scope
    ON returns(workspace_id, marketplace, date);
CREATE INDEX IF NOT EXISTS idx_returns_order
    ON returns(workspace_id, order_id);

/* EVERY MESSAGE THIS APP SENT TO A BUYER.
   -----------------------------------------------------------------------
   An outward-facing action with no record of it is not acceptable: a message
   to a customer cannot be unsent, and "did we already reply to them?" has to be
   answerable months later, by someone who was not there.

   Amazon does not give the messages back. getMessagingActionsForOrder says what
   MAY be sent, never what WAS -- so if this app does not write it down, nothing
   does.

   The body is stored verbatim. A log that keeps only "a message was sent" is
   the version of this that gets trusted and should not be: the whole question
   is usually what was actually said.

   Failures are kept too, with Amazon's own words in `error`. A message that was
   refused is a thing somebody has to know about, and a log of successes only
   would show a customer as contacted when they were not. */
/* WHERE THE PARCEL IS.
   -----------------------------------------------------------------------
   AMAZON DOES NOT GIVE BACK THE TRACKING YOU UPLOAD. Measured, not assumed:

       getOrder                     no tracking number, no carrier. It carries
                                    OrderStatus, NumberOfItemsShipped/Unshipped,
                                    ShipServiceLevel and the ship-by dates
       getOrderItems                QuantityShipped only
       All Orders report            33 columns, none of them tracking or carrier
       MerchantFulfillment          get_shipment needs a shipmentId, and SP-API
                                    publishes no "list my shipments" call -- so
                                    it can read back a label THIS app bought and
                                    cannot discover tracking for anything else

   So the number has to come from the seller, the same way the per-order costs
   do: a sheet out, a sheet back. `source` records which -- 'upload' for that,
   'amazon' for a label bought through Amazon Buy Shipping, so the two can never
   be confused.

   THE CARRIER'S STATUS IS A SEPARATE QUESTION AND A SEPARATE FAILURE.
   `status` is what the carrier last said; `checked_at` is when it was asked.
   Those two together are the whole difference between "delivered" and "it said
   delivered four days ago and nobody has asked since". A status with no
   checked_at beside it is a claim about the present made from the past.

   `raw_status` keeps the carrier's own wording. Every carrier invents its own
   vocabulary -- "Delivered", "DELIVERED", "Signed for", "Parcel delivered" --
   and mapping them onto a common word loses information the seller sometimes
   needs. Both are kept: the mapped one to group by, the original to read. */
/* THE Dr PPC CONSOLE'S OWN STORE.

   Three things live here that Amazon has no opinion about: the plan the
   operator writes, the rules that decide which lane a search term belongs to,
   and the record of what was decided. All of it is this business's own
   judgement, which is why none of it can be derived and all of it has to be
   kept.

   A PLAN IS A CHAIN OF IMMUTABLE REVISIONS, NOT A ROW THAT GETS EDITED.

       "Every save creates an immutable revision. Only an activated revision is
        approved strategy."

   That is the whole design and it is worth honouring exactly. A plan decides
   what the analyst is allowed to propose and what a scheduled run measures
   against; if it could be edited in place then a proposal made last week could
   not be explained, because the thing it was made against would be gone. So a
   save writes a NEW revision and activation is a separate act -- a draft is not
   strategy until somebody says it is.

   `body` is the whole plan as JSON: identity, the markdown strategy document,
   the goals and the budget allocations. One column rather than six tables
   because the plan is read and written whole, and because its shape is still
   settling -- a schema per field would have to be migrated every time a goal
   grows an attribute. */
CREATE TABLE IF NOT EXISTS drppc_plans (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace  TEXT,
    revision     INTEGER NOT NULL,      -- 1, 2, 3... per workspace+marketplace
    status       TEXT NOT NULL,         -- 'draft' | 'active' | 'superseded'
    title        TEXT,
    period_start TEXT,
    period_end   TEXT,
    body         TEXT,                  -- the whole plan, as JSON
    created_at   TEXT,
    created_by   TEXT,
    activated_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_drppc_plan_rev
    ON drppc_plans(workspace_id, marketplace, revision);
CREATE INDEX IF NOT EXISTS idx_drppc_plan_status
    ON drppc_plans(workspace_id, marketplace, status);

/* WHICH LANE A SEARCH TERM BELONGS TO, and on whose authority.

   Branded and non-branded spend are judged completely differently -- paying to
   appear on your own name is defensive, paying to appear on a category term is
   prospecting -- and Amazon does not tell you which is which. Somebody has to
   decide, and the decision has to be reviewable afterwards, which is what
   `rationale` and `source` are for.

   PRIORITY ORDERS THE MATCHES, and every match stays visible. A term can be
   caught by more than one rule, and hiding the losers would make a
   classification impossible to argue with. The screen shows all of them.

   `evidence` is what the pattern is matched against -- a search term today, a
   campaign id or an ad group later -- so the same table can hold the exact
   campaign assignments the console also wants without a second one. */
CREATE TABLE IF NOT EXISTS drppc_rules (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace  TEXT,
    lane         TEXT NOT NULL,         -- 'branded' | 'non_branded' | 'unclassified'
    evidence     TEXT NOT NULL,         -- 'search_term' | 'campaign_id' | 'ad_group'
    match_type   TEXT NOT NULL,         -- 'contains' | 'exact' | 'starts_with' | 'regex'
    pattern      TEXT NOT NULL,
    priority     INTEGER NOT NULL DEFAULT 100,
    rationale    TEXT,
    source       TEXT,                  -- 'reviewed' | 'imported'
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT,
    created_by   TEXT
);
CREATE INDEX IF NOT EXISTS idx_drppc_rules_ws
    ON drppc_rules(workspace_id, marketplace, active, priority);

/* THE APPEND-ONLY LEDGER, for the events that have nowhere else to live.

   MOST OF THE CONSOLE'S HISTORY IS NOT KEPT HERE, AND THAT IS DELIBERATE.
   A plan revision already carries its own created_at, created_by and
   activated_at; a lane rule carries the same; a sync run is a row in sync_jobs.
   Copying any of those into a second table would create two records of one fact
   that can disagree, which is exactly what Rule 12 exists to prevent. The
   Activity page DERIVES those from the rows that already hold them.

   What lands here is the rest: a setting changed, an execution mode changed, a
   proposal accepted or rejected -- things that alter what the console will do
   and leave no other trace. Nothing is ever updated or deleted; a correction is
   a new row, because a ledger that can be edited is not evidence of anything.

   NOTHING IN THIS TABLE REACHES AMAZON. It records what was decided here. */
/* ONE-OFF JOBS THAT HAVE ALREADY BEEN DONE.
   -----------------------------------------------------------------------
   Not schema migrations -- _migrate() handles those, and they are safe to
   re-run because adding a column that exists is a no-op. This is for jobs that
   change DATA, where running twice is not harmless.

   The one that needed it: seeding the per-product cost store from the numbers
   that used to be read out of SKUs. Re-running it after somebody DELETED a cost
   they had decided was wrong would put it straight back, which is the opposite
   of what they asked for. So it is recorded here and never repeats. */
CREATE TABLE IF NOT EXISTS app_migrations (
    name      TEXT PRIMARY KEY,
    ran_at    TEXT NOT NULL,
    detail    TEXT
);

CREATE TABLE IF NOT EXISTS drppc_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace  TEXT,
    at           TEXT NOT NULL,           -- ISO timestamp, when it happened
    kind         TEXT NOT NULL,           -- plan|observation|decision|action|
                                          -- execution|verification|system
    actor        TEXT NOT NULL,           -- human|analyst|scheduler|system|
                                          -- admin_assisted|external
    action       TEXT NOT NULL,           -- the short verb, e.g. 'settings_saved'
    title        TEXT NOT NULL,
    detail       TEXT,
    entity_type  TEXT,
    entity_id    TEXT,
    who          TEXT                     -- the person, when there was one
);
CREATE INDEX IF NOT EXISTS idx_drppc_events_ws
    ON drppc_events(workspace_id, marketplace, at);

/* THE COSTS AMAZON KNOWS NOTHING ABOUT, and the one Amazon charges but attaches
   to no order.

   The P&L is built from what Amazon reports, and Amazon reports nothing about
   the accountant, the software, the postage bought elsewhere or the packaging.
   A profit figure that leaves those out is not a business's profit, and no
   amount of care with fees fixes that.

   IT ALSO CATCHES THE ONE REAL CHARGE THE ORDER-JOINED QUERIES CANNOT SEE.
   Measured on nestwell_goods: the per-order fees come to 1.28 of "other" while
   the account was actually charged 61.28. The missing 60.00 is the monthly
   selling subscription, which Amazon posts against the ACCOUNT and not against
   any sale -- so a query that joins fees to orders can never find it. domain/
   pnl.py has reported it as an unattributed fixed cost since the fee work; this
   is where it stops being a note and starts being subtracted.

   MONTHLY, WITH A START AND AN OPTIONAL END, rather than one row per month.
   A subscription of 30.00 a month entered once should appear in March, April
   and May without being retyped, and should STOP appearing when it is
   cancelled. `starts` and `ends` are dates; `ends` NULL means "still running".
   One-offs are entered with starts == ends.

   THE AMOUNT IS PER MONTH and is apportioned by day across whatever window the
   P&L is asked for, because a P&L for 12 days of a month should not carry a
   whole month's rent. domain/expenses.py owns that arithmetic. */
CREATE TABLE IF NOT EXISTS manual_expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace  TEXT,               -- NULL = the whole account, every market
    name         TEXT NOT NULL,      -- "Amazon selling subscription"
    category     TEXT,               -- free text, for grouping on screen
    amount       REAL NOT NULL,      -- per month, in `currency`
    currency     TEXT,
    starts       TEXT NOT NULL,      -- YYYY-MM-DD, the first month it applies
    ends         TEXT,               -- NULL while it is still being charged
    note         TEXT,
    created_at   TEXT,
    updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_manexp_ws
    ON manual_expenses(workspace_id, marketplace, starts);

CREATE TABLE IF NOT EXISTS order_tracking (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id    TEXT NOT NULL,
    marketplace     TEXT NOT NULL,
    order_id        TEXT NOT NULL,
    sku             TEXT,                -- a multi-line order can ship separately
    carrier         TEXT,                -- as the seller wrote it
    carrier_code    TEXT,                -- normalised, for the lookup
    tracking_number TEXT NOT NULL,
    status          TEXT,                -- mapped: in_transit, delivered, ...
    raw_status      TEXT,                -- the carrier's own words
    last_event      TEXT,                -- the newest scan, in words
    last_event_at   TEXT,                -- when that scan happened
    checked_at      TEXT,                -- when WE last asked the carrier
    check_error     TEXT,                -- why the last check failed, if it did
    source          TEXT,                -- 'upload' | 'amazon'
    added_at        TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tracking_key
    ON order_tracking(workspace_id, marketplace, order_id, tracking_number);
CREATE INDEX IF NOT EXISTS idx_tracking_order
    ON order_tracking(workspace_id, order_id);
CREATE INDEX IF NOT EXISTS idx_tracking_status
    ON order_tracking(workspace_id, status);

CREATE TABLE IF NOT EXISTS buyer_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace  TEXT NOT NULL,
    order_id     TEXT NOT NULL,
    action       TEXT NOT NULL,       -- Amazon's own action name
    body         TEXT,                -- exactly what was sent
    ok           INTEGER,             -- 1 sent, 0 refused
    error        TEXT,                -- Amazon's words when it refused
    sent_by      TEXT,                -- which user pressed send
    sent_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_buyermsg_order
    ON buyer_messages(workspace_id, order_id);
CREATE INDEX IF NOT EXISTS idx_buyermsg_when
    ON buyer_messages(workspace_id, sent_at);

CREATE TABLE IF NOT EXISTS ppc_search_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace  TEXT NOT NULL,
    report_id    TEXT NOT NULL,
    date_from    TEXT,
    date_to      TEXT,
    search_term  TEXT NOT NULL,
    keyword      TEXT,                   -- the targeting that triggered it
    match_type   TEXT,
    campaign     TEXT,
    ad_group     TEXT,
    impressions  INTEGER,
    clicks       INTEGER,
    spend        REAL,
    sales        REAL,
    orders       INTEGER,
    units        INTEGER,
    uploaded_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_pst_scope
    ON ppc_search_terms(workspace_id, marketplace, report_id);
CREATE INDEX IF NOT EXISTS idx_pst_term
    ON ppc_search_terms(workspace_id, marketplace, search_term);

/* The brand's own words, so branded spend can be told from non-branded.
   Amazon does not report this split -- the seller says which terms are theirs
   and everything else follows. Orbit does the same thing with its "Add brand
   term..." box, and it is the single most useful cut on the whole screen:
   paying to appear on your own name is defensive, and mixing it in makes a
   healthy-looking ACOS out of money that was never winning new customers. */
CREATE TABLE IF NOT EXISTS ppc_brand_terms (
    workspace_id TEXT NOT NULL,
    term         TEXT NOT NULL,
    added_at     TEXT,
    PRIMARY KEY (workspace_id, term)
);

/* THE WEEKLY KPI PACK, one row per week, FROZEN.

   Replaces a Google Sheet where the current week held live formulas over two
   source tabs and every earlier week held numbers pasted by hand. That design
   is why the sheet was wrong in two ways at once when it was read on
   18 Aug 2026:

     * the "current" week showed the previous week's figures to the cent,
       because the freeze happened and the source tabs were never refreshed;
     * CPA read $7.70 in the frozen columns and $27.26 in the live one -- the
       formula had been corrected at some point, so the history was computed a
       different way from the present and the row was not comparable at all.

   A week is written ONCE, from the reports that describe that week, and never
   recomputed. That is the whole point: last week cannot change because this
   week's formula changed. `payload` holds the finished pack as JSON so a later
   change to the arithmetic cannot silently rewrite history either -- if the
   maths improves, it applies to new weeks and the old ones still say what was
   reported at the time.

   PRIMARY KEY on (workspace, marketplace, week_start) so re-uploading the same
   week corrects it rather than duplicating it. */
CREATE TABLE IF NOT EXISTS weekly_kpi (
    workspace_id TEXT NOT NULL,
    marketplace  TEXT NOT NULL,
    week_start   TEXT NOT NULL,          -- YYYY-MM-DD, the Sunday
    week_end     TEXT NOT NULL,
    payload      TEXT NOT NULL,          -- the finished pack, as JSON
    source       TEXT,                   -- 'upload' or 'api'
    built_at     TEXT,
    PRIMARY KEY (workspace_id, marketplace, week_start)
);
CREATE INDEX IF NOT EXISTS idx_wkpi_scope
    ON weekly_kpi(workspace_id, marketplace, week_start DESC);

/* HOW MUCH STOCK THERE WAS, ON EACH DAY.
 *
 * Amazon does not keep this for a merchant-fulfilled seller. It reports what
 * stock is there NOW; the history is gone the moment it changes. Without it,
 * "how fast does this sell" can only be answered by dividing units by days --
 * and that counts every day the product was OUT OF STOCK as a day it sold
 * nothing, which understates real demand by exactly the amount that matters.
 *
 * So the quantity is recorded each time the live catalogue is refreshed, which
 * already happens on a timer. One row per SKU per day; the LAST reading of a
 * day wins, because what matters for "was it sellable today" is whether it ran
 * out, and a re-check later in the day is the better evidence.
 *
 * This starts empty. The metrics that need it say so rather than guessing --
 * a velocity computed over two days of history is not a velocity.
 */
CREATE TABLE IF NOT EXISTS stock_daily (
    workspace_id TEXT NOT NULL,
    marketplace  TEXT NOT NULL,
    date         TEXT NOT NULL,          -- YYYY-MM-DD
    sku          TEXT NOT NULL,
    asin         TEXT,
    qty          INTEGER,                -- NULL means Amazon did not say
    status       TEXT,                   -- Active / Inactive / Incomplete
    fulfillment  TEXT,                   -- DEFAULT (merchant) / AMAZON (FBA)
    recorded_at  TEXT,
    PRIMARY KEY (workspace_id, marketplace, date, sku)
);
CREATE INDEX IF NOT EXISTS idx_stock_daily_scope
    ON stock_daily(workspace_id, marketplace, sku, date DESC);

-- WHAT AMAZON TOOK, AND WHAT WENT BACK TO BUYERS.
--
-- From the Finances API (listFinancialEvents), which is a different thing from
-- the Sales & Traffic report: that one says what was ORDERED, this says what was
-- actually CHARGED and REFUNDED once the money moved. The two never agree
-- exactly and are not meant to -- an order placed on the 1st and refunded on the
-- 9th is revenue on the 1st and a refund on the 9th.
--
-- FEES ARE STORED POSITIVE. Amazon sends them negative, because from its side
-- they are money leaving. On a screen "Amazon fees: 3.00" is what a person
-- means, and a column that is sometimes negative and sometimes not is the kind
-- of thing that silently flips a profit calculation.
--
-- Financial events are keyed by SELLER SKU, not ASIN. The SKU is mapped to an
-- ASIN through the live catalogue snapshot where one exists; where it does not,
-- the row still lands on the account total (asin '*') so the headline figures
-- stay right even when a SKU cannot be attributed. A fee that cannot be placed
-- against a product is still a fee you paid.
CREATE TABLE IF NOT EXISTS finance_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    date TEXT NOT NULL,
    asin TEXT NOT NULL DEFAULT '*',
    referral_fees REAL,                 -- Amazon's commission
    fba_fees REAL,                      -- fulfilment, storage, weight-based
    other_fees REAL,                    -- everything else Amazon charged
    refunds REAL,                       -- principal returned to buyers
    refund_units INTEGER,
    refund_fees_returned REAL,          -- the part of the fee Amazon gave back
    reimbursements REAL,                -- money Amazon paid back for its own errors
    promos REAL,                        -- discounts you funded
    principal REAL,                     -- what buyers were charged, per Finances
    tax REAL,                           -- VAT/tax Amazon reported ON TOP of principal
    refund_tax REAL,                    -- tax handed back with a refund
    units INTEGER,                      -- units shipped, on the SAME basis as the fees
    cogs REAL,                          -- what those units cost, where the cost is known
    cogs_units INTEGER,                 -- how many of the units had a known cost
    currency TEXT,
    source TEXT,                        -- 'finances_api' | 'settlement' later
    fetched_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_finance_key
    ON finance_daily(workspace_id, marketplace, date, asin);
CREATE INDEX IF NOT EXISTS idx_finance_range
    ON finance_daily(workspace_id, marketplace, date);

-- WHAT DATES ACTUALLY HAVE DATA.
--
-- Asked BEFORE any data is requested. Amazon delivers sales with a lag and never
-- has today, so without this the dashboard draws empty columns for days that were
-- never going to exist and looks broken. Reading it first is the difference
-- between "no data yet for 12 Aug" and a chart that appears to say sales were nil.
CREATE TABLE IF NOT EXISTS data_availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    source TEXT NOT NULL,               -- 'sales' | 'ads'
    first_date TEXT,
    last_date TEXT,
    days INTEGER,
    fetched_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_avail_key
    ON data_availability(workspace_id, marketplace, source);

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
-- ---- RETIRED, BUT STILL CREATED. -----------------------------------------
--
-- Nothing writes here any more. A product waiting to be generated is a row in
-- `listings` with status=QUEUED, written by data/queued_store.add_queued from
-- either of the two ways in (the CSV upload, or the "Add a product" form). One
-- table, one source of truth: queued, generated and live are the same kind of
-- thing at different stages, and the generator reads QUEUED rows from the same
-- place it writes its results back to.
--
-- THE TABLE IS STILL CREATED, DELIBERATELY, and the brief asked for the
-- opposite. Commenting this out was tried and is wrong, for one reason:
-- scripts/migrate_statuses.py does not DELETE a migrated queue row, it marks it
-- source="migrated:<original>" so a move that turns out wrong can still be
-- read. That promise cannot be kept on a database where the table does not
-- exist -- and on a fresh database every reader of it raises "no such table"
-- instead of finding it empty.
--
-- What actually retires a table is nothing writing to it, which is now true.
-- An empty table costs a few bytes; a missing one costs the ability to look at
-- what was moved.
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
    -- WHAT AMAZON SAID BACK. api_payload_json is the body we SENT; this is the
    -- issues array Amazon returned with it, kept structured (code, severity,
    -- message, attributeNames) rather than flattened into the Notes prose, so
    -- the listing page can show the failing field next to the field itself.
    api_issues_json TEXT,
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


/* ==========================================================================
   SOURCE REPRICER -- the supplier side of a listing.

   A SKU is only touched by the repricer if it has been ENROLLED. That is the
   blast radius control: the feature can ship to every account and still change
   nothing until a SKU is opted in, one at a time.
   ========================================================================== */

/* Which SKUs the repricer is allowed to act on, and how hard. */
CREATE TABLE IF NOT EXISTS sourcing_enrolment (
    workspace_id TEXT NOT NULL,
    marketplace  TEXT NOT NULL,
    sku          TEXT NOT NULL,
    enrolled     INTEGER DEFAULT 1,
    mode         TEXT DEFAULT 'dry_run',   -- 'dry_run' decides and logs; 'live' pushes
    added_at     TEXT,
    -- IS THE LISTING STILL ON AMAZON? 'ok', 'gone', or NULL for never checked.
    -- A SKU deleted in Seller Central stays enrolled here for ever otherwise, and
    -- the repricer goes on pricing something that cannot be bought. Six of
    -- jack_uk's 67 answered 404 GONE. NULL and 'gone' are deliberately different:
    -- one means nobody has looked.
    listing_state   TEXT,
    listing_checked TEXT,
    PRIMARY KEY (workspace_id, marketplace, sku)
);

/* The suppliers for one SKU. Several per SKU is the normal case. */
CREATE TABLE IF NOT EXISTS sourcing_sources (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    marketplace  TEXT NOT NULL,
    sku          TEXT NOT NULL,
    url          TEXT NOT NULL,
    kind         TEXT DEFAULT 'ebay',      -- 'ebay' (API) | 'html' (scraped)
    label        TEXT,
    priority     INTEGER DEFAULT 100,      -- lower wins ties; the user's own order
    enabled      INTEGER DEFAULT 1,
    /* A postage cost the supplier does not publish, typed once by the user.
       Unknown postage is not free postage -- without this the source is skipped
       for want of a cost, which is visible and fixable. Guessing is not. */
    shipping_override REAL,
    added_at     TEXT
);

/* Every check of a source. History, not just the latest, so a price that moves
   around can be seen moving rather than inferred from one reading. */
CREATE TABLE IF NOT EXISTS sourcing_checks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     INTEGER NOT NULL,
    checked_at    TEXT,
    status        TEXT,                    -- 'fetched' | 'gone' | 'failed'
    price         REAL,
    shipping      REAL,                    -- NULL means UNKNOWN, never free
    currency      TEXT,
    in_stock      INTEGER,                 -- 1 yes, 0 no, NULL unknown
    dispatch_days INTEGER,
    error         TEXT
);

/* Rules. One row per account is the default; a row with a sku overrides it for
   that SKU alone, so one awkward product cannot force the rest to be loosened. */
CREATE TABLE IF NOT EXISTS sourcing_rules (
    workspace_id         TEXT NOT NULL,
    marketplace          TEXT NOT NULL,
    sku                  TEXT NOT NULL DEFAULT '',   -- '' = the account default
    strategy             TEXT,
    require_in_stock     INTEGER,
    max_dispatch_days    INTEGER,
    handling_buffer_days INTEGER,
    min_margin_pct       REAL,
    -- TWO PERCENTAGE PROFIT TARGETS, on top of the flat min_profit, set
    -- independently and BOTH applied -- the price takes the highest floor.
    -- Margin is profit as a share of what the customer pays; ROI as a share of
    -- what you paid, and the two give very different prices from the same cost.
    -- NULL = that target is off.
    target_margin_pct    REAL,
    target_roi_pct       REAL,
    -- The single-target form these replaced. Still READ so an account that set
    -- one before there were two boxes keeps it; never written any more. See
    -- domain/sourcing.rule_with_defaults, which folds it into whichever of the
    -- two above it names.
    -- (min_margin_pct above is from the repricer's first draft and nothing
    --  reads it; left in place because dropping a column in SQLite rewrites the
    --  table for no gain.)
    profit_target_kind   TEXT,
    profit_target_pct    REAL,
    referral_rate        REAL,
    min_price            REAL,
    max_price            REAL,
    max_change_pct       REAL,
    min_change           REAL,
    stale_after_hours    REAL,
    in_stock_quantity    INTEGER,
    PRIMARY KEY (workspace_id, marketplace, sku)
);

/* Every decision, whether or not it was pushed. This is the answer to "why did
   my price change at 3am", and it has to survive being asked weeks later. */
CREATE TABLE IF NOT EXISTS sourcing_actions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id   TEXT NOT NULL,
    marketplace    TEXT NOT NULL,
    sku            TEXT NOT NULL,
    at             TEXT,
    action         TEXT,                   -- 'none' | 'update' | 'out_of_stock'
    source_id      INTEGER,
    from_price     REAL, to_price     REAL,
    from_quantity  INTEGER, to_quantity  INTEGER,
    from_lead_days INTEGER, to_lead_days INTEGER,
    reason         TEXT,
    blocked_by     TEXT,
    applied        INTEGER DEFAULT 0,      -- 0 dry run, 1 pushed, -1 push failed
    inputs_age_mins REAL
);

CREATE INDEX IF NOT EXISTS idx_srcsources_sku  ON sourcing_sources(workspace_id, marketplace, sku);
CREATE INDEX IF NOT EXISTS idx_srcchecks_src   ON sourcing_checks(source_id, checked_at);
CREATE INDEX IF NOT EXISTS idx_srcactions_sku  ON sourcing_actions(workspace_id, marketplace, sku, at);

-- THINGS THAT HAPPENED WHICH SOMEBODY SHOULD SEE.
--
-- The repricer used to HOLD a price change it thought too large and wait to be
-- noticed. Asked for the other way round:
--
--     "i dont want the app to hold the change if there is more than the max
--      change value, i just want it to send me the notification"
--
-- So the change goes through and a row lands here instead. That only works if
-- the record is durable: a toast is gone the moment the page is closed, and the
-- 4-hour run happens when nobody is looking.
--
-- READ STATE IS PER ROW, not a global "last seen" marker, so a notification
-- opened on a phone is still unread nowhere else and nothing is silently
-- skipped by a clock.
CREATE TABLE IF NOT EXISTS notifications(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id  TEXT,
    marketplace   TEXT,
    type          TEXT,      -- price_change | large_move | out_of_stock
                             -- | back_in_stock | supplier_ended | error
    sku           TEXT,
    title         TEXT,
    body          TEXT,
    is_read       INTEGER DEFAULT 0,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_notif_ws ON notifications(workspace_id, is_read, id);

-- WHAT AMAZON SAID IT WOULD TAKE, PER PRODUCT.
--
--     "get accurate fees from amazon per item"
--
-- The repricer priced every SKU at a flat 15%. Measured against what Amazon has
-- actually settled: jack_uk 17.5%, nestwell_goods 18.0%, selvora_limited 18.0%.
-- Every floor it computed was therefore too low, and a "20% ROI" was really
-- about 14%.
--
-- A RATE, NOT AN AMOUNT, AND THAT IS WHAT MAKES THIS WORKABLE. The fee depends
-- on the price and the repricer is computing the price, so asking for an amount
-- is circular. Amazon's referral fee is a PERCENTAGE by category, so the rate
-- implied by one quote holds at any price -- quote once, derive the rate, and
-- the circle is gone.
--
-- It is also what keeps the API usage sane: one call per product per week
-- instead of one per product per four-hour cycle. 67 SKUs would otherwise be
-- 67 calls every cycle against a limit Amazon enforces.
--
-- FBA IS DELIBERATELY NOT IN THE RATE. It is a per-unit figure that depends on
-- the item's size and weight band, not a share of the price, and it is genuinely
-- zero on a merchant-fulfilled order. Rolling it into a percentage would make
-- the rate wrong at every price except the one it was quoted at.
CREATE TABLE IF NOT EXISTS fee_quotes(
    workspace_id  TEXT NOT NULL,
    marketplace   TEXT NOT NULL,
    asin          TEXT NOT NULL,
    rate          REAL,          -- (referral + closing) / the price it was quoted at
    referral      REAL,
    closing       REAL,
    quoted_price  REAL,          -- kept so a reader can see what it was measured at
    currency      TEXT,
    quoted_at     TEXT,
    PRIMARY KEY (workspace_id, marketplace, asin)
);

-- THE GAP BETWEEN WHAT AMAZON QUOTES AND WHAT AMAZON TAKES, PER ACCOUNT.
--
-- The quote above answers with the referral and closing fee. That is not the
-- whole of what leaves the account. MEASURED on the same ASIN at the same
-- 34.99 price: Amazon quoted 5.25 and took 5.25 on jack_uk, and quoted 5.25
-- and took 6.30 on nestwell_goods -- more, on all eight of its settled orders.
-- Amazon charges VAT on its own fees to an account it has no VAT number for,
-- and a quote is the figure before that.
--
-- NOTHING HERE KNOWS THAT. The multiplier is actual / quoted, measured across
-- the products that have both, so it captures whatever Amazon adds -- fee VAT,
-- digital services tax, a per-order charge, a fee type invented next year. The
-- app never has to learn what those charges are called, and a constant written
-- into the code would have been a guess about a tax position that changes the
-- day a VAT number is registered.
--
-- STORED, NOT DERIVED ON EVERY READ, because the pricing path asks per SKU on
-- every draw of the screen. `orders_seen` and `quotes_seen` are what make it
-- self-correcting: they are the counts the figure was measured from, so one
-- more settled order or one more quote makes the stored answer no longer match
-- the data, and it is worked out again. No timer, no manual refresh, nothing
-- to remember to press.
CREATE TABLE IF NOT EXISTS fee_multipliers(
    workspace_id  TEXT NOT NULL,
    marketplace   TEXT NOT NULL,
    multiplier    REAL,          -- actual fees / what the quotes predicted
    samples       INTEGER,       -- products behind it (quote AND settled sales)
    actual_fees   REAL,          -- the money that actually left
    quoted_fees   REAL,          -- what the quotes said it would be
    orders_seen   INTEGER,       -- settled orders at the time of measuring
    quotes_seen   INTEGER,       -- quotes held at the time of measuring
    measured_at   TEXT,
    PRIMARY KEY (workspace_id, marketplace)
);

-- Every AI call the app makes, and what it cost.
--
-- One row per call, never aggregated on the way in: a total cannot be broken
-- down afterwards, and the question is always "which account, doing what".
--
-- workspace_id is "" when a call genuinely belongs to no account (a settings
-- test, a connection check). That is recorded as "" rather than guessed at,
-- and the screen reports it separately -- spend attributed to the wrong
-- account is worse than spend attributed to none.
CREATE TABLE IF NOT EXISTS ai_usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    at            TEXT NOT NULL,            -- 'YYYY-MM-DD HH:MM:SS', local
    day           TEXT NOT NULL,            -- 'YYYY-MM-DD', for grouping
    workspace_id  TEXT NOT NULL DEFAULT '',
    feature       TEXT NOT NULL,            -- what the user was doing
    provider      TEXT NOT NULL,            -- 'anthropic' | 'openrouter'
    model         TEXT NOT NULL DEFAULT '',
    kind          TEXT NOT NULL DEFAULT 'text',   -- 'text' | 'image' | 'vision'
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    images        INTEGER DEFAULT 0,
    -- NULL, not 0, when the price of this model is not known. A cost of zero
    -- for a call that certainly cost something is the one number that would
    -- make this dashboard worse than no dashboard.
    cost_usd      REAL,
    ok            INTEGER DEFAULT 1,
    error         TEXT DEFAULT '',
    sku           TEXT DEFAULT '',
    ms            INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_aiusage_day  ON ai_usage(day, workspace_id);
CREATE INDEX IF NOT EXISTS idx_aiusage_feat ON ai_usage(workspace_id, feature, day);

-- One line of one order, with the moment it was placed.
--
-- WHY THIS IS STORED AT ALL. The Hourly Sales screen answers "which hour of
-- which day does this product sell in", and Amazon has no report for it: the
-- Sales & Traffic report is daily, and the only per-hour source is the Orders
-- API, which needs ONE CALL PER ORDER to learn which ASIN was in it. Thirty
-- days of orders is thirty days of calls every time the screen is opened, and
-- SP-API is rate limited -- so each order is fetched once and kept.
--
-- purchase_date is stored as Amazon sends it, in UTC. The screen converts to
-- the marketplace's own zone, because an order placed at 11pm in London is an
-- evening sale, and storing a local time would make the rows unreadable the
-- moment the account sells in a second country.
CREATE TABLE IF NOT EXISTS order_lines (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id  TEXT NOT NULL,
    marketplace   TEXT NOT NULL,
    order_id      TEXT NOT NULL,
    purchase_date TEXT NOT NULL,          -- '2026-08-14T21:04:11Z', UTC
    asin          TEXT NOT NULL DEFAULT '',
    sku           TEXT NOT NULL DEFAULT '',
    title         TEXT NOT NULL DEFAULT '',
    units         INTEGER NOT NULL DEFAULT 0,
    revenue       REAL NOT NULL DEFAULT 0,
    currency      TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT '',
    fetched_at    TEXT NOT NULL DEFAULT ''
);
-- One row per line of an order: the same order id appears once per ASIN in it.
CREATE UNIQUE INDEX IF NOT EXISTS idx_orderlines_uniq
    ON order_lines(workspace_id, marketplace, order_id, asin, sku);
CREATE INDEX IF NOT EXISTS idx_orderlines_when
    ON order_lines(workspace_id, marketplace, purchase_date);

/* Costs that are not the supplier's price: postage you pay, prep, an advertising
   figure you allocate by hand. Asked for as "additional charges per asin, which
   can be sometimes my shipping price, my prep charges, my ads costs which i
   write manually".

   ONE ROW PER NAMED CHARGE, not one column per kind. The list of things a seller
   pays for is not fixed and never will be -- storage, relabelling, a courier
   surcharge, an inspection -- and a schema with a `prep_cost` column forces
   every future charge to be squeezed into a name that does not fit, or another
   migration. A row per charge also means the profit screen can show WHAT the
   costs were and not merely their total, which is the thing that makes a thin
   margin explainable.

   PER UNIT, because profit is worked out per unit sold. A charge that is really
   per shipment is entered as its per-unit share; saying so here is what stops it
   being guessed at later.

   effective_from lets a charge change without rewriting history: the row that
   applies to an order is the newest one dated on or before that order. Absent
   means "since always", which is what a first entry should mean. */
CREATE TABLE IF NOT EXISTS asin_charges (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id   TEXT NOT NULL,
    marketplace    TEXT NOT NULL,
    asin           TEXT NOT NULL DEFAULT '',
    sku            TEXT NOT NULL DEFAULT '',      -- '' = applies to the ASIN
    label          TEXT NOT NULL DEFAULT '',      -- 'postage', 'prep', 'ads'...
    amount         REAL NOT NULL DEFAULT 0,       -- per unit, in the account's currency
    effective_from TEXT NOT NULL DEFAULT '',      -- 'YYYY-MM-DD', '' = since always
    note           TEXT NOT NULL DEFAULT '',
    updated_at     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_asincharges_lookup
    ON asin_charges(workspace_id, marketplace, asin, sku);

/* WHAT AMAZON TOOK, AND WHICH ORDER IT TOOK IT FROM.
   finance_daily records the same money by DATE and ASIN, which answers "what
   moved this week" -- a cash question. It cannot answer "what did the orders I
   took last Tuesday earn", because the fee for Tuesday's order arrives whenever
   Amazon settles it, often weeks later and on a day with no sales of its own.

   That is why the P&L grid had two calendars in one column: sales dated by when
   the order was placed, fees dated by when the money moved, and no day where
   both appear. Measured on jack_uk: every money row fell on Jul 22 - Aug 12 and
   every sales row on Aug 14. Nothing lined up, and any arithmetic across them
   was wrong.

   Amazon does name the order on each event -- measured, 13 of 13 shipment
   events and 1 of 1 refunds -- so keeping that id lets each fee be reported on
   the date its ORDER was placed, and the whole grid becomes one calendar.

   KEYED BY POSTING DAY AS WELL AS ORDER. One order can be settled once and
   refunded later, on different days; a row per (order, day) means re-reading a
   window replaces exactly that window's rows and never double-counts, and never
   loses a refund that fell outside it. */
CREATE TABLE IF NOT EXISTS order_fees (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id  TEXT NOT NULL,
    marketplace   TEXT NOT NULL,
    order_id      TEXT NOT NULL,
    posted_date   TEXT NOT NULL,          -- when the money moved
    referral_fees REAL NOT NULL DEFAULT 0,
    fba_fees      REAL NOT NULL DEFAULT 0,
    other_fees    REAL NOT NULL DEFAULT 0,
    principal     REAL NOT NULL DEFAULT 0,   -- what the buyer was charged, ex VAT
    tax           REAL NOT NULL DEFAULT 0,   -- VAT, collected and owed onward
    refunds       REAL NOT NULL DEFAULT 0,
    refund_tax    REAL NOT NULL DEFAULT 0,
    refund_units  INTEGER NOT NULL DEFAULT 0,
    refund_fees_returned REAL NOT NULL DEFAULT 0,
    promos        REAL NOT NULL DEFAULT 0,
    units         INTEGER NOT NULL DEFAULT 0,
    currency      TEXT NOT NULL DEFAULT '',
    fetched_at    TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_orderfees_uniq
    ON order_fees(workspace_id, marketplace, order_id, posted_date);
CREATE INDEX IF NOT EXISTS idx_orderfees_order
    ON order_fees(workspace_id, marketplace, order_id);

-- Amazon's field definitions for one product type, kept between restarts.
--
-- These were held in memory only, so every restart threw them away and the app
-- fetched all of them from Amazon again -- 42 of them on one account, seconds
-- each, and each one spends quota. A product type's definition changes rarely
-- (Amazon revises them occasionally, not daily), so it is worth keeping.
--
-- Keyed by marketplace as well as type: the UK and US definitions of the same
-- product type are genuinely different documents, with different required
-- fields and different allowed values.
CREATE TABLE IF NOT EXISTS schema_cache (
    product_type  TEXT NOT NULL,
    marketplace   TEXT NOT NULL,
    payload       TEXT NOT NULL,          -- the parsed schema, as JSON
    fetched_at    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (product_type, marketplace)
);
"""


# Columns added to tables that already exist in the wild. CREATE TABLE IF NOT
# EXISTS does nothing to a table that is already there, so a column added to
# SCHEMA above never reaches a database created before it -- the app then fails
# on a machine that has been running longest, which is the worst place to find
# out. Each entry is (table, column, type); applying one twice is a no-op.
_ADDED_COLUMNS = [
    # THE DAY A SEARCH TERM'S SPEND HAPPENED, so the Search Terms page can
    # follow the date picker.
    #
    # The report was stored at REPORT-WINDOW grain: one batch covering
    # date_from..date_to, with no way to ask what happened on the Tuesday. That
    # was right when it was written -- the spec's own Critical Rule 2 says the
    # Search Term Report has no day breakdown -- and it is now known to be
    # avoidable. Measured against the live API on 7 Sep 2026: spSearchTerm with
    # timeUnit DAILY is ACCEPTED and returns a `date` column, 393 rows across 7
    # distinct dates on nestwell_goods. So the grain was a property of how the
    # report was ASKED FOR, not of the report.
    #
    # NULL ON EVERY ROW ALREADY STORED, and that is the honest value: a batch
    # covering thirty days cannot be split back into thirty days, and writing
    # date_from here would claim a month of spend happened on its first
    # morning. Rows with no date are reported at their window, as before; rows
    # with one can be summed for any window inside it.
    ("ppc_search_terms", "date", "TEXT"),
    # Opt-in, per listing, for the GTIN exemption. See column_map.py.
    ("listings", "gtin_exemption", "TEXT"),
    # WHETHER A SUPPLIER IS TRACKED YET, or is only attached to a draft.
    #
    #     "these suppliers should be added to the all orders page sources and in
    #      repricer when the listing goes live, not on draft, on draft the
    #      sources should stay on the drafts page"
    #
    # SUPPLIER 2 AND 3. "Source URL" is supplier 1 and already exists; these are
    # the ones the owner asked to be able to give:
    #
    #     "i said ask me for upto 3 suppliers in the template, i will add more
    #      suppliers if i have them"
    #
    # Without them the multi-supplier merge had exactly one link to work with on
    # the database backend, however many were pasted in. See column_map.py.
    ("listings", "supplier_2", "TEXT"),
    ("listings", "supplier_3", "TEXT"),
    # 'draft' while the listing is not buyable on Amazon; 'live' once it is.
    # Both states are the SAME row -- the links, their priority and every price
    # check already taken carry over on the flip, so nothing is re-fetched and
    # the drafts page keeps the full detail all along. NULL reads as 'live', so
    # every source enrolled before this column existed keeps behaving as it did.
    ("sourcing_sources", "stage", "TEXT"),
    # Amazon's own reply to the last Preview/Submit. In SCHEMA too; here so a
    # database that already exists gains it without being rebuilt.
    ("listings", "api_issues_json", "TEXT"),
    ("sales_daily", "parent_asin", "TEXT"),
    ("finance_daily", "units", "INTEGER"),
    ("finance_daily", "cogs", "REAL"),
    ("finance_daily", "cogs_units", "INTEGER"),
    ("finance_daily", "tax", "REAL"),
    ("finance_daily", "refund_tax", "REAL"),
    # COUPON AND DEAL FEES, OUT OF "other".
    #
    # Amazon charges a fee every time a coupon is redeemed and a flat fee to run
    # a Lightning or Best Deal. Both used to land in other_fees beside the
    # monthly subscription and the digital services fee, where they cannot be
    # told apart -- and they are the only ones in that bucket a seller can do
    # something about, because they are the price of a promotion that was a
    # choice.
    #
    # NULL, NOT 0, ON EVERY ROW ALREADY STORED. A row synced before this column
    # existed has its coupon fees inside other_fees, and writing 0.00 here would
    # claim they were measured at nothing. domain/pnl.py reports the line as
    # unknown for those windows rather than as nought.
    ("finance_daily", "promo_fees", "REAL"),
    ("order_fees", "promo_fees", "REAL"),
    ("sourcing_sources", "shipping_override", "REAL"),
    # The percentage profit target. In SCHEMA too, for databases created after
    # this; here so the ones that already exist gain it without being rebuilt.
    ("sourcing_rules", "profit_target_kind", "TEXT"),
    ("sourcing_rules", "profit_target_pct", "REAL"),
    # WHICH WAY A PRICE IS ALLOWED TO MOVE. 'up_only' | 'up_and_down' |
    # 'match_floor'; NULL means up_only, which is the default.
    #
    #     "Up only (DEFAULT) -- price can only increase. Never decreases even
    #      if supplier gets cheaper. Protects your market price."
    #
    # Left NULL rather than back-filled: rule_with_defaults reads a missing
    # value as up_only, so every SKU already tracked gets the protective
    # setting without a write, and a row that has one keeps it.
    ("sourcing_rules", "direction", "TEXT"),
    # TWO TARGETS, SET INDEPENDENTLY, replacing the kind+pct pair above. Asked
    # for as "give me 2 different boxes for setting the roi or margin target".
    # The old pair is still READ, so an account that set one before this keeps
    # it (domain/sourcing.rule_with_defaults folds it in); nothing writes it any
    # more.
    #
    # target_margin_pct is the column declared in SCHEMA above and described
    # there as unread since the repricer's first draft. Checked before reusing
    # it: NULL in every row. So it gets the meaning its name always implied
    # rather than the table gaining a second column called the same thing.
    ("sourcing_rules", "target_roi_pct", "REAL"),
    # Whether the listing is still on Amazon. In SCHEMA too, for databases made
    # after this; here so the ones that exist gain it without being rebuilt.
    ("sourcing_enrolment", "listing_state", "TEXT"),
    ("sourcing_enrolment", "listing_checked", "TEXT"),
    # HOW MANY THE SUPPLIER SAYS THEY HAVE. eBay reports it on the same call the
    # price comes from, and it was being thrown away -- so "in stock" was a yes
    # or no when the number behind it was already on the wire. One left and two
    # hundred left are different facts about a listing you are about to promise.
    ("sourcing_checks", "available_qty", "INTEGER"),
    # POSTAGE THE BUYER PAID, kept beside the item price rather than folded into
    # it. The owner counts revenue as everything the buyer handed over --
    # "this is the total revenue i generated" -- so the two have to be separable:
    # Amazon's own Ordered Product Sales is the item price ALONE, and a screen
    # that cannot tell them apart cannot be reconciled against Seller Central.
    ("order_lines", "shipping", "REAL"),
    # WHAT THAT LINE COST, frozen at the moment the order was seen. Looked up
    # later instead, an order from July would silently pick up August's supplier
    # price and last month's profit would move every time a supplier did.
    ("order_lines", "cogs", "REAL"),
    ("order_lines", "cogs_source", "TEXT"),    # 'manual' | 'tracked' | 'sku' | ''
    ("order_lines", "cogs_at", "TEXT"),        # when it was resolved
    # WHERE A DAY'S orders/units/ordered_sales CAME FROM.
    #
    # Amazon publishes the same trade twice and the Orders API is the one that is
    # right FIRST: measured on nestwell_goods, the Sales & Traffic report had
    # delivered nothing for three days while the Orders API had 173.43 of real
    # sales in them -- so the screen showed 149.95 where the truth was 323.38.
    #
    # The live figures therefore win for those three columns, and this records
    # that they did, so the report's own later answer cannot quietly overwrite a
    # better one. Everything the report uniquely has -- sessions, page views, buy
    # box -- is untouched by this.
    ("sales_daily", "orders_source", "TEXT"),
    # HOW IT GETS HERE AND WHEN, which is what the owner reads off the eBay page
    # before deciding which link to buy from:
    #
    #   "postage free Royal Mail Tracked 48" and "estimated between Wed 19 Aug
    #    and Mon 24 Aug to postal code BH166FH"
    #
    # All of it comes back on the same getItem call the price already came from
    # (probe_ebay_delivery.py, 17 Aug 2026, item 186107152290) and all of it was
    # being thrown away. carrier is eBay's shippingServiceCode -- the NAMED
    # service, "Evri Tracked", which is the line a person actually reads; the
    # bare shippingCarrierCode is "Hermes" and means less. postage_text is the
    # sentence, kept whole rather than rebuilt in three screens from the parts.
    ("sourcing_checks", "carrier", "TEXT"),
    ("sourcing_checks", "postage_text", "TEXT"),
    ("sourcing_checks", "delivery_min", "TEXT"),      # YYYY-MM-DD
    ("sourcing_checks", "delivery_max", "TEXT"),      # YYYY-MM-DD
    # THE POSTCODE THE ESTIMATE WAS COMPUTED TO. Not decoration: with no postcode
    # eBay answered "by 21 Aug" for the free service and "by 24 Aug" once
    # BH166FH was sent -- three days apart on the same option, measured. A
    # delivery date whose destination is unknown cannot be promised to a buyer,
    # so the destination is stored beside it.
    ("sourcing_checks", "delivery_postcode", "TEXT"),
    # WHO IS SELLING IT. eBay's Browse API returns seller.username on the same
    # getItem call everything above came from, and it was being dropped, so the
    # only thing a screen had to show for a source was the raw URL:
    #
    #   https://www.ebay.co.uk/itm/235976183512?_skw=cable&epid=27050...
    #
    # Asked for as: "i do not want the full ebay link just display the name of
    # the seller and the link attached to it so i can click on the seller name
    # to open the product link". Stored rather than derived, because it is a
    # fact about the supplier that only the supplier can tell us.
    ("sourcing_checks", "seller", "TEXT"),
    # THE PRICE A PRODUCT SELLS AT, held against a target that would lower it.
    # "this rule is for the items where i am sure that this is the market price and
    # this product sells on this price point no matter the roi or margin".
    # Separate from min_price, which is loss protection -- see hold_price in
    # domain/sourcing.DEFAULT_RULE for why one column could not be both.
    ("sourcing_rules", "hold_price", "REAL"),
    # THE NEVER-SELL-AT-BREAK-EVEN FLOOR, as a percentage of what the unit cost.
    # It arrived when the invented 3.00 postage / 2.00 ads / 1.00 profit were
    # removed from the pricing rule: with those at zero, cost + Amazon's fee is
    # the whole floor and a sale at it earns nothing. NULL means "use the
    # default", which is listing/pricing.PRICING_RULE_MIN_ROI_PCT.
    ("sourcing_rules", "min_roi_pct", "REAL"),
    # THE SELLER'S OWN PER-UNIT COSTS. Previously code constants only, which was
    # fine while they were 3.00/2.00/1.00 for everyone. They default to 0.00 now
    # -- nothing is assumed on the owner's behalf -- so there has to be somewhere
    # to say "this one really does cost me 4.20 to post". NULL means the default.
    ("sourcing_rules", "shipping_label", "REAL"),
    ("sourcing_rules", "ads_margin", "REAL"),
    ("sourcing_rules", "min_profit", "REAL"),
    # WHICH ADVERTISING PRODUCT A ROW CAME FROM. Every row that exists before
    # this column did came from a Sponsored Products report -- that is the only
    # thing the app has ever pulled -- so the default back-fills them correctly
    # rather than leaving them unattributed. See the note in SCHEMA: without it
    # a Brands pull overwrites the Products figures for the same day.
    ("ads_daily", "ad_product", "TEXT NOT NULL DEFAULT 'SPONSORED_PRODUCTS'"),
    ("ads_campaign_daily", "ad_product",
     "TEXT NOT NULL DEFAULT 'SPONSORED_PRODUCTS'"),
]

# Unique keys that GAINED a column. Adding the column is not enough: the old
# index still enforces the old key, so two ad products would still collide.
# (table, old index, new index, columns) -- the new one is created first and the
# old dropped only if that succeeded, so a failure leaves the database enforcing
# the stricter-but-wrong key rather than no key at all.
_REPLACED_INDEXES = [
    ("ads_daily", "idx_ads_key", "idx_ads_key2",
     "workspace_id, marketplace, date, asin, ad_product"),
    ("ads_campaign_daily", "idx_adscamp_key", "idx_adscamp_key2",
     "workspace_id, marketplace, date, campaign_id, ad_product"),
]


def _migrate(conn):
    """Bring an existing database up to the current SCHEMA. Idempotent."""
    for table, column, coltype in _ADDED_COLUMNS:
        try:
            have = {r["name"] for r in conn.execute("PRAGMA table_info(%s)" % table)}
        except Exception:
            continue                       # table not created yet; SCHEMA will do it
        if column not in have:
            try:
                conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, coltype))
            except Exception:
                pass                       # raced with another thread; harmless

    for table, old_ix, new_ix, cols in _REPLACED_INDEXES:
        try:
            have = {r["name"] for r in conn.execute("PRAGMA table_info(%s)" % table)}
        except Exception:
            continue                       # table not created yet
        if not have:
            continue
        # Every column of the new key must exist, or the CREATE fails and the
        # old index would be dropped for nothing.
        if any(c.strip() not in have for c in cols.split(",")):
            continue
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS %s ON %s(%s)"
                         % (new_ix, table, cols))
        except Exception:
            continue                       # keep the old key rather than none
        try:
            conn.execute("DROP INDEX IF EXISTS %s" % old_ix)
        except Exception:
            pass


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
            _migrate(conn)
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
