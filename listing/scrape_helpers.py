"""listing/scrape_helpers.py -- scraping helpers: browser settings, fetching a page, flattening attribute values, eBay item ids.

Moved word for word out of amazon_listing_generator.py (Milestone 4, owner-approved 28 Sep 2026).
amazon_listing_generator.py still imports every name below, so dashboard.<name> and every
route that is handed one keep working exactly as before. Nothing here may
import dashboard (it would load a second copy of the app).
"""

import asyncio
from api import ebay as _ebay_api          # single source of the eBay client


def _extract_ebay_item_id(url: str) -> str:
    return _ebay_api.item_id_from_url(url)


def _flatten_attr_value(entry) -> str:
    """Turn one SP-API attribute entry into a clean human-readable string.
    Handles {value}, {value,unit}, {displayValue}, and nested dimension shapes
    like {length:{value,unit}, width:..., height:...} -- so we never dump a raw
    Python dict (e.g. \"{'length': {'value': 30...}}\") into the attribute set."""
    if not isinstance(entry, dict):
        return str(entry).strip()
    if entry.get("value") not in (None, ""):
        unit = str(entry.get("unit") or entry.get("unit_of_measure") or "").strip()
        return f"{entry['value']} {unit}".strip()
    for k in ("displayValue", "amount", "name"):
        if entry.get(k) not in (None, ""):
            return str(entry[k]).strip()
    parts = []
    for axis in ("length", "width", "height", "depth", "weight"):
        sub = entry.get(axis)
        if isinstance(sub, dict) and sub.get("value") not in (None, ""):
            unit = str(sub.get("unit", "")).strip()
            parts.append(f"{axis} {sub['value']} {unit}".strip())
    return ", ".join(parts)


_BROWSER_CFG = {}     # built on first use; see _browser_cfg()


def _browser_cfg():
    """The scraping browser's settings, built the first time a page is scraped.

    This used to be a module-level constant, which meant importing crawl4ai --
    2.1 seconds, and with it numpy, aiohttp and two copies of Playwright -- every
    time this program started, including the many runs that scrape nothing at
    all. The settings themselves are unchanged; only WHEN they are built moved.
    """
    if "cfg" in _BROWSER_CFG:
        return _BROWSER_CFG["cfg"]
    from crawl4ai import BrowserConfig
    _BROWSER_CFG["cfg"] = BrowserConfig(
        headless=True, verbose=False,
        headers={
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-GB,en;q=0.9",
        },
        # Pin the amazon.co.uk delivery location to a UK postcode BEFORE any
        # page loads. Without this, a non-UK visitor (e.g. from Pakistan) gets
        # served a location-fallback view: prices hidden, no Buy Box, "cannot
        # ship to your location" banners -- exactly why the scraper was
        # returning thin data on UK PDPs when SP-API fell back. SW1A 1AA =
        # London postcode.
        cookies=[
            {"name": "lc-main",    "value": "en_GB",   "domain": ".amazon.co.uk", "path": "/"},
            {"name": "i18n-prefs", "value": "GBP",     "domain": ".amazon.co.uk", "path": "/"},
            {"name": "sp-cdn",     "value": "L5Z9:GB", "domain": ".amazon.co.uk", "path": "/"},
        ],
    )
    return _BROWSER_CFG["cfg"]


async def _scrape(url: str, css: str = None, timeout: int = 25000,
                  delay: float = 2.0) -> str:
    # Imported here rather than at the top of the file: this is the only place
    # the browser engine is needed, and loading it costs 2.1s of every run.
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    run_cfg = CrawlerRunConfig(
        css_selector=css, word_count_threshold=15,
        remove_overlay_elements=True, exclude_external_links=True,
        page_timeout=timeout, delay_before_return_html=delay,
        excluded_tags=["nav", "header", "footer", "script", "style"] if not css else [],
    )
    async def _run():
        async with AsyncWebCrawler(config=_browser_cfg()) as crawler:
            result = await crawler.arun(url=url, config=run_cfg)
            return (result.markdown or result.cleaned_html or "").strip()
    # Hard ceiling: the page_timeout above is crawl4ai-internal and can still
    # hang on browser launch/navigation. Kill the whole attempt a few seconds
    # past the page timeout so a stuck browser can never freeze the run.
    try:
        return await asyncio.wait_for(_run(), timeout=(timeout / 1000.0) + 8)
    except asyncio.TimeoutError:
        return ""
