"""Other sellers can authorize this app, and their tokens are not left in clear.

    "I need to add multi-tenant OAuth support to AltaScraper so other Amazon
     sellers can authorize my app and I can make SP-API calls on their behalf"

WHAT IS BEING PROTECTED. A refresh token is worse than a password: SP-API has
no read-only token, so the same token that reads a seller's listings can
overwrite and delete them. Holding one for somebody else is holding the keys to
their shopfront. Hence encryption at rest with a key that lives only in
Railway's environment, and hence most of the assertions below.

TWO DESIGN DECISIONS THE TESTS PIN DOWN, because both are easy to undo by
accident later:

  seal() REFUSES without a key, so a missing key can never be silently
  downgraded to storing plain text; but unseal() PASSES THROUGH unsealed
  values, so jack_uk / sheelady_us / nestwell -- live accounts selling real
  products -- keep working with no migration step.

  account_creds() is the ONE place a stored token becomes a usable token. If a
  second place ever grows, it will send ciphertext to Amazon and the failure
  will look like a revoked token rather than a bug.

The app is in DRAFT on the Solution Provider Portal, so the consent URL must
carry &version=beta. That is a fact about the app's state, and when it is
published the constant changes and this test changes with it.
"""
import importlib
import json
import os
import sys
import tempfile

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
import accounts as ACC
import routes.auth_oauth_routes as OA

REAL = "Atzr|IwEBIFAKEfakeFAKEtokenvalue0123456789"

# ===================================================================
print("== a key is required to encrypt, and refused loudly when absent ==")
os.environ.pop("ALTA_TOKEN_KEY", None)
falsy("no key means no encryption available", TC.have_key())
try:
    TC.seal(REAL)
    check("seal() refuses without a key", "did not raise", "raises")
except TC.TokenKeyMissing as e:
    check("seal() refuses without a key", True, True)
    # The person reading this is the person who can fix it.
    truthy("  and the refusal names the variable to set", "ALTA_TOKEN_KEY" in str(e))
    truthy("  and where to set it", "Railway" in str(e))
    truthy("  and says nothing was stored", "Nothing was saved" in str(e))

print("\n== an unencrypted token still works, so nothing needs migrating ==")
check("unseal passes a plain token through", TC.unseal(REAL), REAL)
check("  and an empty one stays empty", TC.unseal(""), "")
falsy("  a real Amazon token is not mistaken for ciphertext", TC.is_sealed(REAL))

# ===================================================================
print("\n== with a key, the token is unreadable at rest and recoverable in use ==")
os.environ["ALTA_TOKEN_KEY"] = TC.new_key()
truthy("a key makes encryption available", TC.have_key())
sealed = TC.seal(REAL)
truthy("the stored value is marked as sealed", TC.is_sealed(sealed))
falsy("  and does not contain the token", REAL in sealed)
falsy("  nor its recognisable prefix", "Atzr|" in sealed)
check("  and it comes back exactly", TC.unseal(sealed), REAL)
check("sealing twice does not double-encrypt", TC.unseal(TC.seal(sealed)), REAL)

print("\n== a wrong key does not take out an unrelated screen ==")
# Every caller of account_creds already handles "no token" by refusing to talk
# to Amazon. Raising here would turn a deployment fault into a broken page.
os.environ["ALTA_TOKEN_KEY"] = TC.new_key()          # different key
check("an undecryptable token reads as absent", TC.unseal(sealed), "")

# ===================================================================
print("\n== one place turns a stored token into a usable one ==")
os.environ["ALTA_TOKEN_KEY"] = TC.new_key()
key_now = os.environ["ALTA_TOKEN_KEY"]
acct = {"id": "x", "lwa_client_id": "amzn1.application.aaa",
        "lwa_client_secret": "shh", "seller_id": "A1SELLER",
        "refresh_token": TC.seal(REAL)}
creds = ACC.account_creds(acct)
check("account_creds decrypts", creds["refresh_token"], REAL)
check("  and still reports the seller", creds["seller_id"], "A1SELLER")
check("  and the client id", creds["lwa_app_id"], "amzn1.application.aaa")
# A plain-token account must go through the same function unchanged.
check("a plain account is unaffected",
      ACC.account_creds({"refresh_token": REAL})["refresh_token"], REAL)

