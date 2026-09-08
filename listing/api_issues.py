"""listing/api_issues.py -- what Amazon said back about a listing.

ONE SHAPE FOR AMAZON'S REPLY (CLAUDE.md Rule 12).

putListingsItem answers every Preview and every Submit with an `issues` array.
Each entry carries four things worth keeping:

    code            e.g. "4000001"   -- Amazon's own identifier for the rule
    severity        ERROR | WARNING | INFO
    message         the sentence shown to a human
    attributeNames  which field(s) the rule blames, e.g. ["item_dimensions"]

Until now only the sentences survived: they were joined with "; " into the
Notes column ("API SUBMIT REJECTED by Amazon (3 error(s)): ..."). That tells
the owner WHAT Amazon objected to but never WHERE, so a rejected listing had
to be read line by line to find the field. attributeNames is the part that
lets the listing page put the complaint next to the box that caused it.

WHY A MODULE AND NOT A FEW LINES IN THE GENERATOR
Three places need the same shape: the generator writes it, dashboard._card
reads it out to the browser, and the tests check it. Parsing JSON that may be
empty, may be a bare list, may be an object, or may be old prose is exactly the
kind of thing that grows three slightly different versions if it is inlined.

NOTHING HERE TALKS TO AMAZON OR TO THE DATABASE. It converts between Amazon's
reply and the string kept in the `api_issues_json` column, and back.
"""
import json
import time

# What the column holds. Bumped only if the stored shape ever changes, so a
# reader can tell a new record from one written by an older build.
VERSION = 1

_SEVERITIES = ("ERROR", "WARNING", "INFO")


def _one(issue):
    """One of Amazon's issues, reduced to the four fields we keep.

    Defensive about the shape: sp-api hands back plain dicts, but a cached or
    replayed response can hold objects, and a missing key must not raise in the
    middle of a submit run.
    """
    if not isinstance(issue, dict):
        return None
    sev = str(issue.get("severity", "") or "").strip().upper()
    if sev not in _SEVERITIES:
        sev = "ERROR" if sev else "WARNING"
    # "attributeNames" is Amazon's spelling on the way IN; "fields" is ours on
    # the way back OUT of the column. Both are read here because _one runs on
    # both journeys -- reading only Amazon's spelling silently emptied the field
    # list every time a stored record was parsed back, which is the one thing
    # this module exists to preserve.
    names = (issue.get("attributeNames") or issue.get("attribute_names")
             or issue.get("fields") or [])
    if isinstance(names, str):
        names = [names]
    out = {
        "code":     str(issue.get("code", "") or "").strip(),
        "severity": sev,
        "message":  str(issue.get("message", "") or "").strip(),
        "fields":   [str(n).strip() for n in names if str(n).strip()],
    }
    if not out["message"] and not out["code"]:
        return None
    return out


def pack(issues, *, mode="", status=""):
    """Amazon's issues array -> the string stored in api_issues_json.

    `mode` is "preview" or "submit" -- the same error means different things in
    the two ("we did not send it" vs "Amazon refused it"). `status` is
    Amazon's own ACCEPTED / INVALID verdict on a submit.

    Returns "" for an empty or unusable array, which is what clears the column:
    a listing that previews clean must not keep yesterday's complaint.
    """
    kept = [x for x in (_one(i) for i in (issues or [])) if x]
    if not kept:
        return ""
    return json.dumps({
        "v":       VERSION,
        "at":      time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode":    str(mode or ""),
        "status":  str(status or "").upper(),
        "issues":  kept,
    }, ensure_ascii=False)


