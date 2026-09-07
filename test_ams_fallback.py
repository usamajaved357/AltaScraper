"""Phase 4 is NOT built, and the panels that wanted it degrade honestly.

    "Skip Phase 4 entirely (AMS/AWS). Owner doesn't have an AWS account. Build
     the graceful degradation fallbacks instead ... Do NOT create ads_hourly
     table, hourly_baseline_cache table, or workers/ams_consumer.py ... Keep
     the env var check (AWS_SQS_QUEUE_URL) in code so AMS auto-activates if
     added later, but don't build the AMS subscription or SQS consumer"

Amazon publishes hourly advertising figures only through Marketing Stream, a
push integration needing an AWS SQS queue. There is no pull API: asking the
ordinary reporting endpoint for hourly data is refused in Amazon's own words,
"configuration timeUnit is not supported for this report type".

THE TRAP THIS FILE GUARDS. "Auto-activates if added later" is easy to write as
`if AWS_SQS_QUEUE_URL is set: draw hourly`. That fails in the worst direction:
a queue URL can be set the moment the queue is created, hours before the first
message lands -- and with no consumer built, for ever. A screen switching on
the variable would abandon a correct daily chart for an empty hourly one. So
`configured` (setup) and `available` (data) are separate questions, and only
`available` may change what is drawn.
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
    print("  %-64s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from domain import ams

CFG = os.path.join(HERE, "config.json")

print("=== nothing from AWS is built ===")
falsy("there is no SQS consumer worker",
      os.path.exists(os.path.join(HERE, "workers", "ams_consumer.py")))
falsy("  nor a workers package at all",
      os.path.isdir(os.path.join(HERE, "workers")))
DB = open(os.path.join(HERE, "data", "db.py"), encoding="utf-8").read()
falsy("no ads_hourly table is created", "ads_hourly" in DB)
falsy("  nor hourly_baseline_cache", "hourly_baseline_cache" in DB)
AMS = open(os.path.join(HERE, "domain", "ams.py"), encoding="utf-8").read()
# THE IMPORT, not the word. ams.py says "No boto3, no queue, no subscription"
# in its own docstring -- prose explaining what it deliberately does not do,
# which is the opposite of the thing being guarded against. An earlier form of
# this check matched the word and failed on that sentence.
falsy("nothing imports boto3", "import boto3" in AMS)
falsy("  and nothing subscribes to a stream",
      "create_stream_subscription" in AMS or "sqs.receive_message" in AMS)
falsy("  no AWS client is ever built", "boto3.client(" in AMS)
try:
    REQ = open(os.path.join(HERE, "requirements.txt"), encoding="utf-8").read()
    falsy("  boto3 is not a dependency", "boto3" in REQ)
except IOError:
    pass

print("\n=== configured and available are DIFFERENT questions ===")
_saved = {n: os.environ.get(n) for n in ams.ENV_VARS}
try:
    for n in ams.ENV_VARS:
        os.environ.pop(n, None)
    falsy("with nothing set, nothing is configured", ams.configured())
    falsy("  and nothing is available", ams.available(CFG))
    check("  all five variables are reported missing",
          len(ams.missing()), len(ams.ENV_VARS))
    truthy("  and the reason names Marketing Stream",
           "Marketing Stream" in ams.status(CFG)["why"])

    # THE ONE THE INSTRUCTION NAMED.
    os.environ["AWS_SQS_QUEUE_URL"] = "https://sqs.us-east-1.amazonaws.com/1/q"
    truthy("a queue URL alone counts as configured", ams.configured())
    falsy("  but STILL does not make hourly data available", ams.available(CFG))
    truthy("  and the reason says which settings are missing",
           "missing" in ams.status(CFG)["why"])

    # EVERY VARIABLE SET, AND STILL NO DATA -- because no consumer exists.
    for n in ams.ENV_VARS:
        os.environ[n] = "set"
    os.environ["AWS_SQS_QUEUE_URL"] = "https://sqs.us-east-1.amazonaws.com/1/q"
    check("with every variable set, none is missing", ams.missing(), [])
    truthy("  it reads as configured", ams.configured())
    falsy("  and hourly data is STILL not available", ams.available(CFG))
    truthy("  because the consumer is not built, and it says so",
           "consumer" in ams.status(CFG)["why"])
finally:
    for n, v in _saved.items():
        if v is None:
            os.environ.pop(n, None)
        else:
            os.environ[n] = v

print("\n=== it flips on its own when hours really arrive ===")
# Not by an environment variable, and not by anybody editing a screen: by rows
# existing. Exercised against a real table rather than asserted from the source.
import sqlite3
import tempfile
import types

import data as _data_pkg
_real_db = _data_pkg.db
_tmp = os.path.join(tempfile.mkdtemp(prefix="altaams_"), "h.db")
_c = sqlite3.connect(_tmp)


class _Conn(object):
    def execute(self, q, a=()):
        return _c.execute(q, a)


try:
    _data_pkg.db = types.SimpleNamespace(get_db=lambda *a, **k: _Conn())
    falsy("no table at all -> not available", ams.available(CFG))
    _c.execute("CREATE TABLE ads_hourly (workspace_id TEXT, spend REAL)")
    _c.commit()
    falsy("  a table with no rows is not data either", ams.available(CFG))
    _c.execute("INSERT INTO ads_hourly VALUES ('x', 1.0)")
    _c.commit()
    truthy("  one stored hour, and it is available", ams.available(CFG))
finally:
    _data_pkg.db = _real_db
    _c.close()

print("\n=== a database that cannot be read never crashes a screen ===")
try:
    _data_pkg.db = types.SimpleNamespace(
        get_db=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no db")))
    falsy("an unreadable database means no hourly data, not an exception",
          ams.available(CFG))
    truthy("  and status still answers", bool(ams.status(CFG)["why"]))
finally:
    _data_pkg.db = _real_db

print("\n=== the PPC screen asks ams, and does not test the env itself ===")
PA = open(os.path.join(HERE, "domain", "ppc_analytics.py"),
          encoding="utf-8").read()
truthy("availability delegates to the one module", "_ams.status(config_path)" in PA)
falsy("  and never reads the AWS variables itself", "AWS_SQS" in PA)
falsy("  nor hardcodes hourly as impossible", '"hourly": {"ok": False' in PA)
truthy("the panel's ok follows STORED ROWS", '_hourly["available"]' in PA)
truthy("  and carries the setup state for the diagnostic",
       '"configured": _hourly["configured"]' in PA)

print("\n=== the day trail draws days, and says so ===")
# IT DRAWS A CURVE, NOT BARS, AND THAT IS THE OWNER'S CHOICE.
#
#     "see day trail graphs that were real graphs earlier but in the recent
#      edits you made the thick candles, please revert the day trails graph
#      style"
#
# It was briefly one bar per card. The argument for bars was that a running
# total can only climb, so the last card always stands tallest -- but he has
# seen both and prefers the curve. What this file cares about is the thing that
# would be dishonest either way: that the panel does not imply HOURS it does not
# have.
PJ = open(os.path.join(HERE, "static", "js", "ppcanalytics.js"),
          encoding="utf-8").read()
truthy("each card draws the cumulative curve", "ppcMiniLine(cum.slice(" in PJ)
truthy("  and the caption says these are days, not hours",
       "days rather than hours" in PJ)
truthy("  naming why there are no hours to draw",
       "no hourly figures" in PJ)
# The running total is a different figure from the day's own spend, and the
# hover has to name it or the shape is read as one day's spend.
truthy("  the hover names the running total for what it is",
       "Spent so far this window" in PJ)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
raise SystemExit(1 if fails else 0)
