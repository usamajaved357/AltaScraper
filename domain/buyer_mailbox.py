"""domain/buyer_mailbox.py -- which mailbox an account's buyer messages arrive in.

One set per ACCOUNT, stored on the account record in config.json: each company
has its own Seller Central, and each Seller Central emails buyer messages to
its own address. Four fields:

    mailbox_host      IMAP server (default imap.gmail.com)
    mailbox_port      993 (IMAP over SSL)
    mailbox_user      the address signed in with
    mailbox_password  an APP PASSWORD, never the account's real one

THE PASSWORD IS SEALED AT REST exactly as accounts.save_account seals refresh
tokens: with auth/token_crypto when ALTA_TOKEN_KEY is set, as given when it is
not (the rule every other stored secret here follows, so a deployment without
the key keeps working; the screen says which it is). It is unsealed in ONE
place, credentials() below, and never leaves the server: public_view() reports
only whether one is stored and its last four characters.

A BLANK PASSWORD KEEPS THE STORED ONE, the same rule as the eBay cert and the
advertising secret, so correcting the address alone cannot wipe it.
"""
from config import settings as _settings

DEFAULT_HOST = "imap.gmail.com"
DEFAULT_PORT = 993
FIELDS = ("mailbox_host", "mailbox_port", "mailbox_user", "mailbox_password")

# Values that are a mask or a placeholder, never a password someone typed.
_NOT_A_VALUE = ("•", "*", "PUT_", "ROTATE")


def _port(v):
    try:
        p = int(str(v or "").strip() or DEFAULT_PORT)
    except (TypeError, ValueError):
        return DEFAULT_PORT
    return p if 0 < p < 65536 else DEFAULT_PORT


def is_configured(account):
    """Has this account been given a mailbox to read? (user AND password)"""
    a = account or {}
    return bool(str(a.get("mailbox_user") or "").strip()
                and str(a.get("mailbox_password") or "").strip())


def credentials(account):
    """(host, port, user, password) -- the ONE place the password is unsealed."""
    from auth import token_crypto as _tc
    a = account or {}
    return (str(a.get("mailbox_host") or "").strip() or DEFAULT_HOST,
            _port(a.get("mailbox_port")),
            str(a.get("mailbox_user") or "").strip(),
            _tc.unseal(str(a.get("mailbox_password") or "")))


def public_view(account):
    """What a screen may see. Never the password -- set or not, last four."""
    from auth import token_crypto as _tc
    a = account or {}
    stored = str(a.get("mailbox_password") or "")
    plain = _tc.unseal(stored) if stored else ""
    return {
        "host": str(a.get("mailbox_host") or "").strip() or DEFAULT_HOST,
        "port": _port(a.get("mailbox_port")),
        "user": str(a.get("mailbox_user") or "").strip(),
        "has_password": bool(stored),
        "password_tail": (plain[-4:] if len(plain) >= 4 else "") if plain else "",
        "sealed": _tc.is_sealed(stored) if stored else None,
        "configured": is_configured(a),
    }


def typed_password(body):
    """The password the form sent, or "" when it sent none (or only a mask).
    Google shows an app password in four groups of four; the spaces are not
    part of it, and a pasted one keeps them."""
    pw = str((body or {}).get("mailbox_password") or "").strip().replace(" ", "")
    return "" if (not pw or pw.startswith(_NOT_A_VALUE)) else pw


def password_needed(account, body, typed):
    """Why the STORED password must not be used with what the form sent, or "".

    The stored password only ever goes back to the server and address it was
    typed for. Changing either without typing it again would hand it to
    whatever server was named -- a way to read out a secret this app otherwise
    never shows (security review, 30 Sep 2026).
    """
    if typed or not str((account or {}).get("mailbox_password") or "").strip():
        return ""
    host, _port_, user, _pw = credentials(account)
    b = body or {}
    new_host = str(b.get("mailbox_host") or "").strip() or DEFAULT_HOST
    new_user = str(b.get("mailbox_user") or "").strip()
    changed = (("mailbox_host" in b and new_host.lower() != host.lower())
               or ("mailbox_user" in b and new_user.lower() != user.lower()))
    return ("Type the app password again when changing the server or the "
            "address." if changed else "")


def _used_by_other(raw, account_id, user):
    """The label of ANOTHER account already reading this address, or ""."""
    u = str(user or "").strip().lower()
    if not u:
        return ""
    for a in (raw.get("accounts") or []):
        if str(a.get("id") or "") == str(account_id or ""):
            continue
        if str(a.get("mailbox_user") or "").strip().lower() == u:
            return str(a.get("label") or a.get("id") or "another account")
    return ""


def save(config_path, account_id, body):
    """Write one account's mailbox settings. -> (ok, error, account_after).

    `clear: true` removes all four -- the mailbox stops being read.
    """
    from auth import token_crypto as _tc
    b = body or {}
    raw = _settings.read_raw(config_path)
    target = None
    for a in (raw.get("accounts") or []):
        if str(a.get("id") or "") == str(account_id or ""):
            target = a
            break
    if target is None:
        return False, "No account called %r." % account_id, None
    if b.get("clear"):
        for f in FIELDS:
            target.pop(f, None)
    else:
        pw = typed_password(b)
        why = password_needed(target, b, pw)
        if why:
            return False, why, None
        user = str(b.get("mailbox_user", target.get("mailbox_user")) or "").strip()
        other = _used_by_other(raw, account_id, user)
        if other:
            # ONE MAILBOX, ONE ACCOUNT. Every Amazon message in a mailbox is
            # filed under the account reading it; a second account on the
            # same address would show the first company's customers too.
            return False, ("%s already receives buyer messages for %s. Each "
                           "account needs its own address." % (user, other)), None
        if "mailbox_host" in b:
            target["mailbox_host"] = str(b.get("mailbox_host") or "").strip() or DEFAULT_HOST
        if "mailbox_port" in b:
            target["mailbox_port"] = _port(b.get("mailbox_port"))
        if "mailbox_user" in b:
            target["mailbox_user"] = user
        if pw:
            target["mailbox_password"] = _tc.seal(pw) if _tc.have_key() else pw
    if not _settings.write_raw(raw, config_path):
        return False, "The settings file could not be written.", None
    return True, "", dict(target)