def parse(raw):
    """The stored string -> {"at","mode","status","issues":[...]}.

    Never raises. Anything unreadable -- blank, old prose, truncated JSON --
    comes back as an empty record, because a listing screen must still draw
    when the column holds something unexpected.
    """
    empty = {"at": "", "mode": "", "status": "", "issues": []}
    if not raw:
        return empty
    if isinstance(raw, dict):
        doc = raw
    else:
        try:
            doc = json.loads(str(raw))
        except Exception:
            return empty
    if isinstance(doc, list):          # a bare issues array, written by hand
        doc = {"issues": doc}
    if not isinstance(doc, dict):
        return empty
    kept = [x for x in (_one(i) for i in (doc.get("issues") or [])) if x]
    return {
        "at":     str(doc.get("at", "") or ""),
        "mode":   str(doc.get("mode", "") or ""),
        "status": str(doc.get("status", "") or ""),
        "issues": kept,
    }


def errors(rec):
    """Only the blocking ones. Takes either the stored string or a parsed record."""
    if not isinstance(rec, dict) or "issues" not in rec:
        rec = parse(rec)
    return [i for i in rec["issues"] if i["severity"] == "ERROR"]


# Amazon's code for "the data you sent matches an existing ASIN, and disagrees
# with it". It is NOT a complaint about any one value being wrong.
CATALOGUE_MATCH_CODES = {"8541"}

# An ASIN, for NAMING the products in the explanation only. The decision is made
# on the CODE, never on the prose (CLAUDE.md Rule 4).
_ASIN_RE = None


def catalogue_conflict(rec):
    """Is Amazon refusing because our data MATCHES another product? -> dict|None.

    -> {"code", "fields", "asins", "message"} or None.

    WHY THIS IS NOT AN ORDINARY REJECTED FIELD, and why auto-fix must stop.

        "a color is not something amazon should stuck on"

    Right, and it was not really stuck on the colour. On 11.96_2Days_B0FM82BDC5
    Amazon answered:

        "We found more than one ASIN matching the SKU data provided. The
         '{color.value,color.standardized_values}' conflicts with 1 ASINs in the
         catalogue (Merchant Green / Amazon Blue) for B0HJ3W6M84..."

    Amazon names `color` because that is where our data DISAGREES with an ASIN it
    thinks we are describing -- not because the colour is invalid. Auto-fix read
    it as an ordinary flagged field, asked for a value, was given "Green" (which
    it already was), applied it, previewed, got the identical answer, and
    declared itself stuck. Two rounds spent on a field that was never wrong.

    AND THE "FIX" WOULD HAVE BEEN THE WORST OUTCOME. The only value that
    satisfies the complaint is Amazon's -- Blue. Setting it would make our
    product match somebody else's ASIN, which is precisely the piggyback listing
    CLAUDE.md Rule 1 exists to prevent. So this is not a field to try harder at;
    it is a stop.

    Decided on the CODE. The ASINs are pulled out for the sentence only, with a
    strict pattern, and nothing branches on them.
    """
    global _ASIN_RE
    if not isinstance(rec, dict) or "issues" not in rec:
        rec = parse(rec)
    for raw in rec.get("issues") or []:
        # THROUGH _one, LIKE EVERY OTHER READER HERE. Amazon spells it
        # attributeNames on the way in and this column spells it fields on the
        # way back out, and _one is the one place that knows both. Reading
        # i["fields"] directly worked on a stored record and came back empty on
        # a reply straight from Amazon -- the same silent-empty-field-list bug
        # this module's own note about _one describes.
        i = _one(raw)
        if not i:
            continue
        if str(i.get("code") or "").strip() not in CATALOGUE_MATCH_CODES:
            continue
        if _ASIN_RE is None:
            import re
            _ASIN_RE = re.compile(r"\bB0[A-Z0-9]{8}\b")
        msg = str(i.get("message") or "")
        asins = []
        for a in _ASIN_RE.findall(msg):
            if a not in asins:
                asins.append(a)
        return {"code": str(i.get("code") or ""),
                "fields": list(i.get("fields") or []),
                "asins": asins,
                "message": msg}
    return None


