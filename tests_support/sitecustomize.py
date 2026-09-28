"""Test runs only: a text read of a split file returns the whole feature.

run_tests.py puts this folder first on PYTHONPATH, so Python imports this file
at start-up in every test process (and in any Python process a test starts).
It changes ONE thing: open(path) / io.open(path) for READING TEXT, where path is
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


def _feature_open(file, mode="r", *args, **kwargs):
    if (_features is not None and isinstance(file, (str, bytes, os.PathLike))
            and "b" not in mode and not any(c in mode for c in "wax+")):
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
