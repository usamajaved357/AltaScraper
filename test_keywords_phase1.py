"""Phase 1 analytics: keywords, stored, and nothing running on its own.

    "Build the Phase 1 analytics features ... but with one critical constraint:
     NO automated jobs, NO scheduled tasks, NO cron, NO background workers.
     Everything runs only when a user manually clicks a button or visits a page."

Four screens over the SQP data the app could already fetch but never remembered:
Keyword Spy, ASIN Insights, Rank Tracker, Keyword History. The new part is
memory -- every manual search writes to the store, so history accumulates
because somebody used the tool.

THE THREE THINGS MOST LIKELY TO GO WRONG HERE ARE ALL ABOUT HONESTY, and each
has a section below.

  RANK COUNTS DOWN. Search frequency rank 1 is the MOST searched term, so a
  rank that FALLS is a keyword that ROSE. Shown raw, every arrow points the
  wrong way and somebody drops a keyword that was climbing.

  A GAP IS NOT A FALL. With manual-only collection the history has holes by
  design. A keyword in one week and not the other usually means nobody pulled
  that week -- scoring it as a 100% drop would be inventing a finding.

  "CLICK SHARE" IS NOT CTR. The plan's schema names click_share and
  conversion_share. In Brand Analytics those are one ASIN's slice of ALL clicks
  or purchases for a query, across every seller. Neither function this reads
  returns them. clicks/impressions is our own click-through rate -- a different
  number, and a 40% CTR is not 40% of the market. Storing one under the other's
  name would make every later comparison wrong in a way nobody could see.
"""
import os
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
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return open(os.path.join(HERE, *p), encoding="utf-8").read()


ROUTES = read("routes", "keywords_routes.py")
STORE = read("domain", "keyword_store.py")
SHELL = read("static", "js", "shell.js")
GUARD = read("auth", "guard.py")

# A database of its own, so the test never touches the real one.
os.environ["ALTASCRAPER_DB"] = os.path.join(tempfile.mkdtemp(), "kw_test.db")
from domain import keyword_store as K

WS, MKT = "test_ws", "UK"

# ===================================================================
print("== NOTHING runs on its own ==")


def code_only(src):
    """Source with comments and the module docstring removed.

    Both files EXPLAIN that they use no scheduler -- "No APScheduler, no
    Celery" -- so a raw text search finds the words in the very sentence
    promising their absence. A comment recording a rule is not a breach of it.
    """
    body = src.split('"""', 2)[-1] if src.lstrip().startswith('"""') else src
    return "\n".join(l.split("#")[0] for l in body.splitlines())


ROUTES_CODE, STORE_CODE = code_only(ROUTES), code_only(STORE)
# The whole constraint, checked against the code rather than trusted.
for word in ("APScheduler", "BackgroundScheduler", "Celery", "schedule.every",
             "threading.Timer", "setInterval", "add_job", "crontab"):
    falsy("no %s" % word, word in ROUTES_CODE or word in STORE_CODE)
# A background thread would be the quiet way to break this.
falsy("no thread is started", "Thread(" in ROUTES_CODE or "Thread(" in STORE_CODE)
truthy("and the constraint is written where it must hold",
       "NOTHING HERE RUNS ON ITS OWN" in ROUTES)

print("\n== the store remembers, and does not double-count ==")
rows = [{"term": "garden hose", "rank": 1500, "asin1": "B01"},
        {"term": "hose reel", "rank": 8000, "asin1": "B03"}]
check("a pull is saved", K.save_search_terms(WS, MKT, rows, "2026-08-03",
                                             "2026-08-09", seed="hose"), 2)
K.save_search_terms(WS, MKT, [{"term": "garden hose", "rank": 1400, "asin1": "B01"}],
                    "2026-08-03", "2026-08-09", seed="hose")
# Searching the same seed twice in a week is normal and must not double the
# history -- the second pull is the same week's truth, so it replaces.
check("searching the same week again does not duplicate",
      K.stored_counts(WS, MKT)["keywords"], 2)
K.save_search_terms(WS, MKT, [{"term": "garden hose", "rank": 1100, "asin1": "B01"},
                              {"term": "new term", "rank": 400, "asin1": "B09"}],
                    "2026-08-10", "2026-08-16", seed="hose")
