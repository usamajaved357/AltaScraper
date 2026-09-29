"""tools/arch_rules.py -- the architecture guard's rules (29 Sep 2026).

    py -3.11 tools/arch_rules.py                    report every rule: new / legacy / fixed
    py -3.11 tools/arch_rules.py --baseline-shrink  drop FIXED legacy entries from the baseline

PURPOSE: NO NEW ARCHITECTURAL DEBT. Today's code is not failed for what it
already does (that is the BASELINE, tools/arch_baseline.json); new code is.
The target shape (docs/architecture-audit-2026-09-29.md section 2):

    browser JS -> routes/<feature> -> domain/ + listing/ -> data/ + api/

These rules cover what no existing test did (the others -- SQL in routes, the
engine as a library, one Anthropic constructor, one order-items read, atomic
JSON writes, JS name clashes, loops pinning their account, ... -- stay where
they are; docs/architecture.md section 14 lists them all).

EVERY RULE
  * says exactly what it catches (RULES below, and each function's docstring)
  * has stable keys: file + symbol (+ #n for a repeat), never a line number,
    so moving code around does not break the guard
  * allows a documented exception in a COMMENT on the statement (any of its
    lines, or its decorators, or the line above):
        # arch-ok: <rule-id> -- <reason: at least 10 non-space characters>
  * is tested against deliberate bad examples and known-good code
    (test_architecture_guard.py)

The baseline only SHRINKS: an entry whose violation is gone fails the test
until it is removed (--baseline-shrink); its size per rule is pinned in the
test, so it cannot be grown by hand or by deleting and re-creating it; and a
legacy large function that grows past its recorded size counts as new debt.
"""
import ast
import hashlib
import io
import json
import os
import re
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, "tools", "arch_baseline.json")

# The app's own packages. Root-level scripts (probes, one-off migrations) and
# tests are not the architecture; dashboard.py is checked where a rule says so.
APP_DIRS = ("routes", "domain", "listing", "data", "api", "monitor", "auth", "config")
LOWER = ("domain", "listing", "data", "api", "monitor")     # below routes/

RULES = {
    "spapi-client-outside-api":
        "An Amazon SP-API client class (sp_api.api.*) is imported outside api/, "
        "the one layer that talks to outside services. Build clients in api/ "
        "(api/sp_client, api/amazon_orders, ...). Anthropic clients are already "
        "held to one constructor by test_one_anthropic_constructor.py.",
    "routes-import-dashboard":
        "A route module imports dashboard.py. Routes get what they need injected "
        "through register(), never by importing the app module.",
    "lower-imports-upper":
        "domain/, listing/, data/, api/ or monitor/ imports routes/ or dashboard.py, "
        "or api/ imports domain/ -- the dependency points the wrong way.",
    "module-mutable-global":
        "Process-wide state at module level (also inside a module-level if/try): "
        "an EMPTY container ({} [] set() dict() list() defaultdict() deque() ...) "
        "under any name -- it exists to be filled -- or any container under a "
        "lowercase name. ALL_CAPS names holding filled literals are read-only "
        "tables by convention and are not flagged.",
    "duplicate-function":
        "Two functions (module-level, nested, or methods) in the app packages "
        "with an identical body of 5+ statements -- a second copy of a helper "
        "that already exists (Rule 12).",
    "large-function":
        "A function of more than 200 lines in the app packages or dashboard.py "
        "(a routes/ register() container excepted). A legacy one that GROWS past "
        "its recorded size + 10% + 20 lines counts as new debt.",
    "background-open-account":
        "Code below routes/ that takes the server's open account or marketplace "
        "(active_account_id / active_marketplace read from state, or a call to "
        "request_account.current / id_or_open, which fall back to it) -- a "
        "background job must be handed its account (Rule 14).",
}

LARGE_LINES = 200
DUP_MIN_STMTS = 5
_OK = re.compile(r"#\s*arch-ok:\s*([a-z-]+)\s*--\s*(.*)$")

_CACHE = {}


