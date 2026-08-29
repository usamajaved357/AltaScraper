"""auth/guard.py -- which request needs which permission, decided in ONE place.

PLAIN ENGLISH
Hiding a button in the browser is not security. Anyone can open the browser
console and call /submit or /delete directly, whatever the screen shows them. So
permission is checked on the server, on every single request, before the app
does anything. This file is that check, and it is the only copy of it.

HOW IT DECIDES
An ordered table of URL prefixes, first match wins, most specific first:

  * a rule mapping to a permission -> the user must hold that permission
  * a rule mapping to None         -> any signed-in user may do it (reads,
                                      diagnostics, and the handful of screens
                                      everyone needs to get started)

Anything NOT in the table:

  * GET / HEAD / OPTIONS -> allowed. These read; anyone with an account may look.
  * anything else        -> requires "edit". This is the important half: a route
                            I forgot to list still fails closed for a viewer
                            rather than silently being wide open. New routes
                            added later inherit that protection automatically.

WHY A TABLE AND NOT A DECORATOR ON EVERY ROUTE
There are around 200 routes across 30 files. A decorator per route means 200
chances to forget one, and no single place to read the policy. Here the whole
policy is forty lines you can audit in one sitting.
"""
from flask import jsonify, redirect, request, session, url_for

from auth import users

# Reachable without being signed in at all.
#
# oauth_login / oauth_callback are here because the person using them is a
# SELLER AUTHORIZING US, who has no account on this app and never will -- that
# is the entire point of multi-tenant OAuth. Requiring a sign-in would make the
# flow impossible rather than secure.
#
# What protects them instead is the state nonce: /auth/login issues one into
# the caller's own session and /auth/callback requires it back unchanged and
# unexpired, so a callback that did not begin here is refused and nothing is
# stored. That is the control that matters here, because the risk is not
# "somebody reads a page" -- it is "somebody gets this app to attach a token to
# an account of their choosing", and a login wall would not have stopped that
# on its own. See routes/auth_oauth_routes.py.
#
# privacy_page / terms_page are public for the same reason and one more: Amazon
# checks the privacy policy URL when an app is submitted for publication, and a
# checker that has to sign in finds a login form instead of a policy.
PUBLIC_ENDPOINTS = {"_login", "_healthz", "static", "_pubimg",
                    "invite_page", "invite_accept",
                    "oauth_login", "oauth_callback", "oauth_diagnose",
                    "privacy_page", "terms_page"}

