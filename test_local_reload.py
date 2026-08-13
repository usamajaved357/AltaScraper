"""A locally running app must show template and CSS edits without a restart."""
import io, os, sys, time
sys.path.insert(0, r"D:\AltaScraper")
os.chdir(r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-58s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

src = io.open("dashboard.py", encoding="utf-8").read()

print("=== the two things that were frozen at startup ===")
check("templates are told to auto-reload off-server",
      'app.config["TEMPLATES_AUTO_RELOAD"] = True' in src, True)
check("  and the jinja env too (config alone is not enough once built)",
      "app.jinja_env.auto_reload = True" in src, True)
check("the asset stamp is re-read off-server", "if not _paas:" in src, True)
check("both sit behind the SAME PaaS check", src.count("if not _paas:"), 2)

print("\n=== a real Flask app behaves as intended ===")
from flask import Flask
import tempfile, shutil
TMP = tempfile.mkdtemp(prefix="altatpl_")
tpl = os.path.join(TMP, "t.html")
io.open(tpl, "w", encoding="utf-8").write("VERSION-ONE")

app = Flask(__name__, template_folder=TMP)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True

@app.route("/")
def index():
    from flask import render_template
    return render_template("t.html")

c = app.test_client()
check("first render", c.get("/").get_data(as_text=True).strip(), "VERSION-ONE")
time.sleep(1.05)                     # mtime resolution
io.open(tpl, "w", encoding="utf-8").write("VERSION-TWO")
check("the edit appears WITHOUT a restart",
      c.get("/").get_data(as_text=True).strip(), "VERSION-TWO")

print("\n=== and without it, the old behaviour is reproduced ===")
app2 = Flask(__name__, template_folder=TMP)
app2.jinja_env.auto_reload = False
@app2.route("/")
def index2():
    from flask import render_template
    return render_template("t.html")
c2 = app2.test_client()
check("first render", c2.get("/").get_data(as_text=True).strip(), "VERSION-TWO")
time.sleep(1.05)
io.open(tpl, "w", encoding="utf-8").write("VERSION-THREE")
check("the edit is INVISIBLE -- this was the bug",
      c2.get("/").get_data(as_text=True).strip(), "VERSION-TWO")

shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
