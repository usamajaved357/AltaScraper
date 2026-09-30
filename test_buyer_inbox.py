# -*- coding: utf-8 -*-
"""Customer messages (30 Sep 2026): buyer messages read from the seller's mailbox.

Amazon's API cannot read buyer messages; Seller Central emails them. Pins:
  - only mail from an alias @marketplace.amazon.<country> is stored; personal
    mail and look-alike domains never are
  - the order id is parsed from the subject, else the body; the marketplace
    from the alias domain
  - the mailbox is opened READ-ONLY and fetched with BODY.PEEK[]; nothing is
    ever stored, copied, moved or expunged
  - HTML is stripped (script content dropped), attachments are not read,
    the body is capped
  - idempotent by message id; each NEW message reaches the bell once
  - account A's messages never appear under B; marking read is per account
  - a failed check is recorded on the account's status, without the password
  - the password is sealed at rest when a key is set and NEVER in any reply
  - every route refuses when no account is named; guard + activity entries

SAFE HOWEVER IT IS RUN: its own throwaway config and database, a FAKE mail
server object, no network.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
fails = []

_TMP = tempfile.mkdtemp(prefix="altainbox_")
_CFG = os.path.join(_TMP, "config.json")
json.dump({"anthropic_api_key": "not-a-key", "google_spreadsheet_id": "not-a-sheet",
           "google_service_account_json": os.path.join(_TMP, "none.json"),
           "accounts": [{"id": "ta", "label": "T A", "marketplaces": ["UK", "DE"],
                         "default_marketplace": "UK"},
                        {"id": "tb", "label": "T B", "marketplaces": ["UK"],
                         "default_marketplace": "UK"}]}, open(_CFG, "w"))
os.environ["CONFIG_PATH"] = _CFG
os.environ["ALTASCRAPER_DB"] = os.path.join(_TMP, "t.db")
os.environ["ALTASCRAPER_BACKGROUND"] = "off"

from auth import token_crypto as TC            # noqa: E402
os.environ["ALTA_TOKEN_KEY"] = TC.new_key()

PW = "abcdwxyzsecr3tpw"


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-74s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def mail(frm, subject, body, mid=None, html=None, attach=None, date="Tue, 29 Sep 2026 10:00:00 +0000"):
    from email.message import EmailMessage
    m = EmailMessage()
    m["From"] = frm
    m["To"] = "seller@example.com"
    m["Subject"] = subject
    m["Date"] = date
    if mid:
        m["Message-ID"] = mid
    m.set_content(body)
    if html:
        m.add_alternative(html, subtype="html")
    if attach:
        m.add_attachment(attach.encode("utf-8"), maintype="text", subtype="plain",
                         filename="note.txt")
    return m.as_bytes()


UK = mail("Jane Buyer <abc123xyz@marketplace.amazon.co.uk>",
          "Inquiry from Amazon customer Jane (Order: 202-1234567-7654321)",
          "Hello, where is my parcel?", mid="<m1@amazon>",
          attach="ATTACHMENT-SECRET-TEXT")
PERSONAL = mail("Friend <friend@gmail.com>", "Dinner 202-9999999-9999999",
                "PERSONAL-MAIL-TEXT", mid="<p1@gmail>")
DE = mail("k@marketplace.amazon.de", "Nachricht von Kunde",
          "", mid="<m2@amazon>",
          html="<html><head><style>.x{}</style></head><body><p>Bestellung "
               "305-1111111-2222222</p><script>alert('SCRIPT-TEXT')</script>"
               "<div>Danke &amp; Gruss</div></body></html>")
LOOKALIKE = mail("x@marketplace.amazon.co.uk.evil.example", "Order 202-1234567-7654321",
                 "LOOKALIKE-TEXT", mid="<e1@evil>")
NO_ID = mail("zz@marketplace.amazon.co.uk", "A question", "No order here.")
MAILS = {b"1": UK, b"2": PERSONAL, b"3": DE, b"4": LOOKALIKE, b"5": NO_ID}


class FakeIMAP:
    """Records every call. Returns every mail to any search -- as a server that
    ignored the FROM filter would -- so the domain's own filter is what is tested."""
    last = None

    def __init__(self, host, port, ssl_context=None, timeout=None):
        self.host, self.port, self.log = host, port, []
        self.ssl_context = ssl_context
        FakeIMAP.last = self

    def login(self, user, password):
        self.log.append(("login", user))
        if password != PW:
            import imaplib
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")
        return "OK", [b"ok"]

    def select(self, box="INBOX", readonly=False):
        self.log.append(("select", box, readonly))
        return "OK", [b"5"]

    def search(self, charset, *crit):
        self.log.append(("search",) + tuple(crit))
        return "OK", [b" ".join(sorted(MAILS))]

    def fetch(self, mid, what):
        self.log.append(("fetch", mid, what))
        return "OK", [(b"%s (BODY[] {1}" % mid, MAILS[mid]), b")"]

    def logout(self):
        self.log.append(("logout",))

    def _forbidden(self, name):
        self.log.append(("FORBIDDEN", name))
        return "OK", []

    def store(self, *a):
        return self._forbidden("store")

    def expunge(self, *a):
        return self._forbidden("expunge")

    def copy(self, *a):
        return self._forbidden("copy")

    def append(self, *a):
        return self._forbidden("append")


