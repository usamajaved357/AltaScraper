"""api/amazon_messaging.py -- the only place this app messages a buyer.

WHAT AMAZON ALLOWS, AND WHAT IT DOES NOT
There is no free-form buyer messaging in SP-API. Amazon publishes a fixed set of
message TYPES, decides per order which of them may be sent, and rejects anything
else. domain/daily_check.py already says as much in its own words: "the Messaging
API only says what you are ALLOWED to send."

So nothing here composes a message of its own. It asks Amazon what is permitted
for one order, and can send only those.

THE ACTION NAME IS THE ENDPOINT. THAT IS NOT A DETAIL.
Amazon's actions response gives each permitted action a NAME and an href:

    "name": "confirmOrderDetails"
    "href": "/messaging/v1/orders/{id}/messages/confirmOrderDetails"

The python-amazon-sp-api client names its methods differently, and at least one
of them does NOT line up:

    create_confirm_order_details    -> /messages/confirmOrderDetails    matches
    create_unexpected_problem       -> /messages/unexpectedProblem      matches
    create_negative_feedback_removal-> /messages/negativeFeedbackRemoval

    ...while the action Amazon actually offered on a live order was named
    "updateFeedback", whose href is /messages/updateFeedback.

Those are different endpoints. Mapping "updateFeedback" onto the negative
feedback method by their similar English would POST to a path Amazon never
authorised for that order -- a guess about a WRITE that reaches a customer,
which is precisely what CLAUDE.md Rule 4 forbids.

So the mapping is not written by hand. _senders() reads the library's own
@sp_endpoint decorators and matches on the LAST PATH SEGMENT, so an action can
only be sent through a method that posts to the endpoint of the same name. An
action with no exact match is reported as unsendable, with the reason, rather
than sent through the nearest-looking thing.

SENDING IS GATED TWICE
    1. the action must be one Amazon listed as permitted FOR THIS ORDER, checked
       again at send time and not trusted from whatever the page was holding
    2. it must have an exact endpoint match

Neither gate is a UI concern. A screen cannot talk anyone past them.
"""
import re


def _senders():
    """{action name -> bound method name}, read from the client's own paths.

    Built by inspection rather than typed out, so a library upgrade that moves
    an endpoint cannot silently leave this file pointing at the old one.
    """
    import inspect

    from sp_api.api import Messaging

    out = {}
    try:
        src = inspect.getsource(Messaging)
    except Exception:
        return out
    # Each POST method is preceded by its own @sp_endpoint("...path...").
    for m in re.finditer(
            r'@sp_endpoint\(\s*["\']([^"\']+)["\'][^)]*method\s*=\s*["\']POST["\'][^)]*\)\s*'
            r'def\s+(\w+)\s*\(', src, re.S):
        path, method = m.group(1), m.group(2)
        seg = path.rstrip("/").rsplit("/", 1)[-1]
        if seg and "{" not in seg:
            out[seg] = method
    return out


