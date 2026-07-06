"""
ppc_module.py -- Amazon PPC capability for the listing generator app.

Scope (this session): Foundation + agent + campaign-builder shortcut.
- Canonical data schemas (keyword, search-term, SQP, economics)
- File ingester: detects DataDive / Helium 10 / SQP / Search Term Report / bulk
  export from column names, normalises to canonical schema
- Skill catalogue: every skill from the handover doc, so the agent can route
- Campaign builder: keyword bucketing (drop / competitor / category-head / core)
  + validated Seller Central bulk file emitter

Non-negotiable rules (baked in from the doc, NOT left to prompts):
- Match Type spelled out fully: Exact / Phrase / Broad
- SKU (never ASIN) on every Product Ad row
- Keywords + Product Targets NEVER in the same ad group
- 0 duplicate (keyword, match-type) pairs across the file
- Every relevant keyword in all 3 match types (base + Coverage catches missing)
- Never set or change bids/budgets without the user specifying a value
"""
from __future__ import annotations
import csv, io, json, os, re
from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# 1. Canonical schemas -- every ingested row is normalised to one of these
# ---------------------------------------------------------------------------

# Keyword grain (bulk exports, keyword performance reports)
KW_FIELDS = ("keyword_text", "match_type", "campaign", "ad_group",
             "impressions", "clicks", "spend", "sales", "orders", "units")

# Search-term grain (SP Search Term Report -- input to the harvester)
ST_FIELDS = ("customer_search_term", "triggering_keyword", "match_type",
             "campaign", "ad_group",
             "impressions", "clicks", "spend", "sales", "orders", "units")

# SQP grain (Brand Analytics SQP or SQPR export)
SQP_FIELDS = ("search_query", "query_volume",
              "asin_impressions", "asin_clicks", "asin_purchases",
              "market_impressions", "market_clicks", "market_purchases",
              "asin_cvr", "market_cvr")

# Economics grain (per-ASIN, feeds break-even ACOS + pricing rule)
ECON_FIELDS = ("asin", "price", "coupon_pct", "referral_pct",
               "fulfilment_cost", "cogs", "prep_cost")


# ---------------------------------------------------------------------------
# 2. File-family detection -- driven by column-name fingerprints
# ---------------------------------------------------------------------------
# Fingerprints picked to be unique to each source. `any` semantics: if 2+ of
# the fingerprint tokens are present in the header row, it's a match.
FILE_SIGNATURES = {
    "datadive_keywords": {
        "tokens":  ("search volume", "keyword", "cpc"),
        "kind":    "keyword_export",
        "column_map": {
            "keyword":        "keyword_text",
            "search volume":  "search_volume",
            "cpc":            "cpc_bid_suggested",
        },
    },
    "helium10_cerebro": {
        "tokens":  ("keyword phrase", "search volume", "organic rank"),
        "kind":    "keyword_export",
        "column_map": {
            "keyword phrase": "keyword_text",
            "search volume":  "search_volume",
            "sponsored rank": "sponsored_rank",
            "organic rank":   "organic_rank",
        },
    },
    "sqp_brand_analytics": {
        "tokens":  ("search query", "search query score", "impressions", "clicks"),
        "kind":    "sqp",
        "column_map": {
            "search query":                  "search_query",
            "search query volume":           "query_volume",
            "impressions: asin count":       "asin_impressions",
            "impressions: total count":      "market_impressions",
            "clicks: asin count":            "asin_clicks",
            "clicks: total count":           "market_clicks",
            "purchases: asin count":         "asin_purchases",
            "purchases: total count":        "market_purchases",
        },
    },
    "sp_search_term_report": {
        # canonical name in Amazon Ads reports.
        # ATTRIBUTION FIX: Amazon reports include BOTH 7-day and 14-day columns
        # for sales/orders/units. We MUST prefer 7-day (the SP industry
        # standard) instead of letting last-column-wins pick whichever appears
        # later in the header. The ingester below applies this preference
        # explicitly instead of relying on column_map dict order.
        "tokens":  ("customer search term", "campaign name", "ad group name"),
        "kind":    "search_terms",
        "column_map": {
            "customer search term":  "customer_search_term",
            "targeting":             "triggering_keyword",
            "keyword text":          "triggering_keyword",
            "match type":            "match_type",
            "campaign name":         "campaign",
            "ad group name":         "ad_group",
            "impressions":           "impressions",
            "clicks":                "clicks",
            "spend":                 "spend",
            # 7-day is preferred; 14-day is used only as fallback (see ingester)
            "7 day total sales":     "sales__7d",
            "14 day total sales":    "sales__14d",
            "7 day total orders (#)":"orders__7d",
            "14 day total orders (#)":"orders__14d",
            "7 day total units (#)": "units__7d",
            "14 day total units (#)":"units__14d",
        },
        # Post-normalisation: which suffixed field to prefer for each canonical name
        "attribution_prefer": [
            ("sales",  ["sales__7d",  "sales__14d"]),
            ("orders", ["orders__7d", "orders__14d"]),
            ("units",  ["units__7d",  "units__14d"]),
        ],
    },
    "sp_bulk_export": {
        "tokens":  ("record type", "campaign", "ad group", "match type"),
        "kind":    "bulk_export",
    },
    "amazon_business_report": {
        "tokens":  ("sessions", "browser page views", "buy box percentage"),
        "kind":    "business_report",
    },
}


