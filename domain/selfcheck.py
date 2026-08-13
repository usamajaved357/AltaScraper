"""domain/selfcheck.py -- the app's own black box.

WHY THIS EXISTS
When something breaks on the server the browser shows a message that is usually
about the SYMPTOM, not the cause -- "Unexpected token '<'" when the real problem
was an expired session, or an empty page when the real problem was a wiped disk.
Working out which is which meant opening Railway, reading logs, guessing, and
redeploying to test the guess. That is slow, and every redeploy on an ephemeral
filesystem destroys more state.

So the app records its own faults. Every server error is kept here with the URL,
the time, who was signed in, and the tail of the traceback. Then ONE page shows
the deployment's configuration and its recent errors together, and one button
copies the whole thing as text.

Nothing here is written to disk. It is a short in-memory list that is emptied on
restart -- deliberately, because it holds request paths and error text and has no
business outliving the process that produced it.

SECRETS
Error messages sometimes quote the thing that failed, and that thing is sometimes
a credential. Everything stored here goes through redact() first, so the text is
safe to paste into a chat or an issue.
"""
import os
import re
import threading
import time
import traceback

MAX_ERRORS = 50          # a rolling window; older entries fall off the end
TRACE_LINES = 12         # tail of the traceback -- enough to name the real line

_lock = threading.Lock()
_errors = []             # newest last
_counts = {}             # "METHOD /path" -> how many times, since boot
_booted = time.time()


# --- secret scrubbing -------------------------------------------------------
# Long opaque strings are the shape every credential shares: SP-API refresh
# tokens (Atzr|...), AWS keys (AKIA...), Anthropic keys (sk-ant-...), Google
# private keys. Matching the SHAPE rather than a list of known names means a
# credential we have not thought of is still caught.
_SECRET_PATTERNS = [
    (re.compile(r"(?i)\bAtzr\|[A-Za-z0-9_\-\.]+"), "Atzr|<redacted>"),
    (re.compile(r"(?i)\bsk-ant-[A-Za-z0-9_\-]+"), "sk-ant-<redacted>"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AKIA<redacted>"),
    (re.compile(r"(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                re.S), "<private key redacted>"),
    # key=value and "key": "value" for anything NAMED like a secret. The quotes
    # are part of the separator, not the key -- a JSON key is `"password":`, so
    # requiring the colon to follow the word directly never matched JSON at all.
    (re.compile(r"(?i)\b(secret|password|passwd|token|api[_-]?key|refresh[_-]?token|"
                r"access[_-]?key|client[_-]?secret|private[_-]?key)\b"
                r"([\"']?\s*[:=]\s*[\"']?)([^\s\"',}]{3,})"),
     r"\1\2<redacted>"),
]


def redact(text):
    """Remove anything credential-shaped. Always applied before storing."""
    s = str(text or "")
    for pat, repl in _SECRET_PATTERNS:
        try:
            s = pat.sub(repl, s)
        except Exception:
            pass
    return s


# --- recording --------------------------------------------------------------
def record(path, method, status, exc, user="", trace=None):
    """Remember one server fault. Never raises -- a failure to record an error
    must not become a second error."""
    try:
        tb = trace if trace is not None else traceback.format_exc()
        tail = [ln.rstrip() for ln in str(tb).strip().splitlines()][-TRACE_LINES:]
        entry = {
            "at": time.time(),
            "path": redact(path or ""),
            "method": str(method or ""),
            "status": int(status or 500),
            "kind": type(exc).__name__ if exc is not None else "Error",
            "message": redact(str(exc or ""))[:400],
            "user": str(user or "")[:120],
            "trace": [redact(x)[:300] for x in tail],
        }
        key = "%s %s" % (entry["method"], entry["path"])
        with _lock:
            _errors.append(entry)
            del _errors[:-MAX_ERRORS]
            _counts[key] = _counts.get(key, 0) + 1
    except Exception:
        pass


def recent(limit=25):
    """Newest first, so the thing that just broke is at the top."""
    with _lock:
        rows = list(_errors[-int(limit or 25):])
        counts = dict(_counts)
    rows.reverse()
    return {"errors": rows, "total": len(_errors), "repeats": counts,
            "since": _booted, "uptime": time.time() - _booted}


def clear():
    with _lock:
        del _errors[:]
        _counts.clear()


# --- one pasteable block ----------------------------------------------------
def as_text(diag):
    """Everything worth knowing as plain text, ready to paste.

    `diag` is the dict from domain.deploy_check.check(). Kept here rather than in
    deploy_check because deploy_check answers "is the configuration right?" and
    this answers "what should I send someone?" -- different jobs.
    """
    out = ["ALTASCRAPER DIAGNOSTICS",
           "generated %s" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
           "uptime %s" % _dur(time.time() - _booted),
           ""]

    out.append("CONFIGURATION")
    for c in (diag or {}).get("checks", []):
        out.append("  [%s] %-28s %s" % ("ok" if c.get("ok") else "!!",
                                        c.get("name", ""), c.get("detail", "")))
        if not c.get("ok") and c.get("why"):
            out.append("       -> %s" % c["why"])

    ref = (diag or {}).get("refresher") or {}
    if ref:
        out += ["", "BACKGROUND SYNC"]
        for line in _refresher_lines(ref):
            out.append("  " + line)

    r = recent(15)
    out += ["", "RECENT SERVER ERRORS (%d in the last %s)"
            % (r["total"], _dur(r["uptime"]))]
    if not r["errors"]:
        out.append("  none")
    for e in r["errors"]:
        out.append("  %s  %s %s  ->  %s: %s"
                   % (time.strftime("%H:%M:%S", time.localtime(e["at"])),
                      e["method"], e["path"], e["kind"], e["message"]))
        for ln in e["trace"][-4:]:
            out.append("        " + ln)
    return "\n".join(out)


def _refresher_lines(ref):
    lines = []
    accts = ref.get("accounts") or ref.get("workers") or {}
    if isinstance(accts, dict):
        for name, st in accts.items():
            if isinstance(st, dict):
                age = st.get("age")
                lines.append("%-20s last refreshed %s"
                             % (name, _dur(age) + " ago" if age else "never"))
            else:
                lines.append("%-20s %s" % (name, st))
    elif accts:
        lines.append(str(accts)[:200])
    if not lines:
        lines.append(str(ref)[:300])
    return lines


def _dur(seconds):
    if not seconds:
        return "0s"
    s = int(seconds)
    if s < 90:
        return "%ds" % s
    if s < 5400:
        return "%dm" % (s // 60)
    if s < 172800:
        return "%dh" % (s // 3600)
    return "%dd" % (s // 86400)


# --- startup banner ---------------------------------------------------------
def boot_banner(diag):
    """What to print into the server log the moment the app starts.

    A misconfigured deployment currently announces itself hours later, as missing
    data. This makes it announce itself at boot, in the one place a server always
    has: its log. Silent when everything is correct, so it stays worth reading.
    """
    bad = [c for c in (diag or {}).get("checks", []) if not c.get("ok")]
    if not bad:
        return ("  deployment check: all clear (state in %s)"
                % (diag or {}).get("data_dir", "?"))
    line = "=" * 72
    out = [line, "  DEPLOYMENT PROBLEMS -- %d found. The app will start anyway."
           % len(bad), line]
    for c in bad:
        out.append("  * %s: %s" % (c.get("name", ""), c.get("detail", "")))
        if c.get("why"):
            out.append("      %s" % c["why"])
    out += ["", "  Open /diag in the app for the full picture.", line]
    return "\n".join(out)
