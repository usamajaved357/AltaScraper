"""domain/activity_catalog.py -- which requests are meaningful work, and what they were.

The activity log (domain/activity.py) is fed from ONE place: an after-request
hook (routes/activity_routes.py) that asks this catalogue "was that request a
piece of work worth recording?". Every feature is covered without each one
keeping its own tracking, and a new write route is recorded by adding one line
here -- not by editing the feature.

WHAT IS RECORDED. Only the routes listed below, and only with the method listed
(writes, plus the few GETs that START work: /run/generate streams, so it is a
GET). Reads, polls, previews and dry runs are not listed, so they are never
recorded. A refused or failed attempt IS recorded, with ok=False.

WHAT A ROW HOLDS. The account(s) the request names -- read with the guard's own
readers (auth/guard.request_body_for_check + named_workspaces), so the log and
the permission check can never disagree about which account a request was for --
the marketplace, the entity (SKU, order, upload, campaign, user), how many things
it touched, the NAMES of the fields sent (never their values, except a short
allow-list), uploaded file NAMES (never content) and the error if it failed.
"""
from domain import activity as _act

W = ("POST", "PUT", "PATCH", "DELETE")
G = ("GET",)

# (methods, path, match, category, action, what it was -- a phrase, entity type)
# match: "=" exact path, "/" the path and anything under it.
CATALOG = [
    # ---- files uploaded (the upload history keeps the file itself) ----
    (W, "/input/upload",            "=", "files", "file.product_template", "Uploaded a product template", "upload"),
    (W, "/cogs/upload_sheet",       "=", "files", "file.cost_sheet", "Uploaded a product cost sheet", "upload"),
    (W, "/cogs/upload",             "=", "files", "file.cost_sheet", "Uploaded product costs", "upload"),
    (W, "/cogs/orders/upload",      "=", "files", "file.order_costs", "Uploaded an order cost sheet", "upload"),
    (W, "/tracking/upload",         "=", "files", "file.tracking", "Uploaded tracking numbers", "upload"),
    (W, "/sourcing/sources/upload", "=", "files", "file.supplier_links", "Uploaded supplier links", "upload"),
    (W, "/sourcing/minprice_upload", "=", "files", "file.min_prices", "Uploaded min prices", "upload"),
    (W, "/miles/upload",            "=", "files", "file.miles_items", "Uploaded a Miles item list", "upload"),
    (W, "/weekly/upload",           "=", "files", "file.weekly", "Uploaded a weekly report", "upload"),
    (W, "/returns/upload",          "=", "files", "file.returns", "Uploaded a returns report", "upload"),
    (W, "/ppc/report/upload",       "=", "files", "file.ppc_report", "Uploaded a PPC report", "upload"),
    (W, "/miles_template/upload",   "=", "files", "file.miles_template", "Uploaded a Miles template", "upload"),
    (W, "/returns/clear",           "=", "files", "file.returns_clear", "Cleared uploaded returns data", ""),
    (W, "/weekly/clear",            "=", "files", "file.weekly_clear", "Cleared uploaded weekly data", ""),

    # ---- listings and drafts ----
    (G, "/run/generate",            "=", "listings", "listing.generate", "Started generating drafts", "sku"),
    (G, "/run/regen",               "=", "listings", "listing.regenerate", "Started regenerating drafts", "sku"),
    (G, "/run/retry",               "=", "listings", "listing.retry", "Retried failed drafts", "sku"),
    (W, "/asin-studio/create-draft", "=", "listings", "listing.create", "Created a draft in ASIN Studio", "sku"),
    (W, "/seller/draft",            "=", "listings", "listing.create_from_seller", "Created drafts from a seller's catalogue", "sku"),
    (W, "/variant/queue",           "=", "listings", "listing.create_variant", "Queued a new variant", "sku"),
    (W, "/input/add",               "=", "listings", "listing.queue_add", "Added products to the queue", "sku"),
    (W, "/input/update",            "=", "listings", "listing.queue_update", "Changed a queued product", "sku"),
    (W, "/input/delete",            "=", "listings", "listing.queue_delete", "Removed a queued product", "sku"),
    (W, "/input/clear",             "=", "listings", "listing.queue_clear", "Cleared the queue", "sku"),
    (W, "/edit",                    "=", "listings", "listing.edit", "Edited a listing", "sku"),
    (W, "/approve",                 "=", "listings", "listing.status", "Changed a listing's approval status", "sku"),
    (W, "/delete",                  "=", "listings", "listing.delete", "Deleted a listing draft", "sku"),
    (W, "/rescan/apply",            "=", "listings", "listing.rescan_apply", "Applied a compliance rescan", "sku"),
    (W, "/autofix/start",           "=", "listings", "listing.autofix", "Started auto-fix", "sku"),
    (W, "/sync/pull/apply",         "=", "listings", "listing.sync_pull", "Pulled live listing data into drafts", "sku"),
    # /product_types/drafts is NOT listed: it only lists candidates when the Fix
    # product types dialog opens; the fixes themselves are /edit (re-review).
    (W, "/asin-studio/generate",    "=", "listings", "listing.copy_generate", "Generated listing copy in ASIN Studio", "sku"),

    # ---- images ----
    (W, "/genimage",                "=", "images", "image.generate", "Generated an image", "sku"),
    (W, "/genimage/secondary",      "=", "images", "image.generate", "Generated secondary images", "sku"),
    (W, "/genimage/start_batch",    "=", "images", "image.generate", "Generated images", "sku"),
    (W, "/genimage/from_concept",   "=", "images", "image.generate", "Generated an image from a concept", "sku"),
    (W, "/genimage/refine",         "=", "images", "image.refine", "Refined an image", "sku"),
    (W, "/genimage/secondary_v2",   "=", "images", "image.generate", "Generated secondary images", "sku"),
    (W, "/genimage/save_to_media",  "=", "images", "image.save", "Saved an image to the library", "sku"),
    (W, "/media/upload",            "=", "images", "image.upload", "Uploaded images", "sku"),
    (W, "/media/delete",            "=", "images", "image.delete", "Deleted an image", "sku"),

    # ---- sent to Amazon ----
    # /run/api and /run/api_verify are NOT listed: the Listings screen and the
    # auto-fix loop start them by themselves (autoverify.js on every load), so
    # counting them would credit a person with checks the app ran (change review).
    (G, "/run/api_submit",          "=", "amazon", "amazon.submit", "Submitted listings to Amazon", "sku"),
    # One product's Submit / Preview goes through the queue; the body's `mode`
    # says which (see _BODY_MODES), exactly as auth/guard BODY_RULES reads it.
    (W, "/preview/enqueue",         "=", "amazon", "amazon.preview", "Queued an Amazon preview", "sku"),
    (W, "/sync/push/confirm",       "=", "amazon", "amazon.push", "Pushed listing changes to Amazon", "sku"),
    (W, "/optimize/push",           "=", "amazon", "amazon.push_optimized", "Pushed optimised copy to Amazon", "sku"),
    (W, "/variations/apply",        "=", "amazon", "amazon.variations", "Applied a variation family on Amazon", "sku"),
    (W, "/listing/push_image",      "=", "amazon", "amazon.image_push", "Pushed an image to Amazon", "sku"),
    (W, "/listing/image_push",      "=", "amazon", "amazon.image_push", "Pushed images to Amazon", "sku"),

    # ---- price, stock and handling ----
    (W, "/listing/price/apply",     "=", "pricing", "price.set", "Changed a price", "sku"),
    (W, "/listing/price/percent_apply", "=", "pricing", "price.bulk", "Changed prices by a percentage", "sku"),
    (W, "/stock/bulk_update",       "=", "pricing", "stock.set", "Changed stock", "sku"),
    (W, "/handling/bulk_update",    "=", "pricing", "handling.set", "Changed handling time", "sku"),

    # ---- repricer and suppliers ----
    (W, "/sourcing/manual_price",   "=", "repricer", "repricer.manual_price", "Set a manual price", "sku"),
    (W, "/sourcing/arm",            "=", "repricer", "repricer.arm", "Armed the repricer", "sku"),
    (W, "/sourcing/apply",          "=", "repricer", "repricer.apply", "Applied repricer prices", "sku"),
    (W, "/sourcing/enrol",          "=", "repricer", "repricer.enrol", "Enrolled a product in the repricer", "sku"),
    (W, "/sourcing/enrol_bulk",     "=", "repricer", "repricer.enrol", "Enrolled products in the repricer", "sku"),
    (W, "/sourcing/unenrol_bulk",   "=", "repricer", "repricer.unenrol", "Removed products from the repricer", "sku"),
    (W, "/sourcing/rules",          "=", "repricer", "repricer.rules", "Changed repricer rules", ""),
    (W, "/sourcing/source",         "/", "repricer", "supplier.change", "Changed a supplier link", "sku"),
    (W, "/sourcing/sources/clear",  "=", "repricer", "supplier.clear", "Cleared supplier links", "sku"),

    # ---- PPC ----
    (W, "/ppc/build_campaigns",     "=", "ppc", "ppc.build", "Built PPC campaigns", "campaign"),
    (W, "/ppc/harvest",             "=", "ppc", "ppc.harvest", "Harvested search terms", "campaign"),
    (W, "/ppc/agent",               "=", "ppc", "ppc.agent", "Ran the PPC agent", "campaign"),
    (W, "/ppc/brand_terms",         "=", "ppc", "ppc.brand_terms", "Changed brand terms", ""),
    (W, "/drppc/run",               "=", "ppc", "ppc.drppc_run", "Ran Dr PPC", "campaign"),
    (W, "/drppc/console/settings",  "=", "ppc", "ppc.settings", "Changed Dr PPC settings", ""),
    (W, "/drppc/console/plan/activate", "=", "ppc", "ppc.plan_activate", "Activated a Dr PPC plan", "plan"),
    (W, "/drppc/console/plan",      "=", "ppc", "ppc.plan_save", "Saved a Dr PPC plan", "plan"),
    (W, "/drppc/console/rule/delete", "=", "ppc", "ppc.rule_delete", "Deleted a Dr PPC rule", "rule"),
    (W, "/drppc/console/rule",      "=", "ppc", "ppc.rule_add", "Added a Dr PPC rule", "rule"),
    # Campaign controls (30 Sep 2026): real changes on Amazon -- state, budget,
    # bid, negatives. domain/ppc_control also keeps its own before/after record.
    (W, "/ppc/control/change",      "=", "ppc", "ppc.control_change", "Changed a campaign on Amazon", "campaign"),
    (W, "/ppc/control/negative",    "=", "ppc", "ppc.control_negative", "Added a negative on Amazon", "campaign"),

    # ---- orders and tracking ----
    (W, "/tracking/set",            "=", "orders", "order.tracking_set", "Set tracking on an order", "order"),
    (W, "/tracking/refresh",        "=", "orders", "order.tracking_refresh", "Refreshed tracking", "order"),
    (W, "/returns/message",         "=", "orders", "order.return_message", "Messaged about a return", "order"),
    # A record that a PERSON bought it from the supplier; the app buys nothing.
    (W, "/orders/purchase/remove",  "=", "orders", "order.purchase_remove", "Removed a supplier-purchase record", "order"),
    (W, "/orders/purchase",         "=", "orders", "order.purchase", "Recorded buying an order from the supplier", "order"),
    # A real change on Amazon; /orders/ship/preview only reads and is not listed.
    (W, "/orders/ship/confirm",     "=", "amazon", "amazon.ship_confirm", "Confirmed an order as dispatched on Amazon", "order"),

    # ---- costs ----
    (W, "/cogs/set",                "=", "costs", "cost.set", "Set a product cost", "sku"),
    (W, "/cogs/clear",              "=", "costs", "cost.clear", "Cleared product costs", "sku"),
    (W, "/cogs/order",              "=", "costs", "cost.order", "Set an order's cost", "order"),
    (W, "/cogs/mode",               "=", "costs", "cost.mode", "Changed how costs are counted", ""),
    (W, "/cogs/refreeze",           "=", "costs", "cost.refreeze", "Re-froze order costs", "order"),
    (W, "/charges/save",            "=", "costs", "cost.charge_save", "Saved a per-product charge", "sku"),
    (W, "/charges/delete",          "=", "costs", "cost.charge_delete", "Deleted a per-product charge", "sku"),
    (W, "/expenses",                "/", "costs", "cost.expense", "Changed an expense", "expense"),

    # ---- inventory ----
    (W, "/inventory/build",         "=", "inventory", "inventory.build", "Built an inventory plan", ""),
    (W, "/inventory/v2/run",        "=", "inventory", "inventory.run", "Ran the inventory check", ""),

    # ---- team and accounts (names and roles only; credentials never stored) ----
    (W, "/users/create",            "=", "team", "team.user_create", "Added a team member", "user"),
    (W, "/users/invite",            "=", "team", "team.user_invite", "Sent a new invite link", "user"),
    (W, "/users/update",            "=", "team", "team.user_update", "Changed a team member", "user"),
    (W, "/users/delete",            "=", "team", "team.user_delete", "Removed a team member", "user"),
    (W, "/accounts/save",           "=", "team", "team.account_save", "Changed an account's settings", "account"),
    (W, "/accounts/delete",         "=", "team", "team.account_delete", "Removed an account", "account"),
    # An operator override of the open account's Amazon pull status (sync.js).
    (W, "/sync/mark_status",        "=", "team", "account.pull_status", "Overrode an account's pull status", ""),
    # Connection settings: field NAMES only; secret-named fields are dropped.
    (W, "/settings/ads",            "=", "team", "team.settings_ads", "Changed the Amazon Ads connection", ""),
    (W, "/settings/tracking",       "=", "team", "team.settings_tracking", "Changed the tracking connection", ""),
    (W, "/settings/ebay",           "=", "team", "team.settings_ebay", "Changed the eBay connection", ""),
    (W, "/settings/mailbox",        "=", "team", "team.settings_mailbox", "Changed the customer messages mailbox", ""),
]

