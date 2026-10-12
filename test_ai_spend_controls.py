"""The AI-spend controls the owner approved on 12 Oct 2026.

    "I see there is a lot of AI spend. Can we drop down the AI spend and replace
     it with something else?" -- then, of the proposals: yes to a separate model
    for writing image instructions, to not paying twice, and to readable labels;
    and instead of fewer images, "give the user an option to select the number
    of images before creating."

1. writer_model: ai_select.prompt_write, when set, is the model that writes each
   image's instruction -- winning over the run's text model; unset, nothing
   changes.
2. A strategist batch reuses the strategist's product reading (remember_spec /
   recalled_spec, keyed by ACCOUNT and SKU) instead of reading it again.
3. Redo sends back the instruction the image was drawn from (reuse_prompt), and
   run_pipeline then only draws: no reading, no writing.
4. The number of images is chosen before "Suggest & auto-generate".
No network: the provider steps are replaced.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from domain import ai_providers as P             # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def src(*parts):
    return open(os.path.join(HERE, *parts), encoding="utf-8").read()


print("== 1. the instruction model ==")
cfg = {"ai_select": {"prompt_enhance": "anthropic/claude-sonnet-4.6"}}
check("unset: the run's text model", P.writer_model(cfg, "openai/gpt-5.1"),
      "openai/gpt-5.1")
check("unset, no run model: the text model setting", P.writer_model(cfg, None),
      "anthropic/claude-sonnet-4.6")
cfg2 = {"ai_select": {"prompt_enhance": "anthropic/claude-sonnet-4.6",
                      "prompt_write": "google/gemini-2.5-flash"}}
check("set: it wins, even over the run's text model",
      P.writer_model(cfg2, "anthropic/claude-sonnet-4.6"), "google/gemini-2.5-flash")
check("enhance_prompt asks writer_model", "model = writer_model(config, provider)"
      in src("domain", "ai_providers.py"), True)
S = src("routes", "settings_routes.py")
check("Settings returns and saves prompt_write (blank clears it)",
      '"prompt_write"' in S and 'sel.pop("prompt_write", None)' in S, True)
check("Settings screen has the box", 'id="ai_write"' in src("static", "js", "settings.js"),
      True)

print("== 2. the strategist's reading is reused, per account ==")
P._SPEC_BY_SKU.clear()
P.remember_spec("nestwell_goods", "FAN-1", "white ceiling fan, 3 blades")
check("the same account and SKU get it", P.recalled_spec("nestwell_goods", "FAN-1"),
      "white ceiling fan, 3 blades")
check("another account with the same SKU does not",
      P.recalled_spec("jack_uk", "FAN-1"), "")
P._SPEC_BY_SKU[("nestwell_goods", "OLD")] = ("stale", time.time() - P._SPEC_TTL - 5)
check("an old reading is not reused", P.recalled_spec("nestwell_goods", "OLD"), "")
P.remember_spec("", "FAN-2", "x")
check("no account named, nothing kept", ("", "FAN-2") in P._SPEC_BY_SKU, False)
G = src("routes", "genimage_routes.py")
check("strategize remembers it", "ai_providers.remember_spec(_rqa.named_now()" in G, True)
check("from_concept reuses it", "ai_providers.recalled_spec(" in G, True)

calls = []
P.describe_product = lambda *a, **k: calls.append("read") or {"ok": True,
                                                              "description": "READ"}
P.enhance_prompt = lambda config, brief, *a, **k: (calls.append("write"),
                                                   {"ok": True, "prompt": "P:" + brief[:20],
                                                    "provider": "m"})[1]
P.generate_image = lambda config, prompt, *a, **k: (calls.append(("draw", prompt)),
                                                    {"ok": True, "image_b64": "AAAA",
                                                     "provider": "img"})[1]
P.hard_constraints = lambda spec: ""
res = P.run_pipeline({}, brief="b", reference_image="ref.png",
                     product_spec="KNOWN SPEC")
check("a given reading is not read again", "read" in calls, False)
check("  and it reaches the instruction", res.get("product_spec"), "KNOWN SPEC")

print("== 3. Redo only draws ==")
calls.clear()
res = P.run_pipeline({}, brief="b", reference_image="ref.png",
                     reuse_prompt="THE FINISHED INSTRUCTION")
check("no reading, no writing", [c for c in calls if c in ("read", "write")], [])
check("drawn from the same instruction", calls, [("draw", "THE FINISHED INSTRUCTION")])
check("  and it comes back", res.get("detailed_prompt"), "THE FINISHED INSTRUCTION")
check("Redo sends it", "reuse_prompt:r.prompt" in src("static", "js", "howworks.js"), True)
check("the routes pass it", G.count("reuse_prompt=_reuse_of(b)"), 4)

print("== 4. the number of images is chosen first ==")
J = src("static", "js", "genimage.js")
check("a count beside main and secondary auto-generate",
      "_studioCountSelect('main', 6, 3)" in J and "_studioCountSelect('secondary', 8, 7)" in J,
      True)
check("  and the strategist is asked for that many",
      'getElementById("strat_n_" + kind)' in J, True)
check("the product page asks how many", "How many secondary images" in
      src("static", "js", "pdp_imagegen.js"), True)
check("the Listings bulk button asks how many", "How many secondary images per product"
      in src("static", "js", "listings_selection.js"), True)
check("the server keeps it within 1-8", "max(1, min(8, int(b.get(\"n\", 3) or 3)))" in G,
      True)

print()
if fails:
    print("FAILED: %d" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL PASSED")
