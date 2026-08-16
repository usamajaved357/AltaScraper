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

    if _is_fba(current):
        return current, {"action": "none", "price": None, "quantity": None,
                         "lead_days": None, "source_id": None, "rejections": [],
                         "inputs_age_mins": None,
                         "blocked_by": "this is an FBA listing",
                         "reason": ("Amazon holds the stock for this SKU, so its "
                                    "handling time and availability are not ours "
                                    "to set. Leaving it alone.")}

    decision = _sourcing.decide(current, pairs, rule, now)

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
