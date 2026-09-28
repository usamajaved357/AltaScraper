"""The files a feature is made of, read as one text (test support only).

Milestone 4 splits the big files by feature, moving code word for word. Around
280 tests read those files as text by their old path to check what the code
says. This module is the one place that knows which files make up each feature
(tests_support/features.json) and returns them joined, so those tests keep
checking the same code wherever it now lives.

    feature_text("static/js/listings.js")  -> the original plus its parts

sitecustomize.py (beside this file) routes plain text reads of an original
through here when the test runner starts a test. Nothing in the app imports
this module.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ALTA_FEATURES_JSON lets test_feature_sources.py try the hook on a practice
# manifest without touching the real one.
_MANIFEST = os.environ.get("ALTA_FEATURES_JSON") or os.path.join(ROOT, "tests_support", "features.json")


def _load():
    with open(_MANIFEST, "rb") as fh:            # binary: never through the hook
        raw = json.loads(fh.read().decode("utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


FEATURES = _load()


def _key(path):
    """The manifest key for a path, or None. Case-insensitive (Windows)."""
    try:
        full = os.path.normcase(os.path.abspath(os.fspath(path)))
    except TypeError:
        return None
    for k in FEATURES:
        if os.path.normcase(os.path.join(ROOT, *k.split("/"))) == full:
            return k
    return None


def is_split(path):
    """True when the path is an original that now has parts beside it."""
    k = _key(path)
    return bool(k) and len(FEATURES[k]) > 1


def feature_text(path, encoding="utf-8"):
    """Every file of the feature, joined in order, each ending in a newline."""
    k = _key(path)
    parts = FEATURES[k] if k else [os.fspath(path)]
    out = []
    for rel in parts:
        with open(os.path.join(ROOT, *rel.split("/")), "rb") as fh:
            t = fh.read().decode(encoding)
        out.append(t if t.endswith("\n") else t + "\n")
    return "".join(out)
