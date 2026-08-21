"""A cost sheet is read in ONE place, and `price` is not a cost.

    COGS defect 3 of the three deferred on 18 Aug 2026: "two upload paths, two
    CSV parsers, and cogs.js accepts a column named `price`."

THE ONE THAT COULD HAVE COST REAL MONEY. static/js/cogs.js had its own CSV
parser and its own list of column names to accept as the cost. The last name on
that list was a bare `price`. On an Amazon listings export (the file anybody
would reach for when asked for a sheet of their SKUs) `price` is the SELLING
price. Uploading one set every SKU's cost to what it sells for. Every product on
the account would then show a loss of roughly its own Amazon fee -- no error,
nothing on screen to say what had happened, and the figure that changed is the
one every profit, margin and ROI in the app is built on.

domain/cogs.COST_COLS has never accepted a bare `price`. Only the browser copy
did. That is what a second implementation of the same rule is for.

The browser parser was the weaker reader in every other way too: CSV only,
no currency symbols, no thousands separator, and blind to whether a SKU matched
anything on the account. domain/source_bulk.read_table does all of it and was
already what /cogs/upload_sheet used.

AND THE TWO WRITE PATHS DISAGREED ABOUT WHAT A COST IS. /cogs/upload put the
value straight into _COGS_OVERRIDE and saved the file itself -- the exact shape
of the bug domain/cogs_store.py exists to end. float("-3") is a perfectly good
float, so a negative cost went in through that route and was refused through
every other one.
"""
import ast
import json
import os
import subprocess
import sys
import tempfile

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


def read(*p):
    return open(os.path.join(HERE, *p), encoding="utf-8").read()


JS = read("static", "js", "cogs.js")
RT = read("routes", "cogs_routes.py")
CODE = "\n".join(l.split("//")[0] for l in JS.splitlines()
                 if not l.strip().startswith(("*", "/*", "//")))

print("== `price` is not a cost column, anywhere ==")
from domain import cogs as _cogs
falsy("domain/cogs.COST_COLS does not accept a bare 'price'",
      "price" in _cogs.COST_COLS)
truthy("  it does accept the ones that are unambiguous",
       "cost" in _cogs.COST_COLS and "cogs" in _cogs.COST_COLS)
falsy("the browser no longer has its own list either",
      '"sourcecost", "price"' in CODE or "'sourcecost', 'price'" in CODE)

# The thing itself: a real Amazon listings export must be refused outright.
from domain import source_bulk as _sb
amz = ("seller-sku,asin1,item-name,price,quantity\n"
       "15.10_2Days_B0F7D29MFZ,B0F7D29MFZ,\"Grill, Large\",29.99,4\n")
h, rows, err = _sb.read_table(amz.encode("utf-8"), "listings.csv")
rep = _cogs.apply_sheet("config.json", "jack_uk", "A1F83G8C2ARO7P", h, rows)
falsy("an Amazon listings export is refused as a cost sheet", rep.get("ok"))
truthy("  and says which column it wanted", "cost" in str(rep.get("error", "")))

print("\n== ONE reader, and it is the server's ==")
falsy("the browser's CSV splitter is gone", "_cgSplit" in JS)
falsy("  and nothing calls it", "_cgSplit(" in CODE)
truthy("the file itself is posted", "FormData" in CODE)
truthy("  to /cogs/upload_sheet", '"/cogs/upload_sheet"' in CODE)
falsy("  not to the rows endpoint", '"/cogs/upload"' in CODE)
truthy("the server reads it with source_bulk", "_sb.read_table" in RT)

print("\n== the quoted comma that started this ==")
# "A product name like 'Grill, Large' is quoted and contains one, so every
# column after it shifted and the cost was read from the wrong place."
good = ('sku,asin,product,cost,cost now,where from\n'
        '15.10_2Days_B0F7D29MFZ,B0F7D29MFZ,"Grill, Large",£12.50,15.10,eBay\n'
        'BLANKROW,,"Untouched",,,\n')
