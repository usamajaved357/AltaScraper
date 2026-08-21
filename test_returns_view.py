"""Why things come back, and what it costs.

WHAT AMAZON ACTUALLY GIVES US, measured on the live accounts 15 Aug 2026:

    GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA   CANCELLED -- no data. These
        accounts are MFN; there are no FBA returns to report.
    GET_FLAT_FILE_RETURNS_DATA_BY_RETURN_DATE   DONE, 35 columns, real rows.
    a 90-day window                             FATAL. Amazon caps it at 60.

So two sections of the original report cannot be built from a seller-fulfilled
account -- the disposition a return was graded with, and the customer's comment
-- because Amazon only records those when it physically receives the return in
its own warehouse, which is FBA. An MFN return goes straight back to the seller.
Uploading an FBA file fills them in; that is what the manual path is FOR.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

from domain import returns_view as RV

print("=== Amazon's reason codes become four things you can DO ===")
check("a defect is a product problem", RV.nature_of("DEFECTIVE"), "Product Quality")
check("  even with the seller-fulfilled prefix",
      RV.nature_of("CR-DEFECTIVE"), "Product Quality")
check("wrong description is a LISTING problem, not a product one",
      RV.nature_of("NOT_AS_DESCRIBED"), "Listing Content")
check("  and so is 'not compatible'", RV.nature_of("CR-NOT_COMPATIBLE"), "Listing Content")
check("changed their mind is neither", RV.nature_of("UNWANTED_ITEM"), "Customer Preference")
check("broken by the carrier is shipping",
      RV.nature_of("DAMAGED_BY_CARRIER"), "Shipping / Delivery")
# A misfiled return points at the wrong fix, which is worse than an unfiled one.
check("something we have no rule for is NOT forced into a bucket",
      RV.nature_of("SOME_NEW_CODE_2027"), "Unclassified")
check("  and neither is a blank", RV.nature_of(""), "Unclassified")

print("\n=== the real report's columns, as Amazon writes them ===")
MFN_HEAD = ["Order ID", "Order date", "Return request date", "Return request status",
            "Amazon RMA ID", "ASIN", "Merchant SKU", "Item Name", "Return quantity",
            "Return Reason", "Resolution", "Order Amount", "Refunded Amount", "Category"]
MFN_ROW = ["206-6011978-5897935", "16-Jul-2026", "23-Jul-2026", "Approved",
           "DDt8fkJzRRMA", "B0H7N2Q5GG", "15.10_2Days_B0F7D29MFZ",
           "Bayonet Ceiling Fan", "1", "CR-NOT_COMPATIBLE", "StandardRefund",
           "33.24", "34.99", "Home"]
kind, idx = RV.detect(MFN_HEAD)
check("a seller-fulfilled report is recognised", kind, "mfn")
rows, kind2, skipped = RV.parse_rows(MFN_HEAD, [MFN_ROW])
check("one return parsed", len(rows), 1)
r = rows[0]
# Amazon writes 23-Jul-2026 here, not an ISO date; sorting the raw string puts
# April before January.
check("the date is made sortable", r["date"], "2026-07-23")
check("the prefix is stripped from the reason", r["reason"], "NOT_COMPATIBLE")
check("  and classified", r["nature"], "Listing Content")
check("the ACTUAL refund is read, not estimated", r["refunded"], 34.99)
check("FBA-only fields are absent, not blank",
      (r["disposition"], r["comment"]), (None, None))

print("\n=== an FBA file is told apart by its COLUMNS, not its name ===")
# The same report downloaded twice gets two different filenames.
FBA_HEAD = ["return-date", "order-id", "sku", "asin", "product-name", "quantity",
            "reason", "status", "detailed-disposition", "customer-comments"]
FBA_ROW = ["2026-05-14", "111-2", "PRO-SS", "B0DNFX8MW3", "Promixx Pro", "1",
           "DEFECTIVE", "Unit returned to inventory", "CUSTOMER_DAMAGED",
           "Motor not as fast"]
k2, _ = RV.detect(FBA_HEAD)
check("an FBA report is recognised", k2, "fba")
frows, fk, _s = RV.parse_rows(FBA_HEAD, [FBA_ROW])
check("  its disposition comes through", frows[0]["disposition"], "CUSTOMER_DAMAGED")
check("  and the customer's own words", frows[0]["comment"], "Motor not as fast")

print("\n=== the summary ===")
s = RV.summarise(rows + frows, {"B0H7N2Q5GG": {"units": 40, "sales": 1400.0}})
check("two returns", s["total_returns"], 2)
check("two products", s["unique_skus"], 2)
# A count says nothing on its own: twelve is excellent on four thousand orders
# and a catastrophe on twenty.
check("the rate is worked out where units sold are known",
      s["asins"][0]["rate"] is not None or s["asins"][1]["rate"] is not None, True)
check("  and is None, never 0, where they are not",
      [a["rate"] for a in s["asins"] if a["asin"] == "B0DNFX8MW3"], [None])
check("the refund total is real money", s["refunded"], 34.99)
truthy("  and says so", s["refunded_is_actual"])
check("the four causes are counted",
      sorted(s["natures"].keys()), ["Listing Content", "Product Quality"])
truthy("each cause carries what to DO about it",
       "supplier" in s["nature_actions"]["Product Quality"])
truthy("the FBA-only sections are flagged as present", s["has_disposition"])
truthy("  including the comments", s["has_comments"])

print("\n=== with seller-fulfilled data only, the gaps are STATED ===")
s2 = RV.summarise(rows, {})
check("no disposition", s2["has_disposition"], False)
check("no comments", s2["has_comments"], False)
# Without units sold there IS no rate; 0% would read as "nothing comes back".
check("no rate at all when nothing is known about units sold",
      s2["return_rate"], None)

import inspect as _i
SRC = _i.getsource(__import__("routes.returns_routes", fromlist=["x"]).register)
truthy("the route explains WHY those two are missing",
       "physically receives" in SRC or "receives it" in SRC)
truthy("  and points at the upload that would fill them",
       "Upload an FBA Customer Returns file" in SRC)
# CANCELLED means Amazon had nothing to give, which is not an error.
truthy("an empty report is not reported as a failure", "__EMPTY__" in SRC)
# Matched on a fragment: the sentence is split across source lines, so the whole
# phrase never appears contiguously in the file.
truthy("  and says so in words", "not a failure" in SRC)
truthy("the 60-day cap is enforced, not discovered", "MAX_DAYS" in SRC)

print("\n=== gated with the money screens ===")
from auth.guard import required_permission, feature_for
check("reading needs no special permission",
      required_permission("/returns/report", "GET"), None)
check("uploading only parses, so nor does it",
      required_permission("/returns/upload", "POST"), None)
# CHANGED DELIBERATELY: Returns is its own page now, so it can be withheld from
# someone who may still see the sales dashboard. It INHERITS sales until set, so
# the access anyone actually has is unchanged -- revenue going back out is still
# revenue, and a lister still cannot see it.
check("it is its own page", feature_for("/returns/report"), "returns")
from auth import users as _U
# RETURNS NOW FOLLOWS ORDERS, which is where the menu puts it -- the Orders
# group has two tabs, All orders and Returns Intelligence, and setting the group
# has to move both. Orders itself still follows sales, so the access anyone
# actually has is unchanged: returns -> orders -> sales.
check("  falling back to orders", _U.FEATURE_PARENT.get("returns"), "orders")
check("  which itself falls back to sales", _U.FEATURE_PARENT.get("orders"), "sales")
check("  so a lister still cannot see it",
      _U.feature_level({"active": True, "role": "lister", "features": {}}, "returns"),
      "none")

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
