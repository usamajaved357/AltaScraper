"""listing/product_type.py -- every listing knows what Amazon calls it.

THE PROBLEM, IN THE OWNER'S WORDS:

    "but why are we having products with no product type, the app should be
     able to pull the product type of the items, dont skip compliance checks"

MEASURED, on his own database: 32 of 303 listings have no product_type. All 32
are on jack_uk; 30 are GENERATED, one is a variation PARENT and one is QUEUED.
Their SKUs carry eBay item ids (336475288886) where an ASIN would be, so there
was never an ASIN to read a type from, and the paths that made them -- the
variation children, the parent row, the Miles rows -- did not infer one either.

WHY A BLANK IS NOT HARMLESS. The compliance gate reads product_type to decide
whether a category can apply to this product at all. With no type it cannot
decide, and the choice is between flagging things that are not electrical and
missing things that are. Two of those 32 are "12V 10A AC to DC Adapter 120W
Power Supply" and "100W Rechargeable LED Work Light" -- both genuinely
electrical, both with an electrical flag resting on a field that is empty.

The answer is not to change how the gate treats a blank. It is to stop having
blanks.

WHERE THE ANSWER COMES FROM, BEST FIRST

  1. what the row already says          -- never overwritten
  2. Amazon, for a listing that is live -- its own answer, not ours
  3. the title                          -- infer_product_type, one shared rule
                                           set (CLAUDE.md Rule 12)

AND "HOME" IS NOT AN ANSWER. infer_product_type falls back to "HOME" so that a
submit always has a real type to send. Writing that onto a row is a different
act: the gate would then read "HOME" as a FACT about the product, and for the
12V power supply above that would turn its electrical check off -- the exact
failure this module exists to prevent. So nothing is stored unless a rule
actually matched, and a row we cannot type stays blank.
"""
import json


def from_title(title, comp_data=None):
    """The type the title implies, or "" if nothing matched.

    Deliberately thin: the rules live in amazon_listing_generator's
    _PT_INFER_RULES, which is also what the generator uses when it creates a
    listing, so a type inferred here and a type inferred there cannot differ.
    """
    try:
        from amazon_listing_generator import infer_product_type
    except Exception:
        return ""
    return infer_product_type(dict(comp_data or {}), item_name=str(title or ""),
                              default="") or ""


def from_amazon(config_path, account, marketplace, sku):
    """What Amazon itself calls this SKU. "" when it cannot say.

    Only useful for a listing that is actually on Amazon. Goes through
    api/amazon_listings, which is the one place that knows how to fetch a live
    listing -- including productTypes in includedData, without which
    product_type comes back empty for every live listing (Rule 12).
    """
    try:
        import accounts as _acc
        from api import amazon_listings as _al
    except Exception:
        return ""
    try:
        got = _al.get_item(_acc.account_creds(account), marketplace,
                           str(account.get("seller_id") or ""), sku,
                           _acc.marketplace_id(marketplace) or "")
    except Exception:
        return ""
    if not isinstance(got, dict) or got.get("status") != getattr(_al, "OK", "ok"):
        return ""
    return str(got.get("product_type") or "").strip()


def resolve(row, comp_data=None):
    """The product type for one row, without asking Amazon. "" if unknown."""
    have = str((row or {}).get("product_type") or "").strip()
    if have:
        return have
    # The attributes the generator stored are a better haystack than the title
    # alone -- item_type_keyword and the browse nodes are in there.
    cd = dict(comp_data or {})
    if not cd:
        try:
            cd = json.loads(str((row or {}).get("attributes_json") or "") or "{}")
            if not isinstance(cd, dict):
                cd = {}
            cd = {"attributes": cd}
        except Exception:
            cd = {}
    return from_title((row or {}).get("title") or "", cd)


def backfill(config_path, workspace_id):
    """Fill in the blanks for one workspace. Returns (blank_before, filled).

    NOTHING WITH A TYPE IS TOUCHED, and nothing is invented: a row whose title
    matches no rule is left blank, because a wrong type is worse than none --
    it is the difference between "we do not know" and a false statement the
    compliance gate will act on.

    Safe to run on every recompute; a row it cannot type simply stays blank and
    is tried again next time, which is what should happen after a Sync brings
    Amazon's own answer in.
    """
    from data import db as _db

    conn = _db.get_db(config_path)
    rows = [dict(r) for r in conn.execute(
        "SELECT sku, title, product_type, attributes_json FROM listings "
        "WHERE workspace_id=? AND COALESCE(product_type,'')=''", (workspace_id,))]
    if not rows:
        return 0, 0

    filled = 0
    for r in rows:
        pt = resolve(r)
        if not pt:
            continue
        conn.execute(
            "UPDATE listings SET product_type=? WHERE workspace_id=? AND sku=?",
            (pt, workspace_id, r.get("sku")))
        filled += 1
    if filled:
        conn.commit()
    return len(rows), filled


