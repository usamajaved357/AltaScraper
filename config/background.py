"""config/background.py -- may this process start background work?

    ALTASCRAPER_BACKGROUND=off     (also 0 / false / no)

WHY. The roadmap's safe parallel server test (29 Sep 2026) runs a second copy of
the app beside production. Every copy used to start, unconditionally, the job
timers (including sourcing_apply, which pushes repricer prices), the ASIN
monitor loop, the live-catalogue refresher and the nightly Google backup -- so a
test copy on a copy of the data would have repeated production's Amazon reads,
Google writes and, with auto-pricing on, price pushes. With this set to off,
none of them start; every screen, every button and /jobs/run/<job> still work,
so anything can still be done on purpose.

Unset (the default) changes nothing. Each starter asks enabled() itself
(data/scheduler.start and register_jobs' one-time supplier repair,
monitor/checker.start_scheduler, domain/live_refresher.start,
domain/backup.NIGHTLY.start), so there is one switch and no logic in
dashboard.py (CLAUDE.md Rule 7).

ONLY THIS BUILD HAS IT. An older build (production 0e5529e) ignores the
variable, so a test copy running old code must have the outside services
blanked in its config instead (docs/runbooks/backup-and-parallel-test.md).
"""
import os

ENV = "ALTASCRAPER_BACKGROUND"
_OFF = ("off", "0", "false", "no")


def enabled(environ=None):
    """True unless ALTASCRAPER_BACKGROUND says off."""
    env = os.environ if environ is None else environ
    return str(env.get(ENV) or "").strip().lower() not in _OFF


def refusal(what):
    """The line a starter prints / returns when it is switched off."""
    return "%s not started: %s=off (a test or parallel copy)" % (what, ENV)
