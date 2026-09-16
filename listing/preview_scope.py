"""listing/preview_scope.py -- which listings a Preview or Submit run may touch,
and what a Preview may write back.

    "it says it is fixed 33 but still when i open pdp i see that error message
     still displaying there"
    "yes add the bulk preview button in the app. which lets user to preview
     selected listings"

Amazon's reply to the last Preview or Submit is kept on the listing (see
listing/api_issues.py), and only a fresh Preview or Submit replaces it. After
"Fix product types" changed 33 listings, the note Amazon attached when it
ACCEPTED them -- "your product type has been updated from HOME to PILLOW" --
stayed on the page, and nothing could clear it: Preview skipped every SUBMITTED
listing, and those were most of them.

A Preview sends nothing (VALIDATION_PREVIEW), so asking Amazon about a submitted
listing is safe. What is NOT safe is what the run wrote afterwards: a clean
Preview sets the status to API_READY and an unclean one to API_ERROR. On a
SUBMITTED listing that would put a listing Amazon already holds back among the
drafts and make it submittable a second time.

So, decided here and nowhere else:
  * a SUBMITTED listing is previewed only when the owner NAMED it (ticked it) --
    the whole-account Preview keeps its old scope exactly;
  * its Preview refreshes Amazon's reply and nothing else: the status, the note
    and the record of the payload it was submitted with are left alone.
"""

# Submit publishes vetted rows only.
SUBMIT_ELIGIBLE = frozenset({"APPROVED", "API_READY"})

# Preview is read-only validation, so it runs on any row with a SKU and a product
# type -- including held ones -- to show what Amazon needs BEFORE approving.
PREVIEW_ELIGIBLE = frozenset({"APPROVED", "API_READY", "API_ERROR", "NEEDS_REVIEW",
                              "COMPLIANCE_HOLD", "IP_HOLD", "HOLD", ""})

# Previewed only when named, and never re-statused by it.
PREVIEW_WHEN_NAMED = frozenset({"SUBMITTED"})


def eligible(submit, named=False):
    """The statuses this run processes. `named`: the run was given specific SKUs."""
    if submit:
        return set(SUBMIT_ELIGIBLE)
    out = set(PREVIEW_ELIGIBLE)
    if named:
        out |= PREVIEW_WHEN_NAMED
    return out


def keeps_status(submit, status):
    """True when this run must write Amazon's reply only -- no status, no note,
    no payload record -- because the listing is already with Amazon."""
    return (not submit) and str(status or "").strip().upper() in PREVIEW_WHEN_NAMED
