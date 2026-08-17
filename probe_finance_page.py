"""probe_finance_page.py -- audit the Finance screen against the stored money.

    python probe_finance_page.py

WHAT IT CHECKS, and why each one is a way this screen can lie
  1. Does the Finance screen's contribution agree with the Sales screen's profit
     for the same account and the same days? They read the same table. If they
     disagree, at least one of them is wrong and there is no way to tell which
     from either screen.
  2. Are funded coupons taken off? Amazon reports the FULL price and the discount
     separately, so a discount that is not subtracted is counted as money kept.
  3. Is the fee Amazon returns on a refund added back? Charging a referral fee on
     a sale that was returned understates exactly the products with returns.
  4. Do the footer totals equal the rows above them?
  5. Is VAT handled on one basis across the window, not summed from a period
     where only some days carried Amazon's tax lines?

Reads the database only -- no Amazon calls, so it is safe to run any time.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")


def main():
    import dashboard as D
    from data import db as _db
    from domain import contribution as _contrib
    from domain import sales_data as _sd

    conn = _db.get_db(D.CONFIG_PATH)
    pairs = conn.execute(
        "SELECT workspace_id, marketplace, COUNT(*) n, MIN(date) a, MAX(date) b "
        "FROM finance_daily GROUP BY workspace_id, marketplace "
        "ORDER BY n DESC").fetchall()
    if not pairs:
        print("no finance data stored at all -- nothing to audit")
        return

    cfg = D._cfg()
    problems = []

    for p in pairs:
        wsid, mkt = p["workspace_id"], p["marketplace"]
        start, end = p["a"], p["b"]
        rate = _sd.vat_rate_for(cfg, wsid)
        print("\n" + "=" * 70)
        print("%s / %s   %s to %s   (%d day-rows)" % (wsid, mkt, start, end, p["n"]))
        print("  VAT rate on file: %s" % ("not set" if rate is None else rate))

        rows, tot = _contrib.by_product(D.CONFIG_PATH, wsid, mkt, start, end,
                                        vat_rate=rate)
        if not rows:
            print("  no per-product rows in that window")
            continue

        cur = tot.get("currency") or ""
        print("  %d products   revenue %.2f %s   fees %.2f   refunds %.2f"
              % (tot["products"], tot["revenue"], cur, tot["fees"], tot["refunds"]))
        print("  promotions funded %.2f   refund fees returned %.2f   "
              "reimbursements %.2f"
              % (tot.get("promos") or 0, tot.get("refund_fees_returned") or 0,
                 tot.get("reimbursements") or 0))
        print("  VAT %s (%s)   net revenue %.2f   net proceeds %.2f"
              % (tot.get("vat"), tot.get("vat_basis") or "-",
                 tot.get("net_revenue") or 0, tot.get("net_proceeds") or 0))
        print("  contribution %s   margin %s%%"
              % (tot.get("contribution"), tot.get("margin_pct")))

        # ---- 1. the two screens must agree -------------------------------
        # The Sales screen's own answer for the same days, from the same table.
        # totals(), not a guessed daily(): the first version of this probe asked
        # for a function that does not exist and printed "nothing to compare
        # against", which is a check that silently does not run -- worse than no
        # check, because the output reads as if it passed.
        s_tot = _sd.totals(D.CONFIG_PATH, wsid, mkt, start, end, vat_rate=rate)
        if not s_tot:
            print("\n  FAIL  the Sales screen returned nothing for these days")
            problems.append("%s/%s: sales_data.totals returned nothing" % (wsid, mkt))
        else:
            s_np = round(float(s_tot.get("net_proceeds") or 0), 2)
            f_np = round(tot.get("net_proceeds") or 0, 2)
            # The account total row (asin='*') carries money that could not be
            # attributed to a product, so the per-product sum is legitimately
            # LOWER. Report the gap rather than calling it a failure.
            star = conn.execute(
                "SELECT SUM(COALESCE(principal,0)) pr, SUM(COALESCE(promos,0)) pm "
                "FROM finance_daily WHERE workspace_id=? AND marketplace=? "
                "  AND date>=? AND date<=? AND asin='*'",
                (wsid, mkt, start, end)).fetchone()
            print("\n  --- Finance screen vs Sales screen, same days ---")
            print("    Sales   net proceeds (all money): %10.2f" % s_np)
            print("    Finance net proceeds (per product): %8.2f" % f_np)
            print("    account-total principal %.2f  promos %.2f"
                  % (star["pr"] or 0, star["pm"] or 0))
            # THE TWO ARE NOT SUPPOSED TO BE EQUAL, and two earlier versions of
            # this check got that wrong in two different ways.
            #
            # The account row (asin='*') carries everything; the product rows
            # carry only what could be attributed to a SKU. So money moves BOTH
            # ways: charges with no SKU (the selling subscription) make the
            # products look better than the account, and sales whose SKU is not
            # in the catalogue snapshot make them look worse.
            #
            # The first version called any excess a failure and reported jack_uk
            # as broken -- that £50 was two £25 subscriptions. The second netted
            # off the unattributed FEES only and reported selvora as broken --
            # that gap is unattributed REVENUE, and much larger.
            #
            # So the check is an identity, per column: everything on the account
            # row must appear either against a product or in a disclosed
            # "unattributed" figure. Anything left over is a genuine fault.
            print("    difference %+.2f" % round(f_np - s_np, 2))
            acct = conn.execute(
                "SELECT SUM(COALESCE(principal,0)) principal, "
                "  SUM(COALESCE(referral_fees,0)+COALESCE(fba_fees,0)"
                "     +COALESCE(other_fees,0)) fees, "
                "  SUM(COALESCE(refunds,0)) refunds, "
                "  SUM(COALESCE(units,0)) units "
                "FROM finance_daily WHERE workspace_id=? AND marketplace=? "
                "  AND date>=? AND date<=? AND asin='*'",
                (wsid, mkt, start, end)).fetchone()
            print("\n    --- everything on the account is either on a product "
                  "or disclosed ---")
            checks = [
                ("revenue", acct["principal"],
                 sum(r["revenue"] for r in rows), tot.get("unattributed_revenue")),
                ("fees", acct["fees"],
                 sum(r["fees"] for r in rows), tot.get("unattributed_fees")),
                ("units", acct["units"],
                 sum(r["units"] for r in rows), tot.get("unattributed_units")),
            ]
            for name, on_account, on_products, disclosed in checks:
                left = round(float(on_account or 0) - float(on_products or 0)
                             - float(disclosed or 0), 2)
                print("      %-8s account %10.2f  products %10.2f  "
                      "disclosed %9.2f  unexplained %7.2f  %s"
                      % (name, float(on_account or 0), float(on_products or 0),
                         float(disclosed or 0), left,
                         "ok" if abs(left) < 0.02 else "FAIL"))
                if abs(left) >= 0.02:
                    problems.append("%s/%s: %.2f of %s is on the account row, not "
                                    "on any product, and not disclosed"
                                    % (wsid, mkt, left, name))

            # AND IT MUST BE ON THE SCREEN, not merely in the response. A figure
            # the code knows and the page never prints is not a disclosure.
            said = " ".join(n["text"] for n in _contrib.notes(rows, tot))
            for label, value, phrase in (
                    ("charges with no SKU", tot.get("unattributed_fees"),
                     "no single product"),
                    ("sales with no product", tot.get("unattributed_revenue"),
                     "NOT in the list")):
                if value:
                    ok = phrase in said
                    print("      %s (%.2f) is said on screen: %s"
                          % (label, float(value), "yes" if ok else "NO"))
                    if not ok:
                        problems.append("%s/%s: %.2f of %s is not disclosed on "
                                        "the screen" % (wsid, mkt, float(value),
                                                        label))

        # ---- 2. coupons are taken off ------------------------------------
        promos = tot.get("promos") or 0
        print("\n  --- funded discounts ---")
        if not promos:
            print("    no coupons or deals in this window")
        else:
            # Recompute the contribution WITHOUT the discount, to show what the
            # screen used to report and by how much it flattered.
            costed = tot["units"] and tot["cogs_units"] == tot["units"]
            if costed:
                was = round((tot["net_proceeds"] + promos) - tot["cogs"], 2)
                now = tot["contribution"]
                print("    %.2f %s funded" % (promos, cur))
                print("    contribution now %.2f, and %.2f if it were ignored"
                      % (now, was))
                print("    ok    the discount is taken off"
                      if now < was else "    FAIL  it is NOT taken off")
                if now >= was:
                    problems.append("%s/%s: funded discounts are not deducted"
                                    % (wsid, mkt))
            else:
                print("    %.2f %s funded (contribution withheld -- uncosted "
                      "units, so no before/after to show)" % (promos, cur))

        # ---- 3. the returned fee is added back ---------------------------
        rfr = tot.get("refund_fees_returned") or 0
        print("\n  --- refunds ---")
        print("    refunds %.2f on %d units, fee returned %.2f"
              % (tot["refunds"], tot.get("refund_units") or 0, rfr))
        if tot["refunds"] and not rfr:
            print("    note  refunds with no fee returned. Amazon does return the "
                  "referral fee on most refunds, so check a refund in Seller "
                  "Central if this window has many.")

        # ---- 4. the footer equals the rows -------------------------------
        print("\n  --- footer vs rows ---")
        for k in ("revenue", "fees", "refunds", "promos", "cogs", "net_proceeds",
                  "units"):
            summed = sum((r.get(k) or 0) for r in rows)
            summed = round(summed, 2) if isinstance(summed, float) else summed
            shown = tot.get(k)
            shown = round(shown, 2) if isinstance(shown, float) else shown
            same = abs((summed or 0) - (shown or 0)) < 0.02
            print("    %-14s rows %12s   footer %12s   %s"
                  % (k, summed, shown, "ok" if same else "MISMATCH"))
            if not same:
                problems.append("%s/%s: footer %s (%s) != the rows (%s)"
                                % (wsid, mkt, k, shown, summed))

        # ---- 5. VAT on one basis ----------------------------------------
        print("\n  --- VAT ---")
        bases = sorted({r.get("vat_basis") or "" for r in rows})
        print("    bases across products: %s" % bases)
        if len(bases) > 1:
            print("    note  more than one basis in one window. That is legitimate "
                  "when Amazon itemised tax on some products and not others, but "
                  "the total VAT is then only as good as the worst of them.")
        blank = [r["asin"] for r in rows if r.get("vat") is None]
        if blank:
            print("    %d products have no VAT figure at all: %s"
                  % (len(blank), ", ".join(blank[:6])))

        # ---- the products that matter ------------------------------------
        print("\n  --- biggest five by revenue ---")
        for r in rows[:5]:
            print("    %-12s rev %8.2f  fees %7.2f  promo %6.2f  cogs %7.2f  "
                  "contrib %8s  %s"
                  % (r["asin"], r["revenue"], r["fees"], r["promos"], r["cogs"],
                     r["contribution"], (r["title"] or "")[:28]))

    print("\n" + "=" * 70)
    if problems:
        print("PROBLEMS FOUND (%d):" % len(problems))
        for x in problems:
            print("  * %s" % x)
    else:
        print("no arithmetic problems found on the stored data")


if __name__ == "__main__":
    main()