# /preview/enqueue carries what it will do in its body -- the guard reads the
# same field (auth/guard BODY_RULES).
_BODY_MODES = {
    "/preview/enqueue": {
        "api_submit": ("amazon.submit", "Submitted a listing to Amazon"),
        "api_verify": ("amazon.verify", "Checked a listing with Amazon"),
    },
}

# Request fields that only say WHERE (account/marketplace/CSRF) -- not "what changed".
_SCOPE_FIELDS = {"account", "account_id", "workspace", "workspace_id", "ws", "id",
                 "marketplace", "marketplace_id", "mkt", "market", "csrf", "_csrf",
                 "csrf_token"}
# The only request VALUES ever stored: short, business, never secret.
_SAFE_VALUES = ("sku", "asin", "field", "target", "status", "mode", "kind", "type",
                "price", "new_price", "percent", "quantity", "qty", "stock",
                "handling_time", "days", "cost", "amount", "bid", "budget", "role",
                "action", "order_id", "amazon_order_id", "carrier", "email", "name")
_ENTITY_KEYS = {
    "sku": ("sku", "seller_sku", "skus", "asin"),
    "order": ("order_id", "amazon_order_id", "orders", "order_ids"),
    "user": ("id", "user_id", "email"),
    "account": ("id", "account", "account_id"),
    "campaign": ("campaign_id", "campaigns", "campaign"),
    "plan": ("plan_id", "id"),
    "rule": ("rule_id", "id"),
    "expense": ("id",),
    "upload": ("upload_id",),
}
_LIST_KEYS = ("skus", "asins", "rows", "items", "orders", "order_ids", "ids",
              "selected", "products", "campaigns", "updates", "changes")
