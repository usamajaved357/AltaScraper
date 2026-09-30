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
import threading

from api import amazon_listings as _al
from domain import currency as _currency
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


# A price changed in the PRICE EDITOR (one listing or a bulk %). Recorded since
# 29 Sep 2026 (the editor's recording had been failing silently), under its own
# action so it does NOT start the repricer's rest period -- it never did, and
# whether it should is the owner's decision (it would also pause the stock-out
# protection on every SKU a bulk change touched). The repricer's own price box
# records "update" and keeps pausing, as before.
PRICE_EDITOR_ACTION = "price_editor"


def _last_applied(config_path, ws, mkt, sku):
    for a in _repo.recent_actions(config_path, ws, mkt, sku, limit=50):
        if a.get("applied") == 1 and a.get("action") != PRICE_EDITOR_ACTION:
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

    # ONLY WHAT ACTUALLY DIFFERS GETS SENT.
    #
    #     "if the prices dont need to be changed i think repricer should not
    #      change anything, if a price change is required yes we should do it.
    #      the stock update is requured, yes do it"
    #
    # This used to patch the price on EVERY push, because the decision always
    # carries one -- so a run whose only real change was putting stock back to
    # three also rewrote the price to the number it already was. Harmless
    # arithmetically and not harmless otherwise: it is an edit to a live offer,
    # it shows in Amazon's own change history, and it makes "the repricer
    # changed my price" true on a day when it changed nothing.
    #
    # The two halves are now independent, which is exactly what he asked for:
    # the price goes only when the price moves, the stock goes whenever the
    # stock is wrong, and neither waits for the other.

    if decision.get("price") is not None:
        offers = copy.deepcopy(attrs.get("purchasable_offer") or [])
        if not offers:
            return [], ("this listing has no purchasable_offer to edit, so there is "
                        "no price field to patch")
        found = False       # the shape exists and we know where the number goes
        differs = False     # ...and the number we would write is not the one there
        for off in offers:
            for entry in (off.get("our_price") or []):
                for sched in (entry.get("schedule") or []):
                    key = ("value_with_tax" if "value_with_tax" in sched
                           else ("value" if "value" in sched else None))
                    if key is None:
                        continue
                    found = True
                    # Compared as money, to the penny. A float read back from
                    # Amazon can be 15.629999999999999 where ours is 15.63, and
                    # a bare != would call those two different prices for ever.
                    try:
                        same = (abs(float(sched[key])
                                    - float(decision["price"])) < 0.005)
                    except (TypeError, ValueError):
                        same = False    # unreadable: treat as needing the write
                    if not same:
                        differs = True
                    sched[key] = decision["price"]
        if not found:
            return [], ("purchasable_offer carries no our_price schedule, so the "
                        "price could not be set without inventing a shape")
        if differs:
            patches.append({"op": "replace", "path": "/attributes/purchasable_offer",
                            "value": offers})

    want_qty = decision.get("quantity")
    want_lead = decision.get("lead_days")
    if want_qty is not None or want_lead is not None:
        avail = copy.deepcopy(attrs.get("fulfillment_availability") or [])
        if not avail:
            return [], ("this listing has no fulfillment_availability to edit, so "
                        "stock and handling time cannot be patched")
        differs = False
        for a in avail:
            if want_qty is not None:
                try:
                    if int(a.get("quantity")) != int(want_qty):
                        differs = True
                except (TypeError, ValueError):
                    differs = True      # absent or unreadable: set it
                a["quantity"] = int(want_qty)
            # Only set a handling time where one already exists: writing it onto a
            # channel that never carried it is a guess about Amazon's schema.
            if want_lead is not None and "lead_time_to_ship_max_days" in a:
                try:
                    if int(a["lead_time_to_ship_max_days"]) != int(want_lead):
                        differs = True
                except (TypeError, ValueError):
                    differs = True
                a["lead_time_to_ship_max_days"] = int(want_lead)
        if differs:
            patches.append({"op": "replace",
                            "path": "/attributes/fulfillment_availability",
                            "value": avail})

    if not patches:
        return [], "there is nothing to change"
    return patches, ""


def seller_creds(cfg, workspace_id, marketplace):
    """(creds, marketplace_id, seller_id) for one account -- what run_live and
    every price send need. Raises RuntimeError for an account this app does not
    have. ONE copy (price-write map F7, 29 Sep 2026): the repricer's timer job
    (data/scheduler.py) and the Repricer screen (routes/sourcing_routes.py) each
    wrote it out, line for line; this is that code, unchanged. The credentials
    and marketplace id come from domain/accounts; the account is found by id
    here, as both copies did (domain/amazon_fees._creds_for finds it with
    accounts.get_account -- a third copy, recorded in known-issues)."""
    from domain import accounts as _acc
    c = cfg() if callable(cfg) else (cfg or {})
    for a in (c.get("accounts") or []):
        if str(a.get("id")) == str(workspace_id):
            return (_acc.account_creds(a), _acc.marketplace_id(marketplace),
                    str(a.get("seller_id") or ""))
    raise RuntimeError("no account called %s" % workspace_id)


