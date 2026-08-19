"""domain/generate_plan.py -- what a generate run WOULD do, before it does it.

    "check and let me know if the current workflow of listing generation works
     while preventing the already created listing copies to be created again"

The generate run decides, per queued product, whether it has already been made.
Getting that wrong costs money twice -- the AI spend, and a second copy of a live
listing -- and until now the only way to find out was to press Generate and read
the log as it scrolled.

THIS IS A REPORT ON THE REAL RULE, NOT A SECOND OPINION ABOUT IT. It calls the
generator's own load_existing_skus_and_asins and applies the same condition
process_row applies. If this and a run ever disagreed, one of them would be
wrong and there would be no way to tell which -- so there is one rule and this
reads it.

IT SPENDS NOTHING. No AI call, no Amazon call, no write.

THE RUNNING SET IS MODELLED, and it has to be. The rule is not "is this ASIN in
the output" but "has it been seen YET", and a run ADDS each ASIN as it goes. So
a competitor ASIN appearing twice in the queue is made ONCE -- the first row
takes the work and the second is skipped by it. A report that missed that would
overstate the work and the cost.
"""
import re

ASIN_RE = re.compile(r"\b(B0[A-Z0-9]{8})\b")


def asin_of(row):
    """The competitor ASIN for one queued product.

    competitor_asin FIRST, because data/input_import fills it on import and the
    queue is what the run reads. Taking it from the URL instead would disagree
    with the queue wherever the two differ -- the sort of quiet mismatch that
    makes a working duplicate check look broken.
    """
    a = str((row or {}).get("competitor_asin") or "").strip().upper()
    if re.fullmatch(r"B0[A-Z0-9]{8}", a):
        return a
    for k in ("amazon_url", "Amazon URL", "asin", "ASIN"):
        m = ASIN_RE.search(str((row or {}).get(k) or "").upper())
        if m:
            return m.group(1)
    return ""


def plan(rows, seen_asins, taken_skus=None):
    """What a run over `rows` would do, given what has already been made.

    Returns counts plus the ASINs in each bucket, so a screen can show the list
    rather than only a number -- "27 to generate" is a fact, and the 27 ASINs
    are a thing somebody can check.
    """
    running = set(seen_asins or ())
    already = set(seen_asins or ())
    out = {"generate": [], "skip": [], "repeat": [], "no_asin": 0}
    for r in (rows or []):
        a = asin_of(r)
        if not a:
            out["no_asin"] += 1
            continue
        if a in running:
            # Already made before this run, or already taken by an earlier row
            # in this same queue. Two different situations and they read
            # differently on screen.
            out["skip" if a in already else "repeat"].append(a)
            continue
        out["generate"].append(a)
        running.add(a)
    out["counts"] = {
        "queued": len(rows or []),
        "generate": len(out["generate"]),
        "skip": len(out["skip"]),
        "repeat": len(out["repeat"]),
        "no_asin": out["no_asin"],
        "already_made": len(already),
        "skus_on_record": len(taken_skus or ()),
    }
    out["verdict"] = verdict(out["counts"])
    return out


def verdict(c):
    """One sentence a person can act on, including when it looks wrong.

    The dangerous state is a full queue with NOTHING on record: that is exactly
    what a broken duplicate guard looks like, and it is indistinguishable from a
    genuine first run. Saying so is the difference between noticing and
    regenerating the lot.
    """
    if not c["queued"]:
        return ("Nothing is queued. Import from the sheet, or add products by "
                "hand, before generating.")
    if not c["already_made"]:
        return ("Nothing is on record as already generated. If this account HAS "
                "made listings before, the duplicate check is not seeing them "
                "and a run would remake everything — stop and check. If it "
                "genuinely has not, this is a first run and is correct.")
    if not c["generate"]:
        return ("Everything queued has already been generated. A run would make "
                "nothing new.")
    if not c["skip"]:
        return ("All %d queued products are new — none of them matches the %d "
                "already on record."
                % (c["generate"], c["already_made"]))
    return ("%d of the %d queued have already been generated and would be "
            "skipped. %d would be made."
            % (c["skip"], c["queued"], c["generate"]))


def for_workspace(config_path, workspace_id, config=None):
    """The plan for one account, read from the real stores.

    Deliberately tolerant: a missing queue or an unreadable output store gives
    an answer that says so, rather than an exception on a screen whose whole job
    is to reassure somebody before they spend money.
    """
    cfg = dict(config or {})
    cfg["_config_path"] = config_path
    cfg["_account_id"] = workspace_id

    err = ""
    seen, taken = set(), set()
    try:
        import amazon_listing_generator as G
        ws = G.output_ws(cfg)
        # PROBE THE STORE FIRST, and this is not belt and braces.
        #
        # load_existing_skus_and_asins CATCHES its own read errors and returns
        # empty sets with a console warning. That is reasonable for a run -- a
        # generate should not die because a store hiccupped -- but it means an
        # UNREADABLE store and an account that has generated nothing produce the
        # identical answer here.
        #
        # And those two need opposite responses. One is a first run; the other
        # would regenerate an entire catalogue at full AI spend. So the store is
        # read directly, where the exception still exists, before trusting a
        # zero. Found because this only failed inside the full suite: alone the
        # import happened to raise, and in the suite it did not.
        G._safe_records(ws)
        taken, seen = G.load_existing_skus_and_asins(ws, cfg)
    except Exception as e:
        err = "Could not read what has already been generated: %s" % str(e)[:180]

    rows, imported_at = [], ""
    try:
        from data import input_import as _ii
        rows = _ii.rows(config_path, workspace_id) or []
        imported_at = (_ii.summary(config_path, workspace_id) or {}).get("imported_at") or ""
    except Exception as e:
        err = (err + " | " if err else "") + \
              "Could not read the input queue: %s" % str(e)[:150]

    out = plan(rows, seen, taken)
    out["workspace"] = workspace_id
    out["imported_at"] = imported_at
    if err:
        out["error"] = err
        # A plan built on a store that could not be read is not a plan.
        out["verdict"] = ("This could not be worked out: " + err +
                          " Do not rely on the numbers above.")
    return out
