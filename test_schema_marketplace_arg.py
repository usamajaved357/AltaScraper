"""/schema names its marketplace; it never borrows the server's (architecture batch A4).

WHAT IT WAS. /schema/<pt>?mkt=US set _state["active_marketplace"] = "US" for
the length of the request so dashboard._load_schema would read it, then put the
old value back. That value is ONE for the whole server: any other request
running meanwhile -- another tab, a job -- read "US" too (master audit S11; only
the restore half was fixed in Milestone 3).

NOW. _load_schema and its helpers take the marketplace as an argument; /schema
passes it. With no argument they read the active marketplace exactly as before,
so every other caller is unchanged. This pins:
  - the payload answers for the marketplace asked for, else the active one, else UK
  - the active marketplace is never written while /schema runs
  - the helpers with no marketplace still follow the active one
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
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


import dashboard as D

PT = "A4_TEST_TYPE"


def fake(mkt):
    return {"enums": {"color": ["%s-red" % mkt]}, "required": ["req_%s" % mkt],
            "attrs": ["attr_%s" % mkt], "subfields": {"sub_%s" % mkt: {}},
            "titles": {"color": "Colour %s" % mkt}, "help": {}, "maxitems": {},
            "readonly": []}


class Watch(dict):
    """The schema cache, recording the active marketplace at every lookup --
    i.e. what a concurrent request would have read while /schema was running."""
    seen = []

    def __contains__(self, k):
        Watch.seen.append(D._state.get("active_marketplace", ""))
        return dict.__contains__(self, k)


_real_cache = D._state["schemas"]
_had_mkt = "active_marketplace" in D._state
_real_mkt = D._state.get("active_marketplace", "")
cache = Watch(_real_cache)
cache["%s::UK" % PT] = fake("UK")
cache["%s::US" % PT] = fake("US")
D._state["schemas"] = cache

app = D.build_app()
app.config["TESTING"] = True
try:
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user"] = "owner"; s["role"] = "owner"; s["is_owner"] = True

        print("=== the marketplace asked for ===")
        D._state["active_marketplace"] = "UK"
        Watch.seen = []
        j = c.get("/schema/%s?mkt=us" % PT).get_json() or {}
        check("answers for US", j.get("marketplace"), "US")
        check("  with the US schema", j.get("required"), ["req_US"])
        check("  and the US values", (j.get("enums") or {}).get("color"), ["US-red"])
        check("the open marketplace was never switched meanwhile",
              sorted(set(Watch.seen)), ["UK"])
        check("  and is still UK after", D._state.get("active_marketplace"), "UK")

        print("=== none asked: the open one ===")
        D._state["active_marketplace"] = "US"
        j = c.get("/schema/%s" % PT).get_json() or {}
        check("answers for the open marketplace", j.get("marketplace"), "US")
        check("  with its schema", j.get("attrs"), ["attr_US"])
        D._state["active_marketplace"] = ""
        j = c.get("/schema/%s" % PT).get_json() or {}
        check("none open: UK", (j.get("marketplace"), j.get("required")), ("UK", ["req_UK"]))

        print("=== the helpers with no marketplace are unchanged ===")
        D._state["active_marketplace"] = "US"
        check("_schema_required follows the open marketplace", D._schema_required(PT), ["req_US"])
        check("  unless one is named", D._schema_required(PT, "uk"), ["req_UK"])
        check("_options_for too", D._options_for(PT, "UK").get("color"), ["UK-red"])

        print("=== ?refresh=1 clears the marketplace asked for, not the open one ===")
        D._state["active_marketplace"] = "UK"
        from domain import schema_cache as _sc
        forgot = []
        _real_forget = _sc.forget
        _sc.forget = lambda cfg, pt, mkt: forgot.append((pt, mkt))
        _real_read, _real_creds = _sc.read, D._sp_creds
        # NO CALL TO AMAZON. After the clear the loader looks again: the stored
        # copy answers nothing and the credentials refuse, so it gives up locally.
        _sc.read = lambda *a, **k: None
        def _no_amazon(*a, **k):
            raise RuntimeError("test: no Amazon call")
        D._sp_creds = _no_amazon
        try:
            cache_before_uk = dict.__contains__(cache, "%s::UK" % PT)
            c.get("/schema/%s?mkt=US&refresh=1" % PT)
        finally:
            _sc.forget, _sc.read, D._sp_creds = _real_forget, _real_read, _real_creds
        check("the US copy was dropped", dict.__contains__(cache, "%s::US" % PT)
              and cache["%s::US" % PT] is not None and cache["%s::US" % PT].get("required") == ["req_US"], False)
        check("  the UK copy was left alone", dict.__contains__(cache, "%s::UK" % PT), cache_before_uk)
        check("  the stored US copy was forgotten", (PT, "US") in forgot, True)
        check("  and nothing of UK's", (PT, "UK") in forgot, False)
        check("  the open marketplace untouched", D._state.get("active_marketplace"), "UK")
finally:
    D._state["schemas"] = _real_cache
    if _had_mkt:
        D._state["active_marketplace"] = _real_mkt
    else:
        D._state.pop("active_marketplace", None)

print("=== the route no longer writes the open marketplace ===")
src = open("routes/listing_routes.py", "rb").read().decode("utf-8")
body = src[src.index('@app.route("/schema/<path:pt>")'):]
body = body[:body.index("@app.route", 10)]
import re as _re
check("no write to active_marketplace in /schema (any form)",
      bool(_re.search(r'active_marketplace"\]\s*=(?!=)|\.update\(|set_shared|setdefault\(\s*"active_marketplace', body)), False)

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\nall /schema marketplace checks passed")
