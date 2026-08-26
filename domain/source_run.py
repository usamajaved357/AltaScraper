"""domain/source_run.py -- decide what would happen, and write it down.

This is the dry run. It reads the stored supplier readings, asks
domain/sourcing.py what should happen to each enrolled SKU, and records the
answer in sourcing_actions with applied=0. It pushes NOTHING. Phase D adds the
one step that does, and it will call exactly this and then act on the result --
so what you read in the log now is what will happen then, not an approximation
of it.

WHY THE CURRENT STATE MATTERS AS MUCH AS THE SUPPLIER'S
A decision needs to know what Amazon has RIGHT NOW, because the guards are
comparisons: max_change_pct only means something against the current price, and
"do not push trivia" only means something against the current handling time.
Without the current price the biggest guard against a misparsed supplier page is
simply absent -- so when it is missing that is said out loud rather than passed
over, and the decision is held.

FBA IS NOT OURS TO TOUCH
The repricer was designed for merchant-fulfilled listings, where we buy from a
supplier and post it ourselves. On an FBA listing Amazon holds the stock: the
handling time is theirs and going "out of stock" because a supplier ran out is
simply false -- the units are in their warehouse. Those SKUs are reported and
skipped rather than half-handled.
"""
import datetime as _dt

from domain import source_repo as _repo
from domain import sourcing as _sourcing


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "").replace("£", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _int(v):
    f = _num(v)
    return None if f is None else int(f)


def current_for(config_path, workspace_id, marketplace, sku):
    """What Amazon has now for this SKU, from the catalogue snapshot we hold.

    Returns {} when the SKU is not in the snapshot at all -- which is itself
    worth knowing, because it usually means the catalogue has not been synced
    since the SKU was created.
    """
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, workspace_id, marketplace) or {}
    except Exception:
        return {}
    want = str(sku or "").strip().upper()
    for it in (rec.get("items") or []):
        if str(it.get("sku") or "").strip().upper() != want:
            continue
        return {"price": _num(it.get("price")),
                "quantity": _int(it.get("qty")),
                "lead_days": _int(it.get("handling")),
                "fulfillment": str(it.get("fulfillment") or ""),
                "status": str(it.get("status") or ""),
                # OUR OWN ASIN, carried through so the fee can be asked about
                # THIS product. Not the one in the SKU -- that is the COMPETITOR
                # ASIN the listing was researched from (see rowAsin in
                # static/js/listings.js), and asking Amazon what IT charges on
                # someone else's product is a different question.
                "asin": str(it.get("asin") or ""),
                "found": True}
    return {}


def _is_fba(current):
    """AFN / AMAZON_NA / FBA all mean Amazon holds the stock."""
    f = str((current or {}).get("fulfillment") or "").upper()
    return bool(f) and ("AFN" in f or "AMAZON" in f or "FBA" in f)


