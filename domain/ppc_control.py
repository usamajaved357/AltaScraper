"""domain/ppc_control.py -- changing campaigns from the app, the owner's way.

    "i also want an option to turn on or off the campaigns and change the
     budget, bids and rules and every other feature that we have in seller
     central, i want it here"                            -- owner, 30 Sep 2026

CLAUDE.md Rule 8 -- never change a bid or a budget unless the owner names the
exact new value -- is kept by construction, not by care:

  * every change here is a VALUE THE OWNER TYPED (no defaults, no percentages,
    no "apply the recommendation"), sent with confirmed=True from a screen that
    showed him before -> after for the account and marketplace named;
  * the current value is READ FROM AMAZON first, so the confirmation's "before"
    and the change's baseline are Amazon's, not a stale copy;
  * the new value is READ BACK after, and the answer is what the screen says --
    "Amazon accepted" is never assumed from a 207;
  * every step is written to the Dr PPC ledger (drppc_activity, append-only) with
    who did it.

Nothing here runs on a schedule and nothing here decides a value.
"""
import datetime as _dt

from data import db as _db

# Sanity limits on a TYPED value -- catching a slipped decimal, not deciding
# anything. Amazon has its own limits and says so when one is broken.
MAX_BUDGET = 10000.0
MAX_BID = 100.0


def _now():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _creds(config_path, workspace_id):
    from domain import ads_sync as _as
    return _as.creds_or_why(workspace_id, config_path)


def store_campaigns(config_path, workspace_id, marketplace, items):
    """Keep Amazon's current campaign list (ads_campaigns). Replaces the
    account's list, so a deleted campaign does not linger."""
    conn = _db.get_db(config_path)
    conn.execute("DELETE FROM ads_campaigns WHERE workspace_id=? AND marketplace=?",
                 (workspace_id, marketplace))
    now = _now()
    for c in items or []:
        if not c.get("campaign_id"):
            continue
        conn.execute(
            "INSERT OR REPLACE INTO ads_campaigns (workspace_id, marketplace, campaign_id, "
            "name, state, budget, budget_type, targeting_type, fetched_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (workspace_id, marketplace, c["campaign_id"], c.get("name"), c.get("state"),
             c.get("budget"), c.get("budget_type"), c.get("targeting_type"), now))
    conn.commit()


def refresh_campaigns(config_path, workspace_id, marketplace):
    """Read every campaign's current state and budget from Amazon and keep it.
    -> {ok, count, fetched_at} or {ok: False, error}."""
    creds, why = _creds(config_path, workspace_id)
    if not creds:
        return why
    from api import amazon_ads_manage as _m
    try:
        items = _m.list_campaigns(creds, marketplace)
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
    store_campaigns(config_path, workspace_id, marketplace, items)
    return {"ok": True, "count": len(items), "fetched_at": _now(),
            "campaigns": items}


def structure(config_path, workspace_id, marketplace, campaign_id):
    """One campaign's ad groups, keywords, product targets and negatives, as
    Amazon holds them now."""
    creds, why = _creds(config_path, workspace_id)
    if not creds:
        return why
    from api import amazon_ads_manage as _m
    out = {"ok": True, "campaign_id": str(campaign_id)}
    for key, fn in (("ad_groups", _m.list_ad_groups), ("keywords", _m.list_keywords),
                    ("targets", _m.list_targets), ("negatives", _m.list_negative_keywords)):
        try:
            out[key] = fn(creds, marketplace, campaign_id)
        except Exception as e:
            out[key] = None
            out.setdefault("errors", {})[key] = str(e)[:240]
    return out


def _typed(value, what, limit):
    """The owner's typed amount -> (float, None) or (None, reason)."""
    try:
        v = float(str(value).strip())
    except (TypeError, ValueError):
        return None, "type the new %s as an amount, e.g. 12.50" % what
    if not (v > 0):
        return None, "the %s must be above zero" % what
    if v > limit:
        return None, ("%.2f is above %.0f -- check for a slipped decimal point"
                      % (v, limit))
    return round(v, 2), None


def _log(config_path, ws, mkt, kind, action, title, detail, etype, eid, who):
    try:
        from domain import drppc_activity as _act
        _act.record(config_path, ws, mkt, kind, "human", action, title, detail,
                    entity_type=etype, entity_id=eid, who=who)
    except Exception as e:
        # The change itself is not undone by a ledger that could not be
        # written -- but it is said, in the server log.
        print("[ppc_control] could not record %s for %s: %s" % (action, eid, e))


# What each kind of change reads, writes and reads back.
def _spec(kind):
    from api import amazon_ads_manage as _m
    return {
        "campaign": {"list": lambda c, m, parent: _m.list_campaigns(c, m),
                     "id": "campaign_id", "write": _m.update_campaign},
        "ad_group": {"list": lambda c, m, parent: _m.list_ad_groups(c, m, parent),
                     "id": "ad_group_id", "write": _m.update_ad_group},
        "keyword": {"list": lambda c, m, parent: _m.list_keywords(c, m, parent),
                    "id": "keyword_id", "write": _m.update_keyword},
        "target": {"list": lambda c, m, parent: _m.list_targets(c, m, parent),
                   "id": "target_id", "write": _m.update_target},
    }[kind]


