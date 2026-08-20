"""The privacy policy has to exist, and has to be readable without signing in.

    "the page https://app.altascraper.com/privacy says Not Found"

NOT COSMETIC. Amazon's Solution Provider Portal requires a reachable privacy
policy URL and checks it when an app is submitted for publication, so a 404 here
is one of the things keeping the app in DRAFT (see [[oauth-multitenant]] and
routes/auth_oauth_routes.py). It is also the page a seller is entitled to read
BEFORE handing this app a token that can rewrite and delete their listings.

PUBLIC IS THE POINT. Amazon's checker has no account here, and neither does a
seller deciding whether to connect. A policy behind a login is a login form.

WHAT THE TEXT MUST DO. Say what the code actually does, not boilerplate -- which
scopes are read, who receives what, where the token lives. The two claims worth
pinning are the ones a seller would most want to be true and would have no way
to verify: that buyer personal data never reaches an AI provider, and that the
token is encrypted at rest and revocable without our involvement. Both are
statements about behaviour asserted elsewhere in this suite
(test_oauth_multitenant.py), so the page and the code cannot quietly disagree.

NOT LEGALLY REVIEWED. This suite can check the page is accurate about the
system. Whether it satisfies UK GDPR is a question for somebody qualified.
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


def read(*p):
    return open(os.path.join(HERE, *p), encoding="utf-8").read()


PRIV = read("templates", "privacy.html")
TERMS = read("templates", "terms.html")
LEGAL = read("routes", "legal_routes.py")
GUARD = read("auth", "guard.py")
DASH = read("dashboard.py")

print("== the routes exist and are wired in ==")
truthy("there is a /privacy route", '@app.route("/privacy")' in LEGAL)
truthy("there is a /terms route", '@app.route("/terms")' in LEGAL)
truthy("and they are registered", "_legal_routes.register(app)" in DASH)
# Rule 7: a new feature gets its own file rather than growing dashboard.py.
truthy("in their own module", os.path.exists(os.path.join(HERE, "routes", "legal_routes.py")))

print("\n== and are readable without signing in ==")
truthy("privacy is public", '"privacy_page"' in GUARD)
truthy("terms is public", '"terms_page"' in GUARD)
truthy("  and why is written down, not just done",
       "finds a login form instead of a policy" in GUARD)

print("\n== the policy is specific about what is read ==")
for claim in ("Selling Partner API", "listings", "Orders", "Finances",
              "Inventory", "postcode"):
    truthy("names %s" % claim, claim in PRIV)

print("\n== and about who else receives data ==")
truthy("names Amazon", "Amazon" in PRIV)
truthy("names Anthropic", "Anthropic" in PRIV)
truthy("names Google", "Google" in PRIV)
truthy("and the hosting provider", "Hosting provider" in PRIV)

print("\n== the two claims a seller cannot verify for themselves ==")
# Both are behaviours asserted in test_oauth_multitenant.py, so the page and the
# code cannot quietly drift apart.
truthy("buyer data never goes to an AI provider",
       "never sent to any AI provider" in PRIV)
# Fragments that sit within ONE line: the prose wraps in the source, so the
# sentence as it reads does not exist contiguously in the file.
truthy("  and the AI section says so too", "Order and buyer data is" in PRIV)
truthy("the token is encrypted at rest", "stored encrypted at rest" in PRIV)
truthy("  with the key outside the code and config",
       "rather than in the application's" in PRIV)
truthy("and revocation does not need us",
       "without needing our involvement" in PRIV)
truthy("  naming where to do it", "Manage Your Apps" in PRIV)

print("\n== it does not claim more than is true ==")
# A policy that promises a guarantee nobody is running is worse than none.
falsy("no uptime guarantee is implied in the terms",
      "guaranteed uptime" in TERMS and "we guarantee" in TERMS.lower())
truthy("the terms say availability is not guaranteed",
       "without a guaranteed uptime" in TERMS)
truthy("and that AI output can be wrong", "AI output can be" in TERMS)
# Rule 1: the owner publishes under their OWN brands, so responsibility for
# what is published sits with them, and the terms should say so plainly.
truthy("the seller stays responsible for what is published",
       "you decide what is sent to" in TERMS)

print("\n== the pages point at each other, so neither is a dead end ==")
truthy("privacy links to terms", 'href="/terms"' in PRIV)
truthy("terms links to privacy", 'href="/privacy"' in TERMS)
truthy("and both name the operating company", "{{ owner }}" in PRIV and "{{ owner }}" in TERMS)
truthy("  with a real default", "GREEN HAVEN GOODS LTD" in LEGAL)

print("\n== and the file says out loud that it is not legal advice ==")
truthy("the module records that no lawyer has reviewed it",
       "HAS NOT BEEN REVIEWED BY A LAWYER" in LEGAL)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
