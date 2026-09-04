"""Amazon's reply to a Preview/Submit is KEPT, and SHOWN.

Before this, putListingsItem's issues array was flattened into one Notes
sentence ("API SUBMIT REJECTED by Amazon (3 error(s)): ...") and the field names
Amazon blamed were thrown away. The listing page showed nothing at all: a
submit failed and there was no way on that page to see why.

These check the whole path -- pack/parse, the storage column, the generator
write, dashboard._card serving it, and the page drawing it.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def _read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8") as f:
        return f.read()


def code(src):
    """JS with its comments stripped -- a test must not pass on a comment."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


# ---- the shape ------------------------------------------------------------

def test_pack_keeps_the_field_names():
    from listing import api_issues
    raw = api_issues.pack([
        {"code": "4000001", "severity": "ERROR",
         "message": "The value is invalid.",
         "attributeNames": ["item_dimensions", "package_dimensions"]},
    ], mode="submit", status="INVALID")
    doc = json.loads(raw)
    assert doc["mode"] == "submit" and doc["status"] == "INVALID"
    assert doc["issues"][0]["fields"] == ["item_dimensions", "package_dimensions"], \
        "attributeNames is the whole point -- it must survive"
    assert doc["issues"][0]["code"] == "4000001"


def test_no_issues_clears_the_column():
    """A listing that previews clean must stop showing yesterday's rejection."""
    from listing import api_issues
    assert api_issues.pack([]) == ""
    assert api_issues.pack(None) == ""


def test_parse_never_raises():
    from listing import api_issues
    for junk in ("", None, "not json", "{", "[]", "API SUBMIT REJECTED by Amazon",
                 '{"issues": "nonsense"}', 17):
        rec = api_issues.parse(junk)
        assert rec["issues"] == [], junk


def test_parse_accepts_a_bare_array():
    from listing import api_issues
    rec = api_issues.parse(json.dumps([
        {"severity": "WARNING", "message": "m", "attributeNames": "brand"}]))
    assert rec["issues"][0]["fields"] == ["brand"], "a string attributeNames is one name"


def test_errors_and_by_field():
    from listing import api_issues
    raw = api_issues.pack([
        {"code": "1", "severity": "ERROR", "message": "bad", "attributeNames": ["brand"]},
        {"code": "2", "severity": "WARNING", "message": "meh", "attributeNames": ["brand"]},
        {"code": "3", "severity": "INFO", "message": "fyi"},
    ])
    assert len(api_issues.errors(raw)) == 1
    assert len(api_issues.by_field(raw)["brand"]) == 2
    assert "fyi" not in json.dumps(api_issues.by_field(raw)), \
        "an issue that names no field belongs at the top, not against a box"


# ---- the storage ----------------------------------------------------------

def test_the_column_exists_both_ways():
    """New databases get it from SCHEMA; existing ones from _ADDED_COLUMNS."""
    src = _read("data", "db.py")
    assert "api_issues_json TEXT" in src, "not in CREATE TABLE listings"
    assert '("listings", "api_issues_json", "TEXT")' in src, \
        "a database that already exists would never gain it"


def test_the_header_is_mapped_and_last():
    """ORDERED_HEADERS is this dict in order and positional writes follow it,
    so a new key must go on the END or it shifts every column after it."""
    from data.column_map import HEADER_TO_COL
    assert HEADER_TO_COL["API Issues JSON"] == "api_issues_json"
    assert list(HEADER_TO_COL)[-1] == "API Issues JSON"


def test_the_live_database_has_the_column():
    from data import db
    conn = db.get_db(os.path.join(HERE, "config.json"))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(listings)")}
    assert "api_issues_json" in cols


# ---- the generator writes it ---------------------------------------------

def test_generator_records_amazons_reply():
    src = _read("amazon_listing_generator.py")
    assert 'issues_col  = col("API Issues JSON")' in src
    assert "_api_issues.pack(" in src
    # Written on EVERY outcome, not just the failures: pack() returns "" for a
    # clean reply, and that empty string is what clears a stale rejection.
    body = src[src.index("msgs    = _issue_str(issues, attrs)"):]
    body = body[:body.index("if submit:")]
    assert "issues_col" in body, "the write must sit before the pass/fail branch"


