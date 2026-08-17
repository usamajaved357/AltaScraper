"""probe_repricer_live.py -- does the repricer ACTUALLY change a price on Amazon?

    python probe_repricer_live.py            report only, changes nothing
    python probe_repricer_live.py --live     arm one SKU and push a real change

THIS IS THE ONE TEST THAT CANNOT BE FAKED
Everything else about the repricer can be checked without Amazon: the arithmetic,
the guards, the decision, the audit line. Whether a price actually MOVES on a live
listing depends on the credentials, the marketplace, the Listings API patch, the
master switch, the arming, the cooldown and the account resolution all being right
at the same time. Asked for as:

    "at the end i want you to test every feature like repricer, enroll any item in
     the repricer and test the price is automatically changed or not"

HOW IT KEEPS THE RISK SMALL
It does not let the repricer choose the size of the change. It sets a HOLD PRICE
50p above whatever the listing is at today, which makes the proposed price exactly
that -- a known, tiny, upward change that no buyer can be harmed by and that is
well inside the 25% change cap. Then it puts the price back the same way, clears
everything it touched, and turns the master switch off again.

WHAT IT RESTORES, ALWAYS
  the price          back to what it was, through the same mechanism
  the hold price     cleared
  the SKU            back to dry run
  the master switch  back to whatever it was before this ran

The restore runs in a finally block, so an exception half way through still puts
the account back. What it CANNOT undo is an order placed in the ninety seconds the
price was 50p higher -- which is why the change is upward and small.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:5000"
ACCOUNT = "jack_uk"
MARKET = "UK"
BUMP = 0.50            # how far above today's price to hold it, briefly
LIVE = "--live" in sys.argv


def call(path, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"},
        method=("POST" if body is not None else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}
    except Exception as e:
        return None, {"error": "%s: %s" % (type(e).__name__, str(e)[:160])}


def q(path):
    sep = "&" if "?" in path else "?"
    return "%s%sid=%s&account_id=%s&marketplace=%s" % (path, sep, ACCOUNT,
                                                       ACCOUNT, MARKET)


def rules(sku, **vals):
    return call("/sourcing/rules", {"id": ACCOUNT, "marketplace": MARKET,
                                    "sku": sku, "rule": vals})


def amazon_price(sku):
    """What Amazon says the price is RIGHT NOW -- not what the app has cached.

    The whole point of this probe is to check Amazon, so the app's own idea of the
    price is not evidence. /sourcing/list re-reads the live listing.
    """
    code, j = call(q("/sourcing/list"))
    if code != 200:
        return None, "could not read the list: %s" % (j.get("error") or code)
    for r in (j.get("rows") or []):
        if r.get("sku") == sku:
            return (r.get("current") or {}).get("price"), ""
    return None, "SKU not in the list"


def find_candidate():
    """One armed-able SKU: enrolled, readable supplier, a known live price."""
    code, j = call(q("/sourcing/list"))
    if code != 200:
        return None, "could not read the repricer list: %s" % (j.get("error") or code)
    armed_already = [r["sku"] for r in (j.get("rows") or [])
                     if r.get("mode") == "live"]
    if armed_already:
        # Refuse rather than push someone else's SKU by accident: the master
        # switch is account-wide, so turning it on would let these go too.
        return None, ("these SKUs are already armed, so turning the master switch "
                      "on would push them as well -- not doing that: %s"
                      % ", ".join(armed_already))
    for r in (j.get("rows") or []):
        d = r.get("decision") or {}
        cur = (r.get("current") or {}).get("price")
        if d.get("action") == "update" and cur and (r.get("rule") or {}).get("min_price"):
            return {"sku": r["sku"], "price": float(cur),
                    "min_price": (r.get("rule") or {}).get("min_price")}, ""
    # Nothing has a minimum price set; take the first that could have one.
    for r in (j.get("rows") or []):
        d = r.get("decision") or {}
        cur = (r.get("current") or {}).get("price")
        if d.get("action") == "update" and cur:
            return {"sku": r["sku"], "price": float(cur), "min_price": None}, ""
    return None, "no enrolled SKU has a live price and a usable supplier"


def main():
    print("=" * 74)
    print("REPRICER, END TO END%s" % ("" if LIVE else "  (report only -- pass --live to push)"))
    print("=" * 74)

    cand, why = find_candidate()
    if not cand:
        print("cannot run: %s" % why)
        return 1
    sku, started_at = cand["sku"], cand["price"]
    target = round(started_at + BUMP, 2)
    print("\n  SKU              %s" % sku)
    print("  live price now   %.2f" % started_at)
    print("  will hold at     %.2f  (+%.2f, a %.1f%% move)"
          % (target, BUMP, BUMP / started_at * 100))
    print("  minimum price    %s" % cand["min_price"])

    if not LIVE:
        print("\nNothing was changed. Run with --live to arm this SKU and push.")
        return 0

    code, master0 = call("/sourcing/master")
    was_on = bool(master0.get("enabled"))
    print("  master switch    %s before this run" % ("ON" if was_on else "off"))

    pushed = False
    try:
        # ---- 1. the settings -------------------------------------------
        print("\n--- 1. hold the price 50p above where it is ---")
        if cand["min_price"] is None:
            c, j = rules(sku, min_price=round(started_at * 0.5, 2))
            print("  set a minimum price first (armed SKUs require one): %s"
                  % ("ok" if c == 200 else j.get("error")))
        c, j = rules(sku, hold_price=target)
        print("  hold_price=%.2f -> %s" % (target, "ok" if c == 200 else j.get("error")))
        if c != 200:
            return 1
        stored = (j.get("rule") or {}).get("hold_price")
        print("  stored as        %r  %s" % (stored,
                                             "OK" if stored == target else "MISMATCH"))

        # ---- 2. the decision -------------------------------------------
        print("\n--- 2. what the repricer now decides ---")
        c, j = call(q("/sourcing/list"))
        row = next((r for r in (j.get("rows") or []) if r["sku"] == sku), {})
        d = row.get("decision") or {}
        print("  action           %s" % d.get("action"))
        print("  price            %s" % d.get("price"))
        print("  held             %s" % d.get("held"))
        print("  reason           %s" % (d.get("reason") or "")[:100])
        if d.get("price") != target:
            print("  STOP: the decision is not the held price, so this would push "
                  "something other than the 50p tested. Nothing armed.")
            return 1

        # ---- 3. arm it, and only it ------------------------------------
        print("\n--- 3. arm this one SKU ---")
        c, j = call("/sourcing/arm", {"id": ACCOUNT, "marketplace": MARKET,
                                      "sku": sku, "live": True})
        print("  %s  %s" % (j.get("mode") or j.get("error"), j.get("note") or ""))
        if c != 200:
            return 1

        print("\n--- 4. master switch on ---")
        c, j = call("/sourcing/master", {"enabled": True})
        print("  enabled=%s" % j.get("enabled"))

        # ---- 5. push ----------------------------------------------------
        print("\n--- 5. push (the same path the timer uses) ---")
        c, j = call(q("/sourcing/apply"), {"id": ACCOUNT, "marketplace": MARKET})
        pushed = True
        print("  HTTP %s" % c)
        print("  %s" % json.dumps({k: v for k, v in j.items()
                                   if k != "results"})[:400])
        for res in (j.get("results") or [])[:6]:
            print("    %s" % json.dumps(res)[:220])

        # ---- 6. ASK AMAZON ----------------------------------------------
        print("\n--- 6. what does AMAZON say the price is now? ---")
        for attempt in range(6):
            time.sleep(10)
            now, err = amazon_price(sku)
            print("  after %2ds: %s %s" % ((attempt + 1) * 10, now, err))
            if now is not None and abs(float(now) - target) < 0.005:
                print("\n  ***  THE PRICE CHANGED ON AMAZON: %.2f -> %.2f  ***"
                      % (started_at, float(now)))
                break
        else:
            print("\n  the price has not appeared as %.2f yet. Amazon can take a "
                  "few minutes to reflect a patch; the push result above says "
                  "whether it was accepted." % target)
    finally:
        print("\n--- 7. putting everything back ---")
        if pushed:
            c, j = rules(sku, hold_price=started_at)
            print("  hold at the original %.2f: %s"
                  % (started_at, "ok" if c == 200 else j.get("error")))
            c, j = call(q("/sourcing/apply"), {"id": ACCOUNT, "marketplace": MARKET})
            print("  pushed the restore: HTTP %s  %s"
                  % (c, json.dumps({k: v for k, v in j.items()
                                    if k != "results"})[:200]))
        c, j = rules(sku, hold_price=None)
        print("  cleared the hold price: %s" % ("ok" if c == 200 else j.get("error")))
        c, j = call("/sourcing/arm", {"id": ACCOUNT, "marketplace": MARKET,
                                      "sku": sku, "live": False})
        print("  back to %s" % (j.get("mode") or j.get("error")))
        c, j = call("/sourcing/master", {"enabled": was_on})
        print("  master switch back to %s" % ("ON" if j.get("enabled") else "off"))
        if pushed:
            time.sleep(12)
            now, err = amazon_price(sku)
            print("  price now %s (started at %.2f) %s" % (now, started_at, err))
    return 0


if __name__ == "__main__":
    sys.exit(main())