def decide_one(config_path, workspace_id, marketplace, sku, now=None):
    """The decision for one SKU, with the current state that produced it."""
    now = now or _dt.datetime.now()
    current = current_for(config_path, workspace_id, marketplace, sku)
    pairs = _repo.pairs_for(config_path, workspace_id, marketplace, sku)
    rule = _repo.rule_for(config_path, workspace_id, marketplace, sku)

    # The listing's own currency, from its marketplace. Set here rather than
    # stored, because it is a fact about the marketplace and not a preference --
    # and a stored copy could be edited into disagreeing with reality.
    rule.setdefault("currency", _sourcing.CURRENCY_FOR.get(
        str(marketplace or "").upper()))

    # WHAT AMAZON ACTUALLY TAKES ON THIS PRODUCT.
    #
    #     "the fees of amazon reflecting in the details should be accurate and
    #      not estimate of 15 percent like i see right now in the app"
    #
    # Right, and it was worse than a rounding difference. MEASURED against what
    # Amazon has settled on these accounts: jack_uk 17.5%, nestwell_goods 18.0%,
    # selvora_limited 18.0%, against the flat 15% every floor was built on. On a
    # 24.00 unit that is 33.89 instead of 35.12 -- pricing 1.23 too low, and a
    # "20% ROI" that is really about 14%.
    #
    # SET ONCE, HERE, so every one of the thirteen places decide() reads
    # rule["referral_rate"] follows without knowing anything about fees. This is
    # the only spot a rule is assembled before decide runs, so it is the only
    # spot that has to change (CLAUDE.md Rule 12).
    #
    # Cache-only: allow_quote=False. This function runs for every enrolled SKU
    # on every page load, and a live call apiece would be sixty-seven of them
    # before the screen could draw. The cache is filled by /sourcing/fees.
    # HOW LONG THE POSTAGE TAKES, from the one place settings live. Amazon
    # counts the handling time and the postage transit separately, so the
    # handling time must not include the postage days -- see
    # sourcing.handling_days(). Stamped here for the same reason the fee rate
    # is: this is the only spot a rule is assembled before decide() runs, so it
    # is the only spot that has to know where a setting is kept.
    try:
        from config import settings as _settings
        _pol = (_settings.read_raw(config_path) or {}).get("shipping_policy_days")
        if _pol not in (None, ""):
            rule["shipping_policy_days"] = max(0, int(_pol))
    except Exception:
        pass          # the module default stands, and it is the real policy today

    rule["fee_basis"], rule["fee_detail"] = "", ""
    try:
        from domain import amazon_fees as _fees
        _rate, _basis, _detail = _fees.rate_for_asin(
            config_path, None, workspace_id, marketplace, None,
            current.get("asin"), current.get("price"),
            is_fba=_is_fba(current), allow_quote=False)
        if _rate:
            rule["referral_rate"] = _rate
        rule["fee_basis"], rule["fee_detail"] = _basis, _detail
    except Exception:
        pass          # a fee lookup that fails must never stop a price being worked out

    if _is_fba(current):
        return current, {"action": "none", "price": None, "quantity": None,
                         "lead_days": None, "source_id": None, "rejections": [],
                         "inputs_age_mins": None,
                         "blocked_by": "this is an FBA listing",
                         "reason": ("Amazon holds the stock for this SKU, so its "
                                    "handling time and availability are not ours "
                                    "to set. Leaving it alone.")}

    # HAS AMAZON STILL GOT THIS SKU? Read from the enrollment row, which the
    # listing check writes -- not asked here, because that would be one Amazon
    # call per SKU on every draw of the screen.
    state = ""
    try:
        for e in _repo.enrolled(config_path, workspace_id, marketplace):
            if str(e.get("sku")) == str(sku):
                state = str(e.get("listing_state") or "")
                break
    except Exception:
        state = ""

    decision = _sourcing.decide(current, pairs, rule, now, listing_state=state)

    # A decision to change the price with nothing to compare against has lost
    # its most important guard. Say so rather than quietly pushing.
    if decision["action"] == "update" and current.get("price") is None:
        note = ("we do not know this listing's current price, so the "
                "%.0f%% change limit could not be applied"
                % _sourcing.rule_with_defaults(rule)["max_change_pct"])
        decision = dict(decision, action="none", blocked_by=note,
                        reason=(decision["reason"] + " -- held because " + note
                                + (". Sync the catalogue and it will price normally."
                                   if not current.get("found") else "")))

    # WHICH FEE THIS PRICE WAS BUILT ON, carried to the screen. A rate is a
    # number; whether it came from Amazon or from an average of your own
    # settled orders is the difference between a figure and a guess, and a
    # screen that cannot tell them apart will present one as the other.
    decision["fee_basis"] = rule.get("fee_basis") or ""
    decision["fee_detail"] = rule.get("fee_detail") or ""
    # On the breakdown too, because that is the table the "Amazon's cut" line is
    # drawn from and it is read on its own (_priceBreakdown in sourcing.js).
    if isinstance(decision.get("breakdown"), dict):
        decision["breakdown"]["fee_basis"] = decision["fee_basis"]
        decision["breakdown"]["fee_detail"] = decision["fee_detail"]

    # EVERY AMAZON CHARGE ON THE PRICE THIS DECISION LANDED ON -- the "All
    # Amazon fees" panel. Worked out at the DECIDED price rather than the one
    # live on Amazon, because the panel sits inside a row that is proposing a
    # change and the reader is asking what Amazon takes out of THAT.
    try:
        from domain import amazon_fees as _fees
        _at = decision.get("price") or current.get("price")
        if _at:
            decision["fees"] = _fees.breakdown_for(
                config_path, workspace_id, marketplace, current.get("asin"),
                _at, is_fba=_is_fba(current),
                currency=current.get("currency") or "GBP")
    except Exception:
        pass          # a breakdown that cannot be built must not lose the price
    return current, decision


def dry_run(config_path, workspace_id=None, marketplace=None, now=None,
            record=True, log=None):
    """Decide for every enrolled SKU. Writes to the log, changes nothing live.

    Never raises: one odd SKU must not stop the rest, and this runs on a timer.
    """
    now = now or _dt.datetime.now()
    rows = _repo.enrolled(config_path, workspace_id, marketplace)
    out = []
    # below_target counts SKUs earning less than the percentage target at their
    # CURRENT price. It is deliberately not one of the actions: a listing can be
    # underwater and have nothing to change about it -- those are the ones worth
    # seeing, and counting it as an action would hide them among the no-ops.
    counts = {"update": 0, "out_of_stock": 0, "none": 0, "blocked": 0,
              "below_target": 0}

    for row in rows:
        ws, mkt, sku = row["workspace_id"], row["marketplace"], row["sku"]
        try:
            current, decision = decide_one(config_path, ws, mkt, sku, now)
        except Exception as e:                       # never let one SKU stop the pass
            current, decision = {}, {
                "action": "none", "price": None, "quantity": None,
                "lead_days": None, "source_id": None, "rejections": [],
                "inputs_age_mins": None, "blocked_by": "could not decide",
                "reason": str(e)[:300]}
        counts[decision["action"]] = counts.get(decision["action"], 0) + 1
        if decision.get("blocked_by"):
            counts["blocked"] += 1
        # meets is None when there is no target, or not enough to tell. Only an
        # explicit False is a listing that is genuinely short.
        if (decision.get("target") or {}).get("meets") is False:
            counts["below_target"] += 1
        if record:
            _repo.record_action(config_path, ws, mkt, sku, decision,
                                current=current, applied=0)
        if log:
            log("%s -> %s %s" % (sku, decision["action"],
                                 decision.get("blocked_by") or ""))
        out.append({"workspace_id": ws, "marketplace": mkt, "sku": sku,
                    "mode": row.get("mode") or "dry_run",
                    "current": current, "decision": decision})

    return {"ok": True, "skus": len(rows), "counts": counts, "decisions": out,
            "note": ("no SKUs are enrolled in the repricer yet" if not rows else "")}