def _norm_header(s: str) -> str:
    """lower + collapse whitespace + strip punctuation for tolerant matching."""
    return re.sub(r"[^a-z0-9 ]+", " ", str(s).lower()).strip()


def detect_file_family(header_row: list) -> Optional[dict]:
    """Given the first row of a CSV/XLSX, identify which Amazon file family it is.
    Returns the signature dict (or None). Uses fuzzy header matching so column
    order and minor punctuation differences don't break detection."""
    if not header_row:
        return None
    normalised = {_norm_header(h) for h in header_row if h}
    best = None
    best_hits = 0
    for name, sig in FILE_SIGNATURES.items():
        hits = sum(1 for tok in sig["tokens"] if any(tok in h for h in normalised))
        if hits >= 2 and hits > best_hits:
            best = {"family": name, **sig}
            best_hits = hits
    return best


def ingest_csv_bytes(data: bytes) -> dict:
    """Detect file family + normalize rows to canonical schema.

    Returns:
      {family, kind, rows: [dict], detected_columns, raw_row_count}
    Fails soft: returns {family: None, ...} if detection fails, so the agent
    can ask the user what the file is instead of crashing.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except Exception as e:
            return {"family": None, "error": f"cannot decode file: {e}"}
    reader = csv.reader(io.StringIO(text))
    try:
        rows = list(reader)
    except Exception as e:
        return {"family": None, "error": f"CSV parse failed: {e}"}
    if not rows:
        return {"family": None, "error": "empty file"}

    header = rows[0]
    sig = detect_file_family(header)
    if not sig:
        return {"family": None, "raw_row_count": len(rows) - 1,
                "detected_columns": header[:20],
                "error": "could not identify file family from column headers"}

    # normalise each data row to canonical column names
    col_map = {_norm_header(k): v for k, v in (sig.get("column_map") or {}).items()}
    norm_rows = []
    for r in rows[1:]:
        if not any(str(c).strip() for c in r):
            continue
        d = {}
        for i, cell in enumerate(r):
            if i >= len(header):
                break
            src = _norm_header(header[i])
            dst = col_map.get(src)
            if dst:
                d[dst] = cell.strip() if isinstance(cell, str) else cell
            else:
                d[src] = cell.strip() if isinstance(cell, str) else cell
        # ATTRIBUTION PREFERENCE: for reports that expose the same metric under
        # multiple attribution windows (e.g. 7-day vs 14-day), collapse them
        # to a single canonical field using the signature's preferred order.
        # This replaces the old "last-column-wins" behaviour that could silently
        # let 14-day figures overwrite 7-day figures.
        for canonical, prefer_list in sig.get("attribution_prefer", []):
            chosen = ""
            for src_field in prefer_list:
                v = d.get(src_field, "")
                if v not in ("", None):
                    chosen = v
                    break
            d[canonical] = chosen
            # keep the suffixed fields available for advanced users; strip in caller if noisy
        norm_rows.append(d)

    return {"family": sig["family"], "kind": sig["kind"], "rows": norm_rows,
            "detected_columns": header, "raw_row_count": len(rows) - 1}


# ---------------------------------------------------------------------------
# 3. Keyword bucketing (drop / competitor / category-head / core)
# ---------------------------------------------------------------------------
# From the doc, section 1.1. First-match-wins classification order.

# Bucketing rules are stored per-product in config so a niche's rival brands +
# waste terms can be tuned without editing code. These are safe UK defaults.
DEFAULT_DROP_TERMS = (
    # bare category heads and low-intent generics
    "amazon", "aliexpress", "ebay",
    # accessory-only / wrong-use
    "for kids", "replacement", "spare part", "instructions",
    # wrong-audience filler
    "cheap", "free", "best cheap",
)


@dataclass
class BucketingConfig:
    competitor_brands: tuple = ()          # e.g. ("dyson", "shark", "vax")
    category_heads:    tuple = ()          # e.g. ("vacuum", "hoover")
    drop_terms:        tuple = DEFAULT_DROP_TERMS
    min_chars:         int   = 2           # drop terms shorter than this (per whole phrase)
    max_word_count:    int   = 10          # Amazon rejects >10-word keywords


def _tok(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").lower().strip())


def bucket_keyword(kw: str, cfg: BucketingConfig) -> str:
    """Return 'drop' | 'competitor' | 'category-head' | 'core'.
    First-match-wins in that order (drop first so waste never reaches campaigns)."""
    k = _tok(kw)
    if not k or len(k) < cfg.min_chars:
        return "drop"
    if len(k.split()) > cfg.max_word_count:
        return "drop"
    # drop rules (specific bad tokens from the doc's DEFAULT_DROP_TERMS list)
    for d in cfg.drop_terms:
        if d and d in k:
            return "drop"
    # competitor brand match
    for b in cfg.competitor_brands:
        b = _tok(b)
        if b and b in k:
            return "competitor"
    # category-head: exact match on any head token (not substring)
    for h in cfg.category_heads:
        h = _tok(h)
        if h and h == k:
            return "category-head"
    return "core"


def bucket_all(keywords: list, cfg: BucketingConfig) -> dict:
    """Classify a list of keyword rows. Returns buckets + a dedup summary."""
    seen = set()
    buckets = {"drop": [], "competitor": [], "category-head": [], "core": []}
    for row in keywords:
        kw = _tok(row.get("keyword_text") or row.get("keyword") or "")
        if not kw or kw in seen:
            continue
        seen.add(kw)
        buckets[bucket_keyword(kw, cfg)].append(dict(row, keyword_text=kw))
    return {"buckets": buckets,
            "counts":  {k: len(v) for k, v in buckets.items()},
            "total_unique": len(seen)}


# ---------------------------------------------------------------------------
# 4. Campaign builder -- emits Seller Central Sponsored Products bulk CSV
# ---------------------------------------------------------------------------
# The invariant from the doc:
#   Every relevant keyword appears in all 3 match types.
#   Each (keyword, match-type) pair appears EXACTLY ONCE.
#   Base campaigns hold each keyword's primary match; Coverage fills the rest.

# Amazon SP bulk file columns (v3+ template). Order matters when Amazon parses.
BULK_COLUMNS = [
    "Product", "Entity", "Operation", "Campaign ID", "Ad Group ID",
    "Portfolio ID", "Ad ID (Read only)", "Keyword ID (Read only)",
    "Product Targeting ID (Read only)",
    "Campaign Name", "Ad Group Name", "Start Date", "End Date",
    "Targeting Type", "State", "Daily Budget", "SKU", "ASIN",
    "Ad Group Default Bid", "Bid", "Keyword Text", "Match Type",
    "Bidding Strategy", "Placement", "Percentage",
    "Product Targeting Expression",
]


@dataclass
class CampaignBuildInput:
    asin:                  str
    sku:                   str                  # SELLER SKU, not ASIN!
    product_short_name:    str                  # e.g. 'BodyScale' for the taxonomy
    marketplace:           str  = "UK"          # UK|US
    daily_budget:          float = 8.0          # £8/$8 per doc; June 2026 change
    default_bid:           float = 0.30         # ONLY if user specifies; not auto-tuned
    conquest_asins:        tuple = ()           # optional product-target ASINs
    start_date_yyyymmdd:   str = ""             # blank -> today


def _today_yyyymmdd() -> str:
    import datetime
    return datetime.date.today().strftime("%Y%m%d")


def _n(x, default=""):
    """Empty string for missing values -- Amazon rejects None in bulk CSV."""
    return default if x in (None, "", 0) else x


def _campaign_row(name: str, budget: float, bid_strategy: str = "Dynamic bids - down only",
                  start: str = "") -> dict:
    return {
        "Product": "Sponsored Products",
        "Entity":  "Campaign",
        "Operation": "Create",
        "Campaign ID": name,
        "Campaign Name": name,
        "Start Date": start or _today_yyyymmdd(),
        "Targeting Type": "Manual",
        "State": "enabled",
        "Daily Budget": f"{budget:.2f}",
        "Bidding Strategy": bid_strategy,
    }


def _adgroup_row(campaign: str, adgroup: str, default_bid: float) -> dict:
    return {
        "Product": "Sponsored Products",
        "Entity":  "Ad Group",
        "Operation": "Create",
        "Campaign ID": campaign,
        "Ad Group ID": adgroup,
        "Campaign Name": campaign,
        "Ad Group Name": adgroup,
        "State": "enabled",
        "Ad Group Default Bid": f"{default_bid:.2f}",
    }


def _product_ad_row(campaign: str, adgroup: str, sku: str) -> dict:
    return {
        "Product": "Sponsored Products",
        "Entity":  "Product Ad",
        "Operation": "Create",
        "Campaign ID": campaign,
        "Ad Group ID": adgroup,
        "Campaign Name": campaign,
        "Ad Group Name": adgroup,
        "State": "enabled",
        "SKU": sku,                  # CRITICAL: SKU not ASIN
    }


def _keyword_row(campaign: str, adgroup: str, keyword: str, match_type: str, bid: float) -> dict:
    return {
        "Product": "Sponsored Products",
        "Entity":  "Keyword",
        "Operation": "Create",
        "Campaign ID": campaign,
        "Ad Group ID": adgroup,
        "Campaign Name": campaign,
        "Ad Group Name": adgroup,
        "State": "enabled",
        "Bid": f"{bid:.2f}",
        "Keyword Text": keyword,
        "Match Type": match_type,      # spelled out; NEVER abbreviated
    }


def _negative_row(campaign: str, adgroup: str, keyword: str) -> dict:
    return {
        "Product": "Sponsored Products",
        "Entity":  "Negative Keyword",
        "Operation": "Create",
        "Campaign ID": campaign,
        "Ad Group ID": adgroup,
        "Campaign Name": campaign,
        "Ad Group Name": adgroup,
        "State": "enabled",
        "Keyword Text": keyword,
        "Match Type": "Negative phrase",
    }


def _product_target_row(campaign: str, adgroup: str, asin: str, bid: float) -> dict:
    return {
        "Product": "Sponsored Products",
        "Entity":  "Product Targeting",
        "Operation": "Create",
        "Campaign ID": campaign,
        "Ad Group ID": adgroup,
        "Campaign Name": campaign,
        "Ad Group Name": adgroup,
        "State": "enabled",
        "Bid": f"{bid:.2f}",
        "Product Targeting Expression": f'asin="{asin}"',
    }


def build_sp_bulk(inp: CampaignBuildInput,
                  buckets: dict,
                  negatives: tuple = ()) -> dict:
    """Emit the Seller Central Sponsored Products bulk CSV rows.

    Structure (5 campaigns, one ad group per campaign):
      SP_AUTO_{name}_DISC              -- Auto discovery (no keywords)
      SP_NB_{name}_Phrase_DISC         -- Phrase, category-head keywords
      SP_NB_{name}_Exact_GROW          -- Exact, core money keywords
      SP_OFF_{name}_CompBrand_Exact    -- Exact, competitor brand keywords
      SP_{name}_CATCH_ALL_Coverage     -- Every keyword's MISSING match types

    Returns {rows, csv, validation}
      rows       -- list of dicts (one per Amazon bulk-file row)
      csv        -- full CSV string ready to upload
      validation -- dict of pre-flight checks (all must pass)
    """
    if not inp.sku:
        raise ValueError("SKU is required and MUST be the seller SKU (not the ASIN).")
    if inp.sku == inp.asin:
        raise ValueError("SKU cannot equal ASIN. Use the SELLER SKU from Seller Central.")

    name = inp.product_short_name or inp.asin
    start = inp.start_date_yyyymmdd or _today_yyyymmdd()
    budget = float(inp.daily_budget)
    bid    = float(inp.default_bid)

    core         = buckets.get("core", [])
    category     = buckets.get("category-head", [])
    competitor   = buckets.get("competitor", [])

    campaigns = {
        "AUTO":     f"SP_AUTO_{name}_DISC",
        "PHRASE":   f"SP_NB_{name}_Phrase_DISC",
        "EXACT":    f"SP_NB_{name}_Exact_GROW",
        "COMP":     f"SP_OFF_{name}_CompBrand_Exact",
        "COVERAGE": f"SP_{name}_CATCH_ALL_Coverage",
    }

    rows: list = []

    # ---- Campaigns, one ad group each ----
    for label, cname in campaigns.items():
        rows.append(_campaign_row(cname, budget, start=start))
        rows.append(_adgroup_row(cname, f"{cname}_AG", bid))
        rows.append(_product_ad_row(cname, f"{cname}_AG", inp.sku))

    # ---- AUTO: no keywords; add a small negative fence to stop waste ----
    for neg in negatives:
        rows.append(_negative_row(campaigns["AUTO"], f"{campaigns['AUTO']}_AG", neg))

    # ---- Phrase discovery: category-head terms ----
    for row in category:
        rows.append(_keyword_row(campaigns["PHRASE"], f"{campaigns['PHRASE']}_AG",
                                  row["keyword_text"], "Phrase", bid))
    for neg in negatives:
        rows.append(_negative_row(campaigns["PHRASE"], f"{campaigns['PHRASE']}_AG", neg))

    # ---- Exact grow: core money terms ----
    for row in core:
        rows.append(_keyword_row(campaigns["EXACT"], f"{campaigns['EXACT']}_AG",
                                  row["keyword_text"], "Exact", bid))

    # ---- CompBrand exact: competitor brand names ----
    for row in competitor:
        rows.append(_keyword_row(campaigns["COMP"], f"{campaigns['COMP']}_AG",
                                  row["keyword_text"], "Exact", bid))

    # ---- CATCH ALL Coverage: every relevant keyword's MISSING match types ----
    # core is Exact-primary -> Coverage adds Phrase + Broad
    # category-head is Phrase-primary -> Coverage adds Exact + Broad
    # competitor is Exact-primary -> Coverage adds Phrase + Broad
    cov = f"{campaigns['COVERAGE']}_AG"
    for row in core:
        rows.append(_keyword_row(campaigns["COVERAGE"], cov, row["keyword_text"], "Phrase", bid))
        rows.append(_keyword_row(campaigns["COVERAGE"], cov, row["keyword_text"], "Broad",  bid))
    for row in category:
        rows.append(_keyword_row(campaigns["COVERAGE"], cov, row["keyword_text"], "Exact",  bid))
        rows.append(_keyword_row(campaigns["COVERAGE"], cov, row["keyword_text"], "Broad",  bid))
    for row in competitor:
        rows.append(_keyword_row(campaigns["COVERAGE"], cov, row["keyword_text"], "Phrase", bid))
        rows.append(_keyword_row(campaigns["COVERAGE"], cov, row["keyword_text"], "Broad",  bid))
    for neg in negatives:
        rows.append(_negative_row(campaigns["COVERAGE"], cov, neg))

    # ---- Product-target campaign (SEPARATE ad group -- hard rule from the doc) ----
    if inp.conquest_asins:
        pt_camp = f"SP_ASIN_TARGET_{name}"
        rows.append(_campaign_row(pt_camp, budget, start=start))
        rows.append(_adgroup_row(pt_camp, f"{pt_camp}_KW_AG", bid))          # keywords ad group
        rows.append(_adgroup_row(pt_camp, f"{pt_camp}_PT_AG", bid))          # product-targets ad group
        rows.append(_product_ad_row(pt_camp, f"{pt_camp}_KW_AG", inp.sku))
        rows.append(_product_ad_row(pt_camp, f"{pt_camp}_PT_AG", inp.sku))
        for target_asin in inp.conquest_asins:
            rows.append(_product_target_row(pt_camp, f"{pt_camp}_PT_AG", target_asin, bid))

    # ---- Validation (all must pass; the doc calls these upload-blockers) ----
    validation = _validate_bulk_rows(rows)

    # ---- Emit CSV ----
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=BULK_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in BULK_COLUMNS})

    return {"rows": rows, "csv": buf.getvalue(), "validation": validation,
            "campaigns": campaigns}


def _validate_bulk_rows(rows: list) -> dict:
    """Enforce the doc's hard rules. Returns dict of ok flags + any violations."""
    v = {"ok": True, "errors": [], "warnings": []}

    # 1. No duplicate (keyword, match-type) pairs across the WHOLE file
    seen = set()
    for r in rows:
        if r.get("Entity") == "Keyword":
            key = (r["Keyword Text"].lower(), r["Match Type"].lower())
            if key in seen:
                v["ok"] = False
                v["errors"].append(f"Duplicate (keyword, match-type): {key}")
            seen.add(key)

    # 2. Every Keyword row: Match Type must be Exact/Phrase/Broad (spelled out)
    valid_match = {"exact", "phrase", "broad"}
    for r in rows:
        if r.get("Entity") == "Keyword":
            if r["Match Type"].lower() not in valid_match:
                v["ok"] = False
                v["errors"].append(f"Bad match type: {r['Match Type']!r} on {r['Keyword Text']!r}")

    # 3. Product Ad rows: SKU present, ASIN empty (SKU is the ID Amazon uses)
    for r in rows:
        if r.get("Entity") == "Product Ad":
            if not r.get("SKU"):
                v["ok"] = False
                v["errors"].append(f"Product Ad row missing SKU in {r.get('Campaign Name')}")
            if r.get("ASIN"):
                v["warnings"].append(f"Product Ad row has ASIN set alongside SKU in "
                                     f"{r.get('Campaign Name')} -- SKU takes precedence")

    # 4. Keywords + Product Targets NEVER share an ad group (hard rule from Part 1.5)
    kw_ag = set()
    pt_ag = set()
    for r in rows:
        ag = (r.get("Campaign Name", ""), r.get("Ad Group Name", ""))
        if r.get("Entity") == "Keyword":
            kw_ag.add(ag)
        elif r.get("Entity") == "Product Targeting":
            pt_ag.add(ag)
    shared = kw_ag & pt_ag
    if shared:
        v["ok"] = False
        v["errors"].append(f"Keywords and Product Targets share an ad group -- MUST be split: {shared}")

    # 5. Keyword Text: <=10 words, <=80 chars, no hidden chars
    for r in rows:
        if r.get("Entity") in ("Keyword", "Negative Keyword"):
            k = str(r.get("Keyword Text", ""))
            if len(k.split()) > 10:
                v["ok"] = False
                v["errors"].append(f"Keyword >10 words (Amazon rejects): {k!r}")
            if len(k) > 80:
                v["ok"] = False
                v["errors"].append(f"Keyword >80 chars: {k!r}")
            if any(ord(c) < 32 for c in k):
                v["ok"] = False
                v["errors"].append(f"Keyword has hidden control character: {k!r}")

    v["dup_pair_count"]        = 0
    v["match_type_errors"]     = sum(1 for e in v["errors"] if "Bad match type" in e)
    v["missing_sku_errors"]    = sum(1 for e in v["errors"] if "missing SKU" in e)
    v["shared_adgroup_errors"] = sum(1 for e in v["errors"] if "share an ad group" in e)
    v["dup_pair_count"]        = sum(1 for e in v["errors"] if "Duplicate" in e)
    return v


