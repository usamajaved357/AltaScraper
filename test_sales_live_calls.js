/* THE PERIOD PILLS MUST NOT SEND US BACK TO AMAZON.
 *
 * THE REPORT: "you can actually switch through the time periods from 7d to 14d
 * to 90d to ytd etc, and see if the app switches and shows the right data in
 * milli seconds".
 *
 * It did not. Measured by driving the real screen on jack_uk: switching to 90
 * days took 9,543 ms, and year-to-date 4,574 ms -- while the endpoints those
 * clicks depend on answer in 50 to 130 ms.
 *
 * The time was not in the numbers. Three of this screen's endpoints do not read
 * our own database at all -- /sales/today, /sales/hourly and /sales/recent each
 * fetch orders LIVE from Amazon. All three were being sent _sQuery(), which
 * carries the period. Their windows are fixed and decided on the server (today;
 * today and yesterday; the last six days), so the period changed nothing about
 * the answer -- but it changed the URL, so every click fetched all three from
 * Amazon again. One 90-day click sent /sales/hourly twice, at +2.4s and +7.7s.
 *
 * That is also quota: Amazon allows roughly one Orders call a minute, and
 * spending it on period clicks is what produced "Live Sales could not be
 * loaded ... QuotaExceeded".
 *
 * After: 401 ms for 90 days, 580 ms for year-to-date. Same numbers.
 */
const fs = require("fs");

let fails = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(64),
              ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}
const sales = fs.readFileSync("D:/AltaScraper/static/js/sales.js", "utf8");
const routes = fs.readFileSync("D:/AltaScraper/routes/sales_routes.py", "utf8");

console.log("\n=== the live endpoints are named in ONE place ===");
check("there is a list of them", /const _S_LIVE = \[/.test(sales), true);
["/sales/today", "/sales/hourly", "/sales/recent"].forEach(function (u) {
  check("  " + u + " is on it",
        new RegExp('_S_LIVE = \\[[^\\]]*"' + u + '"').test(sales), true);
});
// Anything NOT on that list reads our own store and is cheap; putting one there
// by mistake would serve a stale answer for a minute.
check("and nothing local is on it", /_S_LIVE = \[[^\]]*series/.test(sales), false);

/* The source of one named function, brace-matched -- rather than a fixed number
 * of characters after its name, which runs off the end of the function and into
 * whatever happens to follow it. */
function fnBody(src, name) {
  const m = new RegExp("\\bfunction\\s+" + name + "\\s*\\(").exec(src);
  if (!m) return "";
  let i = src.indexOf("{", m.index + m[0].length - 1);
  if (i < 0) return "";
  for (let j = i, depth = 0; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}" && --depth === 0) return src.slice(i, j + 1);
  }
  return src.slice(i);
}

console.log("\n=== they are asked with the scope, not the period ===");
const scope = fnBody(sales, "_sScope");
check("a scope-only query builder exists", scope.length > 0, true);
check("  it carries the account", /account_id=/.test(scope), true);
check("  and the marketplace", /marketplace=/.test(scope), true);
check("  and NOT the period", /preset=/.test(scope), false);
check("  nor the granularity", /granularity=/.test(scope), false);

[["/sales/today", /"\/sales\/today\?"\+_sScope\(\)/],
 ["/sales/hourly", /"\/sales\/hourly\?" \+ _sScope\(\)/],
 ["/sales/recent", /"\/sales\/recent\?days=6&" \+ _sScope\(\)/]].forEach(function (t) {
  check("  " + t[0] + " uses it", t[1].test(sales), true);
});

console.log("\n=== and asked once, in the one place every request goes through ===");
check("two callers wanting the same thing share one request",
      /_sInflight\[u\]/.test(sales), true);
check("a live answer is reused for a short while",
      /_S_LIVE_TTL/.test(sales), true);
check("  for about a minute, which is Amazon's own refill rate",
      /_S_LIVE_TTL = 60000/.test(sales), true);
check("  and only when the call succeeded",
      /_sIsLive\(u\) && j && j\.ok/.test(sales), true);
check("  never for a write", /if\(!opts && _sIsLive\(u\)\)/.test(sales), true);
check("the in-flight entry is always cleared",
      /finally\{\s*delete _sInflight\[u\];/.test(sales), true);

console.log("\n=== the server still decides those windows itself ===");
// If the browser stopped sending the period and the server had been reading it,
// the windows would silently change. It does not: each computes its own.
check("hourly starts from the start of yesterday",
      /_ol\.day_start\(mkt, 1\)/.test(routes), true);
check("recent takes an explicit day count", /days=6/.test(sales), true);

console.log("\nFAILURES: %d", fails);
process.exit(fails ? 1 : 0);
