"""domain/compliance_scan.py -- scan a LIVE listing and score it.

    Orbit's Compliance checker: pick an ASIN, get a score out of 100, a status
    (Compliant / Minor / Major / Critical) and a list of warnings, kept as scans
    you can come back to.

WHAT IS NEW HERE AND WHAT IS NOT.

The checks are NOT new. listing/compliance.py already holds all of them --
forbidden brand names, restricted phrasing, category claims, regulated claims,
IP violations -- and they are good, because they were each written after a real
listing was refused or taken down. What they have never done is run against a
listing that is ALREADY LIVE.

They run at generation time, on copy this app is about to submit. So a listing
written before a rule existed, or edited in Seller Central afterwards, or
inherited from a supplier, has never been looked at by any of them. That is
precisely the listing most likely to be carrying something, and it is what this
module is for. Not one check is reimplemented (CLAUDE.md Rule 12); this decides
what to feed them, how to weigh what comes back, and what to store.

THE SCORE IS A SUMMARY, NEVER THE ANSWER.

A number out of 100 is what makes a list of forty ASINs sortable, and that is
its whole job. Every point deducted is traceable to a named finding, and the
findings are what a person acts on. A score with no findings behind it would be
an opinion with a decimal point.

    CRITICAL   something that gets a listing taken down: another company's brand
               name, a medical or disease claim.
    MAJOR      something Amazon's filters act on: restricted phrasing, an
               unsupported certification claim.
    MINOR      something that weakens the listing or invites a challenge.

A CATEGORY WITH NO RULE IS NOT A PASS.

If the product type does not match a known lane, listing/compliance screens it
against EVERY lane, which is the strict reading and the right one. But this
module also says so out loud, because "we found nothing" and "we did not know
what to look for" are different sentences and only one of them is reassuring.

NOTHING IS AUTO-FIXED. This reads and reports. Changing live listing copy is a
submission to Amazon and belongs behind a person's decision, not behind a scan.
"""
import datetime
import threading

from domain import jsonstore

_LOCK = threading.Lock()
_FILE = "compliance_scans.json"

MAX_SCANS = 300

CRITICAL = "critical"
MAJOR = "major"
MINOR = "minor"

# What each finding costs. Deliberately steep at the top: one competitor brand
# name in a title is not "a few points off", it is the listing gone.
WEIGHT = {CRITICAL: 34, MAJOR: 12, MINOR: 4}

# Where the status boundaries sit. Named rather than buried in comparisons, so
# the four words on the screen mean something checkable.
BANDS = [(90, "Compliant"), (70, "Minor issues"), (40, "Major issues"),
         (0, "Critical")]


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _path(config_path):
    return jsonstore.path_beside_config(config_path, _FILE)


def load(config_path):
    d = jsonstore.read_json(_path(config_path), None)
    if not isinstance(d, dict) or not isinstance(d.get("scans"), list):
        return {"scans": []}
    return d


def _save(config_path, data):
    return jsonstore.write_json_atomic(_path(config_path), data, indent=2)


def listing_from(record):
    """Turn a catalogue/snapshot record into the shape the checks expect.

    listing/compliance reads title / bullet_1..5 / description / item_highlights,
    because that is the shape this app builds when it GENERATES a listing. A live
    listing read back from Amazon has the same content under different names, so
    this is the adapter -- and it lives here rather than in the checks, so the
    checks keep one input shape (Rule 12).
    """
    r = record or {}
    attrs = r.get("attributes") or {}

    def attr(name):
        v = attrs.get(name)
        if isinstance(v, list):
            v = " | ".join(str(x) for x in v if x)
        return str(v or "")

    bullets = []
    bp = attrs.get("bullet_point")
    if isinstance(bp, list):
        bullets = [str(x) for x in bp if x]
    elif bp:
        # The catalogue joins repeated attributes with " | " -- split it back so
        # a finding can name WHICH bullet, which is the difference between a
        # report somebody can act on and one they have to search.
        bullets = [b.strip() for b in str(bp).split("|") if b.strip()]

    out = {
        "title": str(r.get("title") or attr("item_name") or ""),
        "description": str(r.get("description") or attr("product_description") or ""),
        "item_highlights": attr("item_type_keyword"),
    }
    for i in range(1, 6):
        out["bullet_%d" % i] = bullets[i - 1] if len(bullets) >= i else ""
    return out


def _finding(sev, kind, what, where, why, fix=""):
    return {"severity": sev, "kind": kind, "what": what, "where": where,
            "why": why, "fix": fix}


