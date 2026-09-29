# -*- coding: utf-8 -*-
"""Startup names the configuration a feature cannot work without
(master continuation, Priority 6: "Startup should clearly report missing
required configuration"; docs/deployment-manifest.md §3-4).

domain/deploy_check.check -- printed as the boot banner and shown on /diag --
now also reports, by NAME only (never a value):
  * ALTA_TOKEN_KEY when any account is an OAuth seller (without it their
    stored tokens cannot be read);
  * whether an AI key is configured (listing generation needs one);
  * whether background work is on or off (ALTASCRAPER_BACKGROUND).
"""
import json
import os
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
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


from domain import deploy_check as DC               # noqa: E402

SECRET = "sk-ant-THIS-MUST-NEVER-APPEAR"


def run(cfg_obj, env):
    tmp = tempfile.mkdtemp(prefix="altadc_")
    p = os.path.join(tmp, "app.json")
    json.dump(cfg_obj, open(p, "w"))
    saved = {k: os.environ.get(k) for k in ("ALTA_TOKEN_KEY", "ALTASCRAPER_BACKGROUND")}
    for k in saved:
        os.environ.pop(k, None)
    os.environ.update(env)
    try:
        res = DC.check(p)
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
    return {i["name"]: i for i in res["checks"]}, json.dumps(res)


items, blob = run({"accounts": [{"id": "o1", "auth": "oauth"}]}, {})
check("an OAuth account with no ALTA_TOKEN_KEY is a problem",
      items.get("ALTA_TOKEN_KEY is set (OAuth accounts)", {}).get("ok"), False)
items, _ = run({"accounts": [{"id": "o1", "auth": "oauth"}]}, {"ALTA_TOKEN_KEY": "k" * 44})
check("  and fine once it is set", items["ALTA_TOKEN_KEY is set (OAuth accounts)"]["ok"], True)
items, _ = run({"accounts": [{"id": "a"}]}, {})
check("no OAuth accounts: the key is not asked for", "ALTA_TOKEN_KEY is set (OAuth accounts)" in items, False)
check("no AI key is reported", items["An AI key is configured"]["ok"], False)
items, blob = run({"accounts": [], "anthropic_api_key": SECRET}, {})
check("an AI key present is fine", items["An AI key is configured"]["ok"], True)
check("  and its VALUE never appears in the report", SECRET in blob, False)
items, _ = run({"accounts": []}, {"ALTASCRAPER_BACKGROUND": "off"})
check("background work OFF is stated", "OFF" in items["Background work"]["detail"], True)
items, _ = run({"accounts": []}, {})
check("background work ON is stated", items["Background work"]["detail"].startswith("on"), True)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.exit(1 if fails else 0)