def actions_for(creds, marketplace, order_id):
    """What Amazon permits on this order, with each action's schema.

    Read-only. -> {"ok": True, "actions": [...]} or {"ok": False, "error": ...}.
    Never raises: "we could not ask" and "nothing is permitted" are different
    answers and a screen has to be able to tell them apart.
    """
    try:
        from sp_api.api import Messaging
        from sp_api.base import Marketplaces
        enum = getattr(Marketplaces, str(marketplace).upper(), Marketplaces.UK)
        got = Messaging(credentials=creds, marketplace=enum) \
            .get_messaging_actions_for_order(str(order_id))
        payload = got.payload if hasattr(got, "payload") else got
    except Exception as e:
        return {"ok": False, "actions": [],
                "error": "%s: %s" % (type(e).__name__, str(e)[:250])}

    senders = _senders()
    out = []
    for a in ((payload or {}).get("_embedded") or {}).get("actions") or []:
        schema = (a.get("_embedded") or {}).get("schema") or {}
        name = str(schema.get("name")
                   or ((a.get("_links") or {}).get("self") or {}).get("name") or "")
        if not name:
            continue
        props = schema.get("properties") or {}
        # Only the fields a person has to fill in. Amazon's schemas for these
        # are shallow -- a single rawMessageBody, or nothing at all.
        fields = []
        for k, v in props.items():
            fields.append({
                "name": k,
                "type": v.get("type") or "string",
                "title": v.get("title") or v.get("description") or k,
                "max_length": v.get("maxLength"),
                "enum": v.get("enum"),
                "required": k in (schema.get("required") or []),
            })
        # Amazon can list an action and disable it -- "you may only send this
        # once per order" is expressed that way. Sendable means BOTH that it is
        # not disabled and that we have its exact endpoint.
        disabled = bool(schema.get("disabled"))
        why = ""
        if disabled:
            why = str(schema.get("disabledReason") or
                      "Amazon has disabled this action for this order.")
        elif name not in senders:
            why = ("This app has no verified endpoint for '%s'. It is not sent "
                   "through a similarly-named one, because that would post to "
                   "an endpoint Amazon did not authorise for this order." % name)
        out.append({
            "name": name,
            "title": schema.get("title") or name,
            "description": schema.get("description") or "",
            "fields": fields,
            "required": schema.get("required") or [],
            "sendable": (not disabled) and (name in senders),
            "why_not": why,
        })
    return {"ok": True, "actions": out}


def send(creds, marketplace, order_id, action, values):
    """Send ONE permitted message. -> {"ok": bool, ...}. Never raises.

    `values` is what the person typed, keyed by the schema's own field names.
    Nothing is added to it and nothing is invented: a message this app composed
    on its own behalf would be a message the seller never wrote.
    """
    order_id = str(order_id or "").strip()
    action = str(action or "").strip()
    if not order_id or not action:
        return {"ok": False, "error": "an order and an action are both needed"}

    # GATE 1 -- Amazon must permit it FOR THIS ORDER, asked again now. The page
    # may have been open for an hour, and "you may only send this once per
    # order" becomes true the moment somebody else sends it.
    perm = actions_for(creds, marketplace, order_id)
    if not perm.get("ok"):
        return {"ok": False, "error": ("Amazon could not be asked whether this "
                                       "message is allowed: %s"
                                       % perm.get("error"))}
    match = next((a for a in perm["actions"] if a["name"] == action), None)
    if not match:
        return {"ok": False, "error": (
            "Amazon does not permit '%s' on this order. Permitted right now: %s"
            % (action, ", ".join(a["name"] for a in perm["actions"]) or "nothing"))}
    if not match["sendable"]:
        return {"ok": False, "error": match["why_not"] or "not sendable"}

    # GATE 2 -- an exact endpoint, never a similar one.
    senders = _senders()
    method_name = senders.get(action)
    if not method_name:
        return {"ok": False, "error": (
            "This app has no verified endpoint for '%s'." % action)}

    # Only the fields Amazon's own schema declares, and every required one.
    body = {}
    for f in match["fields"]:
        v = (values or {}).get(f["name"])
        if v is None or str(v).strip() == "":
            if f["required"]:
                return {"ok": False,
                        "error": "%s is required." % (f["title"] or f["name"])}
            continue
        v = str(v)
        if f.get("max_length") and len(v) > int(f["max_length"]):
            return {"ok": False, "error": (
                "%s is %d characters; Amazon allows %d."
                % (f["title"] or f["name"], len(v), int(f["max_length"])))}
        body[f["name"]] = v

    try:
        from sp_api.api import Messaging
        from sp_api.base import Marketplaces
        enum = getattr(Marketplaces, str(marketplace).upper(), Marketplaces.UK)
        client = Messaging(credentials=creds, marketplace=enum)
        fn = getattr(client, method_name)
        res = fn(order_id, body=body)
        payload = res.payload if hasattr(res, "payload") else res
    except Exception as e:
        return {"ok": False,
                "error": "Amazon refused the message: %s: %s"
                         % (type(e).__name__, str(e)[:300])}
    return {"ok": True, "action": action, "order_id": order_id,
            "sent": body, "response": payload}
