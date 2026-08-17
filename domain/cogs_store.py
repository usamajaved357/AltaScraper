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


def set_cost(config_path, account_id, sku, cost):
    """Set or clear one SKU's cost. `cost` None or "" clears it.

    Returns (stored_or_None, ok). A value that is not a number is refused rather
    than stored as text, because every reader calls float() on it and would then
    fall back to "no cost known" for a cost that was typed and accepted.
    """
    load(config_path)
    k = key(account_id, sku)
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
