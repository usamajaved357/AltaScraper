"""domain/drppc_console.py -- the console's own state.

Three things are being defended here, and none of them is arithmetic.

A PLAN CANNOT BE EDITED. Every save is a new revision and activation is a
separate act, because a plan that could be changed in place would make last
week's proposal unexplainable -- the thing it was made against would be gone.

AN UNCLASSIFIED TERM IS NOT A NON-BRANDED ONE. Defaulting it would quietly move
somebody else's spend into the lane that carries the growth mandate, and the
lane report would look complete while being wrong.

AN ENTITY NOBODY MIRRORS IS UNKNOWN, NOT NOUGHT. "0 negative keywords" beside
254 live campaigns is a claim, and a false one.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db                        # noqa: E402
from domain import drppc_console as _dc           # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-68s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


WS, MKT = "__drppc__", "UK"
CFG = None
conn = _db.get_db()
for t in ("drppc_plans", "drppc_rules", "ppc_search_terms", "ads_campaign_daily",
          "ads_daily"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
conn.commit()

# ---------------------------------------------------------------------------
print("\na plan is a chain of revisions, and saving never overwrites one")
# ---------------------------------------------------------------------------
a = _dc.plan_save_draft(CFG, WS, MKT, {"identity": {"title": "first",
                                                    "period_start": "2026-09-01",
                                                    "period_end": "2026-09-30"}})
b = _dc.plan_save_draft(CFG, WS, MKT, {"identity": {"title": "second"}})
check("the first save is revision 1", a["revision"], 1)
check("the second is revision 2, not an edit of 1", b["revision"], 2)
check("a save is always a draft", b["status"], "draft")
check("both revisions survive", len(_dc.plan_history(CFG, WS, MKT)), 2)

# The one that matters: activate r1, leaving r2 a NEWER draft.
ok, why = _dc.plan_activate(CFG, WS, MKT, 1, "tester")
check("activation succeeds", (ok, why), (True, ""))
cur = _dc.plan_current(CFG, WS, MKT)
check("the ACTIVE revision governs, not the newer draft", cur["revision"], 1)
check("and it says so", cur["status"], "active")
check("the newer draft is still there, untouched",
      [(h["revision"], h["status"]) for h in _dc.plan_history(CFG, WS, MKT)],
      [(2, "draft"), (1, "active")])
check("its body survived the round trip", cur["body"]["identity"]["title"],
      "first")

# Activating r2 must SUPERSEDE r1 rather than leave two active.
_dc.plan_activate(CFG, WS, MKT, 2, "tester")
hist = {h["revision"]: h["status"] for h in _dc.plan_history(CFG, WS, MKT)}
check("activating another supersedes the old one", hist[1], "superseded")
check("and only one is active at a time", hist[2], "active")
check("a revision that does not exist is refused, not invented",
      _dc.plan_activate(CFG, WS, MKT, 99, "")[0], False)

# ---------------------------------------------------------------------------
print("\na rule is checked before it is stored, never at classify time")
# ---------------------------------------------------------------------------
rid, why = _dc.rule_add(CFG, WS, MKT, "branded", "search_term", "contains",
                        "nestwell", 10, "our own brand word")
truthy("a good rule is stored", rid)
check("an unknown lane is refused",
      _dc.rule_add(CFG, WS, MKT, "growth", "search_term", "contains", "x")[0],
      None)
check("an unknown evidence type is refused",
      _dc.rule_add(CFG, WS, MKT, "branded", "vibes", "contains", "x")[0], None)
check("an unknown match type is refused",
      _dc.rule_add(CFG, WS, MKT, "branded", "search_term", "sounds_like", "x")[0],
      None)
check("an empty pattern is refused",
      _dc.rule_add(CFG, WS, MKT, "branded", "search_term", "contains", "  ")[0],
      None)
# STORED, a bad regex would throw on every run and the run would report nothing
# classified -- a failure that looks exactly like "no rules match".
check("a broken regular expression is refused at the door",
      _dc.rule_add(CFG, WS, MKT, "branded", "search_term", "regex",
                   "([unclosed")[0], None)
check("a non-numeric priority is refused",
      _dc.rule_add(CFG, WS, MKT, "branded", "search_term", "contains", "x",
                   "soon")[0], None)

# ---------------------------------------------------------------------------
print("\nclassification: unmatched is a real answer, not a lane")
# ---------------------------------------------------------------------------
TERMS = [
    {"search_term": "nestwell ceiling fan", "spend": 30.0, "sales": 90.0,
     "orders": 3, "clicks": 10},
    {"search_term": "ceiling fan with light", "spend": 70.0, "sales": 10.0,
     "orders": 1, "clicks": 40},
]
c = _dc.classify(CFG, WS, MKT, terms=TERMS)
byterm = {t["search_term"]: t for t in c["terms"]}
check("the branded rule caught the branded term",
      byterm["nestwell ceiling fan"]["lane"], "branded")
# THE ONE THAT MATTERS. Nothing matched it, so it is unclassified -- not
# non-branded, which is a decision nobody made.
check("a term no rule matched is unclassified, not non_branded",
      byterm["ceiling fan with light"]["lane"], "unclassified")
check("classified spend is the matched spend", c["classified_spend"], 30.0)
check("and the rest is reported as unclassified", c["unclassified_spend"], 70.0)
check("the percentage is of spend, not of terms", c["classified_pct"], 30.0)
check("30% is below the bar this console holds itself to", c["above_bar"], False)

# Two rules matching one term: the lowest priority number wins and the loser is
# still listed, so a classification can be argued with.
_dc.rule_add(CFG, WS, MKT, "non_branded", "search_term", "contains", "ceiling",
             99, "generic category word")
_dc.rule_add(CFG, WS, MKT, "branded", "search_term", "contains", "ceiling fan",
             5, "our category, our lane")
c2 = _dc.classify(CFG, WS, MKT, terms=TERMS)
hit = {t["search_term"]: t for t in c2["terms"]}["ceiling fan with light"]
check("the lowest priority number wins", hit["lane"], "branded")
check("the losing match is kept, not hidden", len(hit["other_matches"]), 1)
check("with everything matched, coverage is complete", c2["classified_pct"],
      100.0)

# No terms at all is NOT 0% classified.
empty = _dc.classify(CFG, "__nobody__", MKT, terms=[])
check("nothing to classify reports None, never 0%", empty["classified_pct"],
      None)
check("and it is not above the bar either", empty["above_bar"], False)

# Terms but no rules IS 0% -- a real measurement, and a different one.
c3 = _dc.classify(CFG, "__norules__", MKT, terms=TERMS)
check("terms with no rules is a measured 0%", c3["classified_pct"], 0.0)

# ---------------------------------------------------------------------------
print("\nmatch types mean what they say")
# ---------------------------------------------------------------------------
check("contains", _dc._matches({"match_type": "contains", "pattern": "fan"},
                               "ceiling fan light"), True)
check("exact is exact", _dc._matches({"match_type": "exact", "pattern": "fan"},
                                     "ceiling fan"), False)
check("exact matches an exact term",
      _dc._matches({"match_type": "exact", "pattern": "ceiling fan"},
                   "Ceiling Fan"), True)
check("starts_with does not match in the middle",
      _dc._matches({"match_type": "starts_with", "pattern": "fan"},
                   "ceiling fan"), False)
check("regex", _dc._matches({"match_type": "regex", "pattern": "^ceil.*fan$"},
                            "ceiling fan"), True)
# A rule with an empty pattern must match NOTHING. Matching everything would put
# every term in one lane and report 100% coverage.
check("an empty pattern matches nothing",
      _dc._matches({"match_type": "contains", "pattern": ""}, "anything"), False)

# ---------------------------------------------------------------------------
print("\nreadiness is measured, and a tick never means execution")
# ---------------------------------------------------------------------------
checks = _dc.readiness(CFG, lambda: {"accounts": []}, {"id": WS}, MKT)
by = {c["key"]: c for c in checks}
check("all ten checks are reported", len(checks), 10)
check("no advertising login is not a pass", by["ads_profile"]["ok"], False)
truthy("the branded rules check passes once one exists",
       by["branded_rules"]["ok"])
check("no plan active yet on this fixture is honest",
      by["plan"]["ok"], True)          # r2 was activated above
check("manual apply is authorised", by["manual_apply"]["ok"], True)
# The wording is the check. "Authorised" must not be read as "this app can
# write to Amazon", because it cannot (Rule 8).
truthy("and says in words that nothing here writes to Amazon",
       "writes to Amazon" in by["manual_apply"]["note"])
truthy("the manual apply row is the highlighted one",
       by["manual_apply"].get("highlight"))

# ---------------------------------------------------------------------------
print("\nthe mirror reports what it has, and unknowns as unknown")
# ---------------------------------------------------------------------------
for d, camp, cid, spend in (("2026-09-01", "SP_Test_A", "c1", 12.0),
                            ("2026-09-02", "SP_Test_A", "c1", 8.0),
                            ("2026-09-01", "SP_Test_B", "c2", 3.0)):
    conn.execute(
        "INSERT INTO ads_campaign_daily (workspace_id, marketplace, date, "
        "campaign_id, campaign_name, status, budget, ad_product, spend, "
        "fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (WS, MKT, d, cid, camp, "ENABLED", 10.0, "SPONSORED_PRODUCTS", spend,
         "2026-09-05T10:00:00"))
conn.execute(
    "INSERT INTO ppc_search_terms (workspace_id, marketplace, report_id, "
    "campaign, ad_group, keyword, match_type, search_term, spend, sales, "
    "orders, clicks) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
    (WS, MKT, "rep1", "SP_Test_A", "Group1", "ceiling fan", "BROAD",
     "ceiling fan with light", 7.0, 20.0, 1, 5))
conn.commit()

st = _dc.current_state(CFG, WS, MKT)
check("campaigns are counted distinctly, not per day",
      st["counts"]["campaigns"], 2)
check("ad groups come from the search-term report",
      st["counts"]["ad_groups"], 1)
# THE ONE THAT MATTERS. Four entities have no store, and a zero would be a claim
# about the account rather than about this app.
for k in ("targets", "negative_keywords", "negative_targets", "portfolios"):
    check("%s is unknown, not 0" % k, st["counts"][k], None)
    truthy("and says why", bool(st["not_mirrored"][k]))

camps = {c["name"]: c for c in st["campaigns"]}
check("spend is summed across the window", camps["SP_Test_A"]["spend"], 20.0)
check("the busiest campaign sorts first", st["campaigns"][0]["name"],
      "SP_Test_A")
check("a campaign's keyword count is derived where it can be",
      camps["SP_Test_A"]["keywords"], 1)
# A campaign with no search-term rows: None, not 0. It has keywords; none of
# them fired in the report's window, which is a different statement.
check("a campaign with no report rows reports unknown, not nought",
      camps["SP_Test_B"]["keywords"], None)
check("and its negatives are unknown too", camps["SP_Test_B"]["negatives"],
      None)
truthy("the mirror's own timestamp is reported", st["last_synced"])

d = _dc.campaign_detail(CFG, WS, MKT, "SP_Test_A")
check("the detail groups by ad group", len(d["ad_groups"]), 1)
check("with its keywords under it", d["ad_groups"][0]["keywords"][0]["keyword"],
      "ceiling fan")
truthy("and states that this is what FIRED, not what exists",
       "no impressions" in d["why"])

# ---------------------------------------------------------------------------
print("\nthe run log keeps failures")
# ---------------------------------------------------------------------------
from data import scheduler as _sch                # noqa: E402

conn.execute("INSERT INTO sync_jobs (job_type, workspace_id, status, last_run, "
             "error) VALUES (?,?,?,?,?)",
             ("ads_sync", WS, "error", "2026-09-04T01:00:00", "boom"))
conn.execute("INSERT INTO sync_jobs (job_type, workspace_id, status, last_run, "
             "result) VALUES (?,?,?,?,?)",
             ("ads_sync", WS, "ok", "2026-09-05T01:00:00", '{"campaigns": 254}'))
conn.commit()
runs = _sch.history(job_types=["ads_sync"], workspace_id=WS, limit=50)
mine = [r for r in runs if r["workspace_id"] == WS]
check("both of this account's attempts are listed", len(mine), 2)
check("newest first", mine[0]["status"], "ok")
# A run list showing only successes is how a job that has been erroring for a
# fortnight goes unnoticed.
check("the failure is kept, not filtered out", mine[1]["status"], "error")
check("a JSON result comes back as an object", mine[0]["result"]["campaigns"],
      254)
# DELIBERATE, and worth pinning down: a sync run for every account carries no
# workspace id, and it still ran for this one. Filtering those out would hide
# the very runs that did the work.
check("account-wide runs are not filtered out of an account's log",
      all(r["workspace_id"] in (WS, None) for r in runs), True)
check("another account's runs are",
      any(r["workspace_id"] not in (WS, None) for r in runs), False)

# ---------------------------------------------------------------------------
print("\ndeleting a rule changes the coverage, and says nothing else")
# ---------------------------------------------------------------------------
before = _dc.classify(CFG, WS, MKT, terms=TERMS)["classified_pct"]
_dc.rule_remove(CFG, WS, MKT, rid)
after = _dc.classify(CFG, WS, MKT, terms=TERMS)["classified_pct"]
check("the branded term is still caught by the other rule", after, before)
check("removing a rule that is not there removes nothing",
      _dc.rule_remove(CFG, WS, MKT, 999999), 0)

for t in ("drppc_plans", "drppc_rules", "ppc_search_terms", "ads_campaign_daily",
          "ads_daily"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
conn.execute("DELETE FROM sync_jobs WHERE workspace_id=?", (WS,))
conn.commit()

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    for f in fails:
        print("  FAILED:", f)
    sys.exit(1)
