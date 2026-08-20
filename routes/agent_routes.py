"""routes/agent_routes.py -- the assistant that can actually look.

POST /agent/ask   ask a question about the open account, in plain English
GET  /agent/tools what it is allowed to look at (for the UI, and for auditing)

WHAT THIS IS, IN ONE PARAGRAPH

You type a question. Claude decides which of the app's own read-only screens
would answer it, this file calls those screens, hands the results back, and
Claude writes the answer from what came back. It cannot change anything: every
tool is a GET from a fixed list (domain/agent_tools.py). Nothing here submits
to Amazon, edits a listing, or moves a price.

WHY THE LOOP IS WRITTEN OUT BY HAND

The SDK has a tool runner that would hide it. It is written out here because
three things have to happen between the model asking for a tool and getting an
answer, and all three are the point of the feature:

  * the ACCOUNT is attached server-side, so a question cannot reach another
    account's money however it is phrased;
  * every call is LOGGED with what it asked and what came back, so an answer
    that looks wrong can be traced to the screen it came from;
  * the loop STOPS -- a hard cap on rounds, so a confused model cannot spend
    the owner's credits in a circle.

WHAT IT IS NOT ALLOWED TO SAY
CLAUDE.md rule 8: it must never propose a bid or budget change. It may report
what a campaign did. Choosing a new number is the owner's, and the system
prompt below says so.
"""
import json
import time

from flask import request, jsonify

MODEL = "claude-opus-5"
MAX_ROUNDS = 6          # tool calls, not messages -- see the loop below
MAX_TOKENS = 8000

SYSTEM = """You are the assistant inside AltaScraper, the tool this Amazon \
seller runs their business from. You answer questions about ONE account -- the \
one they have open -- by calling the tools, which read the app's own screens.

HOW TO ANSWER

Plain English first, then the numbers. Short. The owner is not a developer: \
never use a technical term without saying what it means in the same sentence.

Call account_in_view before your first real answer, and name the account, the \
marketplace and the date range you answered for. "Sales were 4,210" is not an \
answer; "jack_uk, UK, 21 July to 19 August: 4,210" is.

WHAT YOU MUST NOT DO

Never invent a number, an ASIN, a SKU or a product name. Every figure in your \
answer must have come from a tool result in this conversation. If you did not \
read it, you do not know it.

If a tool returns an error, or nothing, or says it has too little history, SAY \
THAT. Do not fill the gap with a reasonable-sounding figure, and do not answer \
a money question from memory. A missing answer is useful; a confident wrong one \
is not.

Never convert a currency. Report each marketplace in the currency it sold in \
and say which.

Never propose a new bid or a new budget. You may say what a campaign spent and \
what it returned. Choosing the number is the owner's decision.

You cannot change anything -- you have no tool that writes. If they ask you to \
fix, submit, reprice or relist something, say which screen in the app does it.

MEASURED, OR ESTIMATED

Some results mark which of their fields were counted and which are estimates \
resting on an assumption. Carry that distinction into your answer. Cover, \
thirty-day demand and stock gaps are estimates: they assume the next thirty \
days look like the last. What is on hand, what sold, and what Amazon charged \
are counted.

If a window includes today, say the period is not finished -- comparing a part \
period against a whole one reads as a fall that has not happened.

BEFORE YOU QUOTE A PROFIT FIGURE

Check how much of the catalogue has a cost recorded. profit_by_product and \
sales_summary both report it. A profit worked out while some products have no \
cost is not a small error in one direction -- uncosted units bring revenue and \
no cost, so the margin can only ever be flattered. If any are missing, say how \
many before you say the number.

WHEN TWO FIGURES DISAGREE

Say they disagree and say why, rather than picking one quietly. Revenue on the \
sales screen is what shoppers ORDERED. Money on the finance screen is what \
Amazon actually PAID after cancellations, returns and fees. Both are true and \
they answer different questions; a gap between them is usually not an error.

WHICH PERIOD, EXACTLY

"Last month" means the previous calendar month. "The last 30 days" means the \
last thirty days. They are different periods -- nine days apart in August -- \
and answering one with the other looks right and is not. Name the grain you \
used in the answer, every time.

If a list was trimmed, the result says so. Repeat it rather than summarising \
the visible part as if it were all of it."""