# (prefix, permission). ORDER MATTERS -- first match wins, so anything more
# specific must come before the broader prefix it sits under.
RULES = [
    # -- user administration. /users/me reports who YOU are and what YOU may do,
    #    which every signed-in user needs in order to draw their own screen, so
    #    it is exempted before the broader /users rule.
    ("/users/me",                       None),
    ("/users",                          "manage_users"),

    # -- credentials and settings. /accounts/list and /accounts/select are the
    #    two everyone needs just to open a workspace, so they are exempted here
    #    BEFORE the broader account rules below.
    ("/accounts/list",                  None),
    ("/accounts/select",                None),          # workspace-checked below
    ("/accounts/save",                  "manage_accounts"),
    ("/accounts/delete",                "manage_accounts"),
    ("/accounts/remove_brand",          "manage_accounts"),
    ("/accounts/set_default_marketplace", "manage_accounts"),
    ("/accounts/detect_brands",         "manage_accounts"),
    ("/accounts/detect_marketplaces",   "manage_accounts"),
    ("/settings",                       "manage_accounts"),
    # -- notification channels. Two reasons this is not the default "edit":
    #    a channel holds a webhook URL, which is a bearer credential -- whoever
    #    has it can post into that Slack channel forever; and enabling one makes
    #    this app start speaking OUTSIDE itself, into a room full of people who
    #    did not ask it to. Both are decisions for whoever runs the account, not
    #    for anyone who happens to be able to edit a listing.
    ("/notify",                         "manage_accounts"),
    ("/sp_diagnose",                    "manage_accounts"),
    # /diag reports where state is stored, which environment variables are set,
    # and the tail of recent server tracebacks. That is operator information --
    # useful to whoever runs the deployment, and no business of a VA's.
    ("/diag",                           "manage_accounts"),

    # -- the source repricer. Reading the dry run is how anyone finds out what
    #    the app is about to do to live listings, so it is open to any signed-in
    #    user and exempted BEFORE the broader rule. Everything that changes what
    #    it will do -- enrolling a SKU, adding a supplier, editing the rules --
    #    needs 'publish', because that is what enrolling a SKU eventually causes,
    #    even though no publish happens at the moment the button is pressed.
    ("/sourcing/list",                  None),
    ("/sourcing/log",                   None),
    # The pick-list is the account's own live listings, which anyone who may see
    # the Listings screen can already see, plus which of them are enrolled --
    # which /sourcing/list shows too. Reading it changes nothing; enrolling from
    # it is a separate call and still needs publish.
    ("/sourcing/candidates",            None),
    # Counting the supplier links reads and changes nothing, exactly like the
    # three above.
    ("/sourcing/sources/count",         None),
    # STRIPS EVERY SUPPLIER LINK off the repricer, and takes their recorded
    # price readings with them -- a supplier's price on a day nobody was
    # watching cannot be fetched again. Adding or removing ONE supplier is
    # ordinary repricer work and stays under "publish" with the rest; removing
    # all of them at once is a bulk delete, and that is a different question
    # from "may this person work the repricer".
    #
    # ABOVE the broad /sourcing line, or it never fires -- first match wins, and
    # everything under /sourcing was resolving to publish.
    ("/sourcing/sources/clear",         "approve_delete"),
    # ASKING AMAZON WHAT IT CHARGES IS A READ. It sends nothing to a listing and
    # changes no price -- it fills the fee cache that pricing then reads. Under
    # the broad line below it would have needed "publish", which would stop
    # somebody with view rights from finding out that the 15% they are looking
    # at is not what Amazon actually takes. Above it, for the reason spelled out
    # on the line above: first match wins.
    ("/sourcing/fees",                  None),
    # THE FLOOR SHEET, going out. It lists what each tracked SKU sells for and
    # costs -- the same figures /sourcing/list already answers with -- and it
    # sends nothing to Amazon. Downloading it is a read.
    ("/sourcing/minprice_template.csv", None),
    # Its way BACK IN is not. It writes a floor onto every row it can match,
    # and with the arm box ticked it also puts those SKUs live, which is the
    # single most consequential thing on this screen: a live SKU can change a
    # real price without anyone watching. Same right as arming one by hand.
    #
    # ABOVE the broad /sourcing line for the reason spelled out above: first
    # match wins, and this must not fall through to anything weaker.
    ("/sourcing/minprice_upload",       "publish"),
    # SETS A LIVE PRICE ON AMAZON, immediately, by hand. It is the one route on
    # this screen that does not wait for the four-hourly run -- so it needs the
    # same right as arming, and for the same reason: it changes what a customer
    # is charged. Above the broad line below; first match wins.
    ("/sourcing/manual_price",          "publish"),
    ("/sourcing",                       "publish"),

    # -- importing an eBay seller. Finding and screening send NOTHING anywhere;
    #    screening only ASKS Amazon what is allowed. Drafting writes into this
    #    app's own store -- the same act as creating a draft by hand -- so it
    #    needs "edit", not "publish". Publishing those drafts is still /submit,
    #    gated as it always was.
    ("/seller/find",                    None),
    ("/seller/screen",                  None),
    ("/seller/draft",                   "edit"),

    # -- variation families. Looking at candidates, the themes a product type
    #    allows, and the preview all send NOTHING to Amazon, so they are open to
    #    anyone who may see listings. /variations/apply creates a listing and
    #    rewrites others, which is publishing by any measure.
    ("/variations/apply",               "publish"),
    ("/variations",                     None),

    # -- publishing to Amazon
    ("/submit/target",                  None),          # read-only: names the destination
    ("/submit",                         "publish"),
    ("/optimize/push",                  "publish"),
    # /sync/push/confirm is the LIVE WRITE surface -- it pushes a listing's
    # fields to Amazon. It was falling through to the "edit" default, so a
    # Lister could have published changes. That is precisely what `publish`
    # exists to prevent. (/sync/push itself only PROPOSES a diff, but it is
    # gated the same way: seeing a proposed push you may not perform is
    # pointless, and the two are one action to the user.)
    ("/sync/push",                      "publish"),
    ("/listing/push_image",             "publish"),
    # Reading which slots exist sends nothing; writing one to Amazon is
    # publishing, the same as push_image beside it.
    ("/listing/image_slots",            None),
    ("/listing/image_push",             "publish"),
    ("/handling/bulk_update",           "publish"),     # writes handling time live
    ("/stock/bulk_update",              "publish"),     # writes stock live

    # -- advertising
    ("/ppc",                            "ppc"),

    # -- destructive / final
    ("/approve",                        "approve_delete"),
    ("/delete",                         "approve_delete"),
    ("/clear_empty",                    "approve_delete"),
    ("/miles/clear_history",            "approve_delete"),
    # Deletes every manually-set cost for the account in one go, and there is no
    # undo -- cogs_overrides.json is rewritten without them. Setting ONE cost is
    # ordinary editing and stays under "edit"; wiping all of them moves every
    # profit, margin and ROI figure on every screen at once, which is the same
    # weight as a bulk delete. Listed above the broader /cogs entries so the
    # narrower rule wins.
    ("/cogs/clear",                     "approve_delete"),
    # Deletes frozen weekly reporting history, and there is no undo -- the row
    # holds a finished pack, so the only way back is re-uploading the source
    # files. Uploading a week is ordinary work and stays under "edit"; throwing
    # a year of it away is a bulk delete whatever it is called. Above the
    # broader /weekly entry so the narrower rule wins.
    ("/weekly/clear",                   "approve_delete"),

    # -- shared, long-running work. These are gated by OWNERSHIP in the route
    #    (domain/job_owner.py) rather than by permission: everyone who may do
    #    the work may watch and stop THEIR OWN. Listed here so the gap is a
    #    decision on the record rather than an oversight -- /genimage/jobs_active
    #    and /preview/jobs previously needed no permission at all, so a
    #    view-only user could watch what everyone was working on.
    ("/genimage/jobs_active",           "edit"),
    ("/preview/jobs",                   "edit"),

    # -- IMAGES. Two different jobs, and they used to need the same permission.
    #
    # MAKING an image is gated by the `images` FEATURE at "edit" level, which the
    # doorman checks above -- so these need no action permission of their own.
    # They used to fall through to the default "edit", which is the permission for
    # creating and editing listing DRAFTS, so there was no way to let someone make
    # images without also letting them rewrite listings.
    #
    # KEEPING an image -- saving it into the library, uploading a file, deleting
    # one -- is a separate permission, so "may generate, may not add or remove
    # files" is expressible. Pushing an image to Amazon stays "publish", which is
    # the strongest of the three and already correct.
    ("/genimage/save_to_media",         "upload_images"),
    ("/media/upload",                   "upload_images"),
    ("/media/delete",                   "upload_images"),
    ("/genimage",                       None),          # feature level is the gate
    ("/recipes",                        None),          # ditto -- saved treatments

    # -- the generator's input queue. Importing REPLACES what is generated next,
    #    and clearing throws work away, so they are gated accordingly rather than
    #    falling through to the default read rule.
    # -- changing a live selling price. The preview sends nothing to Amazon, so
    #    it needs only what seeing a listing needs. Applying changes what buyers
    #    pay on a real listing, which is publishing.
    ("/listing/price/preview",          None),
    ("/listing/price/apply",            "publish"),
    # The percentage pair follows exactly the same split, for the same reason:
    # working out what +10% comes to on each listing reads Amazon and sends
    # nothing; applying it changes what buyers pay on many listings at once.
    ("/listing/price/percent_preview",  None),
    ("/listing/price/percent_apply",    "publish"),

    # -- adding a variant. Planning reads and sends nothing; queueing writes a
    #    product into this workspace's own queue, which is the same act as
    #    adding one by hand.
    ("/variant/plan",                   None),
    ("/variant/queue",                  "edit"),

    # -- orders. Read-only and it changes nothing on Amazon, so it needs only
    #    what seeing sales figures needs. The feature gate below puts it with
    #    sales, which is where someone who may not see money must not see it.
    ("/orders/list",                    None),
    ("/orders/detail",                  None),

    # -- returns. Reading is read-only; uploading a file only parses it and
    #    stores nothing, so it needs no more than seeing the figures does.
    ("/returns/report",                 None),
    ("/returns/upload",                 None),

    # -- what the AI cost. Reads a ledger this app wrote; spends nothing and
    #    changes nothing, so it needs no more than seeing the figures does.
    ("/aiusage/summary",                None),
    ("/aiusage/calls",                  None),

    # -- moving listings out of Google Sheets. Reading the status changes
    #    nothing. Running the import writes several hundred rows into this
    #    account's store, which is an operator action rather than day-to-day
    #    work, so it sits with the other account-level settings.
    ("/migrate/status",                 None),
    ("/migrate/import",                 "manage_accounts"),

    # -- backups. Reading the status and checking whether the app has
    #    everything the sheet has change nothing. Running a backup writes to a
    #    spreadsheet, and the download hands over the ENTIRE dataset in one
    #    file -- every account's listings, costs and prices at once -- so it is
    #    held to the highest bar in the app.
    ("/backup/status",                  None),
    ("/backup/verify",                  None),
    ("/backup/run",                     "manage_accounts"),
    ("/backup/download",                "manage_accounts"),

    ("/input/status",                   None),
    ("/input/rows",                     None),
    ("/input/import",                   "edit"),
    # Adding and changing a queued product is the same act as editing the input
    # sheet, so "edit". Deleting one throws work away like clearing does, but a
    # single row rather than the queue -- still a deletion, still gated as one.
    ("/input/add",                      "edit"),
    ("/input/update",                   "edit"),
    ("/input/delete",                   "approve_delete"),
    ("/input/clear",                    "approve_delete"),

    # TEMPORARY -- goes with routes/admin_migrate_routes.py.
    #
    # Listed explicitly because the default for an unlisted GET is None, i.e.
    # any signed-in user. This route rewrites every listing's status and deletes
    # queue rows, so it takes the same permission /input/clear does. The query
    # key on the route is a second factor, not the gate: it travels in the URL
    # and therefore into logs and browser history.
    ("/admin/migrate",                  "approve_delete"),

    # -- sales. The feature gate above already decides who may SEE any of it;
    #    pulling from Amazon is work, so it needs "edit" like other mutations.
    ("/sales/sync",                     "edit"),
    ("/sales",                          None),

    # -- work that happens over GET, so the default read rule would let it
    #    through. Listed explicitly so it needs "edit" like any other mutation.
    ("/run/health",                     None),          # diagnostics only
    ("/run/stack",                      None),
    ("/run",                            "edit"),
    ("/miles/run_log",                  None),
    ("/miles/run_csv",                  None),
    ("/miles/runs",                     None),
    ("/miles/run_active",               None),
    ("/miles/run_tail",                 None),
    ("/miles/results",                  None),
    ("/miles/run",                      "edit"),
    ("/miles/generate",                 "edit"),
    ("/miles/optimize",                 "edit"),
    ("/rescan/apply",                   "edit"),
]

