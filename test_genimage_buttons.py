# -*- coding: utf-8 -*-
"""#95 -- every image-generation button, and the saved-recipe feature is gone.

WHAT THE USER ASKED FOR (two things in one message)
---------------------------------------------------
  "i see i have very many options to create the images ... i want you to test
   all other buttons for any 4 items and see if it works, and delete the
   'use a saved recipe (templated)' thing from my app, i dont want this
   feature at all."

The live run of all ten buttons across four products is NOT in this file -- it
costs real money at OpenRouter and takes ~13 minutes.  It lives in
probe_genimage_buttons.py and was run once; the result was 9 of 10 passing,
with the one failure being the provider's safety filter refusing a weed-slasher
("The request failed because the input text may contain sensitive
information").  That is the bug this file guards against coming back:

  - the refusal is RECOGNISED as a refusal, not reported as a broken app
  - the brief is reworded once and retried automatically
  - the person is TOLD the brief was reworded (softened_prompt in the result),
    because the picture was then made from words they did not write

and the second half guards the deletion: no live code path may still offer a
saved recipe, or a button appears that leads nowhere.
"""
import ast
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(name, cond, detail=""):
    if cond:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s   %s" % (name, detail))
        FAILS.append(name)


def read(rel):
    with open(os.path.join(HERE, rel), encoding="utf-8") as fh:
        return fh.read()


def code_only_js(src):
    """Strip // and /* */ comments so a word in MY OWN comment cannot pass a test.

    This bit me repeatedly earlier in the session: an assertion went green
    because the string it looked for survived only inside a comment I had
    written explaining the removal.
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in src.split("\n"))


def code_only_py(src):
    """Same idea for Python: parse it, blank every docstring, unparse."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body[0].value.value = ""
    return ast.unparse(tree)


print("== 1. the saved-recipe feature is gone from the UI ==")

gen_raw = read(os.path.join("static", "js", "genimage.js"))
gen = code_only_js(gen_raw)

# Every symbol the feature was built out of.  If any survives in live code the
# feature is only half-removed, which is worse than leaving it: a button that
# calls a function that no longer exists is a dead end with no error message.
for sym in ["loadRecipes", "recipesManageHTML", "saveRecipe", "recTplPick",
            "deleteRecipe", "recipeOpts", "STUDIO.recipes"]:
    check("no %s in live js" % sym, sym not in gen)

check("no recipe pane in the pane list",
      not re.search(r"\[\s*'creative'[^\]]*recipe", gen))
check("no studioRun('recipe') branch",
      "'recipe'" not in gen and '"recipe"' not in gen,
      "a recipe mode string is still reachable")

# The four panes that remain.  Named explicitly so that deleting one by
# accident later is a test failure rather than a silent loss of a button.
for pane in ["creative", "source", "secondary", "aplus"]:
    check("pane %s still offered" % pane, "'%s'" % pane in gen)

# The reason for the removal is recorded in the file itself.  Not decoration:
# /recipes/* is still mounted server-side, and the next person to read
# genimage.js needs to know that is deliberate and not an oversight.
check("removal reason is written down in the file",
      "recipe" in gen_raw.lower() and "/recipes" in gen_raw)


print("\n== 2. a safety refusal is recognised, reworded and retried ==")

ai_raw = read(os.path.join("domain", "ai_providers.py"))
ai = code_only_py(ai_raw)

check("_refused_as_sensitive exists", "_refused_as_sensitive" in ai)
check("_soften_for_filter exists", "_soften_for_filter" in ai)
check("run_pipeline retries after a refusal",
      "_soften_for_filter" in ai.split("def run_pipeline")[-1],
      "the softener is defined but run_pipeline never calls it")

import sys
sys.path.insert(0, HERE)
from domain import ai_providers as AP

# The exact wording the provider used on the weed slasher.  "sensitive
# information" -- NOT "sensitive content", which is what I matched first and
# which is why the retry did not fire on the first attempt.
real_body = ('{"error":{"message":"The request failed because the input text '
             'may contain sensitive information.","code":400}}')
check("the wording the provider actually used is matched",
      AP._refused_as_sensitive(400, real_body) is True,
      "got %r" % (AP._refused_as_sensitive(400, real_body),))
check("the other wording is matched too",
      AP._refused_as_sensitive(400, '{"error":"sensitive content detected"}') is True)
check("content policy is matched",
      AP._refused_as_sensitive(400, "blocked by our content policy") is True)

# A refusal is not the same thing as a broken request.  If these two were
# confused, every genuine 400 would trigger a pointless second paid call.
check("a plain bad request is NOT a refusal",
      AP._refused_as_sensitive(400, '{"error":"model not found"}') is False)
check("a server fault is NOT a refusal",
      AP._refused_as_sensitive(500, "upstream timeout") is False)

# The rewording must change the words that upset the filter and keep the words
# that identify the product.  A softener that drops the product is useless --
# it would generate a picture of something else.
hard = "Heavy duty steel weed slasher blade for cutting brush, 16 inch handle"
soft = AP._soften_for_filter(hard)
check("the brief is actually changed", soft != hard, "unchanged: %r" % soft)
check("the trigger word is replaced", "slasher" not in soft.lower(), soft)
for keep in ["16", "steel", "handle"]:
    check("the brief still says %s" % keep, keep in soft.lower(), soft)

# Nothing to soften -> return it untouched, so run_pipeline's
# `if softened != detailed` guard stops it burning a second call for nothing.
mild = "A blue ceramic coffee mug on a white background"
check("a harmless brief is left alone", AP._soften_for_filter(mild) == mild)