def register(app, *, CONFIG_PATH, _cfg, _active_account=None, _state=None):
    """Attach /agent/*. See the module docstring for the design."""

    def _scope():
        """The account this chat is pinned to. Server-side, always."""
        try:
            acc = (_active_account() or {}) if callable(_active_account) else {}
        except Exception:
            acc = {}
        aid = str(acc.get("id") or (_state or {}).get("active_account_id") or "")
        mkt = str(acc.get("default_marketplace")
                  or (_state or {}).get("active_marketplace") or "").upper()
        import datetime as _dt
        return {
            "account_id": aid,
            "account_name": str(acc.get("name") or acc.get("label") or aid),
            "marketplace": mkt,
            "today": _dt.date.today().isoformat(),
            "note": ("Amazon has no figures for today. A window that ends "
                     "yesterday is the most recent complete one."),
        }

    def _fetch(path, params):
        """Call one of this app's own endpoints, as this same user.

        The incoming cookie is forwarded so the app's permission rules
        (auth/guard.py) apply to the assistant exactly as they apply to the
        person asking. An assistant that could read a screen its user cannot
        open would be a hole, not a feature.
        """
        client = app.test_client()
        headers = {}
        cookie = request.headers.get("Cookie")
        if cookie:
            headers["Cookie"] = cookie
        resp = client.get(path, query_string=params, headers=headers)
        try:
            return resp.status_code, resp.get_json(silent=True)
        except Exception:
            return resp.status_code, None

    @app.route("/agent/tools")
    def agent_tools_list():
        """What the assistant can look at -- for the UI, and for auditing.

        Published deliberately. "An AI is reading my account" is a fair thing
        to be uneasy about; the answer is a list of the fourteen read-only
        screens it can open, which is this.
        """
        from domain import agent_tools as _at
        return jsonify({
            "ok": True,
            "scope": _scope(),
            "read_only": True,
            "model": MODEL,
            "tools": [{"name": t["name"], "reads": t["path"] or "(no screen)",
                       "what": t["description"]} for t in _at.TOOLS],
        })

    @app.route("/agent/ask", methods=["POST"])
    def agent_ask():
        """Answer one question, calling screens as needed.

        Body: {"messages": [{"role": "user"|"assistant", "text": "..."}]}
        Returns the answer plus a TRACE of every screen that was read, so the
        owner can check the answer against the screen rather than trust it.
        """
        from domain import agent_tools as _at
        from domain import ai_usage as _usage

        body = request.get_json(force=True, silent=True) or {}
        history = body.get("messages") or []
        if not history:
            return jsonify({"ok": False, "error": "Ask a question first."}), 400

        cfg = _cfg() if callable(_cfg) else {}
        key = str(cfg.get("anthropic_api_key") or "").strip()
        if not key:
            return jsonify({"ok": False, "error": (
                "No Anthropic key is set. Settings > AI has the field.")}), 400

        try:
            import anthropic
        except ImportError:
            return jsonify({"ok": False, "error": (
                "The anthropic library is not installed here "
                "(pip install anthropic).")}), 500

        scope = _scope()
        if not scope["account_id"]:
            return jsonify({"ok": False, "error": (
                "Open an account first -- the assistant answers about the "
                "account you have open.")}), 400

        messages = []
        for m in history:
            role = "assistant" if m.get("role") == "assistant" else "user"
            text = str(m.get("text") or "").strip()
            if text:
                messages.append({"role": role, "content": text})
        if not messages or messages[0]["role"] != "user":
            return jsonify({"ok": False, "error": "Ask a question first."}), 400

        client = anthropic.Anthropic(api_key=key)
        tools = _at.definitions()
        trace, rounds, spent = [], 0, False
        t0 = time.time()

        try:
            while True:
                # ONE wrapper for every Anthropic call in this app, so the
                # spend ledger sees this feature like it sees the others.
                kw = dict(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEM,
                    thinking={"type": "adaptive"},
                    messages=messages,
                )
                # The last call deliberately carries NO tools, which is what
                # forces an answer out of what has already been read. An empty
                # list is not the same thing as no list -- it is rejected --
                # so the key is left out entirely.
                if not spent:
                    kw["tools"] = tools
                resp = _usage.call_anthropic(
                    client, CONFIG_PATH,
                    feature="assistant",
                    workspace_id=scope["account_id"],
                    **kw)

                if resp.stop_reason != "tool_use":
                    break

                messages.append({"role": "assistant", "content": resp.content})

                # EVERY tool_use block in the turn must be answered, and in ONE
                # user message. Answering only the first is rejected by the API;
                # splitting them across messages teaches the model to stop
                # asking for several at once, which costs a round trip a time.
                asks = [b for b in resp.content if b.type == "tool_use"]
                results = []

                if rounds >= MAX_ROUNDS:
                    # Stop, and tell it why, rather than looping on the owner's
                    # credits. It answers from what it has instead of asking
                    # for a fifteenth screen.
                    stop = ("Stopped: %d screens is the limit for one question. "
                            "Answer from what you have read so far, and say "
                            "which part you could not check." % MAX_ROUNDS)
                    for blk in asks:
                        results.append({"type": "tool_result",
                                        "tool_use_id": blk.id,
                                        "content": stop, "is_error": True})
                    messages.append({"role": "user", "content": results})
                    spent = True
                    continue

                for blk in asks:
                    rounds += 1
                    args = blk.input if isinstance(blk.input, dict) else {}
                    out, is_err = _at.run(blk.name, args,
                                          fetch=_fetch, scope=scope)
                    trace.append({
                        "tool": blk.name,
                        "asked": args,
                        "ok": not is_err,
                        "reads": (_at.BY_NAME.get(blk.name) or {}).get("path"),
                        "error": (out or {}).get("error") if is_err else None,
                    })
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": blk.id,
                        "content": json.dumps(out, default=str)[:60000],
                        "is_error": is_err,
                    })
                messages.append({"role": "user", "content": results})

        except anthropic.RateLimitError:
            return jsonify({"ok": False, "error": (
                "Anthropic is rate limiting us. Wait a moment and ask "
                "again.")}), 429
        except anthropic.AuthenticationError:
            return jsonify({"ok": False, "error": (
                "Anthropic rejected the key in Settings > AI.")}), 400
        except anthropic.APIStatusError as e:
            return jsonify({"ok": False,
                            "error": "Anthropic returned %d: %s"
                                     % (e.status_code, str(e)[:200])}), 502
        except anthropic.APIConnectionError:
            return jsonify({"ok": False, "error": (
                "Could not reach Anthropic. Check the connection.")}), 502
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "%s: %s" % (type(e).__name__,
                                                 str(e)[:200])}), 500

        # A refusal is a real outcome, not a crash -- say which it was.
        if getattr(resp, "stop_reason", "") == "refusal":
            return jsonify({"ok": False, "error": (
                "Claude declined to answer that one."), "trace": trace}), 200

        answer = "\n".join(b.text for b in resp.content
                           if getattr(b, "type", "") == "text").strip()
        return jsonify({
            "ok": True,
            "answer": answer or "(no answer came back)",
            "scope": scope,
            # The receipts. Every screen that was read, in order, so the owner
            # can open the same screen and check rather than take it on trust.
            "trace": trace,
            "rounds": rounds,
            "ms": int((time.time() - t0) * 1000),
            "read_only": True,
        })