_NESTED_FIELDS = ("updates", "fields", "changes", "attributes", "values")


def match(method, path):
    """The catalogue entry for this request, or None if it is not work."""
    m = str(method or "").upper()
    p = str(path or "")
    for methods, route, how, *rest in CATALOG:
        if m not in methods:
            continue
        if p == route or (how == "/" and p.startswith(route.rstrip("/") + "/")):
            return (route, how) + tuple(rest)
    return None


def edit_before_value(config_path, account, sku, target, key):
    """THE OLD VALUE of the field one /edit is about to change, or None.

    Read BEFORE the route runs (routes/activity_routes' before_request) with the
    same lookups /edit uses -- data.backend.store_for on the body's `account`
    (the store /edit writes; never the open one), listing.repo.locate and
    listing.repo.attributes_of -- so the record can say
    "item_name: 'Old' -> 'New'". Never raises; None when it cannot tell (no
    account named, no row yet, a secret-named field)."""
    try:
        if not account or not sku or not key or _act._is_secret_key(key):
            return None
        from data import backend as _be
        from listing import repo as _repo
        ws = _be.store_for(account, {}, config_path)
        if ws is None:
            return None
        found = _repo.locate(ws, sku)
        if not found.ok:
            return None
        headers = found.headers or []
        if target == "col":
            if key not in headers:
                return None
            return _repo.cell_value(ws, found.row, headers.index(key) + 1, default="")
        if target == "attr":
            if "Attributes JSON" not in headers:
                return None
            return _repo.attributes_of(ws, found.row, headers).get(key, "")
    except Exception:
        return None
    return None


