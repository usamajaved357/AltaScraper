"""domain/buyer_inbox.py -- the messages buyers send, read from the seller's mailbox.

    Owner, 30 Sep 2026: "add the customer messages section in the app, if i
    receive any message i should be able to see it in the app".

WHERE THEY COME FROM. Amazon's SP-API cannot read buyer messages (see
api/imap_mailbox.py). Seller Central emails every one of them to the address
set under Notification Preferences -> Messaging -> Buyer Messages. Each comes
from a unique alias at marketplace.amazon.<country> -- e.g.
abc123@marketplace.amazon.co.uk -- with the order number in the subject. So
this module reads that mailbox (through api/imap_mailbox, read-only), keeps
ONLY mail from such an alias, and files it under the order it is about.

WHAT IS KEPT. The sender alias, subject, a plain-text body (HTML stripped,
attachments dropped, capped), the order id, the marketplace (from the alias's
domain) and when it arrived. Nothing else from the mailbox is stored: a message
from any other sender is dropped before it is looked at further, so the
seller's personal mail never lands in this database.

WHAT "READ" MEANS. read_at is this app's own flag. The mailbox is never
changed -- a message opened here is still unread in Gmail.

ONE ACCOUNT, ONE MAILBOX. Every row carries the workspace it was fetched for,
and every read filters on it. message_id is unique PER WORKSPACE, so the same
email forwarded into two accounts' mailboxes is two rows, never one row shared.

FAILURES ARE RECORDED, never swallowed: each check writes last_ok_at or
last_error to buyer_inbox_status, and the screen shows it.

SENDING IS NOT HERE. Replying reaches a customer and waits for the owner
(phase 2). The app's existing SENT log (buyer_messages, written by
/returns/message) is read here only so a thread can show it.
"""
import datetime
import email
import hashlib
import re
from email import policy as _policy
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

from data import db as _db

# NNN-NNNNNNN-NNNNNNN -- every Amazon order id.
ORDER_RE = re.compile(r"(?<!\d)(\d{3}-\d{7}-\d{7})(?!\d)")

# The buyer-alias domain's country part -> the app's marketplace code. Also
# the one table the Seller Central link is built from (reply_url), so the two
# cannot disagree about which country a domain is.
TLD_MARKET = {
    "co.uk": "UK", "com": "US", "ca": "CA", "com.mx": "MX", "com.br": "BR",
    "de": "DE", "fr": "FR", "it": "IT", "es": "ES", "nl": "NL", "se": "SE",
    "pl": "PL", "com.be": "BE", "com.tr": "TR", "ae": "AE", "sa": "SA",
    "eg": "EG", "in": "IN", "co.jp": "JP", "com.au": "AU", "sg": "SG",
}
_ALIAS_RE = re.compile(r"^[^@\s]+@marketplace\.amazon\.([a-z.]+)$", re.I)

BODY_MAX = 20000          # characters of text kept per message
FIRST_LOOK_DAYS = 30      # how far back the very first check reads
SNIPPET = 140

KIND = "buyer_message"    # the bell's notification type


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt):
    return dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")


# ---- reading one email -----------------------------------------------------

def marketplace_of(address):
    """"UK" for an alias @marketplace.amazon.co.uk; "" for anything else."""
    m = _ALIAS_RE.match(str(address or "").strip())
    if not m:
        return ""
    return TLD_MARKET.get(m.group(1).lower(), "")


def reply_url(marketplace):
    """Seller Central's message inbox for that marketplace ("" if unknown).
    NOT VERIFIED against a live Seller Central for every country."""
    mk = str(marketplace or "").upper()
    for tld, code in TLD_MARKET.items():
        if code == mk:
            return "https://sellercentral.amazon.%s/messaging/inbox" % tld
    return ""


