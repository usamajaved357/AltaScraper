"""domain/cogs_store.py -- the manual cost overrides, owned in ONE place.

WHY THIS EXISTS, AND THE BUG IT FIXES.

The overrides lived in dashboard.py as a module-level dict, and other modules
reached them with `import dashboard as _d; getattr(_d, "_COGS_OVERRIDE")`.

dashboard.py is the file that is RUN, so its module name is "__main__".
`import dashboard` therefore does not find the running module -- it loads the
file a SECOND time, as a separate module object, with its own
`_COGS_OVERRIDE = {}`. Nothing ever fills that copy: `_load_cogs_overrides()`
is called from main(), which the duplicate never runs.

So every consumer that reached for it that way read a permanently empty dict.
MEASURED on jack_uk: a cost typed on the listings screen reached the Repricer and
the cost sheet, and did NOT reach the Sales page's cost coverage (46 known
before, 46 after -- when the same call in-process gives 47). routes/sales_routes
and routes/orders_routes both did it this way, so the Sales figures and the
Orders profit column ignored every manual cost that had ever been set.

Reported as: "i am concirned that after putting the cogs in the listngs section
for an item will reflect right data about profits and all wherever cogs have a
roll." It did not, and this is why.

THE RULE NOW: nobody imports dashboard for this. Everybody imports this module.
The dict is created once here and NEVER REBOUND -- loading mutates it in place --
so a reference handed out at startup stays correct for the life of the process,
which is the other half of the same bug.

This module holds the STORE. domain/cogs.py holds the RULES -- which cost wins,
and how one is read out of a SKU name. They are deliberately separate: one is
about where a number is kept, the other about which number is true.
"""
import json
import os
import threading

# The one dict. Mutated, never replaced -- see the module docstring.
_OVERRIDES = {}
_LOADED_FROM = ""
_LOCK = threading.Lock()


def path_for(config_path):
    """Where the overrides live: beside config.json, as cogs_overrides.json."""
    base = os.path.dirname(os.path.abspath(str(config_path or "config.json")))
    return os.path.join(base, "cogs_overrides.json")


def key(account_id, sku):
    """The one key shape: "<account>::<SKU>". Everything agrees on this."""
    return "%s::%s" % (str(account_id or ""), str(sku or ""))


def norm(sku):
    """A SKU folded to the form used for MATCHING only. Never for storing.

    AMAZON SPELLS THE SAME SKU TWO WAYS, and both are its own answer:

        Orders API    10.99_3Days_B0GGSNN4Q6
        Finances API  10.99_3DAYS_B0GGSNN4Q6

    Same product, same listing, one seller. Measured on nestwell_goods the day
    the Finances role was granted: the finance sync reported three SKUs as
    unmapped -- 10.99_3DAYS_B0GGSNN4Q6, 15.09_3DAYS_B0F7D29MFZ,
    6.89_2DAYS_B0GY4MTGKD -- while costs for all three were sitting in the store
    under the mixed-case spelling. Cost of goods came back 0.0% covered on an
    account that is fully costed, so every one of those orders would have shown
    its profit as unknown.

    This was always latent. It never showed because resolve() used to fall back
    to reading the number out of the SKU name, and that parse takes the leading
    number and never looks at the rest, so "3DAYS" and "3Days" gave the same
    answer by accident. Removing that fallback -- the right change -- took the
    accident away and left the flaw showing.

    Case and surrounding space only. NOT punctuation, NOT internal spaces: a SKU
    is an identifier the seller chose, and "grill-large" and "grill large" are
    entitled to be two different products.
    """
    return str(sku or "").strip().upper()


def find(overrides, account_id, sku):
    """The stored cost for one SKU: (value, matched_key), else (None, "").

    Exact first, so nothing about the normal path changes or slows. Only a MISS
    pays for the fold, and only then does it scan -- the store holds tens of
    costs, not thousands, so a scan on the way to "no cost known" is free.

    Takes the dict rather than reading the module's own, because resolve() is
    handed an overrides dict by its callers and the finance parser carries one
    across a whole sync. One matcher either way (Rule 12).
    """
    if not overrides:
        return None, ""
    k = key(account_id, sku)
    if k in overrides:
        return overrides[k], k
    want = "%s::%s" % (str(account_id or ""), norm(sku))
    if not norm(sku):
        return None, ""
    for other in overrides:
        s = str(other)
        if "::" not in s:
            continue
        acct, _, other_sku = s.partition("::")
        if "%s::%s" % (acct, norm(other_sku)) == want:
            return overrides[other], s
    return None, ""