from domain import buyer_inbox as BI            # noqa: E402
from domain import buyer_mailbox as BM          # noqa: E402
from data import db as DB                       # noqa: E402

print("== parsing one email ==")
m = BI.parse(UK)
check("an Amazon alias is a buyer message", bool(m), True)
check("  order id from the subject", m["order_id"], "202-1234567-7654321")
check("  marketplace from the alias domain", m["marketplace"], "UK")
check("  the attachment is never read", "ATTACHMENT-SECRET-TEXT" in m["body_text"], False)
check("personal mail is not a buyer message", BI.parse(PERSONAL), None)
check("a look-alike domain is not a buyer message", BI.parse(LOOKALIKE), None)
d = BI.parse(DE)
check("HTML-only: order id from the body, marketplace DE", (d["order_id"], d["marketplace"]),
      ("305-1111111-2222222", "DE"))
check("  script and style content dropped, entities decoded",
      ("SCRIPT-TEXT" in d["body_text"], ".x{}" in d["body_text"], "Danke & Gruss" in d["body_text"]),
      (False, False, True))
n = BI.parse(NO_ID)
check("no Message-ID: a stable made-up id, no order", (n["message_id"] == BI.parse(NO_ID)["message_id"],
                                                       n["order_id"]), (True, ""))
check("the body is capped", len(BI._tidy("x" * 50000)), BI.BODY_MAX)
check("reply link for UK", BI.reply_url("UK"), "https://sellercentral.amazon.co.uk/messaging/inbox")

print("== settings: the password sealed at rest, never shown ==")
ok, err, after = BM.save(_CFG, "ta", {"mailbox_user": "seller@example.com",
                                      "mailbox_password": "abcd wxyz secr 3tpw"})
check("saved", (ok, err), (True, ""))
raw_text = open(_CFG, encoding="utf-8").read()
check("the stored value is sealed, not the password", (PW in raw_text, TC.is_sealed(after["mailbox_password"])),
      (False, True))
acc_a = json.load(open(_CFG))["accounts"][0]
check("credentials() unseals it (spaces from Google's display removed)", BM.credentials(acc_a)[3], PW)
check("defaults: imap.gmail.com:993", BM.credentials(acc_a)[:2], ("imap.gmail.com", 993))
pv = BM.public_view(acc_a)
check("public view: set + last four, no password", (pv["has_password"], pv["password_tail"], PW in json.dumps(pv)),
      (True, "3tpw", False))
BM.save(_CFG, "ta", {"mailbox_user": "seller@example.com", "mailbox_password": ""})
check("a blank password keeps the stored one",
      BM.credentials(json.load(open(_CFG))["accounts"][0])[3], PW)
BM.save(_CFG, "ta", {"mailbox_password": "•••• 3tpw"})
check("a masked value is never saved as the password",
      BM.credentials(json.load(open(_CFG))["accounts"][0])[3], PW)
acc_a = json.load(open(_CFG))["accounts"][0]

print("== a check: read-only, Amazon's mail only, idempotent ==")
r = BI.poll(_CFG, acc_a, imap_factory=FakeIMAP)
check("first check: 3 new (UK, DE, no-order), personal + look-alike dropped", (r["ok"], r["new"]), (True, 3))
log = FakeIMAP.last.log
check("INBOX opened read-only", ("select", "INBOX", True) in log, True)
check("every fetch is BODY.PEEK[] (never sets \\Seen), size-capped",
      sorted({x[2] for x in log if x[0] == "fetch"}), ["(BODY.PEEK[]<0.%d>)" % 1048576])
