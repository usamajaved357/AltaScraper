# -*- coding: utf-8 -*-
"""The one order-items read (api/amazon_orders.order_items_raw, 29 Sep 2026).

Four places read getOrderItems by hand and only one followed NextToken, so an
order longer than a page was read in part. Pins: every page is read; a client
the caller holds is reused (no extra client); no code outside api/ calls
getOrderItems itself. Amazon is never contacted: the client is a fake.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


from api import amazon_orders as AO            # noqa: E402


class R:
    def __init__(self, payload):
        self.payload = payload


class FakeOC:
    def __init__(self):
        self.calls = []

    def get_order_items(self, oid, NextToken=None):
        self.calls.append(NextToken)
        if NextToken is None:
            return R({"OrderItems": [{"OrderItemId": "1"}], "NextToken": "p2"})
        if NextToken == "p2":
            return R({"OrderItems": [{"OrderItemId": "2"}], "NextToken": "p3"})
        return R({"OrderItems": [{"OrderItemId": "3"}]})


built = []
AO.client = lambda creds, enum: built.append(1) or FakeOC()
oc = FakeOC()
got = AO.order_items_raw(None, None, "206-1", oc=oc)
check("every page is read, in order", [x["OrderItemId"] for x in got], ["1", "2", "3"])
check("  asking with each NextToken Amazon gave", oc.calls, [None, "p2", "p3"])
check("a client the caller holds is reused, none built", built, [])
AO.order_items_raw({"x": 1}, "UK", "206-2")
check("with no client given, exactly one is built", built, [1])

print("\n== no code outside api/ calls getOrderItems itself ==")
hits = []
for top in ("routes", "domain", "data", "listing", "monitor"):
    base = os.path.join(HERE, top)
    for root, _d, files in os.walk(base):
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(root, f)
                if re.search(r"\.get_order_items\(", open(p, encoding="utf-8").read()):
                    hits.append(os.path.relpath(p, HERE))
check("only api/ reads an order's items from Amazon", hits, [])

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
