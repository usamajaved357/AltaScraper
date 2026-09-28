"""Every background job names its account when it starts (architecture batch A10).

A job runs after the request that started it is gone, so "the open account" at
the time it finishes can belong to another tab or another person. The rule the
code already follows, pinned here so it cannot be lost:

    job               stamped at start with                     and then
    image batch       request_account.current() -> _acct_id    files each image there
    auto-fix          account_id on the job                     stops if the open account moves
    preview queue     account_id= on enqueue                    keyed per account
    /run/<mode>       the account captured in the request       refuses when none is open

Two remaining fallbacks are RECORDED, not changed (docs/architecture-audit-
2026-09-29.md, bugs 8-9): an image batch started with NO account falls back at
finish time to whatever is open then, and the ASIN monitor defaults to jack_uk.
The checks below read raw file bytes: they are about these exact files.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

fails = []


def truthy(l, g):
    if not g:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if g else "FAIL"))


def src(p):
    return open(p, "rb").read().decode("utf-8")


G = src("routes/genimage_routes.py")
start = G[G.index("def genimage_start_batch"):]
start = start[:start.index("\n    @app.route")] if "\n    @app.route" in start else start
truthy("image batch: account taken from the request at enqueue",
       "_acct_now = _rqa.current(_state)" in start)
truthy("  SET on every job, never setdefault (browser cannot choose it)",
       'jb["_acct_id"] = _acct_now' in start and "setdefault(\"_acct_id\"" not in start)
truthy("  before the worker thread starts",
       start.index('jb["_acct_id"] = _acct_now') < start.index("threading.Thread("))

IJ = src("domain/image_jobs.py")
truthy("image worker files by the stamped account first",
       'job.get("_acct_id", "")' in IJ)

AF = src("domain/autofix_jobs.py")
truthy("auto-fix job carries account_id", re.search(r'"account_id":\s*account_id', AF) is not None)
truthy("  and stops when the open account is not the job's",
       '(_app._state.get("active_account_id") or "") != (acct or "")' in AF)
AFR = src("routes/autofix_job_routes.py")
truthy("  the route names the account when it creates the job", "_af_new(" in AFR)

PJ = src("routes/preview_job_routes.py")
truthy("preview queue: account_id= on enqueue", "account_id=str((_acc or {}).get(\"id\"" in PJ)
truthy("  after the same write check /run makes", "mismatch_for_write(request, _state" in PJ)

LR = src("routes/listing_routes.py")
truthy("/run: refuses with no account open", "No account is open. Open the account" in LR)
truthy("  and the stream uses the captured account, not _state",
       "_run_acct = _scope_acct_id" in LR)

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\nevery job names its account at start")
