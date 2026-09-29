# -*- coding: utf-8 -*-
"""Telling Amazon an order was dispatched (29 Sep 2026) -- built, OFF, mock-tested.

Amazon is NEVER contacted here: api.amazon_orders_ship is replaced by a fake
that records every call. Pins:
  - the request matches Amazon's ConfirmShipmentRequest (Rule 4: ordersV0.json,
    read 29 Sep 2026) -- required fields, ISO ship date, carrierCode "Other" +
    carrierName (no guessed carrier codes); whole unshipped orders only
  - while the owner's switch is off, /orders/ship/confirm refuses BEFORE any
    Amazon call, even a read; the switch is read FRESH, both ways
  - switched on, exactly one confirmation is sent and the tracking recorded;
    a second one for the same order is refused by this app's own record
  - Amazon's refusal: its own words, nothing recorded, not retried. No clear
    answer (timeout / no status): "not known", recorded UNSURE, resend blocked
  - success is only an explicit 2xx (api layer); a local save failure after
    Amazon accepted still reports that it was SENT
  - the account must be named and allowed to publish; sending needs "publish"

SAFE HOWEVER IT IS RUN: its own throwaway config and database.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
fails = []

_TMP = tempfile.mkdtemp(prefix="altaship_")
_CFG = os.path.join(_TMP, "config.json")
_BASE = {"anthropic_api_key": "not-a-key", "google_spreadsheet_id": "not-a-sheet",
         "google_service_account_json": os.path.join(_TMP, "none.json"),
         "accounts": [{"id": "ts_a", "label": "T A", "marketplaces": ["UK"],
                       "default_marketplace": "UK"},
                      {"id": "ts_nopub", "label": "No publish", "marketplaces": ["UK"],
                       "default_marketplace": "UK"}]}


def _write_cfg(**extra):
    d = dict(_BASE)
    d.update(extra)
    json.dump(d, open(_CFG, "w"))


_write_cfg()
os.environ["CONFIG_PATH"] = _CFG
os.environ["ALTASCRAPER_DB"] = os.path.join(_TMP, "t.db")
os.environ["ALTASCRAPER_BACKGROUND"] = "off"


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-72s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


from domain import ship_confirm as SC          # noqa: E402

RAW = [{"OrderItemId": "111", "QuantityOrdered": 2, "QuantityShipped": 0},
       {"OrderItemId": "333", "QuantityOrdered": 3}]

print("== the request, against Amazon's schema ==")
p, probs = SC.build_payload("A1F83G8C2ARO7P", RAW, "RM123456789GB", "Royal Mail", "2026-09-30")
check("built with no problems", probs, [])
check("top level: exactly marketplaceId + packageDetail", sorted(p), ["marketplaceId", "packageDetail"])
d = p["packageDetail"]
for k in ("packageReferenceId", "carrierCode", "trackingNumber", "shipDate", "orderItems"):
    check("  required %s present" % k, bool(d.get(k)), True)
check("packageReferenceId is a positive number, as a string", (d["packageReferenceId"], d["packageReferenceId"].isdigit()), ("1", True))
check("no guessed carrier code: Other + the name typed", (d["carrierCode"], d["carrierName"]), ("Other", "Royal Mail"))
check("a date alone becomes ISO 8601 UTC at noon", d["shipDate"], "2026-09-30T12:00:00Z")
check("every line, full quantity, as integers", d["orderItems"],
      [{"orderItemId": "111", "quantity": 2}, {"orderItemId": "333", "quantity": 3}])
check("nothing outside the schema's fields", set(d) <= {"packageReferenceId", "carrierCode", "carrierName",
      "shippingMethod", "trackingNumber", "shipDate", "shipFromSupplySourceId", "orderItems"}, True)
check("Amazon's own 400 example date (02/21/2022) is refused", SC.iso_ship_date("02/21/2022"), None)
check("a time with no zone is refused rather than guessed", SC.iso_ship_date("2026-09-30T10:00:00"), None)
check("a zoned time is converted to UTC", SC.iso_ship_date("2026-09-30T10:00:00+01:00"), "2026-09-30T09:00:00Z")
_, pr = SC.build_payload("A1F83G8C2ARO7P", RAW, "", "Royal Mail")
check("no tracking -> refused in words", pr, ["Type the tracking number first."])
_, pr = SC.build_payload("A1F83G8C2ARO7P", RAW, "RM123456789GB", "")
check("no carrier -> refused (carrierName is required with Other)", len(pr), 1)
PART = [{"OrderItemId": "1", "QuantityOrdered": 2, "QuantityShipped": 1}]
p2, pr = SC.build_payload("A1F83G8C2ARO7P", PART, "RM123456789GB", "RM")
check("partly shipped -> refused (packageReferenceId must be unique per order)",
      (p2, any("already shipped" in x for x in pr)), (None, True))
_, pr = SC.build_payload("A1F83G8C2ARO7P", RAW + [{"OrderItemId": "9", "QuantityOrdered": "two"}], "RM123456789GB", "RM")
check("a line in an unknown shape refuses the ORDER, never skipped", any("does not recognise" in x for x in pr), True)
_, pr = SC.build_payload("A1F83G8C2ARO7P", [dict(RAW[0], IsTransparency=True)], "RM123456789GB", "RM")
check("a Transparency item -> refused in words", any("Transparency" in x for x in pr), True)
check("the switch is off unless exactly true", [SC.is_on({}), SC.is_on({"ship_confirm_enabled": "yes"}), SC.is_on({"ship_confirm_enabled": True})],
      [False, False, True])

print("== the api layer: success only on an explicit 2xx ==")
from api import amazon_orders_ship as AOS      # noqa: E402
from sp_api.base import ApiResponse            # noqa: E402
_real_confirm, _real_client = AOS.confirm_shipment, AOS._client


class _FakeOC:
    def __init__(self, resp):
        self.resp = resp

    def confirm_shipment(self, order_id, **body):
        return self.resp


AOS._client = lambda creds, enum: _FakeOC(ApiResponse(status_code=204))
check("a bodiless 204 is success", _real_confirm({}, None, "1", {}), 204)
for label, resp in (("a 403 shaped {message} (no errors key)", ApiResponse(message="Access denied")),
                    ("an unreadable reply ({})", ApiResponse())):
    AOS._client = (lambda r: (lambda creds, enum: _FakeOC(r)))(resp)
    try:
        _real_confirm({}, None, "1", {})
        check(label + " -> NOT counted as sent", "returned", "NotConfirmed")
    except AOS.NotConfirmed:
        check(label + " -> NOT counted as sent", "NotConfirmed", "NotConfirmed")
AOS._client = _real_client

print("== the routes, with Amazon replaced by a fake ==")
from domain import accounts as ACC             # noqa: E402
from sp_api.base import SellingApiException    # noqa: E402
calls = []
state = {"mode": "ok"}


def fake_items(creds, enum, oid):
    calls.append(("items", oid))
    return RAW


def fake_confirm(creds, enum, oid, body):
    calls.append(("confirm", oid, body))
    if state["mode"] == "refuse":
        # Built the way sp_api raises it (_core.parse_response: errors, headers=).
        raise SellingApiException([{"code": "InvalidInput", "message": "carrierName is not valid"}], headers={})
    if state["mode"] == "timeout":
        raise TimeoutError("read timed out")
    return 204


AOS.order_items = fake_items
AOS.confirm_shipment = fake_confirm
ACC.account_creds = lambda acc: {"refresh_token": "fake"}
ACC.can_publish = lambda acc: (acc or {}).get("id") == "ts_a"

import dashboard as D                          # noqa: E402
app = D.build_app()
app.config["TESTING"] = True
c = app.test_client()
BODY = {"account": "ts_a", "marketplace": "UK", "order_id": "203-1",
        "tracking_number": "RM123456789GB", "carrier": "Royal Mail", "ship_date": "2026-09-30"}
n_sent = lambda: len([x for x in calls if x[0] == "confirm"])   # noqa: E731

r = c.post("/orders/ship/confirm", json=BODY)
check("switched off: confirm refused", (r.status_code, (r.get_json() or {}).get("switched_on")), (409, False))
check("  and Amazon was not contacted at all", calls, [])
r = c.post("/orders/ship/preview", json=BODY)
j = r.get_json() or {}
check("preview works while off", (r.status_code, j.get("ok"), j.get("switched_on")), (200, True, False))
check("  it read the lines and sent NOTHING", [x[0] for x in calls], ["items"])
check("  and says what would be sent", "Royal Mail tracking RM123456789GB" in (j.get("summary") or ""), True)
check("  with the reason it is off", bool(j.get("why_off")), True)
r = c.post("/orders/ship/preview", json={"order_id": "203-1", "tracking_number": "RM123456789GB", "carrier": "RM"})
check("no account named -> refused", r.status_code, 400)
r = c.post("/orders/ship/preview", json=dict(BODY, account="ts_nopub"))
check("an account not allowed to publish -> refused before Amazon", (r.status_code, len(calls)), (400, 1))

_write_cfg(ship_confirm_enabled=True)          # no restart, no cache reset
calls.clear()
r = c.post("/orders/ship/confirm", json=BODY)
j = r.get_json() or {}
check("switched ON takes effect at once, and it is sent", (r.status_code, j.get("ok")), (200, True))
sent = [x for x in calls if x[0] == "confirm"]
check("  exactly one confirmation", len(sent), 1)
check("  with the schema-shaped request", sent[0][2]["packageDetail"]["orderItems"] if sent else None,
      [{"orderItemId": "111", "quantity": 2}, {"orderItemId": "333", "quantity": 3}])
from domain import tracking as TR              # noqa: E402
got = TR.for_orders(_CFG, "ts_a", "UK", ["203-1"]).get("203-1") or []
check("  and the tracking is recorded locally, as sent", [(t["tracking_number"], t["source"]) for t in got],
      [("RM123456789GB", "amazon")])
r = c.post("/orders/ship/confirm", json=BODY)
check("a SECOND send for the same order is refused by this app's record",
      (r.status_code, (r.get_json() or {}).get("already_sent"), n_sent()), (409, True, 1))

state["mode"] = "refuse"
calls.clear()
r = c.post("/orders/ship/confirm", json=dict(BODY, order_id="203-2"))
j = r.get_json() or {}
check("Amazon refuses -> 502 with Amazon's own words", (r.status_code, "carrierName is not valid" in (j.get("error") or "")), (502, True))
check("  and nothing is recorded", TR.for_orders(_CFG, "ts_a", "UK", ["203-2"]), {})
check("  and it is not retried", n_sent(), 1)
check("  and it is not called uncertain", j.get("uncertain"), None)

state["mode"] = "timeout"
calls.clear()
r = c.post("/orders/ship/confirm", json=dict(BODY, order_id="203-3"))
j = r.get_json() or {}
check("no clear answer -> 'not known', never 'refused'",
      (r.status_code, j.get("uncertain"), "not known" in (j.get("error") or ""), "refused" in (j.get("error") or "")),
      (502, True, True, False))
got = TR.for_orders(_CFG, "ts_a", "UK", ["203-3"]).get("203-3") or []
check("  recorded as UNSURE", [t["source"] for t in got], ["amazon_unsure"])
state["mode"] = "ok"
r = c.post("/orders/ship/confirm", json=dict(BODY, order_id="203-3"))
check("  which blocks a resend until someone has looked", (r.status_code, (r.get_json() or {}).get("already_sent")), (409, True))
TR.remove(_CFG, "ts_a", "UK", "203-3", "RM123456789GB")
r = c.post("/orders/ship/confirm", json=dict(BODY, order_id="203-3"))
check("  removing that number allows it again", r.status_code, 200)

_real_add = TR.add


def _broken_add(*a, **k):
    raise RuntimeError("disk full")


TR.add = _broken_add
r = c.post("/orders/ship/confirm", json=dict(BODY, order_id="203-4"))
j = r.get_json() or {}
TR.add = _real_add
check("saved locally fails AFTER Amazon accepted -> still reported SENT",
      (r.status_code, j.get("ok"), "could not be saved" in (j.get("note") or "")), (200, True, True))

r = c.post("/orders/ship/confirm", json=dict(BODY, order_id="203-5", tracking_number=""))
check("switched on, but no tracking -> refused before sending", r.status_code, 400)

_write_cfg()                                   # OFF again, still no restart
calls.clear()
r = c.post("/orders/ship/confirm", json=dict(BODY, order_id="203-6"))
check("switched OFF takes effect at once too (review finding)", (r.status_code, calls), (409, []))

print("== permission and log ==")
from auth import guard as G                    # noqa: E402
from domain import activity_catalog as AC      # noqa: E402
check("sending needs publish", G.required_permission("/orders/ship/confirm", "POST"), "publish")
check("preview needs edit", G.required_permission("/orders/ship/preview", "POST"), "edit")
editor = {"id": "u_e", "role": "custom", "active": True, "permissions": ["edit"],
          "features": {"orders": "edit"}, "workspaces": ["ts_a"], "perms_version": 99}
ok, _w = G.check("/orders/ship/confirm", "POST", editor, {"account": "ts_a"}, {})
check("an editor without publish may NOT send", ok, False)
ok, _w = G.check("/orders/ship/preview", "POST", editor, {"account": "ts_a"}, {})
check("  but may preview", ok, True)
check("sending is recorded in the activity log", (AC.match("POST", "/orders/ship/confirm") or ())[3:4], ("amazon.ship_confirm",))
check("previewing is not (it is a read)", AC.match("POST", "/orders/ship/preview"), None)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