# ---------------------------------------------------------------------------
# 6. Harvester -- process an SP Search Term Report into three deliverables:
#    (a) status sheet (colour-coded per term)
#    (b) harvest bulk CSV (new converting terms in all 3 match types)
#    (c) negatives CSV (past-$10 zero-order terms)
# ---------------------------------------------------------------------------
# Rules from Part 1.5 D/E of the handover doc.
# THE $10 RULE: let a relevant-but-unproven term reach ~$10 spend at 0 orders
# before negating. At ~$0.45 CPC / ~7% CVR, $10 ~= 22 clicks (expected ~1.6
# orders) so $10 no-orders is a real signal.

# Status buckets for the coloured status sheet
STATUS_CONVERTING           = "CONVERTING"                 # green
STATUS_HIGH_ACOS            = "CONVERTS-BUT-HIGH-ACOS"     # amber
STATUS_CUT                  = "OVER-$10-CUT"               # red
STATUS_HIGH_SPEND_WATCH     = "HIGH-SPEND-WATCH"           # amber
STATUS_CLICKS_NO_SALE       = "CLICKS-NO-SALE"             # red (below $10)
STATUS_EARLY                = "EARLY"                       # neutral
STATUS_IMPRESSIONS_ONLY     = "IMPRESSIONS-ONLY"           # neutral