def _first_list(body):
    for k in _LIST_KEYS:
        v = (body or {}).get(k)
        if isinstance(v, list) and v:
            return k, v
    return None, None


def _entity_ids(entity_type, body, args):
    """(the ids the request names for its entity, how many things). Bodies
    first, then the query string. The ids are [] when only a count is known
    (a list under some other key); the count is None when nothing is named."""
    keys = _ENTITY_KEYS.get(entity_type, ())
    for src in (body or {}, args or {}):
        for k in keys:
            if k == "id" and entity_type not in ("user", "account", "plan", "rule", "expense"):
                continue
            try:
                v = src.get(k)
            except Exception:
                v = None
            if isinstance(v, list):
                if v:
                    # Ids only when the list IS ids (not rows of objects).
                    plain = all(isinstance(x, (str, int)) and str(x).strip() for x in v)
                    return ([str(x)[:200] for x in v] if plain else []), len(v)
            elif isinstance(v, (str, int)) and str(v).strip():
                s = str(v).strip()
                if "," in s and k in ("skus", "orders", "order_ids"):
                    parts = [x for x in s.split(",") if x.strip()]
                    return parts, len(parts)
                return [s[:200]], 1
    _k, lst = _first_list(body)
    if lst:
        return [], len(lst)
    return [], None


