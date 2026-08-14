"""domain/run_slots.py -- who may run the generator right now.

WHAT WAS WRONG
One process-wide flag meant ONE Preview or Submit at a time for the whole app.
Two people could not work simultaneously; the second was told "a run is already
in progress" and had to wait, however unrelated their listing was. On an app with
several VAs that is not caution, it is a queue.

But the opposite -- no limit at all -- is worse. Two runs on the SAME SKU write
the same sheet row and submit the same listing twice. And SP-API rate limits are
per SELLING ACCOUNT, so twenty concurrent runs against one account get throttled
into failure and look like Amazon being broken.

THE RULE
  * The same SKU never runs twice at once. That is the correctness limit and it
    is absolute.
  * An account runs a few at once. That is the quota limit, and it is a number.
  * The box runs a few in total, because each run is a Python subprocess.

Different accounts do not block each other at all, which is the case that
mattered: two people in two workspaces are genuinely independent.

STALE SLOTS
A run whose subprocess has died, or that has been held longer than MAX_SECONDS,
is reclaimed. An abandoned browser stream never runs its release, and without
this the old lock wedged until someone restarted the app.
"""
import os
import threading
import time

MAX_SECONDS = 600            # a Preview/Submit should never legitimately exceed this


def _int_env(name, default, lo, hi):
    try:
        return max(lo, min(int(os.environ.get(name) or default), hi))
    except Exception:
        return default


def per_account_limit():
    """Concurrent runs allowed against ONE Amazon account. Small: SP-API quota is
    per selling account, and exceeding it turns into throttling, which reads as
    Amazon failing rather than as us asking too fast."""
    return _int_env("ALTA_RUNS_PER_ACCOUNT", 2, 1, 8)


def total_limit():
    """Concurrent runs across the whole app. Each one is a Python subprocess."""
    return _int_env("ALTA_RUNS_TOTAL", 6, 1, 24)


