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
import threading
import time
from collections import deque

# Lines held for a browser that has fallen behind. ~4000 lines is several
# minutes of generator output -- far more than any real lag -- while still being
# a hard ceiling on memory.
DEFAULT_MAXLEN = 4000


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

    def _drain():
        try:
            for line in iter(proc.stdout.readline, ""):
                if len(buf) == buf.maxlen:
                    dropped[0] += 1     # the append below evicts the oldest line
                buf.append(line)
        except Exception:
            # Pipe closed/killed mid-read: nothing useful to do, and raising here
            # would only kill a daemon thread nobody is watching.
            pass
        finally:
            eof.set()

    threading.Thread(target=_drain, daemon=True, name="run-drain").start()

    reported = 0
    while True:
        try:
            line = buf.popleft()
        except IndexError:
            if eof.is_set():
                return              # child finished AND we've drained everything
            time.sleep(poll)
            continue
        if dropped[0] > reported:
            skipped  = dropped[0] - reported
            reported = dropped[0]
            yield (f"[log] skipped {skipped} line(s) -- this browser was behind; "
                   f"the run itself was never paused\n")
        yield line
