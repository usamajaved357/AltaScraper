"""Go to any of the 43 screens by typing its name.

WHAT WAS COUNTED. 43 screens, in 8 collapsible groups, reached by remembering
which group somebody filed each under: "Category Explorer" is under Manage
catalogue, "Keyword Spy" under Analytics, "Money back" under Inventory. The
bookmark bar (task #170) solved the four or five opened every day. This is the
other thirty-eight.

IT READS THE MENU RATHER THAN KEEPING A LIST. Every entry comes from the
sidebar's own markup at the moment the palette opens -- the section id from
data-sec, the words from the link, the sentence from its title, the icon from
its <i>, the group name from the master row above it. A hand-written copy would
be a second list of what this app can do, and the first thing to go stale
(rule 12). A screen added to the menu is searchable the same day with no edit
in palette.js.

AND IT CANNOT BE A WAY ROUND THE PERMISSION TABLE. Every candidate goes through
maySeeSection(), the same function the sidebar uses, and a nav item the app has
deliberately hidden -- Supplier Import, which only appears for accounts that
have one -- stays hidden here too.

Nothing about what any screen SHOWS changed. This is a way to reach them.
"""
import io
import json
import os
import subprocess
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
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return io.open(os.path.join(HERE, *p), encoding="utf-8").read()


P = read("static", "js", "palette.js")
H = read("templates", "dashboard.html")
C = read("static", "css", "dashboard.css")
B = read("static", "js", "bookmarks.js")
CODE = "\n".join(l.split("//")[0] for l in P.splitlines()
                 if not l.strip().startswith(("*", "/*", "//")))

print("== it is wired in, and last ==")
truthy("the page loads it", "/static/js/palette.js" in H)
truthy("  versioned like every other asset",
       "palette.js?v={{ ASSET_V }}" in H)
# LATE ENOUGH, not last. escape.js loads after it on purpose -- it must see
# whether the palette already handled Escape before acting. What matters is
# that palette.js comes after everything it READS: the sidebar markup,
# maySeeSection and navTo.
_before = H.split("palette.js")[0]
for dep in ("shell.js", "users.js", "sidebar.js"):
    truthy("  %s is loaded before it" % dep, dep in _before)
truthy("the styles are in the one stylesheet", "#palette" in C)
# From the RULES, not from the comment above them -- "#palette" appears in the
# comment first, and slicing on that measured the prose.
_pal_css = C[C.find("#palette{"):][:2600]
truthy("  and use the app's own tokens, not new colours",
       "var(--panel)" in _pal_css and "var(--ink)" in _pal_css
       and "var(--line" in _pal_css)

print("\n== it reads the menu, and keeps no list of its own ==")
truthy("entries come from data-sec in the markup", '"data-sec"' in CODE)
truthy("  the group from the master row", '".nmlbl"' in CODE)
truthy("  the sentence from the link's title", 'getAttribute("title")' in CODE)
falsy("there is no hard-coded list of sections",
      "ALTA_SECTIONS" in CODE or '"listings", "imagerefs"' in CODE)
# 43 nav items exist to be found.
import re
secs = set(re.findall(r'data-sec="([\w-]+)"', H))
truthy("the markup really does carry them all", len(secs) >= 40)
print("     (%d data-sec entries in dashboard.html)" % len(secs))

print("\n== and it cannot show what you may not see ==")
truthy("every candidate goes through maySeeSection",
       'typeof maySeeSection === "function" && !maySeeSection(sec)' in CODE)
check("  in both collection passes", CODE.count("maySeeSection(sec)"), 2)
truthy("an item the app hides stays hidden",
       'a.style.display === "none"' in CODE)
truthy("  and why is recorded", "Supplier Import" in P)
truthy("navigation goes through navTo, which owns the gate",
       "navTo(it.id)" in CODE)
falsy("  it does not set the section itself",
      "CUR_SEC =" in CODE or "location.href =" in CODE)

print("\n== the shortcut does not fight the app's other shortcuts ==")
truthy("Ctrl/Cmd+K", '"k"' in CODE and "ctrlKey || ev.metaKey" in CODE)
truthy("  and not a bare slash", '"/"' not in CODE.split("addEventListener")[-1])
truthy("ignored while typing",
       'tag === "INPUT"' in CODE and "isContentEditable" in CODE)
