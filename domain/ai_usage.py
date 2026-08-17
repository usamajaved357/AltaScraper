"""domain/ai_usage.py -- what the AI actually cost, per account and per feature.

WHY IT IS ONE FILE
Spend leaves the app through two channels: OpenRouter, entirely through
ai_providers._post, and Anthropic, through .messages.create in eleven different
files. Recording it at each of those twelve places would mean twelve chances to
forget one, and a spend dashboard that silently omits a feature is worse than
none -- it is wrong in the flattering direction, and nobody checks a number that
looks reassuring.

So there is one recorder here, one wrapper for Anthropic calls (call_anthropic),
and ai_providers._post records for everything OpenRouter.

WHAT IS DELIBERATELY NOT GUESSED
    * A model with no price in PRICES records cost_usd = NULL, not 0. Zero for a
      call that certainly cost something is the single worst number this file
      could produce, and it would compound quietly across thousands of rows.
      The screen reports how much of the spend is unpriced.
    * A call with no account attached records workspace_id "", and the screen
      shows that separately rather than folding it into whichever account
      happened to be open. Spend on the wrong account is worse than spend on
      none.
    * Recording NEVER raises and never blocks the call it is measuring. A
      failure to write a usage row must not fail a listing generation.
"""
import time

from data import db as _db

# USD per MILLION tokens, and per image. Published list prices, and they change:
# an unknown model is priced as unknown rather than as free, so a stale table
# under-reports loudly instead of silently.
PRICES = {
    # Anthropic
    "claude-opus-4":            (15.00, 75.00),
    "claude-opus-4-1":          (15.00, 75.00),
    "claude-sonnet-4":          (3.00, 15.00),
    "claude-sonnet-4-5":        (3.00, 15.00),
    "claude-3-5-sonnet":        (3.00, 15.00),
    "claude-3-5-haiku":         (0.80, 4.00),
    "claude-haiku-4-5":         (1.00, 5.00),
    "claude-3-opus":            (15.00, 75.00),
    # OpenRouter text models seen in this app
    "openai/gpt-4o":            (2.50, 10.00),
    "openai/gpt-4o-mini":       (0.15, 0.60),
    "openai/gpt-4.1":           (2.00, 8.00),
    "openai/gpt-4.1-mini":      (0.40, 1.60),
    "google/gemini-2.0-flash":  (0.10, 0.40),
    "google/gemini-2.5-flash":  (0.30, 2.50),
    "google/gemini-2.5-pro":    (1.25, 10.00),
    "anthropic/claude-sonnet-4": (3.00, 15.00),
    "anthropic/claude-3.5-sonnet": (3.00, 15.00),
}

# USD per generated image, by model.
IMAGE_PRICES = {
    "google/gemini-2.5-flash-image": 0.039,
    "google/gemini-2.0-flash-exp":   0.039,
    "openai/gpt-image-1":            0.040,
    "black-forest-labs/flux-1.1-pro": 0.040,
    "black-forest-labs/flux-pro":    0.050,
    "stability-ai/sdxl":             0.010,
}


def _price_for(model):
    """(input_per_mtok, output_per_mtok) or None when the model is not priced.

    Matched on the longest known key the model name contains, so
    "claude-sonnet-4-5-20260101" prices as claude-sonnet-4-5 rather than as
    claude-sonnet-4 -- a shorter accidental match would price a call at the
    wrong tier and look perfectly plausible.
    """
    m = str(model or "").lower()
    best = None
    for key, price in PRICES.items():
        if key in m and (best is None or len(key) > len(best[0])):
            best = (key, price)
    return best[1] if best else None


def _image_price_for(model):
    m = str(model or "").lower()
    best = None
    for key, price in IMAGE_PRICES.items():
        if key in m and (best is None or len(key) > len(best[0])):
            best = (key, price)
    return best[1] if best else None


def cost_of(model, input_tokens=0, output_tokens=0, images=0):
    """What one call cost in USD, or None when this model has no known price."""
    total, known = 0.0, False
    if images:
        p = _image_price_for(model)
        if p is None:
            return None
        total += p * int(images)
        known = True
    if input_tokens or output_tokens:
        p = _price_for(model)
        if p is None:
            return None
        total += (int(input_tokens) / 1e6) * p[0]
        total += (int(output_tokens) / 1e6) * p[1]
        known = True
    return round(total, 6) if known else None


def record(config_path, *, feature, provider, model="", workspace_id="",
           input_tokens=0, output_tokens=0, images=0, kind="text",
           ok=True, error="", sku="", ms=0, cost_usd=None):
    """Write one usage row. Never raises.

    A failure to record must never fail the work being recorded -- the usage
    table is a ledger, not a dependency.

    `cost_usd` is the PROVIDER's own figure where it gave one. It wins over the
    PRICES table, which cannot know a model it has never seen -- and an image
    model the table is missing is exactly how a picture came to be recorded at
    zero cost.
    """
    try:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        conn = _db.get_db(config_path)
        conn.execute(
            "INSERT INTO ai_usage (at, day, workspace_id, feature, provider, "
            " model, kind, input_tokens, output_tokens, images, cost_usd, ok, "
            " error, sku, ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            # A caller that named nothing gets the request it came from rather
            # than the word "unknown", which tells nobody which of the fourteen
            # call sites to look at. See unnamed_feature().
            (now, now[:10], str(workspace_id or ""),
             str(feature or "") or unnamed_feature(),
             str(provider or ""), str(model or ""), str(kind or "text"),
             int(input_tokens or 0), int(output_tokens or 0), int(images or 0),
             (cost_usd if cost_usd is not None
              else cost_of(model, input_tokens, output_tokens, images)),
             1 if ok else 0, str(error or "")[:300], str(sku or ""),
             int(ms or 0)))
        conn.commit()
    except Exception:
        pass


