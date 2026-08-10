"""routes/stream_pump.py — keep a slow browser from freezing a running job.

THE PROBLEM THIS SOLVES (in plain English)
-------------------------------------------
The dashboard runs the listing generator as a separate program and shows its
progress live in the browser. The obvious way to do that is:

    for line in iter(proc.stdout.readline, ""):
        yield f"data: {line}\n\n"          # <-- send it to the browser

That looks harmless. It is not. On Flask's built-in server the `yield` does not
return until the browser has actually ACCEPTED the text. So if the browser gets
slow -- and it does, once the on-screen log holds thousands of lines -- the
`yield` waits. While it waits, `readline()` is not being called. The generator's
output has nowhere to go, the small buffer between the two programs fills up,
and the generator freezes part-way through printing a line.

That freeze is total and permanent: the generator's own "give up after 40s"
timers live inside the frozen program, so they never fire either. It looks
exactly like a hung scraper. It isn't -- it is a jammed letterbox.

THE FIX
-------
A dedicated thread empties the generator's output as fast as it is produced,
into a fixed-size buffer. The generator can therefore ALWAYS print, whatever the
browser is doing. If the browser falls behind, the OLDEST display lines are
dropped and the viewer is told how many.

Losing log lines is always better than freezing a run that is midway through
writing to Google Sheets.
"""
import subprocess
import threading
import time
from collections import deque

# Lines held for a browser that has fallen behind. ~4000 lines is several
# minutes of generator output -- far more than any real lag -- while still being
# a hard ceiling on memory.
DEFAULT_MAXLEN = 4000


def spawn(args, **kwargs):
    """Start a child whose output we intend to stream. THE one place that decides
    how a child's text is decoded (CLAUDE.md §12).

    encoding="utf-8", errors="replace" is not optional and must never be dropped.
    With a bare text=True, Windows decodes the child using the ANSI code page
    (cp1252 here). The generator and crawl4ai both emit UTF-8: crawl4ai's
    "[COMPLETE] ●" is E2 97 8F, and 0x8F simply does not exist in cp1252. The
    read then raises UnicodeDecodeError, the reader dies, nobody drains the pipe,
    the pipe fills, and the generator blocks mid-print -- frozen at 0% CPU with
    no error anywhere. That is what stalled a run at item 31/87 and again at
    50/87. errors="replace" turns a fatal decode into one harmless '?'.
    """
    kwargs.setdefault("stdout", subprocess.PIPE)
    kwargs.setdefault("stderr", subprocess.STDOUT)
    kwargs.setdefault("text", True)
    kwargs.setdefault("encoding", "utf-8")
    kwargs.setdefault("errors", "replace")
    kwargs.setdefault("bufsize", 1)
    return subprocess.Popen(args, **kwargs)


def pump_lines(proc, *, maxlen=DEFAULT_MAXLEN, poll=0.05):
    """Yield `proc`'s stdout lines WITHOUT ever letting a slow reader block it.

    Yields raw lines exactly as `iter(proc.stdout.readline, "")` would, so
    callers keep their existing formatting (ANSI stripping, rstrip, SSE framing)
    unchanged. Ends when the child closes stdout and the buffer is drained.

    If lines had to be dropped, a plain-text notice line is yielded inline so the
    viewer knows the log is incomplete -- and knows the RUN was never paused.
    """
    buf     = deque(maxlen=maxlen)
    eof     = threading.Event()
    dropped = [0]
    errors  = []

    def _drain():
        # NEVER stop draining because of a bad line. Giving up here strands the
        # child: it keeps printing into a pipe nobody empties, fills it, and
        # freezes mid-write at 0% CPU with no error shown anywhere. A read error
        # is reported and skipped -- draining continues until real end-of-output.
        consecutive = 0
        try:
            while True:
                try:
                    line = proc.stdout.readline()
                    consecutive = 0
                except Exception as e:
                    consecutive += 1
                    if len(errors) < 5:
                        errors.append(f"{type(e).__name__}: {str(e)[:120]}")
                    # A genuinely dead pipe fails forever -- don't spin on it.
                    if consecutive >= 50:
                        break
                    continue
                if line == "":
                    break                       # real end-of-output
                if len(buf) == buf.maxlen:
                    dropped[0] += 1             # the append below evicts the oldest
                buf.append(line)
        finally:
            eof.set()

    threading.Thread(target=_drain, daemon=True, name="run-drain").start()

    reported = 0
    seen_err = 0
    while True:
        try:
            line = buf.popleft()
        except IndexError:
            if eof.is_set():
                # Surface any read errors instead of ending the log as if the run
                # had simply finished -- a silent ending is what hid the freeze.
                for msg in errors[seen_err:]:
                    yield f"[log] could not read a line from the run: {msg}\n"
                return              # child finished AND we've drained everything
            time.sleep(poll)
            continue
        if len(errors) > seen_err:
            for msg in errors[seen_err:]:
                yield f"[log] could not read a line from the run: {msg}\n"
            seen_err = len(errors)
        if dropped[0] > reported:
            skipped  = dropped[0] - reported
            reported = dropped[0]
            yield (f"[log] skipped {skipped} line(s) -- this browser was behind; "
                   f"the run itself was never paused\n")
        yield line
