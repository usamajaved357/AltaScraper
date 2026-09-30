# -*- coding: utf-8 -*-
"""The AI image helpers read "/media/..." from the app's REAL media folder (30 Sep 2026).

On Railway the media folder is beside config.json on the persistent disk
(/data/media, dashboard._media_root); domain/ai_providers fell back to the
working directory's media/ (/app/media) because DEFAULT_MEDIA_ROOT was never
set, so Refine on a saved/library image said "not found on disk".
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
TMP = tempfile.mkdtemp(prefix="aimedia_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "ra"}]}, open(CFG, "w"))
os.environ["CONFIG_PATH"] = CFG
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "t.db")
os.environ["ALTASCRAPER_BACKGROUND"] = "off"
fails = []


def check(label, ok):
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL"))


import dashboard as D                          # noqa: E402
D.build_app()
from domain import ai_providers as A           # noqa: E402

want = os.path.normpath(os.path.join(TMP, "media"))
check("DEFAULT_MEDIA_ROOT is the app's media folder beside config.json",
      os.path.normpath(A.DEFAULT_MEDIA_ROOT or "") == want)
# A real PNG under that folder is found through its served /media/ path.
os.makedirs(os.path.join(want, "SKU1"), exist_ok=True)
png = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00\x00\x00\x01\x00\x00\x00\x01"
       + b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89" + b"\x00" * 16)
open(os.path.join(want, "SKU1", "a.png"), "wb").write(png)
try:
    uri = A._read_local_image("/media/SKU1/a.png")
    check("a /media/ link resolves to that folder", uri.startswith("data:image/png;base64,"))
except Exception as e:
    check("a /media/ link resolves to that folder (%s)" % e, False)

print("\nFAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
