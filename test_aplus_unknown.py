""""No A+ content" and "Amazon would not say" are different answers.

FOUND BY WALKING THE SCREENS, not by a test: every page load logged a 502 from
/live/aplus. The body says it plainly --

    A+ Content API failed: [{'code': 'Unauthorized',
      'message': 'Access to requested resource is denied.'}]

-- the A+ Content role is not granted to this app's SP-API application. The
route was right to report it. The BROWSER then threw it away:

    if(!j || !j.ok){ APLUS_BY_ASIN = {}; return; }

so the index every A+ badge and panel reads was empty on every account, for
every ASIN, always. A listing that really does carry A+ content on Amazon showed
nothing, and nothing reads as a measurement -- the same fault as the weekly
pack's silent zeroes, in a different corner of the app.

Swallowing it is still right for the GRID: A+ is decoration on top of the
catalogue and a failure here must never stop the listings drawing. What was
missing is the REASON, kept so the places that show A+ can say which of the two
they are looking at.

Nothing is drawn in the ordinary case. An account with no A+ pages does not need
telling on every card; only the unknown gets a line, and the line says the fix
is a permission in Seller Central rather than anything in this app.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


PROBE = r"""
const fs = require("fs"), vm = require("vm");
globalThis.window = globalThis;
globalThis.addEventListener = function(){};
globalThis.document = {getElementById: () => null, querySelectorAll: () => [],
  createElement: () => ({innerHTML:"", querySelector: () => null}),
  addEventListener(){}};
globalThis.esc = s => String(s == null ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
  .replace(/"/g,"&quot;");
globalThis.ownLiveAsin = r => (r && r.own_asin) || "";
globalThis.APLUS_BY_ASIN = {};
globalThis.APLUS_ERROR = "";
// Only the two functions under test, pulled out of listings.js -- loading the
// whole file needs the rest of the app's globals and this is about these two.
const src = fs.readFileSync("static/js/listings.js", "utf8");
const grab = function(name){
  const i = src.indexOf("function " + name + "(");
  if(i < 0) throw new Error("missing " + name);
  let d = 0, j = src.indexOf("{", i);
  for(let k = j; k < src.length; k++){
    if(src[k] === "{") d++;
    else if(src[k] === "}"){ d--; if(!d) return src.slice(i, k + 1); }
  }
  throw new Error("unbalanced " + name);
};
vm.runInThisContext(grab("aplusFor") + "\n" + grab("aplusImages") + "\n"
                    + grab("aplusUnknownNote"));

const out = {};
// 1. Filled index, this ASIN has A+.
APLUS_ERROR = "";
APLUS_BY_ASIN = {"B0DP2V7GR2": [{name: "Hero", images: [{url: "u"}]}]};
out.hasDocs   = aplusFor({own_asin: "B0DP2V7GR2"}).length;
out.hasImages = aplusImages({own_asin: "B0DP2V7GR2"}).length;
out.noteWhenFilled = aplusUnknownNote();

// 2. Filled index, this ASIN simply has none. THE ORDINARY CASE -- silent.
out.otherAsin = aplusFor({own_asin: "B0OTHER123"}).length;
out.noteWhenAccountAsked = aplusUnknownNote();

// 3. Amazon refused. Nothing is known about ANY ASIN.
APLUS_BY_ASIN = {};
APLUS_ERROR = "A+ Content API failed: [{'code': 'Unauthorized', "
            + "'message': 'Access to requested resource is denied.'}]";
const denied = aplusUnknownNote();
out.deniedSaysUnknown  = /Not known/.test(denied);
out.deniedSaysNotNone  = /does not mean there is none/.test(denied);
out.deniedNamesTheRole = /Diagnose SP-API/.test(denied);
out.deniedNamesWhere   = /which permission|missing/.test(denied);
out.deniedQuotesAmazon = /Access to requested resource is denied/.test(denied);
out.deniedEscapes      = !/<script/.test(denied) && /&#39;|&quot;|'/.test(denied);

// 4. A different failure -- still unknown, but no permission advice invented.
APLUS_ERROR = "A+ Content API failed: read timed out";
const other = aplusUnknownNote();
out.otherSaysUnknown = /Not known/.test(other);
out.otherNoAdvice    = !/Seller Central/.test(other);
out.otherQuotes      = /read timed out/.test(other);

console.log(JSON.stringify(out));
"""

try:
    fd, path = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, PROBE.encode("utf-8"))
    os.close(fd)
    r = subprocess.run(["node", path], capture_output=True, text=True, cwd=HERE)
    os.unlink(path)
    if r.returncode != 0:
        print("  FAIL listings.js threw:", (r.stderr or "")[:400])
        raise SystemExit(1)
    g = json.loads(r.stdout.strip().splitlines()[-1])
except FileNotFoundError:
    print("  (node is not on this machine -- not exercised)")
    raise SystemExit(0)

print("=== when the index was filled, nothing changes ===")
check("a document is found for its ASIN", g["hasDocs"], 1)
check("  and its image", g["hasImages"], 1)
check("no note is added when A+ was read successfully",
      g["noteWhenFilled"], "")
# THE ORDINARY CASE MUST STAY SILENT. An account with no A+ pages does not want
# a warning on every card it opens.
check("an ASIN with no A+ shows nothing at all", g["otherAsin"], 0)
check("  and still says nothing", g["noteWhenAccountAsked"], "")

print("\n=== when Amazon refused, the space is not left to speak for itself ===")
truthy("it says the answer is not known", g["deniedSaysUnknown"])
truthy("  and that empty does not mean none", g["deniedSaysNotNone"])
# IT POINTS AT THE DIAGNOSTIC RATHER THAN NAMING ONE ROLE.
#
# This assertion used to require the words "A+ Content role" and "Seller
# Central", and it was wrong in the same way the message was: measured on
# jack_uk/UK the app authenticates fine -- its refresh token works -- and then
# gets 403 [ROLE] on marketplace participation, catalogue, pricing and product
# definitions as well. SEVERAL roles are missing, so telling somebody to grant
# the A+ one sends them to fix a fraction of the problem and conclude the app
# is broken when it comes back refused. The screen cannot know which are
# missing; the Diagnose SP-API button checks each in turn and says.
truthy("  it points at the check that names them", g["deniedNamesTheRole"])
truthy("  and says that is where the missing ones are listed",
       g["deniedNamesWhere"])
truthy("  and quotes what Amazon actually said", g["deniedQuotesAmazon"])
truthy("  with the message escaped, not injected", g["deniedEscapes"])

print("\n=== a different failure gets no invented advice ===")
truthy("a timeout is still 'not known'", g["otherSaysUnknown"])
# Telling somebody to grant a role they already have, because the network
# blipped, sends them to the wrong place.
truthy("  but is not blamed on a permission", g["otherNoAdvice"])
truthy("  and is quoted as it came", g["otherQuotes"])

print("\n=== the reason is per account, and does not outlive it ===")
JS = open("static/js/miles_template.js", encoding="utf-8").read()
SH = open("static/js/shell.js", encoding="utf-8").read()
truthy("the reason is recorded when the call fails", "APLUS_ERROR = String(" in JS)
truthy("  and cleared when it succeeds", 'APLUS_ERROR = "";' in JS)
# Switching account must not report one account's permission problem against the
# next one -- the same rule the line beside it already follows for the index.
truthy("switching account clears it with the rest", 'APLUS_ERROR=""' in SH)
truthy("  a failure still redraws, so the note appears without a reload",
       "APLUS_ERROR = String(" in JS
       and "render();" in JS.split("APLUS_ERROR = String(")[1][:220])

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