# ---- correcting drafts from Amazon's catalogue ---------------------------------
#
#     "why am i seeing that error on almost all of my listings"
#     "fix the product types from amazon"
#
# From 29 Aug 2026 every queued draft generated without its competitor ASIN, so
# its type was guessed from the title -- and HOME is what the guess says for
# almost anything (see amazon_listing_generator.process_row). Amazon then
# re-typed them at Preview: "updated from HOME to TABLE".
#
# THE ANSWER IS THE COMPETITOR ASIN'S TYPE, which is what the generator would
# have used had it been handed the ASIN. Nothing is written here: compare()
# says what WOULD change, and the owner applies it through the listing's own
# save path, so there is still exactly one thing that writes a field.

# A listing Amazon already holds is not a draft, and its type is Amazon's own
# business now. The same "on Amazon" set the barcode clash check uses (Rule 12);
# a variation PARENT and a not-yet-generated QUEUED row are not drafts either.
from domain.barcode_clash import _LIVE as _ON_AMAZON


# ---- which listings the button looks at, and why the others were left out ----
#
#     "i selected 64 listings and clicked on fix product types it shows check 2
#      unsent draft(s) against their competitor asin in amazon's catalog, - to
#      change, 2 already right 0 couldn't check"
#     "no more than 30 drafts have competitor asins in them and even if it is
#      looking at all the drafts this count is wrong and i still have that
#      warning message where amazon shows error of product type in many of the
#      items"
#
# FOUR THINGS were wrong with how the list was drawn up, and all four were silent:
#   * a draft with no competitor ASIN was dropped. There was nothing to look up,
#     which is true -- but Amazon's product-type SEARCH can say what a product
#     is from its title, and the box on the listing already uses it;
#   * a SUBMITTED listing was dropped. Right by default, never explained, and
#     impossible to override -- yet "your product type has been updated" is the
#     note Amazon attaches when it ACCEPTS a listing;
#   * the listings the owner had ticked were ignored: the whole account was read;
#   * the dialog reported only what it HAD checked, so everything left out read
#     as nothing at all.
#
# candidates() draws up the list once, and says for every listing it leaves out
# why it was left out. drafts_to_check() keeps its old meaning exactly --
# competitor-ASIN drafts only, nothing submitted -- for anything relying on it.

BY_ASIN = "asin"     # look the competitor ASIN up in Amazon's catalogue
BY_TITLE = "title"   # no ASIN: ask Amazon's product-type search about the title

SKIP_ON_AMAZON = "on_amazon"      # LIVE / ACTIVE -- its type is Amazon's now
SKIP_SUBMITTED = "submitted"      # sent to Amazon; included only on request
SKIP_PARENT = "parent"            # a variation parent is not a product
SKIP_QUEUED = "queued"            # not generated yet
SKIP_NOTHING = "nothing_to_ask"   # no competitor ASIN and no title either
SKIP_NOT_FOUND = "not_found"      # ticked, but not a draft in this account