import ssl as _ssl                               # noqa: E402
ctx_ = FakeIMAP.last.ssl_context
check("the server's certificate is verified",
      bool(ctx_) and ctx_.verify_mode == _ssl.CERT_REQUIRED and ctx_.check_hostname, True)
check("the search asks for Amazon's senders", any("FROM" in x for x in log if x[0] == "search"), True)
check("nothing stored/copied/moved/expunged", [x for x in log if x[0] == "FORBIDDEN"], [])
conn = DB.get_db(_CFG)
bodies = " ".join(r0["body_text"] or "" for r0 in conn.execute("SELECT body_text FROM buyer_inbox"))
check("personal and look-alike text never reached the database",
      ("PERSONAL-MAIL-TEXT" in bodies, "LOOKALIKE-TEXT" in bodies), (False, False))
r = BI.poll(_CFG, acc_a, imap_factory=FakeIMAP)
check("second check: nothing new (unique message id)", (r["ok"], r["new"]), (True, 0))
bell = conn.execute("SELECT COUNT(*) FROM notifications WHERE workspace_id='ta' AND type='buyer_message'").fetchone()[0]
check("each new message reached the bell exactly once", bell, 3)
st = BI.status(_CFG, "ta")
check("status: last_ok_at set, no error, last_seen kept", (bool(st.get("last_ok_at")), st.get("last_error"),
                                                           bool(st.get("last_seen"))), (True, "", True))

print("== threads, per account ==")
th = BI.threads(_CFG, "ta")
check("three threads for A", len(th), 3)
t_uk = next(t for t in th if t["order_id"] == "202-1234567-7654321")
check("  unread count and reply link", (t_uk["unread"], t_uk["reply_url"].endswith(".co.uk/messaging/inbox")), (1, True))
check("B sees none of A's", BI.threads(_CFG, "tb"), [])
BI.store(_CFG, "tb", dict(BI.parse(UK), body_text="B-ONLY"))
check("the same email filed for B is B's own row", (len(BI.threads(_CFG, "tb")), BI.unread_count(_CFG, "ta")), (1, 3))
check("B's order thread via A: nothing", [x for x in BI.thread(_CFG, "ta", "202-1234567-7654321")
                                          if x.get("body_text") == "B-ONLY"], [])
conn.execute("INSERT INTO buyer_messages (workspace_id, marketplace, order_id, action, body, ok, error, sent_by, sent_at) "
             "VALUES ('ta','UK','202-1234567-7654321','confirmDeliveryDetails','{}',1,'','me@x','2026-09-29T11:00:00')")
conn.commit()
full = BI.thread(_CFG, "ta", "202-1234567-7654321")
check("the thread shows the app's sent message after the buyer's", [x["kind"] for x in full], ["buyer", "app"])
check("marking A's thread read changes A only", (BI.mark_read(_CFG, "ta", "202-1234567-7654321"),
                                                BI.unread_count(_CFG, "ta"), BI.unread_count(_CFG, "tb")), (1, 2, 1))
check("a thread with no order is found by its sender", len(BI.thread(_CFG, "ta", "", "zz@marketplace.amazon.co.uk")), 1)

print("== odd mail never stops a check ==")
BOGUS = (b"From: q@marketplace.amazon.co.uk\r\nSubject: Order 202-5555555-5555555\r\n"
         b"Message-ID: <bogus@amazon>\r\nContent-Type: text/plain; charset=x-bogus\r\n\r\nHi\xff there\r\n")
check("an unknown charset is read, not raised", (BI.parse(BOGUS) or {}).get("order_id"), "202-5555555-5555555")
FUTURE = mail("f@marketplace.amazon.co.uk", "Order 202-6666666-6666666", "later", mid="<f1@amazon>",
              date="Fri, 01 Jan 2099 10:00:00 +0000")
check("a Date in the future is capped at now", BI.parse(FUTURE)["received_at"] < "2099", True)
NODATE = (b"From: n@marketplace.amazon.co.uk\r\nSubject: hello\r\n\r\nbody\r\n")
check("no Message-ID and no Date: the same id every time",
      BI.parse(NODATE)["message_id"] == BI.parse(NODATE)["message_id"], True)
