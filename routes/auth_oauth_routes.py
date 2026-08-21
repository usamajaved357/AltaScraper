"""routes/auth_oauth_routes.py — multi-tenant Amazon OAuth (Login with Amazon).

Lets a seller who is not us authorize this app, so SP-API calls can be made on
their behalf. Two routes and nothing else:

    GET /auth/login     send the seller to Amazon's consent page
    GET /auth/callback  Amazon sends them back; swap the code for a token

WHERE THE CREDENTIALS GO
------------------------
Into the account model this app already has (domain/accounts.py), not a new
sellers table. Chosen deliberately: every SP-API call in this app -- listings,
orders, pricing, reports, submit -- already resolves its credentials through
accounts.account_creds(). Writing OAuth sellers into the same shape means all
of that works for them on day one with no changes, and there is one answer to
"what are this seller's credentials" rather than two that can disagree
(rule 12).

The refresh token is encrypted at rest by save_account (auth/token_crypto.py).

THE APP IS IN DRAFT
-------------------
GREEN HAVEN GOODS LTD's app is not published on the Solution Provider Portal
yet, so the consent URL MUST carry &version=beta. Without it Amazon rejects the
authorization for a draft app. This is a fact about the app's state, not about
the code -- when it is published, remove the parameter. It is a single named
constant below for that reason.

RULE 1 IS NOT TOUCHED HERE. This file authenticates sellers. It does not decide
listing mode, it never sends merchant_suggested_asin, and it has no opinion
about how listings are created.
"""
import datetime as _dt
import json
import os
import re
import secrets
import urllib.parse
import urllib.request

from flask import jsonify, redirect, request, session

# Amazon rejects an authorization for an app that is still in draft unless the
# consent URL says so. Remove when the app is published.
DRAFT_VERSION_PARAM = "beta"

# The application's id on the Solution Provider Portal (GREEN HAVEN GOODS LTD).
# Public -- it appears in the consent URL the seller sees. Not a secret; the
# LWA client secret is, and that one is read from the environment.
APPLICATION_ID = "amzn1.sp.solution.c4570a5c-28b0-4a4a-83ad-7a29695f3786"

TOKEN_ENDPOINT = "https://api.amazon.com/auth/o2/token"

# Which Seller Central a seller consents on. Amazon requires the host for the
# seller's OWN region -- consenting to a UK app on sellercentral.amazon.com
# does not work. Keyed by the same marketplace codes accounts.MARKETPLACE_IDS
# uses, so there is one vocabulary for marketplaces in this app and not two.
CONSENT_HOSTS = {
    "US": "sellercentral.amazon.com",
    "CA": "sellercentral.amazon.ca",
    "MX": "sellercentral.amazon.com.mx",
    "BR": "sellercentral.amazon.com.br",
    "UK": "sellercentral.amazon.co.uk",
    "DE": "sellercentral.amazon.de",
    "FR": "sellercentral.amazon.fr",
    "IT": "sellercentral.amazon.it",
    "ES": "sellercentral.amazon.es",
    "NL": "sellercentral.amazon.nl",
    "SE": "sellercentral.amazon.se",
    "PL": "sellercentral.amazon.pl",
    "BE": "sellercentral.amazon.com.be",
    "TR": "sellercentral.amazon.com.tr",
    "AE": "sellercentral.amazon.ae",
    "SA": "sellercentral.amazon.sa",
    "EG": "sellercentral.amazon.eg",
    "IN": "sellercentral.amazon.in",
    "JP": "sellercentral.amazon.co.jp",
    "AU": "sellercentral.amazon.com.au",
    "SG": "sellercentral.amazon.sg",
}

DEFAULT_MARKETPLACE = "UK"

