"""A supplier link is shown by NAME, and an alert says its reason once.

TWO COMPLAINTS, ONE SHAPE

    "in the order details i see the ebay link is shown as full i do not want the
     full ebay link just display the name of the seller and the link attached to
     it so i can click on the seller name to open the product link"

    "all the text all over the app should be arranged and should not be floating
     freely"

Both are the same fault: something written for one context being repeated into
another where it does not belong. A raw URL is the right thing to STORE and the
wrong thing to SHOW. A self-contained sentence is right for a webhook posting
one alert into a channel, and wrong printed twelve times down a page.

It is also a measurable layout bug, not only an ugly one. A grid column will not
shrink below its longest unbreakable word, and a 120-character eBay URL is one
word: the supplier column of the order panel measured 5,523px wide on a 390px
phone.

WHAT IS PINNED HERE
  1. the name comes from what is KNOWN, in order, and nothing is invented
  2. one function decides it, so the order panel and the repricer cannot
     disagree about what one supplier is called
  3. the seller name survives the round trip from eBay into the database
  4. the shared half of an alert is only said once when it is really shared
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

from domain import source_fetch as _fetch          # noqa: E402
from domain import source_link as _slink           # noqa: E402
from domain import stock_alerts as _alerts         # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                  % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


EBAY = ("https://www.ebay.co.uk/itm/235976183512?_skw=cable+tie&epid=27050"
        "&hash=item36ec0d1f28:g:AAAAAAA&amdata=enc%3AAQAJAAAA")

print("\n== the name comes from what is known, best first ==")
check("a label somebody typed wins -- it is their own word for the supplier",
      _slink.display_name(EBAY, "topseller_uk", "Bob's Wholesale"),
      "Bob's Wholesale")
check("  then the seller name the supplier published",
      _slink.display_name(EBAY, "topseller_uk", ""), "topseller_uk")
check("  then the site and the item, which says where rather than who",
      _slink.display_name(EBAY, "", ""), "ebay.co.uk · item 235976183512")

print("\n== nothing is invented, and the raw URL is never the answer ==")
check("a site with no item number is named by the site alone",
      _slink.display_name("https://www.screwfix.com/p/some-thing/12345x", "", ""),
      "screwfix.com")
check("an unusable URL says so rather than guessing a seller",
      _slink.display_name("", "", ""), "supplier link")
check("  and so does a URL with no host",
      _slink.display_name("not-a-url", "", ""), "not-a-url")
# The old code wrote `label or url`, so URLs are sitting in the label column of
# real rows right now. Treating one as a person's chosen name would put the very
# thing being complained about back on screen.
check("a label that is only the URL again is not treated as a name",
      _slink.display_name(EBAY, "", EBAY), "ebay.co.uk · item 235976183512")
for out in (_slink.display_name(EBAY, "topseller_uk", ""),
            _slink.display_name(EBAY, "", ""),
            _slink.display_name(EBAY, "", EBAY)):
    check("  the answer %r is never a URL" % out[:28],
          out.lower().startswith("http"), False)

print("\n== the seller survives the round trip from eBay ==")
item = {"price": {"value": "10.06", "currency": "GBP"},
        "seller": {"username": "gadget_barn", "feedbackPercentage": "99.4"}}
got = _fetch.from_ebay_item(item)
check("read off the same getItem call the price came from",
      got.get("seller"), "gadget_barn")
check("  a reading with no seller block is blank, not missing",
      _fetch.from_ebay_item({"price": {"value": "1", "currency": "GBP"}})
      .get("seller"), "")
# Every caller reads check["seller"], so it has to exist on a failed reading too
# or each one needs its own guard.
check("  and a failed reading still carries the key",
      "seller" in _fetch.from_ebay_item({}), True)

print("\n== an alert says its shared reason once ==")


def alert(sku, kind=_alerts.ALL_GONE, mode="dry_run", sources=1):
    return {"sku": sku, "kind": kind, "mode": mode, "sources": sources,
            "since": "2026-08-18"}


three = [alert("8.00_3Days_A"), alert("9.00_3Days_B"), alert("7.00_2Days_C")]
shared = _alerts.group_sentence(three)
truthy("there is a shared explanation when they really do share one", shared)
check("  it says what is wrong once", shared.count("out of stock or ended"), 1)
check("  and what to do about it", "set the quantity to 0" in shared, True)
# The whole point: what is left on each row is short.
check("each row keeps only the SKU and what differs",
      _alerts.row_label(three[0]), "8.00_3Days_A — 1 supplier")
truthy("  which is far shorter than the standalone sentence",
       len(_alerts.row_label(three[0])) * 3 < len(_alerts.sentence(three[0])))

print("\n== but only when it is genuinely shared ==")
# Half the list would be told the wrong thing, which is worse than repeating.
mixed_mode = [alert("A", mode="dry_run"), alert("B", mode="live")]
got = _alerts.group_sentence(mixed_mode)
truthy("mixed dry-run and live keeps the shared FACT", got)
check("  but drops what happens next, which differs",
      "set the quantity to 0" in got or "next run" in got, False)
mixed_kind = [alert("A"), alert("B", kind=_alerts.UNREADABLE)]
check("two different kinds share nothing, so nothing is claimed",
      _alerts.group_sentence(mixed_kind), "")
check("an empty list says nothing", _alerts.group_sentence([]), "")
check("  and so does None", _alerts.group_sentence(None), "")

print("\n== the standalone sentence still stands alone ==")
# It is what a webhook posts into a channel with no other context, so splitting
# the shared half out must not have hollowed it.
one = _alerts.sentence(three[0])
for part in ("8.00_3Days_A", "out of stock or ended", "set the quantity to 0"):
    truthy("  a webhook still gets %r" % part, part in one)

print("\n== one function names a link, not two ==")
# The order panel and the repricer both draw supplier links. If each derived its
# own name they would drift, and the same supplier would read two ways on two
# screens (CLAUDE.md Rule 12).
import re                                                     # noqa: E402
srcs = {p: open(r"D:\AltaScraper\%s" % p, encoding="utf-8-sig").read()
        for p in ("domain/order_sources.py", "routes/sourcing_routes.py")}
for p, s in srcs.items():
    truthy("%s asks source_link for the name" % p,
           re.search(r"_slink\.display_name\(", s))
js = open(r"D:\AltaScraper\static\js\sourcing.js", encoding="utf-8-sig").read()
# Same name, same fallback -- read off options_for's `label`, which is what
# display_name() writes into it, rather than off the raw source row. One
# function still decides what a link is called (CLAUDE.md Rule 12).
truthy("the repricer draws the server's name",
       "s.label || _srcShort(s.url)" in js)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