def tokens_from_anthropic(resp):
    """(input, output) from an Anthropic response, whatever shape it arrives in."""
    try:
        u = getattr(resp, "usage", None)
        if u is None and isinstance(resp, dict):
            u = resp.get("usage")
        if u is None:
            return 0, 0
        get = (lambda k: getattr(u, k, None)) if not isinstance(u, dict) else u.get
        return int(get("input_tokens") or 0), int(get("output_tokens") or 0)
    except Exception:
        return 0, 0


def tokens_from_openrouter(payload):
    """(input, output) from an OpenRouter JSON reply."""
    try:
        u = (payload or {}).get("usage") or {}
        return int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
    except Exception:
        return 0, 0


def cost_from_openrouter(payload):
    """What OPENROUTER says the call cost, or None.

    THE PROVIDER'S OWN NUMBER BEATS OUR TABLE, and it is the only figure that can
    be right for a model the table has never heard of. Measured: an image
    generated through bytedance-seed/seedream-4.5 was recorded with cost NULL --
    correct, because guessing is worse than admitting -- but it means the spend
    report is silently lower than the bill.

    PRICES is still there for calls that arrive without a cost, and a model in
    neither place is still priced as unknown rather than as free.
    """
    try:
        u = (payload or {}).get("usage") or {}
        for k in ("cost", "total_cost", "cost_usd"):
            v = u.get(k)
            if v is None:
                continue
            f = float(v)
            if f >= 0:
                return round(f, 6)
    except Exception:
        pass
    return None


# WHAT THE CURRENT WORK IS, and whose. Set by whichever route or run is in
# progress; read by the recorder when a call happens.
#
# Module-level rather than thread-local ON PURPOSE: image batches and generation
# runs work on worker threads, and a thread-local set on the request thread
# would be invisible to them -- every one of those calls would land in the
# ledger as "unknown", which is precisely the spend worth knowing about.
CONTEXT = {"feature": "", "workspace_id": "", "sku": "", "config_path": ""}


def unnamed_feature():
    """A name for a call that did not name itself.

    "unknown" tells nobody anything. 8 of the ledger's 46 rows said it, and there
    was no way to find out which of the fourteen call sites they came from --
    which is the one thing a bill needs to be able to answer.

    So an unnamed call is filed under the request that made it: "call from /ask"
    can be looked up; "unknown" cannot. Outside a request -- a background sweep,
    the generator run as a script -- it says that instead.

    This is a safety net, not a substitute for _feature(): a named step is still
    what the report is built to show.
    """
    try:
        from flask import request, has_request_context
        if has_request_context():
            p = str(getattr(request, "path", "") or "").strip()
            if p:
                return "call from %s" % p[:60]
    except Exception:
        pass
    return "call outside a request"


def set_context(feature=None, workspace_id=None, sku=None, config_path=None):
    """Say what is happening, so the next calls can be attributed to it.

    Only the fields given are changed: a route sets the account once, and each
    step then names itself without clearing whose it is.
    """
    for k, v in (("feature", feature), ("workspace_id", workspace_id),
                 ("sku", sku), ("config_path", config_path)):
        if v is not None:
            CONTEXT[k] = v


def install_anthropic_recorder(config_path):
    """Record EVERY Anthropic call, wherever it is made from. Idempotent.

    WHY IT IS PATCHED RATHER THAN WRAPPED AT EACH SITE.
    .messages.create is called from thirteen places across nine files -- listing
    copy, A+ text, PPC advice, optimisation, the supplier import, the chat. Going
    round them one at a time is thirteen chances to miss one, and the failure
    mode of missing one is a dashboard that under-reports and looks reassuring
    while doing it. Nobody audits a number that seems fine.

    Patching the client class instead means a call site that is added tomorrow is
    recorded without anyone remembering to. The trade is that the interception is
    invisible at the call site, which is why it is written down here and why the
    dashboard names the module doing it.

    Never raises: if the library's shape changes, the app must keep working and
    simply record nothing rather than fail to start.
    """
    try:
        from anthropic.resources.messages import Messages
    except Exception:
        try:
            from anthropic.resources import Messages       # older layouts
        except Exception:
            return False
    if getattr(Messages, "_alta_recorded", False):
        return True
    original = Messages.create

    def create(self, *args, **kwargs):
        t0 = time.time()
        model = kwargs.get("model") or (args[0] if args else "") or ""
        cp = CONTEXT.get("config_path") or config_path
        try:
            resp = original(self, *args, **kwargs)
        except Exception as e:
            # A failed call still spent its input tokens. A month of retries
            # must not look free.
            record(cp, feature=CONTEXT.get("feature") or "unknown",
                   provider="anthropic", model=model,
                   workspace_id=CONTEXT.get("workspace_id") or "",
                   ok=False, error=str(e)[:200],
                   sku=CONTEXT.get("sku") or "",
                   ms=int((time.time() - t0) * 1000))
            raise
        i, o = tokens_from_anthropic(resp)
        record(cp, feature=CONTEXT.get("feature") or "unknown",
               provider="anthropic", model=model,
               workspace_id=CONTEXT.get("workspace_id") or "",
               input_tokens=i, output_tokens=o,
               sku=CONTEXT.get("sku") or "",
               ms=int((time.time() - t0) * 1000))
        return resp

    create._alta_original = original
    Messages.create = create
    Messages._alta_recorded = True
    return True


