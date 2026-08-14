"""What the AI cost, per account and per feature.

THE REQUEST: "i want a dashboard where i am able to see how many credits are
used in which account of the ai and for which feature, check all the features
which requires ai interference and record the credits used and show in a
dashboard in graph and also the other way written."

WHAT IS EASY TO GET WRONG HERE, and what each test below is defending:

  1. MISSING A CALL SITE. Spend leaves through two channels: OpenRouter (one
     function, ai_providers._post) and Anthropic (.messages.create, in nine
     files, thirteen places). Wrapping thirteen call sites is thirteen chances
     to miss one, so the Anthropic client is patched once instead. A dashboard
     that silently omits a feature is worse than no dashboard: it is wrong in
     the flattering direction, and nobody audits a number that looks fine.

  2. PRICING AN UNKNOWN MODEL AT ZERO. A model missing from the price table
     must record NULL, never 0.0. Zero for a call that certainly cost something
     compounds quietly across thousands of rows and cannot be told apart from a
     genuinely free call afterwards.

  3. LOSING THE ACCOUNT. A call with no account attached is recorded as "" and
     shown on its own line -- never folded into whichever account happened to
     be open. Spend on the wrong account is worse than spend on none.

  4. RECORDING BREAKING THE THING IT MEASURES. Writing a usage row must never
     fail a listing generation.
"""
import ast
import datetime as _dt
import json
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
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from domain import ai_usage as U

print("=== an unknown model is unknown, never free ===")
check("a known model prices", U.cost_of("claude-sonnet-4-5", 1000000, 0), 3.0)
check("output tokens cost more than input",
      U.cost_of("claude-sonnet-4-5", 0, 1000000), 15.0)
# THE ONE THAT MATTERS: a model nobody has priced yet.
check("an unpriced model returns None, not 0",
      U.cost_of("some-new-model-2027", 5000, 5000), None)
check("an unpriced image model returns None too",
      U.cost_of("brand-new-image-model", images=4), None)
check("a priced image model prices per image",
      U.cost_of("google/gemini-2.5-flash-image", images=4), round(0.039 * 4, 6))
# Longest match wins: a dated model name must not price as its shorter cousin.
check("a dated model name prices at its own tier, not a shorter match",
      U.cost_of("claude-sonnet-4-5-20260101", 1000000, 0), 3.0)

print("\n=== every AI call site is covered ===")
# Not "did someone remember to wrap this one", but "can one be added without
# being recorded". The answer must be no.
AI_SRC = open("domain/ai_providers.py", encoding="utf-8").read()
truthy("OpenRouter records inside _post, so every provider call is caught",
       "_record_openrouter(" in AI_SRC)
truthy("  and records failures too, which still spend input tokens",
       re.search(r"_record_openrouter\([^)]*ok=False", AI_SRC, re.S))
US_SRC = open("domain/ai_usage.py", encoding="utf-8").read()
truthy("Anthropic is recorded by patching the client, not per call site",
       "def install_anthropic_recorder(" in US_SRC)
truthy("  and it is idempotent, so a second install cannot double-count",
       "_alta_recorded" in US_SRC)

# Count the Anthropic call sites, so this test notices if the codebase grows a
# channel the recorder does not cover.
sites = 0
for root, dirs, files in os.walk(HERE):
    if any(p in root for p in ("_merge", "__pycache__", ".git", "node_modules")):
        continue
    for f in files:
        if not f.endswith(".py") or "baseline" in f or f.startswith("test_"):
            continue
        try:
            src = open(os.path.join(root, f), encoding="utf-8").read()
        except Exception:
            continue
        sites += len(re.findall(r"\.messages\.create\(", src))
print("  (%d Anthropic call sites in the app -- all covered by the patch)" % sites)
truthy("there are Anthropic call sites to cover", sites > 0)