def _end(proc):
    """End a run and everything it started. Never raises.

    proc.terminate() alone was not enough. It signals the child only, so the
    browser the generator launches to scrape product pages carries on -- the
    work stays open, the machine stays busy, and Stop looks like it did nothing.
    And a Python child sitting inside a long HTTP call does not always act on
    SIGTERM promptly, so a plain terminate can be quietly ignored.

    So: the whole process GROUP where the platform has them (spawn puts each run
    in its own), the tree via taskkill on Windows, and SIGKILL as the answer to
    anything still alive five seconds later. Stop has to actually stop.
    """
    import os as _os
    import signal as _sig
    import subprocess as _sp
    try:
        if _os.name == "nt":
            _sp.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
            return
        try:
            _os.killpg(_os.getpgid(proc.pid), _sig.SIGTERM)
        except Exception:
            proc.terminate()
        try:
            proc.wait(timeout=5)
            return
        except Exception:
            pass
        try:
            _os.killpg(_os.getpgid(proc.pid), _sig.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


class RunSlots(object):
    def __init__(self):
        self._lock = threading.Lock()
        self._slots = {}      # key -> {account, sku, owner, started, proc}
        # Which slot THIS thread holds. Every run -- the browser stream, the
        # preview worker, the Miles worker -- happens on its own thread, and
        # fifteen places release the lock by setting a flag rather than by
        # naming a key. Remembering the key per thread lets all of them keep
        # working unchanged and still release the right slot under concurrency.
        self._mine = threading.local()

    # -- internals --------------------------------------------------------
    @staticmethod
    def key(account_id, sku):
        # A run with no SKU (a whole-sheet generate) is keyed on the account
        # alone, so two of THOSE still exclude each other -- they would write
        # the same rows.
        return "%s::%s" % (str(account_id or ""), str(sku or "*"))

    def _reap(self):
        """Drop slots whose work is demonstrably over. Caller holds the lock."""
        now = time.time()
        for k, s in list(self._slots.items()):
            proc = s.get("proc")
            dead = (proc is not None) and (proc.poll() is not None)
            too_old = (now - (s.get("started") or 0)) > MAX_SECONDS
            if dead or too_old:
                self._slots.pop(k, None)

    # -- the decision -----------------------------------------------------
    def acquire(self, account_id="", sku="", owner=""):
        """(True, key) if this run may start, or (False, reason) explaining which
        limit stopped it -- the reason is shown to the user, so it names the
        actual obstacle rather than 'busy'."""
        k = self.key(account_id, sku)
        with self._lock:
            self._reap()
            if k in self._slots:
                who = self._slots[k].get("owner")
                return False, ("This listing is already being processed%s. "
                               "Wait for that run to finish."
                               % (" by someone else" if who and who != owner else ""))
            if len(self._slots) >= total_limit():
                return False, ("The app is already running %d listings at once. "
                               "Yours will start as soon as one finishes."
                               % total_limit())
            same_account = sum(1 for s in self._slots.values()
                               if s.get("account") == str(account_id or ""))
            if same_account >= per_account_limit():
                return False, ("This Amazon account is already running %d listings "
                               "at once. More at the same time would be throttled "
                               "by Amazon, so yours waits its turn."
                               % per_account_limit())
            self._slots[k] = {"account": str(account_id or ""), "sku": str(sku or ""),
                              "owner": str(owner or ""), "started": time.time(),
                              "proc": None}
            self._mine.key = k
            return True, k

    def attach(self, key, proc):
        """Record the subprocess, so a dead one frees its slot immediately."""
        with self._lock:
            s = self._slots.get(key or getattr(self._mine, "key", None))
            if s is not None:
                s["proc"] = proc

    def release(self, key):
        with self._lock:
            self._slots.pop(key, None)
        if getattr(self._mine, "key", None) == key:
            self._mine.key = None

    def release_current(self):
        """Release whatever slot this thread took, if any.

        The old code released by setting a shared flag to False. That worked when
        there was one run; with several it would have to know WHICH run was
        ending, and the fifteen places that do it cannot. The thread knows.
        """
        k = getattr(self._mine, "key", None)
        if k:
            self.release(k)
            return True
        return False

    # -- inspection and stopping -----------------------------------------
    def active(self):
        with self._lock:
            self._reap()
            return [{"key": k, "account": s.get("account"), "sku": s.get("sku"),
                     "owner": s.get("owner"),
                     "seconds": int(time.time() - (s.get("started") or 0))}
                    for k, s in self._slots.items()]

    def stop(self, owner=None, key=None, account=None):
        """Terminate runs. With an owner, only THAT person's -- pressing Stop on
        your own screen must not end a colleague's submit. With an ACCOUNT, only
        that workspace's.

        WHY ACCOUNT MATTERS EVEN WITH ONE USER. Owner alone was the only filter,
        and for the shared-password owner -- who IS the only user on most of
        these installs -- owner is empty, so Stop meant every run on the server.
        Pressing Stop while looking at Jack Reacherd killed a Nestwell Goods
        submit that was halfway through, from a button nowhere near it. Accounts
        are independent businesses; a control in one must not reach into
        another.

        With none of the three, all of them -- which is still what an explicit
        "stop everything" wants.
        """
        stopped = 0
        with self._lock:
            self._reap()
            for k, s in list(self._slots.items()):
                if key is not None and k != key:
                    continue
                if owner is not None and str(s.get("owner") or "") != str(owner):
                    continue
                # A slot with NO account belongs to nobody, so anyone may stop
                # it. Requiring an exact match made such a slot unstoppable:
                # Stop filtered it out, matched nothing, reported success and
                # left the run going -- which is worse than the cross-account
                # reach it was added to prevent, because the run carries on
                # spending. Only a slot that names a DIFFERENT account is left
                # alone.
                s_acct = str(s.get("account") or "")
                if account is not None and s_acct and s_acct != str(account):
                    continue
                proc = s.get("proc")
                if proc is not None:
                    _end(proc)
                self._slots.pop(k, None)
                stopped += 1
        return stopped

    def busy(self):
        with self._lock:
            self._reap()
            return len(self._slots) > 0


SLOTS = RunSlots()