# ---- the server serves it -------------------------------------------------

def test_card_serves_the_parsed_record():
    src = _read("dashboard.py")
    assert "from listing import api_issues as _api_issues" in src
    assert '"api_issues":   _api_issues.parse(g("API Issues JSON"))' in src


# ---- the page draws it ----------------------------------------------------

def test_pdp_draws_the_banner_above_the_tabs():
    js = code(_read("static", "js", "pdp.js"))
    assert "function pdpApiIssues(r)" in js
    # It goes in `blocking` -- the same place the barcode clash and compliance
    # panels go, which is above the tab strip and never folded.
    blk = js[js.index("const blocking ="):]
    blk = blk[:blk.index(";")]
    assert "pdpApiIssues(r)" in blk


def test_field_names_are_buttons_that_go_somewhere():
    js = code(_read("static", "js", "pdp.js"))
    assert "function pdpGoToField(key)" in js
    assert "pdpGoToField(" in js.split("function pdpGoToField")[0], \
        "nothing calls it"
    go = js[js.index("function pdpGoToField"):]
    # The attributes moved onto Product Details -- there is no Attributes tab
    # any more (PDP_MATCH_MOCKUP.md), so this switches to details.
    assert 'PDP_TAB = "details"' in go, "the field is on the details tab now"
    assert "scrollIntoView" in go
    assert ".pdp-attr-label" in go, "it walks the rows, not table cells"


def test_each_attribute_row_carries_its_own_complaint():
    js = code(_read("static", "js", "pdp.js"))
    tbl = js[js.index("function pdpAttrRows"):js.index("function pdpApiIssues")]
    assert "rowIssues" in tbl
    assert 'm.row && m.row.api_issues' in tbl
    # A SHORT LINE, not the message again. PDP_MATCH_MOCKUP.md step 7:
    #     "Do NOT duplicate the full error message next to the field -- the
    #      field only gets a red border + short one-line summary."
    assert "pdp-afield" in tbl, "the row must say Amazon complained about it"
    # The VISIBLE text is a label; Amazon's own sentence is in the title
    # attribute (hover) and, in full, in the banner at the top.
    assert "Amazon refused this field" in tbl
    assert "esc(mine.map(x => x.message" in tbl, \
        "the full wording should be the tooltip"
    assert "'<div>' + esc(x.message" not in tbl, \
        "it must not be printed under the box as well"
    # Amazon names the PARENT even when the fault is in a child
    # (item_dimensions.length.value), so the key is the top level.
    assert 'String(f).split(".")[0]' in tbl


def test_attr_model_carries_the_row():
    js = code(_read("static", "js", "autofix.js"))
    m = js[js.index("attrModel: {"):]
    m = m[:m.index("productType:")]
    assert "row: r," in m, "pdpAttrTable cannot see api_issues without it"


def test_the_styles_exist():
    css = _read("static", "css", "pdp.css")
    # .pdp-at tr.pdp-hit -> .pdp-attr.pdp-hit: the attributes are rows in a
    # form now, not rows in a table.
    for sel in (".pdp-errhead", ".pdp-error.warn", ".pdp-errfield",
                ".pdp-afield", ".pdp-attr.pdp-hit"):
        assert sel in css, sel
    # Every colour it uses must be a defined token, not a literal.
    for tok in ("--pdp-danger:", "--pdp-warn:", "--pdp-dangerbg:", "--pdp-edge:"):
        assert tok in css, tok


def test_warnings_are_folded_when_there_are_errors():
    """'Accepted with warnings' is a success. A wall of amber over a listing
    that went live is noise, so warnings collapse behind a summary."""
    js = code(_read("static", "js", "pdp.js"))
    fn = js[js.index("function pdpApiIssues"):js.index("function pdpGoToField")]
    assert "pdp-errwarns" in fn and "details" in fn
    assert 'errs.length ? "" : " open"' in fn, \
        "with no errors above them, the warnings should be open"


# ---- it survives a Sync, and it shows on the listings page ----------------

