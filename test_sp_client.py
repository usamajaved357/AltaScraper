# -*- coding: utf-8 -*-
"""api/sp_client: every marketplace rule is EXACTLY the expression it replaced,
and every migrated call site builds its client through it (4E, 29 Sep 2026).

The old expressions are copied here verbatim from the call sites, so this test
characterises the constructor arguments before and after the move over awkward
inputs (lower case, blank, unknown, non-EU codes). A difference is a behaviour
change and fails.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


from sp_api.base import Marketplaces                  # noqa: E402
from api import sp_client as SP                       # noqa: E402

M = Marketplaces


def old_api(marketplace):                              # api/amazon_listings._enum (catalog identical)
    code = str(marketplace or "UK").upper()
    if code == "US":
        return M.US
    return getattr(M, code, M.UK)


def old_metrics(marketplace):                          # api/amazon_metrics._enum
    code = str(marketplace or "UK").upper()
    return getattr(M, code, M.UK)


def old_upper_or_uk(m):                                # monitor/pricing._mk_enum, tracker_fetch
    return getattr(M, str(m).upper(), None) or M.UK


def old_messaging(marketplace):                        # api/amazon_messaging
    return getattr(M, str(marketplace).upper(), M.UK)


def old_as_given(m):                                   # listing/handling, inventory, routes
    return getattr(M, m, None) or M.UK


def old_upper_or_us(m):                                # domain/sales_fetch
    return getattr(M, str(m).upper(), None) or M.US


def old_us_or_uk(m):                                   # domain/brand_analytics
    return M.US if str(m).upper() == "US" else M.UK


CODES = ["UK", "US", "DE", "FR", "IT", "ES", "CA", "JP", "uk", "us", "de", "Us", "", "XX", "gb", "GB",
         "AE", "IN", "MX", "AU", "NL", "SE", "PL", "BE", "TR", "SA", "SG", "BR", "EG", "IE"]
print("== each rule is exactly its old expression ==")
for name, old, rule, extra in (("api (listings/catalog)", old_api, SP.API, [None]),
                               ("api (metrics, no US special case)", old_metrics, SP.API, [None]),
                               ("upper_or_uk", old_upper_or_uk, SP.UPPER_OR_UK, [None]),
                               ("upper_or_uk == messaging's default form", old_messaging, SP.UPPER_OR_UK, [None]),
                               ("as_given_or_uk", old_as_given, SP.AS_GIVEN_OR_UK, []),
                               ("upper_or_us", old_upper_or_us, SP.UPPER_OR_US, [None]),
                               ("us_or_uk", old_us_or_uk, SP.US_OR_UK, [None])):
    diff = [c for c in CODES + extra if old(c) != SP.marketplace_enum(c, rule)]
    check("%-34s identical on %d inputs" % (name, len(CODES + extra)), diff, [])
try:
    old_as_given(None)
    raised_old = False
except TypeError:
    raised_old = True
try:
    SP.marketplace_enum(None, SP.AS_GIVEN_OR_UK)
    raised_new = False
except TypeError:
    raised_new = True
check("as_given_or_uk still raises on None, as the old expression did", (raised_old, raised_new), (True, True))

print("== the client gets exactly those arguments ==")


class Rec:
    def __init__(self, **kw):
        self.kw = kw


c = SP.client(Rec, {"k": 1}, "de", rule=SP.UPPER_OR_UK, timeout=30)
check("credentials, marketplace and timeout passed through",
      (c.kw["credentials"], c.kw["marketplace"], c.kw["timeout"]), ({"k": 1}, M.DE, 30))
check("no timeout unless the site set one", "timeout" in SP.client(Rec, {}, "UK").kw, False)
check("  and a timeout of None is passed through, as a site that always passed it did",
      ("timeout" in SP.client(Rec, {}, "UK", timeout=None).kw,
       SP.client(Rec, {}, "UK", timeout=None).kw.get("timeout")), (True, None))

print("== migrated call sites build through it ==")
SITES = {
    "api/amazon_listings.py": "_sp.client(ListingsItemsV20210801",
    "api/amazon_catalog.py": "_sp.client(",
    "api/amazon_metrics.py": "_sp.client(",
    "api/amazon_messaging.py": "_sp.client(Messaging",
    "monitor/pricing.py": "_sp.client(Products",
    "listing/handling.py": "_sp.",
    "domain/tracker_fetch.py": "_sp.client(CatalogItems",
    "domain/inventory_module.py": "_sp.client(Inventories",
    "domain/sales_fetch.py": "_sp.client(Reports",
    "domain/brand_analytics.py": "_sp.client(Reports",
}
for f, needle in SITES.items():
    src = open(os.path.join(HERE, f), encoding="utf-8").read()
    check("%-28s uses api/sp_client" % f, needle in src, True)

print("== a migrated site really runs (not only its text) ==")
# The first version of this move left brand_analytics._run_report reading a
# variable the change had removed (NameError on every new report) -- a text
# check could not see it. So the real function runs here, Amazon faked.
from domain import brand_analytics as BA            # noqa: E402
SENT = {}


class _FakeReports:
    def __init__(self, **kw):
        SENT["ctor"] = kw

    def create_report(self, **body):
        SENT["body"] = body
        raise RuntimeError("stop here -- nothing is sent")


_orig_rep, _orig_ok = BA.Reports, BA._SP_OK
BA.Reports, BA._SP_OK = _FakeReports, True
for code, want in (("US", M.US), ("UK", M.UK), ("DE", M.UK)):
    SENT.clear()
    try:
        BA._run_report({"k": 1}, code, "GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT", None,
                       "2026-09-01", "2026-09-07", log=lambda *a: None, poll_timeout=1)
    except NameError as e:
        SENT["nameerror"] = str(e)
    except Exception:
        pass
    check("brand analytics %s: client and request name %s" % (code, want.name),
          (SENT.get("nameerror"), SENT.get("ctor", {}).get("marketplace"),
           (SENT.get("body") or {}).get("marketplaceIds")),
          (None, want, [want.marketplace_id]))
BA.Reports, BA._SP_OK = _orig_rep, _orig_ok

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.exit(1 if fails else 0)
