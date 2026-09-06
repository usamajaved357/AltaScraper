"""api/sp_reports.py -- the report fetcher, and Amazon's habit of marking a
refusal "DONE".

WHY THIS FILE EXISTS. Ask Amazon for a report it will not build -- too wide a
date range, an unsupported option -- and it does not fail the job. It COMPLETES
it, and the document is one line of prose saying why:

    Date range exceeded. Report can be requested only upto 30 days

Sixty-four bytes, processingStatus DONE. find_recent matches on report type and
DONE, so that refusal becomes the cached answer for every caller asking for the
same type for the next half hour -- including callers whose window Amazon would
have built happily. Met while probing the orders report: a 45-day request was
refused, and the corrected 29-day request came straight back with the same
64-byte refusal, marked "reused".

The checks below are mostly about the boundary: a refusal must be recognised, and
a real report -- however small, however odd -- must NEVER be mistaken for one.
Throwing away a genuine report because it looked short would lose data silently,
which is the worse of the two failures.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from api import sp_reports as _sr                 # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


print("\nAmazon's refusals are recognised")
# The exact body that caused this, kept verbatim.
check("the one that started it",
      _sr.looks_like_refusal(
          "Date range exceeded. Report can be requested only upto 30 days"),
      True)
check("with a trailing newline, as it actually arrives",
      _sr.looks_like_refusal(
          "Date range exceeded. Report can be requested only upto 30 days\n"),
      True)
check("another shape of the same thing",
      _sr.looks_like_refusal("Invalid report options provided."), True)

print("\nand a real report is never mistaken for one")
# A TSV WITH ONE ROW is a real answer -- a quiet day with a single order -- and
# throwing it away would lose that order silently.
check("a one-row TSV survives",
      _sr.looks_like_refusal("amazon-order-id\tsku\n123-456\tABC"), False)
check("a header with no rows survives — an empty day is a measurement",
      _sr.looks_like_refusal("amazon-order-id\tsku\tquantity"), False)
check("XML survives", _sr.looks_like_refusal(
    "<?xml version=\"1.0\"?><Message><Order/></Message>"), False)
check("JSON survives", _sr.looks_like_refusal('{"reportSpecification":{}}'),
      False)
# Long prose is not a refusal either: Amazon's refusals are terse, and a long
# body that happens to lack tabs is more likely to be something real.
check("a long body is left alone", _sr.looks_like_refusal("word " * 200), False)
check("a multi-line body is left alone",
      _sr.looks_like_refusal("line one\nline two\nline three"), False)

print("\nand nothing at all is not a refusal either")
# AN EMPTY REPORT IS A REAL ANSWER: no orders in the window. Treating it as a
# refusal would make every quiet week raise an error.
check("empty is not a refusal", _sr.looks_like_refusal(""), False)
check("whitespace is not a refusal", _sr.looks_like_refusal("   \n  "), False)
check("None is not a refusal", _sr.looks_like_refusal(None), False)


print("\nfetch rebuilds rather than inheriting somebody else's failure")


class _Doc:
    """What the SDK hands back: an object with a .payload attribute.

    NOT a dict with a "payload" key -- _payload() checks hasattr, so a dict
    would be passed through whole and every lookup would quietly miss. Getting
    this wrong made the first version of this test pass while exercising
    nothing, which is the failure mode a fake is supposed to prevent.
    """

    def __init__(self, payload):
        self.payload = payload


class FakeRC:
    """Stands in for the SP-API Reports client. Records what was asked for."""

    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.created = 0
        self.downloads = []

    def get_reports(self, **kw):
        # A recent DONE report exists -- the poisoned one.
        return _Doc({"reports": [
            {"reportDocumentId": "cached", "processingStatus": "DONE",
             "createdTime": "2026-09-06T10:00:00Z"}]})

    def create_report(self, **kw):
        self.created += 1
        return _Doc({"reportId": "r%d" % self.created})

    def get_report(self, rid, **kw):
        return _Doc({"processingStatus": "DONE",
                             "reportDocumentId": "fresh%s" % rid})

    def get_report_document(self, doc_id, **kw):
        self.downloads.append(doc_id)
        return _Doc({"document": self.bodies.pop(0)})


REFUSAL = "Date range exceeded. Report can be requested only upto 30 days"

# The cached document is a refusal; the fresh one is real. fetch must not hand
# back the refusal, and must not raise -- our own window is fine.
rc = FakeRC([REFUSAL, "amazon-order-id\tsku\n123-456\tABC"])
text, source, _built = _sr.fetch(rc, "GET_ANYTHING", allow_reuse=True)
check("a poisoned cache entry is not returned", text.startswith("amazon-order-id"),
      True)
check("  it says the answer is new, not reused", source, "new")
check("  and it actually asked Amazon to build one", rc.created, 1)
check("  having first tried the cached one", rc.downloads[0], "cached")

# When OUR OWN request is the one refused, raising is right: handing the prose
# back leaves the caller parsing an apology as if it were data.
rc2 = FakeRC([REFUSAL, REFUSAL])
try:
    _sr.fetch(rc2, "GET_ANYTHING", allow_reuse=True)
    check("a refusal of our own request raises", False, True)
except _sr.ReportError as e:
    check("a refusal of our own request raises", True, True)
    check("  quoting what Amazon actually said", "Date range exceeded" in str(e),
          True)

# And the ordinary path is untouched: a good cached report is still reused,
# with no extra build.
rc3 = FakeRC(["amazon-order-id\tsku\n1\t2"])
text3, source3, _ = _sr.fetch(rc3, "GET_ANYTHING", allow_reuse=True)
check("a good cached report is still reused", source3, "reused")
check("  with no report built at all", rc3.created, 0)

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    for f in fails:
        print("  FAILED:", f)
    sys.exit(1)
print("all passed")