# Requests that name a workspace. Enforcing scope HERE is what makes per-user
# workspace access real: every data route reads whichever account is currently
# selected, so refusing the switch is the one choke point that covers all of
# them. Blocking only the UI would leave the data one fetch() away.
WORKSPACE_SWITCH = {
    "/accounts/select": "id",
    "/view/set":        "key",
}

# THE OTHER WAY IN, WHICH WAS OPEN.
#
#     "why is one user able to see the information of another user, every
#      account is separate ... i am concerned that when i give this tool out to
#      random people to test and use they will be able to see other people
#      information"
#
# The design above is sound AS FAR AS IT GOES: refuse the switch, and since
# every data route reads whichever account is currently selected, one choke
# point covers all of them.
#
# It stopped being true. Routes now accept an EXPLICIT account -- ?id=jack_uk,
# ?account_id=..., or the same in a POST body -- because a screen has to be able
# to say which account it is showing rather than trusting a process-wide
# variable. That was itself a fix, for a real bug where pressing Generate while
# looking at Jack Reacherd ran against Nestwell.
#
# But check() is handed the PATH ONLY. It never sees the query string, so a
# named account was never checked against the user's list. MEASURED with a user
# restricted to nestwell_goods:
#
#     POST /accounts/select {id: jack_uk}  -> refused, correctly
#     GET  /trackers?id=jack_uk            -> ALLOWED
#     GET  /catalog/products?id=jack_uk    -> ALLOWED
#     GET  /overview                       -> ALLOWED, and reads every account
#
# So the account is now checked WHEREVER IT IS NAMED, on every request, which
# puts the enforcement back at one place and makes it hold for routes nobody
# has written yet.
WORKSPACE_PARAMS = ("id", "account_id", "workspace_id", "workspace", "ws",
                    # `account` WAS MISSING, and four handlers read it:
                    #   routes/orders_routes.py:118   /orders/list?account=
                    #   routes/orders_routes.py:632   /orders/detail?account=
                    #   routes/listing_routes.py:174  the rows_all helper
                    #   routes/listing_routes.py:807  /rows_all?account=
                    # so a named account went unchecked on exactly the routes
                    # that carry another company's customers -- order lines,
                    # buyer town and postcode. The only thing refusing a
                    # cross-account read there was the "is this the open
                    # account?" comparison in the route, which is a check about
                    # a process-wide variable rather than about who is asking.
                    "account")

