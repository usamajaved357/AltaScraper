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
    # THROUGH rate_for_listing, WHICH ASKS THE SETTLED ORDERS FIRST. This used
    # to go straight to rate_for_asin -- Amazon's quote, or an average, or 15%
    # -- and so a product with a shelf of real Amazon statements behind it was
    # still priced off a percentage. The Sourcing page then reported a higher
    # ROI than the Orders page for the same product on the same day, because
    # Orders reads the statement and this did not. Same question, one answer.
    #
    # AND IT ASKS AMAZON ITSELF WHEN NOTHING IS CACHED (auto=True):
    #
    #     "When the app needs a fee rate for a product and tier 1 (settled
    #      orders) has no data, it should automatically call getMyFeesEstimate
    #      for that ASIN+price if there's no cached quote ... don't wait for the
    #      scheduler or a manual button press."
    #
    # This function runs for every enrolled SKU on every page load, so an
    # unrationed call apiece would be sixty-seven of them before the screen
    # could draw. `auto` is what makes it safe: amazon_fees rations these calls,
    # remembers an account Amazon refuses rather than asking 67 times, and uses
    # a short timeout -- and every one of those limits ends in the same silent
    # fall-through to the account's measured rate. A fee that cannot be fetched
    # never delays or breaks a price; it is simply not the best answer yet, and
    # the next draw or the daily job picks it up.
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

    # HOW MANY UNITS TO KEEP THE LISTING AT.
    #
    #     "there should be a separate default stock setting which is activated
    #      along with the auto pricing being on"
    #
    # Read LIVE, here, for the same reason the fee rate and the postage policy
    # are: this is the only spot a rule is assembled before decide() runs, so it
    # is the only spot that has to know where a setting is kept (Rule 12).
    #
    # Live, and NOT copied onto the SKU at enrolment the way the ROI target and
    # the direction are. Those two are pricing decisions, and changing your mind
    # later must not silently re-price sixty listings. This is one number saying
    # how much stock you hold, so changing it should move everything -- except a
    # SKU somebody has given its own figure, which is a decision and survives.
    #
    # `_repo.rule_for` returns only what was STORED, before defaults are filled
    # in, so an absent key really does mean "never set on this SKU" rather than
    # "set to the built-in 3".
    if rule.get("in_stock_quantity") in (None, ""):
        try:
            from config import settings as _settings
            _stk = (_settings.read_raw(config_path) or {}).get(
                "sourcing_default_stock")
            if _stk not in (None, ""):
                rule["in_stock_quantity"] = max(1, int(_stk))
        except Exception:
            pass      # the module default stands, and it is 3

    rule["fee_basis"], rule["fee_detail"] = "", ""
    try:
        from domain import amazon_fees as _fees
        _rate, _basis, _detail = _fees.rate_for_listing(
            config_path, None, workspace_id, marketplace, None,
            sku, current.get("asin"), current.get("price"),
            is_fba=_is_fba(current), allow_quote=True, auto=True)
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
            # THE RATE THIS DECISION WAS PRICED WITH, handed over rather than
            # looked up again. The panel sits directly under the price it
            # explains, and a second lookup could answer differently -- the
            # settled tier above outranks the quote this panel would find on
            # its own (CLAUDE.md Rule 12).
            decision["fees"] = _fees.breakdown_for(
                config_path, workspace_id, marketplace, current.get("asin"),
                _at, is_fba=_is_fba(current),
                currency=current.get("currency") or "GBP",
                rate=rule.get("referral_rate"), basis=rule.get("fee_basis") or "",
                detail=rule.get("fee_detail") or "")
    except Exception:
        pass          # a breakdown that cannot be built must not lose the price
    return current, decision


