"""domain/workspace_state.py -- give each signed-in person their own workspace.

THE PROBLEM THIS SOLVES
The chosen workspace -- which Amazon account, and therefore which Google Sheet
is read and written -- lived in ONE dictionary in the server process. It was
written by /accounts/select and read by _ws(), _active_account() and about forty
other places.

With one user that is correct and simple. With two it is dangerous: when a VA
opened Green Haven, the owner's workspace silently became Green Haven too, and
the owner's next Approve, Delete, Submit or Optimize went to the VA's sheet.
Nothing warned either of them and the app looked completely normal.

WHY IT IS DONE HERE RATHER THAN AT THE FORTY CALL SITES
Every one of those call sites already asks the same object the same question.
Changing the ANSWER is one edit; changing the QUESTION would be forty, and forty
edits is forty chances to miss one -- the one that then writes to the wrong
Amazon account. So this is a drop-in replacement for the dict: the call sites are
untouched and keep working exactly as written.

WHO GETS THEIR OWN, AND WHO DOES NOT
Only the keys that describe a workspace are scoped. cfg, gc, schemas and vv are
shared caches -- expensive to build, identical for everyone, and correct to share.
Scoping those would multiply the memory and the API calls for no benefit.

Requests with no signed-in session -- the background refresher, anything running
in a worker thread -- fall back to the process-wide value, which is also what is
persisted to app_state.json and restored on boot. Those have no user to belong
to, and a background refresh must still know which accounts exist.
"""
try:
    from flask import has_request_context, session
except Exception:                                    # importable without Flask
    def has_request_context():
        return False
    session = None

SESSION_KEY = "ws"          # where a person's own workspace lives in their cookie


def _mine():
    """This user's workspace store, or None when there is nobody to attribute it
    to (a background thread, or a request from someone not signed in)."""
    if not has_request_context() or session is None:
        return None
    try:
        if not session.get("uid"):
            # Not a real account -- the shared-password owner, or signed out.
            # There is exactly one of them, so the process-wide value is right.
            return None
        return session.setdefault(SESSION_KEY, {})
    except Exception:
        return None


class WorkspaceState(dict):
    """A dict whose workspace keys are per-user and whose caches are shared.

    Subclasses dict rather than wrapping one so that anything treating it as a
    plain dictionary -- json.dumps, **kwargs, a stray dict() call -- still works.
    """

    def __init__(self, initial=None, scoped=()):
        super().__init__(initial or {})
        # A frozenset, not a tuple: this is consulted on every get and set.
        self._scoped = frozenset(scoped)

    # -- reading ----------------------------------------------------------
    def _read(self, key, default=None, found=None):
        if key in self._scoped:
            mine = _mine()
            if mine is not None and key in mine:
                return mine[key]
        if found is not None:
            found[0] = dict.__contains__(self, key)
        return dict.get(self, key, default)

    def get(self, key, default=None):
        return self._read(key, default)

    def __getitem__(self, key):
        if key in self._scoped:
            mine = _mine()
            if mine is not None and key in mine:
                return mine[key]
        return dict.__getitem__(self, key)

    def __contains__(self, key):
        if key in self._scoped:
            mine = _mine()
            if mine is not None and key in mine:
                return True
        return dict.__contains__(self, key)

    # -- writing ----------------------------------------------------------
    def __setitem__(self, key, value):
        if key in self._scoped:
            mine = _mine()
            if mine is not None:
                mine[key] = value
                # Flask only re-signs the cookie when it is told the session
                # changed, and mutating a nested dict does not tell it.
                try:
                    session.modified = True
                except Exception:
                    pass
                return
        dict.__setitem__(self, key, value)

    def setdefault(self, key, default=None):
        if key in self._scoped:
            mine = _mine()
            if mine is not None:
                if key not in mine:
                    self[key] = default
                return mine[key]
        return dict.setdefault(self, key, default)

    def pop(self, key, *a):
        if key in self._scoped:
            mine = _mine()
            if mine is not None and key in mine:
                v = mine.pop(key)
                try:
                    session.modified = True
                except Exception:
                    pass
                return v
        return dict.pop(self, key, *a)

    def update(self, other=(), **kw):
        for k, v in (dict(other, **kw)).items():
            self[k] = v

    # -- the shared, process-wide view ------------------------------------
    def shared(self, key, default=None):
        """The process-wide value, ignoring who is asking.

        app_state.json is the DEFAULT for people who have not chosen a workspace
        yet, and the only thing background work can use. Persisting one user's
        choice as everyone's default is the bug, so saving reads through this.
        """
        return dict.get(self, key, default)

    def set_shared(self, key, value):
        dict.__setitem__(self, key, value)

    def is_personal(self):
        """True when the caller has a workspace of their own in play."""
        return _mine() is not None


def make(initial=None, scoped=()):
    return WorkspaceState(initial, scoped)