check("a second week is its own", K.stored_counts(WS, MKT)["weeks"], 2)
check("weeks come back newest first",
      [w["report_start"] for w in K.weeks_available(WS, MKT)],
      ["2026-08-10", "2026-08-03"])

print("\n== rank counts DOWN, so a falling rank is a rising keyword ==")
cmp_ = {r["keyword"]: r for r in K.compare_weeks(WS, MKT, "2026-08-10", "2026-08-03")}
gh = cmp_["garden hose"]
check("  rank went 1400 -> 1100", (gh["rank_prev"], gh["rank_now"]), (1400, 1100))
check("  and 'moved' reports that as +300, meaning MORE searched",
      gh["moved"], 300)
truthy("  which is prev minus now, not now minus prev",
       "moved = (rb - ra)" in STORE)
truthy("  and the reason is recorded where the sum is",
       "RANK IS BACKWARDS" in STORE)

print("\n== a gap is not a fall ==")
# "hose reel" was saved in the EARLIER week (2026-08-03) and "new term" in the
# later one (2026-08-10). My first version of these two assertions had them the
# wrong way round; the code was right.
check("a keyword only in the earlier week is marked, not scored",
      (cmp_["hose reel"]["moved"], cmp_["hose reel"]["only_in"]), (None, "prev"))
check("  and one only in the newer week likewise",
      (cmp_["new term"]["moved"], cmp_["new term"]["only_in"]), (None, "now"))
# Real movers must not be buried under rows that cannot be compared.
first = K.compare_weeks(WS, MKT, "2026-08-10", "2026-08-03")[0]
check("  real movement sorts above the uncomparable rows",
      first["keyword"], "garden hose")

print("\n== raw counts are stored; rates are computed and named honestly ==")
check("SQP rows save", K.save_sqp(WS, MKT, "B0H66Q1XFK",
      [{"query": "hose", "impressions": 1000, "clicks": 50, "cart_adds": 10,
        "purchases": 5}], "2026-08-10", "2026-08-16"), 1)
# ASKED OF THE DATABASE, not of the source text. Both files discuss click_share
# at length in order to explain why it is absent, so a text search finds it in
# the sentence promising it is not there. The columns that actually exist are
# the only answer that means anything.
_cols = {t: {r[1] for r in K._conn().execute("PRAGMA table_info(%s)" % t)}
         for t in ("keyword_data", "keyword_asin_data", "rank_tracking")}
for t, cols in _cols.items():
    falsy("%s has no click_share column" % t, "click_share" in cols)
    falsy("  nor conversion_share", "conversion_share" in cols)
truthy("the raw counts are what is stored",
       {"impressions", "clicks", "cart_adds", "purchases"}
       <= _cols["keyword_asin_data"])
truthy("  and Amazon's own rank is kept as it comes",
       "search_frequency_rank" in _cols["keyword_data"])
truthy("CTR is computed at display time", '"ctr": round(clk / imp * 100, 2)' in ROUTES)
truthy("  and the screen says it is not Amazon's click share",
       "click share" in ROUTES and "does not contain" in ROUTES)
truthy("  with the distinction recorded in the store too",
       "TWO WORDS THIS FILE REFUSES TO USE LOOSELY" in STORE)

print("\n== the tracker measures visibility and says so, rather than faking rank ==")
K.watch_add(WS, MKT, "garden hose", "B0H66Q1XFK")
check("a pair can be watched", len(K.watch_list(WS, MKT)), 1)
K.save_rank_check(WS, MKT, "garden hose", "B0H66Q1XFK",
                  {"impressions": 1000, "clicks": 50, "purchases": 5},
                  start="2026-08-10")
h = K.rank_history(WS, MKT)
check("a check is recorded", len(h), 1)
# The honest part: organic position is not measurable here and is left empty
# rather than filled with something else wearing its name.
check("  organic position stays empty", h[0]["organic_position"], None)
truthy("  and the schema says why", "organic_position IS DELIBERATELY LEFT NULL" in STORE)
truthy("  the route says what it measures instead",
       "Search VISIBILITY, not organic position" in ROUTES)
truthy("  naming scraping as the thing not being done",
       "against Amazon's terms" in STORE or "against Amazon's terms" in ROUTES)
# A keyword with no data must be recorded as zero, not skipped: "checked, and
# there was nothing" reads very differently from "never checked".
truthy("a keyword with no row is stored as zeros, not skipped",
       "or skipped" in ROUTES.lower() or "not skipped" in ROUTES)