def _entity(entity_type, path, body, args):
    """(entity id or "", how many things, every id named): the id only when
    exactly one is named."""
    ids, count = _entity_ids(entity_type, body, args)
    return (ids[0] if count == 1 and len(ids) == 1 else ""), count, ids


MAX_BATCH_ROWS = 1000


def rows(method, path, body, args, files, response, before=None):
    """The log rows for one catalogued request: [] if it is not work, else
    describe()'s one row -- or, for a BATCH that names its products (a SKU
    list), ONE ROW PER PRODUCT.

    Owner, 30 Sep 2026: "When a batch submission contains multiple
    products/listings, record each product separately in employee activity"
    -- so a 20-product batch is 20 products of work, and "changed after
    sending" finds each by its own SKU. Each row carries the same
    detail.batch_id and batch_size. The reply is one outcome for the whole
    batch (a streamed run), so its ok/failed applies to every row. A refusal
    stays ONE row: nothing was attempted. Past MAX_BATCH_ROWS the rest are
    counted on the last row (detail.batch_overflow)."""
    d, ids = _describe(method, path, body, args, files, response, before)
    if not d:
        return []
    if (d.get("entity_type") != "sku" or len(ids) < 2
            or (d.get("detail") or {}).get("refused")):
        return [d]
    import uuid
    skus = [str(x).strip() for x in ids if str(x).strip()]
    kept = skus[:MAX_BATCH_ROWS]
    batch_id = uuid.uuid4().hex[:12]
    base = (d.get("detail") or {})
    out = []
    for i, sku in enumerate(kept):
        det = dict(base, batch_id=batch_id, batch_size=len(skus))
        if i == len(kept) - 1 and len(skus) > len(kept):
            det["batch_overflow"] = len(skus) - len(kept)
        out.append(dict(d, entity_id=sku[:200], entity_count=1, detail=det,
                        summary=_batch_summary(d["summary"], sku, len(skus))))
    return out


def _batch_summary(summary, sku, size):
    """describe()'s sentence for one product of a batch: the "(N)" count
    becomes the product and "one of N"."""
    tail = " (%d)" % size
    head, sep, rest = summary.partition(tail)
    if not sep:
        return "%s %s (one of %d)" % (summary, sku, size)
    return "%s %s (one of %d)%s" % (head, sku, size, rest)


def _fields(body):
    """The NAMES of what was sent (minus scope and secret names)."""
    if not isinstance(body, dict):
        return []
    names = [k for k in body if k not in _SCOPE_FIELDS and not _act._is_secret_key(k)]
    for nk in _NESTED_FIELDS:
        v = body.get(nk)
        if isinstance(v, dict):
            names += ["%s.%s" % (nk, k) for k in v if not _act._is_secret_key(k)]
    return sorted(set(str(n)[:60] for n in names))[:40]


def _values(body):
    out = {}
    if not isinstance(body, dict):
        return out
    for k in _SAFE_VALUES:
        v = body.get(k)
        if isinstance(v, (str, int, float, bool)) and str(v) != "":
            out[k] = v
    return out


