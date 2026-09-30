"""routes/buyer_inbox_routes.py -- Customer messages: what buyers wrote.

    GET  /inbox/threads          one entry per order thread, newest first
    GET  /inbox/thread           every message in one thread (?order_id= or ?from_alias=)
    GET  /inbox/unread           the unread count, for the nav badge
    POST /inbox/read             mark a thread (or everything) read IN THIS APP
    POST /inbox/refresh          check the mailbox now

    GET  /settings/mailbox       the account's mailbox settings, password never included
    POST /settings/mailbox       save them (a blank password keeps the stored one)
    POST /settings/mailbox/test  sign in read-only and count; changes nothing

The rules live in domain/buyer_inbox.py and domain/buyer_mailbox.py; the mail
server is spoken to only by api/imap_mailbox.py. Nothing here sends anything to
a buyer -- replying waits for the owner.

THE ACCOUNT MUST BE NAMED (CLAUDE.md Rule 14). Every route refuses when the
page names no account; none falls back to the server's open one. The guard
(auth/guard.py) has already checked the signed-in person may use the account.
"""
from flask import jsonify, request

from domain import request_account as _req_acct


def register(app, *, CONFIG_PATH, _cfg, _state):
    """Attach /inbox/* and /settings/mailbox* to the app. `_state` only so a
    saved mailbox drops the cached settings (_state["cfg"]), as every other
    settings route does -- it is never read for an account."""

    def _account():
        """(account, None) or (None, refusal) -- the account the page named."""
        from domain import accounts as _acc
        aid = _req_acct.named_now()
        if not aid:
            return None, (jsonify({"ok": False, "error": (
                "Which account? This screen is per account, and no account was "
                "named, so nothing was read or changed.")}), 400)
        acc = _acc.get_account(_cfg() or {}, aid, CONFIG_PATH)
        if not acc:
            return None, (jsonify({"ok": False, "error":
                                   "No account called %r." % aid}), 404)
        return acc, None

    def _thread_args(src):
        return (str(src.get("order_id") or "").strip(),
                str(src.get("from_alias") or "").strip().lower())

    # ---- reading ------------------------------------------------------------
    @app.route("/inbox/threads")
    def inbox_threads():
        from domain import buyer_inbox as _bi
        from domain import buyer_mailbox as _box
        acc, bad = _account()
        if bad:
            return bad
        aid = str(acc.get("id"))
        try:
            rows = _bi.threads(CONFIG_PATH, aid)
            unread = _bi.unread_count(CONFIG_PATH, aid)
            st = _bi.status(CONFIG_PATH, aid)
        except Exception as e:
            return jsonify({"ok": False, "error": "Could not read the stored "
                            "messages: %s" % str(e)[:200]}), 500
        mk = [str(m or "").upper() for m in (acc.get("marketplaces") or [])
              if str(m or "").upper() not in ("", "__ALL__")]
        home = str(acc.get("default_marketplace") or (mk[0] if mk else "")).upper()
        return jsonify({"ok": True, "account": aid,
                        "connected": _box.is_configured(acc),
                        "mailbox_user": _box.public_view(acc).get("user", ""),
                        "status": st, "threads": rows, "unread": unread,
                        "reply_url": _bi.reply_url(home)})

    @app.route("/inbox/thread")
    def inbox_thread():
        from domain import buyer_inbox as _bi
        acc, bad = _account()
        if bad:
            return bad
        oid, alias = _thread_args(request.args)
        if not (oid or alias):
            return jsonify({"ok": False, "error": "Which thread? Name an order."}), 400
        msgs = _bi.thread(CONFIG_PATH, str(acc.get("id")), oid, alias)
        if not msgs:
            return jsonify({"ok": False, "error": (
                "No messages for that order on this account.")}), 404
        mkt = next((m.get("marketplace") for m in msgs if m.get("marketplace")), "")
        return jsonify({"ok": True, "order_id": oid, "from_alias": alias,
                        "marketplace": mkt, "messages": msgs,
                        "reply_url": _bi.reply_url(mkt)})

    @app.route("/inbox/unread")
    def inbox_unread():
        from domain import buyer_inbox as _bi
        from domain import buyer_mailbox as _box
        acc, bad = _account()
        if bad:
            return bad
        aid = str(acc.get("id"))
        return jsonify({"ok": True, "account": aid,
                        "connected": _box.is_configured(acc),
                        "unread": _bi.unread_count(CONFIG_PATH, aid)})

    # ---- changing this app's own state ----------------------------------------
    @app.route("/inbox/read", methods=["POST"])
    def inbox_read():
        from domain import buyer_inbox as _bi
        acc, bad = _account()
        if bad:
            return bad
        b = request.get_json(silent=True) or {}
        oid, alias = _thread_args(b)
        if not (oid or alias or b.get("all")):
            return jsonify({"ok": False, "error": "Which thread? Name an order."}), 400
        aid = str(acc.get("id"))
        n = _bi.mark_read(CONFIG_PATH, aid, oid, alias, everything=bool(b.get("all")))
        return jsonify({"ok": True, "changed": n,
                        "unread": _bi.unread_count(CONFIG_PATH, aid)})

    @app.route("/inbox/refresh", methods=["POST"])
    def inbox_refresh():
        from domain import buyer_inbox as _bi
        from domain import buyer_mailbox as _box
        acc, bad = _account()
        if bad:
            return bad
        if not _box.is_configured(acc):
            return jsonify({"ok": False, "connected": False, "error": (
                "No mailbox is connected for this account yet.")}), 400
        res = _bi.poll(CONFIG_PATH, acc)
        res["status"] = _bi.status(CONFIG_PATH, str(acc.get("id")))
        return jsonify(res), (200 if res.get("ok") else 502)

    # ---- the mailbox settings (manage_accounts, auth/guard.py "/settings") ----
    @app.route("/settings/mailbox", methods=["GET", "POST"])
    def settings_mailbox():
        from domain import buyer_mailbox as _box
        acc, bad = _account()
        if bad:
            return bad
        from auth import token_crypto as _tc
        if request.method == "GET":
            return jsonify({"ok": True, "account": acc.get("id"),
                            "can_seal": _tc.have_key(), **_box.public_view(acc)})
        b = request.get_json(silent=True) or {}
        ok, err, after = _box.save(CONFIG_PATH, str(acc.get("id")), b)
        if not ok:
            return jsonify({"ok": False, "error": err}), 400
        _state["cfg"] = None          # the next read sees the saved mailbox
        return jsonify({"ok": True, "account": acc.get("id"),
                        "can_seal": _tc.have_key(), **_box.public_view(after)})

    @app.route("/settings/mailbox/test", methods=["POST"])
    def settings_mailbox_test():
        """Sign in, open the inbox READ-ONLY, count. Changes nothing.

        Tests what is typed when a password is typed (so it can be checked
        before saving), otherwise what is stored.
        """
        from api import imap_mailbox as _imap
        from domain import buyer_mailbox as _box
        acc, bad = _account()
        if bad:
            return bad
        b = request.get_json(silent=True) or {}
        host, port, user, password = _box.credentials(acc)
        typed = _box.typed_password(b)
        # The stored password only goes back to the server and address it was
        # saved for (domain/buyer_mailbox.password_needed).
        why = _box.password_needed(acc, b, typed)
        if why:
            return jsonify({"ok": False, "error": why}), 400
        host = str(b.get("mailbox_host") or "").strip() or host
        port = b.get("mailbox_port") or port
        user = str(b.get("mailbox_user") or "").strip() or user
        if typed:
            password = typed
        if not (user and password):
            return jsonify({"ok": False, "error": (
                "Enter the email address and its app password first.")}), 400
        return jsonify(_imap.test(host, port, user, password))
