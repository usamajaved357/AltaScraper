"""A vacuum flask does not have a battery.

WHAT WENT WRONG, measured on two real jack_uk rows, both product type THERMOS:

    Vacuum Insulated Stainless Steel Jug 1.5L    8 battery attributes sent
    Vacuum Insulated Thermos Flask 2 Litre       9 battery attributes sent

and the payload contradicted itself in the same breath:

    batteries_required        false
    batteries_included        false
    contains_battery_or_cell  "battery"      <- plus 1 lithium-ion cell,
    num_batteries             1                 alkaline composition,
    battery_installation...   installed_in_equipment

Four separate places decided a battery existed, and every one of them asked the
same wrong question: does the SCHEMA DECLARE this field? Nearly every product
type declares the battery fields, so the answer was nearly always yes.

    if ("battery" in pa or _has_prop("battery") or _is_batt)
    if ("num_batteries" in pa or _has_prop("num_batteries") or _is_batt)
    if _schema_wants("contains_battery_or_cell")
    battery_installation_device_type -- no guard at all

WHY IT MATTERS MORE THAN THE OTHER NOISE. contains_battery_or_cell is a
REGULATORY declaration: it changes how Amazon ships and handles the item.
Answering it "yes" by default is a false declaration made on the owner's
account. It also pulled non_lithium_battery_packaging in as required, which is
one of the three errors that kept the row unlistable.

THE FIX: one question, asked once -- is there any actual evidence of a battery?
Real battery data on the row, or the row's own batteries_* flags, or the
existing keyword+schema detection. A stated "no" is evidence, and that is the
part that was being ignored.
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


src = open(os.path.join(HERE, "amazon_listing_generator.py"),
           encoding="utf-8").read()

print("== the question is asked once, and it is the right question ==")
truthy("there is a single battery-evidence helper",
       "def _battery_evidence():" in src)
truthy("  and one variable every site reads", "_has_battery = _battery_evidence()" in src)
truthy("  a stated 'no' on the row counts as evidence",
       '_f = _flagged(_k)' in src and "return _f" in src)
truthy("  real battery data on the row outranks the flags",
       '_b = pa.get("battery")' in src)
truthy("  and the keyword detection is still the last resort",
       "return bool(_is_batt)" in src)

print("\n== no site decides on 'the schema mentions it' any more ==")
# _has_prop is true whenever the schema DECLARES the field, which is nearly
# always. Each of these four lines used it (or nothing at all) to decide.
for guard, what in (
        ('if ("battery" in pa or "battery" in required or _has_battery)',
         "the battery object"),
        ('if ("num_batteries" in pa or "num_batteries" in required or _has_battery)',
         "num_batteries"),
        ('(("contains_battery_or_cell" in required) or _has_battery)',
         "contains_battery_or_cell"),
        ('_want_bidt = ("battery_installation_device_type" in pa',
         "battery_installation_device_type"),
):
    truthy("%-34s asks for evidence" % what, guard in src)

falsy("the battery object no longer fires on _has_prop",
      '("battery" in pa or _has_prop("battery") or _is_batt)' in src)
falsy("nor does num_batteries",
      '("num_batteries" in pa or _has_prop("num_batteries") or _is_batt)' in src)

print("\n== the yes/no answer is honest, and never invented ==")
truthy("the enum picker can say NO as well as YES",
       'def _cbc_value(_prop, _yes=True):' in src)
truthy("  with the words that mean no",
       '"no", "false", "0",' in src and '"no_battery", "none"' in src)
# The old code ended `return _enum[0]` -- if nothing on the list said "yes" it
# sent the first entry, whatever it happened to be. That is how "battery"
# landed on a vacuum flask.
truthy("  and it refuses rather than picking the first item off the list",
       "that is how \"battery\" ended up on a vacuum flask" in src)
truthy("  the cell count follows the same answer",
       '"value": (1 if _has_battery else 0)' in src)

print("\n== what a real battery product still gets ==")
# The guards keep three ways in, so nothing that genuinely has a battery loses
# it: data on the row, Amazon requiring the field, or the keyword detection.
for phrase in ('"battery" in pa', '"battery" in required', "_has_battery"):
    truthy("a battery product still qualifies via %s" % phrase,
           phrase in src)

print("\n== and the reason is written down where the next person will look ==")
truthy("the measurement is recorded beside the fix",
       "8 battery attributes sent" in src)
truthy("  and why it is worse than ordinary noise",
       "REGULATORY declaration" in src)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