K.watch_remove(WS, MKT, "garden hose", "B0H66Q1XFK")
check("and a pair can be unwatched", len(K.watch_list(WS, MKT)), 0)

print("\n== one SQP pull per ASIN, not per keyword ==")
# The report is per ASIN and holds every query for it. Amazon rations these at
# roughly one a minute, so ten keywords on one ASIN must be one report.
truthy("the check groups by ASIN", "by_asin.setdefault" in ROUTES)
truthy("  and says why", "ONE SQP PULL PER ASIN" in ROUTES)

print("\n== the new routes are governed and scoped like everything else ==")
from auth import guard as G
for p in ("/keywords/spy", "/keywords/asin-insights", "/keywords/rank-tracker",
          "/keywords/rank-tracker/check", "/keywords/history"):
    check("  %-30s -> traffic" % p, G.feature_for(p), "traffic")
truthy("and they carry the account guard",
       "_wrong_account" in ROUTES and "account_scope" in ROUTES)
truthy("  refusing a borrowed token, which answers for the LENDER",
       "seller_scope_allowed" in ROUTES)

print("\n== every section is reachable AND visible ==")
# The visibility list was a SECOND hand-written copy of ALTA_SECTIONS. Forgetting
# it is invisible: the page loads, the data arrives, the onOpen runs, and you see
# nothing. It caught `permissions` once and all four keyword screens again.
falsy("the hand-written visibility list is gone",
      '["imagerefs","setup","generate","miles","sales"' in SHELL)
truthy("  it is derived from ALTA_SECTIONS now",
       'ALTA_SECTIONS.filter(s => s !== "listings")' in SHELL)
truthy("  and the trap is recorded", "0 pixels tall" in SHELL)
for s in ("kwspy", "kwasin", "ranktracker", "kwhistory"):
    truthy("  %s is a known section" % s, '"%s"' % s in SHELL)
U = read("static", "js", "users.js")
# Each names ITSELF and inherits traffic, so any one of them can be granted
# alone -- and with nothing set each still resolves to traffic, which is where
# search data belongs.
from auth import users as _AU
for s in ("kwspy", "kwasin", "ranktracker", "kwhistory"):
    truthy("  %s has a permission of its own" % s, '%s:"%s"' % (s, s) in U)
    check("    falling back to traffic", _AU.FEATURE_PARENT.get(s), "traffic")

print("\n== the analytics work does not reach into the protected tools ==")
# The brief: "do NOT modify amazon_listing_generator.py, the image generator,
# the repricer, the COGS system, or any existing tool. Build new features as
# SEPARATE files on SEPARATE routes."
#
# THIS USED TO READ `git status` and fail if any of those files was dirty for
# ANY reason. That is not the brief -- it is a lock on the whole repository, and
# it fired the first time the user asked for a COGS fix by name (defect 3 of the
# three deferred on 18 Aug: the browser's second CSV parser reading `price`, the
# selling price, as the cost). A test that turns "this piece of work must not
# touch X" into "nobody may ever touch X again" stops describing the work.
#
# What the brief actually forbids is the analytics feature depending on, calling
# into, or reshaping those tools -- so that is what is checked, in the analytics
# files themselves, where it cannot rot.
PROTECTED = ["amazon_listing_generator", "listing.pricing", "listing/pricing",
             "genimage", "sourcing", "cogs_store", "domain.cogs",
             "domain/cogs.py", "cogs_routes"]
ANALYTICS = [("domain", "keyword_store.py"), ("routes", "keywords_routes.py"),
             ("static", "js", "keywordspy.js"), ("static", "js", "keywordasin.js"),
             ("static", "js", "ranktracker.js"), ("static", "js", "keywordhistory.js")]
for parts in ANALYTICS:
    try:
        src = read(*parts)
    except Exception:
        fails.append("missing %s" % "/".join(parts))
        print("  MISSING", "/".join(parts))
        continue
    body = "\n".join(l.split("//")[0] for l in src.splitlines()
                     if not l.strip().startswith(("#", "*", "/*", "//")))
    hit = sorted(p for p in PROTECTED if p in body)
    check("  %s reaches for none of them" % "/".join(parts[-1:]), hit, [])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
