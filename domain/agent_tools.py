"""domain/agent_tools.py -- what the assistant is allowed to look at.

WHY THIS EXISTS

The app already had a chat box ("Ask Claude", routes/listing_routes.py) and it
could not see anything. It knew what you typed and nothing else -- ask it "how
did last week go" and it would either decline or, worse, write a plausible
paragraph containing no real number. That is the whole difference between a
chat box and an assistant: not the model, the reach.

Orbit's three agents were asked, at length, what they can actually do. Every
useful answer came back the same shape -- the agent does not know anything, it
CALLS something and reports what came back:

    Ava, asked how it answers a money question:
    "I call ava__get_pnl_summary ... I never estimate financials. If the tool
     returns nothing I say so."

    Steven, asked for its formulas:
    "in_stock_rate, oos_adjusted velocity ... I return the fields the tool
     returns. I don't recompute them."

So the design here is deliberately unambitious: this file does NOT know how to
work out profit, coverage, or what moved yesterday. It knows which of the app's
OWN read-only screens answers each question, and it calls that.

WHY IT CALLS ENDPOINTS RATHER THAN DOMAIN FUNCTIONS

CLAUDE.md rule 12 -- one place per concept. Every figure below already has one
place that produces it, and that place is an endpoint the screens already draw
from. Reaching past them into the domain layer would mean re-deciding the date
window, the VAT rate, the basis calendar and the trimming at a second site, and
the two would drift apart from the first fix onward. Calling the endpoint means
the assistant and the screen can never disagree -- they are reading the same
sentence.

THE THREE GUARANTEES

1. READ-ONLY. Only GET, only from the list below. There is no tool here that
   writes, submits, prices, or contacts Amazon. The assistant cannot change
   anything, so a wrong answer stays a wrong answer rather than becoming a
   wrong action.
2. SCOPED SERVER-SIDE. The account and marketplace are attached by the caller
   (routes/agent_routes.py) from whatever the user has open. They are NOT
   arguments the model can set, so no question can be phrased in a way that
   reads another account's money.
3. TRIMMED OUT LOUD. Long lists are cut, and the cut says so in the result --
   "showing 40 of 312". Silent truncation is the one that turns into a false
   summary, because a list that looks whole gets described as whole.
"""

# ---------------------------------------------------------------------------
# The allowlist.
#
# path      the app's own read-only endpoint -- the SAME one the screen calls
# params    query arguments the model may set (scope is never one of them)
# trim      (key, limit, ordered_by) -- lists to cut, and what the order means
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "account_in_view",
        "path": None,                      # answered locally, see run()
        "params": {},
        "description":
            "Which account and marketplace every other tool will read, and "
            "today's date. Call this FIRST in a conversation so you can name "
            "the account in your answer. The user cannot ask about a different "
            "account in this chat -- they switch account in the app.",
    },
    {
        "name": "sales_summary",
        "path": "/sales/summary",
        "params": {"preset": "str", "start": "date", "end": "date"},
        "description":
            "Headline sales for a window, each figure with its change against "
            "the previous equal period: units, orders, revenue, average price. "
            "Use for 'how are sales', 'how did last month go', 'are we up'.",
    },
    {
        "name": "sales_by_product",
        "path": "/sales/breakdown",
        "params": {"preset": "str", "start": "date", "end": "date",
                   "group": "asin|parent"},
        "description":
            "Sales per product for a window. group=parent rolls variations up "
            "to the parent listing. Use for 'what sold', 'best sellers', "
            "'which product is falling'.",
        "trim": ("rows", 40, "highest revenue first"),
    },
    {
        "name": "profit_by_product",
        "path": "/finance/contribution",
        "params": {"preset": "str", "start": "date", "end": "date"},
        "description":
            "What was actually left after Amazon's real fees, refunds, "
            "advertising and cost of goods -- per product and in total. Fees "
            "are the ones Amazon charged, not an assumption. Products with no "
            "recorded cost are reported separately rather than counted as free: "
            "say so if the answer depends on them.",
        "trim": ("rows", 40, "largest contribution first"),
    },
    {
        "name": "traffic_summary",
        "path": "/traffic/summary",
        "params": {"preset": "str", "start": "date", "end": "date",
                   "group": "asin|parent"},
        "description":
            "Sessions, page views, conversion and Buy Box share. Use when the "
            "question is about whether people are LOOKING (traffic) or BUYING "
            "(conversion) -- the two fail differently and the fix differs.",
        "trim": ("rows", 40, "most sessions first"),
    },
    {
        "name": "what_moved",
        "path": "/leading",
        "params": {"day": "date", "window": "int"},
        "description":
            "Yesterday measured against its own recent history, in standard "
            "deviations -- so a quiet Sunday does not read as a crash. Use for "
            "'anything wrong', 'what changed', 'why is today odd'.",
    },
    {
        "name": "stock_cockpit",
        "path": "/inventory/stock",
        "params": {"horizon": "int"},
        "description":
            "What is in stock now, per SKU, with the value tied up in it. Use "
            "for 'what have I got', 'what is out of stock'.",
        "trim": ("rows", 50, "worst first"),
    },
    {
        "name": "selling_pace_and_cover",
        "path": "/inventory/coverage",
        "params": {"window": "int"},
        "description":
            "How fast each SKU really sells and when it runs out. The pace "
            "counts only the days the SKU was actually sellable, so days it was "
            "out of stock do not read as days nobody wanted it. IMPORTANT: this "
            "result marks which fields are MEASURED and which are ESTIMATES -- "
            "cover, thirty-day demand and the gap assume the next thirty days "
            "look like the last. Repeat that distinction in your answer. The "
            "gap is a coverage shortfall, NOT a purchase order: it knows nothing "
            "about minimum order quantity, case pack or lead time.",
        "trim": ("rows", 50, "worst first"),
    },
    {
        "name": "money_amazon_owes",
        "path": "/inventory/money-back",
        "params": {},
        "description":
            "Orders where Amazon's own published rule says a fee or a refund "
            "should have come back and did not. Each row carries the rule it "
            "was found by. Use for 'is Amazon owing me anything', "
            "'reimbursements'.",
        "trim": ("rows", 40, "largest amount first"),
    },
    {
        "name": "daily_round",
        "path": "/daily/check",
        "params": {},
        "description":
            "The morning checklist the app runs for this account: unshipped "
            "orders, cancellation requests, stranded and delisted listings, "
            "stock, suppliers, the repricer, sync freshness. A check that could "
            "not look says so rather than passing. Use for 'anything I need to "
            "do', 'is everything ok'.",
    },
    {
        "name": "returns",
        "path": "/returns/report",
        "params": {"days": "int"},
        "description":
            "Returns for the window, with the reasons buyers gave. Use for "
            "'why are people returning this', 'return rate'.",
        "trim": ("rows", 40, "most returns first"),
    },
    {
        "name": "recent_orders",
        "path": "/orders/list",
        "params": {},
        "description":
            "The most recent orders with their status. Use for a question about "
            "a specific order or about what has come in today.",
        "trim": ("rows", 30, "newest first"),
    },
    {
        "name": "tracker_alerts",
        "path": "/trackers/alerts",
        "params": {},
        "description":
            "Open alerts from the four trackers -- rank, Buy Box, price and "
            "fee. Use for 'did anything get flagged', 'did I lose the Buy Box'.",
        "trim": ("alerts", 40, "newest first"),
    },
    {
        "name": "products_in_catalogue",
        "path": "/catalog/products",
        "params": {"period": "str"},
        "description":
            "Every product this account sells, with its title and picture. Use "
            "to turn an ASIN or SKU the user mentions into a product name, or "
            "to answer 'what do I sell'.",
        "trim": ("rows", 60, "alphabetical"),
    },
]

