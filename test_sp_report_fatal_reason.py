# -*- coding: utf-8 -*-
"""A FATAL report says Amazon's own reason (owner-approved capture, 30 Sep 2026).

Captured shape (Search Query Performance, nestwell UK): getReport ends
processingStatus FATAL WITH a reportDocumentId, and that document is
{"errorDetails": "A client error occurred. Please double check that your
parameters are valid ..."}. The app used to guess the reason instead.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
fails = []


def check(label, ok):
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL"))


from api import sp_reports as R               # noqa: E402

REASON = ("A client error occurred. Please double check that your parameters are "
          "valid and fulfill the requirements of the report type.")


class FakeRC:
    def __init__(self, doc_id, doc):
        self.doc_id, self.doc = doc_id, doc

    def create_report(self, **kw):
        return {"reportId": "1"}

    def get_report(self, rid):
        p = {"processingStatus": "FATAL", "reportId": rid}
        if self.doc_id:
            p["reportDocumentId"] = self.doc_id
        return p

    def get_report_document(self, doc_id, download=True):
        if self.doc is None:
            raise RuntimeError("no document")
        return {"document": self.doc}


def run(rc):
    try:
        R.create_and_wait(rc, "GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT")
    except R.ReportError as e:
        return e
    return None


e = run(FakeRC("amzn1.spdoc.x", json.dumps({"errorDetails": REASON})))
check("FATAL is still a ReportError with status FATAL", e is not None and e.status == "FATAL")
check("  carrying Amazon's own reason", getattr(e, "amazon_error", "") == REASON)
check("  and saying it in the message", REASON in str(e))
e = run(FakeRC(None, None))
check("no document: no reason, the old message stands",
      e is not None and not getattr(e, "amazon_error", "") and "FATAL" in str(e))
e = run(FakeRC("amzn1.spdoc.x", None))
check("a document that cannot be read never breaks the error",
      e is not None and e.status == "FATAL" and not getattr(e, "amazon_error", ""))
src = open(os.path.join(HERE, "routes", "sqp_routes.py"), encoding="utf-8").read()
check("the SQP route shows Amazon's reason instead of guessing", "Its reason: " in src and "amazon_error" in src)

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
