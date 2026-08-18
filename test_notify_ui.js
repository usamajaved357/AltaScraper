// The Notifications screen — the outward-facing part must be obvious.
//
// Adding an address and starting to broadcast to it are two different
// decisions. A screen that conflates them means a mistyped webhook begins
// posting into somebody else's Slack channel immediately, and a webhook URL is
// a bearer credential: whoever holds it can post there forever.
//
// So this test is about restraint, not features:
//   * a new channel arrives switched OFF
//   * the full URL never reaches the browser
//   * nothing sends on load, or on a timer
//   * a failure is shown, not swallowed
const fs = require("fs");
const path = require("path");

const FAIL = [];
function check(label, ok) {
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL"));
  if (!ok) FAIL.push(label);
}
function read(p) { return fs.readFileSync(path.join(__dirname, p), "utf8"); }
function codeOnly(s) {
  return s.split("\n")
    .filter((l) => !l.trim().startsWith("//"))
    .map((l) => l.replace(/\s\/\/.*$/, ""))
    .join("\n");
}

const JS = codeOnly(read("static/js/notify.js"));
const PY = read("routes/notify_routes.py");
const DOM = read("domain/notify.py");
const HTML = read("templates/dashboard.html");
const SHELL = codeOnly(read("static/js/shell.js"));
const GUARD = read("auth/guard.py");

console.log("== a new channel arrives switched off ==");
// The whole safety posture. Adding an address and broadcasting to it are two
// decisions; conflating them means a typo starts sending straight away.
check("the add form does not send an enabled flag",
  JS.indexOf("ntfAdd") > 0 && !/enabled:\s*true/.test(JS));
check("  the module defaults enabled to false", /enabled=False/.test(DOM));
check("  and the screen says so in words",
  /switched off/i.test(JS) || /switched off/i.test(HTML));
check("  telling you to test before turning it on", /test first/i.test(JS + HTML));

console.log("== the webhook URL never reaches the browser ==");
// A Slack Incoming Webhook is a bearer credential. Rendering it puts it in
// screenshots, in shoulder-surfing range, and in any support thread about the
// screen.
check("the list endpoint does not ask for secrets",
  !/include_secret\s*=\s*True/.test(PY));
check("  the module redacts by default", /def redact\(/.test(DOM));
check("  and the screen draws the redacted field", /url_shown/.test(JS));
check("  never a raw url", !/c\.url\b/.test(JS));

console.log("== nothing sends by itself ==");
// Posting into somebody's Slack is outward-facing and cannot be taken back.
check("opening the screen only loads", /if\(sec==="notify"\)/.test(SHELL) &&
  /ntfLoad\(\)/.test(SHELL));
check("  and never sends", !/ntfSendNow\(\)/.test(SHELL));
check("sending is a button", /ntfSendNow/.test(JS));
check("  wired to an explicit endpoint", /\/notify\/send/.test(JS));
// If anything ever puts this on a timer, this is the check that should fail.
check("no timer calls the sender",
  !/setInterval[^)]*ntfSend/.test(JS) && !/setTimeout[^)]*ntfSend/.test(JS));

console.log("== an alert is not repeated until the channel is muted ==");
// These alerts are STATES: a rank off target is off target every time anything
// checks. Sent hourly, the reliable human response is to mute the channel — and
// then the real one is missed too.
check("sends carry a key", /key=key/.test(DOM) || /key=/.test(PY));
check("  the route keys on the SET of what is wrong", /key = "trackers:/.test(PY));
check("  the quiet window is explained on screen", /muted/i.test(JS));
check("  and a skip is recorded, not dropped", /SKIPPED/.test(DOM));

console.log("== a failure is shown ==");
// A notification system whose failures are invisible turns "nobody told me"
// into "the app told me it was fine".
check("the log is drawn", /notify\/log/.test(JS));
check("  including the failure reason", /e\.detail/.test(JS));
check("  and failures are styled as failures", /failed/.test(JS));

console.log("== truncation is said out loud ==");
// A list that stops at twenty without saying so reads as "there were twenty".
check("more than twenty says how many more", /and %d more/.test(PY));

console.log("== it is not a screen for everyone ==");
// A channel holds a credential and makes the app speak outside itself.
check("/notify needs manage_accounts",
  /\("\/notify",\s*"manage_accounts"\)/.test(GUARD));

console.log("== it is reachable ==");
check("there is a nav item", /data-sec="notify"/.test(HTML));
check("  and a panel", /id="sec_notify"/.test(HTML));
check("  and the script is loaded", /notify\.js\?v=/.test(HTML));
check("  and navTo knows about it", /"notify"/.test(SHELL));

console.log("\n" + FAIL.length + " failed");
FAIL.forEach((f) => console.log("  - " + f));
process.exit(FAIL.length ? 1 : 0);