# Where Amazon sends the seller back. Registered on the Solution Provider
# Portal and must match byte for byte, so it is not assembled from the incoming
# request -- behind a proxy request.url_root can be http:// or an internal
# hostname, and a redirect_uri that differs by one character is rejected with an
# error that names nothing useful.
DEFAULT_REDIRECT_URI = "https://app.altascraper.com/auth/callback"

_STATE_SESSION_KEY = "_oauth_state"
_STATE_MAX_AGE_SECONDS = 900        # 15 minutes to finish consenting


def _redirect_uri():
    return str(os.environ.get("ALTA_OAUTH_REDIRECT_URI")
               or DEFAULT_REDIRECT_URI).strip()


def _now():
    return _dt.datetime.now(_dt.timezone.utc)


def _slug(s):
    """An account id from a seller's name. Same shape accounts._slug makes."""
    out = re.sub(r"[^a-z0-9]+", "_", str(s or "").strip().lower()).strip("_")
    return out or "seller"


def register(app, *, _cfg, CONFIG_PATH):
    """Attach the /auth/login and /auth/callback routes."""
    import accounts as _acc
    from auth import token_crypto as _tc

    def _fail(msg, code=400, **extra):
        """One shape for every refusal, and every one of them says what to do.

        These are read by a seller who has just been bounced out of an Amazon
        consent screen. "invalid_request" tells them nothing; naming the actual
        problem and who can fix it is the difference between a support message
        and a retry.
        """
        body = {"ok": False, "error": msg}
        body.update(extra)
        return jsonify(body), code

    # ----------------------------------------------------------- diagnose
    @app.route("/auth/diagnose")
    def oauth_diagnose():
        """Is THIS RUNNING PROCESS configured to do OAuth?

            "/auth/login returns ... ALTA_LWA_CLIENT_ID and
             ALTA_LWA_CLIENT_SECRET are not both set ... although i have
             deployed the latest code"

        Deploying code does not set environment variables, and there is no way
        to tell from the outside whether a variable is missing, misspelt, set on
        a different service, or set but not picked up because the process was
        never restarted. Guessing between those costs more than answering it.

        NO VALUES ARE RETURNED, and no lengths -- a length is a small leak and
        buys nothing. Only whether each name is present and non-empty, plus
        enough about the host to catch the most likely cause: variables set on
        one platform while another is serving the domain. This repo contains a
        render.yaml as well as a Dockerfile, so that confusion is available.

        Public, like the routes it diagnoses: whoever is fixing the deployment
        needs to read it, and it exposes nothing that is not already implied by
        /auth/login's own refusal message.
        """
        def _set(name):
            return bool(str(os.environ.get(name) or "").strip())

        # ALTA_TOKEN_KEY is reported by VALIDITY, not presence. A key that is
        # set but malformed passes every "is it there" check and then fails at
        # the only moment that costs something -- after a seller has already
        # approved the permissions screen and the one-time code has been spent.
        _kstate, _kwhy = _tc.key_status()
        required = {
            "ALTA_LWA_CLIENT_ID": _set("ALTA_LWA_CLIENT_ID"),
            "ALTA_LWA_CLIENT_SECRET": _set("ALTA_LWA_CLIENT_SECRET"),
            "ALTA_TOKEN_KEY": _kstate == "ok",
        }
        recommended = {
            # Not required to start the flow, but the state nonce lives in the
            # Flask session, which is signed with this. Unset means a new random
            # key every boot and every worker, so the state check fails
            # intermittently and confusingly. See the note in dashboard.py.
            "APP_SECRET_KEY": _set("APP_SECRET_KEY"),
        }
        optional = {
            "ALTA_OAUTH_REDIRECT_URI": _set("ALTA_OAUTH_REDIRECT_URI"),
        }
        # Which platform is actually running this. Each injects its own marker.
        host = "unknown"
        if os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"):
            host = "render"
        elif os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_SERVICE_ID"):
            host = "railway"
        elif os.environ.get("WEBSITE_INSTANCE_ID"):
            host = "azure"
        elif os.environ.get("DYNO"):
            host = "heroku"

        ready = all(required.values())
        notes = []
        # A KEY THAT IS SET BUT WRONG is a different problem from one that is
        # absent, and saying "missing" for it sends somebody to add a variable
        # that is already there. Reported separately.
        if _kstate == "invalid":
            notes.append("ALTA_TOKEN_KEY IS SET BUT UNUSABLE. " + _kwhy)
        if not ready:
            missing = [k for k, v in required.items()
                       if not v and not (k == "ALTA_TOKEN_KEY" and _kstate == "invalid")]
            if missing:
                notes.append(
                    "Not ready. Missing on the RUNNING process: %s. Setting a "
                    "variable is not the same as deploying code -- add them in "
                    "the dashboard of the platform actually serving this "
                    "domain, then restart or redeploy so the process picks "
                    "them up." % ", ".join(missing))
        if host != "unknown":
            notes.append(
                "This process is running on %s. If you set the variables "
                "somewhere else, that is the whole problem." % host)
        else:
            notes.append(
                "Could not tell which platform is running this from its "
                "environment. This repo carries BOTH a render.yaml and a "
                "Dockerfile, so check which one actually serves "
                "app.altascraper.com before adding variables anywhere.")
        if ready and not recommended["APP_SECRET_KEY"]:
            notes.append(
                "APP_SECRET_KEY is not set. OAuth will start, but the state "
                "check lives in the Flask session and that session is signed "
                "with a key that is randomly regenerated on every boot and per "
                "worker when this is unset -- so authorizations will fail "
                "intermittently with 'this authorization did not start here'.")
        return jsonify({"ok": True, "ready_for_oauth": ready,
                        "required": required, "recommended": recommended,
                        "optional": optional, "host": host, "notes": notes})

    # ---------------------------------------------------------------- login
    @app.route("/auth/login")
    def oauth_login():
        """Send a seller to Amazon to approve this app.

        Refuses BEFORE the redirect if this deployment cannot finish the job.
        Discovering that the token cannot be stored only AFTER the seller has
        read a permissions screen and pressed Confirm wastes their time and
        looks broken; the checks that can be made early are made early.
        """
        mkt = str(request.args.get("marketplace")
                  or DEFAULT_MARKETPLACE).strip().upper()
        host = CONSENT_HOSTS.get(mkt)
        if not host:
            return _fail(
                "This app does not know which Seller Central to send you to for "
                "marketplace %r. Supported: %s."
                % (mkt, ", ".join(sorted(CONSENT_HOSTS))),
                marketplace=mkt)

        cid, sec = _acc.oauth_app_creds()
        if not cid or not sec:
            return _fail(
                "This deployment is not configured to connect Amazon sellers "
                "yet: ALTA_LWA_CLIENT_ID and ALTA_LWA_CLIENT_SECRET are not "
                "both set. Add them in the Railway dashboard and redeploy. "
                "Nothing was sent to Amazon.", 503)
        # Refuse here rather than after consent -- see token_crypto's header.
        # key_status(), not have_key()-as-presence: a key that is SET but
        # malformed used to pass this check, send the seller to Amazon, and fail
        # only on the way back with the token already exchanged.
        _kstate, _kwhy = _tc.key_status()
        if _kstate != "ok":
            return _fail(
                "This deployment cannot store a seller's Amazon token securely "
                "yet, and this app will not hold somebody else's Amazon token "
                "unencrypted. %s Nothing was sent to Amazon." % _kwhy,
                503, token_key=_kstate)

        # CSRF: a nonce we issue, keep in the caller's own session, and require
        # back unchanged. Without it, anyone could hand a seller a crafted
        # callback URL and have this app attach a token to an account of their
        # choosing. The marketplace rides along in the session rather than in
        # the state string, so a tampered state cannot change which marketplace
        # the resulting account is created for.
        nonce = secrets.token_urlsafe(32)
        session[_STATE_SESSION_KEY] = {
            "nonce": nonce,
            "marketplace": mkt,
            "issued": _now().isoformat(),
        }
        session.modified = True

        params = {
            "application_id": APPLICATION_ID,
            "redirect_uri": _redirect_uri(),
            "state": nonce,
        }
        if DRAFT_VERSION_PARAM:
            params["version"] = DRAFT_VERSION_PARAM
        url = "https://%s/apps/authorize/consent?%s" % (
            host, urllib.parse.urlencode(params))
        return redirect(url, code=302)

    # ------------------------------------------------------------- callback
    @app.route("/auth/callback")
    def oauth_callback():
        """Amazon sends the seller back here after they approve.

        Amazon appends: spapi_oauth_code (one-time, short-lived),
        selling_partner_id (the seller's merchant token) and the state we
        issued. The code is exchanged for a refresh token, which is the thing
        worth having -- it is long-lived and is what every later SP-API call is
        built from.
        """
        code = str(request.args.get("spapi_oauth_code") or "").strip()
        partner = str(request.args.get("selling_partner_id") or "").strip()
        got_state = str(request.args.get("state") or "").strip()

        want = session.get(_STATE_SESSION_KEY) or {}
        session.pop(_STATE_SESSION_KEY, None)   # single use, whatever happens

        if not want.get("nonce"):
            return _fail(
                "This authorization did not start here, or the browser dropped "
                "the session before Amazon sent you back. Start again from the "
                "Connect Amazon link.", 400)
        # secrets.compare_digest: constant-time, so a wrong state cannot be
        # found one character at a time by timing the replies.
        if not got_state or not secrets.compare_digest(got_state, want["nonce"]):
            return _fail(
                "This authorization could not be verified as the one that "
                "started here, so nothing was saved. Start again from the "
                "Connect Amazon link.", 400)
        try:
            issued = _dt.datetime.fromisoformat(want.get("issued", ""))
            if (_now() - issued).total_seconds() > _STATE_MAX_AGE_SECONDS:
                return _fail(
                    "This authorization took longer than 15 minutes, so it was "
                    "not accepted. Start again from the Connect Amazon link.",
                    400)
        except Exception:
            pass

        if not code:
            # Amazon also lands here when the seller presses Cancel.
            return _fail(
                "Amazon did not send an authorization code back, which usually "
                "means the approval was cancelled. Nothing was saved.", 400)
        if not partner:
            return _fail(
                "Amazon did not say which seller account this authorization is "
                "for, so it cannot be stored against one. Nothing was saved.",
                400)

        mkt = str(want.get("marketplace") or DEFAULT_MARKETPLACE).upper()
        cid, sec = _acc.oauth_app_creds()
        if not cid or not sec:
            return _fail(
                "This deployment is missing ALTA_LWA_CLIENT_ID / "
                "ALTA_LWA_CLIENT_SECRET, so the code Amazon returned cannot be "
                "exchanged. Nothing was saved.", 503)

        # --- exchange the one-time code for a refresh token -----------------
        payload = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _redirect_uri(),
            "client_id": cid,
            "client_secret": sec,
        }).encode("utf-8")
        req = urllib.request.Request(
            TOKEN_ENDPOINT, data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                tok = json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            # Amazon's error body names the actual fault (invalid_grant,
            # invalid_client, redirect_uri mismatch) and is worth surfacing --
            # it is the difference between "it failed" and "the redirect URI on
            # the portal does not match this deployment".
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:400]
            except Exception:
                detail = str(e)[:400]
            return _fail(
                "Amazon refused to exchange the authorization code, so nothing "
                "was saved. Amazon said: %s" % detail, 502)

        refresh = str(tok.get("refresh_token") or "").strip()
        if not refresh:
            return _fail(
                "Amazon returned a response with no refresh token in it, so "
                "there is nothing to store. Nothing was saved.", 502,
                amazon_response={k: v for k, v in (tok or {}).items()
                                 if k != "access_token"})

        # --- store it as an account -----------------------------------------
        # The id is derived from the seller's merchant token, so a seller who
        # re-authorizes UPDATES their record instead of creating a second one
        # holding a now-stale token.
        acct_id = "amzn_%s_%s" % (_slug(partner), mkt.lower())
        cfg = _cfg()
        existing = {}
        try:
            existing = _acc.get_account(cfg, acct_id, CONFIG_PATH) or {}
        except Exception:
            existing = {}
        # AND IF SOME OTHER WORKSPACE IS ALREADY THIS SELLER, IT IS THAT ONE.
        #
        # The id above is derived from the merchant token so that authorizing
        # twice updates one record. It only ever looked at the id, though, so a
        # seller who had been set up BY HAND -- with a label, an output sheet, a
        # VAT rate, a COGS mode and a marketplace list -- got a second, bare
        # workspace on their first authorization.
        #
        # Seen on the live app, 21 Aug 2026: the switcher listed "Nestwell Goods
        # LTD" and "Amazon seller ZAAYT4". Both are A8YN8LJZAAYT4. The same
        # company, twice, with listings and costs landing in whichever was open.
        #
        # One Amazon seller is one workspace (domain/accounts.by_seller_id).
        if not existing:
            try:
                existing = _acc.by_seller_id(cfg, partner, CONFIG_PATH, mkt) or {}
            except Exception:
                existing = {}
            if existing.get("id"):
                # Write into the record that is already there, keeping its id,
                # so nothing that points at it -- sheets, stored listings,
                # orders, costs -- is orphaned.
                acct_id = str(existing["id"])

        account = {
            **existing,
            "id": acct_id,
            "label": existing.get("label") or ("Amazon seller %s" % partner[-6:]),
            "seller_id": partner,
            "marketplace": mkt,
            "auth": "oauth",
            "refresh_token": refresh,      # save_account encrypts it
            "status": "active",
            "authorized_at": _now().isoformat(),
        }
        try:
            _acc.save_account(cfg, CONFIG_PATH, account)
        except _tc.TokenKeyMissing as e:
            return _fail(str(e), 503)
        except Exception as e:
            # SAY WHAT WENT WRONG, NOT JUST ITS CLASS NAME.
            #
            # This reported type(e).__name__ and threw the message away, so a
            # real failure surfaced as "could not save it (RuntimeError)" --
            # which names nothing, fixes nothing, and sends somebody to the
            # hosting platform's logs to find a sentence this process already
            # had in its hand. That happened, on a live authorization.
            #
            # The one RuntimeError reachable here is our own, from
            # token_crypto._fernet(), and it says exactly what is wrong with the
            # key. It contains no key material -- it names the variable and the
            # underlying exception type -- so it is safe to return.
            #
            # Anything else is unexpected, so it gets the class name AND its
            # message, truncated. An error a user cannot act on is a bug in the
            # error, not just in the thing that failed.
            _detail = str(e).strip() or type(e).__name__
            return _fail(
                "The authorization with Amazon SUCCEEDED, but this app could "
                "not store the token, so nothing was saved. %s Once that is "
                "fixed, ask the seller to connect again — the code Amazon sent "
                "is single-use and has now been spent."
                % _detail[:400], 500,
                failed_at="storing the token, after Amazon had already approved",
                exception=type(e).__name__)

        # Deliberately NOT selected as the active account. Connecting a seller
        # and switching the whole app over to them are two different intentions,
        # and doing the second silently is how the next action lands on the
        # wrong shopfront.
        return jsonify({
            "ok": True,
            "account_id": acct_id,
            "seller_id": partner,
            "marketplace": mkt,
            "message": "Amazon account connected. It is now in the account "
                       "switcher; open it there when you want to work on it.",
        })

    return app