def test_the_refusal_becomes_a_warning():
    """So it appears wherever warnings already do -- the card badge, the
    detailed row's chip, the product page's hero -- without any of those three
    learning about a new field."""
    src = _read("listing", "warnings.py")
    assert "def amazon_refused(row):" in src
    assert "_refused," in src, "it must be in the list every active row is checked against"
    assert '"amazon_refused", "high"' in src, "a refusal is not a low warning"


def test_only_errors_raise_it():
    """'Accepted with warnings' is a success. A mark on a listing Amazon took
    would make the mark meaningless."""
    from listing import warnings as W
    from listing import api_issues as AI
    warn_only = AI.pack([{"code": "1", "severity": "WARNING", "message": "m"}])
    assert W.amazon_refused({"api_issues_json": warn_only}) is None
    err = AI.pack([{"code": "1", "severity": "ERROR", "message": "m",
                    "attributeNames": ["item_name"]}])
    got = W.amazon_refused({"api_issues_json": err})
    assert got and got["severity"] == "high"
    assert "item_name" in got["message"], "it must say WHICH field"
    assert got["details"]["fields"] == ["item_name"]


def test_a_row_outside_the_active_statuses_is_still_checked():
    """THE WHOLE POINT. ACTIVE_STATUSES is QUEUED/GENERATED/SUBMITTED/LIVE, and
    a refused listing is in API_ERROR -- the reported one had been moved on to
    APPROVED. Both sit outside that set, so the only two statuses that can carry
    a refusal were the two that could never show one."""
    from listing import warnings as W
    from listing import api_issues as AI
    assert "API_ERROR" not in W.ACTIVE_STATUSES
    assert "APPROVED" not in W.ACTIVE_STATUSES
    err = AI.pack([{"code": "1", "severity": "ERROR", "message": "no good",
                    "attributeNames": ["brand"]}])
    rows = [{"sku": "A", "status": "APPROVED", "api_issues_json": err},
            {"sku": "B", "status": "API_ERROR", "api_issues_json": err},
            {"sku": "C", "status": "APPROVED"}]
    out = W.for_rows(rows)
    assert [w["type"] for w in out.get("A", [])] == ["amazon_refused"]
    assert [w["type"] for w in out.get("B", [])] == ["amazon_refused"]
    assert "C" not in out, "a row with nothing to say is left alone, not blanked"


def test_a_fixed_refusal_is_cleared_not_stranded():
    """A row that HAD one and no longer does must be written back empty --
    otherwise a fixed listing keeps a red mark forever."""
    from listing import warnings as W
    rows = [{"sku": "A", "status": "APPROVED",
             "warnings": json.dumps([{"type": "amazon_refused", "severity": "high",
                                      "message": "old"}])}]
    out = W.for_rows(rows)
    assert out.get("A") == [], out


def test_sync_cannot_erase_it():
    """The reply lives in its own column, not in the status.

        "After a Sync the error disappeared and the status changed to APPROVED."

    upsert_row writes only the columns it is given and api_issues_json is not in
    the generator's blank-row template, so a re-generation cannot blank it
    either. Only a fresh Preview or Submit writes it."""
    gen = _read("amazon_listing_generator.py")
    assert "API Issues JSON" in gen
    # The only writer: the column is looked up once, guarded once, written once.
    assert gen.count("issues_col") == 3, gen.count("issues_col")
    assert 'queue(i, issues_col, _api_issues.pack(' in gen
    store = _read("data", "store.py")
    assert "cols = [c for c in data if c in COL_TO_HEADER" in store, \
        "upsert must write only the columns it was handed"


# ---- the driver -----------------------------------------------------------
# run_tests.py executes this file with the interpreter, not pytest (there is no
# pytest here), so the functions above have to be called and the exit code has
# to mean something.

if __name__ == "__main__":
    _fails = []
    for _name, _fn in sorted(list(globals().items())):
        if not _name.startswith("test_") or not callable(_fn):
            continue
        try:
            _fn()
            print("  ok    %s" % _name)
        except Exception as _e:
            _fails.append("%s: %s" % (_name, _e))
            print("  FAIL  %s -- %s" % (_name, _e))
    print("\nFAILURES: %d" % len(_fails))
    for _f in _fails:
        print("  - " + _f)
    raise SystemExit(1 if _fails else 0)
