"""auth/users.py -- user accounts, passwords, invitations and permissions.

PLAIN ENGLISH
Until now the app had one shared password. Anyone who knew it could do
everything: publish to Amazon, change bids, read the SP-API keys. This module
gives each person their own account, so you can let someone write listings all
day without ever letting them publish one or see your credentials.

HOW SOMEONE GETS IN
You add their email. The app generates a one-time invitation link that you send
them however you like -- WhatsApp, Signal, anything. They open it and choose
their own password. No email server is involved, because the app has none, and
you never see or set their password.

WHAT IS STORED
users.json, beside config.json (so on Render's persistent disk, and never in
git). Passwords are stored ONLY as salted hashes via Werkzeug, which Flask
already depends on -- the plain password is never written down, so a leaked
users.json does not hand over anyone's login. Invitation tokens are stored the
same way, hashed, so a leaked file cannot be used to claim a pending invite.

YOU CANNOT LOCK YOURSELF OUT
While users.json holds no ACTIVE user, the existing shared password keeps working
exactly as before and is treated as the owner. Nothing changes for you until you
choose to add someone. See is_bootstrap().
"""
import hashlib
import re
import secrets
import threading
import time

from werkzeug.security import check_password_hash, generate_password_hash

from domain import jsonstore

_FILE = "users.json"
_LOCK = threading.RLock()

# ---- the permission vocabulary ------------------------------------------
# Every permission is a thing a person can DO. Reading is not on this list:
# anyone with an account can look. These are the actions worth withholding.
PERMISSIONS = {
    "edit":            "Create and edit drafts, generate copy and images",
    "approve_delete":  "Approve, hold and delete listings",
    "publish":         "Publish and push changes live to Amazon",
    "ppc":             "Change PPC campaigns, bids and budgets",
    "manage_accounts": "View and change Amazon credentials, accounts and settings",
    "manage_users":    "Add, change and remove users",
}

# Roles are presets, not a separate mechanism -- picking a role fills in the
# permission list, which remains individually editable afterwards.
ROLES = {
    "owner":   ["edit", "approve_delete", "publish", "ppc", "manage_accounts", "manage_users"],
    "manager": ["edit", "approve_delete", "publish", "ppc"],
    "lister":  ["edit"],
    "viewer":  [],
}

ALL_WORKSPACES = "*"          # the wildcard in a user's workspace list
INVITE_TTL_SECONDS = 7 * 24 * 3600


# ---- storage -------------------------------------------------------------

def _path(config_path):
    return jsonstore.path_beside_config(config_path, _FILE)


def _load(config_path):
    data = jsonstore.read_json(_path(config_path), default=None)
    if not isinstance(data, dict):
        data = {}
    users = data.get("users")
    if not isinstance(users, list):
        users = []
    return {"version": 1, "users": [u for u in users if isinstance(u, dict)]}


def _save(config_path, data):
    # indent=2 so the file stays hand-readable: if something ever goes wrong with
    # accounts, you must be able to open this file and understand it.
    return jsonstore.write_json_atomic(_path(config_path), data, indent=2)


# ---- helpers -------------------------------------------------------------

def normalise_email(email):
    return str(email or "").strip().lower()


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


def valid_email(email):
    return bool(_EMAIL_RE.match(normalise_email(email)))


def _hash_token(token):
    """Invitation tokens are stored hashed, for the same reason passwords are."""
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _new_id():
    return "u_" + secrets.token_hex(8)


def public(user):
    """A user record safe to send to the browser: no hashes, no tokens."""
    if not isinstance(user, dict):
        return None
    return {
        "id": user.get("id", ""),
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "role": user.get("role", "viewer"),
        "permissions": list(user.get("permissions") or []),
        "workspaces": list(user.get("workspaces") or []),
        "active": bool(user.get("active", True)),
        "created_at": user.get("created_at"),
        "last_login": user.get("last_login"),
        # Whether they have finished setting a password -- shown in the UI so you
        # can see at a glance who has not accepted their invitation yet.
        "pending_invite": not bool(user.get("password_hash")),
        "invite_expired": _invite_expired(user),
    }