class _Text(HTMLParser):
    """HTML to text: tags dropped, script/style dropped with their content,
    block tags become line breaks. Nothing is ever rendered from HTML."""
    _BLOCK = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table", "hr"}
    _SKIP = {"script", "style", "head", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self.skip += 1
        elif tag in self._BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self.skip:
            self.skip -= 1
        elif tag in self._BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(html):
    p = _Text()
    try:
        p.feed(str(html or ""))
        p.close()
    except Exception:
        return re.sub(r"<[^>]*>", " ", str(html or ""))
    return "".join(p.out)


def _tidy(text):
    lines = [re.sub(r"[ \t ]+", " ", ln).strip()
             for ln in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out[:BODY_MAX]


def _part_text(part):
    """A text part as str. A charset Python does not know is read as UTF-8
    with replacement characters rather than failing the whole message."""
    try:
        return part.get_content()
    except Exception:
        raw = part.get_payload(decode=True) or b""
        try:
            return raw.decode(part.get_content_charset() or "utf-8", "replace")
        except LookupError:
            return raw.decode("utf-8", "replace")


def text_body(msg):
    """The message as plain text. text/plain preferred; HTML stripped;
    attachments never read."""
    plain, html = [], []
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment" or part.get_filename():
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain":
            plain.append(str(_part_text(part) or ""))
        elif ctype == "text/html":
            html.append(str(_part_text(part) or ""))
    # An EMPTY text part is not a text body: some mail carries a blank
    # text/plain beside the real HTML one.
    text = "\n".join(plain)
    if text.strip():
        return _tidy(text)
    return _tidy(html_to_text("\n".join(html)))


def parse(raw):
    """One email's bytes -> a message dict, or None when it is not a buyer
    message (any sender that is not an Amazon marketplace alias)."""
    try:
        msg = email.message_from_bytes(bytes(raw or b""), policy=_policy.default)
    except Exception:
        return None
    frm = parseaddr(str(msg.get("From") or ""))[1].strip().lower()
    mkt = marketplace_of(frm)
    if not mkt:
        return None                     # not Amazon's: never stored, never read
    subject = str(msg.get("Subject") or "").strip()[:300]
    try:
        when = parsedate_to_datetime(str(msg.get("Date") or ""))
        if when.tzinfo is None:
            when = when.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        when = _now()
    # NEVER LATER THAN NOW. The Date header is the sender's claim; a date in
    # 2099 would become the next check's start day and nothing newer would
    # ever be found.
    when = min(when, _now())
    body = text_body(msg)
    m = ORDER_RE.search(subject) or ORDER_RE.search(body)
    mid = str(msg.get("Message-ID") or "").strip()[:300]
    if not mid:
        # No id: one made from the email's own bytes, so a second check
        # recognises the same email whatever it says about itself.
        mid = "sha1:" + hashlib.sha1(bytes(raw or b"")).hexdigest()
    return {"message_id": mid, "from_alias": frm, "marketplace": mkt,
            "order_id": m.group(1) if m else "", "subject": subject,
            "body_text": body, "received_at": _iso(when)}


# ---- storage ----------------------------------------------------------------

def store(config_path, workspace_id, m):
    """Insert one parsed message for one account. True when it was NEW."""
    if not workspace_id or not m:
        return False
    conn = _db.get_db(config_path)
    cur = conn.execute(
        "INSERT OR IGNORE INTO buyer_inbox (workspace_id, marketplace, order_id, "
        " message_id, from_alias, subject, body_text, received_at, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (str(workspace_id), m.get("marketplace") or "", m.get("order_id") or "",
         m["message_id"], m.get("from_alias") or "", m.get("subject") or "",
         m.get("body_text") or "", m.get("received_at") or "", _iso(_now())))
    conn.commit()
    return (cur.rowcount or 0) > 0


def status(config_path, workspace_id):
    """The last check's outcome for this account, or {} if never checked."""
    row = _db.get_db(config_path).execute(
        "SELECT last_ok_at, last_error, last_error_at, last_seen, checked_at "
        "FROM buyer_inbox_status WHERE workspace_id=?",
        (str(workspace_id),)).fetchone()
    return dict(row) if row else {}


def _set_status(config_path, workspace_id, ok, error="", last_seen=None):
    conn = _db.get_db(config_path)
    now = _iso(_now())
    conn.execute("INSERT OR IGNORE INTO buyer_inbox_status (workspace_id) VALUES (?)",
                 (str(workspace_id),))
    if ok:
        conn.execute("UPDATE buyer_inbox_status SET last_ok_at=?, last_error='', "
                     "checked_at=?, last_seen=COALESCE(?, last_seen) "
                     "WHERE workspace_id=?", (now, now, last_seen, str(workspace_id)))
    else:
        conn.execute("UPDATE buyer_inbox_status SET last_error=?, last_error_at=?, "
                     "checked_at=? WHERE workspace_id=?",
                     (str(error or "unknown error")[:500], now, now, str(workspace_id)))
    conn.commit()


# ---- the check ----------------------------------------------------------------

def _since(config_path, workspace_id):
    """The day to search from: the newest message already held, else 30 days
    back. A DAY, because IMAP SINCE is a date; repeats are dropped by the
    unique message id."""
    st = status(config_path, workspace_id)
    seen = str(st.get("last_seen") or "")
    try:
        return datetime.date.fromisoformat(seen[:10])
    except ValueError:
        return (_now() - datetime.timedelta(days=FIRST_LOOK_DAYS)).date()


def _announce(config_path, workspace_id, m):
    """One bell entry per new message. The bell's failure is said, not hidden."""
    from domain import notify as _notify
    title = ("Buyer message about order %s" % m["order_id"]) if m.get("order_id") \
        else "Buyer message"
    snippet = (m.get("body_text") or "").replace("\n", " ")[:SNIPPET]
    got = _notify.record(config_path, workspace_id, KIND, title,
                         "\n".join(x for x in (m.get("subject"), snippet) if x),
                         marketplace=m.get("marketplace") or "")
    if got is None:
        print("[buyer_inbox] the bell could not record a message for %s"
              % workspace_id, flush=True)


def poll(config_path, account, imap_factory=None):
    """Check ONE account's mailbox now. -> {"ok", "new", "seen", "error"}.

    Never raises: the outcome is written to buyer_inbox_status either way, so
    one account's broken mailbox cannot stop the job reaching the next.
    """
    ws = str((account or {}).get("id") or "")
    try:
        return _poll_once(config_path, account, imap_factory)
    except Exception as e:
        err = "The check stopped unexpectedly: %s" % str(e)[:300]
        try:
            _set_status(config_path, ws, False, err)
        except Exception as e2:
            print("[buyer_inbox] could not record the failure for %s: %s"
                  % (ws, str(e2)[:200]), flush=True)
        return {"ok": False, "new": 0, "error": err}


def _poll_once(config_path, account, imap_factory=None):
    from api import imap_mailbox as _imap
    from domain import buyer_mailbox as _box
    ws = str((account or {}).get("id") or "")
    if not ws:
        return {"ok": False, "new": 0, "error": "no account"}
    if not _box.is_configured(account):
        return {"ok": False, "new": 0, "skipped": True,
                "error": "no mailbox is connected for this account"}
    host, port, user, password = _box.credentials(account)
    if not password:
        err = ("The stored mailbox password could not be read (the encryption "
               "key changed?). Enter it again in Settings.")
        _set_status(config_path, ws, False, err)
        return {"ok": False, "new": 0, "error": err}
    since = _since(config_path, ws)
    try:
        raws = _imap.fetch_since(host, port, user, password, since,
                                 factory=imap_factory)
    except Exception as e:
        err = str(e).replace(password, "•••")[:500]
        _set_status(config_path, ws, False, err)
        return {"ok": False, "new": 0, "error": err}
    new, seen, newest, bad = [], 0, None, []
    for raw in raws:
        # ONE BAD EMAIL IS ONE BAD EMAIL. A message that cannot be read or
        # stored is counted and said, and the rest are still filed.
        try:
            m = parse(raw)
            if not m:
                continue
            seen += 1
            if not newest or m["received_at"] > newest:
                newest = m["received_at"]
            if store(config_path, ws, m):
                new.append(m)
        except Exception as e:
            bad.append(str(e)[:120])
    for m in new:
        _announce(config_path, ws, m)
    _set_status(config_path, ws, True, last_seen=newest)
    if bad:
        _set_status(config_path, ws, False,
                    "%d message%s could not be read (%s)"
                    % (len(bad), "" if len(bad) == 1 else "s", bad[0]))
    return {"ok": True, "new": len(new), "seen": seen, "unreadable": len(bad)}


def poll_all(config_path, conf, workspace_id=None, imap_factory=None):
    """The 10-minute job: every account with a mailbox connected."""
    from domain import accounts as _acc
    from domain import buyer_mailbox as _box
    done, errors, new = [], [], 0
    for a in (_acc.load_accounts(conf or {}, config_path, persist=False) or []):
        aid = str(a.get("id") or "")
        if not aid or (workspace_id and aid != workspace_id):
            continue
        if not _box.is_configured(a):
            continue
        r = poll(config_path, a, imap_factory=imap_factory)
        done.append(aid)
        new += r.get("new") or 0
        if not r.get("ok"):
            errors.append({"workspace": aid, "error": r.get("error")})
    return {"checked": done, "new": new, "errors": errors}


# ---- reading it back ------------------------------------------------------------

def _thread_key(row):
    return row.get("order_id") or ("from:" + (row.get("from_alias") or ""))


def threads(config_path, workspace_id, limit=300):
    """One entry per order (or per sender when no order id), newest first."""
    rows = [dict(r) for r in _db.get_db(config_path).execute(
        "SELECT id, marketplace, order_id, from_alias, subject, body_text, "
        " received_at, read_at FROM buyer_inbox WHERE workspace_id=? "
        "ORDER BY received_at DESC, id DESC", (str(workspace_id),))]
    by = {}
    order = []
    for r in rows:
        k = _thread_key(r)
        t = by.get(k)
        if t is None:
            t = {"key": k, "order_id": r["order_id"], "from_alias": r["from_alias"],
                 "marketplace": r["marketplace"], "subject": r["subject"],
                 "snippet": (r["body_text"] or "").replace("\n", " ")[:SNIPPET],
                 "last_at": r["received_at"], "count": 0, "unread": 0,
                 "reply_url": reply_url(r["marketplace"])}
            by[k] = t
            order.append(k)
        t["count"] += 1
        if not r["read_at"]:
            t["unread"] += 1
    return [by[k] for k in order[:int(limit)]]


def unread_count(config_path, workspace_id):
    return _db.get_db(config_path).execute(
        "SELECT COUNT(*) FROM buyer_inbox WHERE workspace_id=? AND "
        "(read_at IS NULL OR read_at='')", (str(workspace_id),)).fetchone()[0]


def sent_for(config_path, workspace_id, order_id, limit=20):
    """What THIS APP has sent about an order (buyer_messages), newest first.
    The one reader of that table (the returns screen uses it too)."""
    if not order_id:
        return []
    return [dict(r) for r in _db.get_db(config_path).execute(
        "SELECT action, body, ok, error, sent_by, sent_at "
        "FROM buyer_messages WHERE workspace_id=? AND order_id=? "
        "ORDER BY id DESC LIMIT ?", (str(workspace_id), str(order_id), int(limit)))]


def _where(workspace_id, order_id="", from_alias=""):
    if order_id:
        return "workspace_id=? AND order_id=?", [str(workspace_id), str(order_id)]
    return ("workspace_id=? AND order_id='' AND from_alias=?",
            [str(workspace_id), str(from_alias).lower()])


def thread(config_path, workspace_id, order_id="", from_alias=""):
    """Every message in one thread, oldest first: the buyer's, and what the
    app sent (kind "app"). [] when the thread is not this account's."""
    if not (order_id or from_alias):
        return []
    sql, args = _where(workspace_id, order_id, from_alias)
    got = [dict(r, kind="buyer") for r in _db.get_db(config_path).execute(
        "SELECT id, marketplace, order_id, from_alias, subject, body_text, "
        " received_at AS at, read_at FROM buyer_inbox WHERE " + sql, args)]
    for s in sent_for(config_path, workspace_id, order_id):
        got.append({"kind": "app", "action": s.get("action"), "body_text": s.get("body"),
                    "ok": s.get("ok"), "error": s.get("error"),
                    "sent_by": s.get("sent_by"), "at": s.get("sent_at")})
    got.sort(key=lambda m: str(m.get("at") or ""))
    return got


def mark_read(config_path, workspace_id, order_id="", from_alias="", everything=False):
    """This app's read flag only; the mailbox is not touched. -> rows changed."""
    now = _iso(_now())
    conn = _db.get_db(config_path)
    if everything:
        sql, args = "workspace_id=?", [str(workspace_id)]
    elif order_id or from_alias:
        sql, args = _where(workspace_id, order_id, from_alias)
    else:
        return 0
    n = conn.execute("UPDATE buyer_inbox SET read_at=? WHERE (read_at IS NULL OR "
                     "read_at='') AND " + sql, [now] + args).rowcount
    conn.commit()
    return n or 0