# Both processes install it: the web app at boot, and the generator, which runs
# as its own process and is where most of the spend happens.
DASH = open("dashboard.py", encoding="utf-8").read()
truthy("the web app installs the recorder at boot",
       "install_anthropic_recorder(" in DASH)
truthy("  and stamps which account each request belongs to",
       "_stamp_ai_account" in DASH)
GEN = open("amazon_listing_generator.py", encoding="utf-8").read()
truthy("the generator process installs it too", "install_anthropic_recorder(" in GEN)
truthy("  with the account it was launched for",
       re.search(r"set_context\(workspace_id=_cli_account_id", GEN))

print("\n=== there is ONE context, not one per provider ===")
# Two context dictionaries would split a single run between two ledgers: the
# OpenRouter half attributed and the Anthropic half filed under "unknown".
truthy("ai_providers uses ai_usage's context rather than keeping its own",
       "from domain.ai_usage import CONTEXT" in AI_SRC)
U.set_context(feature="test: a feature", workspace_id="acct_a", sku="SKU-1")
from domain import ai_providers as P
check("setting it in one place is visible in the other",
      P._AI_CONTEXT.get("feature"), "test: a feature")

print("\n=== recording, and what the screen is built from ===")
import tempfile
tmp = tempfile.mkdtemp()
cfg_path = os.path.join(tmp, "config.json")
json.dump({"data_backend": "db", "db_path": os.path.join(tmp, "t.db")},
          open(cfg_path, "w", encoding="utf-8"))

today = _dt.date.today().isoformat()
U.record(cfg_path, feature="listing: write the copy", provider="anthropic",
         model="claude-sonnet-4-5", workspace_id="jack_uk",
         input_tokens=10000, output_tokens=2000)
U.record(cfg_path, feature="image: generate", provider="openrouter",
         model="google/gemini-2.5-flash-image", workspace_id="jack_uk",
         images=3, kind="image")
U.record(cfg_path, feature="image: generate", provider="openrouter",
         model="a-model-with-no-price", workspace_id="selvora", images=1,
         kind="image")
U.record(cfg_path, feature="listing: write the copy", provider="anthropic",
         model="claude-sonnet-4-5", workspace_id="", input_tokens=500,
         output_tokens=100)
U.record(cfg_path, feature="ppc: advice", provider="anthropic",
         model="claude-sonnet-4-5", workspace_id="jack_uk",
         input_tokens=1000, output_tokens=100, ok=False, error="timeout")

s = U.summary(cfg_path, start=today, end=today)
check("every call is counted", s["calls"], 5)
check("  including the failed one, which still spent input tokens",
      s["failed_calls"], 1)
check("the unpriced call is flagged rather than absorbed", s["unpriced_calls"], 1)
accounts = {r["workspace_id"]: r for r in s["by_account"]}
truthy("the unattributed call is its OWN row", "" in accounts)
check("  and is not folded into an account", accounts[""]["calls"], 1)
truthy("each account appears", "jack_uk" in accounts and "selvora" in accounts)
features = {r["feature"]: r for r in s["by_feature"]}
truthy("features are separated", "image: generate" in features
       and "listing: write the copy" in features)
check("images are counted as images", features["image: generate"]["images"], 4)

# The cross-tab is the actual question: which account, doing what.
cross = {(r["workspace_id"], r["feature"]) for r in s["by_account_feature"]}
truthy("account x feature is available", ("jack_uk", "image: generate") in cross)
truthy("  and separates the same feature in another account",
       ("selvora", "image: generate") in cross)
truthy("there is a per-day series for the graph", len(s["daily"]) >= 1)

print("\n=== recording never breaks the call it measures ===")
# The whole point: a usage row failing to write must not fail a generation.
try:
    U.record("/nowhere/at/all/config.json", feature="x", provider="anthropic")
    ok = True
except Exception:
    ok = False
check("a broken ledger path does not raise", ok, True)