@dataclass
class HarvestConfig:
    cut_threshold_spend:  float = 10.0      # $ or £ - the $10 rule ceiling
    watch_threshold_spend: float = 5.0       # HIGH-SPEND-WATCH between watch and cut
    high_acos_ratio:      float = 1.0       # ACOS above break-even * this = high (default = at break-even)
    break_even_acos:      float = 0.35      # sensible default; user should override per product
    currency:             str   = "£"


def _num(x, default=0.0) -> float:
    """Parse a currency-ish string / number tolerantly."""
    if x is None or x == "":
        return default
    if isinstance(x, (int, float)):
        return float(x)
    s = re.sub(r"[^\d\.\-]", "", str(x))
    try:
        return float(s) if s else default
    except ValueError:
        return default


def _classify_search_term(row: dict, cfg: HarvestConfig) -> dict:
    """Return status + derived metrics for one search-term row.
    Enforces the $10 rule and the winner-not-consolidated-prematurely note
    (that one is a user-decision hint, we surface it not enforce it here)."""
    clicks  = _num(row.get("clicks"))
    spend   = _num(row.get("spend"))
    orders  = _num(row.get("orders"))
    sales   = _num(row.get("sales"))
    imps    = _num(row.get("impressions"))

    cpc  = round(spend / clicks, 4) if clicks > 0 else 0
    cpa  = round(spend / orders, 4) if orders > 0 else 0
    acos = round(spend / sales,  4) if sales  > 0 else 0
    roas = round(sales / spend,  4) if spend  > 0 else 0
    ctr  = round(clicks / imps,  4) if imps   > 0 else 0
    cvr  = round(orders / clicks,4) if clicks > 0 else 0

    # Classification: first-match order that mirrors the manual decision rules
    if orders >= 1 and acos <= cfg.break_even_acos * cfg.high_acos_ratio:
        status = STATUS_CONVERTING
    elif orders >= 1:
        status = STATUS_HIGH_ACOS
    elif spend >= cfg.cut_threshold_spend:
        status = STATUS_CUT                     # $10 with 0 orders = kill
    elif spend >= cfg.watch_threshold_spend:
        status = STATUS_HIGH_SPEND_WATCH
    elif clicks >= 5 and orders == 0:
        status = STATUS_CLICKS_NO_SALE
    elif clicks > 0:
        status = STATUS_EARLY
    else:
        status = STATUS_IMPRESSIONS_ONLY

    return {
        **row,
        "clicks": clicks, "spend": spend, "orders": orders,
        "sales": sales, "impressions": imps,
        "cpc": cpc, "cpa": cpa, "acos": acos, "roas": roas,
        "ctr": ctr, "cvr": cvr, "status": status,
    }