def catalogue_conflict_note(cc):
    """The sentence to show when catalogue_conflict() fires. Plain English.

    It says three things, because all three were missing from the log the owner
    read: that the field named is not the fault, what Amazon has actually done,
    and what the two ways out are. Neither of them is "let the app pick a
    value" -- the app changing our product to match somebody else's ASIN is the
    one outcome that must never happen by itself (CLAUDE.md Rule 1).
    """
    if not cc:
        return ""
    fields = [f for f in (cc.get("fields") or []) if f]
    asins = cc.get("asins") or []
    out = ("Stopped: the barcode on this listing already belongs to a product "
           "in Amazon's catalogue"
           + (" (%s)" % ", ".join(asins[:3]) if asins else "")
           + ". Amazon matched the two on that barcode and then refused because "
             "the rest of the details disagree")
    if fields:
        out += " (" + ", ".join(fields[:4]) + ")"
    out += (".\n\nTHE FIELD AMAZON NAMES IS NOT THE FAULT. Matching is done on "
            "the product identifier -- Amazon's own words: error 8541 \"occurs "
            "when your Product ID, such as UPC, EAN, JAN, and ISBN, corresponds "
            "to the Product ID of an existing ASIN\". The colour or title it "
            "then complains about is what disagrees AFTER the match, not what "
            "caused it. Changing them cannot clear it.\n\n"
            "Check the barcode first: if it is on the wrong product, replace it "
            "with one that belongs to this one. Auto-fix will not adjust the "
            "other fields to match, because the only values that satisfy the "
            "complaint are the other product's, and adopting them would attach "
            "this listing to somebody else's ASIN (CLAUDE.md Rule 1).")
    return out


def stale_identifiers(issues, current_barcode):
    """Barcodes Amazon is still complaining about that this listing no longer uses.

    WHY THIS EXISTS.

        "i changed the ean before submitting, i am confused here"

    Amazon leaves the errors from a FAILED submission attached to the SKU. A
    later, successful submission does not clear them. So getListingsItem keeps
    answering with a complaint about a barcode that was replaced -- and the app
    repeated it word for word as though it described the submission just made.
    Measured on 9.99_2Days_B0BP1HNW8G: Amazon stored ean 4545156646383 and went
    DISCOVERABLE as B0HJ2W3XZ1, while still returning issue 100980 about
    04545844574868.

    Amazon hands us the offending value in attributeNames, beside the field name
    -- so the comparison needs nothing extra fetched and no Amazon call.

    THE VALUE COMES FROM THE STRUCTURED FIELD, NEVER FROM THE MESSAGE TEXT
    (CLAUDE.md Rule 4). Reading a code out of Amazon's prose is how the "The"/
    "Your" phantom-field bug happened.

    Both sides go through normalize_gtin, so the 14-digit form Amazon quotes back
    (04545844574868) is recognised as the EAN-13 the box holds (4545844574868)
    and is NOT reported as stale. Without that, replacing nothing would look like
    replacing something.

    -> [the codes named, as Amazon wrote them]. Empty when the listing has no
    usable barcode of its own, because then there is nothing to compare against
    and "stale" would be a guess.
    """
    from listing.barcode import normalize_gtin      # single source (Rule 12)

    now, _t = normalize_gtin(current_barcode)
    if not now:
        return []
    out = []
    for raw in (issues or []):
        one = _one(raw)
        if not one:
            continue
        for f in one["fields"]:
            digits = "".join(c for c in str(f) if c.isdigit())
            # A field NAME is snake_case; a barcode is nothing but digits of a
            # GTIN length. Anything else in attributeNames is a real field.
            if digits != str(f).strip() or len(digits) not in (8, 12, 13, 14):
                continue
            was, _t2 = normalize_gtin(f)
            if was and was != now and f not in out:
                out.append(f)
    return out


def by_field(rec):
    """{field name: [issue, ...]} for every issue that names a field.

    An issue can blame more than one field and appears under each. Issues that
    name none are not in here at all -- they belong at the top of the page, not
    against a box.
    """
    if not isinstance(rec, dict) or "issues" not in rec:
        rec = parse(rec)
    out = {}
    for i in rec["issues"]:
        for f in i["fields"]:
            out.setdefault(f, []).append(i)
    return out
