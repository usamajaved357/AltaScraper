"""tools/asset_report.py -- what the dashboard page makes a browser download.

    py -3.11 tools/asset_report.py            table, biggest first
    py -3.11 tools/asset_report.py --json     the same, machine-readable

A MEASUREMENT, NOT AN OPINION. The roadmap asked for performance to be measured
before anything is "optimised", and the first question is always how much the
page weighs. This reads templates/dashboard.html, finds every /static/ script
and stylesheet it loads, and reports each file's size on disk and gzipped (what
actually crosses the wire when the server compresses).

Reads files only. Starts no app, opens no database, makes no network call, and
writes nothing -- so it is safe to run anywhere, including against a checkout
with no config.json at all.
"""
import gzip
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "templates", "dashboard.html")
REF = re.compile(r'(?:src|href)="/static/([^"?]+)(?:\?[^"]*)?"')


def assets(page=PAGE):
    """[(published path, bytes, gzipped bytes)] in the order the page loads them."""
    html = open(page, encoding="utf-8").read()
    seen, out = set(), []
    for rel in REF.findall(html):
        if rel in seen or not rel.endswith((".js", ".css")):
            continue
        seen.add(rel)
        fp = os.path.join(ROOT, "static", *rel.split("/"))
        if not os.path.isfile(fp):
            out.append((rel, None, None))       # referenced but missing: say so
            continue
        raw = open(fp, "rb").read()
        out.append((rel, len(raw), len(gzip.compress(raw, 6))))
    return out


def main(argv):
    rows = assets()
    have = [r for r in rows if r[1] is not None]
    missing = [r[0] for r in rows if r[1] is None]
    total = sum(r[1] for r in have)
    total_gz = sum(r[2] for r in have)
    if "--json" in argv:
        print(json.dumps({"files": [{"path": p, "bytes": b, "gzip": g} for p, b, g in rows],
                          "total_bytes": total, "total_gzip": total_gz,
                          "missing": missing}, indent=1))
        return 1 if missing else 0
    print("%-44s %10s %10s" % ("file", "KB", "KB gzip"))
    for p, b, g in sorted(have, key=lambda r: -r[1]):
        print("%-44s %10.1f %10.1f" % (p, b / 1024.0, g / 1024.0))
    js = [r for r in have if r[0].endswith(".js")]
    css = [r for r in have if r[0].endswith(".css")]
    print("-" * 66)
    print("%-44s %10.1f %10.1f" % ("%d scripts" % len(js),
                                   sum(r[1] for r in js) / 1024.0,
                                   sum(r[2] for r in js) / 1024.0))
    print("%-44s %10.1f %10.1f" % ("%d stylesheets" % len(css),
                                   sum(r[1] for r in css) / 1024.0,
                                   sum(r[2] for r in css) / 1024.0))
    print("%-44s %10.1f %10.1f" % ("TOTAL", total / 1024.0, total_gz / 1024.0))
    for m in missing:
        print("MISSING: /static/" + m + " is loaded by the page but not on disk")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
