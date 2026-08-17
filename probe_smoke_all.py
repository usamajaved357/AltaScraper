"""probe_smoke_all.py -- ask every screen for its data and report what answers.

    python probe_smoke_all.py [BASE_URL]

WHAT THIS IS FOR
The last request of the session was "test every feature". A screen is not tested by
loading it; it is tested by asking the endpoint behind it for real data and looking
at what comes back. So this walks the app's own routes, calls the read-only ones,
and reports three things for each: did it answer, did it answer OK, and did it
answer with anything IN it.

The third is the one that matters. An endpoint returning {"ok": true, "rows": []}
is a pass by any HTTP measure and an empty screen to the person looking at it, so
empty answers are listed separately rather than counted as successes.

NOTHING HERE WRITES. Only GET routes are called, and the ones that cost money or
touch Amazon are named in _SKIP with the reason. The live repricer test -- which
does change a price -- is deliberately a separate script.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"

# Routes NOT called, and why. Every one of these would either cost money, contact
# Amazon or eBay, or change something.
_SKIP = {
    "/genimage": "generates images -- costs money at OpenRouter",
    "/aplus": "generates images -- costs money",
    "/recipes": "the engine behind Creative; called only through a generate",
    "/sourcing/check": "contacts every supplier",
    "/sourcing/apply": "CHANGES PRICES on Amazon",
    "/sourcing/arm": "arms a SKU for live pricing",
    "/sync": "pulls from Amazon, rate-limited to about one report a minute",
    "/live/refresh": "pulls the whole catalogue from Amazon",
    "/submit": "sends listings to Amazon",
    "/logout": "would end the session this probe is using",
    "/backup": "writes a backup archive",
    "/miles": "runs the Miles harvester",
    "/ebay": "contacts eBay",
    "/ppc": "contacts the Advertising API",
}

# Query strings for routes that need one to say anything. Without these they
# answer "no account selected", which is correct and tells us nothing.
#
# BOTH SPELLINGS OF THE ACCOUNT. The app has two route families and they read
# different parameter names: the Sales screens take `account_id` (see
# domain/request_account.named) and Finance, Returns and the Repricer take `id`
# (routes/scope.resolve). Sending only `id` made every live-orders endpoint answer
# "Live orders need this workspace's own Amazon account", which this probe first
# reported as four broken endpoints -- they were not; they were being asked about
# whichever account the server had open. Sending both asks each family in its own
# language.
_ARGS = {
    "id": "jack_uk",
    "account_id": "jack_uk",
    "marketplace": "UK",
}


def routes():
    """Every GET route the app has registered, from the app itself."""
    sys.path.insert(0, r"D:\AltaScraper")
    import dashboard as D
    app = D.build_app()
    out = []
    for rule in app.url_map.iter_rules():
        if "GET" not in (rule.methods or set()):
            continue
        path = str(rule)
        if "<" in path:                      # needs a parameter we cannot invent
            continue
        out.append(path)
    return sorted(set(out))


def skip_reason(path):
    for prefix, why in _SKIP.items():
        if path.startswith(prefix):
            return why
    return ""


def call(path):
    q = "&".join("%s=%s" % (k, v) for k, v in _ARGS.items())
    url = BASE + path + ("&" if "?" in path else "?") + q
    started = time.time()
    try:
        with urllib.request.urlopen(url, timeout=90) as r:
            body = r.read()
            secs = time.time() - started
            ctype = r.headers.get("Content-Type", "")
            if "json" not in ctype:
                return {"code": r.status, "secs": secs, "kind": ctype.split(";")[0],
                        "size": len(body)}
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                return {"code": r.status, "secs": secs, "error": "not valid JSON",
                        "size": len(body)}
            return {"code": r.status, "secs": secs, "json": data, "size": len(body)}
    except urllib.error.HTTPError as e:
        return {"code": e.code, "secs": time.time() - started,
                "error": e.read()[:200].decode("utf-8", "replace")}
    except Exception as e:
        return {"code": None, "secs": time.time() - started,
                "error": "%s: %s" % (type(e).__name__, str(e)[:160])}


def emptiness(data):
    """"" if it has content, else a word for what kind of empty it is.

    An {"ok": true} with nothing in it is a pass to a health check and a blank
    screen to a person, which is the distinction this whole script exists to draw.
    """
    if not isinstance(data, dict):
        return "" if data else "empty"
    if data.get("ok") is False:
        return ""                            # a refusal is an answer, reported below
    for key in ("rows", "items", "orders", "alerts", "products", "listings",
                "actions", "skus", "options", "columns", "metrics", "cards",
                "sources", "candidates", "accounts", "series"):
        if key in data:
            v = data[key]
            if isinstance(v, (list, dict)) and len(v) == 0:
                return "no %s" % key
            return ""
    # Nothing recognisable to count. Only "ok" and a couple of scalars is empty.
    if set(data) <= {"ok", "error", "note", "message"}:
        return "nothing but a status"
    return ""


def main():
    paths = routes()
    print("%d GET routes with no parameters\n" % len(paths))
    good, refused, broke, blank, skipped = [], [], [], [], []

    for p in paths:
        why = skip_reason(p)
        if why:
            skipped.append((p, why))
            continue
        r = call(p)
        code = r.get("code")
        if code != 200:
            broke.append((p, "HTTP %s %s" % (code, (r.get("error") or "")[:90])))
            continue
        if "json" not in r:
            good.append((p, "%s %d bytes in %.1fs"
                         % (r.get("kind") or "?", r.get("size", 0), r["secs"])))
            continue
        data = r["json"]
        if isinstance(data, dict) and data.get("ok") is False:
            refused.append((p, str(data.get("error"))[:110]))
            continue
        e = emptiness(data)
        if e:
            blank.append((p, "%s (%.1fs)" % (e, r["secs"])))
        else:
            good.append((p, "%.1fs, %d bytes" % (r["secs"], r.get("size", 0))))

    def show(title, rows):
        print("\n" + "=" * 72)
        print("%s -- %d" % (title, len(rows)))
        print("=" * 72)
        for p, note in rows:
            print("  %-44s %s" % (p, note))

    show("ANSWERED WITH DATA", good)
    show("ANSWERED, BUT EMPTY -- a blank screen to whoever opens it", blank)
    show("REFUSED (a real answer: says why it cannot)", refused)
    show("BROKEN", broke)
    show("NOT CALLED ON PURPOSE", skipped)

    print("\n" + "=" * 72)
    print("%d with data, %d empty, %d refused, %d BROKEN, %d skipped"
          % (len(good), len(blank), len(refused), len(broke), len(skipped)))
    return 1 if broke else 0


if __name__ == "__main__":
    sys.exit(main())
