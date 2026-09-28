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
import re

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


def _read(rel, encoding):
    with open(os.path.join(ROOT, *rel.split("/")), "rb") as fh:
        return fh.read().decode(encoding)


# WHERE A MOVED BLOCK USED TO BE. The original keeps a one-line pointer (JS)
# or an include (templates) at the exact spot each block left, so the feature
# can be put back together IN THE ORIGINAL ORDER -- a test that slices "from
# X to Y" keeps finding the same text between them.
_POINTER = re.compile(r'^[ \t]*// .*: moved to (static/js/[\w./-]+) \(Milestone 4\)[^\r\n]*$', re.M)
_INCLUDE = re.compile(r'^\{% include "([\w./-]+\.html)" %\}$', re.M)


def _body(rel, encoding):
    """A part without the header line(s) the move added (up to the first blank line)."""
    t = _read(rel, encoding).replace("\r\n", "\n")
    if rel.endswith(".js") and t.startswith("//"):
        t = t.split("\n\n", 1)[1] if "\n\n" in t else t
    return t


def feature_text(path, encoding="utf-8"):
    """The feature as one text, in the ORIGINAL file's order where that is known.

    A part named by exactly one pointer (JS) or include (template) in the
    original is put back at that spot; every other part (CSS pieces, which were
    cut in order anyway; a file several pointers share) follows in manifest
    order. Each file ends in a newline.
    """
    k = _key(path)
    parts = FEATURES[k] if k else [os.fspath(path)]
    main = k or parts[0]
    orig = _read(main, encoding)
    nl = "\r\n" if "\r\n" in orig else "\n"
    o = orig.replace("\r\n", "\n")
    placed = set()
    ptr = {}
    for m in _POINTER.finditer(o):
        ptr.setdefault(m.group(1), []).append(m)
    for rel, ms in ptr.items():
        if len(ms) == 1 and rel in parts:
            o = o.replace(ms[0].group(0), _body(rel, encoding).rstrip("\n"), 1)
            placed.add(rel)
    if main.endswith(".html"):
        def _inc(m):
            rel = "templates/" + m.group(1)
            if rel in parts:
                placed.add(rel)
                return _read(rel, encoding).replace("\r\n", "\n").rstrip("\n")
            return m.group(0)
        o = _INCLUDE.sub(_inc, o)
    out = []
    for rel in parts:
        if rel == main:
            t = o.replace("\n", nl)
        elif rel in placed:
            continue
        else:
            t = _read(rel, encoding)
        out.append(t if t.endswith("\n") else t + "\n")
    return "".join(out)
