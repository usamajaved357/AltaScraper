"""routes/legal_routes.py — the public legal pages.

    "the page https://app.altascraper.com/privacy says Not Found"

WHY THIS IS NOT COSMETIC. Amazon's Solution Provider Portal requires a reachable
privacy policy URL, and it is checked when an app is submitted for publication.
The app is in DRAFT (see routes/auth_oauth_routes.py), and this being a 404 is
one of the things that stops it leaving draft. It is also the page a seller is
entitled to read BEFORE deciding whether to hand this app a token that can
rewrite their listings.

PUBLIC BY NECESSITY, like the OAuth routes beside it: the reader is a seller who
has no account here and never will. Nothing on these pages is account data --
they are static text about how the app behaves.

THE TEXT IS A FACTUAL DESCRIPTION OF WHAT THE CODE ACTUALLY DOES, written from
the code: which Amazon scopes are read, which third parties receive data, where
tokens live and how they are protected. It is deliberately specific rather than
boilerplate, because a vague policy is worse than none -- it is the document
somebody relies on.

IT HAS NOT BEEN REVIEWED BY A LAWYER. It is accurate about the system; whether
it is sufficient for UK GDPR and for Amazon's own acceptable-use terms is a
question for somebody qualified, and the owner has been told so plainly rather
than left to assume this page is finished.
"""
from flask import render_template


def register(app, *, OWNER_NAME="GREEN HAVEN GOODS LTD", OWNER_EMAIL="",
             OWNER_CRN="16578100"):
    """Attach /privacy and /terms."""

    @app.route("/privacy")
    def privacy_page():
        return render_template("privacy.html",
                               owner=OWNER_NAME, crn=OWNER_CRN,
                               email=OWNER_EMAIL)

    @app.route("/terms")
    def terms_page():
        # Amazon asks for a privacy policy; a terms page is not required, but a
        # link to one that 404s is worse than no link, and the portal form has a
        # field for it. Kept in the same file so the two cannot drift.
        return render_template("terms.html",
                               owner=OWNER_NAME, crn=OWNER_CRN,
                               email=OWNER_EMAIL)

    return app
