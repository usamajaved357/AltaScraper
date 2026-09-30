"""api/imap_mailbox.py -- read a mailbox over IMAP, and never change it.

WHY A MAILBOX AT ALL. Amazon's SP-API cannot read buyer messages: the Messaging
API only SENDS Amazon's fixed templates, and Amazon's own developer support
says "We currently do not provide a functionality to let developer get the
buyer Messages". What Seller Central does do is email every buyer message to
the address set under Notification Preferences -> Messaging -> Buyer Messages.
So the app reads that mailbox (domain/buyer_inbox.py decides what to keep).

READ-ONLY, THREE WAYS OVER. The seller's mailbox is theirs; nothing here may
mark a message read, move it or delete it:
  * the folder is opened with EXAMINE (select(readonly=True)), which the server
    itself enforces -- a STORE would be refused;
  * messages are fetched with BODY.PEEK[], which does not set \\Seen;
  * this module has no call to store, copy, move, expunge or append.

ONLY AMAZON'S MAIL IS DOWNLOADED. The search asks the server for messages
FROM "marketplace.amazon." -- the buyer-alias domain -- so personal mail is not
even downloaded. domain/buyer_inbox.py checks the sender again, exactly, before
anything is stored.

NO PASSWORD IN AN ERROR. imaplib's errors quote the server's reply, not the
password, but every message leaving here is scrubbed of it anyway, because an
error string ends up on a screen.
"""
import datetime
import imaplib
import ssl

# What the IMAP server is asked to match in the From header. A substring
# match (RFC 3501 SEARCH FROM), so it covers every marketplace's domain.
FROM_FILTER = "marketplace.amazon."

# At most this many messages per check, OLDEST FIRST. A first check of a busy
# mailbox must not download months of mail in one go; the caller moves its
# start date to the newest one it got, so the rest arrive on the next checks.
FETCH_LIMIT = 200

# At most this much of each message is downloaded (BODY.PEEK[]<0.N>): a buyer's
# words are at the top, and an attached photo must not cost megabytes per check.
MAX_BYTES = 1024 * 1024

TIMEOUT_S = 30


class MailboxError(Exception):
    """Anything that went wrong talking to the mailbox, already scrubbed."""


def _scrub(text, password):
    s = str(text or "")
    if password:
        s = s.replace(str(password), "•••")
    return s[:300]


def _open(host, port, user, password, factory=None):
    """A logged-in connection with INBOX opened READ-ONLY."""
    make = factory or imaplib.IMAP4_SSL
    # THE SERVER'S CERTIFICATE IS CHECKED. imaplib's default context does not
    # verify it, so without this anyone on the path could pose as the mail
    # server and collect the app password.
    conn = make(host, int(port or 993), ssl_context=ssl.create_default_context(),
                timeout=TIMEOUT_S)
    try:
        conn.login(user, password)
    except Exception as e:
        _close(conn)
        raise MailboxError("The mailbox refused the sign-in: %s"
                           % _scrub(e, password))
    typ, _data = conn.select("INBOX", readonly=True)
    if typ != "OK":
        _close(conn)
        raise MailboxError("The inbox could not be opened read-only.")
    return conn


def _close(conn):
    """Log out. A failed logout loses nothing: the session held no changes."""
    try:
        conn.logout()
    except Exception:
        pass          # nothing to lose: the session was read-only


def _imap_date(d):
    return d.strftime("%d-%b-%Y")


def _search(conn, since):
    crit = ["SINCE", _imap_date(since), "FROM", '"%s"' % FROM_FILTER]
    typ, data = conn.search(None, *crit)
    if typ != "OK":
        raise MailboxError("The mailbox would not search for Amazon's messages.")
    raw = (data or [b""])[0] or b""
    return [x for x in raw.split() if x]


def test(host, port, user, password, factory=None, days=30):
    """Sign in, open INBOX read-only and count. Changes nothing.

    -> {"ok": True, "total": n, "amazon_recent": m} or {"ok": False, "error"}.
    """
    try:
        conn = _open(host, port, user, password, factory)
    except MailboxError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": "Could not reach %s:%s -- %s"
                % (host, port, _scrub(e, password))}
    try:
        typ, data = conn.search(None, "ALL")
        total = len(((data or [b""])[0] or b"").split()) if typ == "OK" else None
        since = datetime.date.today() - datetime.timedelta(days=days)
        amazon = len(_search(conn, since))
        return {"ok": True, "total": total, "amazon_recent": amazon, "days": days}
    except Exception as e:
        return {"ok": False, "error": _scrub(e, password)}
    finally:
        _close(conn)


def fetch_since(host, port, user, password, since, factory=None,
                limit=FETCH_LIMIT):
    """The raw RFC 822 bytes of Amazon's messages since `since` (a date).

    The OLDEST `limit` of them (the caller starts the next check from the
    newest it received), each cut at MAX_BYTES. Raises MailboxError, scrubbed.
    """
    try:
        conn = _open(host, port, user, password, factory)
    except MailboxError:
        raise
    except Exception as e:
        raise MailboxError("Could not reach %s:%s -- %s"
                           % (host, port, _scrub(e, password)))
    try:
        ids = _search(conn, since)[:int(limit)]
        out = []
        for mid in ids:
            typ, data = conn.fetch(mid, "(BODY.PEEK[]<0.%d>)" % MAX_BYTES)
            if typ != "OK":
                continue
            for part in (data or []):
                if isinstance(part, tuple) and len(part) >= 2 \
                        and isinstance(part[1], (bytes, bytearray)):
                    out.append(bytes(part[1]))
        return out
    except MailboxError:
        raise
    except Exception as e:
        raise MailboxError(_scrub(e, password))
    finally:
        _close(conn)