print("\n== an OAuth seller uses OUR application, not credentials of its own ==")
os.environ["ALTA_LWA_CLIENT_ID"] = "amzn1.application-oa2-client.APPID"
os.environ["ALTA_LWA_CLIENT_SECRET"] = "appsecret"
oauth_acct = {"id": "amzn_a1b2_uk", "auth": "oauth", "seller_id": "A1B2C3",
              "marketplace": "UK", "status": "active",
              "refresh_token": TC.seal(REAL)}
truthy("it is recognised as an OAuth seller", ACC.is_oauth(oauth_acct))
oc = ACC.account_creds(oauth_acct)
check("the client id comes from the environment",
      oc["lwa_app_id"], "amzn1.application-oa2-client.APPID")
check("  and so does the secret", oc["lwa_client_secret"], "appsecret")
check("  while the token is the seller's own", oc["refresh_token"], REAL)

print("\n== and it counts as having its own credentials ==")
# has_own_creds gates every seller-scoped call and every WRITE. Answering "no"
# here would connect a seller and then quietly refuse to do anything for them.
truthy("an active OAuth seller may act as itself", ACC.has_own_creds(oauth_acct))
truthy("  so seller-scoped calls are allowed", ACC.seller_scope_allowed(oauth_acct))
truthy("  and it may publish", ACC.can_publish(oauth_acct))
falsy("  and it is not treated as borrowing", ACC.is_borrowed(oauth_acct))
# A revoked authorization must stop being usable the moment it is marked so.
revoked = {**oauth_acct, "status": "revoked"}
falsy("a revoked authorization may not act", ACC.has_own_creds(revoked))
falsy("  and may not publish", ACC.can_publish(revoked))
# Without the app's own credentials nothing can authenticate at all.
os.environ.pop("ALTA_LWA_CLIENT_SECRET", None)
falsy("no app secret means no OAuth seller can act", ACC.has_own_creds(oauth_acct))
os.environ["ALTA_LWA_CLIENT_SECRET"] = "appsecret"

# ===================================================================
print("\n== saving encrypts, and reading back returns the real token ==")
tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                  encoding="utf-8")
json.dump({"accounts": []}, tmp)
tmp.close()
try:
    os.environ["ALTA_TOKEN_KEY"] = key_now
    ACC.save_account({}, tmp.name, {"id": "newguy", "label": "New Guy",
                                    "refresh_token": REAL})
    on_disk = json.load(open(tmp.name, encoding="utf-8"))["accounts"][0]
    falsy("the token is not on disk in clear", REAL in json.dumps(on_disk))
    truthy("  it is stored sealed", TC.is_sealed(on_disk["refresh_token"]))
    check("  and reads back correctly",
          ACC.account_creds(on_disk)["refresh_token"], REAL)

    # Without a key this must behave exactly as it always did, because this is
    # also how the ordinary account editor saves your own accounts.
    os.environ.pop("ALTA_TOKEN_KEY", None)
    ACC.save_account({}, tmp.name, {"id": "plainguy", "refresh_token": REAL})
    rows = json.load(open(tmp.name, encoding="utf-8"))["accounts"]
    plain = next(a for a in rows if a["id"] == "plainguy")
    check("with no key, saving still works", plain["refresh_token"], REAL)
    check("  and does not disturb the sealed one",
          next(a for a in rows if a["id"] == "newguy")["refresh_token"],
          on_disk["refresh_token"])
finally:
    os.unlink(tmp.name)
    os.environ["ALTA_TOKEN_KEY"] = key_now

# ===================================================================
print("\n== the consent URL matches the app's actual state ==")
#     "the app is still in Draft, not published. Add &version=beta"
check("draft, so version=beta", OA.DRAFT_VERSION_PARAM, "beta")
check("the application id is the one on the portal", OA.APPLICATION_ID,
      "amzn1.sp.solution.c4570a5c-28b0-4a4a-83ad-7a29695f3786")
check("UK consent goes to UK Seller Central",
      OA.CONSENT_HOSTS["UK"], "sellercentral.amazon.co.uk")
check("  and US to US", OA.CONSENT_HOSTS["US"], "sellercentral.amazon.com")
check("the default marketplace is UK", OA.DEFAULT_MARKETPLACE, "UK")
# The redirect_uri is registered on the portal and must match byte for byte, so
# it is never assembled from the incoming request -- behind a proxy that yields
# http:// or an internal hostname and Amazon rejects it.
check("the redirect uri is the registered one",
      OA.DEFAULT_REDIRECT_URI, "https://app.altascraper.com/auth/callback")
