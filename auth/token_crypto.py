"""Lock and unlock ONE secret field. Nothing else.

WHY THIS EXISTS
---------------
Multi-tenant OAuth means this app holds OTHER SELLERS' refresh tokens. A
refresh token is not a password-equivalent, it is worse: SP-API has no
read-only token, so the same token that reads a seller's listings can also
overwrite and delete them. Holding one for somebody else is holding the keys to
their shopfront, and it sits in config.json next to everything else.

So the token is encrypted at rest with a key that never touches the repo or
config.json -- it lives in ALTA_TOKEN_KEY, an environment variable set in the
Railway dashboard. One file leak then yields ciphertext instead of tokens.

TWO RULES THAT MATTER MORE THAN THE ALGORITHM
---------------------------------------------
1. seal() REFUSES rather than falls back. A crypto helper that quietly returns
   plain text when its key is missing is worse than no encryption at all,
   because everything downstream still reports success and nobody finds out
   until the leak. If the key is absent, seal() raises and the OAuth routes
   refuse to complete an authorization. Failing loudly is the feature.

2. unseal() PASSES THROUGH anything that is not sealed. jack_uk, sheelady_us
   and nestwell hold their tokens in clear today, and they are live accounts
   selling real products. Encryption must not be a flag day: an unsealed value
   is returned unchanged, so nothing breaks, and those accounts pick up
   encryption the next time they are saved.

WHAT THIS DELIBERATELY IS NOT
-----------------------------
Not a general crypto layer, not a key manager, not a secrets store. One field,
two functions. If a second kind of secret ever needs this, it calls these --
it does not grow a second copy of them (rule 12).
"""
import os

# A short, unmistakable marker so unseal() can tell "this is ciphertext" from
# "this is a token somebody pasted in". Amazon's refresh tokens begin "Atzr|",
# so no real token can collide with this prefix.
_PREFIX = "enc:v1:"

_ENV_KEY = "ALTA_TOKEN_KEY"


class TokenKeyMissing(RuntimeError):
    """Raised when something asks to encrypt and there is no key to do it with.

    Carries the fix, not just the fault -- this surfaces in a route response
    and the person reading it is the person who can set the variable.
    """

    def __init__(self):
        super().__init__(
            "Cannot store this seller's Amazon token because no encryption key "
            "is set. Add an environment variable named %s in the Railway "
            "dashboard, set to a key from token_crypto.new_key(), then redeploy "
            "and ask the seller to connect again. Nothing was saved."
            % _ENV_KEY)


def new_key() -> str:
    """Generate a key to paste into Railway. Never called by the app itself."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode("ascii")


def key_status():
    """('ok'|'missing'|'invalid', explanation). The whole truth about the key.

    WHY THIS IS NOT JUST "IS IT SET". It used to be, and that gap cost a real
    authorization: a key that was PRESENT but not a valid Fernet key sailed
    through the pre-flight check in /auth/login, the seller was sent to Amazon,
    approved the permissions screen, came back -- and only THEN did seal() fail,
    with the token already exchanged and nothing able to store it.

    The comment above have_key() said refusing after consent is the worse
    experience, and then this checked the one thing that could not detect the
    problem. Presence is not readiness.
    """
    raw = str(os.environ.get(_ENV_KEY) or "").strip()
    if not raw:
        return ("missing",
                "%s is not set. Generate one with token_crypto.new_key() and "
                "add it in the hosting dashboard." % _ENV_KEY)
    try:
        from cryptography.fernet import Fernet
        Fernet(raw.encode("ascii"))
    except Exception as e:
        return ("invalid",
                "%s is set but is not a valid key (%s). It must be a 32-byte "
                "url-safe base64 key -- exactly what token_crypto.new_key() "
                "prints, pasted with no quotes and no trailing spaces. A "
                "password or passphrase will not work."
                % (_ENV_KEY, type(e).__name__))
    return ("ok", "")


def have_key() -> bool:
    """Is encryption available AND usable right now?

    Callers use this to refuse an OAuth flow BEFORE sending somebody to Amazon,
    rather than after -- being told the connection failed on return, having
    already approved, is a worse experience than being told it is not ready.
    That promise only holds if this validates the key rather than merely
    noticing it exists; see key_status().
    """
    return key_status()[0] == "ok"


def _fernet():
    raw = str(os.environ.get(_ENV_KEY) or "").strip()
    if not raw:
        raise TokenKeyMissing()
    from cryptography.fernet import Fernet
    try:
        return Fernet(raw.encode("ascii"))
    except Exception as e:
        # A malformed key is a deployment mistake, and saying so plainly beats
        # a stack trace about base64 padding.
        raise RuntimeError(
            "%s is set but is not a valid key (%s). It must be a 32-byte "
            "url-safe base64 key -- generate one with token_crypto.new_key()."
            % (_ENV_KEY, type(e).__name__))


def is_sealed(value) -> bool:
    return str(value or "").startswith(_PREFIX)


def seal(value: str) -> str:
    """Encrypt a token for storage. Raises if no key is configured.

    An already-sealed value is returned unchanged, so saving an account twice
    does not double-encrypt it.
    """
    s = str(value or "")
    if not s:
        return ""
    if is_sealed(s):
        return s
    return _PREFIX + _fernet().encrypt(s.encode("utf-8")).decode("ascii")


def unseal(value: str) -> str:
    """Decrypt a stored token. Anything not sealed is returned as it is.

    That pass-through is what lets encrypted and plain accounts coexist while
    the existing ones migrate. It is safe because the marker cannot occur in a
    real Amazon token.

    A sealed value that will not decrypt returns "" rather than raising: the
    callers are credential lookups, and every one of them already handles "no
    token" by refusing to talk to Amazon. Raising here would instead take out
    an unrelated screen. The wrong key is a deployment fault and shows up
    immediately as "connect this account first".
    """
    s = str(value or "")
    if not s or not is_sealed(s):
        return s
    try:
        return _fernet().decrypt(s[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except Exception:
        return ""
