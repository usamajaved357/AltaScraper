"""What every element on every screen LOOKS like, as a fingerprint (Milestone 4).

    py -3.11 tools/style_snapshot.py OUT.json [--width 1366] [--only sales,orders]
    py -3.11 tools/style_snapshot.py --compare BEFORE.json AFTER.json

A move of CSS or JS must not change what anybody sees. This proves it: for each
screen (and the product page open over Listings) it records every element's
full computed style -- all properties, plus its ::before and ::after -- as a
hash, keyed by the element's position in the page. Two snapshots taken before
and after a change must be identical; --compare prints the first differences
(screen, element, which properties) and exits 1 if there are any.

Runs on a temporary copy of the sandbox with the same seeded data and the same
blocked outside world as tools/browser_smoke.py (it reuses its helpers), so
nothing real is read or written. Animations are frozen and the clock is not a
factor: only styles are compared, not pixels.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

_JS = r"""(rootSel) => {
  const props = [];
  const probe = getComputedStyle(document.documentElement);
  for (let i = 0; i < probe.length; i++) props.push(probe[i]);
  props.sort();
  const h = s => { let x = 2166136261; for (let i = 0; i < s.length; i++) { x ^= s.charCodeAt(i); x = Math.imul(x, 16777619); } return (x >>> 0).toString(16); };
  const pathOf = e => { const p = []; for (; e && e !== document.documentElement; e = e.parentElement) {
      let i = 0, s = e; while ((s = s.previousElementSibling)) i++; p.push(e.tagName.toLowerCase() + ':' + i); }  // position only: some screens mint random ids per render
    return p.reverse().join('>'); };
  const out = {};
  const roots = rootSel.split(',').map(s => document.querySelector(s)).filter(Boolean);
  const all = [];
  for (const r of roots) { all.push(r); r.querySelectorAll('*').forEach(e => all.push(e)); }
  for (const e of all) {
    if (e.closest('script,style,template,svg defs')) continue;
    const parts = [];
    for (const pseudo of [null, '::before', '::after']) {
      const cs = getComputedStyle(e, pseudo);
      if (pseudo && (cs.content === 'none' || cs.content === 'normal')) { parts.push(''); continue; }
      parts.push(props.map(p => p + ':' + cs.getPropertyValue(p)).join(';'));
    }
    out[pathOf(e)] = [h(parts[0]), h(parts[1]), h(parts[2])];
  }
  return out;
}"""

# WAIT UNTIL THE PAGE HAS STOPPED CHANGING: a panel caught mid-load (a spinner
# in one run, the finished grid in the other) is a difference in DATA timing,
# not in styles. Resolves after 1s with no DOM change, or after 12s regardless.
_QUIET = r"""() => new Promise(res => {
  let t = setTimeout(done, 1000); const cap = setTimeout(done, 12000);
  const mo = new MutationObserver(() => { clearTimeout(t); t = setTimeout(done, 1000); });
  mo.observe(document.body, {subtree: true, childList: true, attributes: true, characterData: true});
  function done() { mo.disconnect(); clearTimeout(cap); res(true); }
})"""

# Everything that could make two identical builds differ, frozen.
_FREEZE = """*, *::before, *::after { animation: none !important; transition: none !important;
  caret-color: transparent !important; }"""


def snapshot(out_path, width=1366, only=None):
    import browser_smoke as bs
    from playwright.sync_api import sync_playwright
    tmp = tempfile.mkdtemp(prefix="stylesnap_")
    cwd = os.getcwd()
    result = {"width": width, "screens": {}}
    try:
        bs._copy_sandbox(tmp)
        srv, base = bs._serve(tmp)
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(viewport={"width": width, "height": 900})
            page = ctx.new_page()
            page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base) else r.abort())
            page.goto(base + "/")
            page.wait_for_load_state("networkidle")
            ids = page.evaluate("() => (ACCOUNTS || []).map(a => a.id)")
            bs._seed_markers(srv.db_path, {"A": ids[0], "B": ids[1]})
            page.evaluate("id => enterAccount(id)", ids[0])
            page.wait_for_load_state("networkidle")
            screens = [s for s in bs.SCREENS if not only or s in only]
            for sec in screens:
                page.evaluate("s => { try { navTo(s); } catch (e) {} }", sec)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                page.add_style_tag(content=_FREEZE)
                page.evaluate(_QUIET)
                # Only what is ON SCREEN: this screen and the top bar. Hidden
                # screens keep whatever state an earlier visit left behind.
                result["screens"][sec] = page.evaluate(_JS, "#sec_%s,.appbar" % sec)
            if not only or "listings" in only:
                page.evaluate("() => navTo('listings')")
                page.wait_for_load_state("networkidle")
                sku = page.evaluate("() => ((typeof ROWS !== 'undefined' && ROWS) || [])[0] ? ROWS[0].sku : ''")
                if sku:
                    page.evaluate("s => pdpOpen(s)", sku)
                    page.wait_for_load_state("networkidle")
                    page.add_style_tag(content=_FREEZE)
                    page.evaluate(_QUIET)
                    result["screens"]["pdp"] = page.evaluate(_JS, "#pdp")
            b.close()
        srv.shutdown()
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh)
    n = sum(len(v) for v in result["screens"].values())
    print("snapshot: %d screens, %d elements -> %s" % (len(result["screens"]), n, out_path))


def compare(a_path, b_path, show=12):
    A = json.load(open(a_path, encoding="utf-8"))["screens"]
    B = json.load(open(b_path, encoding="utf-8"))["screens"]
    diffs = []
    for sec in sorted(set(A) | set(B)):
        a, b = A.get(sec, {}), B.get(sec, {})
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                diffs.append((sec, k, a.get(k), b.get(k)))
    print("screens: %d before, %d after; elements compared: %d; differences: %d"
          % (len(A), len(B), sum(len(v) for v in A.values()), len(diffs)))
    for d in diffs[:show]:
        print("  %s  %s\n     before %s\n     after  %s" % d)
    return 1 if diffs else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--compare":
        sys.exit(compare(args[1], args[2]))
    w = int(args[args.index("--width") + 1]) if "--width" in args else 1366
    only = args[args.index("--only") + 1].split(",") if "--only" in args else None
    snapshot(args[0], w, only)