def load(config_path, force=False):
    """Read the file into the dict, in place. Safe to call more than once.

    IN PLACE, not by assignment: something registered at startup is holding this
    dict, and rebinding the name here would leave it pointing at the old one --
    which is half of the bug in the docstring above.
    """
    global _LOADED_FROM
    p = path_for(config_path)
    with _LOCK:
        if _LOADED_FROM == p and not force:
            return _OVERRIDES
        got = {}
        try:
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    got = json.load(f) or {}
        except Exception:
            got = {}                # a corrupt file must not stop the app
        if isinstance(got, dict):
            _OVERRIDES.clear()
            _OVERRIDES.update({str(k): v for k, v in got.items()})
        _LOADED_FROM = p
    return _OVERRIDES


def all_overrides(config_path=None):
    """The live dict. Loaded on first ask when a config path is given."""
    if config_path and _LOADED_FROM != path_for(config_path):
        load(config_path)
    return _OVERRIDES


def save(config_path):
    """Write the dict out. Never raises: a failed save must not lose the edit."""
    p = path_for(config_path)
    try:
        with _LOCK:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(_OVERRIDES, f, indent=2)
        return True
    except Exception:
        return False


def count_for(config_path, account_id):
    """How many costs are stored for one account. Reads nothing else.

    Separate from clear_account() on purpose: the confirmation has to say a real
    number BEFORE anything is deleted, and a count produced by the same reader
    that will do the deleting cannot disagree with it. "Delete 47 costs?" is only
    worth asking if the 47 is the 47 that will go.
    """
    load(config_path)
    pre = key(account_id, "")
    with _LOCK:
        return sum(1 for k in _OVERRIDES if str(k).startswith(pre))


def clear_account(config_path, account_id):
    """Delete every manually-set cost for ONE account. Returns how many went.

    SCOPED TO THE ACCOUNT, and that is the whole care in this function. The keys
    are "<account>::<SKU>" in one flat dict shared by every workspace, so a
    careless clear() here would wipe Nestwell's costs while Jack's screen was
    open. The prefix is built with key(account_id, "") rather than by string
    concatenation, so it can only ever mean what every other reader means by it.

    An empty account_id would give the prefix "::" and match nothing, which is
    the safe direction: better to delete none than all. It is refused outright
    rather than relied on.

    IN PLACE, never rebinding -- see the module docstring. Something registered
    at startup is holding this dict.
    """
    aid = str(account_id or "").strip()
    if not aid:
        return 0
    load(config_path)
    pre = key(aid, "")
    with _LOCK:
        doomed = [k for k in _OVERRIDES if str(k).startswith(pre)]
        for k in doomed:
            _OVERRIDES.pop(k, None)
    if doomed:
        save(config_path)
    return len(doomed)


def set_cost(config_path, account_id, sku, cost):
    """Set or clear one SKU's cost. `cost` None or "" clears it.

    Returns (stored_or_None, ok). A value that is not a number is refused rather
    than stored as text, because every reader calls float() on it and would then
    fall back to "no cost known" for a cost that was typed and accepted.
    """
    load(config_path)
    k = key(account_id, sku)
    # ONE ENTRY PER SKU, WHATEVER CASE IT ARRIVES IN. Amazon hands the same SKU
    # back in two spellings (see norm()), so a cost typed against one and then
    # cleared against the other would leave the first still standing -- a cost
    # the owner believes they deleted, still quietly pricing their orders. If a
    # cost is already stored under another spelling, that is the row we edit.
    if k not in _OVERRIDES:
        _got, _k = find(_OVERRIDES, account_id, sku)
        if _k:
            k = _k
    if cost in (None, "", "null"):
        with _LOCK:
            _OVERRIDES.pop(k, None)
        return None, save(config_path)
    try:
        v = float(cost)
    except (TypeError, ValueError):
        return None, False
    if v < 0:
        return None, False
    with _LOCK:
        _OVERRIDES[k] = v
    return v, save(config_path)