# Sentinels that are not workspace ids. `__all__` means "the account that is
# open" by the time a route reads it (routes/orders_routes.py turns it into ""),
# and an old bookmark may still carry it -- refusing it as an unknown workspace
# would show an error for something nobody chose.
WORKSPACE_SENTINELS = ("__all__", "_no_account", "")

# Paths where an `id` means something else entirely. Checking these against the
# workspace list would refuse ordinary work -- deleting a media file by id,
# editing a user by id -- so they are named rather than guessed at.
WORKSPACE_PARAM_EXEMPT = (
    "/users",            # user ids
    "/media",            # media/file ids
    "/notify/channel",   # channel ids
    "/trackers/watch",   # asin + metric, no workspace
    "/input/",           # input row ids
    "/listing/",         # sku-scoped
    "/row",              # row ids
    "/genimage",         # job ids
    "/aplus",            # module ids
    "/drive",            # drive file ids
)


def named_workspace(path, args, json_body):
    """The account this request names, if it names one. "" when it does not.

    Read from the query string first and the body second, because that is the
    order the routes themselves read them in -- and a check that looked
    somewhere else from the code it protects would be a check in name only.
    """
    p = str(path or "")
    for ex in WORKSPACE_PARAM_EXEMPT:
        if p.startswith(ex):
            return ""
    for field in WORKSPACE_PARAMS:
        try:
            v = (args or {}).get(field)
        except Exception:
            v = None
        if v and str(v).strip() not in WORKSPACE_SENTINELS:
            return str(v).strip()
    for field in WORKSPACE_PARAMS:
        try:
            v = (json_body or {}).get(field)
        except Exception:
            v = None
        if v and str(v).strip() not in WORKSPACE_SENTINELS:
            return str(v).strip()
    # AND ONE LEVEL INTO A LIST OF ROWS.
    #
    # This read TOP-LEVEL fields only, so a request that names its account
    # per-row named nothing as far as this was concerned and no workspace check
    # ran at all. Found by reading the routes rather than by a report:
    #
    #     POST /orders/items {"orders": [{"order_id": ..,
    #                                     "account_id": "jack_uk"}, ...]}
    #
    # A batch shape like that is the natural way to ask about sixty orders at
    # once, and it walked straight past the doorman -- a user restricted to
    # nestwell_goods could read jack_uk's order contents, product titles and
    # profit by posting that.
    #
    # The FIRST account named anywhere in the batch is what is checked. Every
    # row in a batch should belong to one account; if they do not, checking the
    # first is what makes the rest refuse, which is the outcome wanted.
    try:
        for _v in (json_body or {}).values():
            if not isinstance(_v, list):
                continue
            for _row in _v[:200]:
                if not isinstance(_row, dict):
                    continue
                for field in WORKSPACE_PARAMS:
                    _rv = _row.get(field)
                    if _rv:
                        return str(_rv).strip()
    except Exception:
        pass
    return ""


