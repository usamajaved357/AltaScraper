"""The restricted-products checker got faster. It must not have got different.

WHY THIS FILE EXISTS AT ALL. Everything here is a SPEED change to code that
decides whether a product may be sold. That is the most dangerous kind of edit
in this repository: a wrong answer is not a slow screen, it is a listing that
should have been stopped, or a warning nobody needed that teaches the reader to
click past the one that matters. So the old code is kept, in this file, and the
two are run against every listing in the database and every keyword in the
rulebook, and they must agree exactly.

WHAT WAS MEASURED, profiling the Listings screen (88 rows, jack_uk):

    _attach_restricted     344.9 ms   3.92 ms/row     73,919 regex searches
    _attach_viability      266.5 ms   3.03 ms/row
    _attach_claim_flags     37.0 ms   0.42 ms/row
    re.compile called 11,502 times per request, rebuilding patterns it had
    just built

THREE CHANGES, EACH ONE PROVABLY THE SAME ANSWER:

  wordish is remembered      The terms come from fixed rulebooks on disk, so the
                             same few thousand strings are asked for over and
                             over and the answer for a given string never
                             changes. A compiled pattern is immutable.

  the haystack is built once The product's category words were joined and
                             lowercased inside _category_signal, which is called
                             once per category -- so the same three fields were
                             joined forty-six times per listing, always giving
                             the same string.

  one search before eighteen Each entry's strong keywords as a single
                             alternation carrying the SAME boundary guards. It
                             matches exactly when at least one of the individual
                             patterns matches: the engine backtracks between
                             alternatives at each position, so a keyword that
                             fails its right-hand boundary does not stop another
                             from being tried there.

  corroborating words are    They are read in ONE place -- used_kws, behind
  only worked out when they  `if cat_sig` -- and they do not decide `matched`.
  can be used                Computing them without a category signal was work
                             whose answer was thrown away.

RESULT: 344.9 ms -> 74.8 ms. 73,919 searches -> 21,602. 0 mismatches in 26,396
comparisons against the old implementation.
"""
import json
import os
import sys
import time

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


from listing import restricted as R


def old_check(text="", marketplace="UK", product_type="", category_path="",
              browse_nodes=None):
    """check_restricted_type EXACTLY as it was before the speed work.

    Every pattern, every time; the haystack rebuilt per category; the
    corroborating words worked out whether or not anything could use them.
    """
    mkt = (marketplace or "").upper()
    mkt_known = mkt in ("UK", "US")
    text_hay = str(text or "")
    matches = []
    for cid, e in R._ENTRIES.items():
        # The old _category_signal, inlined, so this does not depend on the
        # signature of the one that is still in the module.
        tokens = R._CATEGORY_SIGNALS.get(cid)
        if not tokens:
            cat_sig = False
        else:
            hay = "  ".join(str(x) for x in (product_type, category_path,
                            " ".join(browse_nodes or [])) if x).lower()
            if any(R.wordish(ex).search(hay)
                   for ex in R._CATEGORY_EXCLUDE.get(cid, [])):
                cat_sig = False
            else:
                cat_sig = any(R.wordish(t).search(hay) for t in tokens)
        strong_hits = [kw for kw, pat in e["kw_strong"] if pat.search(text_hay)]
        corrob_hits = [kw for kw, pat in e["kw_corrob"] if pat.search(text_hay)]
        matched = bool(strong_hits) or cat_sig
        if not matched:
            continue
        if strong_hits and not cat_sig and R._accessory_only(e, text_hay, strong_hits):
            continue
        st = e["statuses"].get(mkt) if mkt_known else None
        tier = R._norm_tier(st["value"]) if st else "RESTRICTED"
        source = st["source"] if st else ""
        action = ("BLOCK" if (mkt_known and tier == "PROHIBITED"
                              and source == "amazon_notice") else "WARN")
        used = strong_hits + ([k for k in corrob_hits] if cat_sig else [])
        matches.append({
            "id": cid, "label": e["label"],
            "status": (st["value"] if st else "unknown for this marketplace"),
            "tier": tier, "source": source, "action": action,
            "reason": e.get("reason_tier3") or e.get("reason", ""),
            "regulator": e.get("regulator_tier3") or e.get("regulator", ""),
            "docs": R._docs_for_match(e, mkt), "depth": e.get("depth", ""),
            "matched_keywords": used, "category_signal": cat_sig,
            "asin_seen": e.get("asin_seen", ""),
            "false_positive_warning": e.get("false_positive_warning", "")})
    overall = ("BLOCK" if any(m["action"] == "BLOCK" for m in matches)
               else ("WARN" if matches else "NONE"))
    return {"matched": bool(matches), "marketplace": mkt,
            "marketplace_known": mkt_known, "overall_action": overall,
            "matches": matches}


