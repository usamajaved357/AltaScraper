"""monitor/storefront_name.py — ISOLATED best-effort seller-name resolver.

The Pricing API returns SellerId but NOT the seller's display name. This module is the ONLY
place that touches Amazon's storefront HTML. ALL page-structure-dependent parsing lives here,
behind ONE narrow interface:

    resolve_seller_name(seller_id, marketplace) -> str   ("" on ANY failure)

So when Amazon changes the storefront HTML it is a one-file fix, and it can NEVER break the
checker/diff logic (which only ever calls this function and treats "" as "unknown"). This is
opt-in enrichment, never a dependency of monitoring.
"""
import re
import html as _html
import urllib.request

# Amazon storefront domains per marketplace (BE = amazon.com.be).
_TLD = {"UK": "co.uk", "GB": "co.uk", "DE": "de", "FR": "fr", "IT": "it", "ES": "es",
        "NL": "nl", "PL": "pl", "SE": "se", "BE": "com.be", "IE": "ie"}


def storefront_url(seller_id, marketplace):
    tld = _TLD.get(str(marketplace).upper(), "co.uk")
    return f"https://www.amazon.{tld}/sp?seller={seller_id}"


def _fetch_name(seller_id, marketplace, timeout):
    try:
        req = urllib.request.Request(storefront_url(seller_id, marketplace), headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
            "Accept-Language": "en-GB,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(500000)
        return _parse_name(raw.decode("utf-8", "replace"))
    except Exception:
        return ""


def resolve_seller_name(seller_id, marketplace, timeout=15):
    """Best-effort seller display name. Tries the seller's own marketplace FIRST, then falls back
    across the other EU domains -- a seller listing on e.g. SE often only has a resolvable profile
    on another EU domain (UK/DE/...). Returns "" if none resolve. Result is cached one-time upstream."""
    if not seller_id:
        return ""
    order, seen = [], set()
    for m in [str(marketplace).upper(), "UK", "DE", "FR", "IT", "ES", "NL", "SE", "PL", "BE", "IE"]:
        if m and m not in seen:
            seen.add(m); order.append(m)
    for m in order:
        nm = _fetch_name(seller_id, m, timeout)
        if nm:
            return nm
    return ""


# --- everything below is page-structure-dependent and intentionally quarantined here ---
def _parse_name(page):
    for pat in (
        r'id="seller-name"[^>]*>\s*([^<]{1,120}?)\s*<',
        r'"sellerName"\s*:\s*"([^"]{1,120})"',
        r'id="sellerName"[^>]*>\s*([^<]{1,120}?)\s*<',
        r'name="seller-name"[^>]*content="([^"]{1,120})"',
    ):
        m = re.search(pat, page, re.I)
        if m:
            name = _clean(m.group(1))
            if _plausible(name):
                return name
    # fall back to the <title>: "Amazon.co.uk seller profile: <Name>" or "<Name>"
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
    if m:
        t = _clean(m.group(1))
        t = re.sub(r"(?i)^amazon[^:]*seller profile:\s*", "", t)
        t = re.sub(r"(?i)\s*[:|\-]\s*amazon.*$", "", t)
        if _plausible(t):
            return t
    return ""


def _clean(s):
    s = _html.unescape(str(s or "")).strip()
    return re.sub(r"\s+", " ", s)


def _plausible(name):
    return bool(name) and len(name) <= 120 and "amazon" not in name.lower() \
        and "robot" not in name.lower() and "captcha" not in name.lower()