# Which FEATURE AREA a path belongs to. First match wins, most specific first.
# This is the "may they SEE it" axis; RULES above is "may they DO it".
#
# Anything not listed belongs to no feature and is governed by RULES alone --
# so adding a route cannot accidentally hide it from everyone.
FEATURE_PATHS = [
    # Revenue is commercially sensitive, so it is its own feature rather than
    # riding on "listings" -- a lister needs listings and has no business
    # reading turnover.
    # ---- PER-PAGE ENTRIES COME FIRST, because first match wins and each of
    #      these sits under a broader prefix below. Every one of them inherits
    #      its area's level until it is set individually (see FEATURE_PARENT in
    #      auth/users.py), so adding them changed nobody's access.
    # ---- THE SCREENS ADDED LATER, WHICH WERE UNGOVERNED ----
    #
    # MEASURED: feature_for() returned nothing for all ten of them, so they were
    # governed by RULES alone -- which is "any user who may edit". A person with
    # sales set to `none` could open the Business Overview and read every
    # account's revenue.
    #
    # They are mapped onto the EXISTING features rather than given ten new ones,
    # because the question "may this person see turnover" does not become a
    # different question because the screen is new. Ten more checkboxes would be
    # ten more things to set correctly and the same answer either way.
    # AND THE SAME OMISSION HAPPENED AGAIN, with the screen added after that
    # note was written. /brief returns the weekly business brief: revenue,
    # profit, what moved up and down. feature_for("/brief") returned None, so it
    # was governed by RULES alone -- "any user who may edit" -- and a person
    # with sales set to `none` could read the whole thing.
    #
    # This is the second time a new screen has shipped ungoverned, which says
    # the default is the problem rather than the author: an unlisted path is
    # readable, so forgetting is silent. test_permission_coverage.py now fails
    # when a section has no feature, so the third one cannot ship quietly.
    # Phase 1 analytics, governed ON ARRIVAL rather than after somebody notices.
    # Same feature as /sqp: this is search performance, and it is commercially
    # sensitive in the way turnover is -- what the marketplace searches for, and
    # what converts on our listings. Listed BEFORE /keywords would be, and the
    # prefix covers every route in routes/keywords_routes.py including the
    # rank-tracker POSTs.
    ("/keywords",             "traffic"),
    # ASIN Studio writes copy and creates a draft -- a LISTINGS power.
    ("/asin-studio",          "listings"),
    ("/brief",                "sales"),      # revenue, profit, weekly movement
    ("/leading",              "sales"),      # yesterday's revenue and units
    ("/catalog/products",     "listings"),   # the product catalogue
    ("/categories",           "listings"),
    ("/compliance",           "listings"),
    ("/trackers",             "monitor"),    # watching an ASIN's numbers
    ("/sqp",                  "traffic"),    # search performance is traffic
    ("/drppc",                "ppc"),
    # /notify holds a webhook credential and is already restricted to
    # manage_accounts by RULES; the feature axis follows the same reasoning.
    ("/notify",               "accounts"),

    ("/orders",               "orders"),
    ("/returns",              "returns"),
    ("/traffic",              "traffic"),
    ("/hourly",               "hourly"),
    ("/finance",              "finance"),
    ("/aiusage",              "aiusage"),
    ("/sourcing",             "repricer"),
    ("/variations",           "variations"),
    ("/variant",              "variations"),
    ("/seller",               "sellerimport"),
    # Generating and publishing is its own page and its own risk: it is the one
    # that creates listings on Amazon.
    ("/run",                  "generate"),
    ("/preview",              "generate"),
    ("/input",                "generate"),

    ("/sales",                "sales"),
    # (Contribution per product, orders, returns and AI spend all used to map
    #  straight to "sales" here. They are still the same commercially-sensitive
    #  area -- someone who may not see revenue must not see it one order at a
    #  time either -- but each now has its own entry ABOVE and inherits "sales"
    #  until it is set, so the default is unchanged and the page can be turned
    #  off on its own.)
    ("/ppc",                  "ppc"),
    ("/inventory",            "inventory"),
    ("/monitor",              "monitor"),
    ("/genimage",             "images"),
    ("/media",                "images"),
    ("/aplus",                "images"),
    ("/recipes",              "images"),
    ("/settings",             "accounts"),
    ("/accounts/list",        None),     # needed to draw the workspace list
    ("/accounts/select",      None),     # and to open one
    ("/accounts",             "accounts"),
    ("/sp_diagnose",          "accounts"),
    # (The repricer, variations and seller import are mapped ABOVE, each to its
    #  own page feature. They still inherit "listings" until set, which is the
    #  behaviour they had: someone with no access to listings has no business
    #  seeing what is about to happen to their prices either.)
    ("/rows",                 "listings"),
    ("/row",                  "listings"),
    ("/live",                 "listings"),
    ("/listing",              "listings"),
    ("/approve",              "listings"),
    ("/edit",                 "listings"),
    ("/delete",               "listings"),
    ("/suggest",              "listings"),
    ("/submit",               "listings"),
    ("/optimize",             "listings"),
    ("/sync",                 "listings"),
]