def call_anthropic(client, config_path, *, feature, workspace_id="", sku="",
                   **kwargs):
    """client.messages.create(**kwargs), recorded.

    THE ONE WRAPPER. Anthropic is called from eleven files and none of them
    should learn how to price a token or where the ledger lives; they should say
    what they are doing and let this record it. Re-raises whatever the API
    raises, so behaviour at the call site is unchanged -- but a failed call is
    recorded too, because a run that burns tokens and then errors has still
    spent them.
    """
    t0 = time.time()
    model = kwargs.get("model") or ""
    try:
        resp = client.messages.create(**kwargs)
    except Exception as e:
        record(config_path, feature=feature, provider="anthropic", model=model,
               workspace_id=workspace_id, ok=False, error=str(e)[:200], sku=sku,
               ms=int((time.time() - t0) * 1000))
        raise
    i, o = tokens_from_anthropic(resp)
    record(config_path, feature=feature, provider="anthropic", model=model,
           workspace_id=workspace_id, input_tokens=i, output_tokens=o,
           sku=sku, ms=int((time.time() - t0) * 1000))
    return resp


# ---- reading it back --------------------------------------------------------

def summary(config_path, start=None, end=None, workspace_id=None):
    """Everything the dashboard shows. Totals, and the breakdowns behind them."""
    conn = _db.get_db(config_path)
    where, args = ["1=1"], []
    if start:
        where.append("day>=?"); args.append(start)
    if end:
        where.append("day<=?"); args.append(end)
    if workspace_id:
        where.append("workspace_id=?"); args.append(workspace_id)
    w = " AND ".join(where)

    def rows(sql, extra=()):
        return [dict(r) for r in conn.execute(sql, tuple(args) + tuple(extra))]

    tot = conn.execute(
        "SELECT COUNT(*) calls, SUM(input_tokens) tin, SUM(output_tokens) tout, "
        "       SUM(images) imgs, SUM(cost_usd) cost, "
        "       SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END) unpriced, "
        "       SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) failed "
        "FROM ai_usage WHERE " + w, tuple(args)).fetchone()

    return {
        "calls": (tot["calls"] or 0),
        "input_tokens": (tot["tin"] or 0),
        "output_tokens": (tot["tout"] or 0),
        "images": (tot["imgs"] or 0),
        "cost_usd": (round(tot["cost"], 4) if tot["cost"] is not None else 0.0),
        # How much of the picture is missing, stated rather than absorbed.
        "unpriced_calls": (tot["unpriced"] or 0),
        # A failed call still spent its input tokens; counted, and shown, so a
        # month of retries does not look free.
        "failed_calls": (tot["failed"] or 0),
        "by_account": rows(
            "SELECT workspace_id, COUNT(*) calls, SUM(cost_usd) cost, "
            "       SUM(input_tokens+output_tokens) tokens, SUM(images) images "
            "FROM ai_usage WHERE " + w + " GROUP BY workspace_id "
            "ORDER BY cost DESC NULLS LAST"),
        "by_feature": rows(
            "SELECT feature, COUNT(*) calls, SUM(cost_usd) cost, "
            "       SUM(input_tokens+output_tokens) tokens, SUM(images) images "
            "FROM ai_usage WHERE " + w + " GROUP BY feature "
            "ORDER BY cost DESC NULLS LAST"),
        "by_model": rows(
            "SELECT model, provider, COUNT(*) calls, SUM(cost_usd) cost, "
            "       SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END) unpriced "
            "FROM ai_usage WHERE " + w + " GROUP BY model, provider "
            "ORDER BY cost DESC NULLS LAST"),
        "daily": rows(
            "SELECT day, SUM(cost_usd) cost, COUNT(*) calls "
            "FROM ai_usage WHERE " + w + " GROUP BY day ORDER BY day"),
        # The cross-tab the question is really about: which account, doing what.
        "by_account_feature": rows(
            "SELECT workspace_id, feature, COUNT(*) calls, SUM(cost_usd) cost "
            "FROM ai_usage WHERE " + w + " GROUP BY workspace_id, feature "
            "ORDER BY cost DESC NULLS LAST"),
    }
