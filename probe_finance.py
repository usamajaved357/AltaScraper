"""probe_finance.py -- what Amazon ACTUALLY sends on each order line, VAT included.

CLAUDE.md Rule 4: do not guess. domain/finance_data.py keeps only the charge
whose ChargeType is "principal" and drops everything else on the item, including
anything Amazon calls Tax. Whether that is right depends entirely on what
Amazon sends -- if Principal is the VAT-INCLUSIVE price then profit is currently
overstated by the VAT, and if it is VAT-EXCLUSIVE then dropping Tax is correct.

Nothing but reading is done here. No database is written and nothing is sent to
Amazon beyond one page of financial events.

    python probe_finance.py jack_uk UK
    python probe_finance.py jack_uk UK --days 30
    python probe_finance.py jack_uk UK --raw        (dump one whole shipment)
"""
import json
import sys
import datetime as dt
from collections import defaultdict

sys.path.insert(0, r"D:\AltaScraper")


def _amt(o):
    try:
        return float((o or {}).get("CurrencyAmount") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    account_id, marketplace = args[0], args[1].upper()
    days = 14
    if "--days" in argv:
        try:
            days = int(argv[argv.index("--days") + 1])
        except Exception:
            pass

    cfg = json.load(open("config.json", encoding="utf-8"))
    acc = next((a for a in (cfg.get("accounts") or [])
                if str(a.get("id")) == account_id), None)
    if not acc:
        print("no account called %r. Known: %s" % (
            account_id, ", ".join(str(a.get("id")) for a in (cfg.get("accounts") or []))))
        return 1

    from domain import accounts as _acc
    from domain import finance_fetch as _ff

    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    print("account   : %s (%s)" % (account_id, marketplace))
    print("window    : %s .. %s\n" % (start, end))

    try:
        payload = _ff.raw_sample(marketplace, _acc.account_creds(acc),
                                 start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    except Exception as e:
        print("Amazon refused the request: %s" % str(e)[:400])
        return 1

    shipments = ((payload or {}).get("FinancialEvents") or {}).get("ShipmentEventList") or []
    print("shipment events in this page: %d" % len(shipments))
    if not shipments:
        print("\nNothing to read. Either this account has had no orders in the window,")
        print("or Finances has not been synced for it yet.")
        return 0

    charges = defaultdict(lambda: {"n": 0, "total": 0.0})
    fees = defaultdict(lambda: {"n": 0, "total": 0.0})
    promos = defaultdict(lambda: {"n": 0, "total": 0.0})
    lines = 0
    sample = None

    for sh in shipments:
        for item in (sh.get("ShipmentItemList") or []):
            lines += 1
            if sample is None:
                sample = item
            for ch in (item.get("ItemChargeList") or []):
                k = str(ch.get("ChargeType") or "?")
                charges[k]["n"] += 1
                charges[k]["total"] += _amt(ch.get("ChargeAmount"))
            for fe in (item.get("ItemFeeList") or []):
                k = str(fe.get("FeeType") or "?")
                fees[k]["n"] += 1
                fees[k]["total"] += _amt(fe.get("FeeAmount"))
            for pr in (item.get("PromotionList") or []):
                k = str(pr.get("PromotionType") or "?")
                promos[k]["n"] += 1
                promos[k]["total"] += _amt(pr.get("PromotionAmount"))

    print("item lines                  : %d\n" % lines)

    print("--- ItemChargeList: every ChargeType Amazon sent ---")
    kept = 0.0
    for k in sorted(charges):
        v = charges[k]
        keep = (k.lower() == "principal")
        if keep:
            kept = v["total"]
        print("  %-28s x%-4d %10.2f   %s" % (k, v["n"], v["total"],
              "<- KEPT as revenue" if keep else "<- DROPPED by the parser"))

    print("\n--- ItemFeeList ---")
    for k in sorted(fees):
        print("  %-28s x%-4d %10.2f" % (k, fees[k]["n"], fees[k]["total"]))
    if promos:
        print("\n--- PromotionList ---")
        for k in sorted(promos):
            print("  %-28s x%-4d %10.2f" % (k, promos[k]["n"], promos[k]["total"]))

    print("\n--- THE ANSWER ---")
    tax = sum(v["total"] for k, v in charges.items() if "tax" in k.lower()
              and "shipping" not in k.lower())
    if tax:
        ratio = (tax / kept) if kept else 0
        print("  Amazon sends Tax SEPARATELY from Principal (%.2f of tax against" % tax)
        print("  %.2f of principal = %.1f%%)." % (kept, ratio * 100))
        print("  => Principal is the VAT-EXCLUSIVE price, so revenue is already net of")
        print("     VAT and profit is NOT overstated by it. What IS missing: that tax")
        print("     is collected and owed onward, so it should be shown, not dropped.")
    else:
        print("  NO separate Tax line on the item charges.")
        print("  => Principal is whatever the buyer was charged. If you are")
        print("     VAT-registered and this is a UK/EU sale, that figure INCLUDES VAT,")
        print("     and every profit and contribution figure is overstated by it.")
    print("\n  Either way this is now measured rather than assumed. Paste this output")
    print("  back and the VAT handling gets built from it.")

    if "--raw" in argv and sample is not None:
        print("\n--- one whole item line, verbatim ---")
        print(json.dumps(sample, indent=2)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