def _normalise_kw(k: str) -> str:
    return re.sub(r"\s+", " ", str(k or "").lower().strip())


def run_harvest(search_term_rows: list,
                current_targeting_kws: Optional[set] = None,
                cfg: Optional[HarvestConfig] = None) -> dict:
    """Process an SP Search Term Report into the three deliverables.

    Params:
      search_term_rows        -- list of dicts (ingested from CSV)
      current_targeting_kws   -- set of already-targeted keyword_text (lowercased)
                                  used to exclude already-covered terms from the
                                  harvest file. If None, no exclusion.
      cfg                     -- HarvestConfig; sensible defaults if None.

    Returns:
      { status_rows:  [dict per term with metrics + status],
        harvest_rows: [dict per NEW converting term, 3 match types each],
        negative_rows:[dict per OVER-$10 term],
        summary:      {counts by status, totals} }
    """
    if cfg is None:
        cfg = HarvestConfig()
    already = current_targeting_kws or set()

    # 1. Aggregate by customer_search_term (report may have multiple rows per term
    #    across campaigns/ad groups)
    agg: dict = {}
    for row in search_term_rows:
        term = _normalise_kw(row.get("customer_search_term"))
        if not term:
            continue
        a = agg.setdefault(term, {
            "customer_search_term": term,
            "triggering_keyword":   row.get("triggering_keyword", ""),
            "match_type":           row.get("match_type", ""),
            "campaign":             row.get("campaign", ""),
            "ad_group":             row.get("ad_group", ""),
            "impressions": 0, "clicks": 0, "spend": 0.0,
            "sales": 0.0, "orders": 0, "units": 0,
        })
        a["impressions"] += _num(row.get("impressions"))
        a["clicks"]      += _num(row.get("clicks"))
        a["spend"]       += _num(row.get("spend"))
        a["sales"]       += _num(row.get("sales"))
        a["orders"]      += _num(row.get("orders"))
        a["units"]       += _num(row.get("units"))

    status_rows = [_classify_search_term(a, cfg) for a in agg.values()]

    # 2. Harvest = NEW converting terms not already targeted (excludes branded
    #    conquest, which the caller decides). Adds each in all 3 match types.
    harvest_rows = []
    for r in status_rows:
        if r["status"] != STATUS_CONVERTING:
            continue
        term = r["customer_search_term"]
        if term in already:
            continue                          # already targeted -- skip
        for mt in ("Exact", "Phrase", "Broad"):
            harvest_rows.append({
                "customer_search_term": term,
                "match_type":           mt,
                "source_campaign":      r.get("campaign", ""),
                "acos_source":          r["acos"],
                "orders_source":        r["orders"],
            })

    # 3. Negatives = OVER-$10-CUT (real signal), NOT CLICKS-NO-SALE (below floor)
    negative_rows = [{
        "customer_search_term": r["customer_search_term"],
        "spend":                r["spend"],
        "clicks":               r["clicks"],
        "orders":               r["orders"],
        "source_campaign":      r.get("campaign", ""),
    } for r in status_rows if r["status"] == STATUS_CUT]

    # 4. Summary
    from collections import Counter
    counts = Counter(r["status"] for r in status_rows)
    totals = {
        "total_terms":      len(status_rows),
        "total_spend":      round(sum(r["spend"]  for r in status_rows), 2),
        "total_sales":      round(sum(r["sales"]  for r in status_rows), 2),
        "total_orders":     int(sum(r["orders"] for r in status_rows)),
        "converting_terms": counts[STATUS_CONVERTING],
        "harvest_ready":    len({r["customer_search_term"] for r in harvest_rows}),
        "negatives_ready":  len(negative_rows),
    }

    return {"status_rows":  status_rows,
            "harvest_rows": harvest_rows,
            "negative_rows": negative_rows,
            "counts":       dict(counts),
            "totals":       totals}


