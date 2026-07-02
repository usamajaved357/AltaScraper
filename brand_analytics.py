"""
brand_analytics.py
===================
Amazon Brand Analytics pulls via SP-API, used to ground listing keywords in
REAL Amazon search data instead of inference. Two phases:

PHASE 1 -- creation-time keyword seeding (works pre-launch):
    GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT
    Category/marketplace-wide top search terms with search-frequency rank and
    the top-3 clicked ASINs per term. NOT tied to your ASIN, so it works for a
    brand-new product. Requires the Brand Analytics SP-API role + Brand Registry
    on the calling account (Shee'lady US has this). The compressor-oil terms are
    the same regardless of which brand pulls them, so Shee'lady's access can seed
    Miles/Headbanger keywords.

PHASE 2 -- post-launch optimisation (works once the ASIN is live):
    GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT  (SQP)
    Per-ASIN top search queries with impressions/clicks/cart-adds/purchases.
    Needs the ASIN live with search history (~1-4 weeks). Use it to refine an
    existing listing: front-load the terms that actually convert.

Both reports:
  - are REQUEST-ONLY (cannot be scheduled)
  - use fixed calendar boundaries (WEEK = Sunday..Saturday)
  - have an SLA delay (weekly data ready ~end of Monday, 48h after period close)
  - return a document you download + parse

This module is import-safe: if python-amazon-sp-api isn't installed it degrades
to a clear error rather than crashing the app at import.
"""

from __future__ import annotations
import csv
import gzip
import io
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from sp_api.api import Reports
    from sp_api.base import Marketplaces, ReportType
    _SP_OK = True
except Exception as _e:           # pragma: no cover
    _SP_OK = False
    _SP_IMPORT_ERROR = str(_e)

# --- report type strings (used directly so we don't depend on enum members) ---
RT_SEARCH_TERMS = "GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT"
RT_SQP          = "GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT"

# Where pulled raw data is cached so we don't re-pull the same week repeatedly.
# Same directory as config.json (the persistent disk in production) so the
# cache survives a redeploy instead of living in the ephemeral container fs.
_CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
_CACHE_DIR = Path(os.path.dirname(os.path.abspath(_CONFIG_PATH))) / "brand_analytics_cache"
_CACHE_DIR.mkdir(exist_ok=True)


# =============================================================================
# Date helpers -- reports require fixed calendar weeks (Sunday..Saturday)
# =============================================================================
def _last_complete_week():
    """Return (start_iso, end_iso) for the most recent COMPLETE Sun..Sat week
    that should have data available given the ~48h SLA. We step back far enough
    that the data is reliably ready."""
    today = datetime.now(timezone.utc).date()
    # Find the most recent Saturday strictly before "today - 3 days" (SLA buffer)
    cutoff = today - timedelta(days=3)
    # weekday(): Mon=0..Sun=6; Saturday=5
    days_since_sat = (cutoff.weekday() - 5) % 7
    last_sat = cutoff - timedelta(days=days_since_sat)
    last_sun = last_sat - timedelta(days=6)
    return last_sun.isoformat(), last_sat.isoformat()


# =============================================================================
# Core report runner: create -> poll -> download -> bytes
# =============================================================================
def _marketplace_enum(marketplace: str):
    return Marketplaces.US if str(marketplace).upper() == "US" else Marketplaces.UK