def feature_for(path):
    """The feature area a path belongs to, or None if it belongs to none."""
    p = str(path or "")
    for prefix, feat in FEATURE_PATHS:
        if p == prefix or p.startswith(prefix + "/") or p.startswith(prefix + "?"):
            return feat
    return None


def required_permission(path, method):
    """The permission this request needs, or None if any signed-in user may do it."""
    p = str(path or "")
    for prefix, perm in RULES:
        if p == prefix or p.startswith(prefix + "/") or p.startswith(prefix + "?"):
            return perm
    if str(method or "GET").upper() in ("GET", "HEAD", "OPTIONS"):
        return None                       # reads are open to anyone signed in
    return "edit"                         # unlisted mutation -> fails closed


def check(path, method, user, json_body=None, args=None):
    """Decide one request. Returns (allowed: bool, message: str).

    `json_body` is only needed for workspace switches; pass the parsed body or
    None. It is read defensively -- a malformed body must not crash the doorman.

    `args` is the query string. Without it a request naming another account --
    ?id=jack_uk -- is invisible to this function, which is exactly how a user
    restricted to one workspace could read every other one. It defaults to None
    so existing callers keep working, and the doorman always passes it.
    """
    if not user:
        return False, "Not signed in."
    if not user.get("active", True):
        return False, "This account has been disabled."

    p = str(path or "")

    # 1. Workspace scope, before anything else: a user restricted to Nestwell
    #    must not be able to select Jack Reacherd, whatever else they may do.
    for prefix, field in WORKSPACE_SWITCH.items():
        if p == prefix:
            ws = ""
            try:
                ws = str((json_body or {}).get(field, "") or "")
            except Exception:
                ws = ""
            if not users.can_access_workspace(user, ws):
                return False, "You do not have access to that workspace."
            return True, ""

    # 1b. AN ACCOUNT NAMED ANYWHERE ELSE IN THE REQUEST.
    #
    # Routes take ?id=<account> so a screen can say which account it is showing
    # rather than trusting a process-wide variable. Nothing checked it. A user
    # restricted to nestwell_goods could read jack_uk by asking for it.
    #
    # Checked HERE, before features and permissions, for the same reason the
    # switch is: no amount of feature access makes another company's turnover
    # your business.
    named = named_workspace(p, args, json_body)
    if named and not users.can_access_workspace(user, named):
        return False, "You do not have access to that workspace."

    # 2. FEATURE ACCESS -- "may they see this area at all?"
    #
    # Checked before the permission, because a feature set to `none` should be
    # refused outright rather than producing "you need the ppc permission" for
    # a screen the person is not supposed to know exists.
    feat = feature_for(p)
    is_read = str(method or "GET").upper() in ("GET", "HEAD", "OPTIONS")
    if feat:
        lvl = users.feature_level(user, feat)
        if lvl == "none":
            return False, ("You do not have access to %s."
                           % users.FEATURES.get(feat, feat))
        if lvl == "view" and not is_read:
            return False, ("You have read-only access to %s."
                           % users.FEATURES.get(feat, feat))
        if is_read:
            # The feature level IS the read gate. Requiring the action
            # permission as well would make "view" meaningless -- someone given
            # read-only sight of PPC would still be refused the PPC page,
            # because `ppc` is the permission for CHANGING bids.
            #
            # Feature level is the floor, the action permission the ceiling:
            # seeing costs view, doing costs the permission.
            return True, ""

    # 3. Ordinary permission check.
    perm = required_permission(p, method)
    if perm is None:
        return True, ""
    if users.has_permission(user, perm):
        return True, ""
    return False, _denial_message(perm)