def push_patches(creds, mkt, seller_id, sku, marketplace_id, product_type, patches,
                 rejected="Amazon rejected the change", issue_width=120):
    """Send price patches built by build_patches. -> (ok, why, submission_id).

    THE ONE SEND for every price writer (architecture 4F, 29 Sep 2026): the
    repricer (apply_one), the repricer's price box, the price editor and the
    percentage change each wrote this call and its refusal wording out by hand.
    What differs between them -- which gates run, the floor, how a failure is
    returned -- stays with each; only the send is shared. `rejected` and
    `issue_width` keep each caller's own words exactly as they were.

    ACCEPTED ONLY: anything but Amazon's OK is a refusal, worded from Amazon's
    own issue messages (Rule 4), never a guess.
    """
    res = _al.patch(creds, mkt, seller_id, sku, marketplace_id, product_type, patches,
                    issue_locale=("en_US" if str(mkt).upper() == "US" else "en_GB"))
    if res.get("status") != _al.OK:
        return False, _al.refusal_text(res, rejected, issue_width), ""
    return True, "", res.get("submission_id")


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

    sent, why, submission_id = push_patches(creds, mkt, seller_id, sku, marketplace_id,
                                            got["product_type"], patches)
    if not sent:
        out = dict(decision, blocked_by=why)
        _repo.record_action(config_path, ws, mkt, sku, out, current=current, applied=-1,
                        at=now.strftime("%Y-%m-%d %H:%M:%S"))
        return {"sku": sku, "applied": -1, "blocked_by": why, "decision": out}

    out = dict(decision, reason=(decision.get("reason", "") +
                                 " [pushed, Amazon submission %s]" % submission_id))
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
            "submission_id": submission_id}


def record_manual_price(config_path, ws, mkt, sku, price, was=None, current=None,
                        how="", who=None, pauses_repricer=True):
    """A person changed a live price: write it down where the repricer writes
    its own changes, and update the app's record of what it is selling for.

    ONE place for every manual price path (the repricer's price box, the price
    editor, the percentage change). The price editor's two routes used to call
    record_action with an argument it does not take (`error=""`); the TypeError
    was swallowed, so no hand-made price change was ever recorded (price-write
    review, 29 Sep 2026). Either way the next repricer decision compares against
    the NEW price (the snapshot below).

    pauses_repricer: True for the repricer's own box (action "update": its rest
    period starts from the change, as it always did); False for the price
    editor (action PRICE_EDITOR_ACTION: recorded, but it pauses nothing and is
    not counted as a repricer push -- the behaviour it had before, see above).
    `how`: "" for the repricer's box (its wording kept), else a short phrase
    such as "price editor" or "bulk +5%" put in front of the sentence."""
    if who is None:
        try:
            from domain import job_owner as _jo
            who = _jo.label(config_path)
        except Exception:
            who = ""
    sentence = ("Manual: %s%s set by %s"
                % (("%.2f -> " % float(was)) if was is not None else "",
                   "%.2f" % price, who or "hand"))
    decision = {
        "action": "update" if pauses_repricer else PRICE_EDITOR_ACTION,
        "price": round(price, 2),
        "quantity": None, "lead_days": None, "source_id": None,
        "manual": True, "manual_by": who,
        "reason": ("%s -- %s" % (how, sentence)) if how else sentence,
        "blocked_by": "", "rejections": [], "inputs_age_mins": None,
    }
    _repo.record_action(config_path, ws, mkt, sku, decision,
                        current=(current if current is not None else {"price": was}),
                        applied=1,
                        at=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    # AND THE APP'S OWN RECORD OF WHAT IT IS SELLING FOR. Without this the
    # next decision compares the supplier against the OLD price, so a hand
    # raise would immediately read as "too dear, cut it" -- which is the
    # opposite of "the repricer respects the manual change".
    try:
        from domain import live_snapshots as _ls
        _ls.set_price(config_path, ws, mkt, sku, round(price, 2))
    except Exception:
        pass
    return decision


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
        # The listing's own marketplace currency, from the shared map (was "$"
        # for the US and "£" for every other marketplace, EU included).
        sym=_currency.symbol_for_marketplace(mkt))


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

    # ONE PUSH RUN AT A TIME. The four-hourly job and the "Push now" button
    # are separate callers; running together, both read the cooldown before
    # either had recorded its push, so the same SKU could be patched twice
    # and the 4-hour rest period meant nothing (repricer review, 30 Sep 2026).
    # One process only -- the app runs a single worker.
    if not _RUN_LOCK.acquire(False):
        return {"ok": True, "pushed": 0, "skipped": 0, "busy": True,
                "note": ("another push run is already going -- nothing was "
                         "pushed twice. Try again in a minute.")}
    try:
        return _run_live_locked(config_path, cfg, creds_for, now,
                                workspace_id, marketplace, log)
    finally:
        _RUN_LOCK.release()


_RUN_LOCK = threading.Lock()


def _run_live_locked(config_path, cfg, creds_for, now, workspace_id,
                     marketplace, log):
    """run_live's body, run while holding _RUN_LOCK."""
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