print("== the fast path exists ==")
truthy("every entry with strong keywords has a screen",
       all(e.get("kw_screen") is not None
           for e in R._ENTRIES.values() if e["kw_strong"]))
truthy("  and one with none has no screen rather than an empty regex",
       all(e.get("kw_screen") is None
           for e in R._ENTRIES.values() if not e["kw_strong"]))
truthy("wordish is memoised", hasattr(R.wordish, "cache_info"))
truthy("  and hands back the same compiled pattern",
       R.wordish("nebulizer") is R.wordish("nebulizer"))
truthy("the haystack has its own function", hasattr(R, "_category_haystack"))
truthy("  and _category_signal still works without being given one",
       R._category_signal(next(iter(R._CATEGORY_SIGNALS)), "x", "y", None)
       in (True, False))

print("\n== the screen matches exactly when some keyword does ==")
# The property the whole optimisation rests on, stated as a property and
# checked as one.
bad_screen = []
for cid, e in R._ENTRIES.items():
    scr = e.get("kw_screen")
    if scr is None:
        continue
    for kw, pat in e["kw_strong"]:
        for probe in (kw, "the " + kw + " here", "x" + kw, kw + "x",
                      kw.upper(), "(" + kw + ")"):
            any_individual = any(p.search(probe) for _k, p in e["kw_strong"])
            if bool(scr.search(probe)) != any_individual:
                bad_screen.append((cid, kw, probe))
check("the screen agrees with 'any individual pattern', every time",
      bad_screen[:5], [])
print("     (checked %d entries)" % sum(1 for e in R._ENTRIES.values()
                                        if e.get("kw_screen") is not None))

print("\n== old and new, on every listing this app holds ==")
cases = []
n_db = 0
try:
    from data import db as _db
    for r in _db.get_db().execute(
            "SELECT title, product_type, amazon_category FROM listings"):
        cases.append((r[0] or "", r[1] or "", r[2] or ""))
    n_db = len(cases)
except Exception as e:
    print("  (no database to read: %s)" % str(e)[:80])

kws = set()
for e in R._ENTRIES.values():
    for kw, _p in e["kw_strong"]:
        kws.add(kw)
    for kw, _p in e["kw_corrob"]:
        kws.add(kw)
# Every keyword alone, and in the shapes that break a boundary guard.
for kw in sorted(kws):
    cases += [(kw, "", ""), ("the " + kw + " thing", "", ""),
              ("x" + kw, "", ""), (kw + "x", "", ""), ("x" + kw + "x", "", ""),
              (kw.upper(), "", ""), (" " + kw + ".", "", ""),
              ("(" + kw + ")", "", ""), (kw + "-pack", "", ""),
              ("anti-" + kw, "", "")]
cases += [("", "", ""), ("   ", "", ""), ("a" * 4000, "", ""),
          ("nebulizer inhaler kratom", "", ""),
          ("Compressor Oil ISO 46", "MACHINE_LUBRICANT", "Automotive"),
          ("Patio Heater 13kW", "SPACE_HEATER", "Garden > Heating")]

mismatch = []
t_old = t_new = 0.0
for txt, pt, cat in cases:
    for mkt in ("UK", "US", "DE", ""):
        t0 = time.perf_counter()
        a = old_check(txt, mkt, pt, cat)
        t_old += time.perf_counter() - t0
        t0 = time.perf_counter()
        b = R.check_restricted_type(txt, mkt, pt, cat)
        t_new += time.perf_counter() - t0
        b = {k: b[k] for k in a}
        if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True):
            mismatch.append((txt[:50], mkt))
check("old and new agree on every one", mismatch[:5], [])
print("     (%d cases x 4 marketplaces = %d comparisons; %d real listings, "
      "%d rulebook keywords)" % (len(cases), len(cases) * 4, n_db, len(kws)))
if t_new > 0:
    print("     (old %.2fs, new %.2fs -- %.1fx)" % (t_old, t_new, t_old / t_new))
    truthy("and the new one really is faster", t_new < t_old)

print("\n== whole-word matching is defined ONCE ==")
from listing import compliance as C
truthy("compliance uses restricted's matcher", C._wordish is R.wordish)
src = open(os.path.join(HERE, "listing", "compliance.py"), encoding="utf-8").read()
check("  and has no second definition of it",
      src.count("def _wordish"), 0)
from listing import sourcing_viability as V
truthy("sourcing_viability uses it too", V.wordish is R.wordish)
# The rule itself, from all three doors.
for m, name in ((R.wordish, "restricted"), (C._wordish, "compliance"),
                (V.wordish, "sourcing_viability")):
    check("  %s: 'Esso' does not match inside 'compressor'" % name,
          bool(m("Esso").search("compressor")), False)
    check("  %s: 'Esso' does match on its own" % name,
          bool(m("Esso").search("Genuine Esso oil")), True)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
