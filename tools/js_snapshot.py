"""Every global function the page defines, and its source, as a fingerprint.

    py -3.11 tools/js_snapshot.py OUT.json
    py -3.11 tools/js_snapshot.py --compare BEFORE.json AFTER.json

Milestone 4 moves JavaScript between files word for word. After such a move the
page must define exactly the same global functions with exactly the same source
(fn.toString()), and the same top-level let/const names must still resolve --
otherwise an inline onclick somewhere would find nothing, or the wrong thing.
This records both, after the page has loaded and every screen has been opened
once, on a temporary sandbox copy (tools/browser_smoke.py helpers; nothing real
is touched). --compare lists any function added, removed or changed, and exits
1 if there is one.
"""
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)


def _lexical_names():
    """Top-level let/const/class names in every script the page loads."""
    page = open(os.path.join(ROOT, "templates", "dashboard.html"), encoding="utf-8").read()
    names = set()
    for src in re.findall(r'<script src="/(static/js/[^"?]+)', page):
        p = os.path.join(ROOT, *src.split("/"))
        if not os.path.exists(p):
            continue
        for m in re.finditer(r"(?m)^(?:let|const|class)\s+([A-Za-z_$][\w$]*)", open(p, encoding="utf-8").read()):
            names.add(m.group(1))
        for m in re.finditer(r"(?m)^let\s+[^;]*", open(p, encoding="utf-8").read()):
            for n in re.findall(r",\s*([A-Za-z_$][\w$]*)\s*=", m.group(0)):
                names.add(n)
    return sorted(names)


_JS = r"""(names) => {
  const h = s => { let x = 2166136261; for (let i = 0; i < s.length; i++) { x ^= s.charCodeAt(i); x = Math.imul(x, 16777619); } return (x >>> 0).toString(16); };
  const fns = {};
  const skip = new Set(Object.getOwnPropertyNames(Object.getPrototypeOf(window)));
  for (const k of Object.getOwnPropertyNames(window)) {
    let v; try { v = window[k]; } catch (e) { continue; }
    if (typeof v === 'function' && !/\{\s*\[native code\]\s*\}\s*$/.test(Function.prototype.toString.call(v)))
      fns[k] = h(Function.prototype.toString.call(v));
  }
  const lex = {};
  for (const n of names) { try { lex[n] = typeof (0, eval)(n); } catch (e) { lex[n] = 'MISSING'; } }
  return {fns, lex};
}"""


def snapshot(out_path):
    import browser_smoke as bs
    from playwright.sync_api import sync_playwright
    tmp = tempfile.mkdtemp(prefix="jssnap_")
    cwd = os.getcwd()
    try:
        bs._copy_sandbox(tmp)
        srv, base = bs._serve(tmp)
        errors = []
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": 1366, "height": 900})
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base) else r.abort())
            page.goto(base + "/")
            page.wait_for_load_state("networkidle")
            for sec in bs.SCREENS:
                page.evaluate("s => { try { navTo(s); } catch (e) {} }", sec)
                try:
                    page.wait_for_load_state("networkidle", timeout=6000)
                except Exception:
                    pass
            got = page.evaluate(_JS, _lexical_names())
            b.close()
        srv.shutdown()
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    got["page_errors"] = errors
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(got, fh)
    missing = [k for k, v in got["lex"].items() if v == "MISSING"]
    print("js snapshot: %d functions, %d top-level names (%d unresolved), %d page errors -> %s"
          % (len(got["fns"]), len(got["lex"]), len(missing), len(errors), out_path))


def compare(a_path, b_path):
    A = json.load(open(a_path, encoding="utf-8"))
    B = json.load(open(b_path, encoding="utf-8"))
    out = []
    for k in sorted(set(A["fns"]) | set(B["fns"])):
        if A["fns"].get(k) != B["fns"].get(k):
            out.append("function %s: %s -> %s" % (k, A["fns"].get(k, "absent"), B["fns"].get(k, "absent")))
    for k in sorted(set(A["lex"]) | set(B["lex"])):
        if A["lex"].get(k) != B["lex"].get(k):
            out.append("name %s: %s -> %s" % (k, A["lex"].get(k, "absent"), B["lex"].get(k, "absent")))
    if len(A.get("page_errors", [])) != len(B.get("page_errors", [])):
        out.append("page errors: %d -> %d %s" % (len(A.get("page_errors", [])), len(B.get("page_errors", [])), B.get("page_errors", [])[:3]))
    print("functions: %d before, %d after; differences: %d" % (len(A["fns"]), len(B["fns"]), len(out)))
    for line in out[:30]:
        print("  " + line)
    return 1 if out else 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--compare":
        sys.exit(compare(a[1], a[2]))
    snapshot(a[0])
