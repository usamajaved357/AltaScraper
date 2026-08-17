"""What the source is selling, against what we would be selling it as.

Found by doing what was asked: "pick any seller from the input sheet you have
access, and extract its some items and draft 5 of them using that import seller
tool and fix bugs while going through that process".

The seller, read off an eBay link already in the input data:
housewaresstore-23. Of the eight items screened, FIVE came back as eBay
condition "New other (see details)" -- eBay's own words for opened, repackaged,
or missing its box. Three of those five were among the ones drafted.

Nothing in the app mentioned it. eBay returns the condition, to_review_row keeps
it on the row, and it was then never read again -- while
amazon_listing_generator.py:4927 puts condition_type new_new on every listing it
has ever built. So an opened-box floodlight would have gone up as Amazon New,
and the first anyone heard of it would have been the claim.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-70s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)
def falsy(l, g): check(l, bool(g), False)

from domain import seller_import as SI

def risk(cond):
    return SI.condition_risk({"condition": cond, "title": "t"})

print("=== eBay's 'New' is nine conditions, and three of them are not new ===")
for good in ("New", "New with tags", "New without tags", "New with box",
             "Brand New"):
    falsy("%-26s is plainly new, so nothing is said" % good, risk(good))

print()
for bad, word in (("New other (see details)", "NEW OTHER"),
                  ("New with defects", "NEW WITH DEFECTS"),
                  ("Open box", "OPEN BOX"),
                  ("Seller refurbished", "REFURBISHED"),
                  ("Certified - Refurbished", "REFURBISHED"),
                  ("Excellent - Refurbished", "REFURBISHED"),
                  ("Used", "USED"),
                  ("Pre-owned", "PRE-OWNED"),
                  ("For parts or not working", "FOR PARTS")):
    r = risk(bad)
    truthy("%-26s is flagged" % bad, r)
    truthy("   and named as %-18s" % word, word in (r or {}).get("message", ""))

print("\n--- it says what WE would be doing, not only what eBay said ---")
m = risk("New other (see details)")["message"]
truthy("it names the mismatch", "listed on Amazon as New" in m)
truthy("  and what it costs", "not as described" in m)
truthy("  and that the check is BEFORE the money is spent", "spend on it" in m)

print("\n--- capitalisation is not a way past it ---")
truthy("NEW OTHER (SEE DETAILS)", risk("NEW OTHER (SEE DETAILS)"))
truthy("  new other", risk("new other"))

print("\n=== saying nothing is not the same as saying new ===")
r = risk("")
truthy("a missing condition IS flagged", r)
truthy("  as unknown rather than as a risk", (r or {}).get("unknown"))
truthy("  and it says why that matters",
       "goes up as New" in (r or {}).get("message", ""))
# Assuming new when nobody said so is the assumption that costs money, which is
# the same reason every other check here answers UNKNOWN rather than CLEAR.

print("\n=== and it changes the verdict, not just the notes ===")
def verdict(cond):
    return SI.screen_one({"condition": cond, "title": "LED work light",
                          "category": "Lighting"})["verdict"]
check("plainly new stays clear", verdict("New"), SI.CLEAR)
check("New other is a caution", verdict("New other (see details)"), SI.CAUTION)
check("  used too", verdict("Used"), SI.CAUTION)
check("no condition at all is unknown", verdict(""), SI.UNKNOWN)

print("\n--- a caution is not a block ---")
# Plenty of 'New other' stock is a shop clearing shelf-worn boxes. Whether this
# supplier's is fine is a judgement about a supplier, not a rule a program makes.
# The point is that the judgement is made knowingly, before the spend.
rows = [{"item_id": "1", "condition": "New other (see details)", "title": "a"},
        {"item_id": "2", "condition": "New", "title": "b"}]
_out, summary = SI.screen(rows)
check("both are still draftable", summary["draftable"], 2)
check("  nothing is blocked", summary["counts"][SI.BLOCKED], 0)
check("  but the batch reports the worst of it", summary["worst"], SI.CAUTION)

print("\n--- the condition comes back on the row, so the screen can show it ---")
one = SI.screen_one({"item_id": "9", "condition": "New other (see details)",
                     "title": "x"})
check("the exact words eBay used", one["condition"], "New other (see details)")

print("\n--- a worse verdict is not overwritten by this one ---")
one = SI.screen_one({"item_id": "9", "condition": "New other (see details)",
                     "title": "x"},
                    restriction_lookup=lambda r: {"blocked": True,
                                                  "reasons": ["gated"]})
check("blocked stays blocked", one["verdict"], SI.BLOCKED)
truthy("  and the condition is still mentioned",
       any("NEW OTHER" in n for n in one["notes"]))

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
