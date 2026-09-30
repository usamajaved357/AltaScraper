"""domain/returns_sync.py -- fetch Amazon's seller-fulfilled returns report,
and keep it, for the "Pull from Amazon" button AND the daily background job.

MOVED, NOT REWRITTEN. routes/returns_routes.py's _fetch and _split were moved
unchanged (30 Sep 2026) so the button and the scheduler use ONE path to Amazon
(CLAUDE.md Rule 12): the Amazon call to api/returns_report.fetch (Rule 7: only
api/ talks to Amazon), the splitting to split() here. The route calls fetch().

WHY A DAILY PULL. Before this the returns table only filled when somebody
pressed the button, so the Refunds view (domain/return_refunds.py) could only be
as current as the last press -- and the report is capped at 60 days, so a month
without a press loses returns for good. Read-only: one report per account and
marketplace, nothing changed on Amazon.
"""
import csv
import io

from api.returns_report import MAX_DAYS, EMPTY  # noqa: F401


def fetch(acc, mkt, days):
    """The seller-fulfilled returns report. -> (headers, rows, error).

    The Amazon call itself is api/returns_report.fetch (Rule 7)."""
    from api import returns_report as _api
    from domain import accounts as _acc_mod
    # Asked lazily, in the original order (sp_api import, client, request).
    text, _none, err = _api.fetch(lambda: _acc_mod.account_creds(acc), mkt,
                                  lambda: _acc_mod.marketplace_id(mkt), days)
    if err:
        return [], [], err
    return split(text)


def split(text):
    """A tab- or comma-separated report -> (headers, rows, error)."""
    lines = [l for l in str(text or "").splitlines() if l.strip()]
    if not lines:
        return [], [], EMPTY
    delim = "\t" if lines[0].count("\t") >= lines[0].count(",") else ","
    rdr = csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)
    rows = list(rdr)
    if not rows:
        return [], [], EMPTY
    return rows[0], rows[1:], ""


def pull_and_store(config_path, acc, workspace_id, marketplace, days=MAX_DAYS,
                   fetcher=None):
    """Fetch the report, parse it, keep every return. THE one fetch-parse-store
    path: the "Pull from Amazon" button and the daily job both call this.

    -> {ok, empty, returns, kind, skipped, headers, stored, added, error,
        store_error}. `fetcher` is fetch() unless a test hands in its own.
    Never raises. A failure to STORE is never fatal (the button's figures are
    already right): it is reported in store_error, and ok stays True."""
    from domain import returns_store as _rstore
    from domain import returns_view as _rv
    try:
        headers, rows, err = (fetcher or fetch)(acc, marketplace, days)
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
    if err == EMPTY:
        return {"ok": True, "empty": True, "returns": [], "kind": "mfn",
                "skipped": 0, "stored": 0, "added": 0, "note": "no returns in the window"}
    if err:
        return {"ok": False, "error": err}
    returns, kind, skipped = _rv.parse_rows(headers, rows)
    if not kind:
        return {"ok": False, "unrecognised": True, "headers": headers,
                "error": ("That report's columns were not recognised. Found: %s"
                          % ", ".join(str(h) for h in headers[:12]))}
    out = {"ok": True, "empty": False, "returns": returns, "kind": kind,
           "skipped": skipped, "headers": headers, "stored": 0, "added": 0}
    try:
        res = _rstore.store(config_path, workspace_id, marketplace, returns,
                            _rstore.SOURCE_REPORT)
        out["stored"], out["added"] = res.get("stored"), res.get("added")
    except Exception as e:
        out["store_error"] = str(e)[:300]
    return out


def _marketplaces(a):
    """The account's marketplaces; its default one when the list is empty."""
    mk = [str(m or "").strip().upper() for m in (a.get("marketplaces") or [])]
    mk = [m for m in mk if m and m != "__ALL__"]
    if not mk and str(a.get("default_marketplace") or "").strip():
        mk = [str(a["default_marketplace"]).strip().upper()]
    return mk


def sync_all(config_path, conf, workspace_id=None, fetcher=None):
    """The daily job: every account that can authenticate as ITSELF, every
    marketplace it sells on. A borrowed token answers for the lender, so an
    account that borrows is skipped (the same rule /returns/report applies).

    Every skip is listed with its reason. When there was something to pull and
    EVERY pull failed, this RAISES, so data/scheduler records the run as failed
    (its message carries each account's error) rather than as a success."""
    from domain import accounts as _acc
    done, skipped = [], []
    for a in (_acc.load_accounts(conf, config_path) or []):
        aid = str(a.get("id") or "")
        if not aid or (workspace_id and aid != workspace_id):
            continue
        if not _acc.has_own_creds(a) or not _acc.seller_scope_allowed(a):
            skipped.append({"workspace": aid, "why": "no Amazon login of its own"})
            continue
        mkts = _marketplaces(a)
        if not mkts:
            skipped.append({"workspace": aid, "why": "no marketplace set"})
            continue
        for mkt in mkts:
            res = pull_and_store(config_path, a, aid, mkt, fetcher=fetcher)
            done.append({"workspace": aid, "marketplace": mkt,
                         "ok": bool(res.get("ok")), "stored": res.get("stored"),
                         "error": (res.get("error") or res.get("store_error") or "")[:160]})
    failed = [d for d in done if not d["ok"]]
    if done and len(failed) == len(done):
        raise RuntimeError("every returns pull failed: " + "; ".join(
            "%s/%s: %s" % (d["workspace"], d["marketplace"], d["error"]) for d in failed)[:1500])
    return {"pulled": done[:40], "failed": len(failed), "skipped": skipped}