def _denial_message(perm):
    """Say plainly what is missing, so nobody has to guess why a click failed."""
    label = users.PERMISSIONS.get(perm, perm)
    return ("You do not have permission for this action. "
            "It needs: %s. Ask the account owner to grant it." % label)


def wants_json():
    """Is this an API call rather than someone typing an address?

    A browser NAVIGATION asks for text/html and is a GET. Everything else here --
    a POST, a JSON body, an explicit JSON Accept, or an XHR marker -- is the
    app's own code calling an endpoint and expecting JSON back.

    Deliberately generous: answering JSON to something that wanted HTML shows a
    small technical message instead of a login page, while answering HTML to
    something that wanted JSON produces the "Unexpected token '<'" error that
    hides the real cause entirely. The second failure is far worse.
    """
    try:
        if request.method != "GET":
            return True
        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return True
        accept = str(request.headers.get("Accept") or "")
        if "application/json" in accept:
            return True
        # PAGE ROUTES ARE ALWAYS NAVIGATIONS, whatever the headers say. Deciding
        # purely on Accept is fragile -- not every client sends text/html, and
        # answering a page request with JSON would show a bare error string
        # instead of the login screen. The page routes are a short, known list,
        # so treat them as certain and use the header only for the rest.
        p = str(request.path or "")
        if p == "/" or p.startswith("/w/") or p.startswith("/login") \
                or p.startswith("/invite/") or p.startswith("/logout"):
            return False
        # A real navigation says text/html. A bare fetch() usually says */*.
        return "text/html" not in accept
    except Exception:
        return False