h2, rows2, _e = _sb.read_table(good.encode("utf-8"), "costs.csv")
rep2 = _cogs.apply_sheet("config.json", "jack_uk", "A1F83G8C2ARO7P", h2, rows2)
check("a quoted comma does not shift the columns",
      rep2["columns"]["cost"], "cost")
check("  'cost' is read, not 'cost now'", rep2["columns"]["cost"], "cost")
_set = [r for r in rep2["rows"] if r["status"] == "set"]
check("  and a pound sign is read as money",
      _set[0]["detail"].split(" ")[0] if _set else None, "12.50")
check("a blank cost is skipped, never zeroed", rep2["skipped"], 1)
falsy("  and no zero was produced", any(v == 0 for v in
                                        (rep2.get("updates") or {}).values()))

print("\n== nothing is written until it is confirmed ==")
from domain import cogs_store as _cs
_before = dict(_cs.all_overrides("config.json"))
_cogs.apply_sheet("config.json", "jack_uk", "A1F83G8C2ARO7P", h2, rows2)
check("apply_sheet itself writes nothing",
      dict(_cs.all_overrides("config.json")), _before)
truthy("the route has a dry run", 'request.form.get("dry_run")' in RT)
# The CODE, not the docstring above it that also says "dry_run".
_body = RT.split("dry = str(request.form")[1][:400]
truthy("  which drops the updates before answering",
       'rep.pop("updates", None)' in _body and "if dry:" in _body)
truthy("the browser asks twice: once to look, once to do",
       "_cgPost(f, true)" in CODE and "_cgPost(f, false)" in CODE)
truthy("  and the confirmation quotes the server's own count",
       "dry.set" in CODE)
truthy("  and names the column it read as the cost", "cols.cost" in CODE)

print("\n== one way IN to the store, so a cost cannot hide from a screen ==")
truthy("/cogs/upload goes through cogs_store", "_cs.set_cost(" in RT)
falsy("  and no longer writes the dict itself",
      "_COGS_OVERRIDE[" in RT)
falsy("  nor saves it separately", "_save_cogs_overrides()" in RT)
check("every write in the file is the store's", RT.count("_cs.set_cost("), 3)
truthy("a refused row is reported rather than dropped", '"refused"' in RT)

# Exercise it: the store refuses what the old path accepted.
check("the store refuses a negative cost",
      _cs.set_cost("config.json", "__t__", "__s__", -1), (None, False))
check("  and text", _cs.set_cost("config.json", "__t__", "__s__", "abc"),
      (None, False))
_v, _ok = _cs.set_cost("config.json", "__t__", "__s__", 4.25)
check("  and accepts a real one", (_v, _ok), (4.25, True))
truthy("  visible through the reference handed out at startup",
       _cs.all_overrides().get("__t__::__s__") == 4.25)
_cs.set_cost("config.json", "__t__", "__s__", None)
falsy("  and clearing removes it", "__t__::__s__" in _cs.all_overrides())
check("the file is back as it was", dict(_cs.all_overrides("config.json")),
      _before)

print("\n== a SKU that is on nothing here is named, not swallowed ==")
# "a hand-typed SKU is one that silently matches nothing" -- the cost is still
# stored, because the catalogue snapshot is not the whole truth, but it is
# counted and said out loud.
typo = ('sku,cost\n15.10_2Days_B0F7D29MFZ,12.50\nDEFINITELY_NOT_A_SKU,7.00\n')
h3, rows3, _e3 = _sb.read_table(typo.encode("utf-8"), "t.csv")
rep3 = _cogs.apply_sheet("config.json", "jack_uk", "A1F83G8C2ARO7P", h3, rows3)
check("the typo is counted", rep3.get("unknown_sku"), 1)
check("  the real SKU is not", len([r for r in rep3["rows"]
                                    if r.get("unknown_sku")]), 1)