def _run_report(creds: dict, marketplace: str, report_type: str,
                report_options: dict | None, start_iso: str, end_iso: str,
                log=print, poll_timeout=300):
    """Create a report, poll until DONE, download + decompress the document.
    Returns the raw text payload (TSV/JSON depending on report type)."""
    if not _SP_OK:
        raise RuntimeError(f"python-amazon-sp-api not available: {_SP_IMPORT_ERROR}")

    mkt = _marketplace_enum(marketplace)
    rep = Reports(credentials=creds, marketplace=mkt)

    body = {
        "reportType": report_type,
        "marketplaceIds": [mkt.marketplace_id],
        "dataStartTime": f"{start_iso}T00:00:00Z",
        "dataEndTime":   f"{end_iso}T23:59:59Z",
    }
    if report_options:
        body["reportOptions"] = report_options

    log(f"  [BA] createReport {report_type} {start_iso}..{end_iso}")
    created = rep.create_report(**body)
    report_id = created.payload.get("reportId")
    if not report_id:
        raise RuntimeError(f"createReport returned no reportId: {created.payload}")

    # Poll
    t0 = time.time()
    doc_id = None
    while time.time() - t0 < poll_timeout:
        st = rep.get_report(report_id)
        status = st.payload.get("processingStatus")
        if status == "DONE":
            doc_id = st.payload.get("reportDocumentId")
            break
        if status in ("CANCELLED", "FATAL"):
            raise RuntimeError(
                f"Report {report_type} ended {status}. "
                f"Likely the period isn't available yet, or the account lacks "
                f"the Brand Analytics role / Brand Registry.")
        log(f"  [BA] status={status} ... waiting")
        time.sleep(8)

    if not doc_id:
        raise RuntimeError(f"Report {report_type} timed out after {poll_timeout}s")

    # Download document (may be gzip)
    docmeta = rep.get_report_document(doc_id, download=False)
    url = docmeta.payload.get("url")
    comp = docmeta.payload.get("compressionAlgorithm")
    import requests
    raw = requests.get(url, timeout=120).content
    if comp == "GZIP":
        raw = gzip.decompress(raw)
    text = raw.decode("utf-8", errors="replace")
    log(f"  [BA] downloaded {len(text)} chars")
    return text


# =============================================================================
# PHASE 1 -- Search Terms report (category-wide, pre-launch)
# =============================================================================
def fetch_search_terms(creds: dict, marketplace: str = "US",
                       start_iso: str | None = None, end_iso: str | None = None,
                       log=print, use_cache=True) -> list:
    """Pull the marketplace top search terms report. Returns a list of dicts:
       {term, rank, asin1, asin2, asin3} sorted by search-frequency rank (1=top).

    NOTE: this report can be very large. We parse it streaming and keep only the
    fields we need. Caller should then filter to relevant terms with
    filter_terms(). Cached per week so repeated calls are cheap."""
    if not start_iso or not end_iso:
        start_iso, end_iso = _last_complete_week()

    cache_key = f"search_terms_{marketplace}_{start_iso}_{end_iso}.json"
    cache_path = _CACHE_DIR / cache_key
    if use_cache and cache_path.exists():
        log(f"  [BA] using cached search terms ({start_iso}..{end_iso})")
        return json.loads(cache_path.read_text(encoding="utf-8"))

    text = _run_report(creds, marketplace, RT_SEARCH_TERMS, None,
                       start_iso, end_iso, log=log)

    rows = _parse_search_terms(text)
    cache_path.write_text(json.dumps(rows), encoding="utf-8")
    log(f"  [BA] parsed {len(rows)} search terms")
    return rows


def _parse_search_terms(text: str) -> list:
    """The Search Terms report is JSON (newer) or TSV (older). Handle both."""
    rows = []
    t = text.lstrip()
    if t.startswith("{") or t.startswith("["):
        try:
            data = json.loads(text)
            recs = data.get("dataByDepartmentAndSearchTerm") or data.get("data") \
                   or (data if isinstance(data, list) else [])
            for r in recs:
                term = (r.get("searchTerm") or r.get("search_term") or "").strip()
                if not term:
                    continue
                rows.append({
                    "term": term,
                    "rank": int(r.get("searchFrequencyRank")
                                 or r.get("search_frequency_rank") or 0),
                    "asin1": r.get("clickedAsin") or r.get("clickedAsin1") or "",
                    "asin2": r.get("clickedAsin2") or "",
                    "asin3": r.get("clickedAsin3") or "",
                })
            return rows
        except Exception:
            pass
    # TSV fallback
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    for r in reader:
        term = (r.get("Search Term") or r.get("searchTerm") or "").strip()
        if not term:
            continue
        rank_raw = (r.get("Search Frequency Rank")
                    or r.get("searchFrequencyRank") or "0").replace(",", "")
        try:
            rank = int(rank_raw)
        except ValueError:
            rank = 0
        rows.append({
            "term": term, "rank": rank,
            "asin1": r.get("#1 Clicked ASIN", ""),
            "asin2": r.get("#2 Clicked ASIN", ""),
            "asin3": r.get("#3 Clicked ASIN", ""),
        })
    return rows


