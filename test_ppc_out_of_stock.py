"""A keyword cannot sell what the listing does not have.

Dr PPC, asked for a case where it would be confidently wrong:

    "Confident negate on zero-order spend while PDP/OOS/brand-credit was the
     real story -- spot via ops checks, other campaigns, and a later re-pull."

That is the trap the zero-order rule walks into on its own. A keyword with
forty clicks and no sales looks identical whether shoppers did not want the
product or could not buy it, and the recommended fix -- add a negative keyword
-- is exactly wrong in the second case.

IT IS ALSO THE ONE MISTAKE HERE THAT HIDES ITSELF. Negate the term, the spend
stops, and it looks like the negation worked. The demand is simply gone, and
nothing on the screen will ever say so.

The second half of this file is the attribution warning, which matters for the
same reason: Amazon keeps crediting sales to a click for up to fourteen days,
so a term that looks like waste today may not be waste by Friday -- and a
negative keyword cannot be undone by waiting.
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
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from domain import dr_ppc as D

TERMS = [
    {"search_term": "protein shaker bottle", "sku": "SHK-1",
     "clicks": 40, "spend": 62.00, "sales": 0, "campaign_name": "SP Auto"},
    {"search_term": "gym water bottle", "sku": "BTL-9",
     "clicks": 35, "spend": 48.50, "sales": 0, "campaign_name": "SP Auto"},
]

print("== with nothing known about stock, both read as waste ==")
w = D.check_wasted_spend(TERMS, "£")
check("two findings", len(w), 2)
check("  both critical", sorted({f["severity"] for f in w}), ["critical"])
truthy("  and both recommend a negative", all("negative exact" in f["do"] for f in w))

print("\n== when the product was out of stock, the advice changes ==")
w2 = D.check_wasted_spend(TERMS, "£", oos_skus=["SHK-1"])
by_kind = {f["kind"]: f for f in w2}
truthy("the empty one is reported separately", "wasted-spend-oos" in by_kind)
truthy("  and the other is still ordinary waste", "wasted-spend" in by_kind)

oos_f = by_kind["wasted-spend-oos"]
truthy("it still reports the money spent", "62.00" in oos_f["what"])
truthy("  and says the listing was empty", "out of stock" in oos_f["what"])
falsy("  but it does NOT tell you to negate",
      "negative" in oos_f["do"].lower())
truthy("  it tells you to wait until it is back in stock",
       "Do NOT negate" in oos_f["do"])
truthy("  and explains that the clicks had nowhere to go",
       "nowhere to go" in oos_f["why"])
truthy("  the number is flagged for anything reading the data",
       oos_f["numbers"].get("out_of_stock") is True)
# Severity drops: it is still money out, but it is not a keyword problem.
check("  and it is no longer critical", oos_f["severity"], D.WARN)

print("\n== an ASIN identifies the product just as well as a SKU ==")
w3 = D.check_wasted_spend(
    [{"search_term": "x", "asin": "B0ABCDEFGH", "clicks": 20,
      "spend": 10.0, "sales": 0}], "£", oos_skus=["b0abcdefgh"])
check("matched case-insensitively", w3[0]["kind"], "wasted-spend-oos")

print("\n== a product that was never out of stock is untouched ==")
w4 = D.check_wasted_spend(TERMS, "£", oos_skus=["SOMETHING-ELSE"])
check("both still ordinary waste",
      sorted({f["kind"] for f in w4}), ["wasted-spend"])
# An empty or missing list must behave exactly as before, not as "all in stock"
# and not as "all out of stock".
check("an empty list changes nothing",
      sorted({f["kind"] for f in D.check_wasted_spend(TERMS, "£", oos_skus=[])}),
      ["wasted-spend"])
check("  and so does None",
      sorted({f["kind"] for f in D.check_wasted_spend(TERMS, "£", oos_skus=None)}),
      ["wasted-spend"])

print("\n== and it does not sit at the top of the list to negate ==")
res = D.run([], TERMS, currency="£", oos_skus=["SHK-1"])
kinds = [f["kind"] for f in res["findings"]]
truthy("both appear", "wasted-spend" in kinds and "wasted-spend-oos" in kinds)
truthy("  real waste comes first",
       kinds.index("wasted-spend") < kinds.index("wasted-spend-oos"))

print("\n== the attribution warning is on every run ==")
notes = " ".join(res.get("notes") or [])
truthy("it says the recent days are still moving", "14 days" in notes)
truthy("  and which days move most", "2 to 7 days" in notes)
truthy("  and why that matters HERE specifically",
       "cannot be undone by waiting" in notes)
# The point is not trivia about attribution. It is that one action on this
# screen is irreversible and the data behind it is not settled.
truthy("  naming the irreversible action", "negative keyword" in notes)

print("\n== a run with no data does not warn about attribution ==")
quiet = D.run([], [], currency="£")
truthy("nothing to be provisional about",
       not any("14 days" in n for n in (quiet.get("notes") or [])))

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)

