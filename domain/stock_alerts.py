"""domain/stock_alerts.py -- SKUs with nowhere left to buy from.

    "add an alert in the app that whenever all the links go out of stock i should
     receive a notification"

WHY THIS HOLDS NO STATE OF ITS OWN
The obvious build is a table of alerts, written when a sweep notices a SKU has
gone dark and cleared when it comes back. That table is then a second copy of a
fact the source readings already carry, and the two drift the moment anything goes
wrong: a sweep that crashes half way leaves alerts for SKUs that recovered, and a
row deleted by hand leaves a SKU with no supplier and no alert. The screen then
shows a warning the data does not support, or misses one it does.

So an alert is a QUESTION ASKED OF THE READINGS, every time, and there is nothing
to keep in step (CLAUDE.md Rule 12). It costs one query per enrolled SKU against
a local database.

WHAT COUNTS AS "NOWHERE TO BUY FROM"
Every source is out of stock or ended, AND at least one source exists. Precisely
NOT this:

  * a SKU with no sources at all -- that is not an alert, it is a SKU nobody has
    set up yet, and mixing the two buries the real ones;
  * a SKU whose sources merely could not be READ this time. "eBay would not
    answer" is not "there is nowhere to buy it". Alerting on it would fire every
    time eBay had a bad minute, and an alert that cries wolf is worse than none --
    the next real one gets ignored. Those SKUs are reported separately as
    `unreadable` so they are still visible without being called an emergency.

PER SKU, NEVER PER ASIN -- one ASIN can carry several SKUs with different
suppliers, and one of them running dry says nothing about the others.
"""
import datetime as _dt

from domain import order_sources as _osrc
from domain import source_repo as _repo

# What the alert is about, so a screen never tests strings itself.
ALL_GONE = "all_sources_gone"
UNREADABLE = "sources_unreadable"


def for_account(config_path, workspace_id, marketplace, now=None):
    """Every enrolled SKU that has nowhere to buy from, and every one we cannot tell.

    Returns {"alerts": [...], "unreadable": [...], "checked": n}. Never raises: it
    is asked by a banner on a screen and by a background job, and neither may fall
    over because one SKU is odd.
    """
    now = now or _dt.datetime.now()
    out = {"alerts": [], "unreadable": [], "checked": 0}
    try:
        rows = _repo.enrolled(config_path, workspace_id, marketplace)
    except Exception:
        return out

    for row in (rows or []):
        sku = str(row.get("sku") or "")
        if not sku:
            continue
        out["checked"] += 1
        try:
            rule = _repo.rule_for(config_path, row["workspace_id"],
                                 row["marketplace"], sku)
        except Exception:
            rule = None
        try:
            opts = _osrc.options_for(config_path, row["workspace_id"],
                                     row["marketplace"], sku, rule=rule, now=now)
        except Exception:
            continue
        summary = _osrc.summary(opts)
        if not summary.get("total"):
            # No suppliers at all. Not an alert -- see the module note.
            continue

        item = {
            "kind": None,
            "workspace_id": row["workspace_id"],
            "marketplace": row["marketplace"],
            "sku": sku,
            "sources": summary["total"],
            "dead": summary["dead"],
            "unknown": summary["unknown"],
            # WHEN IT WENT DARK, as far as the readings can say: the newest check
            # among the dead ones. Not "when we first noticed", which would need
            # the state this module deliberately does not keep.
            "since": max((o.get("checked_at") or "") for o in opts) or "",
            "urls": [o["url"] for o in opts][:8],
            "why": [(o.get("error") or ("out of stock" if o.get("in_stock") is False
                                        else o.get("status") or ""))
                    for o in opts][:8],
            # Whether the app is allowed to act on it. A SKU in dry_run has NOT
            # been taken out of stock on Amazon, so it is still selling something
            # nobody can buy -- which makes the alert more urgent, not less.
            "mode": row.get("mode") or "",
        }
        if summary.get("all_dead"):
            item["kind"] = ALL_GONE
            out["alerts"].append(item)
        elif not summary.get("buyable"):
            # Nothing buyable, but not everything is definitely dead either --
            # some readings failed. Real, and reported, but not an emergency.
            item["kind"] = UNREADABLE
            out["unreadable"].append(item)

    # Longest dark first: a SKU that went out yesterday needs attention before one
    # that went out ten minutes ago.
    out["alerts"].sort(key=lambda x: (x["since"], x["sku"]))
    out["unreadable"].sort(key=lambda x: (x["since"], x["sku"]))
    return out


def sentence(alert):
    """One line for a banner or a webhook. Says what to DO, not just what is wrong."""
    if not alert:
        return ""
    n = alert.get("sources") or 0
    if alert.get("kind") == ALL_GONE:
        return ("%s — all %d supplier%s out of stock or ended. Nothing can be "
                "bought to fulfil this. %s"
                % (alert.get("sku") or "?", n, "" if n == 1 else "s",
                   ("It is still live on Amazon: set the quantity to 0 or find "
                    "another supplier." if str(alert.get("mode")) == "dry_run"
                    else "The repricer will take it out of stock on the next run.")))
    return ("%s — none of its %d supplier%s could be read, so it is not known "
            "whether this can still be bought. Press Check in the Repricer."
            % (alert.get("sku") or "?", n, "" if n == 1 else "s"))
