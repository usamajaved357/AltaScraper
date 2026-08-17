"""One cost, set once, reaching every figure that uses cost.

"i am concirned that after putting the cogs in the listngs section for an item
 will reflect right data about profits and all wherever cogs have a roll"

It did not, and there were two reasons.

BUG 1 -- A PHANTOM SECOND COPY OF THE OVERRIDES.

The manual costs lived in dashboard.py as a module-level dict, and other modules
reached them with `import dashboard as _d; getattr(_d, "_COGS_OVERRIDE")`.

dashboard.py is the file that is RUN, so its module name is "__main__".
`import dashboard` does not find the running module -- it loads the file a SECOND
time, as a separate module object, with its own `_COGS_OVERRIDE = {}` that
nothing ever fills (`_load_cogs_overrides()` is called from main(), which the
duplicate never runs).

routes/sales_routes.py and routes/orders_routes.py both did this. So the Sales
figures and the Orders profit/margin/ROI columns ignored every manual cost that
had ever been set -- silently.

MEASURED on jack_uk, setting 46 pcs wrench = 12.34 through /cogs/set:
    repricer landed cost   None -> 12.34      reached it
    cost sheet             ""   -> 12.34      reached it
    sales cost coverage    46   -> 46         DID NOT           <-- the bug
and the same coverage call made in-process answers 47.

BUG 2 -- THE LISTINGS ROW CARRIED NO COST AT ALL.

/rows returned no cogs field, so after a reload the cell fell back to reading
the SKU prefix. Worse than blank: for a SKU whose name carries a number the cell
then showed THAT, so a hand-typed override looked as though it had been thrown
away -- on the very screen it was typed on.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-70s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)
def falsy(l, g): check(l, bool(g), False)

from domain import cogs_store as CS
from domain import cogs as C

TMP = tempfile.mkdtemp(prefix="altacogs_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))

print("=== the store keeps them beside config.json ===")
check("one known filename", os.path.basename(CS.path_for(CFG)),
      "cogs_overrides.json")
check("  beside the config", os.path.dirname(CS.path_for(CFG)), TMP)
check("one key shape, agreed by everyone", CS.key("acct", "SKU-1"), "acct::SKU-1")

print("\n=== set, read, clear ===")
CS.load(CFG, force=True)
check("nothing to begin with", CS.all_overrides(CFG).get("a::S1"), None)
v, ok = CS.set_cost(CFG, "a", "S1", 7.50)
check("a cost is stored", (v, ok), (7.50, True))
check("  and readable", CS.all_overrides(CFG).get("a::S1"), 7.50)
truthy("  and written to disk", os.path.exists(CS.path_for(CFG)))
check("  as the same number", json.load(open(CS.path_for(CFG))).get("a::S1"), 7.50)
v, ok = CS.set_cost(CFG, "a", "S1", None)
check("clearing removes it", (v, ok), (None, True))
check("  from the dict", "a::S1" in CS.all_overrides(CFG), False)

print("\n--- what is refused rather than stored ---")
# Stored as text, every reader's float() call fails and the cost silently becomes
# "not known" -- for a cost that was typed and accepted.
check("text is refused", CS.set_cost(CFG, "a", "S2", "not a number"), (None, False))
check("  and nothing is stored", "a::S2" in CS.all_overrides(CFG), False)
check("a negative cost is refused", CS.set_cost(CFG, "a", "S3", -1)[1], False)
check("zero IS allowed — free stock is a real answer",
      CS.set_cost(CFG, "a", "S4", 0)[0], 0.0)
CS.set_cost(CFG, "a", "S4", None)

print("\n=== THE DICT IS NEVER REPLACED, only filled ===")
# Something registered at startup is holding this dict. Rebinding the name would
# leave it pointing at one that never changes again -- which is the other half of
# the bug in the docstring.
held = CS.all_overrides(CFG)
CS.set_cost(CFG, "a", "S5", 3.25)
check("a reference taken earlier sees the new cost", held.get("a::S5"), 3.25)
CS.load(CFG, force=True)
check("  and still does after a reload", held is CS.all_overrides(CFG), True)
check("  with the value intact", held.get("a::S5"), 3.25)
S = open(r"D:\AltaScraper\domain\cogs_store.py", encoding="utf-8").read()
truthy("loading mutates in place", "_OVERRIDES.clear()" in S and "_OVERRIDES.update(" in S)
truthy("  and the reason is written down", "would leave it pointing at the old one" in S)

print("\n=== nobody reaches for dashboard to get them any more ===")
# That import is what produced the phantom empty copy.
def _code_lines(src):
    """Lines that are neither blank nor a comment. The prose still NAMES the old
    import, in the docstrings recording why it was wrong, and a test that forbids
    naming a bug deletes the reason it was fixed."""
    return [l for l in src.split("\n")
            if l.strip() and not l.strip().startswith("#")]

for f in ("routes/sales_routes.py", "routes/orders_routes.py",
          "routes/cogs_routes.py"):
    src = open(os.path.join(r"D:\AltaScraper", f), encoding="utf-8").read()
    live = "\n".join(l for l in _code_lines(src)
                     if l.strip().startswith(("import ", "from ")))
    falsy("%-28s never imports dashboard" % f, "dashboard" in live)
    truthy("  it asks the store instead", "cogs_store" in src)

D = open(r"D:\AltaScraper\dashboard.py", encoding="utf-8").read()
truthy("dashboard's own dict IS the store's dict",
       "_COGS_OVERRIDE = _cogs_store_mod.all_overrides()" in D)
_loader = D.split("def _load_cogs_overrides")[1].split("\ndef ")[0]
# Code, not the docstring: the docstring says the words "global _COGS_OVERRIDE"
# in the sentence explaining what it used to do and why that was wrong.
_loader_code = "\n".join(l for l in _loader.split("\n")
                         if l.strip().startswith(("from ", "import ", "_cs.", "global ")))
falsy("  and the loader no longer rebinds it", "global _COGS_OVERRIDE" in _loader_code)
truthy("  it delegates to the store", "_cs.load(CONFIG_PATH)" in _loader)
truthy("  with the module-identity trap recorded", 'its name is\n#   "__main__"' in D
       or 'so its name is' in D)

print("\n=== the listings row carries the cost, and where it came from ===")
truthy("_card attaches it", "**_card_cogs(" in D)
truthy("  from the one resolver, not a second read of the SKU",
       "_c.resolve(_COGS_OVERRIDE" in D)
truthy("  and says which it is", '"cogs_source": src' in D)
truthy("  with the reason recorded",
       "disappeared from the screen it was typed on" in D)

print("\n=== and the resolver's precedence is unchanged ===")
# A typed cost beats the SKU; the SKU beats nothing; 0.00 in a SKU means UNKNOWN.
check("a manual cost wins", C.resolve({"a::9.99_3Days_B0X": 4.0}, "a",
                                      "9.99_3Days_B0X"), (4.0, "manual"))
check("otherwise the SKU is read", C.resolve({}, "a", "9.99_3Days_B0X"),
      (9.99, "sku"))
check("0.00 in a SKU is unknown, not free", C.resolve({}, "a", "0.00_3Days_B0X"),
      (None, ""))
check("a hand-made SKU has no cost", C.resolve({}, "a", "46 pcs wrench"),
      (None, ""))

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
