"""domain/notify.py -- send an alert somewhere other than this app's own screen.

    Orbit has Notifications and Connect WhatsApp in its menu. Everything this app
    has ever produced -- stock alerts, monitor alerts, the daily round, and now
    the trackers -- has been IN-APP ONLY, which means it is only seen by someone
    who has already opened the app to look. An alert nobody is looking at is not
    an alert.

NOTHING IS SENT UNTIL SOMEBODY TURNS IT ON.

Delivery is outward-facing and cannot be taken back: a message posted into a
channel is read by whoever is in that channel, and a webhook URL handed to the
wrong place is a small permanent leak. So this module is deliberately inert by
default:

    * no channel exists until one is added
    * a channel does not send until `enabled` is set true
    * no schedule calls anything here; the callers are explicit
    * "send a test" is a separate, obvious action

TWO CHANNELS, ONE SHAPE.

    slack     an Incoming Webhook URL. Posts {"text": ...}, which is what Slack
              accepts with no app, no scopes and no OAuth.
    webhook   a plain POST of the whole event as JSON, for anything else --
              Zapier, Make, n8n, a WhatsApp bridge. Orbit's "Connect WhatsApp"
              is this: WhatsApp's own API needs a Meta business account and a
              vetted template per message, which is not a thing this app can
              set up on someone's behalf, and pretending otherwise would be a
              button that quietly never works.

REPEATING AN ALERT IS HOW A CHANNEL GETS MUTED.

The alerts these feed on are STATES, not events: a rank that is off target is
off target every time anything checks. Sent every check, that is a message every
hour saying the same thing, and the reliable human response is to mute the
channel -- at which point the real one is missed too. So every send carries a
`key`, and a key already sent within QUIET_HOURS is skipped and recorded as
skipped rather than silently dropped.

A FAILED SEND IS LOUD.

Every attempt is written to a small log with its outcome. A notification system
whose failures are invisible is worse than none: it converts "nobody told me"
into "the app told me it was fine".

NO SECRET LEAVES THIS MODULE. The event payload is built from the message the
caller passes. The webhook URL is a credential and is never echoed back to a
screen in full -- see `redact`.
"""
import datetime
import json
import threading

from domain import jsonstore

_LOCK = threading.Lock()
_FILE = "notify.json"

SLACK = "slack"
WEBHOOK = "webhook"
KINDS = (SLACK, WEBHOOK)

# How long the same alert stays quiet after being sent. Six hours: long enough
# that an unchanged problem is not repeated through a working day, short enough
# that one still left tomorrow is raised again.
QUIET_HOURS = 6

# How many delivery attempts to keep. Enough to answer "did it send this
# morning" without the file becoming a database.
MAX_LOG = 200

SENT = "sent"
FAILED = "failed"
SKIPPED = "skipped"
OFF = "off"


def _now():
    return datetime.datetime.now()


def _iso(dt=None):
    return (dt or _now()).strftime("%Y-%m-%d %H:%M:%S")


def _path(config_path):
    return jsonstore.path_beside_config(config_path, _FILE)


def _blank():
    return {"channels": [], "log": [], "sent_keys": {}}


def load(config_path):
    d = jsonstore.read_json(_path(config_path), None)
    if not isinstance(d, dict):
        return _blank()
    for k, empty in (("channels", []), ("log", []), ("sent_keys", {})):
        if not isinstance(d.get(k), type(empty)):
            d[k] = empty
    return d


def _save(config_path, data):
    return jsonstore.write_json_atomic(_path(config_path), data, indent=2)


def redact(url):
    """A webhook URL as it may be SHOWN. Never the whole thing.

    A Slack Incoming Webhook URL is a bearer credential: anyone holding it can
    post into that channel forever. Rendering it on a screen puts it in
    screenshots, in shoulder-surfing range and in any support conversation about
    the screen. Enough is shown to tell two channels apart and no more.
    """
    u = str(url or "")
    if len(u) < 16:
        return "…" if u else ""
    return u[:24] + "…" + u[-4:]


def _norm_channel(c, include_secret=False):
    out = {"id": c.get("id"), "kind": c.get("kind"), "label": c.get("label", ""),
           "enabled": bool(c.get("enabled")), "account": c.get("account", ""),
           "events": list(c.get("events") or []),
           "url_shown": redact(c.get("url")),
           "added_at": c.get("added_at", ""),
           "last_result": c.get("last_result", ""),
           "last_at": c.get("last_at", "")}
    if include_secret:
        out["url"] = c.get("url", "")
    return out


