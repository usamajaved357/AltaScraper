"""domain/source_apply.py -- the only place that lets a decision reach Amazon.

Everything before this decides and records. This is the step that acts, so it is
written as a list of reasons NOT to. A decision has to pass every one of them,
and each refusal is recorded with its reason, because a repricer that silently
declines to act is as confusing as one that silently acts.

THE GATES, IN ORDER
  1. the master switch is off            -- one place to stop everything, instantly
  2. this SKU is not armed               -- enrollment is per SKU and starts as dry run
  3. this SKU has no min_price           -- see below; this one is not negotiable
  4. the decision is held or is a no-op  -- nothing to do
  5. it was pushed too recently          -- cooldown, so a flapping supplier
                                            cannot thrash a live price
  6. Amazon does not hold the SKU        -- nothing to patch

WHY min_price IS MANDATORY TO ARM
The floor is computed FROM the supplier's cost, so a misread cost produces a
floor that is wrong in the same direction and just as confident. min_price is the
only guard that does not depend on the reading, which makes it the only thing
standing between a parsing bug and selling stock at a loss. Refusing to arm
without one is the single most useful rule in this file.

WHAT IT SENDS
The patch is built by editing the attribute structure AMAZON RETURNED, never one
composed here (Rule 4). If a listing has no purchasable_offer to edit, the push
is refused and says so rather than inventing a shape and hoping.
"""
import copy
import datetime as _dt

from api import amazon_listings as _al
from domain import source_repo as _repo
from domain import source_run as _run
from domain import sourcing as _sourcing

COOLDOWN_HOURS = 4.0        # matches the check timer: at most one push per sweep


def is_enabled(cfg):
    """The master switch. OFF unless someone has explicitly turned it on.

    Defaulting to on would mean a deploy could start moving prices before anyone
    had read a single dry run.
    """
    cfg = cfg() if callable(cfg) else (cfg or {})
    return bool(cfg.get("repricer_enabled", False))


def _last_applied(config_path, ws, mkt, sku):
    for a in _repo.recent_actions(config_path, ws, mkt, sku, limit=50):
        if a.get("applied") == 1:
            return a
    return None


