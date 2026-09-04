"""domain/schema_cache.py -- Amazon's field definitions, kept between restarts.

THE PROBLEM THIS SOLVES

Every product type has a schema: which fields Amazon requires, what values each
one allows, which nested sub-fields exist. The app needs it to draw the edit
drawer's dropdowns, to validate before submitting, and to know which image slots
a listing has.

Fetching one is slow and expensive. It is two calls to Amazon -- getDefinitions
for a link, then a download of the schema document itself from a CDN -- and from
Pakistan that download regularly needs retries. Measured on the live app: 42
distinct product types on one account, seconds each.

They were cached in `_state["schemas"]`, an ordinary dict in the Flask process.
That is lost the moment the process restarts, which on Render is every deploy
and every idle spin-down. So after each deploy the app re-fetched all 42 from
Amazon, and the owner saw:

    "why do we need to fetch schema everytime the page loads, can't we do it
     one time and again when needed and use cache"

Exactly right. The definitions barely change -- Amazon revises a product type
occasionally, not daily -- so keeping them on disk means a restart costs nothing
and the quota is spent on the figures people are waiting for instead.

WHAT IS AND IS NOT DECIDED HERE

This module only stores and retrieves. It never calls Amazon: the caller passes
in a `fetch` function, so the one place that knows how to talk to the Product
Type Definitions API stays where it already is, and this stays testable without
credentials.

WHY A SCHEMA IS NEVER KEPT FOREVER

Two reasons to go back to Amazon:

  the copy is old        Amazon does revise definitions -- a new required field
                         appears, an enum gains a value -- and a listing
                         validated against a stale schema fails at submission
                         with a message about a field the app never showed.

  it was asked for       "Reload Amazon values now" in the edit drawer exists
                         precisely because someone believes the copy is wrong.
                         A refresh that quietly returned the cached copy would
                         be worse than no button at all.

An EMPTY schema is never stored. A failed fetch produces {} and writing that
would cache the failure -- the drawer would then show no dropdowns at all until
the entry expired, and nothing on screen would say why.
"""
import json as _json
import datetime as _dt

from data import db as _db

# How long a stored copy is trusted. Fourteen days is comfortably shorter than
# Amazon's own revision rhythm and long enough that a busy week never refetches.
TTL_DAYS = 14

# What "the schema is really there" means. A fetch that failed comes back as an
# empty shell -- all the keys, nothing in them -- and that must not be stored as
# though it were an answer.
_SUBSTANCE = ("attrs", "enums", "required", "subfields")

# EVERY KEY A CURRENT SCHEMA CARRIES.
#
# A CACHE THAT PREDATES A FIELD IS A CACHE THAT HIDES IT. Three things were
# added to what _load_schema keeps -- `help` (Amazon's own description, for the
# (?) bubble), `maxitems` (how many values a field takes, which decides whether
# a field gets Add More) and `readonly` (fields Amazon refuses to let anyone
# set, which get a padlock). Ninety-eight schemas were already stored WITHOUT
# them, and a stored copy is trusted for a fortnight -- so on those product
# types all three features would have quietly done nothing, with no error and
# nothing on screen to say why. Whether a cached copy is USABLE is this
# module's job, so the check belongs here and not in the caller.
#
# A copy missing any of these is treated as a miss: it is re-fetched once, and
# the fresh answer replaces it. Nothing is deleted -- a fetch that fails still
# falls back to the old copy (see `get`), because an out-of-date help string is
# better than an empty drawer.
_SHAPE = ("enums", "required", "attrs", "subfields", "titles",
          "help", "maxitems", "readonly")


def is_current_shape(info):
    """Does this stored copy carry every key the app now reads?"""
    return isinstance(info, dict) and all(k in info for k in _SHAPE)


def _now():
    return _dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def has_substance(info):
    """Is this a real schema, or the empty shell a failed fetch returns?"""
    if not isinstance(info, dict):
        return False
    if info.get("_error"):
        return False
    return any(info.get(k) for k in _SUBSTANCE)


