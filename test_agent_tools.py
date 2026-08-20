"""The assistant may only look, and only at this account.

Three properties matter more than anything the model says, because they are the
ones a wrong answer cannot recover from:

  1. every tool is a GET, and a GET that really exists on this app
  2. the account cannot be chosen by the model
  3. a trimmed list admits it was trimmed

The first is the one that rots silently: rename an endpoint and the assistant
starts answering "that screen returned 404" instead of the truth, which reads
like a data problem. Checking the allowlist against the app's real routing
table is what keeps that honest.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from domain import agent_tools as AT

print("== every tool points at a real, read-only screen ==")
import dashboard

app = dashboard.build_app()
get_rules = {str(r.rule) for r in app.url_map.iter_rules()
             if sorted(r.methods - {"HEAD", "OPTIONS"}) == ["GET"]}
all_rules = {str(r.rule) for r in app.url_map.iter_rules()}

for t in AT.TOOLS:
    p = t["path"]
    if p is None:
        continue
    truthy("%-24s reads %-22s and that route exists" % (t["name"], p),
           p in all_rules)
    # GET-only is the guarantee. A route that also accepts POST could be
    # reached with a body by something later; the allowlist must not contain
    # one at all.
    truthy("  %-22s is GET-only" % p, p in get_rules)

print("\n== nothing in the list writes ==")
WRITE_WORDS = ("submit", "publish", "apply", "delete", "save", "push",
               "reprice", "send", "create", "update")
for t in AT.TOOLS:
    p = (t["path"] or "").lower()
    bad = [w for w in WRITE_WORDS if w in p]
    check("%-24s path has no writing verb in it" % t["name"], bad, [])

print("\n== the model cannot choose whose account it reads ==")
for t in AT.TOOLS:
    for banned in ("id", "account_id", "marketplace", "workspace_id"):
        truthy("%-24s does not accept '%s'" % (t["name"], banned),
               banned not in t["params"])

calls = []


def fake_fetch(path, params):
    calls.append((path, dict(params)))
    return 200, {"ok": True, "rows": [{"n": i} for i in range(200)]}


SCOPE = {"account_id": "jack_uk", "marketplace": "UK", "today": "2026-08-20"}

out, err = AT.run("sales_by_product",
                  {"preset": "30d", "id": "sheelady_us",
                   "marketplace": "US", "group": "parent"},
                  fetch=fake_fetch, scope=SCOPE)
check("an id smuggled into the arguments is overwritten",
      calls[-1][1]["id"], "jack_uk")
check("  and so is the marketplace", calls[-1][1]["marketplace"], "UK")
check("  while a real argument still gets through",
      calls[-1][1].get("group"), "parent")
truthy("  and an unknown argument is dropped", "foo" not in calls[-1][1])

print("\n== a trimmed list says it was trimmed ==")
check("only the cap is returned", len(out["rows"]), 40)
truthy("and the result says how many there really were",
       "40 of 200" in (out.get("_trimmed") or ""))
truthy("  naming what the order means",
       "highest revenue first" in (out.get("_trimmed") or ""))

# A short list must NOT carry the note, or the note stops meaning anything.
short, _ = AT.run("recent_orders", {},
                  fetch=lambda p, q: (200, {"rows": [{"a": 1}]}), scope=SCOPE)
truthy("a list that fits carries no trim note", "_trimmed" not in short)

print("\n== a screen that refuses is reported, not papered over ==")
bad, is_err = AT.run("profit_by_product", {},
                     fetch=lambda p, q: (400, {"error": "Open an account first."}),
                     scope=SCOPE)
truthy("the failure is flagged as an error", is_err)
check("and the screen's own words are kept",
      bad["error"], "Open an account first.")

boom, is_err2 = AT.run("daily_round", {},
                       fetch=lambda p, q: (_ for _ in ()).throw(RuntimeError("no db")),
                       scope=SCOPE)
truthy("an exception becomes an error result, not a crash", is_err2)
truthy("  and says which screen", "/daily/check" in boom["error"])

truthy("an unknown tool name is refused",
       AT.run("drop_tables", {}, fetch=fake_fetch, scope=SCOPE)[1])

print("\n== the account_in_view tool answers from the scope, not a screen ==")
n_before = len(calls)
who, _ = AT.run("account_in_view", {}, fetch=fake_fetch, scope=SCOPE)
check("it reads no screen at all", len(calls), n_before)
check("and reports the pinned account", who["account_id"], "jack_uk")

print("\n== the schema the model is given ==")
defs = AT.definitions()
check("one definition per tool", len(defs), len(AT.TOOLS))
for d in defs:
    truthy("%-24s has a description worth reading" % d["name"],
           len(d["description"]) > 60)
    truthy("  %-22s takes an object" % d["name"],
           d["input_schema"]["type"] == "object")
    truthy("  %-22s requires nothing" % d["name"],
           d["input_schema"]["required"] == [])

# The two rules that must survive into the prompt, because they are the ones
# where being wrong costs money rather than credibility.
print("\n== the standing rules reached the system prompt ==")
import routes.agent_routes as AR

truthy("it is told never to invent a figure",
       "Never invent a number" in AR.SYSTEM)
truthy("it is told to say when a tool came back empty",
       "SAY THAT" in AR.SYSTEM)
truthy("it is told never to convert a currency",
       "Never convert a currency" in AR.SYSTEM)
truthy("it is told never to propose a bid or budget (CLAUDE.md rule 8)",
       "Never propose a new bid" in AR.SYSTEM)
truthy("it is told it cannot change anything",
       "no tool that writes" in AR.SYSTEM)
truthy("it is told to name the account and the dates",
       "name the account" in AR.SYSTEM)
truthy("it is told to carry the measured/estimated split",
       "MEASURED, OR ESTIMATED" in AR.SYSTEM)
# Ava's own #1 failure: "Profit with missing COGS ... It looks right. It's
# wrong ... This is the top silent failure across all brands."
truthy("it is told to check cost coverage before quoting profit",
       "BEFORE YOU QUOTE A PROFIT FIGURE" in AR.SYSTEM)
truthy("  and told which way the error runs",
       "can only ever be flattered" in AR.SYSTEM)
# Ava #22: ordered vs finance are different questions, not a discrepancy.
truthy("it is told what to do when two figures disagree",
       "WHEN TWO FIGURES DISAGREE" in AR.SYSTEM)
truthy("  and that a gap is usually not an error",
       "usually not an error" in AR.SYSTEM)
truthy("the loop has a hard stop", AR.MAX_ROUNDS <= 12)

print("\n== it can read no screen its user could not open ==")
# The assistant calls the app's own endpoints with the ASKER'S cookie, so
# auth/guard.py applies to it exactly as it applies to the person asking. An
# assistant that could read revenue for a VA who may not see revenue would be a
# hole dressed as a feature. This is the line that makes it inherit rather than
# bypass -- it is asserted because losing it fails silently and permissively.
src = open(os.path.join(HERE, "routes", "agent_routes.py"), encoding="utf-8").read()
truthy("the caller's cookie is forwarded to every screen",
       'request.headers.get("Cookie")' in src)
truthy("  and the tools are GET only", "client.get(path" in src)
truthy("  with no other verb used at all",
       "client.post(" not in src and "client.put(" not in src
       and "client.delete(" not in src)

print("\n== the account is taken from the server, never from the question ==")
truthy("scope comes from the open account",
       "_active_account" in src and "active_account_id" in src)
truthy("  and a chat with no account open is refused, not defaulted",
       "Open an account first" in src)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
