"""A key that is SET but WRONG must fail before the seller consents, not after.

    "The OAuth callback successfully exchanged the code with Amazon but failed
     to save the token. The error message is: 'The authorization worked but this
     app could not save it (RuntimeError).'"

WHAT HAPPENED. ALTA_TOKEN_KEY was set to something that is not a Fernet key --
a passphrase, most likely. Presence was all anything checked, so:

  /auth/login  checked have_key(), which asked only "is the variable set?"  ->  passed
  the seller   read the permissions screen and approved
  Amazon       issued a one-time code, which was exchanged for a refresh token
  seal()       raised RuntimeError, because the key cannot construct a Fernet
  the callback reported "could not save it (RuntimeError)" and stored nothing

Every one of those steps did what it was written to do, which is the point: no
step was buggy on its own. The bug was the CHECK being weaker than the
operation it was standing in front of.

TWO DEFECTS, BOTH IN CODE I WROTE, AND THE SECOND IS THE WORSE ONE.

1. have_key() tested presence while seal() required validity. The comment above
   have_key() even said refusing after consent is the worse experience -- and
   then checked the one thing that could not detect this. Presence is not
   readiness.

2. The callback reported type(e).__name__ and DISCARDED the message. The
   RuntimeError it caught already contained a sentence naming the variable and
   saying what was wrong with it; that sentence was thrown away and replaced
   with the word "RuntimeError", which names nothing and fixes nothing. It sent
   somebody to a hosting platform's logs to find a string the process was
   holding at the time. An error a user cannot act on is a bug in the error.

THE COST IS NOT SYMMETRICAL. Failing before the redirect costs a page refresh.
Failing after costs a seller's consent AND the one-time code, which is spent --
they have to go round the whole loop again.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from auth import token_crypto as TC

GOOD = TC.new_key()
REAL = "Atzr|IwEBIFAKEfakeFAKEtokenvalue0123456789"

print("== the key is judged by whether it WORKS, not whether it exists ==")
os.environ["ALTA_TOKEN_KEY"] = GOOD
check("a generated key is ok", TC.key_status()[0], "ok")
truthy("  and have_key agrees", TC.have_key())

# The reported failure, reproduced.
os.environ["ALTA_TOKEN_KEY"] = "my-super-secret-key-2026"
check("a passphrase is INVALID, not ok", TC.key_status()[0], "invalid")
falsy("  and have_key refuses it", TC.have_key())
try:
    TC.seal(REAL)
    check("  seal() would have raised", "did not raise", "raises")
except RuntimeError:
    check("  seal() would have raised", True, True)   # the reported symptom

os.environ.pop("ALTA_TOKEN_KEY", None)
check("absent is 'missing', which is a different problem",
      TC.key_status()[0], "missing")

print("\n== the three shapes that break it are each caught ==")
for label, val in (("a truncated key", GOOD[:20]),
                   ("hex instead of base64", "a" * 64),
                   ("a passphrase", "hunter2-but-longer")):
    os.environ["ALTA_TOKEN_KEY"] = val
    check("  %s" % label, TC.key_status()[0], "invalid")

print("\n== and whitespace around a good key is tolerated, not rejected ==")
# Copying out of a dashboard picks these up, and rejecting a key that is
# actually correct would send somebody hunting for a problem that is not there.
for label, val in (("trailing space", GOOD + " "),
                   ("trailing newline", GOOD + "\n"),
                   ("leading space", " " + GOOD)):
    os.environ["ALTA_TOKEN_KEY"] = val
    check("  %s still works" % label, TC.key_status()[0], "ok")

print("\n== the message tells you what to do, not just what broke ==")
os.environ["ALTA_TOKEN_KEY"] = "my-super-secret-key-2026"
_why = TC.key_status()[1]
truthy("it names the variable", "ALTA_TOKEN_KEY" in _why)
truthy("  says what the value must be", "url-safe base64" in _why)
truthy("  says where to get one", "new_key()" in _why)
truthy("  and rules out the likely mistake", "passphrase will not work" in _why)
falsy("  and never echoes the key itself", "my-super-secret-key-2026" in _why)
os.environ["ALTA_TOKEN_KEY"] = GOOD

print("\n== /auth/login refuses BEFORE the redirect ==")
SRC = open(os.path.join(HERE, "routes", "auth_oauth_routes.py"),
           encoding="utf-8").read()
_login = SRC.split("def oauth_login")[1].split("def oauth_callback")[0]
truthy("it asks for the key's STATUS", "_tc.key_status()" in _login)
falsy("  not merely whether it is set", "_tc.have_key()" in _login)
truthy("  and says nothing was sent to Amazon", "Nothing was sent to Amazon" in _login)
# The refusal must happen before the consent URL is built.
truthy("  before the redirect is issued",
       _login.index("_kstate") < _login.index("apps/authorize/consent"))

print("\n== and the callback stops swallowing the reason ==")
_cb = SRC.split("def oauth_callback")[1]
falsy("no bare class name as the whole explanation",
      '% type(e).__name__, 500)' in _cb)
truthy("the real message is surfaced", "_detail = str(e).strip()" in _cb)
truthy("  and it says the Amazon half SUCCEEDED",
       "authorization with Amazon SUCCEEDED" in _cb)
# The code Amazon sent is single-use; saying so stops somebody retrying the URL.
truthy("  and that the code is spent", "single-use and has now been spent" in _cb)
truthy("  and where it failed", 'failed_at=' in _cb)

print("\n== the diagnostic separates 'wrong' from 'missing' ==")
# Reporting a set-but-broken key as "missing" sends somebody to add a variable
# that is already there.
truthy("an invalid key is reported as its own state",
       'if _kstate == "invalid":' in SRC)
truthy("  and is not also listed as missing",
       'not (k == "ALTA_TOKEN_KEY" and _kstate == "invalid")' in SRC)
truthy("  and the diagnostic judges it by validity",
       '"ALTA_TOKEN_KEY": _kstate == "ok"' in SRC)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