SRC = open(os.path.join(HERE, "routes", "auth_oauth_routes.py"),
           encoding="utf-8").read()


def code_only(src):
    """Source with comments and the module docstring removed.

    Needed because these files EXPLAIN the things they must not do -- the
    header says the file never sends merchant_suggested_asin, and the note
    above the redirect uri says why it is not built from request.url_root.
    A comment recording a rule is not a breach of it, and asserting against
    raw text cannot tell the two apart.
    """
    body = src.split('"""', 2)[-1] if src.lstrip().startswith('"""') else src
    return "\n".join(l.split("#")[0] for l in body.splitlines())


CODE = code_only(SRC)
falsy("  and is not built from the request", "request.url_root" in CODE)
falsy("  nor from the host header", "request.host" in CODE)
# Every marketplace the app knows must be reachable, or a seller picks one from
# the switcher and is told it is unsupported.
missing = sorted(set(ACC.MARKETPLACE_IDS) - set(OA.CONSENT_HOSTS))
check("every marketplace the app knows has a consent host", missing, [])

print("\n== the callback cannot be driven from outside ==")
truthy("state is issued into the caller's own session", "_STATE_SESSION_KEY" in SRC)
truthy("  compared in constant time", "secrets.compare_digest" in SRC)
truthy("  used once, whatever the outcome", "session.pop(_STATE_SESSION_KEY" in SRC)
truthy("  and expires", "_STATE_MAX_AGE_SECONDS" in SRC)
# The marketplace rides in the session, not in the state string, so tampering
# with state cannot change which marketplace the account is created for.
truthy("the marketplace travels in the session, not the state",
       '"marketplace": mkt,' in SRC)
truthy("the code is exchanged server-side", "authorization_code" in SRC)
truthy("  at Amazon's token endpoint",
       OA.TOKEN_ENDPOINT == "https://api.amazon.com/auth/o2/token")

print("\n== refusals happen before the seller is sent to Amazon ==")
# Being told the connection failed AFTER approving a permissions screen is a
# worse experience than being told it is not ready.
_login = SRC.split("def oauth_login")[1].split("def oauth_callback")[0]
truthy("no app credentials -> refuse up front", "ALTA_LWA_CLIENT_ID" in _login)
truthy("no encryption key -> refuse up front", "have_key()" in _login)
truthy("  saying nothing was sent to Amazon", "Nothing was sent to Amazon" in _login)

print("\n== connecting a seller does not switch the app to them ==")
_cb = SRC.split("def oauth_callback")[1]
falsy("the callback does not select the account", "active_account_id" in _cb)
# A fragment inside ONE literal: the sentence wraps across two source lines, so
# the phrase it reads as does not exist contiguously in the file.
truthy("  and says where to find it", "switcher; open it there" in _cb)
# Re-authorizing must UPDATE the record, not leave a second one holding a
# stale token that something might still pick up.
truthy("the account id is derived from the seller", 'acct_id = "amzn_%s_%s"' in _cb)

print("\n== both routes are reachable without signing in ==")
G = open(os.path.join(HERE, "auth", "guard.py"), encoding="utf-8").read()
truthy("login is public", '"oauth_login"' in G)
truthy("callback is public", '"oauth_callback"' in G)
truthy("  and why is written down, not just done",
       "SELLER AUTHORIZING US" in G)

print("\n== rule 12: one credential lookup, no hand-made copies ==")
for f in ("sp_diagnose.py", "sp_api_doctor.py"):
    s = open(os.path.join(HERE, f), encoding="utf-8").read()
    truthy("%s asks accounts.account_creds()" % f, "account_creds(acc)" in s)
falsy("sp_diagnose no longer rebuilds the creds dict",
      '"refresh_token":     acc.get("refresh_token", ""),'
      in open(os.path.join(HERE, "sp_diagnose.py"), encoding="utf-8").read())

print("\n== rule 1 is untouched ==")
# This file authenticates sellers. It has no opinion about listing mode.
falsy("no merchant_suggested_asin", "merchant_suggested_asin" in CODE)
falsy("no LISTING_OFFER_ONLY", "LISTING_OFFER_ONLY" in CODE)
falsy("  and it does not build listing payloads at all", "putListingsItem" in CODE)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
