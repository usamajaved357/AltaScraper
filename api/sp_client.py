"""api/sp_client.py -- the ONE place an SP-API client is constructed (4E).

Master continuation 4E (29 Sep 2026): "Create one canonical SP-API
client/credential construction path where safely possible ... Characterize
constructor arguments before changing call sites." The map
(active/map-4E-spapi-clients.md) found 45 constructions and SIX different ways
of turning a marketplace code into python-amazon-sp-api's `Marketplaces` enum,
each written inline. They are not the same rule, and some differences are
deliberate (orders refuse to guess -- owner decision 5), so they are NOT merged
into one: each is NAMED here, once, and every call site asks for the rule it
already used. Behaviour is identical (test_sp_client.py compares every rule
with the expression it replaced over awkward inputs); the differences are now
visible in one file instead of hidden in thirty.

    client(ApiClass, creds, code, rule=..., timeout=None)

Credentials are still built by domain/accounts.account_creds (and its
documented variants); this module only builds the client from what it is given.
"""

# ---- the marketplace rules, each exactly as a call site wrote it -----------

API = "api"              # upper-case, blank -> UK, US explicitly, unknown -> UK
#                          (api/amazon_listings, amazon_catalog, amazon_metrics)
UPPER_OR_UK = "upper_or_uk"      # upper-case, unknown -> UK
#                          (monitor/pricing, domain/tracker_fetch, api/amazon_messaging)
AS_GIVEN_OR_UK = "as_given_or_uk"   # the code AS GIVEN (no upper-casing), unknown -> UK
#                          (listing/handling, domain/inventory_module, routes catalog /
#                           compliance / sqp). "us" in lower case is UK here, not US.
UPPER_OR_US = "upper_or_us"      # upper-case, unknown -> US (not UK!)
#                          (domain/sales_fetch, finance_fetch, two live/optimize reads)
US_OR_UK = "us_or_uk"            # only US or UK; everything else (DE, FR...) is UK
#                          (domain/brand_analytics)

RULES = (API, UPPER_OR_UK, AS_GIVEN_OR_UK, UPPER_OR_US, US_OR_UK)


def marketplace_enum(code, rule=API):
    """python-amazon-sp-api's Marketplaces member for `code`, by the named rule."""
    from sp_api.base import Marketplaces as M
    if rule == API:
        c = str(code or "UK").upper()
        if c == "US":
            return M.US
        return getattr(M, c, M.UK)
    if rule == UPPER_OR_UK:
        return getattr(M, str(code).upper(), None) or M.UK
    if rule == AS_GIVEN_OR_UK:
        return getattr(M, code, None) or M.UK
    if rule == UPPER_OR_US:
        return getattr(M, str(code).upper(), None) or M.US
    if rule == US_OR_UK:
        return M.US if str(code).upper() == "US" else M.UK
    raise ValueError("unknown marketplace rule %r" % (rule,))


_UNSET = object()


def client(api_class, creds, code, rule=API, timeout=_UNSET):
    """Construct one SP-API client: credentials, the marketplace by `rule`, and
    `timeout` exactly as the call site passed it -- left out entirely when the
    site did not pass one (several deliberately do not), passed through even
    when it is None (api/amazon_listings always passed it)."""
    kw = {"credentials": creds, "marketplace": marketplace_enum(code, rule)}
    if timeout is not _UNSET:
        kw["timeout"] = timeout
    return api_class(**kw)