def scan(listing, brand="", product_type="", ip_rules=None, source_text=""):
    """Run every check and collect the findings.

    `source_text` is the supplier documentation a claim can be grounded IN.
    Where there is none, the grounding checks are SKIPPED rather than run
    against nothing -- a check with no evidence to compare against would flag
    every specification on the listing, and forty false findings is the same as
    none.
    """
    from listing import compliance as C

    findings = []
    notes = []

    # --- another company's brand name: the one that gets a listing removed ---
    try:
        r = C.check_forbidden_brands(listing) or {}
        for h in (r.get("hits") or []):
            findings.append(_finding(
                CRITICAL, "forbidden-brand", h.get("term", ""), h.get("field", ""),
                "Another company's brand or part code in your copy. This is the "
                "single most common reason a listing is taken down.",
                "Remove the name, or replace it with a description of what the "
                "part fits without naming the maker."))
    except Exception as e:
        notes.append("brand check failed: %s" % str(e)[:110])

    # --- IP: comparative phrasing and unrecognised capitalised words ---------
    if ip_rules:
        try:
            r = C.check_ip_violations(listing, brand, ip_rules) or {}
            # THE KEYS THIS READS MUST BE THE KEYS THE CHECK RETURNS. It used to
            # look for "hits"/"phrases"/"unrecognised"/"caps", none of which
            # check_ip_violations has ever produced -- so the IP section of this
            # scan silently reported nothing, on every listing, always.
            for h in (r.get("phrase_evidence") or []):
                findings.append(_finding(
                    MAJOR, "ip-phrase", str(h), "",
                    "A comparative phrase pointed at a brand name. Amazon treats "
                    "these as trading on another brand.",
                    "Say what the product is, not whose product it is like."))
            for h in (r.get("phrase_note_only") or []):
                findings.append(_finding(
                    MINOR, "ip-phrase-noteonly", str(h), "",
                    "Worth a read, but it names nobody -- \"universal fit\" and "
                    "\"branded\" are claims about your own product, not about "
                    "somebody else's mark.",
                    "Only act on this if the claim is not true of your product."))
            for h in (r.get("phrase_generic") or []):
                # Reported, but honestly: it is not pointed at anyone's brand.
                findings.append(_finding(
                    MINOR, "ip-phrase-generic", str(h), "",
                    "A compatibility phrase pointed at a generic thing, not at a "
                    "brand. Not a trademark problem, but Amazon can still read it "
                    "as a comparison.",
                    "Usually fine. Reword only if the thing it names is a brand."))
            if r.get("caps_over_threshold"):
                for w in (r.get("unknown_caps") or []):
                    findings.append(_finding(
                        MINOR, "unknown-capitalised", str(w), "",
                        "A capitalised word that is not on the safe list. It MAY "
                        "read as a brand name -- this is a guess, not a finding.",
                        "Lower-case it if it is an ordinary word; remove it if it "
                        "is somebody's mark."))
        except Exception as e:
            notes.append("IP check failed: %s" % str(e)[:110])

    # --- restricted phrasing: what Amazon's own filters act on ---------------
    try:
        r = C.check_restricted_phrasing(listing) or {}
        for h in (r.get("hits") or []):
            findings.append(_finding(
                MAJOR, "restricted-phrase", h.get("phrase", ""), h.get("field", ""),
                "Wording Amazon's medical and pesticide filters act on.",
                "Describe what the product physically does instead."))
    except Exception as e:
        notes.append("phrasing check failed: %s" % str(e)[:110])

    # --- category claims: the lane for this product type ---------------------
    try:
        r = C.check_category_claims(listing, product_type) or {}
        # A CATEGORY WITH NO RULE IS NOT A PASS. Said out loud, because "we
        # found nothing" and "we did not know what to look for" are different
        # sentences and only one is reassuring.
        # TWO DIFFERENT GAPS, and both were silent before.
        #
        #   no product type at all  -> screened against EVERY lane, which is the
        #                              strict reading and the right one, but the
        #                              findings may belong to a category this
        #                              product is not in.
        #   an unrecognised type    -> falls back to the GENERAL lane, so the
        #                              specific rules for supplements, skincare,
        #                              cleaning products, medical devices and pet
        #                              products were never applied. A supplement
        #                              whose product type Amazon spells oddly is
        #                              screened as though it were a doormat.
        #
        # Found by testing: an unknown type does not set unknown_category at all,
        # because lane_for_product_type falls back rather than failing. The
        # quieter of the two gaps was the one nothing reported.
        if r.get("unknown_category"):
            notes.append(
                "No product type was available, so this listing was screened "
                "against ALL category lanes. Findings may be from a category "
                "this product is not in.")
        elif str(r.get("lane") or "") == "general" and product_type:
            notes.append(
                "The product type \"%s\" does not match any specific category "
                "lane, so only the GENERAL rules were applied -- the specific "
                "checks for supplements, skincare, cleaning products, medical "
                "devices and pet products were not. If this product is one of "
                "those, this scan has not covered it."
                % str(product_type)[:60])
        for h in (r.get("hits") or []):
            sev = CRITICAL if str(h.get("severity", "")).upper() in ("HIGH", "CRITICAL") else MAJOR
            findings.append(_finding(
                sev, "category-claim", h.get("phrase", ""), h.get("field", ""),
                h.get("rule") or "A claim this product category is regulated for.",
                h.get("swap") or ""))
    except Exception as e:
        notes.append("category check failed: %s" % str(e)[:110])

    # --- claims that need evidence, only where there IS evidence to check ----
    if source_text:
        for fn, kind, sev, why in (
            ("check_unsupported_claims", "unsupported-claim", MAJOR,
             "A standards or approval claim that the product's own "
             "documentation does not support."),
            ("check_regulated_claims", "regulated-claim", MAJOR,
             "A regulated certification claim with no evidence behind it."),
            ("check_numeric_grounding", "invented-figure", MAJOR,
             "A number in the copy that does not appear in the product's own "
             "documentation."),
        ):
            try:
                r = getattr(C, fn)(listing, source_text) or {}
                for key in ("ungrounded", "fabricated", "hits"):
                    for h in (r.get(key) or []):
                        term = (h.get("claim") or h.get("token") or h.get("phrase")
                                or str(h)) if isinstance(h, dict) else str(h)
                        findings.append(_finding(
                            sev, kind, term, (h.get("field", "")
                                              if isinstance(h, dict) else ""),
                            why, "Remove it, or add the document that proves it."))
            except Exception as e:
                notes.append("%s failed: %s" % (fn, str(e)[:90]))
    else:
        notes.append(
            "No supplier documentation was available, so claims that would need "
            "evidence (certifications, standards, specific figures) were NOT "
            "checked. This is a gap in the scan, not a clean result.")

    return {"findings": findings, "notes": notes}


