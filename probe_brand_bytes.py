# Is the APP sending a typo'd brand name?
#
#     "is the app giving a typo to amazon which cause the brand name to be
#      refused?"
#
# A fair question, because the spacing test showed Amazon's answer changes
# completely on a one-character difference:
#
#     AltaboltaVoo   -> 100550  (Amazon knows this name)
#     Altabolta Voo  -> 5665    (Amazon has never seen this name)
#
# So this prints the EXACT bytes of the brand in three places -- what he saved
# in settings, what the row says, and what is inside the payload the app would
# actually send -- with repr() and a codepoint dump, so a trailing space, a
# non-breaking space, a curly character or a case difference cannot hide.
#
# Entirely local. No API calls.
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCOUNT = "nestwell_goods"
WANT = "AltaboltaVoo"

from data.store import ListingStore

cfg = json.load(open("config.json", encoding="utf-8"))
acct = [x for x in cfg["accounts"] if x.get("id") == ACCOUNT][0]


def dump(label, s):
    if s is None:
        print("   %-34s (absent)" % label)
        return
    s = str(s)
    same = "SAME as %r" % WANT if s == WANT else "*** DIFFERENT ***"
    print("   %-34s %-24r %s" % (label, s, same))
    if s != WANT:
        pts = " ".join("%s(%d)" % (repr(c)[1:-1], ord(c)) for c in s)
        print("        codepoints: %s" % pts)


print("=== what he saved in settings ===")
for k in ("brands", "brand_names", "brand"):
    if k in acct:
        v = acct[k]
        if isinstance(v, (list, tuple)):
            for i, b in enumerate(v):
                dump("account[%s][%d]" % (k, i), b)
        else:
            dump("account[%s]" % k, v)

print("\n=== what each draft holds ===")
rows = ListingStore(ACCOUNT, config_path="config.json").get_all_rows()
seen = {}
for r in rows:
    sku = str(r.get("SKU") or "").strip()
    col = r.get("Brand")
    pay = None
    raw = str(r.get("API Payload JSON") or "").strip()
    if raw:
        try:
            at = (json.loads(raw).get("attributes") or {})
            bl = at.get("brand") or []
            if bl:
                pay = (bl[0] or {}).get("value")
        except Exception as e:
            pay = "<unreadable: %s>" % e
    if col is None and pay is None:
        continue
    key = (str(col), str(pay))
    seen.setdefault(key, []).append(sku)

for (col, pay), skus in sorted(seen.items()):
    print("\n   %d listing(s), e.g. %s" % (len(skus), skus[0]))
    dump("Brand column", col)
    dump("brand inside the payload", pay)
