"""A listing already selling on Amazon has as much right to a correct badge.

    "i see ip hold and ip high symbols on many items where it does not have to
     be check and fix them"

The IP rules were corrected so that only EVIDENCE holds a listing. That fixed
what the check DECIDES -- and changed nothing on screen, because the rescan that
carries a corrected rule to already-generated rows skipped any row whose status
it did not own.

Measured on the 295 stored listings: of the 72 rows carrying an IP flag, 37 were
LIVE, APPROVED, SUBMITTED or API_ERROR. Seventeen of jack_uk's twenty were LIVE.
Every one of them was unreachable -- wearing an IP: HIGH badge from a rule that
no longer makes that finding, with no way to clear it short of editing the
database by hand.

The distinction this file pins:

    Status            Amazon's state, or the operator's decision. NEVER rewritten
                      on an APPROVED / LIVE / ERROR / API_* row.
    Notes             This app's own verdict about its own copy. Correctable on
    Compliance Risk   any row, because a stale verdict is not a fact about the
    IP Risk           listing -- it is a fact about a rule we have since fixed.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

from amazon_listing_generator import load_ip_rules
from listing import flags

IPR = load_ip_rules()
CRULES = {}

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


# A perfectly ordinary listing that the OLD rules held: "compatible with" is
# pointed at a generic noun, and the capitalised words are its own feature list.
CLEAN = {
    "SKU": "9.99_3Days_B0TEST0001",
    "Title": "Garden Hose Connector Set Brass 3/4 Inch",
    "Bullet 1": "FITS UK TAPS — Compatible with standard garden tap outlets "
                "commonly found on UK properties.",
    "Bullet 2": "COMPLETE KIT — Three Modes, Battery Indicator, Tripod Base, "
                "Hanging Hook, Magnetic Mount and Carry Strap.",
    "Description (HTML)": "<p>Solid brass, built to last.</p>",
    "Search Terms / KW": "garden hose connector brass",
    "Brand": "AltaboltaVoo",
    "Product Type": "GARDEN_HOSE",
    "Notes": "IP RISK | phrases: compatible with | possible brand words "
             "(unconfirmed): Modes, Battery, Tripod, Base, Hanging, Hook",
    "Compliance Risk": "",
    "IP Risk": "HIGH",
}

print("== a row the flags own is corrected outright ==")
r = flags.rescan_row(dict(CLEAN, Status="IP_HOLD"), IPR, CRULES)
check("the status is ours to rewrite", r["status_owned"], True)
check("  so the hold is lifted", r["new"]["status"], "NEEDS_REVIEW")
check("  and the badge goes", r["new"]["ip_risk"], "")
check("  and both are reported as changed",
      {"status", "ip_risk"} <= r["changed"], True)

print("\n== a LIVE row keeps its status and STILL loses the wrong badge ==")
live = flags.rescan_row(dict(CLEAN, Status="LIVE"), IPR, CRULES)
check("the status is NOT ours", live["status_owned"], False)
check("  so LIVE stays LIVE", live["new"]["status"], "LIVE")
check("  and status is not in the write list", "status" in live["changed"], False)
# The whole point: this used to be skipped and the badge stayed forever.
check("  but the badge is corrected", live["new"]["ip_risk"], "")
check("  and that IS in the write list", "ip_risk" in live["changed"], True)

for st in ("APPROVED", "SUBMITTED", "API_ERROR", "API_READY", "ERROR"):
    row = flags.rescan_row(dict(CLEAN, Status=st), IPR, CRULES)
    check("%s keeps its status" % st, row["new"]["status"], st)
    check("  and still gets a correct badge", row["new"]["ip_risk"], "")

print("\n== a row that SHOULD be held still is, at any status ==")
GUILTY = dict(CLEAN)
GUILTY["Bullet 1"] = ("WORKS WITH YOUR PHONE — Works with recent iPhone 12, 13 "
                      "and 14 series models.")
for st in ("NEEDS_REVIEW", "LIVE"):
    g = flags.rescan_row(dict(GUILTY, Status=st, **{"IP Risk": ""}), IPR, CRULES)
    check("a real trademark leak is still flagged (%s)" % st, g["new"]["ip_risk"], "HIGH")
check("  and a NEEDS_REVIEW row is held for it",
      flags.rescan_row(dict(GUILTY, Status="NEEDS_REVIEW"), IPR, CRULES)["new"]["status"],
      "IP_HOLD")
check("  while a LIVE one is flagged but not re-statused",
      flags.rescan_row(dict(GUILTY, Status="LIVE"), IPR, CRULES)["new"]["status"], "LIVE")

print("\n== notes this module does not own are never dropped ==")
KEEP = dict(CLEAN, Status="LIVE")
KEEP["Notes"] = ("Amazon said: item_type_keyword is invalid | "
                 + CLEAN["Notes"] + " | operator: checked by hand 3 Aug")
k = flags.rescan_row(KEEP, IPR, CRULES)
check("Amazon's own feedback survives",
      "Amazon said: item_type_keyword is invalid" in k["new"]["notes"], True)
check("  and so does an operator's note",
      "operator: checked by hand 3 Aug" in k["new"]["notes"], True)
# The capitalised-word finding is NOT deleted -- it is deliberately still
# reported, because hiding it would trade one wrong answer for another. What
# changes is that it no longer claims to be a risk: the segment is rebuilt under
# an "IP NOTE (no hold)" head instead of "IP RISK", and the badge beside it is
# blank. Asserting it disappeared would have pinned behaviour this app does not
# have and should not have.
check("  the stale IP RISK verdict is gone",
      "IP RISK" in k["new"]["notes"], False)
check("  replaced by a note that admits it is not a hold",
      "IP NOTE (no hold)" in k["new"]["notes"], True)
check("  with the finding still visible",
      "possible brand words" in k["new"]["notes"], True)
check("  and it is not written twice",
      k["new"]["notes"].count("possible brand words"), 1)

print("\n== the route writes every changed row, not only the ones it may re-status ==")
src = open(r"D:\AltaScraper\routes\listing_routes.py", encoding="utf-8").read()
check("the filter is on what changed", 'if res["changed"]:' in src, True)
check("  not on whether the status is ours",
      'if res["eligible"] and res["changed"]' in src, False)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