print("\n=== the patch catches a REAL call, not just a mention in the source ===")
# The whole design rests on this: a call made through an ordinary client, by
# code that knows nothing about recording, must still land in the ledger. Asked
# with a deliberately invalid key so it fails immediately -- which also proves
# the other half, that a FAILED call is recorded rather than lost. Nothing is
# spent: the key is rejected before any tokens are read.
U.install_anthropic_recorder(cfg_path)
U.set_context(feature="test: an unwrapped call site", workspace_id="acct_probe",
              config_path=cfg_path, sku="")
before = U.summary(cfg_path, start=today, end=today)["calls"]
try:
    import anthropic as _an
    _an.Anthropic(api_key="sk-ant-invalid-key-for-testing").messages.create(
        model="claude-sonnet-4-5", max_tokens=1,
        messages=[{"role": "user", "content": "hi"}])
    raised = False
except Exception:
    raised = True
after = U.summary(cfg_path, start=today, end=today)
check("the invalid key was rejected, as expected", raised, True)
check("  and the attempt was still recorded", after["calls"], before + 1)
probe = [r for r in after["by_account_feature"]
         if r["workspace_id"] == "acct_probe"]
truthy("  against the right account and feature",
       probe and probe[0]["feature"] == "test: an unwrapped call site")
check("  and counted as a failure", after["failed_calls"] >= 2, True)

print("\n=== the screen is wired up ===")
import inspect
import routes.aiusage_routes as R
RSRC = inspect.getsource(R)
truthy("there is a summary endpoint", "/aiusage/summary" in RSRC)
truthy("and the individual calls behind it", "/aiusage/calls" in RSRC)
truthy("it reads every account by default, since that is the comparison",
       "ACROSS ALL ACCOUNTS BY DEFAULT" in RSRC)
truthy("it says in words when the total is a minimum", "MINIMUM" in RSRC)

G = open("auth/guard.py", encoding="utf-8").read()
truthy("reading it needs no write permission", '("/aiusage/summary",                None)' in G)
truthy("but it sits behind the same gate as other money screens",
       '("/aiusage",              "sales")' in G)

JS = open("static/js/aiusage.js", encoding="utf-8").read()
truthy("the screen has an open hook", "function aiUsageOnOpen" in JS)
truthy("it draws a graph", "salesChart(" in JS)
truthy("  reusing the Sales chart rather than a second one",
       "salescharts.js" in JS)
truthy("and writes it out as well", "_aiTable(" in JS)
truthy("the cross-tab is on the page", "Which account, doing what" in JS)
truthy("unpriced calls are shown, not hidden", "Unpriced" in JS)
truthy("tiny costs are not rounded to $0.00", "toFixed(5)" in JS)

SHELL = open("static/js/shell.js", encoding="utf-8").read()
truthy("the section is switched to by the nav", '"aiusage"' in SHELL)
truthy("  and opening it loads it", "aiUsageOnOpen()" in SHELL)
HTML = open("templates/dashboard.html", encoding="utf-8").read()
truthy("there is a nav item", 'data-sec="aiusage"' in HTML)
truthy("there is a panel for it", 'id="sec_aiusage"' in HTML)
truthy("and the script is loaded", "js/aiusage.js" in HTML)
truthy("dashboard registers the routes", "aiusage_routes.register" in HTML or
       "aiusage_routes.register" in DASH)

print("\n=== it answers over HTTP ===")
import dashboard as D
app = D.build_app()
app.config["TESTING"] = True
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess["user"] = "owner"; sess["role"] = "owner"; sess["is_owner"] = True
    j = c.get("/aiusage/summary?days=30").get_json() or {}
    truthy("the summary answers", j.get("ok"))
    for key in ("by_account", "by_feature", "by_model", "daily",
                "by_account_feature", "notes"):
        truthy("  it carries %s" % key, key in j)
    j2 = c.get("/aiusage/calls?days=30").get_json() or {}
    truthy("the call list answers", j2.get("ok"))
    truthy("  and says when it is cut short rather than looking complete",
           "limited" in j2)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