def candidates(config_path, workspace_id, skus=None, include_submitted=False):
    """The listings Fix product types will ask Amazon about, and the rest.

    -> {"check":   [{"sku", "title", "asin", "product_type", "status",
                     "marketplace", "method"}],
        "skipped": [{"sku", "title", "status", "reason"}]}

    `skus` narrows it to the listings the owner ticked; None means the account.
    A ticked SKU this account holds no draft for is reported, not ignored.
    """
    from data import db as _db
    import re as _re
    out = {"check": [], "skipped": []}
    try:
        conn = _db.get_db(config_path)
        rows = [dict(r) for r in conn.execute(
            "SELECT sku, title, competitor_asin, product_type, status, "
            "listing_marketplace FROM listings WHERE workspace_id=?",
            (workspace_id,))]
    except Exception:
        return out

    if skus:
        wanted = [str(s).strip() for s in skus if str(s or "").strip()]
        held = {str(r.get("sku") or "").strip() for r in rows}
        for s in wanted:
            if s not in held:
                out["skipped"].append({"sku": s, "title": "", "status": "",
                                       "reason": SKIP_NOT_FOUND})
        keep = set(wanted)
        rows = [r for r in rows if str(r.get("sku") or "").strip() in keep]

    # The "on Amazon" set is barcode_clash's (Rule 12). SUBMITTED is split out of
    # it because it is the one that may be included on purpose.
    on_amazon = set(_ON_AMAZON) - {"SUBMITTED"}
    for r in rows:
        sku = str(r.get("sku") or "")
        title = str(r.get("title") or "").strip()
        status = str(r.get("status") or "").strip().upper()
        base = {"sku": sku, "title": title, "status": status}
        if status in on_amazon:
            out["skipped"].append(dict(base, reason=SKIP_ON_AMAZON))
            continue
        if status == "SUBMITTED" and not include_submitted:
            out["skipped"].append(dict(base, reason=SKIP_SUBMITTED))
            continue
        if status == "PARENT":
            out["skipped"].append(dict(base, reason=SKIP_PARENT))
            continue
        if status == "QUEUED":
            out["skipped"].append(dict(base, reason=SKIP_QUEUED))
            continue
        asin = str(r.get("competitor_asin") or "").strip().upper()
        if _re.fullmatch(r"[A-Z0-9]{10}", asin):
            method = BY_ASIN
        elif title:
            method, asin = BY_TITLE, ""
        else:
            out["skipped"].append(dict(base, reason=SKIP_NOTHING))
            continue
        out["check"].append({
            "sku": sku, "title": title, "asin": asin,
            "product_type": str(r.get("product_type") or "").strip(),
            "status": status,
            "marketplace": str(r.get("listing_marketplace") or "").strip().upper(),
            "method": method})
    return out


def drafts_to_check(config_path, workspace_id):
    """The drafts in one workspace that have a competitor ASIN to ask about.

    -> [{"sku", "title", "asin", "product_type", "status", "marketplace", "method"}]

    Unchanged in meaning: competitor-ASIN drafts only, and nothing already on
    Amazon or submitted. The wider list, with its reasons, is candidates().
    """
    return [d for d in candidates(config_path, workspace_id)["check"]
            if d["method"] == BY_ASIN]


def answer_key(draft):
    """Where compare() finds the answer for one draft.

    By ASIN for a catalogue lookup -- two drafts from one competitor share the
    answer. By SKU for a title search, because two titles are two questions.
    """
    d = draft or {}
    if d.get("method") == BY_TITLE:
        return "title:" + str(d.get("sku") or "")
    return d.get("asin")


def compare(drafts, answers):
    """What Amazon's answers would change. Pure: no database, no network.

    `answers` is {answer_key(draft): result}, where a result is
    api.amazon_catalog.product_type_of(...) for a catalogue lookup, or the same
    shape plus "options" (every type Amazon's search offered) for a title.

    -> [{"sku", "title", "asin", "current", "amazon", "verdict", "why",
         "method", "options"}]
       verdict: "change"      Amazon's type differs -- the one to apply
                "same"        already right
                "not_checked" Amazon could not answer; nothing is changed
    """
    out = []
    for d in drafts or []:
        ans = (answers or {}).get(answer_key(d)) or {}
        amazon = str(ans.get("product_type") or "").strip().upper()
        current = str(d.get("product_type") or "").strip().upper()
        if ans.get("status") != "ok" or not amazon:
            verdict, why = "not_checked", (ans.get("error") or "not asked")
        elif amazon == current:
            verdict, why = "same", ""
        else:
            verdict, why = "change", ""
        options = [str(o).strip().upper() for o in (ans.get("options") or [])
                   if str(o or "").strip()]
        out.append({"sku": d.get("sku"), "title": d.get("title"),
                    "asin": d.get("asin"), "current": current,
                    "amazon": amazon, "verdict": verdict, "why": why,
                    "method": d.get("method") or BY_ASIN, "options": options})
    return out


def still_blank(config_path, workspace_id):
    """The SKUs that even the title could not type, so a screen can say so
    rather than leaving the field quietly empty."""
    from data import db as _db
    try:
        conn = _db.get_db(config_path)
        return [r[0] for r in conn.execute(
            "SELECT sku FROM listings WHERE workspace_id=? "
            "AND COALESCE(product_type,'')=''", (workspace_id,))]
    except Exception:
        return []
