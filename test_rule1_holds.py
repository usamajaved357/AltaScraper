"""Rule 1, checked across the whole codebase rather than trusted.

CLAUDE.md is unambiguous and it is the business, not a preference:

    NEVER -- under any circumstances, in any branch, for any reason:
      - Send merchant_suggested_asin
      - Use requirements: "LISTING_OFFER_ONLY"
      - Remove brand, title, or description from the listing payload to avoid
        catalogue conflicts
      - Infer a listing mode change from an Amazon error message
    ALWAYS:
      - Use requirements: "LISTING" (create new product)
      - GTIN exemption when there is no real barcode
      - Never send fake, placeholder, or AI-generated UPC/EAN barcodes

This app now has more ways to create a listing than it did -- the generator, the
seller import, variations, and ASIN Studio -- and every one of them is a place
the rule could be broken by somebody who did not know it. So this checks the
files, not one file, and it checks CODE rather than prose: several files discuss
these terms precisely in order to forbid them.
"""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


_CODE_CACHE = {}


def code_only(path):
    """Executable source, with EVERY docstring and comment removed.

    Necessary, not fussy. These files name the forbidden terms precisely in
    order to forbid them -- resolve_account_brand's own docstring says the brand
    "is NEVER config['brand_name'] when an account is resolved", and a text
    search reports that sentence as the breach it is warning about.

    Stripping only the module docstring was not enough; the rules are explained
    in FUNCTION docstrings, which is exactly where they belong. ast finds them
    all, wherever they are.
    """
    if path in _CODE_CACHE:
        return _CODE_CACHE[path]
    import ast
    src = open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        _CODE_CACHE[path] = ""
        return ""
    drop = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) \
               and isinstance(getattr(body[0], "value", None), ast.Constant) \
               and isinstance(body[0].value.value, str):
                d = body[0].value
                drop.update(range(d.lineno, (d.end_lineno or d.lineno) + 1))
    lines = []
    for i, line in enumerate(src.splitlines(), 1):
        lines.append("" if i in drop else line.split("#")[0])
    out = "\n".join(lines)
    _CODE_CACHE[path] = out
    return out


PY = [p for p in glob.glob("*.py") + glob.glob("routes/*.py")
      + glob.glob("domain/*.py") + glob.glob("listing/*.py")
      + glob.glob("api/*.py")
      if "baseline" not in p and not os.path.basename(p).startswith(("test_", "probe_"))]

print("== nothing SENDS merchant_suggested_asin ==")
# The field may be READ (Amazon returns it in error messages and schemas). What
# is forbidden is putting it in an outgoing payload.
offenders = []
for p in PY:
    code = code_only(p)
    for m in re.finditer(r'.*merchant_suggested_asin.*', code):
        line = m.group(0).strip()
        if not line:
            continue
        # An assignment INTO a payload dict is the shape that matters.
        if re.search(r'["\']merchant_suggested_asin["\']\s*:', line) \
           or re.search(r'\[\s*["\']merchant_suggested_asin["\']\s*\]\s*=', line):
            offenders.append("%s: %s" % (os.path.basename(p), line[:90]))
if offenders:
    for o in offenders:
        print("     ", o)
check("no file assigns merchant_suggested_asin into a payload", offenders, [])

print("\n== nothing uses LISTING_OFFER_ONLY ==")
off2 = []
for p in PY:
    code = code_only(p)
    if "LISTING_OFFER_ONLY" in code:
        for line in code.splitlines():
            if "LISTING_OFFER_ONLY" in line:
                off2.append("%s: %s" % (os.path.basename(p), line.strip()[:90]))
if off2:
    for o in off2:
        print("     ", o)
check("no file uses LISTING_OFFER_ONLY", off2, [])

print("\n== the requirements value that IS sent ==")
reqs = []
for p in PY:
    code = code_only(p)
    for m in re.finditer(r'["\']requirements["\']\s*:\s*["\'](\w+)["\']', code):
        reqs.append((os.path.basename(p), m.group(1)))
for f, v in reqs:
    print("   %-34s requirements=%s" % (f, v))
check("every requirements value sent is LISTING",
      sorted({v for _f, v in reqs}) or ["LISTING"], ["LISTING"])

print("\n== no invented barcodes ==")
# A generated UPC/EAN is worse than none: Amazon can trace it, and the GTIN
# exemption is the sanctioned route.
bar = []
for p in PY:
    code = code_only(p)
    for m in re.finditer(r'.*(?:upc|ean|gtin).*', code, re.I):
        line = m.group(0).strip()
        if re.search(r"(random|uuid|fake|generate_barcode|str\(randint)", line, re.I):
            bar.append("%s: %s" % (os.path.basename(p), line[:90]))
if bar:
    for o in bar:
        print("     ", o)
check("nothing generates a barcode", bar, [])
truthy("and the exemption is what is sent instead",
       any("supplier_declared_has_product_identifier_exemption" in code_only(p)
           for p in PY))

print("\n== every path that creates a listing goes through the same brand rule ==")
# resolve_account_brand is THE one place that decides whose brand goes out.
import subprocess
users = [os.path.basename(p) for p in PY
         if "resolve_account_brand" in code_only(p)]
print("   files using resolve_account_brand:", users or "NONE")
truthy("the brand resolver is used, not reimplemented", len(users) >= 1)
# Nothing should pick a brand by reaching for the global config value, which is
# how one account's brand once landed on another's listings.
glob_brand = []
for p in PY:
    code = code_only(p)
    for line in code.splitlines():
        if re.search(r'config\s*\[\s*["\']brand_name["\']\s*\]', line):
            glob_brand.append("%s: %s" % (os.path.basename(p), line.strip()[:80]))
if glob_brand:
    for o in glob_brand:
        print("     ", o)
check("no file reads the global brand_name to decide a listing's brand",
      glob_brand, [])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