print("\n== 3. the person is told when their brief was reworded ==")

# The picture came back, but it was made from words the user did not write.
# Saying so is not a nicety: they are about to put this image on a listing.
tail = ai.split("def run_pipeline")[-1]
check("run_pipeline reports softened_prompt", "softened_prompt" in tail)
check("run_pipeline returns the brief it actually used",
      "detailed_prompt" in tail,
      "the reworded brief must be readable, not just flagged")

# Every genimage route returns through ONE helper, _imgresult, which is defined
# in dashboard.py and injected into routes/genimage_routes.py -- so the flag has
# to be added there, not in the routes file (where I looked first).  Adding it in
# one place is also the point: eight call sites would otherwise each need it.
dash_raw = read("dashboard.py")
imgresult = dash_raw.split("def _imgresult", 1)[-1].split("\ndef ", 1)[0]
check("_imgresult passes softened_prompt to the screen",
      "softened_prompt" in imgresult,
      "the flag stops at the server and the screen can never show it")

ui = code_only_js(read(os.path.join("static", "js", "howworks.js")))
check("the screen actually says the brief was reworded",
      "softened_prompt" in ui,
      "the result card never mentions it")
check("  and shows the wording that was used",
      "detailed_prompt" in ui.split("softened_prompt", 1)[-1][:600],
      "flagged but the reworded brief is not readable")


print("\n== 4. every button still reaches a real handler ==")

# The buttons do NOT fetch their route directly -- I assumed they did and wrote
# this check wrongly the first time.  What actually happens: each button calls a
# studioRun* function, which queues work through /genimage/start_batch with a
# `kind` string, and dashboard.py's dispatcher maps that kind to a Flask view by
# NAME.  A view looked up by name is invisible to any rename -- nothing fails at
# import, the button just dies at click time with "unknown job kind" or a
# KeyError.  So check the whole chain link by link.
# The dispatcher, with comments removed but the ORIGINAL QUOTING intact.
# Not code_only_py here: it round-trips through ast.unparse, which rewrites
# string quotes, so looking for "source" silently missed 'source' and reported
# a working dispatcher as broken.  tokenize drops comments and touches nothing
# else, which is what a test asserting on exact source text needs.
def strip_comments_py(src):
    import io
    import tokenize
    out, last = [], (1, 0)
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.start[0] > last[0]:
            out.append("\n" * (tok.start[0] - last[0]))
            last = (tok.start[0], 0)
        out.append(" " * max(0, tok.start[1] - last[1]))
        out.append(tok.string)
        last = tok.end
    return "".join(out)


dash = strip_comments_py(dash_raw)

# link 1: the button exists and calls the runner
for pane, fn in [("creative", "studioRun('creative')"),
                 ("source", "studioRunSource()"),
                 ("secondary", "studioRunSecondary()"),
                 ("aplus", "studioRunAplus()")]:
    check("%s button calls %s" % (pane, fn), fn in gen)
    check("  and %s is defined" % fn.rstrip("()").split("(")[0],
          "function %s" % fn.split("(")[0] in gen)

# link 2: the runner queues that kind
for kind in ["source", "secondary", "aplus", "creative"]:
    check("kind %r is queued" % kind,
          'studioRunBackground("%s"' % kind in gen,
          "no studioRunBackground call for this kind")

# link 3: the dispatcher knows the kind and names a view for it
KIND_TO_VIEW = {
    # "creative" is served by genimage_recipe -- the saved-recipe FEATURE was
    # deleted but this view is the engine Creative runs on. Asserted here so a
    # future tidy-up of "dead" recipe code fails this test instead of silently
    # breaking the button the owner kept.
    "creative": "genimage_recipe",
    "source": "genimage_process_source",
    "secondary": "genimage_secondary_v2",
    "aplus": "aplus_generate",
}
for kind, view in KIND_TO_VIEW.items():
    check("dispatcher handles kind %r" % kind, '"%s"' % kind in dash)
    check("  via view %s" % view,
          'app.view_functions["%s"]' % view in dash,
          "the dispatcher no longer names this view")

# link 4: the named view really IS registered -- the one check a name-based
# lookup cannot do for itself.  Read the app's own view registry.
#
# Importing dashboard is not enough and pretending otherwise made this check
# pass vacuously: a bare import yields an app with 2 routes on it, because all
# the wiring lives in build_app().  Call it.
try:
    os.environ.setdefault("ALTA_NO_BROWSER", "1")
    import dashboard as _dash_mod
    have = set(_dash_mod.build_app().view_functions)
    check("build_app really wired the routes", len(have) > 50,
          "only %d views -- the registry check below would prove nothing" % len(have))
    for kind, view in KIND_TO_VIEW.items():
        check("view %s is registered (kind %r)" % (view, kind), view in have,
              "dispatcher would raise KeyError when this button is clicked")
except Exception as exc:                                   # pragma: no cover
    # Building the app reads config.json and may reach Google Sheets. If that is
    # unavailable, say so loudly -- a skipped check must never look like a pass.
    print("  SKIP  view registry check -- could not build the app: %s: %s"
          % (type(exc).__name__, str(exc)[:160]))
    FAILS.append("view registry check could not run")


print("\n%s" % ("FAILED: " + ", ".join(FAILS) if FAILS else "all checks passed"))
raise SystemExit(1 if FAILS else 0)
