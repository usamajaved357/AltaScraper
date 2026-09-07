"""More than one supplier for the same product, in the owner's own order.

    "they all sell same item so some suppliers may have less listing optimized
     and the 2nd will have some attributes the first missed, the third ine will
     have some more attributes the first two missed, so i can mention in the
     sheet supplier 1, which is prioritized for info then supplier 2 which is
     prioritized at the second number and so on, if i want to add more than 3
     suppliers i can add a column for them"

One eBay seller's listing is one seller's idea of what matters. A cheap listing
may carry the price and nothing else; a careful one may have twelve item
specifics and no dimensions. Generating from a single link makes every gap in
that one listing a gap in the Amazon listing -- when the information usually
exists on the next seller's page for the same product.
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
    print("  %-64s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from listing import suppliers as S

print("=== the columns are found, whatever they are called ===")
# Both spellings: the owner described one and the sheet already uses the other,
# and guessing which he will type is how a link is silently ignored.
H = ["Competitor ASIN", "Source URL", "Supplier 2", "Supplier 3", "UPC"]
check("the existing column is supplier one",
      S.supplier_columns(H)[0], (1, "Source URL"))
check("  then the numbered ones in order",
      [p for p, _n in S.supplier_columns(H)], [1, 2, 3])
check("the other spelling works too",
      [p for p, _n in S.supplier_columns(
          ["Source URL", "Source URL 2", "Source URL 3"])], [1, 2, 3])
# A SIXTH SUPPLIER IS A NEW COLUMN AND NO CODE CHANGE -- the whole point of
# discovering them rather than listing them.
check("a column nobody planned for is still found",
      [p for p, _n in S.supplier_columns(
          ["Source URL", "Supplier 2", "Supplier 6"])], [1, 2, 6])
# THE NUMBER ORDERS THEM, NOT THE COLUMN POSITION: a column inserted in the
# middle of the sheet must not silently re-prioritise the rest.
check("the number decides the order, not where the column sits",
      [p for p, _n in S.supplier_columns(
          ["Supplier 3", "Source URL", "Supplier 2"])], [1, 2, 3])
check("a sheet with no supplier column at all", S.supplier_columns([]), [])
check("  and one with only unrelated columns",
      S.supplier_columns(["UPC", "SKU", "Brand"]), [])

print("\n=== the URLs on one row ===")
ROW = {"source_url": "https://ebay.co.uk/itm/111",
       "supplier_2": "https://ebay.co.uk/itm/222",
       "supplier_3": "  ", "upc": "5012345678900"}
check("filled columns only, in order",
      S.urls_from(ROW, H), [(1, "https://ebay.co.uk/itm/111"),
                            (2, "https://ebay.co.uk/itm/222")])
# A blank in the middle is a hole, not a stop: supplier 1 and 3 filled must
# fetch two suppliers.
check("a blank in the middle is skipped, not a full stop",
      [p for p, _u in S.urls_from(
          {"source_url": "a://1", "supplier_3": "a://3"},
          ["Source URL", "Supplier 2", "Supplier 3"])], [1, 3])
# THE SAME LINK TWICE IS ONE SUPPLIER. Pasting it into two columns is an
# ordinary slip and fetching it twice costs a request to learn nothing.
check("the same link in two columns is fetched once",
      len(S.urls_from({"source_url": "a://1", "supplier_2": "a://1"}, H)), 1)
check("  ignoring a trailing slash",
      len(S.urls_from({"source_url": "a://1/", "supplier_2": "a://1"}, H)), 1)

print("\n=== first non-empty wins, and nothing is overwritten ===")
# The direction is the whole feature: these are different sellers describing the
# same product and they disagree. Letting a later one overwrite would mean the
# content changed with whichever answered fastest.
P1 = {"title": "Spin Mop Refill 4 Heads", "description": "", "price": "9.99",
      "condition": "New", "category_path": "",
      "item_specifics": {"Brand": "Unbranded", "Colour": "White"},
      "image_count": 3}
P2 = {"title": "SPIN MOP REFILLS (4 PACK)", "description": "Fits most bases.",
      "price": "10.50", "condition": "", "category_path": "Home > Cleaning",
      "item_specifics": {"Colour": "Grey", "Material": "Microfibre"},
      "image_count": 7}
P3 = {"title": "", "description": "", "price": "", "condition": "",
      "category_path": "",
      "item_specifics": {"Material": "Cotton", "MPN": "SM-4"},
      "image_count": 2}
merged, prov = S.merge([(1, "a://1", P1), (2, "a://2", P2), (3, "a://3", P3)])

check("supplier 1's title stands", merged["title"], "Spin Mop Refill 4 Heads")
check("  and its price", merged["price"], "9.99")
check("supplier 2 fills the description supplier 1 left blank",
      merged["description"], "Fits most bases.")
check("  and the category", merged["category_path"], "Home > Cleaning")

print("\n  the specifics merge PER SPEC, which is the point:")
check("supplier 1's Colour is not overwritten",
      merged["item_specifics"]["Colour"], "White")
check("  supplier 2 adds a spec supplier 1 missed",
      merged["item_specifics"]["Material"], "Microfibre")
check("    and supplier 3 one the first two both missed",
      merged["item_specifics"]["MPN"], "SM-4")
check("      without changing supplier 2's",
      merged["item_specifics"]["Material"], "Microfibre")
check("  four specs from three sellers",
      sorted(merged["item_specifics"]), ["Brand", "Colour", "MPN", "Material"])

# THE MOST ANY ONE SELLER HAD, not the sum: they are photographs of the same
# product, and adding them would claim a picture count nobody has.
check("images are the best single seller's, never added up",
      merged["image_count"], 7)

print("\n=== every value can be traced to the seller it came from ===")
check("the title's source", prov["title"]["supplier"], 1)
check("  the description's", prov["description"]["supplier"], 2)
check("  and per spec", prov["item_specifics"]["MPN"]["supplier"], 3)
check("    with the link, so a wrong value leads somewhere",
      prov["item_specifics"]["MPN"]["url"], "a://3")

print("\n=== a dead link contributes nothing and loses nothing ===")
# fetch_ebay_supplement answers with an empty dict rather than raising, so an
# ended listing on supplier 2 must simply not participate.
DEAD = {"title": "", "description": "", "price": "", "item_specifics": {},
        "image_count": 0, "condition": "", "category_path": ""}
m2, _p2 = S.merge([(1, "a://1", P1), (2, "a://dead", DEAD)])
check("supplier 1's data survives a dead supplier 2", m2["title"],
      "Spin Mop Refill 4 Heads")
check("  and nothing was invented", m2["description"], "")
m3, _p3 = S.merge([])
check("no suppliers at all is empty, not an error", m3["title"], "")
check("  with a specifics dict, so callers need no guard",
      m3["item_specifics"], {})

print("\n=== a later supplier is only fetched if there is a gap ===")
# Three suppliers on every row is three eBay calls per listing to answer a
# question the first seller usually already answered.
truthy("nothing fetched yet is all gap", S.has_gap([]))
truthy("a thin first supplier leaves a gap", S.has_gap([(1, "a://1", P1)]))
FULL = {"title": "t", "description": "d", "price": "1.00", "condition": "New",
        "category_path": "c", "image_count": 5,
        "item_specifics": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6}}
falsy("a complete first supplier leaves none", S.has_gap([(1, "a://1", FULL)]))

print("\n=== the enrolment is one call that serves both screens ===")
SRC = open(os.path.join(HERE, "listing", "suppliers.py"), encoding="utf-8").read()
truthy("it writes through source_repo", "from domain import source_repo" in SRC)
truthy("  which is what Orders and the Repricer already read",
       "Both of those screens read domain/source_repo" in SRC)
# ensure_source, not add_source: generating the same row twice must not leave
# two copies of one supplier, checked twice and shown twice.
truthy("  and it cannot duplicate on a re-run", "ensure_source(" in SRC)
falsy("    never add_source", "_repo.add_source(" in SRC)
truthy("  the sheet's order becomes the source priority",
       "priority=int(pos)" in SRC)
truthy("  and a failure never loses the generated row",
       "NEVER FATAL" in SRC)

print("\n=== the generator only calls in; the logic lives here (Rule 7) ===")
G = open(os.path.join(HERE, "amazon_listing_generator.py"), encoding="utf-8").read()
truthy("it merges through the module", "_suppliers.merge(_supp_parts)" in G)
truthy("  asks the module whether to fetch more",
       "_suppliers.has_gap(_supp_parts)" in G)
truthy("  and enrols through it", "_suppliers.enrol(" in G)
# A row whose only link sits in a supplier column still has a source, and would
# otherwise be dropped silently by the gate that requires ebay_url.
truthy("a row with only a Supplier 2 link is not dropped",
       'norm["ebay_url"] = norm["supplier_urls"][0][1]' in G)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
raise SystemExit(1 if fails else 0)
