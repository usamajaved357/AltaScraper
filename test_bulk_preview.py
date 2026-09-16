# -*- coding: utf-8 -*-
"""Preview the ticked listings -- including submitted ones, without un-submitting them.

    "it says it is fixed 33 but still when i open pdp i see that error message
     still displaying there"
    "yes add the bulk preview button in the app. which lets user to preview
     selected listings"

The warning on a listing's page is Amazon's reply to its last Preview/Submit.
Preview skipped SUBMITTED listings, so their warnings could never be refreshed;
and a Preview writes API_READY / API_ERROR into the status, which on a submitted
listing would put it back among the drafts.

This RUNS the generator's real Preview loop (run_api) with the store and Amazon
replaced, and checks what it writes.
"""
import json
import os
import re
import sys

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


# ------------------------------------------------------------------ the rule
print("== listing/preview_scope ==")
from listing import preview_scope as PS
check("whole-account Preview does not take SUBMITTED", "SUBMITTED" in PS.eligible(False), False)
check("a named (ticked) Preview does", "SUBMITTED" in PS.eligible(False, named=True), True)
check("Submit is unchanged, named or not",
      (PS.eligible(True), PS.eligible(True, named=True)),
      ({"APPROVED", "API_READY"}, {"APPROVED", "API_READY"}))
check("the old Preview set is intact", PS.eligible(False),
      {"APPROVED", "API_READY", "API_ERROR", "NEEDS_REVIEW", "COMPLIANCE_HOLD", "IP_HOLD", "HOLD", ""})
check("a submitted listing's Preview keeps its status", PS.keeps_status(False, "submitted"), True)
check("  a draft's does not", PS.keeps_status(False, "API_ERROR"), False)
check("  and Submit never does", PS.keeps_status(True, "SUBMITTED"), False)

# --------------------------------------------------------- the real loop, run
print("\n== run_api (preview), store and Amazon replaced ==")
import amazon_listing_generator as G
import sp_api.api as SP
from listing import repo as REPO

HEAD = ["SKU", "Status", "Notes", "Product Type", "API Payload JSON", "API Issues JSON", "UPC", "Brand"]
OLD = json.dumps({"v": 1, "at": "2026-09-11 19:29:41", "mode": "submit", "status": "ACCEPTED",
                  "issues": [{"code": "18367", "severity": "WARNING", "message": "type updated",
                              "fields": ["product_type"]}]})
RECORDS = [
    {"SKU": "SUB-CLEAN", "Status": "SUBMITTED", "Notes": "API SUBMITTED -- accepted", "Product Type": "PILLOW",
     "API Payload JSON": "{submitted body}", "API Issues JSON": OLD, "UPC": "", "Brand": ""},
    {"SKU": "SUB-ERR", "Status": "SUBMITTED", "Notes": "API SUBMITTED -- accepted", "Product Type": "PILLOW",
     "API Payload JSON": "{submitted body}", "API Issues JSON": OLD, "UPC": "", "Brand": ""},
    {"SKU": "DRAFT", "Status": "API_ERROR", "Notes": "", "Product Type": "PILLOW",
     "API Payload JSON": "", "API Issues JSON": OLD, "UPC": "", "Brand": ""},
    {"SKU": "SUB-UNTICKED", "Status": "SUBMITTED", "Notes": "keep", "Product Type": "PILLOW",
     "API Payload JSON": "", "API Issues JSON": OLD, "UPC": "", "Brand": ""},
]
WRITES = []
CALLS = []


class _Resp:
    def __init__(self, payload):
        self.payload = payload


class _Listings:
    def __init__(self, **kw):
        pass

    def put_listings_item(self, seller_id, sku, **kw):
        CALLS.append((sku, kw.get("mode")))
        if sku == "SUB-ERR":
            return _Resp({"status": "INVALID", "issues": [
                {"code": "90220", "severity": "ERROR", "message": "missing", "attributeNames": ["color"]}]})
        return _Resp({"status": "VALID", "issues": []})


def _a1_to_rc(a1):
    m = re.match(r"([A-Z]+)(\d+)", a1)
    col = 0
    for ch in m.group(1):
        col = col * 26 + (ord(ch) - 64)
    return int(m.group(2)), col


saved = {n: getattr(G, n) for n in ("sp_creds", "seller_id_for", "output_ws", "_safe_records",
                                    "_raw_schema_bounded", "build_api_attributes")}
