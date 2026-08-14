"""Every Stop button stops its own work and nothing else.

THE COMPLAINT: "each stop button should stop its relevant functions for which it
is there, not some irrelevant processes."

WHAT WAS WRONG. Two different controls reached across accounts:

  /stop            filtered by OWNER only. For the shared-password owner -- the
                   only user on most installs -- owner is empty, so it stopped
                   every run on the server. Pressing Stop in Jack Reacherd ended
                   a Nestwell Goods submit that was halfway through.

  /genimage/stop_all  filtered by owner only too, and image jobs recorded no
                   account at all, so one person's batches were
                   indistinguishable across workspaces.

And /run/health reported the process-wide flag, so the generation bar appeared
in accounts that had started nothing -- offering a Stop button for somebody
else's work.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

from domain.run_slots import SLOTS

print("=== run slots: Stop is scoped by account ===")
SLOTS._slots.clear()
SLOTS.acquire("jack_uk", "SKU-J1", owner="")
SLOTS.acquire("jack_uk", "SKU-J2", owner="")
SLOTS.acquire("nestwell_goods", "SKU-N1", owner="")
check("three runs across two accounts", len(SLOTS.active()), 3)

stopped = SLOTS.stop(owner=None, account="jack_uk")
check("stopping jack_uk ends both of its runs", stopped, 2)
left = SLOTS.active()
check("  and leaves the other account's alone", len(left), 1)
check("  which is still Nestwell's", left[0]["account"], "nestwell_goods")
# The empty-owner case is the one that was broken: with no user id, owner
# filtering does nothing at all, so account has to carry it.
check("an empty owner does NOT mean every account",
      SLOTS.stop(owner=None, account="jack_uk"), 0)
check("  Nestwell is still running", len(SLOTS.active()), 1)
check("and stopping with no filters at all still stops everything",
      SLOTS.stop(), 1)
SLOTS._slots.clear()

print("\n=== the run bar belongs to one account ===")
import dashboard as D
app = D.build_app(); app.config["TESTING"] = True
SLOTS._slots.clear()
with app.test_client() as c:
    with c.session_transaction() as s:
        s["user"] = "owner"; s["role"] = "owner"; s["is_owner"] = True

    def health(acct):
        c.post("/accounts/select", json={"id": acct, "marketplace": "UK"})
        return c.get("/run/health").get_json() or {}

    SLOTS.acquire("nestwell_goods", "SKU-N1", owner="")
    h_other = health("jack_uk")
    h_mine = health("nestwell_goods")
    check("the account that started it sees it", h_mine.get("mine"), 1)
    # THE BUG: this said RUNNING in every account.
    check("the account that did NOT start it is idle", h_other.get("state"), "IDLE")
    check("  with nothing of its own", h_other.get("mine"), 0)
    check("  but it is TOLD something runs elsewhere, not left guessing",
          h_other.get("elsewhere"), 1)
    SLOTS._slots.clear()

print("\n=== image batches carry their account ===")
import inspect as _i
GEN = _i.getsource(D._new_img_job)
truthy("a new batch records which account it belongs to", '"account"' in GEN)
GSRC = open(r"D:\AltaScraper\routes\genimage_routes.py", encoding="utf-8").read()
truthy("the progress list filters by account", "j_acct != _acct" in GSRC)
truthy("  and says how many run elsewhere rather than hiding them",
       "elsewhere" in GSRC)
truthy("Stop-all is scoped to this account", "left_running_elsewhere" in GSRC)
truthy("  and there is still a way to stop ONE batch",
       "genimage/stop_job" in GSRC)
JS = open(r"D:\AltaScraper\static\js\settings.js", encoding="utf-8").read()
truthy("the bar offers stopping just the batch it is showing",
       "function stopThisGeneration" in JS)
truthy("  and Stop-all says it is limited to this account",
       "running in this account" in JS)

print("\n=== /stop reports what it deliberately left alone ===")
USRC = open(r"D:\AltaScraper\routes\ui_routes.py", encoding="utf-8").read()
truthy("it passes the account to the slots", "account=(acct or None)" in USRC)
truthy("  and returns what was left running elsewhere",
       "left_running_elsewhere" in USRC)

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
