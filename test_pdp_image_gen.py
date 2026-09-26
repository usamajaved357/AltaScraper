# -*- coding: utf-8 -*-
"""The AI image generator is on the product page's Images tab, and it starts.

    "do you remember how we had the image generation built inside the pdp?? i
     want that option again"

It came back first as the full generator form. The owner's PDP redesign
(PDP_REDESIGN_SPEC.md, 26 Sep 2026) then chose "Idea 1: Presets" -- four buttons
that each start a generation in one click, with optional instructions folded
away -- and said NOT to draw the Image Studio form (reference box, two model
pickers) on this page. The drawer still carries the full form.

What must stay true: the presets are Image Studio's OWN jobs through its own
/genimage/start_batch, not a second generator (Rule 12).
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(name, got, want):
    if got == want:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s   got=%r want=%r" % (name, got, want))
        FAILS.append(name)


def read(p):
    return open(os.path.join(HERE, *p.split("/")), encoding="utf-8").read()


PDP = read("static/js/pdp.js")
AF = read("static/js/autofix.js")
GEN = read("static/js/pdp_imagegen.js")
IMGS = read("static/js/pdp_images.js")
HTML = read("templates/dashboard.html")

print("== the drawer keeps the full generator ==")
# No longer handed out separately: no view but the drawer reads it now.
check("the generator is no longer handed to the page", "gen: genBlock" in AF, False)
check("the drawer still gets the generator in its fold run",
      "const toolFolds = _vf.mirror + _genFold + _otherTools;" in AF, True)

print("\n== the product page: presets, not the form ==")
images = PDP[PDP.find('PDP_TAB === "images"'):PDP.find('PDP_TAB === "variations"')]
check("the Images tab no longer draws the full form",
      "pdpGenSection(" in images or "+ p.gen" in images, False)
check("the tab draws the presets", "pdpImgGenSection(r)" in IMGS, True)
check("  outside the part that repaints, so a run is not wiped",
      "'</div>' + gen" in IMGS, True)
check("the page loads the preset file", "pdp_imagegen.js" in HTML, True)
check("the rail's Image studio still scrolls to it", 'class="pdp-gen pdpig"' in GEN, True)

print("\n== the presets are Image Studio's own jobs ==")
check("they start through /genimage/start_batch", '"/genimage/start_batch"' in GEN, True)
check("  and poll the same job status", '"/genimage/job_status?job="' in GEN, True)
check("the sets go through the strategist", '"/genimage/strategize"' in GEN, True)
check("three variations are studioRun's three strategies",
      '["hero_straight", "hero_angle", "hero_personality"]' in GEN, True)
check("the reference picture is found Image Studio's way", "_refImgForItem(r)" in GEN, True)
check("every run says what it costs first", "Each one is a paid call" in GEN, True)
check("results never replace a chosen picture (empty slots only)",
      "_pdpiEmptySlots()" in GEN, True)
check("the model named is the configured one, not a constant",
      '"/ai/settings"' in GEN and "Seedream" not in GEN, True)

node = shutil.which("node")
if not node:
    FAILS.append("node")
    print("  FAIL  node not found")
else:
    js = ("const esc=s=>String(s==null?'':s);\n" + GEN
          + '\nconsole.log(pdpImgGenSection({sku:"X",title:"t"}));\n')
    js = js.replace("setTimeout(_pdpigLoadModel, 0);", "")
    p = subprocess.run([node, "-e", js], capture_output=True, text=True)
    out = p.stdout
    for label in ("Main image", "3 variations", "Secondary set", "A+ content"):
        check("the %s button is drawn" % label, label in out, True)
    check("instructions are folded away until asked for",
          'id="pdpig_instrbox" style="display:none"' in out, True)
    check("  and say they apply to the next click",
          "apply to whichever button you click next" in out, True)
    check("the model line says where results go", "results fill empty slots above" in out, True)

print()
if FAILS:
    print("FAILED: %d" % len(FAILS))
    sys.exit(1)
print("all passed")