def filter_terms(rows: list, include_any: list, top_n: int = 40,
                 forbidden_brands: list = None, forbidden_specs: list = None,
                 require_core: list = None, exclude_any: list = None) -> list:
    """Filter category search terms to those that are BOTH relevant AND compliant.

    A term is kept only if ALL of these pass:
      1. RELEVANCE: contains at least one core product word (require_core) --
         e.g. 'oil', 'lubricant', 'fluid', 'grease'. A term like 'compressor
         cooler fan' is rejected because it has no core lubricant word.
      2. INCLUDE: contains at least one of the include_any seeds (the lubricant
         keyword list) -- the broad topical match.
      3. NO FORBIDDEN BRAND: contains none of the 166 forbidden OEM brands.
      4. NO FORBIDDEN SPEC: contains none of the 44 forbidden spec codes.
      5. NO EXCLUDE: contains none of the exclude_any junk words (parts,
         accessories, unrelated products).

    Returns the top_n most-searched SURVIVING terms (rank 1 = highest volume).
    Every term that comes out of here is safe to inject into the prompt: it has
    already passed the same forbidden-brand/spec gate the listing copy must pass.
    """
    inc = [w.lower() for w in (include_any or []) if w.strip()]
    core = [w.lower() for w in (require_core or DEFAULT_CORE_WORDS) if w.strip()]
    fb = [b.lower() for b in (forbidden_brands or [])]
    fs = [s.lower() for s in (forbidden_specs or [])]
    exc = [w.lower() for w in (exclude_any or DEFAULT_EXCLUDE_WORDS) if w.strip()]

    kept = []
    for r in rows:
        tl = r["term"].lower()

        # 1. relevance: must contain a core product word
        if core and not any(_word_in(c, tl) for c in core):
            continue
        # 2. topical include match
        if inc and not any(w in tl for w in inc):
            continue
        # 3. forbidden brand check (whole-word to avoid 'cat' in 'catalyst')
        if fb and any(_brand_in(b, tl) for b in fb):
            continue
        # 4. forbidden spec code check
        if fs and any(s in tl for s in fs):
            continue
        # 5. junk / unrelated-product exclusion
        if exc and any(_word_in(e, tl) for e in exc):
            continue

        kept.append(r)

    kept.sort(key=lambda r: (r["rank"] if r["rank"] > 0 else 10**9))
    return kept[:top_n]


def _word_in(word: str, text: str) -> bool:
    """Whole-word (token) match so 'oil' matches 'compressor oil' but 'fan'
    doesn't match 'fantastic'."""
    return re.search(r"(?:^|\s)" + re.escape(word) + r"(?:$|\s|s\b)", text) is not None


def _brand_in(brand: str, text: str) -> bool:
    """Whole-word brand match. Multi-word brands ('john deere') matched as a
    phrase; single tokens ('cat', 'cnh') matched as whole words to avoid false
    hits inside ordinary words."""
    b = brand.strip()
    if not b:
        return False
    if " " in b:
        return b in text
    return re.search(r"(?:^|\s)" + re.escape(b) + r"(?:$|\s)", text) is not None


# Core product words -- a term must contain at least one to be product-relevant.
DEFAULT_CORE_WORDS = [
    "oil", "lubricant", "lube", "fluid", "grease", "coolant", "compressor oil",
]

# Junk / unrelated-product words -- a term containing any of these is dropped.
DEFAULT_EXCLUDE_WORDS = [
    "filter", "fan", "belt", "hose", "gauge", "valve", "pump kit", "rebuild kit",
    "separator", "cooler", "tank", "regulator", "fitting", "gasket", "seal kit",
    "manual", "cover", "wheel", "tire", "battery", "charger", "compressor pump",
    "air compressor machine", "portable compressor", "dryer", "drain",
    "for sale", "used", "rental", "repair", "replacement part", "spare part",
]



# =============================================================================
# PHASE 2 -- SQP report (per-ASIN, post-launch)
# =============================================================================
def fetch_sqp_for_asin(creds: dict, asin: str, marketplace: str = "US",
                       start_iso: str | None = None, end_iso: str | None = None,
                       log=print, use_cache=True) -> list:
    """Pull Search Query Performance for ONE live ASIN. Returns a list of dicts
       sorted by purchases desc then impressions desc:
       {query, impressions, clicks, cart_adds, purchases}.
    Requires the ASIN to be live with search history."""
    if not start_iso or not end_iso:
        start_iso, end_iso = _last_complete_week()

    cache_key = f"sqp_{marketplace}_{asin}_{start_iso}_{end_iso}.json"
    cache_path = _CACHE_DIR / cache_key
    if use_cache and cache_path.exists():
        log(f"  [BA] using cached SQP for {asin}")
        return json.loads(cache_path.read_text(encoding="utf-8"))

    report_options = {"reportPeriod": "WEEK", "asin": asin}
    text = _run_report(creds, marketplace, RT_SQP, report_options,
                       start_iso, end_iso, log=log)

    rows = _parse_sqp(text)
    cache_path.write_text(json.dumps(rows), encoding="utf-8")
    log(f"  [BA] parsed {len(rows)} SQP queries for {asin}")
    return rows