def _invite_expired(user):
    inv = (user or {}).get("invite") or {}
    if not inv.get("token_hash"):
        return False
    try:
        return time.time() > float(inv.get("expires") or 0)
    except Exception:
        return True


# ---- queries -------------------------------------------------------------

def list_users(config_path):
    return [public(u) for u in _load(config_path)["users"]]


def get_user(config_path, user_id):
    for u in _load(config_path)["users"]:
        if u.get("id") == user_id:
            return u
    return None


def get_by_email(config_path, email):
    e = normalise_email(email)
    for u in _load(config_path)["users"]:
        if normalise_email(u.get("email")) == e:
            return u
    return None


def is_bootstrap(config_path):
    """True while no ACTIVE user with a password exists.

    In that state the app still accepts the old shared password, so adding the
    user system can never lock you out of your own app. It stops being true the
    moment the first person accepts their invitation.
    """
    for u in _load(config_path)["users"]:
        if u.get("active", True) and u.get("password_hash"):
            return False
    return True


def bootstrap_user():
    """The synthetic owner used while is_bootstrap() is true."""
    return {
        "id": "shared", "email": "", "name": "Shared password",
        "role": "owner", "permissions": list(ROLES["owner"]),
        "workspaces": [ALL_WORKSPACES], "active": True, "bootstrap": True,
    }


# ---- permission checks ---------------------------------------------------

def has_permission(user, perm):
    """Does this user hold `perm`? The ONLY place this question is answered."""
    if not user or not user.get("active", True):
        return False
    if not perm:
        return True                      # the action needs no permission
    return perm in (user.get("permissions") or [])


def can_access_workspace(user, workspace_id):
    """May this user open this workspace (Amazon account / brand)?

    An empty workspace id means the built-in Dropshipping workspace, which is
    named explicitly rather than treated as "no restriction" -- otherwise a
    scoped user could reach it by sending a blank id.
    """
    if not user or not user.get("active", True):
        return False
    allowed = user.get("workspaces") or []
    if ALL_WORKSPACES in allowed:
        return True
    return (str(workspace_id or "") or "dropshipping") in [str(a) for a in allowed]


# ---- mutations -----------------------------------------------------------

def create_user(config_path, email, name="", role="lister", permissions=None,
                workspaces=None):
    """Add a user and return (public_record, invite_token).

    The token is returned ONCE, here. Only its hash is stored, so it cannot be
    recovered later -- if it is lost, issue a new invitation instead.
    """
    email = normalise_email(email)
    if not valid_email(email):
        return None, "That does not look like an email address."
    with _LOCK:
        data = _load(config_path)
        if any(normalise_email(u.get("email")) == email for u in data["users"]):
            return None, "A user with that email already exists."
        role = role if role in ROLES else "lister"
        perms = permissions if isinstance(permissions, list) else ROLES[role]
        perms = [p for p in perms if p in PERMISSIONS]
        ws = workspaces if isinstance(workspaces, list) and workspaces else [ALL_WORKSPACES]
        token = secrets.token_urlsafe(32)
        user = {
            "id": _new_id(),
            "email": email,
            "name": str(name or "").strip(),
            "role": role,
            "permissions": perms,
            "workspaces": [str(w) for w in ws],
            "password_hash": "",
            "active": True,
            "created_at": time.time(),
            "last_login": None,
            "invite": {"token_hash": _hash_token(token),
                       "expires": time.time() + INVITE_TTL_SECONDS},
        }
        data["users"].append(user)
        if not _save(config_path, data):
            return None, "Could not write users.json -- check disk permissions."
        return public(user), token


def new_invite(config_path, user_id):
    """Issue a fresh invitation for an existing user. Returns (token, error).

    Also used for password resets: it clears the existing password, so the link
    is the only way back in and an old password cannot be reused.
    """
    with _LOCK:
        data = _load(config_path)
        for u in data["users"]:
            if u.get("id") == user_id:
                token = secrets.token_urlsafe(32)
                u["invite"] = {"token_hash": _hash_token(token),
                               "expires": time.time() + INVITE_TTL_SECONDS}
                u["password_hash"] = ""
                if not _save(config_path, data):
                    return None, "Could not write users.json."
                return token, None
        return None, "No such user."


