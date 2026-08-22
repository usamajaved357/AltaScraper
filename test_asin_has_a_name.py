"""A product code is never shown where a product NAME belongs.

Two screens were printing machine codes at a person:

    "why do i still have that amazon seller zaayt4 in the app, that is not a
     separate account you said"
    "i see that in the traffic page Top ASINs by Sessions shows no title"

They look unrelated and share a cause: something the app could not name, so it
printed the identifier instead -- and an identifier on screen reads as a THING.
A seller ID under a workspace name reads as a second account. A column headed
"Top ASINs by Sessions" with "(no title recorded)" down it reads as broken.

The seller-ID half is only a caption. config.json has exactly ONE account
carrying A8YN8LJZAAYT4 (nestwell_goods), asserted below so this file fails if a
duplicate account ever really is created -- at which point the answer is to
delete the account, not to reword a label.

The traffic half is a real data gap and is fixed as one: see
domain/catalogue.titles.
"""
import ast
import json
import os
import re

os.chdir(os.path.dirname(os.path.abspath(__file__)))

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


SHELL = read("static/js/shell.js")
TRAF = read("static/js/traffic.js")
CAT = read("domain/catalogue.py")


def code(js):
    """The JS with its comments removed.

    Both of these files EXPLAIN the fix in a comment, quoting the wrong string
    it replaced -- so "is the old text gone?" matched the explanation of why it
    went and reported the fix as unapplied. Assert against what runs.
    """
    out, i, n = [], 0, len(js)
    while i < n:
        c = js[i]
        if c in "\"'`":                      # a string: copy it whole
            j = i + 1
            while j < n and js[j] != c:
                j += 2 if js[j] == "\\" else 1
            out.append(js[i:j + 1])
            i = j + 1
        elif js.startswith("//", i):
            i = js.find("\n", i)
            if i < 0:
                break
        elif js.startswith("/*", i):
            i = js.find("*/", i)
            i = n if i < 0 else i + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


SHELL_CODE = code(SHELL)
TRAF_CODE = code(TRAF)


print("=== A8YN8LJZAAYT4 is a caption, not an account ===")
try:
    cfg = json.loads(read("config.json"))
except Exception:
    cfg = {}
accs = cfg.get("accounts") or {}
if isinstance(accs, dict):
    accs = list(accs.values())
owners = [str(a.get("id") or a.get("name") or "?") for a in accs
          if isinstance(a, dict)
          and str(a.get("seller_id") or "").upper() == "A8YN8LJZAAYT4"]
# If this ever fails the app really did grow a duplicate account and the label
# was telling the truth. Fix the config, not this test.
check("exactly one configured account carries that seller ID", len(owners), 1)

# The caption is written in two places -- the workspace card in the switcher and
# the subtitle under the sidebar heading. Both said "Amazon account · <id>",
# which is why the same string appeared to be a second entry in a list of
# accounts. Both now name the field they are showing.
truthy("no drawn caption calls a seller ID an Amazon account",
       "Amazon account ·" not in SHELL_CODE)
truthy("  the switcher card says what the number IS",
       'Seller ID "+esc(a.seller_id)' in SHELL_CODE)
truthy("  and the sidebar subtitle says the same",
       '"Seller ID " + a.seller_id' in SHELL_CODE)
truthy("an account with no Amazon connection says so in words, in both places",
       SHELL_CODE.count("No Amazon account connected") == 2)


print("\n=== the traffic table names the product, or admits it cannot ===")
truthy("the literal placeholder is no longer drawn",
       "no title recorded" not in TRAF_CODE)
truthy("  an unnamed row falls back to the ASIN itself",
       "r.title || r.asin" in TRAF_CODE)
truthy("  and says why there is no name rather than leaving a blank",
       "not synced yet" in TRAF_CODE)


print("\n=== a name is looked for in everything that has one ===")
# The snapshot is what the refresher has read back from Amazon. Traffic lists
# everything with a SESSION, which includes products that have never sold and
# anything added since the last refresh -- so the snapshot alone cannot name the
# column. Orders carry the title Amazon used at the time.
tree = ast.parse(CAT)
fn = next((n for n in ast.walk(tree)
           if isinstance(n, ast.FunctionDef) and n.name == "titles"), None)
truthy("catalogue.titles exists", fn is not None)
body = ast.get_source_segment(CAT, fn) if fn else ""
truthy("it still reads the live snapshot", "index(config_path" in body)
truthy("  and now also what has actually sold", "FROM order_lines" in body)
truthy("  scoped to the one workspace and marketplace asked for",
       "WHERE workspace_id=? AND marketplace=?" in body)
truthy("  ignoring rows that carry no name to give",
       "COALESCE(title,'')<>''" in body)
# setdefault, not assignment: the snapshot is the CURRENT title, an order is
# whatever it was called on the day it sold.
truthy("the snapshot wins where both know the product",
       "out.setdefault(str(r[\"asin\"])" in body)
truthy("  and a missing table costs the caller nothing",
       "except Exception:" in body)

# THE TRAP. A draft row's ASIN is the COMPETITOR's -- the source the product
# facts were taken from, never ours (CLAUDE.md Rule 1). Joining its title onto
# our traffic would label our sessions with somebody else's product name.
sql = " ".join(re.findall(r'"([^"]*)"', body))
truthy("the drafts table is NOT a source of titles here",
       "FROM listings" not in sql)
truthy("  and the reason is written down where the next person will read it",
       "the ASIN on a" in CAT and "COMPETITOR" in CAT)


print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