def _age_days(stamp):
    try:
        then = _dt.datetime.strptime(str(stamp)[:19], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None                      # unreadable stamp -> treat as unknown
    return (_dt.datetime.utcnow() - then).total_seconds() / 86400.0


def read(config_path, product_type, marketplace, max_age_days=TTL_DAYS,
         require_current=True):
    """The stored schema, or None if there is not a usable one.

    None covers all four of "never fetched", "too old to trust", "stored copy
    is unreadable" and "stored copy predates a field the app now reads" -- the
    caller does the same thing for each: go and ask Amazon.

    `require_current=False` accepts an older shape. Only the stale fallback in
    get() uses it: when Amazon will not answer at all, yesterday's schema
    without its help text is still worth far more than nothing.
    """
    if not product_type:
        return None
    try:
        row = _db.get_db(config_path).execute(
            "SELECT payload, fetched_at FROM schema_cache "
            "WHERE product_type=? AND marketplace=?",
            (str(product_type), str(marketplace or "").upper())).fetchone()
    except Exception:
        return None                      # a cache must never break the app
    if not row:
        return None
    age = _age_days(row["fetched_at"])
    if age is None or age > float(max_age_days):
        return None
    try:
        info = _json.loads(row["payload"])
    except Exception:
        return None
    if not has_substance(info):
        return None
    if require_current and not is_current_shape(info):
        return None
    return info


def write(config_path, product_type, marketplace, info):
    """Store one schema. Refuses to store an empty one -- see the note above."""
    if not product_type or not has_substance(info):
        return False
    try:
        conn = _db.get_db(config_path)
        conn.execute(
            "INSERT INTO schema_cache (product_type, marketplace, payload, fetched_at) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(product_type, marketplace) DO UPDATE SET "
            "  payload=excluded.payload, fetched_at=excluded.fetched_at",
            (str(product_type), str(marketplace or "").upper(),
             _json.dumps(info), _now()))
        conn.commit()
        return True
    except Exception:
        return False


def get(config_path, product_type, marketplace, fetch, force=False,
        max_age_days=TTL_DAYS):
    """The schema for one product type: from store if we have it, else fetched.

    `fetch` is called with no arguments and must return the parsed schema. It is
    passed in rather than imported so that the one place that knows how to talk
    to Amazon stays where it is, and so this can be tested without credentials.

    `force` skips the stored copy and overwrites it -- what "Reload Amazon
    values now" means.
    """
    if not force:
        hit = read(config_path, product_type, marketplace, max_age_days)
        if hit is not None:
            return hit, "stored"
    info = fetch()
    # A FAILED FETCH FALLS BACK TO WHAT WE HAD.
    #
    # Amazon refusing us today does not make yesterday's definition wrong, and
    # an empty schema is not a neutral outcome -- it empties every dropdown in
    # the edit drawer and hides required fields, which looks like the product
    # type has no fields rather than like a failed call.
    if not has_substance(info):
        stale = read(config_path, product_type, marketplace, max_age_days=36500,
                     require_current=False)
        if stale is not None:
            return stale, "stale"
        return info, "failed"
    write(config_path, product_type, marketplace, info)
    return info, "fetched"


def stats(config_path):
    """What is stored, for /diag. Never raises."""
    try:
        conn = _db.get_db(config_path)
        n = conn.execute("SELECT COUNT(*) FROM schema_cache").fetchone()[0]
        oldest = conn.execute(
            "SELECT MIN(fetched_at) FROM schema_cache").fetchone()[0] or ""
        by_mkt = {r[0]: r[1] for r in conn.execute(
            "SELECT marketplace, COUNT(*) FROM schema_cache GROUP BY marketplace")}
        return {"count": n, "oldest": oldest, "by_marketplace": by_mkt,
                "ttl_days": TTL_DAYS}
    except Exception as e:
        return {"count": 0, "error": str(e)[:150]}


def forget(config_path, product_type=None, marketplace=None):
    """Drop stored schemas. With no arguments, all of them."""
    try:
        conn = _db.get_db(config_path)
        if product_type:
            conn.execute(
                "DELETE FROM schema_cache WHERE product_type=?"
                + (" AND marketplace=?" if marketplace else ""),
                ((str(product_type), str(marketplace).upper())
                 if marketplace else (str(product_type),)))
        else:
            conn.execute("DELETE FROM schema_cache")
        conn.commit()
        return True
    except Exception:
        return False