def _parsed(p):
    """(source, lines, tree or None, {line: comment}) -- each file read and
    parsed ONCE per process, whatever number of rules ask."""
    try:
        st = os.stat(p)
        k = (p, st.st_mtime_ns, st.st_size)
    except OSError:
        k = (p, 0, 0)
    got = _CACHE.get(k)
    if got is not None:
        return got
    with open(p, encoding="utf-8", errors="replace") as f:
        s = f.read()
    try:
        tree = ast.parse(s)
    except SyntaxError:
        tree = None
    comments = {}
    # Comments are only needed for exceptions, so only a file that mentions
    # arch-ok is tokenised (tokenising every file was most of the run time).
    if "arch-ok" in s:
        try:
            for tok in tokenize.generate_tokens(io.StringIO(s).readline):
                if tok.type == tokenize.COMMENT:
                    comments[tok.start[0]] = tok.string
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
    got = (s, s.splitlines(), tree, comments)
    _CACHE[k] = got
    return got


_DERIVED = {}


def _nodes_of(p, kind):
    """Cached per-file node lists every rule shares: 'imports' (Import and
    ImportFrom nodes, any depth) and 'functions' ((qualname, node) pairs)."""
    k = (p, kind)
    if k not in _DERIVED:
        tree = _parsed(p)[2]
        if tree is None:
            _DERIVED[k] = []
        elif kind == "imports":
            _DERIVED[k] = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        else:
            _DERIVED[k] = list(_functions(tree))
    return _DERIVED[k]


def _py_files(dirs=APP_DIRS, extra=()):
    for d in dirs:
        base = os.path.join(ROOT, d)
        for root, subdirs, files in os.walk(base):
            subdirs[:] = [x for x in subdirs if x != "__pycache__"]
            for f in sorted(files):
                if f.endswith(".py"):
                    yield os.path.join(root, f)
    for f in extra:
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            yield p


def _rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def excepted(comments, first, last, rule):
    """True when a COMMENT on lines first-1 .. last is a valid
    `# arch-ok: <rule> -- <reason>` for this rule (reason: 10+ non-space
    characters). Only real comments count -- never text inside a string."""
    for n in range(max(1, first - 1), last + 1):
        m = _OK.search(comments.get(n, ""))
        if m and m.group(1) == rule and len(re.sub(r"\s+", "", m.group(2))) >= 10:
            return True
    return False


def _span(node):
    first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return first, getattr(node, "end_lineno", None) or node.lineno