# The ONE place this question is answered. The doorman asks it to decide between
# a JSON 401 and a redirect to the login page; dashboard.py's error handler asks
# it to decide between a JSON error and Flask's HTML error page. They must agree:
# two copies of this rule would drift, and every disagreement shows up in the
# browser as "Unexpected token '<'".
_wants_json = wants_json


def make_doorman(config_path, app_password, login_endpoint="_login"):
    """Build the before_request handler that runs on EVERY request.

    Lives here rather than in dashboard.py so that the decision and its
    enforcement are the same piece of code -- and so it can be tested directly,
    which a function defined inside dashboard.py's __main__ block cannot be.
    """
    def _require_login():
        # _pubimg is intentionally public: it serves a single image whose URL
        # already embeds a valid HMAC token, so Amazon (and only holders of the
        # token) can fetch it.
        if request.endpoint in PUBLIC_ENDPOINTS:
            return

        uid = session.get("uid")

        # Local dev with no shared password AND no accounts: the gate no-ops,
        # exactly as it did before any of this existed.
        if not app_password and users.is_bootstrap(config_path) and not uid:
            return

        if not session.get("authed"):
            # AN API CALL MUST NOT BE REDIRECTED TO AN HTML PAGE.
            #
            # Every fetch() in the app parses the reply as JSON. Redirecting one
            # to /login means the browser quietly follows it, receives the login
            # PAGE, and the app reports:
            #     Unexpected token '<', "<!doctype "... is not valid JSON
            # which says nothing about the real problem -- that the session has
            # expired. It looks like the feature is broken rather than that you
            # are signed out, and it sent us hunting in the wrong place.
            #
            # Browser navigations still redirect, because for those the login
            # page IS the right answer.
            if _wants_json():
                return jsonify({
                    "ok": False, "authed": False,
                    "error": "Your session has expired. Reload the page and sign in again."
                }), 401

            # Carry the destination through the sign-in. Every screen has its own
            # address now, so without this a bookmarked link followed after the
            # session expired would silently dump you on the workspace list.
            nxt = request.full_path if request.method == "GET" else ""
            if nxt.endswith("?"):
                nxt = nxt[:-1]
            return redirect(url_for(login_endpoint, next=nxt) if nxt
                            else url_for(login_endpoint))

        user = users.get_user(config_path, uid) if uid else None

        # Deleted or disabled mid-session -> sign them out and send them to the
        # sign-in screen. NOT a 403: that path answers with JSON, which is right
        # for the app's fetch() calls but would show a disabled person a raw blob
        # of JSON in place of every page they open.
        if uid and (user is None or not user.get("active", True)):
            session.clear()
            if _wants_json():
                return jsonify({"ok": False, "authed": False,
                                "error": "Your account was changed or disabled. "
                                         "Reload the page and sign in again."}), 401
            return redirect(url_for(login_endpoint))

        if user is None:
            if not users.is_bootstrap(config_path):
                # Accounts exist now, so the shared password is no longer a way in.
                session.clear()
                if _wants_json():
                    return jsonify({"ok": False, "authed": False,
                                    "error": "The shared password no longer works now that "
                                             "user accounts exist. Sign in with your own "
                                             "email and password."}), 401
                return redirect(url_for(login_endpoint))
            user = users.bootstrap_user()

        body = request.get_json(silent=True) if request.method == "POST" else None
        # THE QUERY STRING GOES IN TOO. Without it, a request naming another
        # account (?id=jack_uk) is invisible to the check -- which is how a user
        # restricted to one workspace could read every other one.
        ok, why = check(request.path, request.method, user, body, request.args)
        if not ok:
            # 403 with a plain reason, as JSON -- every fetch() in the app expects
            # JSON and would otherwise report a parse error instead of the cause.
            return jsonify({"ok": False, "error": why, "forbidden": True}), 403

    return _require_login


def audit(rules=None):
    """Every rule, for review. Used by the tests and worth printing when the
    policy changes -- a permission table you cannot read is one you cannot trust.
    """
    out = []
    for prefix, perm in (rules or RULES):
        out.append({"prefix": prefix,
                    "permission": perm or "(any signed-in user)",
                    "description": users.PERMISSIONS.get(perm, "") if perm else ""})
    return out