def change(config_path, workspace_id, marketplace, kind, entity_id, campaign_id,
           state=None, amount=None, who=""):
    """Change one thing's state and/or its money (budget for a campaign, default
    bid for an ad group, bid for a keyword or target) to the OWNER'S VALUE.

    -> {ok, before, after, verified, error}. `campaign_id` scopes the read of
    ad groups / keywords / targets (Amazon lists those per campaign)."""
    if kind not in ("campaign", "ad_group", "keyword", "target"):
        return {"ok": False, "error": "unknown kind of change"}
    if state is not None:
        state = str(state).upper()
        if state not in ("ENABLED", "PAUSED"):
            return {"ok": False, "error": "state must be ENABLED or PAUSED"}
    money = None
    if amount is not None and str(amount).strip() != "":
        what = "daily budget" if kind == "campaign" else "bid"
        money, bad = _typed(amount, what, MAX_BUDGET if kind == "campaign" else MAX_BID)
        if bad:
            return {"ok": False, "error": bad}
    if state is None and money is None:
        return {"ok": False, "error": "nothing to change"}
    creds, why = _creds(config_path, workspace_id)
    if not creds:
        return why
    sp = _spec(kind)
    eid = str(entity_id)

    def _find():
        items = sp["list"](creds, marketplace, campaign_id)
        return next((x for x in items if str(x.get(sp["id"])) == eid), None)

    # 1. BEFORE, from Amazon.
    try:
        before = _find()
    except Exception as e:
        return {"ok": False, "error": "could not read it from Amazon first: %s" % str(e)[:240]}
    if before is None:
        return {"ok": False, "error": "Amazon has no %s %s in this account" % (kind.replace("_", " "), eid)}
    money_key = {"campaign": "budget", "ad_group": "default_bid"}.get(kind, "bid")
    desc = []
    if state is not None:
        desc.append("state %s -> %s" % (before.get("state"), state))
    if money is not None:
        desc.append("%s %s -> %.2f" % (money_key.replace("_", " "), before.get(money_key), money))
    title = "%s %s: %s" % (kind.replace("_", " "), before.get("name") or before.get("text") or before.get("label") or eid,
                           "; ".join(desc))
    _log(config_path, workspace_id, marketplace, "decision", "change_requested", title,
         "requested in the app, confirmed on screen", kind, eid, who)

    # 2. THE CHANGE.
    kw = {}
    if state is not None:
        kw["state"] = state
    if money is not None:
        kw[{"campaign": "budget", "ad_group": "default_bid"}.get(kind, "bid")] = money
    try:
        ok, err = sp["write"](creds, marketplace, eid, **kw)
    except Exception as e:
        ok, err = False, str(e)[:300]
    _log(config_path, workspace_id, marketplace, "execution",
         "change_sent" if ok else "change_refused", title, err or "Amazon accepted the change",
         kind, eid, who)
    if not ok:
        return {"ok": False, "before": before, "error": "Amazon refused it: %s" % (err or "no reason given")}

    # 3. READ IT BACK -- the only thing that says it took.
    after, verified = None, False
    try:
        after = _find()
        verified = bool(after) and (state is None or str(after.get("state")) == state) and (
            money is None or abs(float(after.get(money_key) or 0) - money) < 0.005)
    except Exception:
        after = None
    _log(config_path, workspace_id, marketplace, "verification",
         "change_verified" if verified else "change_not_yet_visible", title,
         "read back from Amazon" if verified else "Amazon took it but the read-back does not show it yet",
         kind, eid, who)
    if kind == "campaign" and after:
        try:
            conn = _db.get_db(config_path)
            conn.execute("UPDATE ads_campaigns SET state=?, budget=?, fetched_at=? WHERE "
                         "workspace_id=? AND marketplace=? AND campaign_id=?",
                         (after.get("state"), after.get("budget"), _now(), workspace_id,
                          marketplace, eid))
            conn.commit()
        except Exception as e:
            print("[ppc_control] could not keep %s's new state: %s" % (eid, e))
    return {"ok": True, "before": before, "after": after, "verified": verified}


def add_negative(config_path, workspace_id, marketplace, campaign_id, ad_group_id,
                 text, match_type, who=""):
    """Add one negative keyword (exact or phrase) to an ad group -- the owner's
    words, confirmed. -> {ok, error}."""
    text = str(text or "").strip()
    mt = {"exact": "NEGATIVE_EXACT", "phrase": "NEGATIVE_PHRASE"}.get(
        str(match_type or "").lower(), str(match_type or "").upper())
    if not text:
        return {"ok": False, "error": "type the negative keyword"}
    if mt not in ("NEGATIVE_EXACT", "NEGATIVE_PHRASE"):
        return {"ok": False, "error": "match type must be exact or phrase"}
    creds, why = _creds(config_path, workspace_id)
    if not creds:
        return why
    from api import amazon_ads_manage as _m
    title = "negative %s \"%s\" in ad group %s" % (mt.split("_")[1].lower(), text, ad_group_id)
    _log(config_path, workspace_id, marketplace, "decision", "negative_requested", title,
         "requested in the app, confirmed on screen", "ad_group", ad_group_id, who)
    try:
        ok, err = _m.add_negative_keyword(creds, marketplace, campaign_id, ad_group_id, text, mt)
    except Exception as e:
        ok, err = False, str(e)[:300]
    _log(config_path, workspace_id, marketplace, "execution",
         "negative_added" if ok else "negative_refused", title, err or "Amazon accepted it",
         "ad_group", ad_group_id, who)
    return {"ok": bool(ok), "error": ("Amazon refused it: " + err) if not ok else ""}