def check_listings(config_path, account, workspace_id, marketplace,
                   remove_gone=True):
    """Ask Amazon which enrolled SKUs it still has, and drop the ones it does not.

        "if the listing is deleted from my sellercentral i think the app knows
         it, so lets remove the deleted items from repricer automatically"

    It did know -- but only when somebody pressed the button. This is the same
    check, in one place, called BOTH by that button and by the daily job, so the
    automatic pass and the manual one cannot come to different conclusions
    (CLAUDE.md Rule 12).

    WHAT COUNTS AS DELETED, AND WHAT DOES NOT. Only HTTP 404 from
    getListingsItem -- api/amazon_listings maps that alone to GONE, and
    everything else, a timeout or a 403 from an account whose SP-API roles are
    not granted, to FAILED. A SKU Amazon would not talk about is left EXACTLY as
    it was. Measured on jack_uk, whose Product Fees role is missing: every one
    of its SKUs answers 403, and not one of them may be treated as deleted.

    WHAT "REMOVE" DOES, AND WHAT IT KEEPS. The SKU is unenrolled, so it leaves
    the repricer -- `enrolled()` returns only enrolled=1, so it is gone from the
    list, from every pricing pass and from the supplier template. Nothing is
    deleted: the enrolment row, its supplier links, its price history and its
    rule all stay exactly where they are. If the listing comes back it reappears
    on the Add screen, and re-enrolling it restores everything it had.

    That is why this can be automatic at all. Marking a live SKU deleted by
    mistake would cost a few minutes; deleting its suppliers and its 20% ROI
    target would cost an afternoon and could not be undone.
    """
    from api import amazon_listings as _al
    from domain import accounts as _acc_mod

    acc = account or {}
    rows = _repo.enrolled(config_path, workspace_id, marketplace)
    creds = _acc_mod.account_creds(acc)
    mid = _acc_mod.marketplace_id(marketplace)
    seller = str(acc.get("seller_id") or "")
    out = {"checked": len(rows), "gone": [], "removed": [], "still_there": 0,
           "unreadable": [], "note": "", "error": ""}
    if not (seller and mid):
        out["error"] = ("this account has no seller id or marketplace, so "
                        "Amazon cannot be asked about its listings")
        return out

    for r in rows:
        sku = str(r.get("sku") or "")
        if not sku:
            continue
        try:
            got = _al.get_item(creds, marketplace, seller, sku, mid)
        except Exception:
            # Never raises: this runs on a timer, and one odd SKU must not stop
            # the rest being checked.
            out["unreadable"].append(sku)
            continue
        if got["status"] == _al.GONE:
            # Marked and disarmed in one statement, then taken out of the
            # repricer. In that order: a SKU that is unenrolled but still armed
            # would be one nothing is watching and something could still push.
            _repo.set_listing_state(config_path, workspace_id, marketplace,
                                    sku, _repo.GONE)
            out["gone"].append(sku)
            if remove_gone:
                _repo.unenrol(config_path, workspace_id, marketplace, sku)
                out["removed"].append(sku)
        elif got["status"] == _al.OK:
            _repo.set_listing_state(config_path, workspace_id, marketplace,
                                    sku, _repo.LIVE_OK)
            out["still_there"] += 1
        else:
            # "Amazon would not answer" is NOT "the listing is gone". Marking it
            # gone on a timeout would disarm a perfectly good SKU.
            out["unreadable"].append(sku)

    note = "%d still on Amazon, %d gone" % (out["still_there"], len(out["gone"]))
    if out["removed"]:
        note += (" — %s %s taken out of the repricer. Nothing was deleted: "
                 "their suppliers, history and rules are kept, and re-enrolling "
                 "brings them back"
                 % (", ".join(out["removed"][:6]),
                    "was" if len(out["removed"]) == 1 else "were"))
        if len(out["removed"]) > 6:
            note += " (and %d more)" % (len(out["removed"]) - 6)
    elif out["gone"]:
        note += (" — auto-pricing is now off for %s" % ", ".join(out["gone"][:6])
                 + (" and others" if len(out["gone"]) > 6 else ""))
    if out["unreadable"]:
        note += (". %d could not be read and were left exactly as they were"
                 % len(out["unreadable"]))
    out["note"] = note
    return out


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
