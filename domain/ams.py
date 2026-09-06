"""domain/ams.py -- is Amazon Marketing Stream available? Answered in ONE place.

WHAT AMS IS, AND WHY THE ANSWER IS CURRENTLY NO

Amazon publishes advertising figures BY HOUR only through Marketing Stream, a
push integration: Amazon posts to an AWS SQS queue and something on our side
drains it. There is no pull API for it. Measured on this account, asking the
ordinary reporting API for hourly data is refused in Amazon's own words --
"configuration timeUnit is not supported for this report type".

PHASE 4 IS DELIBERATELY NOT BUILT. By instruction:

    "Skip Phase 4 entirely (AMS/AWS). Owner doesn't have an AWS account. Build
     the graceful degradation fallbacks instead ... Keep the env var check
     (AWS_SQS_QUEUE_URL) in code so AMS auto-activates if added later, but
     don't build the AMS subscription or SQS consumer"

So there is no ads_hourly table, no hourly_baseline_cache, and no
workers/ams_consumer.py. This module is the on-ramp and nothing else: it says
whether AMS is configured and whether its data has actually arrived, so the
screens can ask one question instead of each inventing its own test.

THE TRAP THIS MODULE EXISTS TO AVOID

"Auto-activates if added later" is easy to write as `if AWS_SQS_QUEUE_URL is
set: use hourly data`. That is wrong, and it fails in the worst direction:
setting an environment variable is not the same as hours having arrived. A
queue URL can be set on the day the queue is created, hours before the first
message lands -- and with no consumer built, it can be set for ever without a
single row being stored. A screen that switched on the variable alone would go
looking for hourly data that does not exist and draw an empty grid where it had
been drawing a correct daily one.

So configured() and available() are DIFFERENT QUESTIONS and both are answered:

    configured()  the environment names a queue. A statement about setup.
    available()   hourly rows are actually stored and readable. A statement
                  about DATA, and the only one a screen may switch on.

available() is False today and will stay False until something writes hourly
rows, whatever the environment says. That is the honest meaning of
auto-activation: the screens follow the data, not the intent.

NOTHING HERE TALKS TO AWS. No boto3, no queue, no subscription -- by
instruction. When Phase 4 is really wanted, the consumer writes the table and
available() starts answering True on its own, with no screen changing.
"""
import os

# The five Railway variables Phase 4 would need. Named here so the day someone
# sets them, the diagnostic can say which are present and which are missing
# rather than "not configured".
ENV_QUEUE_URL = "AWS_SQS_QUEUE_URL"
ENV_VARS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", ENV_QUEUE_URL,
            "AWS_SQS_QUEUE_ARN", "AWS_REGION")

# The table a consumer would write. Named, not created -- checking for it by
# name is what lets available() answer honestly without the table existing.
HOURLY_TABLE = "ads_hourly"


def _env(name):
    return str(os.environ.get(name) or "").strip()


def configured():
    """Does the environment name an SQS queue? Setup, not data.

    The queue URL alone, because that is the one the instruction named and the
    one without which nothing else matters. missing() reports the full set.
    """
    return bool(_env(ENV_QUEUE_URL))


def missing():
    """Which of the five variables are not set. Empty when all are."""
    return [n for n in ENV_VARS if not _env(n)]


def available(config_path=None):
    """Are there hourly rows to read? The ONLY question a screen may switch on.

    Deliberately not `configured()`. See the module docstring: an environment
    variable is a statement of intent and this is a statement of fact, and a
    screen that followed the intent would abandon a correct daily chart for an
    empty hourly one.

    Never raises. A database that cannot be opened means no hourly data, which
    is the same answer as no table, and both leave the daily fallback drawing.
    """
    try:
        from data import db as _db
        conn = _db.get_db(config_path) if config_path else _db.get_db()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (HOURLY_TABLE,)).fetchone()
        if not row:
            return False
        got = conn.execute(
            "SELECT 1 FROM %s LIMIT 1" % HOURLY_TABLE).fetchone()
        return bool(got)
    except Exception:
        return False


def status(config_path=None):
    """Everything a screen or a diagnostic needs, in one dict.

    `why` is written for a person rather than a log: it names what is absent and
    what is being drawn instead, so an hourly panel showing daily figures reads
    as a decision rather than as something broken.
    """
    gone = missing()
    have = available(config_path)
    if have:
        why = "Hourly data is stored, so hourly panels can be drawn."
    elif not gone:
        # Every variable set and still no rows: the consumer is the missing
        # half, and saying so stops someone re-checking their AWS console.
        why = ("An SQS queue is configured but no hourly rows have been stored. "
               "The consumer that drains the queue is not built, so panels are "
               "drawn from daily figures.")
    elif configured():
        why = ("An SQS queue is named but %d of the AWS settings are missing "
               "(%s), and no hourly rows are stored. Panels are drawn from "
               "daily figures." % (len(gone), ", ".join(gone)))
    else:
        why = ("Amazon publishes hourly advertising figures only through "
               "Marketing Stream, which needs an AWS SQS queue. None is "
               "configured, so every panel is drawn at the finest grain that "
               "exists, which is a day.")
    return {"configured": configured(), "available": have,
            "missing_env": gone, "why": why}
