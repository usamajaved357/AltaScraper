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
