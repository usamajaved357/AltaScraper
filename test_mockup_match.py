"""The follow-up to the density pass: close the last gaps to the mockup.

    "The density pass landed. Now close the remaining visual gaps between the
     live app and the mockup (altascraper-listings-mockup.html)."

Seven items, and THREE OF THEM HAD A DIFFERENT CAUSE THAN THE BRIEF ASSUMED.
That is worth recording, because each one would have been "fixed" into a file
where the problem was not:

  1. The ALL-CAPS headers were not written in caps. detailedHead() has always
     emitted "Listing status"; `table th{text-transform:uppercase}` in
     dashboard.css was shouting it. The brief proposed rewriting the <th> markup
     that was already correct.

  2/3/4. The gaps were not margins. The side gutter was a SECOND `main#grid{}`
     rule 1500 lines below the first, and the gap between the count row and the
     table header was `.card`'s flex `gap:10px` inherited by `.lrwrap` -- which
     no amount of zeroing margins would have reached.

  7. "Go to Ctrl K" and the pin hint are not in templates/dashboard.html. They
     are built by static/js/bookmarks.js.

WHAT IS ASSERTED HERE IS THE CAUSE, not the symptom -- so a later edit that
restores the real cause fails this file rather than passing it while the screen
regresses. The mockup is parsed for the numbers rather than having them typed in
twice, so a changed mockup shows up as a failure instead of silent drift.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-68s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def rd(p):
    return io.open(os.path.join(HERE, *p.split("/")), encoding="utf-8").read()


CSS = rd("static/css/dashboard.css")
LR = rd("static/css/listrow_detailed.css")
LRJS = rd("static/js/listrow_detailed.js")
LSJS = rd("static/js/listings.js")
BMK = rd("static/js/bookmarks.js")
MOCK = rd("altascraper-listings-mockup.html")


def rule(css, sel):
    """First rule with this selector. See rules()."""
    i = css.find(sel)
    return css[i + len(sel):css.find("}", i)] if i >= 0 else ""


def rules(css, sel):
    """Every rule with this selector -- because a selector written twice is
    exactly the bug item 2 turned out to be. See test_layout_density.rules."""
    out, i = [], css.find(sel)
    while i >= 0:
        out.append(css[i + len(sel):css.find("}", i)])
        i = css.find(sel, i + len(sel))
    return out


print("=== 1. the column headers are two lines, in sentence case ===")

# THE HEADINGS COME FROM THE MOCKUP, not from a list retyped here. Each pair is
# read out of the mockup's own <th> and required to appear in detailedHead()
# spelled the same way -- so renaming one in the mockup fails this rather than
# leaving the app quietly one heading behind.
_pairs = re.findall(r'>([A-Z][a-z][^<]*?)<br><span class="sub">([^<]+)</span>',
                    MOCK)
check("the mockup still declares six headings", len(_pairs), 6)
for name, sub in _pairs:
    truthy("'%s' / '%s' is what the app writes" % (name, sub),
           ('"%s", "%s"' % (name, sub)) in LRJS)

# THE CAPS WERE NEVER IN THE MARKUP. This is the rule that was shouting them.
_appwide = re.search(r"\btable th\{([^}]*)\}", CSS)
truthy("the app-wide table header is still uppercase",
       _appwide and "text-transform:uppercase" in _appwide.group(1))
truthy("  and this screen opts out of it rather than changing it for everyone",
       "text-transform:none" in rule(LR, ".inv-head th{"))
truthy("  the sub-label too", "text-transform:none" in rule(LR, ".inv-head .th-sub{"))
# FOUR LINES came from wrapping "and what Amazon said" inside a 100px column.
truthy("headers do not wrap", "white-space:nowrap" in rule(LR, ".inv-head th{"))
truthy("  and the letter-spacing goes with the caps",
       "letter-spacing:0" in rule(LR, ".inv-head th{"))
# The brief forbids new horizontal scroll. The header is nowrap now, so any
# fixed width narrower than its own text would push the table wider; product is
# the flexible column and absorbs it.
falsy("the product column still claims no width", ".col-product{ width" in LR)

print("\n=== 2 and 3. the table reaches the edges, under the stat cards ===")
_grids = rules(CSS, "main#grid{")
check("main#grid is still written more than once", len(_grids) >= 2, True)
truthy("  one of them still asks for the Orbit gutter",
       any("var(--wspad,32px)" in g for g in _grids))
truthy("  which is 32px unless a media query says otherwise",
       re.search(r"@media[^{]*\{[^@]*?--wspad:10px", CSS, re.S) is not None)
# The fix is a SCOPED override, so no other screen's grid moves and the Orbit
# rule is left alone.
truthy("the listings grid overrides it by specificity",
       "#sec_listings main#grid{" in CSS)
truthy("  10px at the sides", "padding:0 10px 10px"
       in rule(CSS, "#sec_listings main#grid{"))
truthy("  and nothing at the top, so the table meets the count row",
       rule(CSS, "#sec_listings main#grid{").strip().startswith("padding:0"))
# The 12px under the cards was .ui-stats', shared with four other screens.
truthy("the stat cards lose their bottom margin here only",
       "margin-bottom:0" in rule(CSS, "#summary .ui-stats{"))
truthy("  and .ui-stats keeps it everywhere else",
       "margin:0 0 12px" in rd("static/css/datatable.css"))
truthy("#summary matches the mockup's 5px", "padding:5px 10px" in rule(CSS, "#summary{"))
truthy("  which is what the mockup says",
       "padding:5px 10px" in rule(MOCK, ".stats{"))
# The counts line under the cards had its own -6px/12px, which would fight both.
falsy("the extras line no longer pulls itself over the cards",
      'style="margin:-6px 0 12px"' in LSJS)
truthy("  and no longer reopens the gap below them",
       'style="margin:4px 0 0"' in LSJS)

print("\n=== 4. the count row and the table header are flush ===")
# THIS WAS NOT A MARGIN. .lrwrap is class="card lrwrap" and .card is a flex
# column with gap:10px -- the whitespace was that gap, spent between the sort
# bar and the <table>.
truthy(".card is still a flex column with a gap",
       "gap:10px" in rule(CSS, ".card{") and "flex-direction:column" in rule(CSS, ".card{"))
truthy("  and .lrwrap cancels it", "gap:0" in rule(LR, ".lrwrap{"))
truthy("  along with the card border it cannot reach the edges with",
       "border:0" in rule(LR, ".lrwrap{"))
truthy("  and the radius", "border-radius:0" in rule(LR, ".lrwrap{"))
truthy("the wrapper is still the same element", 'class="card lrwrap"' in LRJS)
truthy("and the reason is written down where the next person will look",
       "flex GAP" in LR or "FLEX GAP" in LR)

print("\n=== 6. the metrics refresh itself, with no button ===")
truthy("there is an automatic refresh", "function lrAutoRefresh" in LRJS)
truthy("  it runs when the view draws", re.search(
       r"function detailedBlock\(rows\)\{.*?lrAutoRefresh\(\)", LRJS, re.S) is not None)
truthy("  at most once a page load", "LR_AUTO_TRIED" in LRJS)
check("  and the interval is the 20 hours asked for",
      re.search(r"LR_AUTO_HOURS = (\d+)", LRJS).group(1), "20")

# IT REUSES THE EXISTING FETCH RATHER THAN CARRYING A COPY (Rule 12) -- and it
# deliberately does NOT forget the cache, because forgetting makes every group
# stale by definition and would turn a 20-hourly check into a 20-hourly full
# refetch of rank, pricing and stock for the whole catalogue.
truthy("it goes through the one loader", "lrLoadMetrics(rows, true)" in LRJS)
_auto = LRJS[LRJS.find("function lrAutoRefresh"):]
_auto = _auto[:_auto.find("\n}")]
falsy("  and does not throw the cache away first", "metrics_forget" in _auto)
falsy("  nor call the button's own handler", "lrRefreshMetrics(" in _auto)
truthy("the button's handler is still there for a person to use",
       "async function lrRefreshMetrics(quiet)" in LRJS)
truthy("  silenced only by a flag, not by a second copy of it",
       "if(!quiet && typeof toast" in LRJS)

# TWO CLOCKS. The server's says whether the figures are old; the browser's stops
# a tab reopened all afternoon from firing while Amazon is refusing.
truthy("the server's own timestamp decides staleness", "LR_LAST_FETCH" in _auto)
truthy("  the browser holds a cooldown as well", "localStorage" in _auto)
truthy("  keyed per account", "_lrAutoKey" in LRJS and "acctId()" in LRJS)
truthy("  and storage being unavailable is survivable",
       _auto.count("catch(e){}") >= 2)
# "never fetched" and "not asked yet" are both 0 and must not act the same.
truthy("'never fetched' is told apart from 'not asked yet'", "LR_ANSWERED" in LRJS)
truthy("  and never-fetched falls through to the fetch",
       "if(LR_LAST_FETCH && Date.now()" in LRJS)
# NO FALSE CLAIM ABOUT AMAZON. The brief's own comment said the call "does not
# count against any throttle"; it does. Every SP-API call counts.
falsy("no claim that the call is free of the rate limit",
      re.search(r"does not count against any throttle", LRJS) is not None)
truthy("  the reason it is cheap is named correctly: the server's TTLs",
       "TTL" in _auto or "4h pricing" in LRJS)

print("\n=== 7. the header carries nothing but bookmarks ===")
falsy("the pin hint is gone", "Pin the screens you use most" in BMK)
falsy("  and the Go to button with it", "bmkgoto" in BMK)
falsy("    including its keyboard chip", "bmkkbd" in BMK)
truthy("the star that pins the current page stays", 'class="bmkadd' in BMK)
truthy("  and Ctrl+K still opens the palette",
       "ctrlKey || ev.metaKey" in rd("static/js/palette.js"))
truthy("  with what the removal cost written down",
       "only VISIBLE way into the palette" in BMK)

print("\n=== what must NOT have changed ===")
# "Do NOT change font sizes on anything except column headers ... Do NOT change
# button sizes ... Do NOT add horizontal scrollbars ... Do NOT touch any
# Python/backend code."
check("the header font size is untouched", "font-size:12px" in rule(LR, ".inv-head th{"), True)
check("  and the sub-label's", "font-size:11px" in rule(LR, ".inv-head .th-sub{"), True)
for sel, w in ((".col-cb{", "28px"), (".col-status{", "100px"),
               (".col-perf{", "120px"), (".col-inv{", "110px"),
               (".col-price{", "145px"), (".col-fees{", "105px"),
               (".col-actions{", "24px")):
    truthy("%s is still %s" % (sel.strip("{"), w), "width:" + w in rule(LR, sel))
falsy("no horizontal scroll was added to the wrapper",
      re.search(r"overflow-x:\s*(auto|scroll)", rule(LR, ".lrwrap{")) is not None)
truthy("the toolbar buttons keep the size the last pass gave them",
       "font-size:11px" in rule(CSS, ".wstoolbar .mktbtn{"))

print("\n=== nothing is half-written ===")
for name, txt in (("dashboard.css", CSS), ("listrow_detailed.css", LR)):
    check("%s braces balance" % name, txt.count("{"), txt.count("}"))
truthy("no mojibake in anything touched",
       not re.search(r"â€|Â·|â•", CSS + LR + LRJS + LSJS + BMK))

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