_orig_parse = BI.parse
_calls = {"n": 0}


def _boom_once(raw):
    _calls["n"] += 1
    if _calls["n"] == 1:
        raise ValueError("unreadable test message")
    return _orig_parse(raw)


BI.parse = _boom_once
try:
    r = BI.poll(_CFG, acc_a, imap_factory=FakeIMAP)
finally:
    BI.parse = _orig_parse
st = BI.status(_CFG, "ta")
check("one unreadable email: the check still completes and says so",
      (r["ok"], r.get("unreadable"), "could not be read" in (st.get("last_error") or "")), (True, 1, True))
BI.poll(_CFG, acc_a, imap_factory=FakeIMAP)
check("  and the next clean check clears the error", BI.status(_CFG, "ta").get("last_error"), "")

print("== a failed check is recorded, without the password ==")
BM.save(_CFG, "tb", {"mailbox_user": "b@example.com", "mailbox_password": "wrong-password-123"})
acc_b = json.load(open(_CFG))["accounts"][1]
r = BI.poll(_CFG, acc_b, imap_factory=FakeIMAP)
st = BI.status(_CFG, "tb")
check("refused sign-in: ok False, error recorded", (r["ok"], bool(st.get("last_error"))), (False, True))
check("  the password is not in the error", "wrong-password-123" in (st.get("last_error") or "") + r["error"], False)
check("  A's status untouched", BI.status(_CFG, "ta").get("last_error"), "")

print("== the stored password never goes to a new server; one mailbox per account ==")
ok, err, _a = BM.save(_CFG, "ta", {"mailbox_host": "imap.attacker.example", "mailbox_user": "seller@example.com",
                                   "mailbox_password": ""})
check("changing the server without retyping the password is refused", (ok, "again" in err), (False, True))
check("  and nothing changed", BM.credentials(json.load(open(_CFG))["accounts"][0])[0], "imap.gmail.com")
ok, err, _a = BM.save(_CFG, "tb", {"mailbox_user": "SELLER@example.com", "mailbox_password": "x" * 16})
check("an address another account already reads is refused", (ok, "T A" in err), (False, True))

print("== the 10-minute job ==")
from data import scheduler as S                 # noqa: E402
check("registered every 10 minutes", round((S._JOBS.get("buyer_inbox") or {}).get("hours") * 60), 10)
conf = json.load(open(_CFG))
res = BI.poll_all(_CFG, {"accounts": [dict(a) for a in conf["accounts"]] + [{"id": "tc"}]}, imap_factory=FakeIMAP)
check("only accounts with a mailbox are checked", sorted(res["checked"]), ["ta", "tb"])
check("  B's failure listed, A fine", [e["workspace"] for e in res["errors"]], ["tb"])

print("== the routes ==")
import dashboard as D                            # noqa: E402
app = D.build_app()
app.config["TESTING"] = True
c = app.test_client()
for path in ("/inbox/threads", "/inbox/unread", "/inbox/thread?order_id=1", "/settings/mailbox"):
    check("GET %s with no account -> refused" % path.split("?")[0], c.get(path).status_code, 400)
for path in ("/inbox/read", "/inbox/refresh", "/settings/mailbox", "/settings/mailbox/test"):
    check("POST %s with no account -> refused" % path, c.post(path, json={}).status_code, 400)
check("an unknown account -> refused", c.get("/inbox/threads?account=nope").status_code in (403, 404), True)
j = c.get("/inbox/threads?account=ta").get_json()
check("A's threads: connected, 3 threads, 2 unread", (j["connected"], len(j["threads"]), j["unread"]), (True, 3, 2))
j = c.get("/inbox/thread?account=ta&order_id=202-1234567-7654321").get_json()
check("A's order thread", (j["ok"], len(j["messages"])), (True, 2))
check("B's order-less thread asked for through A: 404",
      c.get("/inbox/thread?account=tb&order_id=305-1111111-2222222").status_code, 404)
