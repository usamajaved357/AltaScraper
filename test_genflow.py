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

# Read once, up front, because most sections below need more than one of them.
sh = open(r"D:\AltaScraper\static\js\shell.js", encoding="utf-8").read()
hw = open(r"D:\AltaScraper\static\js\howworks.js", encoding="utf-8").read()
gf = open(r"D:\AltaScraper\static\js\genflow.js", encoding="utf-8").read()
lj = open(r"D:\AltaScraper\static\js\listings.js", encoding="utf-8").read()


def _nocomment(s):
    """Code only. Several checks below assert what a file DOES, and its comments
    name the very things they explain are no longer used -- matching those would
    fail a file for documenting itself."""
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in s.splitlines())


print("\n=== the moved nodes are on the LISTINGS page, exactly once ===")
# The Generate section is gone, so "inside sec_listings" is now bounded by the
# section that FOLLOWS it rather than by sec_generate.
li = src.index('<div id="sec_listings">')
nxt = src.index('<div id="sec_imagerefs"')
MOVED = ("genflow", "inputupload", "inputsheetwrap", "inputsheet_body",
         "inputsheet_meta", "inputsheet_filter", "genplan")
for nid in MOVED:
    check("#%s appears once" % nid, len(re.findall(r'\bid="%s"' % nid, src)), 1)
    check("  and inside sec_listings", li < src.index('id="%s"' % nid) < nxt, True)

print("\n=== the Generate screen is RETIRED, not just unlinked ===")
check("the section markup is gone", 'id="sec_generate"' in src, False)
check("the sidebar entry is gone", 'data-sec="generate"' in src, False)
# Left in ALTA_SECTIONS it would keep /w/<ws>/generate resolving to a section
# that is no longer in the markup -- a blank page rather than a wrong address.
secs = re.search(r"ALTA_SECTIONS\s*=\s*\[(.*?)\]", sh, re.S).group(1)
check("and it is not a routable section", '"generate"' in secs, False)
check("  while listings still is", '"listings"' in secs, True)
check("nothing navigates to it any more",
      bool(re.search(r"navTo\(\s*[\"']generate[\"']", _nocomment(lj + sh + gf))),
      False)

print("\n=== the drop zone is actually DRAWN where it now lives ===")
# The bug this caught: the markup moved to the Listings page while the code that
# FILLS it still only ran for sec==="generate". #inputupload was an empty div --
# the panel opened, the queue loaded under it, and there was nowhere to drop a
# file. An empty container throws nothing, so only looking finds it.
check("genflowOpen renders the upload panel",
      "inputUploadPanel()" in gf, True)
check("  only when the container is empty, so an upload report survives a reopen",
      "!iu.innerHTML.trim()" in gf, True)
check("shell.js no longer has a generate branch to do it instead",
      'sec==="generate"' in _nocomment(sh), False)

print("\n=== what the retired screen owned is guarded, not left to throw ===")
# #gen_scope is written on the WORKSPACE SWITCH path. Unguarded, a missing
# element throws there and navTo/loadRows below never run -- switching account
# would leave the previous account's rows under the new account's name.
check("the gen_scope write is guarded",
      'const _gs = document.getElementById("gen_scope")' in sh, True)
check("  and only writes when it exists", "if(_gs){" in sh, True)
check("genSelOnInput cannot null-deref now", "if(!src) return;" in hw, True)
check("showStop still guards on its button", 'if(b) b.disabled' in hw, True)

print("\n=== Stop asks the STREAM, not a button that no longer exists ===")
# #stopbtn lived on the retired screen. A check against it would be permanently
# false, so Stop would never appear in the overflow menu again.
check("the run test does not depend on #stopbtn", "#stopbtn" in _nocomment(gf), False)
check("  it asks ES, the EventSource itself",
      'typeof ES !== "undefined"' in gf, True)
check("Stop still calls the same stopRun()", "stopRun()" in gf, True)

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
# Asked of the STREAM now, not of #stopbtn -- that button lived on the retired
# Generate screen, so a check against it would be permanently false and Stop
# would never appear again. Asserted in full in its own section below.
check("  but only offered while something is running",
      'typeof ES !== "undefined"' in gf, True)
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
