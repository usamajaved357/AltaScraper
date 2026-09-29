"""The retired Dropshipping workspace's dropshipping_* keys are not read (owner, 29 Sep 2026).

read.txt: "Leftover dropshipping branch: Conditionally APPROVED for removal ...
prove the dropshipping_* keys are genuinely unused ... If they are unused,
remove the dead branch with tests."

The proof (29 Sep 2026, read-only): no dropshipping_* key in any of 45 config,
account, brand or data JSON files, and the only remaining reader was the
no-account branch of listing/run_command.build_api_run_args; its settings route
(/settings/dropshipping_sheets) had already been removed. This pins that:
  - no application code reads a dropshipping_* key any more;
  - build_api_run_args with no account adds nothing, even if such keys exist.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


from listing import run_command as RC

CFG = {"dropshipping_output_spreadsheet_id": "DS_OUT", "dropshipping_output_tab": "DS_TAB",
       "dropshipping_output_tab_gid": "7", "dropshipping_input_spreadsheet_id": "DS_IN",
       "dropshipping_input_tab_gid": "9"}
for mode in ("api", "api_submit"):
    argv = RC.build_api_run_args(mode, script="gen.py", python_exe="py", skus="S1",
                                 active_account=None, cfg=CFG, config_path="config.json")
    check("%s with no account: nothing from dropshipping_* keys" % mode,
          [a for a in argv if a.startswith("DS_") or a in ("7", "9")], [])
    check("  just the mode and the SKU", argv,
          ["py", "-u", "gen.py"] + (["api"] if mode == "api" else ["api", "submit"]) + ["--skus", "S1"])

READ = re.compile(r"""\.get\(\s*["']dropshipping_|\[\s*["']dropshipping_""")
readers = []
for d, dirs, files in os.walk(HERE):
    dirs[:] = [x for x in dirs if x not in (".git", "_merge_2026-07-04", "__pycache__",
                                            "node_modules", "active", ".claude")]
    for f in files:
        if f.endswith((".py", ".js")) and not f.startswith("test_"):
            p = os.path.join(d, f)
            if READ.search(open(p, "rb").read().decode("utf-8", "replace")):
                readers.append(os.path.relpath(p, HERE))
check("no application code reads a dropshipping_* key", readers, [])

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\nthe dropshipping_* keys are gone for good")