saved_repo = (REPO.read_headers, REPO.batch_write)
saved_li = getattr(SP, "ListingsItemsV20210801")


def run(submit, only):
    del WRITES[:]
    del CALLS[:]
    G.run_api({}, None, {}, submit=submit, marketplace="UK", only_skus=only)
    out = {}
    for u in WRITES:
        r, c = _a1_to_rc(u["range"])
        out[(RECORDS[r - 2]["SKU"], HEAD[c - 1])] = u["values"][0][0]
    return out


try:
    G.sp_creds = lambda config, mkt: {}
    G.seller_id_for = lambda config, mkt: "A1SELLER"
    G.output_ws = lambda config, gc, sid, tab: object()
    G._safe_records = lambda ws: [dict(r) for r in RECORDS]
    G._raw_schema_bounded = lambda pt, creds, hard_timeout=180: ({"item_name": {}}, [], None)
    G.build_api_attributes = lambda row, pt, props, required, config: {"item_name": [{"value": "x"}]}
    REPO.read_headers = lambda ws: list(HEAD)
    REPO.batch_write = lambda ws, updates, value_input_option="RAW": WRITES.extend(updates)
    SP.ListingsItemsV20210801 = _Listings

    w = run(False, {"SUB-CLEAN", "SUB-ERR", "DRAFT"})
    check("the ticked submitted listings are previewed, as VALIDATION_PREVIEW",
          sorted(CALLS), [("DRAFT", "VALIDATION_PREVIEW"), ("SUB-CLEAN", "VALIDATION_PREVIEW"),
                          ("SUB-ERR", "VALIDATION_PREVIEW")])
    check("a clean Preview CLEARS a submitted listing's old warning", w.get(("SUB-CLEAN", "API Issues JSON")), "")
    check("  its status is not written", ("SUB-CLEAN", "Status") in w, False)
    check("  nor its note", ("SUB-CLEAN", "Notes") in w, False)
    check("  nor the record of what was submitted", ("SUB-CLEAN", "API Payload JSON") in w, False)
    got = json.loads(w.get(("SUB-ERR", "API Issues JSON")) or "{}")
    check("a submitted listing with a new complaint gets the new reply",
          [(i["code"], i["fields"]) for i in got.get("issues", [])], [("90220", ["color"])])
    check("  and still is not made API_ERROR", ("SUB-ERR", "Status") in w, False)
    check("a draft's Preview still sets its status", w.get(("DRAFT", "Status")), "API_READY")
    check("  and its note", w.get(("DRAFT", "Notes")), "API PREVIEW clean")
    check("an unticked submitted listing is not touched",
          [k for k in w if k[0] == "SUB-UNTICKED"], [])

    w = run(False, None)
    check("whole-account Preview still skips submitted listings",
          sorted(c[0] for c in CALLS), ["DRAFT"])

    w = run(True, {"SUB-CLEAN", "DRAFT"})
    check("Submit never takes a submitted or errored listing", CALLS, [])
finally:
    for n, f in saved.items():
        setattr(G, n, f)
    REPO.read_headers, REPO.batch_write = saved_repo
    SP.ListingsItemsV20210801 = saved_li

# ------------------------------------------------------------------ the screen
print("\n== the screen ==")
TP = open(os.path.join(HERE, "templates", "dashboard.html"), encoding="utf-8").read()
SJ = open(os.path.join(HERE, "static", "js", "submit.js"), encoding="utf-8").read()
PJ = open(os.path.join(HERE, "static", "js", "product_type.js"), encoding="utf-8").read()
bar = TP[TP.find('id="selbar"'):]
bar = bar[:bar.find("</div>")]
check("the selection bar has a Preview button", 'onclick="bulkPreview()"' in bar, True)
body = SJ[SJ.find("async function bulkPreview"):SJ.find("async function submitOne")]
check("it previews the ticked listings", "selectedSkus()" in body, True)
check("  as one run scoped to them", 'runMode("api", s.drafts)' in body, True)
check("  after a confirmation", "uiConfirm(" in body, True)
check("the browser does not keep its own list of previewable statuses",
      "API_READY" in body or "NEEDS_REVIEW" in body, False)
check("Fix product types says how to clear the old warnings", "press Preview on the selection bar" in PJ, True)

print()
if FAILS:
    print("FAILED: %d" % len(FAILS))
    sys.exit(1)
print("all passed")
