"""The generation flow lives on the page the drafts are on, and was MOVED there.

    "Redesign the listing generator page to remove clutter, clean up the
     generation flow... One page, three collapsible sections that flow top to
     bottom."

WHAT THIS TEST IS ACTUALLY GUARDING, which is not the layout.

The drop zone, the queue and the pre-flight count were not rebuilt on the
listings page -- they were moved, because inputupload.js, inputqueue.js and
genplan.js already do those jobs and carry measured fixes (CLAUDE.md Rule 10:
move code, do not rewrite it). A move has one characteristic failure, and it is
silent: leave the old copy behind and the id exists TWICE, document.getElementById
returns the first one, and inputqueue.js then renders into the node nobody can
see. The panel sits on "Loading..." for ever and nothing errors.

So: every moved id exists exactly once, on the listings page, and the five files
that write to those nodes are still loaded and still load before the file that
calls them.
"""
import collections
import glob
import re
import sys

HTML = r"D:\AltaScraper\templates\dashboard.html"
CSS = r"D:\AltaScraper\static\css\genflow.css"
src = open(HTML, encoding="utf-8").read()
fails = []


def check(label, got, want):
    ok = got == want
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        fails.append(label)


print("=== no id in dashboard.html is defined twice ===")
# The whole file, not just the moved block: a duplicate anywhere is the same
# silent failure, and this is the one place it can be caught cheaply.
dupes = sorted(k for k, v in collections.Counter(
    re.findall(r'\bid="([A-Za-z0-9_\-]+)"', src)).items() if v > 1)
check("every id is unique", dupes, [])

print("\n=== the moved nodes are on the LISTINGS page, exactly once ===")
li = src.index('<div id="sec_listings">')
gi = src.index('<div id="sec_generate"')
MOVED = ("genflow", "inputupload", "inputsheetwrap", "inputsheet_body",
         "inputsheet_meta", "inputsheet_filter", "genplan")
for nid in MOVED:
    check("#%s appears once" % nid, len(re.findall(r'\bid="%s"' % nid, src)), 1)
    check("  and inside sec_listings", li < src.index('id="%s"' % nid) < gi, True)

print("\n=== nothing was left behind on the generate page ===")
gblk = src[gi:src.index('<div id="sec_sales"')]
check("no drop zone", 'id="inputupload"' in gblk, False)
check("no queue", 'id="inputsheetwrap"' in gblk, False)
check("no pre-flight count", 'id="genplan"' in gblk, False)
check("and it says where they went", "Listings page now" in gblk, True)

print("\n=== the five files that own the behaviour are still loaded ===")
OWNERS = ("inputupload.js", "inputqueue.js", "genplan.js", "submit.js", "genui.js")
for f in OWNERS:
    check("%s is loaded" % f, "/static/js/" + f in src, True)
check("genflow.js loads after all five, because it calls into them",
      all(src.index("/static/js/" + f) < src.index("/static/js/genflow.js")
          for f in OWNERS), True)
check("genflow.css is loaded", "/static/css/genflow.css" in src, True)

print("\n=== the fold starts CLOSED and has exactly one way open ===")
# The drafts table is what the page is for. A drop zone above it on every visit
# would push the table off the screen for every visit that is not an upload.
check("the panel is hidden in the markup",
      '<div id="genflow" class="genflow" hidden>' in src, True)
check("the toolbar button exists", 'id="genflow_btn"' in src, True)
check("  and toggles it", 'onclick="genflowToggle()"' in src, True)

print("\n=== every handler the moved markup calls is defined ===")
blk = src[src.index('<div id="genflow"'):src.index('<div id="gridhow">')]
js = "".join(open(p, encoding="utf-8", errors="replace").read()
             for p in glob.glob(r"D:\AltaScraper\static\js\*.js"))
for fn in sorted(set(re.findall(r'on(?:click|input)="([A-Za-z0-9_]+)\(', blk))):
    check("%s() is defined" % fn,
          bool(re.search(r"\bfunction\s+%s\s*\(" % fn, js)), True)