truthy("  except in its own box, where it closes again", 't.id !== "pal_q"' in CODE)
# sidebar.js owns Ctrl+B; they must not both claim a key.
S = read("static", "js", "sidebar.js")
truthy("sidebar.js still owns Ctrl+B", '"b"' in S)
falsy("  and palette.js does not touch B", '=== "b"' in CODE)

print("\n== the bookmark bar says how to reach the rest ==")
truthy("there is a Go to button", 'class="bmkgoto"' in B)
truthy("  which opens the palette", "onclick=\"palOpen()\"" in B)
truthy("  guarded, so the bar still draws without it",
       'typeof palOpen === "function"' in B)
truthy("  and it shows the shortcut", "Ctrl K" in B)
truthy("the button has a style", ".bmkgoto" in C)

print("\n== the ranking is predictable ==")
probe = r"""
const fs=require("fs"),vm=require("vm");
globalThis.document={addEventListener(){},getElementById:()=>null,
  querySelectorAll:()=>[],createElement:()=>({}),body:{appendChild(){}}};
globalThis.window=globalThis;
vm.runInThisContext(fs.readFileSync("static/js/palette.js","utf8"),{filename:"palette.js"});
const S=(q,s)=>_palScore(q,s);
console.log(JSON.stringify({
  startsWins:  S("cat","Category Explorer") > S("cat","Product Catalog"),
  wordStart:   S("cat","Product Catalog") > S("cat","Duplicates"),
  initials:    S("ce","Category Explorer") > 0,
  subsequence: S("keyhis","Keyword History") > 0,
  noMatchZero: S("zzz","Category Explorer") === 0,
  emptyMatches: S("","Anything") > 0,
  // a real match must always beat a subsequence
  realBeatsFuzzy: S("cat","Category Explorer") > S("cat","Compliance Audit Tool"),
}));
_PAL.items = [
  {kind:"sec", id:"categories", label:"Category Explorer", group:"Manage catalogue", note:"Which Amazon categories"},
  {kind:"sec", id:"catalog",    label:"Product Catalog",   group:"Manage catalogue", note:"Every product ranked"},
  {kind:"sec", id:"kwspy",      label:"Keyword Spy",       group:"Reports", note:"top search terms"},
  {kind:"acct",id:"selvora",    label:"SELVORA LIMITED",   group:"Switch account", note:""},
];
const names = q => _palRank(q).map(x=>x.label);
console.log(JSON.stringify({
  categ: names("categ"), cat: names("cat"), key: names("key"), sel: names("sel"),
  none: names("qqqq"), all: names("").length,
}));
"""
try:
    fd, path = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, probe.encode("utf-8"))
    os.close(fd)
    out = subprocess.run(["node", path], capture_output=True, text=True, cwd=HERE,
                         timeout=120)
    os.unlink(path)
    if out.returncode != 0:
        fails.append("palette.js threw")
        print("  FAIL:", (out.stderr or "")[:400])
    else:
        lines = out.stdout.strip().splitlines()
        g = json.loads(lines[-2])
        r = json.loads(lines[-1])
        truthy("a name that STARTS with it comes first", g["startsWins"])
        truthy("  a word start beats a letter buried in a word", g["wordStart"])
        truthy("  initials find it", g["initials"])
        truthy("  and letters in order are a last resort", g["subsequence"])
        truthy("  which never outranks a real match", g["realBeatsFuzzy"])
        truthy("something unrelated scores nothing", g["noMatchZero"])
        truthy("an empty box matches everything", g["emptyMatches"])
        check("'categ' finds the Category screen first",
              r["categ"][0], "Category Explorer")
        # And NOT "Product Catalog": there is no e-then-g after the "cat" in
        # "product catalog", so it is not even a subsequence. A search that
        # returned it would be matching letters rather than words.
        falsy("  and does not drag in Product Catalog",
              "Product Catalog" in r["categ"])
        check("  'cat' on its own finds both", sorted(names_cat := r["cat"]),
              ["Category Explorer", "Product Catalog"])
        check("'key' finds the keyword screen", r["key"], ["Keyword Spy"])
        truthy("'sel' finds the ACCOUNT", "SELVORA LIMITED" in r["sel"])
        check("nothing matching gives nothing", r["none"], [])
        check("an empty query lists them all", r["all"], 4)
except FileNotFoundError:
    print("  (node not on this machine -- not exercised)")
except Exception as e:
    fails.append("ranking probe")
    print("  FAIL ranking probe:", str(e)[:300])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
