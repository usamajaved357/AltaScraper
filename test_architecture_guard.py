# -*- coding: utf-8 -*-
"""The architecture guard (tools/arch_rules.py, 29 Sep 2026): NO NEW DEBT.

Part 1 -- the repository: every rule is run; a violation that is neither in
the baseline (tools/arch_baseline.json, today's legacy code) nor carries an
`# arch-ok: <rule> -- <reason>` exception FAILS; a baseline entry whose
violation is gone FAILS too until it is removed (the baseline only shrinks).

Part 2 -- the checker itself: each rule catches a deliberate bad example,
passes known-good code, honours a reasoned exception and refuses a reasonless
one (a temporary tree; the real repository is not touched).

Part 3 -- a known-good feature passes: the Orders purchase + dispatch code
(built 29 Sep 2026 to the target shape) has no violation of any rule.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-72s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


import arch_rules as A                          # noqa: E402

# THE BASELINE'S SIZE, per rule, pinned here: it may only go DOWN. Deleting the
# file and re-creating it, or adding an entry by hand, changes a count and
# fails below. After fixing legacy debt: --baseline-shrink, then lower these.
BASELINE_SIZE = {
    "spapi-client-outside-api": 31,
    "routes-import-dashboard": 1,
    "lower-imports-upper": 1,
    "module-mutable-global": 38,
    "duplicate-function": 0,
    "large-function": 27,
    "background-open-account": 8,
    # Added from lessons (docs/lessons.md), 29 Sep 2026, via --baseline-new-rule:
    "swallowed-write-failure": 66,
    "config-path-literal": 9,
}

print("== part 1: the repository has no NEW architectural debt ==")
rep = A.evaluate()
for rule, r in rep.items():
    check("%-26s no new violations" % rule, [k for k, _f, _l in r["new"]], [])
    check("%-26s baseline has no fixed (stale) entries" % rule, r["fixed"], [])
check("every rule is described", sorted(A.RULES), sorted(A.CHECKS))
base = A.load_baseline()
check("the baseline names only known rules", sorted(set(base) - set(A.CHECKS)), [])
check("the baseline's size per rule is the pinned size (it only shrinks)",
      {r: len(base.get(r) or {}) for r in A.CHECKS}, BASELINE_SIZE)
check("every legacy large function has its recorded size",
      [k for k, v in (base.get("large-function") or {}).items() if "lines=" not in v], [])

print("\n== part 2: the checker catches what it says, and nothing else ==")
REAL_ROOT = A.ROOT
tmp = tempfile.mkdtemp(prefix="archguard_")


def put(rel, text):
    p = os.path.join(tmp, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


try:
    A.ROOT = tmp
    # spapi-client-outside-api
    bad = put("domain/bad_client.py", "from sp_api.api import Orders\n")
    good = put("api/good_client.py", "from sp_api.api import Orders\n")
    base_only = put("domain/uses_base.py", "from sp_api.base import Marketplaces\n")
    got = [k for k, _f, _l in A.rule_spapi_client_outside_api([bad, good, base_only])]
    check("spapi: a client import in domain/ is caught", got, ["domain/bad_client.py: Orders"])
    ok_ex = put("domain/ok_client.py",
                "# arch-ok: spapi-client-outside-api -- measured legacy path, moving in 4E\n"
                "from sp_api.api import Orders\n")
    short = put("domain/short_client.py", "from sp_api.api import Orders  # arch-ok: spapi-client-outside-api -- ok\n")
    blank = put("domain/blank_client.py", "from sp_api.api import Orders  # arch-ok: spapi-client-outside-api --            \n")
    in_str = put("domain/str_client.py", "X = '# arch-ok: spapi-client-outside-api -- hidden in a string'; from sp_api.api import Orders\n")
    multi = put("domain/multi_client.py", "from sp_api.api import (\n    Orders,\n    Reports,  # arch-ok: spapi-client-outside-api -- measured legacy path, moving in 4E\n)\n")
    got = sorted(k for k, _f, _l in A.rule_spapi_client_outside_api([ok_ex, short, blank, in_str, multi]))
    check("  a reasoned exception passes (even on a later line of the import)",
          [k for k in got if "multi" in k or "ok_client" in k], [])
    check("  a short, blank or string-hidden 'reason' does not",
          got, ["domain/blank_client.py: Orders", "domain/short_client.py: Orders", "domain/str_client.py: Orders"])
    two = put("domain/two_client.py", "from sp_api.api import Orders\nfrom sp_api.api import Reports\n")
    got = sorted(k for k, _f, _l in A.rule_spapi_client_outside_api([two]))
    check("  keys name the class, so a NEW class in a legacy file is new",
          got, ["domain/two_client.py: Orders", "domain/two_client.py: Reports"])

    # routes-import-dashboard
    bad = put("routes/bad_routes.py", "def register(app):\n    import dashboard\n")
    good = put("routes/good_routes.py", "def register(app, *, _cfg):\n    return _cfg\n")
    got = [k for k, _f, _l in A.rule_routes_import_dashboard([bad, good])]
    check("routes-import-dashboard: an import inside register() is caught", got, ["routes/bad_routes.py: dashboard"])

    # lower-imports-upper
    b1 = put("domain/bad_dir.py", "from routes import tracking_routes\n")
    b2 = put("api/bad_api.py", "from domain import accounts\n")
    g1 = put("domain/good_dir.py", "from api import amazon_orders\nfrom data import db\n")
    got = sorted(k for k, _f, _l in A.rule_lower_imports_upper([b1, b2, g1]))
    check("lower-imports-upper: domain->routes and api->domain are caught",
          got, ["api/bad_api.py -> domain.accounts", "domain/bad_dir.py -> routes.tracking_routes"])

    # module-mutable-global
    bad = put("domain/bad_state.py", "_cache = {}\nseen = []\n_JOBS = {}\na, b = {}, []\n"
                                     "try:\n    _REG = dict()\nexcept Exception:\n    pass\nx: dict = {}\n")
    good = put("domain/good_state.py", "LIMITS = {'a': 1}\n__all__ = ['x']\n_ok = ()\n\ndef f():\n    local = {}\n    return local\n")
    got = sorted(k for k, _f, _l in A.rule_module_mutable_global([bad, good]))
    check("module-mutable-global: module-level state is caught -- any case when empty, "
          "tuple targets, inside try, annotated",
          got, ["domain/bad_state.py: %s" % n for n in ("_JOBS", "_REG", "_cache", "a", "b", "seen", "x")])
    check("  filled ALL_CAPS tables, __all__, tuples and function locals are not", len(got), 7)

    # duplicate-function
    body = ("def %s(rows):\n    out = []\n    for r in rows:\n        if r:\n            out.append(r)\n"
            "    out.sort()\n    n = len(out)\n    return out, n\n")
    d1 = put("domain/dup_a.py", body % "tidy")
    d2 = put("listing/dup_b.py", '"""doc"""\n' + (body % "tidy_rows").replace("    out = []", '    """same logic"""\n    out = []'))
    d3 = put("domain/short_a.py", "def a(x):\n    return x\n")
    d4 = put("domain/short_b.py", "def b(x):\n    return x\n")
    got = [k for k, _f, _l in A.rule_duplicate_function([d1, d2, d3, d4])]
    check("duplicate-function: the same body under another name is caught",
          got, ["domain/dup_a.py:tidy == listing/dup_b.py:tidy_rows"])
    check("  one-line helpers that merely look alike are not", len(got), 1)
    nested = ("def register(app):\n    def _scope(b):\n        x = 1\n        y = 2\n        z = x + y\n"
              "        w = z * 2\n        return w\n    return _scope\n")
    n1 = put("routes/a_routes.py", nested)
    n2 = put("routes/b_routes.py", nested.replace("        w = z * 2\n", "        w = (z\n             * 2)\n"))
    got = [k for k, _f, _l in A.rule_duplicate_function([n1, n2])]
    check("  copies nested inside register() are caught, however they are wrapped",
          got, ["routes/a_routes.py:register._scope == routes/b_routes.py:register._scope"])

    # large-function
    big = "def big():\n" + "".join("    x%d = %d\n" % (i, i) for i in range(A.LARGE_LINES + 5))
    bad = put("domain/big.py", big)
    reg = put("routes/reg_routes.py", big.replace("def big():", "def register(app):"))
    dec = put("domain/dec.py", "# arch-ok: large-function -- one generated table, measured on purpose\n"
                               "@staticmethod\n" + big.replace("def big():", "def dec():"))
    got = [k for k, _f, _l, _n in A.rule_large_function([bad, reg, dec])]
    check("large-function: a %d+ line function is caught" % A.LARGE_LINES, got, ["domain/big.py: big"])
    check("  a routes/ register() container is not", "routes/reg_routes.py: register" in got, False)
    check("  an exception above the decorator is honoured", "domain/dec.py: dec" in got, False)
    # A LEGACY large function that grows past its record counts as new debt.
    saved_base = A.BASELINE
    A.BASELINE = put("tools/arch_baseline.json", "{}")
    try:
        grow = {"large-function": {"domain/big.py: big": "legacy lines=150"}}
        A.CHECKS_SAVED = A.CHECKS
        A.CHECKS = {"large-function": lambda: A.rule_large_function([bad])}
        r = A.evaluate(grow)["large-function"]
        check("  a legacy one that grew past its recorded size is NEW",
              [k.split(" (grew")[0] for k, _f, _l in r["new"]], ["domain/big.py: big"])
        same = {"large-function": {"domain/big.py: big": "legacy lines=%d" % (A.LARGE_LINES + 6)}}
        check("  and one that did not grow is still legacy", A.evaluate(same)["large-function"]["new"], [])
        check("--baseline-init refuses while a baseline exists", A.main(["--baseline-init"]), 2)
    finally:
        A.CHECKS = A.CHECKS_SAVED
        A.BASELINE = saved_base

    # background-open-account
    bad = put("domain/bad_job.py", "def job(state):\n    return state.get('active_account_id')\n")
    doc = put("domain/doc_only.py", 'def f():\n    """reads _state["active_account_id"] in prose only"""\n    return 1\n')
    owner = put("domain/request_account.py", "def current(state):\n    return state['active_account_id']\n")
    via = put("domain/via_helper.py", "from domain import request_account as _rqa\n"
                                      "from domain.request_account import current as cur\n"
                                      "def job(state):\n    a = _rqa.current(state)\n    b = cur(state)\n    return a, b\n")
    got = sorted(k for k, _f, _l in A.rule_background_open_account([bad, doc, owner, via]))
    check("background-open-account: a job reading the open account is caught, directly or "
          "through request_account.current however imported",
          got, ["domain/bad_job.py: job reads active_account_id",
                "domain/via_helper.py: job calls request_account (cur)",
                "domain/via_helper.py: job calls request_account.current"])
    check("  prose in a docstring and the designated owner are not", len(got), 3)
    rep2 = put("domain/rep_job.py", "def job(s):\n    a = s.get('active_account_id')\n    b = s.get('active_account_id')\n    return a, b\n")
    got = [k for k, _f, _l in A.rule_background_open_account([rep2])]
    check("  a second read in the same function is its own (#2) entry",
          got, ["domain/rep_job.py: job reads active_account_id", "domain/rep_job.py: job reads active_account_id #2"])
    # swallowed-write-failure (lesson L-silent-failure)
    bad = put("domain/swallow.py", "def f(r):\n    try:\n        record_action(r)\n    except Exception:\n        pass\n")
    said = put("domain/said.py", "def f(r):\n    try:\n        record_action(r)\n    except Exception as e:\n        print(e)\n")
    read = put("domain/readonly.py", "def f(r):\n    try:\n        return load(r)\n    except Exception:\n        pass\n")
    ok_ex = put("domain/why.py", "def f(r):\n    try:\n        record(r)\n"
                                 "    except Exception:  # arch-ok: swallowed-write-failure -- the log must never break a request\n"
                                 "        pass\n")
    got = [k for k, _f, _l in A.rule_swallowed_write_failure([bad, said, read, ok_ex])]
    check("swallowed-write-failure: a write failure passed over in silence is caught",
          got, ["domain/swallow.py: f swallows record_action"])
    check("  a failure that is said, a read, and a reasoned exception are not", len(got), 1)

    # config-path-literal (lesson L-code-vs-data-folder)
    bad = put("domain/cfg_bad.py", "import os\ndef data():\n    return os.path.join(os.path.dirname(__file__), 'config.json')\n")
    owner = put("config/settings.py", "DEFAULT = 'config.json'\n")
    good = put("domain/cfg_good.py", "def data(CONFIG_PATH):\n    return CONFIG_PATH\n")
    got = [k for k, _f, _l in A.rule_config_path_literal([bad, owner, good])]
    check("config-path-literal: a bare config.json path is caught", got, ["domain/cfg_bad.py: data"])
    check("  the settings module that owns the default is not", len(got), 1)

    # introducing a rule: its legacy is recorded ONCE, never for an existing rule
    saved_base = A.BASELINE
    A.BASELINE = put("tools/arch_baseline.json", '{"config-path-literal": {"x": "legacy"}}')
    try:
        check("--baseline-new-rule refuses a rule that already has a baseline",
              A.main(["--baseline-new-rule", "config-path-literal"]), 2)
        check("  and a rule that does not exist", A.main(["--baseline-new-rule", "no-such-rule"]), 2)
    finally:
        A.BASELINE = saved_base
finally:
    A.ROOT = REAL_ROOT
    shutil.rmtree(tmp, ignore_errors=True)

print("\n== part 3: a known-good feature passes every rule ==")
GOOD = ("domain/order_scope.py", "domain/order_purchases.py", "domain/ship_confirm.py",
        "domain/order_attach.py", "routes/order_purchase_routes.py", "routes/order_ship_routes.py",
        "api/amazon_orders.py", "api/amazon_orders_ship.py")
hits = ["%s: %s" % (rule, item[0]) for rule, r in rep.items() for item in r["found"] if item[1] in GOOD]
check("the Orders purchase + dispatch code has no violation (all 8 files exist)",
      (hits, all(os.path.exists(os.path.join(HERE, *g.split("/"))) for g in GOOD)), ([], True))

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