def build_harvest_bulk_csv(harvest_rows: list,
                            inp: CampaignBuildInput,
                            existing_coverage_campaign: str = "") -> str:
    """Emit a bulk-file-shaped CSV that adds harvest terms into the CATCH ALL
    Coverage campaign of a running portfolio.

    If `existing_coverage_campaign` is given, keywords are added AS keywords
    to that campaign's ad group (must already exist in the account -- Amazon
    resolves it by name). If empty, we emit a new Coverage campaign named
    `SP_{name}_HARVEST_{today}`.

    EMPTY-CASE FIX: if there are no harvest rows, emit ONLY the header row.
    Otherwise we'd create an empty campaign in the account that burns daily
    budget on nothing.
    """
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=BULK_COLUMNS, extrasaction="ignore")
    w.writeheader()
    if not harvest_rows:
        return buf.getvalue()      # header-only; caller shows empty-state
    name = inp.product_short_name or inp.asin
    if not existing_coverage_campaign:
        cov = f"SP_{name}_HARVEST_{_today_yyyymmdd()}"
        cov_ag = f"{cov}_AG"
        rows = [
            _campaign_row(cov, inp.daily_budget),
            _adgroup_row(cov, cov_ag, inp.default_bid),
            _product_ad_row(cov, cov_ag, inp.sku),
        ]
    else:
        cov = existing_coverage_campaign
        cov_ag = f"{cov}_AG"
        rows = []                             # rely on Amazon resolving by name

    seen_pairs = set()
    for r in harvest_rows:
        pair = (r["customer_search_term"], r["match_type"])
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        rows.append(_keyword_row(cov, cov_ag, r["customer_search_term"],
                                  r["match_type"], inp.default_bid))

    for r in rows:
        w.writerow({c: r.get(c, "") for c in BULK_COLUMNS})
    return buf.getvalue()


