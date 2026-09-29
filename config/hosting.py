"""config/hosting.py -- is this app running on a hosting platform, and which?

ONE ANSWER. The question was asked in four places, each with its own list of
environment markers (domain/deploy_check.py, domain/media_recover.py,
routes/auth_oauth_routes.py, and now the sign-in gate), and the lists had
already drifted: one knew RENDER_SERVICE_ID and Azure, two did not. A gate
that decides whether the app is open to the internet must not be the copy that
forgot a marker (CLAUDE.md Rule 12; Milestone 2, 28 Sep 2026).

Each platform injects its own variable into every process it runs; none of
them is set on the owner's Windows machine.
"""
import os

# (platform, markers) -- first match wins.
_MARKERS = (
    ("render",  ("RENDER", "RENDER_SERVICE_ID")),
    ("railway", ("RAILWAY_ENVIRONMENT", "RAILWAY_SERVICE_ID")),
    ("azure",   ("WEBSITE_INSTANCE_ID",)),
    ("heroku",  ("DYNO",)),
)


def platform(environ=None):
    """"render" / "railway" / "azure" / "heroku", or "" when not hosted."""
    env = os.environ if environ is None else environ
    for name, keys in _MARKERS:
        if any(env.get(k) for k in keys):
            return name
    return ""


def is_hosted(environ=None):
    """True when a hosting platform is running this process."""
    return bool(platform(environ))
