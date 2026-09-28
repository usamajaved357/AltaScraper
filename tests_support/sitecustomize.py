"""Test runs only: a text read of a split file returns the whole feature.

run_tests.py puts this folder first on PYTHONPATH, so Python imports this file
at start-up in every test process (and in any Python process a test starts).
It changes ONE thing: open(path) / io.open(path) for READING TEXT, called from a
test file (test_*.py), where path is
an original listed in features.json that now has parts, returns the joined text
of the feature instead of the file alone. Every other open -- any other file,
any write, any binary read -- goes straight through untouched.

Why: see features.py. The app never runs with this; only run_tests.py sets
PYTHONPATH to include this folder.
"""
import builtins
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import features as _features
except Exception:                      # a broken manifest must not break Python
    _features = None

_real_open = builtins.open


def _called_from_a_test():
    """Only a TEST's own read is answered with the feature. The app and every
    library read files the normal way even inside a test process -- Jinja
    loading the page template, a route reading it to list the screens -- or
    the page would render with every screen twice. The reader is the first
    frame outside this file and the standard library's file plumbing
    (pathlib, io, codecs); it must be a test_*.py file."""
    f = sys._getframe(2)
    while f is not None:
        name = os.path.basename(f.f_code.co_filename)
        if name not in ("pathlib.py", "io.py", "codecs.py", "_bootlocale.py"):
            return name.startswith("test_")
        f = f.f_back
    return False


def _feature_open(file, mode="r", *args, **kwargs):
    if (_features is not None and isinstance(file, (str, bytes, os.PathLike))
            and "b" not in mode and not any(c in mode for c in "wax+")
            and _called_from_a_test()):
        try:
            split = _features.is_split(file)
        except Exception:
            split = False
        if split:
            enc = kwargs.get("encoding") or (args[1] if len(args) > 1 else None) or "utf-8"
            return io.StringIO(_features.feature_text(file, enc))
    return _real_open(file, mode, *args, **kwargs)


builtins.open = _feature_open
io.open = _feature_open