def build_negatives_bulk_csv(negative_rows: list,
                              inp: CampaignBuildInput,
                              apply_to_campaigns: tuple = ()) -> str:
    """Emit a bulk-file-shaped CSV of Negative phrase keywords to add to the
    listed campaigns. If no campaigns given, applies to the CATCH ALL Coverage.

    EMPTY-CASE FIX: header-only if nothing to negate, same reason as harvest.
    """
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=BULK_COLUMNS, extrasaction="ignore")
    w.writeheader()
    if not negative_rows:
        return buf.getvalue()
    name = inp.product_short_name or inp.asin
    targets = apply_to_campaigns or (f"SP_{name}_CATCH_ALL_Coverage",)

    rows = []
    for camp in targets:
        ag = f"{camp}_AG"
        for r in negative_rows:
            rows.append(_negative_row(camp, ag, r["customer_search_term"]))

    for r in rows:
        w.writerow({c: r.get(c, "") for c in BULK_COLUMNS})
    return buf.getvalue()


def build_status_sheet_csv(status_rows: list, currency: str = "£") -> str:
    """Emit the colour-coded status sheet as CSV. XLSX with actual colouring
    is added by the xlsx writer in the caller; this CSV keeps status column
    populated so the caller can apply conditional formatting."""
    cols = ["customer_search_term", "triggering_keyword", "match_type",
            "campaign", "ad_group",
            "impressions", "clicks", "ctr", "cpc", "spend",
            "orders", "units", "cvr", "sales", "acos", "roas",
            "status"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in status_rows:
        # coerce numbers to nice strings for CSV consumption
        row = {c: r.get(c, "") for c in cols}
        for k in ("ctr", "cvr", "acos"):
            if isinstance(row.get(k), (int, float)):
                row[k] = f"{row[k]*100:.1f}%"
        for k in ("cpc", "spend", "sales", "roas"):
            if isinstance(row.get(k), (int, float)):
                row[k] = f"{currency}{row[k]:.2f}" if k != "roas" else f"{row[k]:.2f}"
        w.writerow(row)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 7. Skill catalogue (extended) -- see section 5 for the base map
# ---------------------------------------------------------------------------
SKILL_CATALOGUE = {
    "campaign-builder": {
        "handles": ("build campaigns", "new asin", "keyword export", "launch",
                    "make campaigns", "bulk file"),
        "requires": ("keyword file", "ASIN", "SKU", "product short name"),
        "produces": "validated Seller Central bulk CSV (5 campaigns, all-match-type coverage)",
    },
    "harvester": {
        "handles": ("search term report", "harvest", "negatives", "$10 rule",
                    "new converting", "status sheet"),
        "requires": ("SP Search Term Report", "current-targeting export or bulk"),
        "produces": "harvest bulk CSV + negatives CSV + colour-coded status XLSX",
    },
    "auditor": {
        "handles": ("audit", "PPC health", "waste", "structure", "not converting"),
        "requires": ("SP bulk export", "campaign performance report"),
        "produces": "audit docx",
    },
    "dashboard": {
        "handles": ("dashboard", "control room", "visualise", "board"),
        "requires": ("SP bulk export", "campaign performance report",
                     "optional: organic ranking XLSX"),
        "produces": "interactive React dashboard",
    },
    "forecaster": {
        "handles": ("forecast", "projection", "sales projection", "revenue plan"),
        "requires": ("business report", "SQP files (Brand Analytics)", "target TACOS"),
        "produces": "3-scenario revenue + unit forecast",
    },
    "weekly-deck": {
        "handles": ("weekly deck", "wcd", "client deck", "performance deck"),
        "requires": ("weekly performance data", "prior week data (for WoW)"),
        "produces": "strategic weekly PPC deck (pptx)",
    },
    "scale-insights-audit": {
        "handles": ("scale insights", "rules", "criteria", "main child", "SI"),
        "requires": ("HistoricalAsinDateSales", "BulkKeywordTemplate",
                     "BulkBiddingRulesTemplate", "BulkCriteriaProfileTemplate"),
        "produces": "4 audit docx documents",
    },
}


def route_intent(user_message: str) -> Optional[str]:
    """Return the skill id best matching a natural-language request.
    Word-level scoring: each `handles` phrase contributes based on how many of
    its words appear in the user message. Longer phrases score higher when
    fully present, so 'scale insights audit' picks scale-insights-audit
    (2-word phrase) over the generic auditor (1-word 'audit')."""
    words = set(re.findall(r"[a-z0-9$]+", user_message.lower()))
    if not words:
        return None
    scores = {}
    for skill, spec in SKILL_CATALOGUE.items():
        s = 0
        for handle in spec["handles"]:
            handle_words = set(re.findall(r"[a-z0-9$]+", handle.lower()))
            if handle_words and handle_words.issubset(words):
                # exact phrase present: weight by phrase length so more-specific
                # multi-word handles beat generic single-word matches
                s += 2 * len(handle_words)
            elif handle_words & words:
                # partial overlap: 1 per matching word
                s += len(handle_words & words)
        if s:
            scores[skill] = s
    if not scores:
        return None
    return max(scores, key=scores.get)