def _hours_since(stamp, now):
    if not stamp:
        return None
    try:
        t = _dt.datetime.strptime(str(stamp)[:19], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    return (now - t).total_seconds() / 3600.0


def why_not(config_path, cfg, ws, mkt, sku, decision, now=None, enrollment=None):
    """The reason this decision may not be pushed, or "" if it may be."""
    now = now or _dt.datetime.now()
    if not is_enabled(cfg):
        return "the repricer's master switch is off"

    row = enrollment
    if row is None:
        rows = [r for r in _repo.enrolled(config_path, ws, mkt) if r["sku"] == sku]
        row = rows[0] if rows else None
    if not row:
        return "this SKU is not enrolled"
    if str(row.get("mode") or "dry_run") != "live":
        return "this SKU is in dry run"

    rule = _sourcing.rule_with_defaults(_repo.rule_for(config_path, ws, mkt, sku))
    if rule.get("min_price") is None:
        return ("no minimum price is set for this SKU -- it is the only guard that "
                "survives a misread supplier cost, so nothing is pushed without it")

    if decision.get("blocked_by"):
        return decision["blocked_by"]
    if decision.get("action") not in ("update", "out_of_stock"):
        return "nothing to change"

    last = _last_applied(config_path, ws, mkt, sku)
    hrs = _hours_since((last or {}).get("at"), now)
    if hrs is not None and hrs < COOLDOWN_HOURS:
        return ("pushed %.1f hours ago -- waiting %.0f hours between changes so a "
                "flapping supplier cannot thrash a live price" % (hrs, COOLDOWN_HOURS))
    return ""


def build_patches(attributes, decision, marketplace_id):
    """Patch operations built by EDITING what Amazon returned.

    Returns (patches, error). The price goes back into the same purchasable_offer
    structure it came out of, and the quantity and handling time into the same
    fulfillment_availability -- so the shape is always one Amazon has already
    accepted for this product type.
    """
    attrs = attributes or {}
    patches = []

    if decision.get("price") is not None:
        offers = copy.deepcopy(attrs.get("purchasable_offer") or [])
        if not offers:
            return [], ("this listing has no purchasable_offer to edit, so there is "
                        "no price field to patch")
        touched = False
        for off in offers:
            for entry in (off.get("our_price") or []):
                for sched in (entry.get("schedule") or []):
                    if "value_with_tax" in sched:
                        sched["value_with_tax"] = decision["price"]
                        touched = True
                    elif "value" in sched:
                        sched["value"] = decision["price"]
                        touched = True
        if not touched:
            return [], ("purchasable_offer carries no our_price schedule, so the "
                        "price could not be set without inventing a shape")
        patches.append({"op": "replace", "path": "/attributes/purchasable_offer",
                        "value": offers})

    want_qty = decision.get("quantity")
    want_lead = decision.get("lead_days")
    if want_qty is not None or want_lead is not None:
        avail = copy.deepcopy(attrs.get("fulfillment_availability") or [])
        if not avail:
            return [], ("this listing has no fulfillment_availability to edit, so "
                        "stock and handling time cannot be patched")
        for a in avail:
            if want_qty is not None:
                a["quantity"] = int(want_qty)
            # Only set a handling time where one already exists: writing it onto a
            # channel that never carried it is a guess about Amazon's schema.
            if want_lead is not None and "lead_time_to_ship_max_days" in a:
                a["lead_time_to_ship_max_days"] = int(want_lead)
        patches.append({"op": "replace", "path": "/attributes/fulfillment_availability",
                        "value": avail})

    if not patches:
        return [], "there is nothing to change"
    return patches, ""


def apply_one(config_path, cfg, creds, marketplace_id, seller_id,
              ws, mkt, sku, now=None, decision=None, current=None):
    """Decide, check every gate, and push if all of them pass. Never raises.

    Returns the decision dict with `applied` and `push` describing what happened,
    and records exactly that -- including the failures, because a push Amazon
    rejected must not be logged as a price we set.
    """
    now = now or _dt.datetime.now()
    if decision is None:
        current, decision = _run.decide_one(config_path, ws, mkt, sku, now)

    blocked = why_not(config_path, cfg, ws, mkt, sku, decision, now)
    if blocked:
        out = dict(decision, blocked_by=blocked)
        _repo.record_action(config_path, ws, mkt, sku, out, current=current, applied=0,
                            at=now.strftime("%Y-%m-%d %H:%M:%S"))
        return {"sku": sku, "applied": 0, "blocked_by": blocked, "decision": out}

    got = _al.get_item(creds, mkt, seller_id, sku, marketplace_id)
    if got["status"] != _al.OK:
        note = ("Amazon does not have this SKU" if got["status"] == _al.GONE
                else "could not read the listing from Amazon: %s" % got["error"])
        out = dict(decision, blocked_by=note)
        _repo.record_action(config_path, ws, mkt, sku, out, current=current, applied=0,
                            at=now.strftime("%Y-%m-%d %H:%M:%S"))
        return {"sku": sku, "applied": 0, "blocked_by": note, "decision": out}

    patches, err = build_patches(got["attributes"], decision, marketplace_id)
    if err:
        out = dict(decision, blocked_by=err)
        _repo.record_action(config_path, ws, mkt, sku, out, current=current, applied=0,
                            at=now.strftime("%Y-%m-%d %H:%M:%S"))
        return {"sku": sku, "applied": 0, "blocked_by": err, "decision": out}

    res = _al.patch(creds, mkt, seller_id, sku, marketplace_id,
                    got["product_type"], patches,
                    issue_locale=("en_US" if str(mkt).upper() == "US" else "en_GB"))
    if res["status"] != _al.OK:
        why = res["error"] or "Amazon rejected the change"
        if res["issues"]:
            why += " -- " + "; ".join(
                str(i.get("message") or "")[:120] for i in res["issues"][:3])
        out = dict(decision, blocked_by=why)
        _repo.record_action(config_path, ws, mkt, sku, out, current=current, applied=-1,
                        at=now.strftime("%Y-%m-%d %H:%M:%S"))
        return {"sku": sku, "applied": -1, "blocked_by": why, "decision": out}

    out = dict(decision, reason=(decision.get("reason", "") +
                                 " [pushed, Amazon submission %s]" % res["submission_id"]))
    _repo.record_action(config_path, ws, mkt, sku, out, current=current, applied=1,
                        at=now.strftime("%Y-%m-%d %H:%M:%S"))

    # TOLD, BECAUSE IT IS NO LONGER HELD.
    #
    #     "i dont want the app to hold the change if there is more than the max
    #      change value, i just want it to send me the notification"
    #
    # sourcing.decide used to refuse a move past max_change_pct and wait to be
    # noticed. It now applies it and raises `large_move`, and this is the other
    # half of that bargain: the moment it is really on Amazon -- after the
    # patch, not before -- somebody is told. Sent here rather than in decide()
    # so a dry run, which decides exactly the same way, never claims a price
    # changed that did not.
    #
    # Never in the way of the push: notify() swallows its own failures, and this
    # is after the action is already recorded, so a Slack outage cannot cost a
    # price change or its log entry.
    try:
        _notify_push(config_path, ws, mkt, sku, out, current)
    except Exception:
        pass
    return {"sku": sku, "applied": 1, "blocked_by": "", "decision": out,
            "submission_id": res["submission_id"]}


def _notify_push(config_path, ws, mkt, sku, decision, current):
    """One line about what has just changed on Amazon: a price, or the stock.

    Only a LARGE move reaches Slack -- see the note on _SLACK_WORTHY in
    domain/notify.py. Sixty-seven four-hourly repricings pinging a channel is a
    channel nobody reads. Going out of stock and coming back always do: those
    are not repricings, they are the listing stopping and starting selling, and
    they happen a handful of times a month.
    """
    from domain import notify as _n
    from domain import catalogue as _cat

    act = decision.get("action")
    if act not in ("update", "out_of_stock"):
        return
    if act == "update" and decision.get("price") is None:
        return
    name = sku
    try:
        idx = _cat.index(config_path, ws, mkt)
        item = _cat.look(idx, sku) or {}
        name = str(item.get("title") or "").strip() or sku
    except Exception:
        pass

    # ---- the listing has just STOPPED selling ---------------------------
    #
    #     "if every supplier is out of stock, make me out of stock on amazon
    #      and also notify me"
    #
    # Told only AFTER the quantity really reached Amazon, like every other
    # message here -- a dry run decides identically and must never claim a
    # listing went out of stock when nothing was pushed. The reason carries
    # WHICH suppliers failed, because "out of stock" without that is a message
    # you have to go and investigate before you can act on it.
    if act == "out_of_stock":
        _n.went_out_of_stock(config_path, ws, sku, name,
                             why=decision.get("reason") or "",
                             marketplace=mkt)
        return

    # ---- ...or STARTED again -------------------------------------------
    # A quantity going from nothing to something is the listing coming back,
    # and it is worth interrupting somebody about for the same reason the stop
    # was: it changes whether the SKU can sell at all.
    was_qty = (current or {}).get("quantity")
    now_qty = decision.get("quantity")
    if (was_qty is not None and now_qty is not None
            and int(was_qty) == 0 and int(now_qty) > 0):
        _n.came_back_in_stock(config_path, ws, sku, name,
                              int(now_qty), marketplace=mkt)

    # A PRICE THAT DID NOT MOVE IS NOT A PRICE MOVE.
    #
    # An up-only SKU whose stock or handling time needed fixing produces
    # action="update" with the price pinned to what Amazon already has -- the
    # push is real and the log entry is right, but announcing "10.06 -> 10.06"
    # is a notification that says nothing. The stock and handling change is
    # still recorded; it just does not ring a bell.
    _was = (current or {}).get("price")
    if (_was is not None and decision.get("price") is not None
            and abs(float(_was) - float(decision["price"])) < 0.005):
        return

    b = decision.get("breakdown") or {}
    drift = decision.get("cost_was")
    _n.price_move(
        config_path, ws, sku, name,
        was=(current or {}).get("price"), now=decision.get("price"),
        cost_was=drift, cost_now=b.get("cost"),
        move_pct=decision.get("move_pct") or 0,
        profit=b.get("profit"),
        roi=((b.get("profit") / b["cost"] * 100)
             if b.get("profit") is not None and b.get("cost") else None),
        marketplace=mkt,
        large=bool(decision.get("large_move")),
        sym=("$" if str(mkt).upper() == "US" else "£"))


def run_live(config_path, cfg, creds_for, now=None, workspace_id=None,
             marketplace=None, log=None):
    """Push every armed SKU whose decision passes the gates. Never raises.

    `creds_for(workspace_id, marketplace)` -> (creds, marketplace_id, seller_id),
    injected so this module needs to know nothing about how accounts are stored.
    """
    now = now or _dt.datetime.now()
    if not is_enabled(cfg):
        return {"ok": True, "pushed": 0, "skipped": 0,
                "note": "the repricer's master switch is off -- nothing was pushed"}

    rows = [r for r in _repo.enrolled(config_path, workspace_id, marketplace)
            if str(r.get("mode") or "dry_run") == "live"]
    pushed = failed = skipped = 0
    detail = []
    for row in rows:
        ws, mkt, sku = row["workspace_id"], row["marketplace"], row["sku"]
        try:
            creds, mkt_id, seller_id = creds_for(ws, mkt)
        except Exception as e:
            skipped += 1
            detail.append({"sku": sku, "applied": 0,
                           "blocked_by": "no credentials: %s" % str(e)[:120]})
            continue
        try:
            res = apply_one(config_path, cfg, creds, mkt_id, seller_id,
                            ws, mkt, sku, now)
        except Exception as e:                    # one SKU must not stop the rest
            skipped += 1
            detail.append({"sku": sku, "applied": 0,
                           "blocked_by": "could not apply: %s" % str(e)[:160]})
            continue
        if res["applied"] == 1:
            pushed += 1
        elif res["applied"] == -1:
            failed += 1
        else:
            skipped += 1
        detail.append({k: res[k] for k in ("sku", "applied", "blocked_by")})
        if log:
            log("%s -> applied=%s %s" % (sku, res["applied"], res["blocked_by"]))

    return {"ok": True, "armed": len(rows), "pushed": pushed, "rejected": failed,
            "skipped": skipped, "detail": detail}