def score(findings):
    """0-100 and a status word.

    Floored at zero rather than going negative: "-40 out of 100" is not a score,
    and a listing with eight critical findings and one with three are both
    simply as bad as this scale goes.
    """
    lost = sum(WEIGHT.get(f.get("severity"), 0) for f in (findings or []))
    n = max(0, 100 - lost)
    status = BANDS[-1][1]
    for floor, name in BANDS:
        if n >= floor:
            status = name
            break
    return n, status


def build(asin, listing, brand="", product_type="", ip_rules=None,
          source_text="", title="", marketplace=""):
    """One complete scan result, ready to store or draw."""
    res = scan(listing, brand, product_type, ip_rules, source_text)
    n, status = score(res["findings"])
    counts = {CRITICAL: 0, MAJOR: 0, MINOR: 0}
    for f in res["findings"]:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    return {
        "asin": str(asin or "").upper(),
        "title": title or listing.get("title", ""),
        "marketplace": str(marketplace or "").upper(),
        "product_type": product_type or "",
        "at": _now(),
        "score": n, "status": status,
        "counts": counts,
        "findings": sorted(res["findings"],
                           key=lambda f: {CRITICAL: 0, MAJOR: 1, MINOR: 2}
                           .get(f["severity"], 3)),
        # Carried, never dropped: a scan that could not check something has to
        # say so on the screen, or its score reads as more thorough than it is.
        "notes": res["notes"],
    }


def store(config_path, workspace_id, result):
    with _LOCK:
        data = load(config_path)
        row = dict(result)
        row["account"] = str(workspace_id or "")
        data.setdefault("scans", []).append(row)
        if len(data["scans"]) > MAX_SCANS:
            del data["scans"][:len(data["scans"]) - MAX_SCANS]
        _save(config_path, data)
    return result


def scans(config_path, workspace_id="", asin="", limit=100):
    out = [s for s in load(config_path).get("scans", [])
           if (not workspace_id or s.get("account") == workspace_id)
           and (not asin or s.get("asin") == str(asin).upper())]
    out.sort(key=lambda s: s.get("at", ""), reverse=True)
    return out[:limit] if limit else out