def channels(config_path, account=None, include_secret=False):
    out = []
    for c in load(config_path).get("channels", []):
        if account and str(c.get("account") or "") not in ("", str(account)):
            continue
        out.append(_norm_channel(c, include_secret))
    return out


def add_channel(config_path, kind, url, label="", account="", events=None,
                enabled=False):
    """Add a place to send to. NOT enabled unless explicitly asked for.

    Defaulting `enabled` to False is the whole safety posture of this module:
    adding an address and starting to broadcast to it are two decisions, and
    conflating them means a mistyped URL begins receiving immediately.
    """
    kind = str(kind or "").strip().lower()
    url = str(url or "").strip()
    if kind not in KINDS:
        return {"ok": False, "error": "Unknown channel type: %s" % kind}
    if not url.lower().startswith("https://"):
        # http:// would send the payload, and on Slack the credential itself, in
        # clear text across the network.
        return {"ok": False, "error": "The address must start with https://"}
    if kind == SLACK and "hooks.slack.com" not in url:
        return {"ok": False,
                "error": "That does not look like a Slack Incoming Webhook URL "
                         "(it should be on hooks.slack.com)."}
    with _LOCK:
        data = load(config_path)
        arr = data.setdefault("channels", [])
        nid = 1 + max([int(c.get("id") or 0) for c in arr] or [0])
        c = {"id": nid, "kind": kind, "url": url, "label": label.strip(),
             "account": str(account or ""), "events": list(events or []),
             "enabled": bool(enabled), "added_at": _iso()}
        arr.append(c)
        _save(config_path, data)
        return {"ok": True, "channel": _norm_channel(c)}


def set_channel(config_path, channel_id, enabled=None, label=None, events=None):
    with _LOCK:
        data = load(config_path)
        for c in data.get("channels", []):
            if str(c.get("id")) != str(channel_id):
                continue
            if enabled is not None:
                c["enabled"] = bool(enabled)
            if label is not None:
                c["label"] = str(label).strip()
            if events is not None:
                c["events"] = list(events or [])
            _save(config_path, data)
            return {"ok": True, "channel": _norm_channel(c)}
    return {"ok": False, "error": "No such channel."}


def remove_channel(config_path, channel_id):
    with _LOCK:
        data = load(config_path)
        before = len(data.get("channels", []))
        data["channels"] = [c for c in data.get("channels", [])
                            if str(c.get("id")) != str(channel_id)]
        _save(config_path, data)
        return {"ok": True, "removed": before - len(data["channels"])}


def _log(config_path, entry):
    with _LOCK:
        data = load(config_path)
        lg = data.setdefault("log", [])
        lg.append(entry)
        if len(lg) > MAX_LOG:
            del lg[:len(lg) - MAX_LOG]
        for c in data.get("channels", []):
            if str(c.get("id")) == str(entry.get("channel_id")):
                c["last_result"] = entry.get("result")
                c["last_at"] = entry.get("at")
        _save(config_path, data)


def log(config_path, limit=50):
    lg = load(config_path).get("log", [])
    return list(reversed(lg[-limit:])) if limit else list(reversed(lg))


def _recently_sent(config_path, key, quiet_hours):
    if not key:
        return False
    seen = load(config_path).get("sent_keys", {}) or {}
    when = seen.get(key)
    if not when:
        return False
    try:
        t = datetime.datetime.strptime(when, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return False
    return (_now() - t) < datetime.timedelta(hours=quiet_hours)


def _mark_sent(config_path, key):
    if not key:
        return
    with _LOCK:
        data = load(config_path)
        seen = data.setdefault("sent_keys", {})
        seen[key] = _iso()
        # Keys older than a week cannot silence anything, and left alone this
        # map is the one part of the file that would grow forever.
        cutoff = _now() - datetime.timedelta(days=7)
        for k in [k for k, v in seen.items()
                  if _older_than(v, cutoff)]:
            seen.pop(k, None)
        _save(config_path, data)


def _older_than(when, cutoff):
    try:
        return datetime.datetime.strptime(when, "%Y-%m-%d %H:%M:%S") < cutoff
    except (TypeError, ValueError):
        return True


def _post(url, payload, timeout=12):
    """POST JSON. Returns (ok, detail). Never raises.

    urllib rather than requests: this is one POST and adding a dependency for it
    would be the tail wagging the dog.
    """
    import urllib.error
    import urllib.request
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = getattr(r, "status", 200)
            text = r.read().decode("utf-8", "replace")[:200]
        return (200 <= int(code) < 300), "HTTP %s %s" % (code, text.strip())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        # The URL is a credential; it must not end up in a log line that a
        # screen then renders.
        return False, "HTTP %s %s" % (e.code, detail.strip())
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e)[:160])


