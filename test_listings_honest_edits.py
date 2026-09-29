"""All Listings: every field that says it edits Amazon really does, and every
one that does not says so (owner, 30 Sep 2026: "make sure every field that
indicates that this is going to be edited and will be sent to amazon after
confirmation should really do what it indicates so it should not be
misleading").

Each check fails on the code before that day's fix. Source reads are raw
(rb), so each file is checked on its own.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-72s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def src(*p):
    return open(os.path.join(HERE, *p), "rb").read().decode("utf-8").replace("\r\n", "\n")


def body(s, head, stop):
    part = s.split(head, 1)[1] if head in s else ""
    return part.split(stop, 1)[0] if stop in part else part


DA = src("static", "js", "drawer_attributes.js")
PE = src("static", "js", "priceedit.js")
LD = src("static", "js", "listrow_detailed.js")
LE = src("static", "js", "listrow_edit.js")
HJ = src("static", "js", "handling.js")
GT = src("static", "js", "gtin.js")
LP = src("static", "js", "listings_panels.js")
AF = src("static", "js", "autofix.js")
DR = src("static", "js", "drawer.js")
RQ = src("static", "js", "runqueue.js")
HP = src("listing", "handling.py")
HR = src("routes", "handling_routes.py")

print("== the drawer's send button really sends ==")
push = body(DA, "async function lvPushChanges(", "\n/* The strip")
check("through Submit, built from the product type's schema",
      "await submitOne(sku)" in push and '"/optimize/push"' not in push, True)
check("  and the button says it submits", "'Submit to send ' + _unsent" in DA, True)

print("\n== the price panel ==")
check("typing drops the stale preview (Enter cannot send the old figure)",
      "if(_PE) _PE.preview = null;" in PE, True)
send = body(PE, "async function priceEditSend(", "\n}\n")
check("  and Send re-checks the figure in the box", "_peTyped() !== j.new" in send, True)
check("'Sells for now' is Amazon's live price, not the app's record",
      "Sells for now</div>" not in PE and '"On Amazon now"' in PE, True)
check("  the sent price is shown at once", "applyPushedLocally([sku], null, {price: r.now})" in PE, True)

print("\n== the detailed view's price box ==")
check("its tooltip no longer claims to be the listing's price",
      '"The price on the listing")\n    + lrFloorCeiling' not in LD
      and "NOT sent to \"\n                    + \"Amazon\"" in LD, True)
check("  and a live listing gets the real path beside it",
      "Change on Amazon</button>" in LD and "priceEdit(' + jsArg(r.sku)" in LD, True)

print("\n== stock, handling, % price ==")
check("the stock box names its marketplace (Rule 14)",
      "if(_mkt) body.marketplace = _mkt;" in LE, True)
check("handling pins the account before its dialog",
      "const _pin = _handlingScope();" in HJ and "_handlingPost({skus, days, push:true, sheet:true}, _pin)" in HJ, True)
check("% price pins it too", "const _pinScope = _handlingScope();" in HJ, True)
check("headlines are what Amazon took, of how many",
      HJ.count("changed on Amazon for ") >= 3, True)
check("a whole-request refusal is said with its reason",
      HJ.count('"Nothing was sent to Amazon:\\n\\n"') >= 2, True)
check("a reply with no status is not 'changed'",
      'status in ("ACCEPTED", "VALID")' in HP and 'status in ("ACCEPTED", "VALID", "")' not in HP, True)
check("a push that will be refused is refused before the local write",
      HR.index("_pacc, _pmkt, _pbad = _push_target()") < HR.index("# --- 1) record it here ---"), True)

print("\n== the GTIN exemption tick (Rule 1: the owner's click) ==")
check("it says it is claimed at submit, and only without a valid barcode",
      "claimed when this listing is submitted" in GT and "valid one is sent instead" in GT, True)
check("  and 'will be claimed' is gone", "GTIN exemption will be claimed for this listing" in GT, False)
check("  a failed save un-ticks the box", "_undo(); toast((j && j.error)" in GT
      and "setGtinExemption(' + _sarg2(r.sku) + ', this.checked, this)" in LP, True)
check("  the bulk reply says ticked, not applied",
      '"GTIN exemption applied to "' in GT, False)

print("\n== saves that are only this app's say so ==")
check("Save all saves every staged change, drawn or not",
      "Object.keys(LR_EDITS || {}).forEach" in LE
      and 'document.querySelectorAll("input.lr-edit.dirty").forEach' not in LE, True)
check("a drawer edit on a live listing says it was not sent",
      "not sent to Amazon yet; the live listing changes when you Submit it" in AF, True)
check("a failed title save can be tried again",
      'if(j && j.ok) el.setAttribute("data-orig", v);' in DR, True)
check("a preview says nothing was sent", "Nothing was sent: Submit publishes it." in RQ
      and "Amazon accepted this listing" not in RQ, True)

print("\nFAILURES: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