BY_NAME = {t["name"]: t for t in TOOLS}


def definitions():
    """The tool list in the shape the Anthropic API wants.

    Descriptions are the ones above verbatim. A tool description IS the
    instruction the model follows when choosing -- keeping them here, next to
    the endpoint each one calls, is what stops the two drifting apart.
    """
    out = []
    for t in TOOLS:
        props, required = {}, []
        for k, kind in t["params"].items():
            if kind == "date":
                props[k] = {"type": "string",
                            "description": "YYYY-MM-DD"}
            elif kind == "int":
                props[k] = {"type": "integer"}
            elif "|" in kind:
                props[k] = {"type": "string", "enum": kind.split("|")}
            else:
                props[k] = {"type": "string"}
        if "preset" in props:
            props["preset"]["description"] = (
                "One of 7d, 14d, 30d, 60d, 90d, ytd. Ignored when start and "
                "end are both given. Windows end YESTERDAY -- Amazon has no "
                "figures for today.")
        out.append({
            "name": t["name"],
            "description": t["description"],
            "input_schema": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        })
    return out


def _trim(payload, spec):
    """Cut a long list and SAY the list was cut.

    A trimmed list that does not admit it is the thing that becomes a false
    summary -- "you have 40 products needing attention" when there are 312.
    """
    if not spec or not isinstance(payload, dict):
        return payload
    key, limit, order = spec
    rows = payload.get(key)
    if not isinstance(rows, list) or len(rows) <= limit:
        return payload
    out = dict(payload)
    out[key] = rows[:limit]
    out["_trimmed"] = ("Showing %d of %d %s (%s). Say so if you summarise the "
                       "list -- the rest were not read."
                       % (limit, len(rows), key, order))
    return out


def run(name, args, *, fetch, scope):
    """Execute one tool. Returns (result_dict, is_error).

    `fetch(path, params) -> (status, json)` is supplied by the route module so
    that nothing in domain/ imports Flask. `scope` is the account this chat is
    pinned to, and it is applied HERE rather than trusted from `args` -- the
    model never gets to choose whose money it reads.
    """
    t = BY_NAME.get(name)
    if not t:
        return {"error": "No such tool: %s" % name}, True

    if t["path"] is None:                       # account_in_view
        return dict(scope), False

    params = {}
    for k, v in (args or {}).items():
        if k in t["params"] and v not in (None, ""):
            params[k] = v
    # Scope last, so it cannot be overridden by a coincidental argument name.
    params["id"] = scope.get("account_id", "")
    params["marketplace"] = scope.get("marketplace", "")

    try:
        status, body = fetch(t["path"], params)
    except Exception as e:
        return {"error": "Could not read %s: %s" % (t["path"], str(e)[:200])}, True

    if status != 200:
        # The endpoint's own words, not a rewrite of them. When a screen would
        # have said "open an account first", the assistant should say that too.
        msg = ""
        if isinstance(body, dict):
            msg = str(body.get("error") or body.get("message") or "")
        return {"error": msg or ("That screen returned %d." % status),
                "asked": t["path"]}, True

    if not isinstance(body, dict):
        body = {"result": body}
    return _trim(body, t.get("trim")), False