def _payload(kind, subject, lines, event, account):
    if kind == SLACK:
        text = "*%s*" % subject
        if lines:
            text += "\n" + "\n".join("• %s" % str(x) for x in lines)
        if account:
            text += "\n_%s_" % account
        return {"text": text}
    # The generic webhook gets the parts rather than a rendered string, so
    # whatever is on the other end can lay it out itself.
    return {"event": event, "account": account, "subject": subject,
            "lines": [str(x) for x in (lines or [])], "at": _iso()}


def send(config_path, subject, lines=None, event="", account="", key="",
         quiet_hours=QUIET_HOURS, force=False):
    """Send one notification to every enabled channel that wants this event.

    Returns {"ok", "sent", "skipped", "failed", "results"}. `ok` is True when
    nothing FAILED -- sending nothing because nothing is configured is a
    perfectly good outcome and must not read as an error, or every caller would
    have to special-case "no channels" to avoid showing a scary message.

    `key` is what makes an alert repeatable-but-not-repetitive. Same key inside
    the quiet window: skipped, and recorded as skipped so the log shows the
    system was working rather than appearing to have gone silent.
    """
    res = {"ok": True, "sent": 0, "skipped": 0, "failed": 0, "results": []}
    chans = [c for c in load(config_path).get("channels", [])
             if c.get("enabled")]
    if account:
        chans = [c for c in chans
                 if str(c.get("account") or "") in ("", str(account))]
    if event:
        # An empty events list means "everything"; naming events narrows it.
        chans = [c for c in chans
                 if not c.get("events") or event in (c.get("events") or [])]
    if not chans:
        res["note"] = "No enabled channel is set up to receive this."
        return res
    if key and not force and _recently_sent(config_path, key, quiet_hours):
        res["skipped"] = len(chans)
        res["note"] = ("Already sent within the last %d hours; not repeating it."
                       % quiet_hours)
        for c in chans:
            _log(config_path, {"at": _iso(), "channel_id": c.get("id"),
                               "channel": c.get("label") or c.get("kind"),
                               "event": event, "subject": subject,
                               "result": SKIPPED, "detail": res["note"]})
        return res
    for c in chans:
        ok, detail = _post(c.get("url"),
                           _payload(c.get("kind"), subject, lines, event, account))
        res["results"].append({"channel_id": c.get("id"),
                               "channel": c.get("label") or c.get("kind"),
                               "ok": ok, "detail": detail})
        res["sent" if ok else "failed"] += 1
        if not ok:
            res["ok"] = False
        _log(config_path, {"at": _iso(), "channel_id": c.get("id"),
                           "channel": c.get("label") or c.get("kind"),
                           "event": event, "subject": subject,
                           "result": SENT if ok else FAILED, "detail": detail})
    if res["sent"]:
        _mark_sent(config_path, key)
    return res


def test(config_path, channel_id):
    """Send one obviously-a-test message to ONE channel.

    Ignores `enabled`, on purpose: the point of a test is to check an address
    before trusting it, and requiring it to be switched on first means the first
    real message is also the first message ever sent.
    """
    for c in load(config_path).get("channels", []):
        if str(c.get("id")) != str(channel_id):
            continue
        ok, detail = _post(c.get("url"),
                           _payload(c.get("kind"),
                                    "AltaScraper test message",
                                    ["If you can read this, the connection works.",
                                     "Sent from the Notifications screen."],
                                    "test", c.get("account", "")))
        _log(config_path, {"at": _iso(), "channel_id": c.get("id"),
                           "channel": c.get("label") or c.get("kind"),
                           "event": "test", "subject": "Test message",
                           "result": SENT if ok else FAILED, "detail": detail})
        return {"ok": ok, "detail": detail}
    return {"ok": False, "detail": "No such channel."}