print("\n=== genflow.js re-implements none of the five ===")
gf = open(r"D:\AltaScraper\static\js\genflow.js", encoding="utf-8").read()


def _nocomment(s):
    """Code only. These checks assert what the file DOES, and the comments
    naming EventSource and :root are there to say who owns them instead --
    matching those would fail the file for explaining itself."""
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in s.splitlines())


gf_code = _nocomment(gf)
check("it does not open a stream of its own (submit.js owns the EventSource)",
      "EventSource" in gf_code, False)
check("it does not parse the generator's output (genui.js owns that)",
      "match(" in gf_code, False)
check("it starts a run through runMode, not by calling /run itself",
      'runMode("generate")' in gf and "/run/generate" not in gf, True)
check("emptying the queue goes through /input/clear, the one route that does it",
      "/input/clear" in gf, True)

print("\n=== an upload ADDS; only Clear empties (inputupload.js's own rule) ===")
check("there is a Clear queue button", "genflowClearQueue" in src, True)
check("  it confirms first", "uiConfirm" in gf, True)
check("  opening the panel clears nothing",
      "input/clear" in gf.split("function genflowOpen")[1].split("function genflowClose")[0],
      False)

print("\n=== the five demoted run actions are BEHIND a button, not deleted ===")
# "rarely used but should not be deleted" -- and two of them are the only way to
# do their job at all: Preview is the only check against Amazon that sends
# nothing, and Stop is the only way to end a run.
check("the toolbar has the overflow button", 'id="genflow_more"' in src, True)
check("  wired to genflowRunMenu", 'onclick="genflowRunMenu(event)"' in src, True)
check("it reuses the rows' own .tilemenu, not a second dropdown",
      'className = "tilemenu"' in gf, True)
# The calls sit inside single-quoted HTML attributes built in JS, so the quotes
# are backslash-escaped in the source: runMode(\'retry\'). Compare with the
# backslashes stripped rather than writing the escaping into the expectation.
gf_flat = gf.replace("\\'", "'")
for mode, label in (("retry", "Retry holds"), ("export", "Export"),
                    ("api", "Preview")):
    check("%s is still reachable" % label, "runMode('" + mode + "')" in gf_flat, True)
check("Submit is still reachable", "submitLive()" in gf, True)
check("Stop is still reachable", "stopRun()" in gf, True)
check("  but only offered while something is running",
      "#stopbtn:not([disabled])" in gf, True)
check("Generate is on the toolbar itself, not buried",
      'onclick="genflowGenerate()"' in src, True)

print("\n=== every function the menu calls is defined somewhere ===")
for fn in sorted(set(re.findall(r"closeRunMenu\(\);([A-Za-z0-9_]+)\(", gf))):
    check("%s() is defined" % fn,
          bool(re.search(r"\bfunction\s+%s\s*\(" % fn, js)), True)

print("\n=== bulk submit is a way IN to submitLive, not a second submit path ===")
lj = open(r"D:\AltaScraper\static\js\listings.js", encoding="utf-8").read()
check("the button exists in the selection bar", 'id="selsubmit"' in src, True)
check("  and calls submitLive", 'onclick="submitLive()"' in src, True)
# submitLive already scopes to selectedSkus() and confirms the destination
# account by name. A new /run/api_submit call here would be a second way to
# publish, with none of that.
check("  genflow.js does not publish on its own",
      "api_submit" in _nocomment(gf), False)
check("the count is updated in updateSelBar, the one selection listener",
      "selsubmit" in lj.split("function updateSelBar")[1].split("\nfunction ")[0], True)

print("\n=== genflow.css uses the app's tokens and defines no palette ===")
css_code = re.sub(r"/\*.*?\*/", "", open(CSS, encoding="utf-8").read(), flags=re.S)
check("no :root block -- dashboard.css owns the palette", ":root" in css_code, False)
check("no raw hex", re.findall(r"#[0-9a-fA-F]{3,6}\b", css_code), [])

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - %s" % f)
sys.exit(1 if fails else 0)