check("  and it is still set, not lost", rep3["set"], 2)
truthy("known SKUs include ones that have SOLD, not just the snapshot",
       "FROM order_lines" in read("domain", "cogs.py"))
truthy("  and the screen says so", "unknown_sku" in CODE)
# A single-line fragment: the sentence is split across two source lines, and
# matching across the break is how these assertions keep failing on correct code.
truthy("  without calling it unusable", "stored, but check for a typo" in JS)

print("\n== the two counters are not described as the same thing ==")
# unmatched = an ASIN-only row matching nothing, so there is no SKU to write to.
# unknown_sku = a SKU that was typed, will be written, and is on nothing here.
truthy("unmatched is described as the ASIN case",
       "only an ASIN" in JS or "give only an ASIN" in JS)
truthy("unknown_sku is described as the typo case", "typo" in JS)

print("\n== the upload button offers the files the reader can open ==")
H = read("templates", "dashboard.html")
_inp = H.split('id="cogs_file"')[1][:160]
truthy("spreadsheets are offered", ".xlsx" in _inp)
truthy("  and CSV still is", ".csv" in _inp)
truthy("read_table really does open xlsx", "openpyxl" in read("domain",
                                                             "source_bulk.py"))

print("\n== the renderer still runs ==")
probe = r"""
const fs=require("fs"),vm=require("vm");
globalThis.document={getElementById:()=>({value:"",click(){},files:[]}),
                     createElement:()=>({innerHTML:"",querySelector:()=>null}),
                     addEventListener(){}};
globalThis.addEventListener=function(){}; globalThis.window=globalThis;
globalThis.FormData=function(){this.append=function(){}};
globalThis.fetch=()=>Promise.resolve({json:()=>Promise.resolve({ok:true})});
vm.runInThisContext(fs.readFileSync("static/js/cogs.js","utf8"),{filename:"cogs.js"});
const r={set:412,skipped:3,unmatched:2,unknown_sku:1,columns:{cost:"cost",sku:"sku"},
         rows:[{row:2,sku:"A",status:"not a number",detail:"could not read 'x'"}]};
const s=_cgSummary(r);
console.log(JSON.stringify({len:s.length, hasSkipped:/3 rows/.test(s),
  hasUnmatched:/2 rows/.test(s), hasUnknown:/1 SKU/.test(s),
  hasBad:/could not be read/.test(s),
  emptyIsEmpty:_cgSummary({rows:[]})===""}));
"""
try:
    fd, path = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, probe.encode("utf-8"))
    os.close(fd)
    out = subprocess.run(["node", path], capture_output=True, text=True, cwd=HERE)
    os.unlink(path)
    if out.returncode != 0:
        fails.append("cogs.js threw")
        print("  FAIL cogs.js threw:", (out.stderr or "")[:300])
    else:
        g = json.loads(out.stdout.strip().splitlines()[-1])
        truthy("the summary names the skipped rows", g["hasSkipped"])
        truthy("  the unmatched rows", g["hasUnmatched"])
        truthy("  the unknown SKUs", g["hasUnknown"])
        truthy("  and the unreadable costs", g["hasBad"])
        truthy("a clean file gets no warnings at all", g["emptyIsEmpty"])
except FileNotFoundError:
    print("  (node not on this machine -- not exercised)")
except Exception as e:
    fails.append("cogs.js probe")
    print("  FAIL probe:", str(e)[:200])

print("\n== both routes still exist ==")
tree = ast.parse(RT)
routes = {d.args[0].value
          for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
          for d in n.decorator_list
          if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "route"
          and d.args and isinstance(d.args[0], ast.Constant)}
for r in ("/cogs/template.csv", "/cogs/set", "/cogs/upload", "/cogs/upload_sheet"):
    truthy("%s is still registered" % r, r in routes)
truthy("miles still posts to upload_sheet",
       "/cogs/upload_sheet" in read("static", "js", "miles_template.js"))

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
