# -*- coding: utf-8 -*-
"""Fix product types: which listings it checks, and why it leaves the rest out.

    "i selected 64 listings and clicked on fix product types it shows check 2
     unsent draft(s) ... 2 already right 0 couldn't check"
    "no more than 30 drafts have competitor asins in them and even if it is
     looking at all the drafts this count is wrong"

Four things, each run for real on a throwaway database with Amazon stubbed out:
  1. every listing left out is named, with its reason;
  2. the ticked listings are the ones checked (else the whole account);
  3. a draft with no competitor ASIN is checked by its TITLE through Amazon's
     product-type search, and nothing is written until Apply;
  4. submitted listings are left out unless included on purpose.
Plus the dialog's pure helpers, run in node.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(name, got, want):
    if got == want:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s   got=%r want=%r" % (name, got, want))
        FAILS.append(name)


tmp = tempfile.mkdtemp(prefix="pt_scope_")
cfg_path = os.path.join(tmp, "config.json")
with open(cfg_path, "w") as fh:
    json.dump({"accounts": [{"id": "nestwell_goods", "label": "Nestwell",
                             "default_marketplace": "UK"}]}, fh)
os.environ["ALTASCRAPER_DB"] = os.path.join(tmp, "altascraper.db")

from data import db as DB
conn = DB.get_db(cfg_path)
W = "nestwell_goods"
ROWS = [
    (W, "8.59_2Days_B0DNYVCK4J", "B0DNYVCK4J", "HOME", "API_READY", "Folding Camping Table"),
    (W, "9.10_2Days_B0DNYVCK4J", "B0DNYVCK4J", "HOME", "GENERATED", "Same competitor"),
    (W, "7.99_3Days_B07GDBY3YS", "B07GDBY3YS", "HOME", "LIVE", "Weed Puller"),
    (W, "6.00_3Days_B0SUBMITTD", "B0SUBMITTD", "HOME", "SUBMITTED", "Sent one"),
    (W, "PARENT-1", "", "HOME", "PARENT", "A parent"),
    (W, "Q-1", "B0QUEUED00", "", "QUEUED", "Waiting"),
    (W, "12.00_3Days_336636956670", "", "HOME", "GENERATED", "Memory Foam Bed Pillow"),
    (W, "13.00_3Days_336636956671", "", "HOME", "GENERATED", "Jump Rope or Exercise Band"),
    (W, "14.00_3Days_336636956672", "", "HOME", "GENERATED", ""),
    ("jack_uk", "12.00_3Days_336636956670", "", "HOME", "GENERATED", "Other account"),
]
for r in ROWS:
    conn.execute("INSERT INTO listings (workspace_id, sku, competitor_asin, product_type, status, title) "
                 "VALUES (?,?,?,?,?,?)", r)
conn.commit()

from listing import product_type as PT

# ------------------------------------------------------------ 1 + 4: reasons
print("== candidates: every listing is checked or left out WITH a reason ==")
got = PT.candidates(cfg_path, W)
check("checked, and how",
      sorted((d["sku"], d["method"]) for d in got["check"]),
      sorted([("8.59_2Days_B0DNYVCK4J", "asin"), ("9.10_2Days_B0DNYVCK4J", "asin"),
       ("12.00_3Days_336636956670", "title"), ("13.00_3Days_336636956671", "title")]))
check("left out, and why",
      sorted((s["sku"], s["reason"]) for s in got["skipped"]),
      sorted([("7.99_3Days_B07GDBY3YS", "on_amazon"), ("6.00_3Days_B0SUBMITTD", "submitted"),
       ("PARENT-1", "parent"), ("Q-1", "queued"),
       ("14.00_3Days_336636956672", "nothing_to_ask")]))
check("no listing is lost: checked + left out = the account",
      len(got["check"]) + len(got["skipped"]), 9)
check("a title draft carries no ASIN",
      {d["asin"] for d in got["check"] if d["method"] == "title"}, {""})

got = PT.candidates(cfg_path, W, include_submitted=True)
check("submitted included on purpose",
      "6.00_3Days_B0SUBMITTD" in [d["sku"] for d in got["check"]], True)
check("  but a LIVE one never is",
      "7.99_3Days_B07GDBY3YS" in [d["sku"] for d in got["check"]], False)

check("drafts_to_check keeps its old meaning (ASIN drafts, nothing submitted)",
      sorted(d["sku"] for d in PT.drafts_to_check(cfg_path, W)),
      ["8.59_2Days_B0DNYVCK4J", "9.10_2Days_B0DNYVCK4J"])

# ------------------------------------------------------------------ 2: ticked
print("\n== candidates: the ticked listings ==")
got = PT.candidates(cfg_path, W, skus=["12.00_3Days_336636956670", "7.99_3Days_B07GDBY3YS", "NOPE-1"])
check("only the ticked are checked", [d["sku"] for d in got["check"]], ["12.00_3Days_336636956670"])
check("a ticked one not in this account is said, not dropped",
      sorted((s["sku"], s["reason"]) for s in got["skipped"]),
      [("7.99_3Days_B07GDBY3YS", "on_amazon"), ("NOPE-1", "not_found")])

# ------------------------------------------------------------ compare, titles
print("\n== compare: title answers are keyed per SKU and carry the options ==")
drafts = [{"sku": "A", "title": "Pillow", "asin": "", "product_type": "HOME", "method": "title"},
          {"sku": "B", "title": "Band", "asin": "", "product_type": "EXERCISE_BAND", "method": "title"},
          {"sku": "C", "title": "Table", "asin": "B0DNYVCK4J", "product_type": "HOME", "method": "asin"}]
answers = {"title:A": {"status": "ok", "product_type": "PILLOW", "options": ["PILLOW", "BED_PILLOW"]},
           "title:B": {"status": "ok", "product_type": "EXERCISE_BAND", "options": ["EXERCISE_BAND"]},
           "B0DNYVCK4J": {"status": "ok", "product_type": "TABLE"}}
v = {r["sku"]: r for r in PT.compare(drafts, answers)}
check("title A is a change with its options",
      (v["A"]["verdict"], v["A"]["amazon"], v["A"]["options"], v["A"]["method"]),
      ("change", "PILLOW", ["PILLOW", "BED_PILLOW"], "title"))
check("title B already right", v["B"]["verdict"], "same")
check("ASIN C still keyed by ASIN", (v["C"]["verdict"], v["C"]["method"]), ("change", "asin"))

# ------------------------------------------------------------------ the routes
print("\n== the routes ==")
from flask import Flask
import accounts as ACC
from api import amazon_catalog as C
from routes import product_type_routes as R

app = Flask(__name__)
R.register(app, CONFIG_PATH=cfg_path, _cfg=lambda: json.load(open(cfg_path)),
           _state={"active_account_id": W})
cli = app.test_client()

asked, searched = [], []
real = (ACC.resolve_catalog_creds, C.product_type_of, C.search_product_types)
try:
    ACC.resolve_catalog_creds = lambda cfg, acc, path=None: ({"refresh_token": "x"}, None)
    C.product_type_of = lambda creds, mkt, mid, asin, timeout=30: (
        asked.append(asin) or {"status": "ok", "product_type": "TABLE", "error": ""})

    def _search(creds, mkt, mid, item_name="", keywords="", timeout=30):
        searched.append(item_name)
        if "Pillow" in item_name:
            return {"status": "ok", "error": "",
                    "types": [{"name": "PILLOW", "display_name": "Pillow"},
                              {"name": "BED_PILLOW", "display_name": "Bed Pillow"}]}
        return {"status": "none", "types": [], "error": ""}
    C.search_product_types = _search

    j = cli.post("/product_types/drafts", json={
        "account": W, "skus": ["12.00_3Days_336636956670", "6.00_3Days_B0SUBMITTD"]}).get_json()
    check("POST drafts: ticked only", [d["sku"] for d in j["drafts"]], ["12.00_3Days_336636956670"])
    check("  with the reasons", [(s["sku"], s["reason"]) for s in j["skipped"]],
          [("6.00_3Days_B0SUBMITTD", "submitted")])
    check("  and how many were ticked", j["selected"], 2)

    j = cli.post("/product_types/drafts", json={
        "account": W, "skus": ["6.00_3Days_B0SUBMITTD"], "include_submitted": True}).get_json()
    check("POST drafts: submitted included on request",
          ([d["sku"] for d in j["drafts"]], j["skipped"]), (["6.00_3Days_B0SUBMITTD"], []))

    j = cli.post("/product_types/lookup", json={
        "account": W, "marketplace": "UK",
        "skus": ["8.59_2Days_B0DNYVCK4J", "9.10_2Days_B0DNYVCK4J",
                 "12.00_3Days_336636956670", "13.00_3Days_336636956671",
                 "6.00_3Days_B0SUBMITTD"]}).get_json()
    rows = {r["sku"]: r for r in j["rows"]}
    check("one catalogue call for two drafts of one competitor", asked, ["B0DNYVCK4J"])
    check("one search per titled draft, by its title",
          sorted(searched), ["Jump Rope or Exercise Band", "Memory Foam Bed Pillow"])
    check("titled pillow: Amazon's first type, and the choices",
          (rows["12.00_3Days_336636956670"]["verdict"], rows["12.00_3Days_336636956670"]["amazon"],
           rows["12.00_3Days_336636956670"]["options"]),
          ("change", "PILLOW", ["PILLOW", "BED_PILLOW"]))
    check("no suggestion is couldn't-check, never a guess",
          (rows["13.00_3Days_336636956671"]["verdict"], rows["13.00_3Days_336636956671"]["amazon"]),
          ("not_checked", ""))
    check("a submitted SKU is not looked up unless included",
          "6.00_3Days_B0SUBMITTD" in rows, False)
    check("nothing written by the lookup",
          conn.execute("SELECT product_type FROM listings WHERE workspace_id=? AND sku=?",
                       (W, "12.00_3Days_336636956670")).fetchone()[0], "HOME")

    asked.clear()
    j = cli.post("/product_types/lookup", json={
        "account": W, "marketplace": "UK", "skus": ["6.00_3Days_B0SUBMITTD"],
        "include_submitted": True}).get_json()
    check("included submitted is looked up", (asked, [r["sku"] for r in j["rows"]]),
          (["B0SUBMITTD"], ["6.00_3Days_B0SUBMITTD"]))

    # A refused search does not stop the catalogue lookups, and vice versa.
    asked.clear(); searched.clear()
    C.search_product_types = lambda *a, **k: (
        searched.append(k.get("item_name")) or {"status": "denied", "types": [], "error": "refused"})
    j = cli.post("/product_types/lookup", json={
        "account": W, "marketplace": "UK",
        "skus": ["12.00_3Days_336636956670", "13.00_3Days_336636956671", "8.59_2Days_B0DNYVCK4J"]}).get_json()
    check("a refused search is asked once, not per title", len(searched), 1)
    check("  and the ASIN lookup still ran", asked, ["B0DNYVCK4J"])
    check("  and the response says denied", j["denied"], True)

    many = ["X%d" % i for i in range(16)]
    for s in many:
        conn.execute("INSERT INTO listings (workspace_id, sku, competitor_asin, product_type, status, title) "
                     "VALUES (?,?,?,?,?,?)", (W, s, "", "HOME", "GENERATED", "Title " + s))
    conn.commit()
    r = cli.post("/product_types/lookup", json={"account": W, "marketplace": "UK", "skus": many})
    check("more than 15 lookups in one request is refused", r.status_code, 400)
finally:
    ACC.resolve_catalog_creds, C.product_type_of, C.search_product_types = real

# --------------------------------------------------------- the dialog, in node
print("\n== the dialog's helpers, run ==")
PJ = open(os.path.join(HERE, "static", "js", "product_type.js"), encoding="utf-8").read()
check("the ticked listings are used", "selectedSkus()" in PJ, True)
check("applied changes still go through editField",
      'editField(r.sku, "col", "Product Type", r.amazon)' in PJ, True)
check("submitted are included only by a button press", '"Include them"' in PJ, True)

node = shutil.which("node")
if not node:
    print("  FAIL  node not found")
    FAILS.append("node")
else:
    script = PJ + r"""