def _outcome(response):
    """(ok, http status, error text) from the reply, reading its body only when
    it is a small, finished JSON or event-stream reply."""
    status = int(getattr(response, "status_code", 200) or 200)
    ok, err = status < 400, ""
    try:
        if getattr(response, "is_streamed", False) or getattr(response, "direct_passthrough", False):
            return ok, status, err
        length = response.calculate_content_length()
        if length is None or length > 256 * 1024:
            return ok, status, err
        mt = str(getattr(response, "mimetype", "") or "")
        if mt == "application/json":
            j = response.get_json(silent=True)
            if isinstance(j, dict):
                if j.get("ok") is False:
                    ok = False
                if not ok:
                    err = str(j.get("error") or j.get("message") or "")
        elif mt == "text/event-stream":
            text = response.get_data(as_text=True)
            if text.startswith("data: [error]"):
                ok = False
                err = text[len("data: [error]"):].split("\n", 1)[0].strip()
    except Exception:
        pass
    return ok, status, err[:300]


def describe(method, path, body, args, files, response, before=None):
    """Everything the log needs about one catalogued request, or None."""
    return _describe(method, path, body, args, files, response, before)[0]


def _describe(method, path, body, args, files, response, before=None):
    """(describe()'s row or None, every entity id the request named)."""
    hit = match(method, path)
    if not hit:
        return None, []
    _route, _how, category, action, phrase, etype = hit
    modes = _BODY_MODES.get(_route)
    if modes and isinstance(body, dict):
        action, phrase = modes.get(str(body.get("mode") or ""), (action, phrase))
    from auth import guard as _g
    accounts = _g.named_workspaces(path, args, body)
    mkt = ""
    for src in (body or {}, args or {}):
        for k in ("marketplace", "marketplace_id", "mkt", "market"):
            try:
                v = src.get(k)
            except Exception:
                v = None
            if isinstance(v, str) and v.strip():
                mkt = v.strip()
                break
        if mkt:
            break
    eid, count, ids = _entity(etype, path, body, args)
    detail = {}
    flds = _fields(body)
    if flds:
        detail["fields"] = flds
    vals = _values(body)
    if path == "/edit" and isinstance(body, dict):
        # /edit sends {sku, key, value}: `key` is the FIELD NAME. The new value
        # is listing content (title, bullet, price...), kept short. The OLD
        # value was read before the route ran (edit_before_value) and is added
        # below only if the edit worked -- a refused edit changed nothing.
        if body.get("key"):
            vals["field"] = str(body.get("key"))[:60]
            v = body.get("value")
            if isinstance(v, (str, int, float, bool)) and not _act._is_secret_key(body.get("key")):
                vals["new_value"] = v
    if vals:
        detail["values"] = vals
    names = []
    try:
        for f in (files.getlist(k) for k in files.keys()) if files else []:
            names += [str(getattr(x, "filename", "") or "") for x in f]
    except Exception:
        names = []
    names = [n for n in names if n]
    if names:
        detail["files"] = names[:20]
        if count is None:
            count = len(names)
    # SEVERAL ACCOUNTS IN ONE REQUEST: filed under none of them (only a viewer
    # of every account sees it), because routes read the account fields in
    # different orders and the first one named may not be the one acted on.
    # The other accounts' ids are not stored.
    if len(accounts) > 1:
        detail["accounts_named"] = len(accounts)
    ok, status, err = _outcome(response)
    if err:
        detail["error"] = err
    if (ok and path == "/edit" and "new_value" in vals
            and isinstance(before, (str, int, float, bool))):
        vals["old_value"] = before
        detail["values"] = vals
    summary = phrase
    if eid:
        summary += " " + eid
    if count and count > 1:
        summary += " (%d)" % count
    # REFUSED IS NOT FAILED. The doorman's 403 comes back before the route ran:
    # nothing was attempted, so it is worded as a refusal, not as work that
    # went wrong (change review).
    if status == 403:
        detail["refused"] = True
        summary = "Refused: " + summary[0].lower() + summary[1:] + (" -- " + err[:160] if err else "")
    elif not ok:
        summary += " -- failed" + (": " + err[:160] if err else "")
    return {"category": category, "action": action, "ok": ok, "http_status": status,
            "workspace_id": accounts[0] if len(accounts) == 1 else "", "marketplace": mkt,
            "entity_type": etype, "entity_id": eid, "entity_count": count,
            "summary": summary, "detail": detail}, ids