def _imports(tree):
    """(node, module) for every import, at any depth."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield node, a.name
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            yield node, node.module
            for a in node.names:
                yield node, node.module + "." + a.name


def _numbered(out, base, rel, line):
    """Append (key, rel, line) with ' #n' on the second and later repeats."""
    n = sum(1 for k, _r, _l in out if k == base or k.startswith(base + " #")) + 1
    out.append((base if n == 1 else "%s #%d" % (base, n), rel, line))


# ---------------------------------------------------------------------------
# The rules. Each -> [(key, file, lineno)]  (large-function adds its size)
# ---------------------------------------------------------------------------

def rule_spapi_client_outside_api(files=None):
    """Each SP-API client class imported (`from sp_api.api import Orders`,
    `import sp_api.api`) in a module outside api/. `sp_api.base`
    (Marketplaces, exceptions) is not a client. Key: file + class."""
    out = []
    for p in (_py_files(extra=("dashboard.py",)) if files is None else files):
        rel = _rel(p)
        if rel.startswith("api/"):
            continue
        _s, _lines, tree, comments = _parsed(p)
        if tree is None:
            continue
        for node in _nodes_of(p, "imports"):
            names = []
            if isinstance(node, ast.ImportFrom) and not node.level and node.module and \
                    (node.module == "sp_api.api" or node.module.startswith("sp_api.api.")):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names
                         if a.name == "sp_api.api" or a.name.startswith("sp_api.api.")]
            if not names:
                continue
            first, last = _span(node)
            if excepted(comments, first, last, "spapi-client-outside-api"):
                continue
            for nm in names:
                _numbered(out, "%s: %s" % (rel, nm), rel, node.lineno)
    return out


def rule_routes_import_dashboard(files=None):
    """`import dashboard` / `from dashboard import X` in routes/, at any
    depth. Key: file + what is imported."""
    out = []
    for p in (_py_files(("routes",)) if files is None else files):
        rel = _rel(p)
        _s, _lines, tree, comments = _parsed(p)
        if tree is None:
            continue
        for node in _nodes_of(p, "imports"):
            what = []
            if isinstance(node, ast.Import):
                what = [a.name for a in node.names if a.name.split(".")[0] == "dashboard"]
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module and \
                    node.module.split(".")[0] == "dashboard":
                what = ["dashboard." + a.name for a in node.names]
            if not what:
                continue
            first, last = _span(node)
            if excepted(comments, first, last, "routes-import-dashboard"):
                continue
            for w in what:
                _numbered(out, "%s: %s" % (rel, w), rel, node.lineno)
    return out


def rule_lower_imports_upper(files=None):
    """domain/listing/data/api/monitor importing routes or dashboard; api
    importing domain. Key: file + the module imported."""
    out = []
    for p in (_py_files(LOWER) if files is None else files):
        rel = _rel(p)
        top = rel.split("/")[0]
        _s, _lines, tree, comments = _parsed(p)
        if tree is None:
            continue
        for node in _nodes_of(p, "imports"):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                # `from routes import x` -> routes.x ; `from domain.a import b` -> domain.a
                mods = ([node.module + "." + a.name for a in node.names]
                        if node.module in ("routes", "domain", "dashboard") else [node.module])
            for m in mods:
                first_pkg = m.split(".")[0]
                bad = first_pkg in ("routes", "dashboard") or (top == "api" and first_pkg == "domain")
                if not bad:
                    continue
                a, b = _span(node)
                if excepted(comments, a, b, "lower-imports-upper"):
                    continue
                _numbered(out, "%s -> %s" % (rel, m), rel, node.lineno)
    return out


_MUTABLE_CALLS = {"dict", "list", "set", "defaultdict", "OrderedDict", "deque", "Counter", "WeakValueDictionary"}


def _container(v):
    """'empty' / 'filled' for a mutable container expression, else None."""
    if isinstance(v, (ast.Dict, ast.List, ast.Set)):
        n = len(v.keys) if isinstance(v, ast.Dict) else len(v.elts)
        return "empty" if n == 0 else "filled"
    if isinstance(v, (ast.DictComp, ast.ListComp, ast.SetComp)):
        return "filled"
    if isinstance(v, ast.Call):
        f = v.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        if name in _MUTABLE_CALLS:
            return "empty" if not v.args or name == "defaultdict" and len(v.args) <= 1 else "filled"
    return None


def _module_level(body):
    """Statements at module level, descending into module-level if/try/with."""
    for node in body:
        yield node
        if isinstance(node, ast.If):
            yield from _module_level(node.body + node.orelse)
        elif isinstance(node, ast.Try):
            yield from _module_level(node.body + node.orelse + node.finalbody
                                     + [s for h in node.handlers for s in h.body])
        elif isinstance(node, ast.With):
            yield from _module_level(node.body)


def rule_module_mutable_global(files=None):
    """Module-level (incl. inside module-level if/try/with) bindings of a
    mutable container: an EMPTY one under any name, a filled one under a
    lowercase name. Tuple targets are split. Key: file + name."""
    out = []
    for p in (_py_files() if files is None else files):
        rel = _rel(p)
        _s, _lines, tree, comments = _parsed(p)
        if tree is None:
            continue
        for node in _module_level(tree.body):
            pairs = []
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        pairs.append((t.id, node.value))
                    elif isinstance(t, (ast.Tuple, ast.List)) and isinstance(node.value, (ast.Tuple, ast.List)) \
                            and len(t.elts) == len(node.value.elts):
                        pairs += [(e.id, v) for e, v in zip(t.elts, node.value.elts) if isinstance(e, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and node.value is not None and isinstance(node.target, ast.Name):
                pairs.append((node.target.id, node.value))
            for name, value in pairs:
                kind = _container(value)
                if kind is None or name == "__all__":
                    continue
                if kind == "filled" and name.strip("_").isupper():
                    continue          # an ALL_CAPS filled table: read-only by convention
                a, b = _span(node)
                if excepted(comments, a, b, "module-mutable-global"):
                    continue
                _numbered(out, "%s: %s" % (rel, name), rel, node.lineno)
    return out


def _body_hash(fn):
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]                       # the docstring is not the logic
    if len(body) < DUP_MIN_STMTS:
        return None
    args = ast.dump(fn.args, annotate_fields=False)
    return hashlib.sha1((args + "".join(ast.dump(b, annotate_fields=False) for b in body))
                        .encode("utf-8")).hexdigest()


def _functions(tree):
    """(qualified name, node) for every function: module-level, nested, methods."""
    def walk(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = prefix + ch.name
                yield q, ch
                yield from walk(ch, q + ".")
            elif isinstance(ch, ast.ClassDef):
                yield from walk(ch, prefix + ch.name + ".")
            else:
                yield from walk(ch, prefix)
    yield from walk(tree, "")


def rule_duplicate_function(files=None):
    """Two or more functions (any nesting, methods included) with an identical
    body of DUP_MIN_STMTS+ statements, ignoring the docstring and the name.
    Key: the sorted list of file:qualified-name."""
    # TWO PASSES, for speed: functions are bucketed by (statements, arguments,
    # statement types) first, and only a bucket holding 2+ is hashed -- an
    # identical body always has the same shape, so nothing is missed. (Line
    # counts are NOT part of the shape: the same code wrapped differently
    # spans a different number of lines.)
    buckets = {}
    for p in (_py_files() if files is None else files):
        rel = _rel(p)
        _s, _lines, tree, comments = _parsed(p)
        if tree is None:
            continue
        for q, node in _nodes_of(p, "functions"):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                body = body[1:]
            if len(body) < DUP_MIN_STMTS:
                continue
            shape = (len(node.args.args), tuple(type(s).__name__ for s in body))
            buckets.setdefault(shape, []).append((p, rel, q, node, comments))
    groups = {}
    for members in buckets.values():
        if len(members) < 2:
            continue
        for p, rel, q, node, comments in members:
            h = _body_hash(node)
            if not h:
                continue
            a, _b = _span(node)
            if excepted(comments, a, a, "duplicate-function"):
                continue
            groups.setdefault(h, []).append(("%s:%s" % (rel, q), rel, node.lineno))
    out = []
    for members in groups.values():
        if len(members) > 1:
            names = sorted(m[0] for m in members)
            out.append((" == ".join(names), members[0][1], members[0][2]))
    return out


def rule_large_function(files=None):
    """Any function (nested included) longer than LARGE_LINES lines, in the app
    packages and dashboard.py; a routes/ module's top-level register() -- the
    register-injection container, whose routes are each measured on their own --
    excepted. Key: file + qualified name. Returns (key, file, line, size)."""
    out = []
    for p in (_py_files(extra=("dashboard.py",)) if files is None else files):
        rel = _rel(p)
        _s, _lines, tree, comments = _parsed(p)
        if tree is None:
            continue
        for q, node in _nodes_of(p, "functions"):
            a, b = _span(node)
            n = b - node.lineno + 1
            if n <= LARGE_LINES:
                continue
            if rel.startswith("routes/") and q == "register":
                continue
            if excepted(comments, a, node.lineno, "large-function"):
                continue
            out.append(("%s: %s" % (rel, q), rel, node.lineno, n))
    return out


_OPEN_KEYS = {"active_account_id", "active_marketplace"}
_OPEN_CALLS = {"current", "id_or_open"}
# THE DESIGNATED OWNERS of "the account the request names, else the open one":
# every route reaches the open account through these, and they are where that
# fallback is audited and tightened. Not violations -- the one place it lives.
OPEN_ACCOUNT_OWNERS = {"domain/request_account.py", "domain/account_scope.py"}


def _request_account_aliases(tree):
    """Names that mean the request_account module, and names bound to its
    current/id_or_open functions, in this file."""
    mods, fns = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "domain.request_account":
                    mods.add(a.asname or "domain.request_account")
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            if node.module == "domain":
                mods |= {a.asname or a.name for a in node.names if a.name == "request_account"}
            elif node.module == "domain.request_account":
                fns |= {a.asname or a.name for a in node.names if a.name in _OPEN_CALLS}
    return mods, fns


def rule_background_open_account(files=None):
    """Code (not comments or docstrings) below routes/ that takes the open
    account/marketplace: `x["active_account_id"]`, `x.get("active_account_id")`
    (and active_marketplace), or a call to request_account.current /
    id_or_open however it was imported. The designated owners are exempt.
    Key: file + enclosing function + what (+ #n when repeated there)."""
    out = []
    for p in (_py_files(LOWER) if files is None else files):
        rel = _rel(p)
        if rel in OPEN_ACCOUNT_OWNERS:
            continue
        _s, _lines, tree, comments = _parsed(p)
        if tree is None:
            continue
        mods, fns = _request_account_aliases(tree)

        def visit(node, where):
            for ch in ast.iter_child_nodes(node):
                w = where
                if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    w = (where + "." if where else "") + ch.name
                hit = None
                if isinstance(ch, ast.Subscript):
                    sl = ch.slice
                    if isinstance(sl, ast.Constant) and sl.value in _OPEN_KEYS:
                        hit = "reads " + sl.value
                elif isinstance(ch, ast.Call):
                    f = ch.func
                    if isinstance(f, ast.Attribute) and f.attr == "get" and ch.args \
                            and isinstance(ch.args[0], ast.Constant) and ch.args[0].value in _OPEN_KEYS:
                        hit = "reads " + ch.args[0].value
                    elif isinstance(f, ast.Attribute) and f.attr in _OPEN_CALLS and \
                            (ast.unparse(f.value) in mods):
                        hit = "calls request_account." + f.attr
                    elif isinstance(f, ast.Name) and f.id in fns:
                        hit = "calls request_account (%s)" % f.id
                if hit:
                    a, b = _span(ch) if hasattr(ch, "lineno") else (0, 0)
                    if not excepted(comments, a, b, "background-open-account"):
                        _numbered(out, "%s: %s %s" % (rel, w or "<module>", hit), rel, ch.lineno)
                visit(ch, w)
        visit(tree, "")
    return out


CHECKS = {
    "spapi-client-outside-api": rule_spapi_client_outside_api,
    "routes-import-dashboard": rule_routes_import_dashboard,
    "lower-imports-upper": rule_lower_imports_upper,
    "module-mutable-global": rule_module_mutable_global,
    "duplicate-function": rule_duplicate_function,
    "large-function": rule_large_function,
    "background-open-account": rule_background_open_account,
}

_SIZE = re.compile(r"lines=(\d+)")


def load_baseline():
    try:
        with open(BASELINE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def evaluate(baseline=None):
    """{rule: {"new": [(key, file, line)], "legacy": [key], "fixed": [key],
    "found": [...]}}. A legacy large function that grew past its recorded
    size + 10% + 20 lines is reported as NEW ("... grew from A to B lines")."""
    base = load_baseline() if baseline is None else baseline
    report = {}
    for rule, fn in CHECKS.items():
        found = fn()
        known = base.get(rule) or {}
        new = []
        for item in found:
            key = item[0]
            if key not in known:
                new.append(item[:3])
                continue
            if rule == "large-function":
                m = _SIZE.search(str(known[key]))
                if m and item[3] > int(m.group(1)) * 1.1 + 20:
                    new.append(("%s (grew from %s to %d lines)" % (key, m.group(1), item[3]),
                                item[1], item[2]))
        keys = {item[0] for item in found}
        report[rule] = {"new": new, "legacy": sorted(keys & set(known)),
                        "fixed": sorted(set(known) - keys), "found": found}
    return report


def _write_baseline(data):
    sys.path.insert(0, ROOT)
    from domain.jsonstore import write_json_atomic
    write_json_atomic(BASELINE, data, indent=1)


def _entry(rule, item):
    v = "legacy (29 Sep 2026)"
    return v + " lines=%d" % item[3] if rule == "large-function" else v


def main(argv):
    rep = evaluate()
    bad = 0
    for rule, r in rep.items():
        print("%-26s new %-3d legacy %-3d fixed %d" % (rule, len(r["new"]), len(r["legacy"]), len(r["fixed"])))
        for k, f, ln in r["new"]:
            bad += 1
            print("    NEW    %s  (%s:%d)" % (k, f, ln))
        for k in r["fixed"]:
            print("    FIXED  %s  -- remove from the baseline (--baseline-shrink)" % k)
    if "--baseline-shrink" in argv:
        base = load_baseline()
        for rule, r in rep.items():
            for k in r["fixed"]:
                (base.get(rule) or {}).pop(k, None)
        _write_baseline(base)
        print("baseline: fixed entries removed -- lower BASELINE_SIZE in test_architecture_guard.py to match")
    if "--baseline-init" in argv:
        # ONE-OFF, the day the guard was introduced: record today's code as
        # legacy. Refuses when a baseline exists; and the test pins the size per
        # rule, so deleting the file and re-creating it cannot grow it unseen.
        if os.path.exists(BASELINE):
            print("STOP: a baseline exists; it only shrinks (--baseline-shrink)")
            return 2
        data = {rule: {item[0]: _entry(rule, item) for item in r["found"]} for rule, r in rep.items()}
        _write_baseline(data)
        print("baseline written: " + ", ".join("%s %d" % (k, len(v)) for k, v in data.items()))
        return 0
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