;(function(){
  const out = {};
  const g = ptSkipGroups([{sku:"a",reason:"submitted"},{sku:"b",reason:"on_amazon"},{sku:"c",reason:"submitted"}]);
  out.groups = g.map(x => [x.reason, x.items.map(i => i.sku), !!x.why]);
  out.pre = [
    ptPreticked({verdict:"change", method:"asin"}),
    ptPreticked({verdict:"change", method:"title", options:["PILLOW"]}),
    ptPreticked({verdict:"change", method:"title", options:["PILLOW","BED_PILLOW"]}),
    ptPreticked({verdict:"same", method:"asin"}),
  ];
  function row(i, ticked, pick){
    return {getAttribute: () => String(i),
            querySelector: sel => sel === ".ptfix-tick" ? {checked: ticked}
                                : (sel === ".ptfix-pick" ? (pick === undefined ? null : {value: pick}) : null)};
  }
  const wrap = {querySelectorAll: () => [row(0, true), row(1, false), row(2, true, "bed_pillow")]};
  const changes = [{sku:"A", amazon:"TABLE"}, {sku:"B", amazon:"CHAIR"}, {sku:"C", amazon:"PILLOW"}];
  out.chosen = ptReadChoices(wrap, changes).map(r => [r.sku, r.amazon]);
  out.untouched = changes[2].amazon;
  console.log(JSON.stringify(out));
})();
"""
    path = os.path.join(tmp, "pt_run.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(script)
    p = subprocess.run([node, path], capture_output=True, text=True)
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        out = {}
        print(p.stdout, p.stderr)
    check("left-out grouped by reason, first-seen order",
          out.get("groups"), [["submitted", ["a", "c"], True], ["on_amazon", ["b"], True]])
    check("preticked only where there is one answer", out.get("pre"), [True, True, False, False])
    check("only ticked rows applied, with the type picked",
          out.get("chosen"), [["A", "TABLE"], ["C", "BED_PILLOW"]])
    check("  and the original row is not mutated", out.get("untouched"), "PILLOW")

print()
if FAILS:
    print("FAILED: %d" % len(FAILS))
    sys.exit(1)
print("all passed")
