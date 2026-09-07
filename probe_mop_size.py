"""probe_mop_size.py -- is `size` really in Amazon's MOP schema?

    Amazon refused the listing: "'Size' is required but missing", code 90220.
    The app parsed the field name correctly and then said "this listing has no
    such field yet", because nothing named `size` was in the schema it holds --
    so there was no box to type the answer into.

CLAUDE.md Rule 4: do not reason about what the schema OUGHT to contain. Ask
Amazon and read the reply. This prints the raw property names for the product
type, says whether `size` is among them, whether Amazon marks it required, and
what shape it wants -- which is what decides how a box for it must be drawn.

A PROBE: live SP-API, excluded from the suite by name, reads only.

Run:  python probe_mop_size.py [PRODUCT_TYPE] [MARKETPLACE]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from config import settings as _cs                    # noqa: E402
from domain import accounts as _acc                   # noqa: E402

CONFIG_PATH = os.path.join(HERE, "config.json")
PT = (sys.argv[1] if len(sys.argv) > 1 else "MOP").upper()
MKT = (sys.argv[2] if len(sys.argv) > 2 else "UK").upper()
WS = "nestwell_goods"

cfg = _cs.read_raw(CONFIG_PATH)
acc = next((a for a in (cfg.get("accounts") or []) if a.get("id") == WS), None)
if not acc:
    print("no account %r" % WS)
    raise SystemExit(1)

creds = _acc.account_creds(acc)
mkt_id = _acc.marketplace_id(MKT)
print("account %s | product type %s | %s (%s)" % (WS, PT, MKT, mkt_id))

from sp_api.api import ProductTypeDefinitions                # noqa: E402
from sp_api.base import Marketplaces                         # noqa: E402

enum = getattr(Marketplaces, MKT, None) or Marketplaces.UK
api = ProductTypeDefinitions(credentials=creds, marketplace=enum)

try:
    got = api.get_definitions_product_type(
        productType=PT, marketplaceIds=[mkt_id],
        requirements="LISTING", locale="en_GB")
except Exception as e:
    print("REFUSED: %s" % str(e)[:300])
    raise SystemExit(1)

pay = got.payload or {}
link = ((pay.get("schema") or {}).get("link") or {}).get("resource")
print("schema url: %s" % (link or "(none)")[:120])
if not link:
    print(json.dumps(pay)[:600])
    raise SystemExit(1)

import urllib.request                                        # noqa: E402
with urllib.request.urlopen(link) as fh:
    schema = json.loads(fh.read().decode("utf-8"))

props = (schema.get("properties") or {})
req = schema.get("required") or []
print("\nproperties: %d   required: %d" % (len(props), len(req)))
print("required list: %s" % json.dumps(req))

print("\nANY PROPERTY WITH 'size' IN ITS NAME:")
hits = sorted(k for k in props if "size" in k.lower())
for k in hits:
    p = props[k] or {}
    print("   %-28s title=%r  required=%s"
          % (k, str(p.get("title") or "")[:44], k in req))
if not hits:
    print("   none")

if "size" in props:
    print("\nTHE RAW `size` DEFINITION, verbatim:")
    print(json.dumps(props["size"], indent=2)[:2400])
else:
    print("\n`size` is NOT a top-level property of this schema.")
    print("Properties whose TITLE mentions size:")
    for k, p in sorted(props.items()):
        t = str((p or {}).get("title") or "")
        if "size" in t.lower():
            print("   %-28s %r  required=%s" % (k, t[:50], k in req))
