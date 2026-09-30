"""domain/miles_history.py -- which Supplier Import (Miles) item numbers an
ACCOUNT has already harvested. Every account has its own; none is shared.

WHY THIS EXISTS (30 Sep 2026)
The history used to be one file for the whole server, miles_harvested.json
beside config.json (dashboard.py _miles_load_history / _miles_save_history).
It is keyed by supplier item number, not account, so one account's harvest
made every other account's upload report those items as "already harvested",
and "Clear harvested history" on one account wiped it for all of them.
Owner decision, 30 Sep 2026: the history for Account A must never be shared
with Account B, and clearing clears only the current account's.

WHERE IT LIVES NOW
One file per account, beside config.json (Render's persistent disk):
    miles_accounts/<account id>/miles_harvested.json
The basename is unchanged on purpose: .gitignore already ignores
"miles_harvested.json" at any depth, so none of these files can be committed.

MIGRATION OF THE OLD SHARED FILE (runs once, the first time any account's
history is touched after the upgrade)
The old entries record no account. Each one is given to an account ONLY where
there is evidence that account harvested it: a saved Supplier Import run
(miles_runs/<id>.json) that names the account and marks the item "harvested"
or "generated". An item with such evidence in two accounts goes to both.
Everything with no evidence goes to
    miles_accounts/_unattributed/miles_harvested.json
which NO account reads -- it is kept so nothing is destroyed, never used to
skip anything. The old file itself is moved, unchanged, to
    miles_accounts/_legacy_original/miles_harvested.json
so the migration cannot run twice. If any write fails the old file is left
where it is and the migration is tried again next time.

With no account named nothing is read (an empty history), nothing is saved and
clear() refuses: there is no shared history any more to fall back to.
"""
import glob
import hashlib
import json
import os
import re
import threading

from domain import jsonstore as _jsonstore

LEGACY_FILE = "miles_harvested.json"
ACCOUNTS_DIR = "miles_accounts"
UNATTRIBUTED = "_unattributed"
LEGACY_ORIGINAL = "_legacy_original"
# A run's per-item status that shows the account really had this item harvested.
EVIDENCE_STATUSES = ("harvested", "generated")

_SAFE_RE = re.compile(r"^[A-Za-z0-9.-][A-Za-z0-9._-]{0,79}$")
_MIGRATE_LOCK = threading.Lock()


def _base_dir(config_path):
    return os.path.dirname(os.path.abspath(str(config_path)))


def _folder_name(account_id):
    """A directory name for the account that cannot leave miles_accounts/ and
    cannot collide with the reserved _unattributed / _legacy_original folders
    (a leading underscore is never used for an account)."""
    a = str(account_id or "").strip()
    if not a:
        return ""
    if _SAFE_RE.match(a) and a not in (".", "..") and ".." not in a:
        return a
    return "h" + hashlib.sha1(a.encode("utf-8")).hexdigest()[:16]


def legacy_path(config_path):
    """The old server-wide history file (read only by the migration)."""
    return os.path.join(_base_dir(config_path), LEGACY_FILE)


def _reserved_path(config_path, folder):
    return os.path.join(_base_dir(config_path), ACCOUNTS_DIR, folder, LEGACY_FILE)


def unattributed_path(config_path):
    return _reserved_path(config_path, UNATTRIBUTED)


def account_path(config_path, account_id):
    """This account's own history file ("" when no account is named)."""
    name = _folder_name(account_id)
    if not name:
        return ""
    return os.path.join(_base_dir(config_path), ACCOUNTS_DIR, name, LEGACY_FILE)


def _as_set(data):
    if not isinstance(data, list):
        return None
    return {str(x) for x in data if str(x).strip()}


def _read_set(path):
    return _as_set(_jsonstore.read_json(path, None)) or set()


# ---- migration of the old shared file ---------------------------------------

def _run_evidence(config_path):
    """{account id: {item numbers}} from saved runs that name their account."""
    out = {}
    for f in glob.glob(os.path.join(_base_dir(config_path), "miles_runs", "*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                meta = json.load(fh)
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        acct = str(meta.get("account") or "").strip()
        skus = meta.get("skus")
        if not acct or not isinstance(skus, dict):
            continue
        for item, st in skus.items():
            if isinstance(st, dict) and st.get("status") in EVIDENCE_STATUSES:
                out.setdefault(acct, set()).add(str(item))
    return out


def plan_migration(config_path):
    """What the migration would do, WITHOUT writing anything:
    {"legacy": n, "attributed": {account: n}, "attributed_items": n,
     "unattributed": n}. Counts only."""
    old = _read_set(legacy_path(config_path)) if os.path.exists(legacy_path(config_path)) else set()
    ev = _run_evidence(config_path)
    per = {a: sorted(old & items) for a, items in ev.items() if old & items}
    got = set()
    for items in per.values():
        got.update(items)
    return {"legacy": len(old), "attributed": {a: len(v) for a, v in per.items()},
            "attributed_items": len(got), "unattributed": len(old - got),
            "_per": per, "_rest": sorted(old - got), "_old": old}


def migrate(config_path):
    """Split the old shared file by evidence (see the module docstring). Safe
    to call any number of times; does nothing once the old file is gone.
    Returns the counts from plan_migration (without item numbers) or None."""
    lp = legacy_path(config_path)
    if not os.path.exists(lp):
        return None
    with _MIGRATE_LOCK:
        if not os.path.exists(lp):
            return None
        plan = plan_migration(config_path)
        ok = True
        for acct, items in plan["_per"].items():
            p = account_path(config_path, acct)
            ok = ok and _jsonstore.write_json_atomic(p, sorted(_read_set(p) | set(items)))
        up = unattributed_path(config_path)
        ok = ok and _jsonstore.write_json_atomic(up, sorted(_read_set(up) | set(plan["_rest"])))
        op = _reserved_path(config_path, LEGACY_ORIGINAL)
        ok = ok and _jsonstore.write_json_atomic(op, sorted(_read_set(op) | plan["_old"]))
        if not ok:
            return None                     # old file kept; tried again next time
        try:
            os.remove(lp)
        except Exception:
            return None
        counts = {k: v for k, v in plan.items() if not k.startswith("_")}
        # Counts only (no item numbers) in the server log, for the owner's review.
        print("[miles_history] split the old shared history: %d entries, %d attributed "
              "by run evidence (%s), %d unattributed (kept apart, read by no account)"
              % (counts["legacy"], counts["attributed_items"],
                 ", ".join("%s=%d" % kv for kv in sorted(counts["attributed"].items())) or "none",
                 counts["unattributed"]), flush=True)
        return counts


# ---- the per-account history ---------------------------------------------------

def load(config_path, account_id) -> set:
    """The item numbers THIS account has harvested. Never another account's,
    never the unattributed leftovers."""
    p = account_path(config_path, account_id)
    if not p:
        return set()
    migrate(config_path)
    return _read_set(p)


def save(config_path, account_id, done) -> bool:
    """Replace this account's history with `done`. True if it was written;
    False (nothing written) when no account is named."""
    p = account_path(config_path, account_id)
    if not p:
        return False
    migrate(config_path)
    return _jsonstore.write_json_atomic(p, sorted(str(x) for x in (done or ())))


def clear(config_path, account_id):
    """Forget this account's history only. Returns how many item numbers it
    held, or None when no account is named or the write failed (then nothing
    was changed)."""
    if not account_path(config_path, account_id):
        return None
    n = len(load(config_path, account_id))
    if not save(config_path, account_id, set()):
        return None
    return n
