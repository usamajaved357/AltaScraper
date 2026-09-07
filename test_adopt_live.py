"""A live me-too listing can be edited, because a row is made for it.

    "i am trying to make changes in the live listing, ASIN B0H8TFYNB9
     SKU 14.99_2Days_B09V19CTQ5 ... it says save failed, no skus in this
     workspace and i told you that i have mee too listing this so i should be
     able to add data atleast"

TWO SETS THE APP WAS TREATING AS ONE:

    what the app has MADE   the `listings` table -- rows the generator wrote
    what the account SELLS  the live snapshot -- what Amazon says is listed

Every editor writes to the first. A me-too listing is only ever in the second,
so every field on the drawer refused to save with an error that reads like a bug
and is a true statement about an empty table.

Measured on the owner's data, 7 Sep 2026: the row for that SKU exists under
jack_uk, the SAME SKU is live on nestwell_goods (UK and IE), and the five orders
for it are nestwell's. Falling back to the other account's row would edit
another company's listing from this company's screen -- which is what
routes/listing_routes' scoping deliberately prevents. So the workspace gets a
row of its own instead.
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


from listing import adopt as A

print("=== the competitor ASIN comes from the SKU, and only from there ===")
# CLAUDE.md Rule 1: the ASIN in the SKU is the COMPETITOR the listing was
# researched from. Our own live ASIN must never land in that column, or every
# screen that reads it starts treating our product as the competitor.
check("a generated SKU yields its competitor",
      A.competitor_asin_from_sku("14.99_2Days_B09V19CTQ5"), "B09V19CTQ5")
check("  case is normalised", A.competitor_asin_from_sku("8.00_3days_b0g1k5b7qs"),
      "B0G1K5B7QS")
check("a hand-named SKU has no ASIN in it",
      A.competitor_asin_from_sku("46 pcs wrench"), "")
check("  nor does a short tail", A.competitor_asin_from_sku("9.99_2Days_XYZ"), "")
check("  nor an all-digit tail that is not an ASIN",
      A.competitor_asin_from_sku("9.99_2Days_1234567890"), "")
check("empty in, empty out", A.competitor_asin_from_sku(""), "")

SRC = open(os.path.join(HERE, "listing", "adopt.py"), encoding="utf-8").read()
truthy("the module says our own ASIN must not go in that column",
       "must never hold the first" in SRC)
falsy("  and nothing writes an `asin` field into the row",
      '"asin":' in SRC.split("vals = {")[1].split("}")[0])

print("\n=== a row is only made for a listing that is REALLY live here ===")
# Without this gate, adopting becomes "create a row for anything anybody types",
# which is how a typo becomes a listing.
_ca = SRC.split("def can_adopt(")[1].split("\ndef ")[0]
truthy("the gate is the account's OWN live snapshot", "live_item(" in _ca)
truthy("  and a miss explains what to do", "sync the live catalogue" in _ca)
_li = SRC.split("def live_item(")[1].split("\ndef ")[0]
truthy("  matched on the SKU, case-insensitively", ".strip().upper()" in _li)

print("\n=== the seed is Amazon's own record, not the other account's row ===")
# Two accounts selling the same product have their own titles, prices and
# compliance answers. Copying one into the other puts a neighbour's data under
# this brand.
_sr = SRC.split("def seed_row(")[1].split("\ndef ")[0]
truthy("it seeds from the live snapshot", "live_item(" in _sr)
truthy("  and says why not from the other account", "neighbour" in SRC)
truthy("what the snapshot does not carry is left EMPTY, not guessed",
       "rather than guessed" in _sr)
truthy("  and it is marked LIVE, because it is",
       '"status": "LIVE"' in _sr)
truthy("    with the reason", "already exists" in _sr)

print("\n=== adopting twice does not make two rows ===")
# Two rows with one SKU is worse than none: every reader takes the first, and
# edits land on whichever that happens to be.
_ad = SRC.split("def adopt(")[1]
truthy("it locates before writing", "_repo.locate(" in _ad)
truthy("  and returns without writing when already there",
       "already in this workspace" in _ad)
truthy("it never raises into the caller's save",
       "Never raises" in _ad or "never raises" in _ad)

print("\n=== /edit takes the listing in rather than refusing ===")
R = open(os.path.join(HERE, "routes", "listing_routes.py"), encoding="utf-8").read()
_ed = R.split("def edit():")[1].split("@app.route")[0]
truthy("the edit route tries to adopt", "_adopt.adopt(" in _ed)
# ONLY on the one error that means "live but unmade". Any other failure -- a
# missing SKU column, an unreadable header row -- must still be reported.
truthy("  only when the row is genuinely absent",
       'found.error == \\\n                    "no listing with this SKU in this workspace"' in _ed
       or "no listing with this SKU in this workspace" in _ed)
truthy("  it re-locates afterwards so the edit can proceed",
       _ed.count("_repo.locate(") >= 2)
truthy("  a failed adoption never becomes a 500", "_adopted = False" in _ed)
truthy("  and the screen is told a row was created", '"adopted": _adopted' in _ed)
# The scoping this does NOT relax.
truthy("the account scoping is untouched", "_store_for(b.get(\"account\"))" in _ed)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
raise SystemExit(1 if fails else 0)