r = c.post("/inbox/read", json={"account": "ta", "all": True})
check("mark all read (A)", (r.get_json()["unread"], BI.unread_count(_CFG, "tb")), (0, 1))
replies = []
g = c.get("/settings/mailbox?account=ta")
replies.append(g.get_data(as_text=True))
check("settings GET: set + tail", (g.get_json()["has_password"], g.get_json()["password_tail"]), (True, "3tpw"))
p = c.post("/settings/mailbox", json={"account": "ta", "mailbox_host": "imap.example.com"})
replies.append(p.get_data(as_text=True))
check("settings POST keeps the password", BM.credentials(json.load(open(_CFG))["accounts"][0])[3], PW)
from api import imap_mailbox as IM               # noqa: E402
_saw = {}
_real_test, _real_fetch = IM.test, IM.fetch_since
IM.test = lambda h, po, u, pw, **k: (_saw.update(pw=pw) or {"ok": True, "total": 5, "amazon_recent": 3, "days": 30})
try:
    t = c.post("/settings/mailbox/test", json={"account": "ta"})
    replies.append(t.get_data(as_text=True))
    check("test uses the stored password server-side", (t.get_json()["ok"], _saw.get("pw") == PW), (True, True))
    _saw.clear()
    t = c.post("/settings/mailbox/test", json={"account": "ta", "mailbox_host": "imap.attacker.example"})
    check("test against ANOTHER server with the stored password: refused, never tried",
          (t.status_code, "pw" in _saw), (400, False))
    IM.fetch_since = lambda *a, **k: (_ for _ in ()).throw(IM.MailboxError("server said no to %s" % PW))
    rf = c.post("/inbox/refresh", json={"account": "ta"})
    replies.append(rf.get_data(as_text=True))
    check("refresh failure -> 502 and recorded", (rf.status_code, bool(BI.status(_CFG, "ta").get("last_error"))), (502, True))
finally:
    IM.test, IM.fetch_since = _real_test, _real_fetch
replies.append(c.get("/inbox/threads?account=ta").get_data(as_text=True))
check("the password is in NO route reply", [x for x in replies if PW in x], [])
BM.save(_CFG, "tb", {"clear": True})
D._state["cfg"] = None
check("disconnected (clear) -> refresh says so, 400",
      c.post("/inbox/refresh", json={"account": "tb"}).status_code, 400)
check("  and the threads reply says not connected",
      c.get("/inbox/threads?account=tb").get_json()["connected"], False)

print("== permissions ==")
from auth import guard as G                      # noqa: E402
from auth import users as U                      # noqa: E402
check("reads declare no permission (feature level decides)",
      [G.required_permission(p, "GET") for p in ("/inbox/threads", "/inbox/thread", "/inbox/unread")], [None, None, None])
check("marking read and refreshing need edit",
      [G.required_permission(p, "POST") for p in ("/inbox/read", "/inbox/refresh")], ["edit", "edit"])
check("mailbox settings need manage_accounts",
      [G.required_permission("/settings/mailbox", m) for m in ("GET", "POST")], ["manage_accounts", "manage_accounts"])
check("the screen's paths sit with orders", G.feature_for("/inbox/threads"), "orders")
limited = {"id": "u_l", "role": "custom", "active": True, "permissions": ["edit"],
           "features": {"orders": "edit"}, "workspaces": ["tb"], "perms_version": 99}
check("a person limited to B may read B", G.check("/inbox/threads", "GET", limited, None, {"account": "tb"})[0], True)
check("  and may NOT read A", G.check("/inbox/threads", "GET", limited, None, {"account": "ta"})[0], False)
check("  nor mark A read", G.check("/inbox/read", "POST", limited, {"account": "ta"}, {})[0], False)
viewer = {"id": "u_v", "role": "custom", "active": True, "permissions": [],
          "features": {f: "view" for f in U.FEATURES}, "workspaces": ["*"], "perms_version": 99}
check("view-only: may read, may not mark read",
      (G.check("/inbox/threads", "GET", viewer, None, {"account": "ta"})[0],
       G.check("/inbox/read", "POST", viewer, {"account": "ta"}, {})[0]), (True, False))
nobody = dict(viewer, features={"orders": "none"})
check("no orders access: no messages either", G.check("/inbox/threads", "GET", nobody, None, {"account": "ta"})[0], False)
from domain import activity_catalog as AC        # noqa: E402
check("saving the mailbox is in the activity log", (AC.match("POST", "/settings/mailbox") or ())[3:4],
      ("team.settings_mailbox",))
from domain import activity as ACT               # noqa: E402
check("  and the password field is dropped, name and value",
      sorted(ACT.redact({"mailbox_password": "abc", "mailbox_user": "u"})), ["mailbox_user"])

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