def accept_invite(config_path, token, password):
    """Set a password using an invitation token. Returns (public_record, error)."""
    if len(str(password or "")) < 8:
        return None, "Choose a password of at least 8 characters."
    th = _hash_token(token)
    with _LOCK:
        data = _load(config_path)
        for u in data["users"]:
            inv = u.get("invite") or {}
            if not inv.get("token_hash"):
                continue
            # compare_digest: constant time, so the comparison cannot be used to
            # guess a token one character at a time.
            if not secrets.compare_digest(str(inv["token_hash"]), th):
                continue
            if not u.get("active", True):
                return None, "That account has been disabled."
            if time.time() > float(inv.get("expires") or 0):
                return None, "That invitation has expired. Ask for a new link."
            u["password_hash"] = generate_password_hash(str(password))
            u["invite"] = {}              # one-time: the link dies on use
            if not _save(config_path, data):
                return None, "Could not write users.json."
            return public(u), None
        return None, "That invitation link is not valid."


def authenticate(config_path, email, password):
    """Check an email and password. Returns the full record, or None."""
    with _LOCK:
        data = _load(config_path)
        e = normalise_email(email)
        for u in data["users"]:
            if normalise_email(u.get("email")) != e:
                continue
            if not u.get("active", True) or not u.get("password_hash"):
                return None
            if not check_password_hash(u["password_hash"], str(password or "")):
                return None
            u["last_login"] = time.time()
            _save(config_path, data)
            return u
    return None


def update_user(config_path, user_id, **fields):
    """Change name/role/permissions/workspaces/active. Returns (public, error)."""
    with _LOCK:
        data = _load(config_path)
        had_manager = _has_manager(data)
        for u in data["users"]:
            if u.get("id") != user_id:
                continue
            if "name" in fields:
                u["name"] = str(fields["name"] or "").strip()
            if "role" in fields and fields["role"] in ROLES:
                u["role"] = fields["role"]
            if "permissions" in fields and isinstance(fields["permissions"], list):
                u["permissions"] = [p for p in fields["permissions"] if p in PERMISSIONS]
            if "workspaces" in fields and isinstance(fields["workspaces"], list):
                u["workspaces"] = [str(w) for w in fields["workspaces"]] or [ALL_WORKSPACES]
            if "active" in fields:
                u["active"] = bool(fields["active"])
            if _lost_last_manager(had_manager, data):
                return None, ("That would leave nobody able to manage users. "
                              "Give someone else the 'manage users' permission first.")
            if not _save(config_path, data):
                return None, "Could not write users.json."
            return public(u), None
        return None, "No such user."


def delete_user(config_path, user_id):
    with _LOCK:
        data = _load(config_path)
        had_manager = _has_manager(data)
        before = len(data["users"])
        data["users"] = [u for u in data["users"] if u.get("id") != user_id]
        if len(data["users"]) == before:
            return False, "No such user."
        if _lost_last_manager(had_manager, data):
            return False, ("That is the only person who can manage users. "
                           "Give someone else that permission first.")
        if not _save(config_path, data):
            return False, "Could not write users.json."
        return True, None


def _has_manager(data):
    """Is there at least one usable account that can manage users?"""
    return any(u.get("active", True) and u.get("password_hash")
               and "manage_users" in (u.get("permissions") or [])
               for u in data["users"])


def _lost_last_manager(had_manager, data):
    """Would this change strip the app of its last user-manager?

    Compared BEFORE against AFTER on purpose. An earlier version simply asked
    "is there a manager now?", which wrongly blocked harmless changes -- such as
    re-enabling a disabled lister -- with a confusing message about managers,
    because there had been no manager before the change either. A rule that only
    fires when a change actually REMOVES the last manager cannot do that.

    Losing the last manager is still fine when it leaves no usable accounts at
    all: that returns the app to the shared password, which is a way back in
    rather than a lockout.
    """
    if not had_manager:
        return False                     # nothing to lose
    if _has_manager(data):
        return False                     # still one left
    return any(u.get("active", True) and u.get("password_hash") for u in data["users"])