def _parse_sqp(text: str) -> list:
    """SQP is returned as JSON with nested metric objects."""
    rows = []
    try:
        data = json.loads(text)
    except Exception:
        return rows
    recs = data.get("dataByAsin") or data.get("data") \
           or (data if isinstance(data, list) else [])
    for r in recs:
        q = (r.get("searchQuery") or r.get("search_query") or "").strip()
        if not q:
            continue

        def _num(d, *keys):
            for k in keys:
                v = d.get(k)
                if isinstance(v, dict):
                    for kk in ("totalCount", "totalClickCount",
                               "totalPurchaseCount", "totalCartAddCount", "value"):
                        if kk in v:
                            try:
                                return int(v[kk])
                            except (TypeError, ValueError):
                                pass
                elif v is not None:
                    try:
                        return int(v)
                    except (TypeError, ValueError):
                        pass
            return 0

        rows.append({
            "query": q,
            "impressions": _num(r, "impressionData", "impressions"),
            "clicks":      _num(r, "clickData", "clicks"),
            "cart_adds":   _num(r, "cartAddData", "cartAdds"),
            "purchases":   _num(r, "purchaseData", "purchases"),
        })
    rows.sort(key=lambda x: (x["purchases"], x["impressions"]), reverse=True)
    return rows


# =============================================================================
# Helpers to turn pulled data into a prompt-ready keyword block
# =============================================================================
def build_keyword_context(search_terms: list = None, sqp: list = None,
                          forbidden_brands: list = None,
                          forbidden_specs: list = None) -> str:
    """Format real Amazon search data into a block the generator injects into
    the listing prompt so the AI prioritises REAL high-volume queries.

    Any query containing a forbidden OEM brand or spec code is dropped here too,
    so even SQP buyer-queries (e.g. 'miles oil for caterpillar') can't smuggle a
    forbidden brand into the prompt."""
    fb = [b.lower() for b in (forbidden_brands or [])]
    fs = [s.lower() for s in (forbidden_specs or [])]

    def _clean(seq, key):
        out = []
        for item in seq:
            term = item[key].lower()
            if fb and any(_brand_in(b, term) for b in fb):
                continue
            if fs and any(s in term for s in fs):
                continue
            out.append(item)
        return out

    parts = []
    if search_terms:
        st = _clean(search_terms, "term")
        top = ", ".join(t["term"] for t in st[:30])
        if top:
            parts.append(
                "REAL AMAZON SEARCH DATA (category top search terms, most-searched "
                "first -- prioritise these high-volume keywords in the title, then "
                "bullets, then backend, in this order of importance). These are "
                "verified compliant and product-relevant:\n" + top + "\n")
    if sqp:
        sq = _clean(sqp, "query")
        conv = ", ".join(f"{q['query']}" for q in sq[:20] if q["purchases"] > 0)
        seen = ", ".join(f"{q['query']}" for q in sq[:20])
        if conv:
            parts.append(
                "\nTHIS ASIN'S CONVERTING SEARCH QUERIES (real buyer queries that "
                "led to purchases -- these MUST appear in the title and bullets):\n"
                + conv + "\n")
        if seen:
            parts.append(
                "\nTHIS ASIN'S TOP IMPRESSION QUERIES (high visibility -- weave into "
                "copy where natural):\n" + seen + "\n")
    return "\n".join(parts)


# Default lubricant keyword seeds for filtering the category report
LUBRICANT_INCLUDE = [
    "compressor oil", "compressor lubricant", "compressor fluid",
    "air compressor oil", "rotary compressor", "screw compressor",
    "hydraulic oil", "hydraulic fluid", "gear oil", "turbine oil",
    "synthetic oil", "iso 32", "iso 46", "iso 68", "iso 100", "iso 150",
    "iso 220", "diester", "lubricant", "industrial oil", "machine oil",
    "vacuum pump oil", "way oil", "slideway", "coolant",
]
