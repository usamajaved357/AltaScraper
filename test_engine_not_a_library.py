"""The listing engine is a runner, not a library (architecture batch A1).

amazon_listing_generator.py runs as a subprocess and holds globals it changes
while it runs (MARKETPLACE_ID, MINIMAL_MODE, ...). Importing it into the web
process loads the whole generator -- and it is not needed for helpers that now
live in listing/. This pins the web-process modules that STILL import it, each
for a reason recorded in docs/architecture-audit-2026-09-29.md, so a new one
cannot creep in unnoticed. Shrink the list as the plan moves them; never grow it
without writing down why.
"""
import ast
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# module -> why it still imports the engine
STILL = {
    "dashboard.py": "starts the generator and reads its constants",
    "listing/flags.py": "check_compliance still lives in the engine",
    "listing/regen.py": "output_ws / load_* / _read_retry still live in the engine",
    "domain/generate_plan.py": "output_ws / _safe_records / load_existing_skus_and_asins still live in the engine",
    "routes/listing_routes.py": "the /suggest route's supplement and competitor fetchers still live in the engine",
}

found = set()
for d, _dirs, files in os.walk(HERE):
    rel_d = os.path.relpath(d, HERE)
    if any(p in rel_d for p in (".git", "_merge_2026-07-04", "__pycache__", "tests_support", ".claude", "tools", "scripts", "active")):
        continue
    for f in files:
        if not f.endswith(".py") or f.startswith(("test_", "probe_")) or "baseline" in f:
            continue
        rel = os.path.normpath(os.path.join(rel_d, f)).replace("\\", "/")
        if rel == "amazon_listing_generator.py" or rel.count("/") == 0 and rel not in STILL:
            continue          # root-level scripts are command-line tools, not the web process
        try:
            tree = ast.parse(open(os.path.join(d, f), "rb").read().decode("utf-8"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if (isinstance(n, ast.Import) and any(a.name == "amazon_listing_generator" for a in n.names)) or \
               (isinstance(n, ast.ImportFrom) and n.module == "amazon_listing_generator"):
                found.add(rel)

fails = []
new = sorted(found - set(STILL))
gone = sorted(set(STILL) - found)
print("web-process modules importing the engine: %d (%s)" % (len(found), ", ".join(sorted(found))))
if new:
    fails.append("new importers: %s -- import the helper from listing/ instead, or record why" % new)
if gone:
    print("  no longer importing it (take them off STILL): %s" % gone)
    fails.append("STILL lists modules that no longer import the engine: %s" % gone)
for f in ("listing/product_type.py", "data/input_row.py", "data/input_import.py", "listing/sync.py"):
    if f in found:
        fails.append("%s imports the engine again (batch A1 moved it off)" % f)
if fails:
    raise SystemExit("FAILED: " + "; ".join(fails))
print("the engine is imported only where recorded")
