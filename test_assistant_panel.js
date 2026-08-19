/* The panel must show its sources, and must not do arithmetic.
 *
 * Two properties are worth pinning here, and neither is about layout.
 *
 * FIRST: it renders the trace. The answer is written by a model, and the one
 * thing that makes it checkable is knowing which screen each figure came from.
 * If the trace ever stops being drawn the panel still looks fine -- it just
 * quietly becomes something to be trusted rather than checked, which is the
 * failure that does not announce itself.
 *
 * SECOND: nothing in this file computes. It draws what /agent/ask returned. A
 * total worked out in the browser is a second place the figure exists, and the
 * two would drift (CLAUDE.md rule 12).
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }
function falsy(label, got){ check(label, !!got, false); }

const read = p => fs.readFileSync("D:/AltaScraper/" + p, "utf8");
const A = read("static/js/assistant.js");

console.log("== it draws the receipts ==");
truthy("the trace is rendered", A.includes("m.trace"));
truthy("  labelled so it can be acted on", A.includes("Read: "));
truthy("  and a screen that failed is shown as failed",
       A.includes("could not read"));
falsy("  the trace is not hidden behind a toggle",
      /display:\s*none[^]{0,80}trace/i.test(A));

console.log("\n== it computes nothing ==");
// A panel that adds up rows is a second place the figure lives.
for (const bad of ["reduce(", "* 100", "toFixed(", "/ rows.length"]) {
  check("no '" + bad + "' arithmetic in the panel",
        A.includes(bad), false);
}

console.log("\n== the account is named before the first answer ==");
truthy("it asks which account it is pinned to", A.includes("/agent/tools"));
truthy("  and shows it in the header", A.includes("asscope"));
truthy("  and re-reads it from every answer", A.includes("j.scope"));

console.log("\n== model text is escaped before it is drawn ==");
truthy("there is an escaper", A.includes("function asEsc"));
truthy("  handling angle brackets", A.includes("&lt;") && A.includes("&gt;"));
truthy("  and the user's own words go through it",
       A.includes("asEsc(m.text)"));
// Only bold and line breaks are honoured. A full markdown pass over model
// output turns a stray underscore in a SKU into italics mid-figure.
truthy("only bold is interpreted", A.includes("\\*\\*([^*]+)\\*\\*"));
falsy("  no italic rule", A.includes("_([^_]+)_"));

console.log("\n== it says what it cannot do ==");
truthy("the footer says it cannot change anything",
       A.includes("cannot change anything"));
truthy("  and that it answers for the open account only",
       A.includes("account you have open"));

console.log("\n== it is separate from the listing chat ==");
// Sharing a panel would mean one box that sometimes knows your sales.
falsy("it does not reuse the listing chat's ids",
      A.includes("chatwrap") || A.includes("chatbody")
      || A.includes("sendChat"));
const HTML = read("templates/dashboard.html");
truthy("the page loads it", HTML.includes("static/js/assistant.js"));
truthy("  and the existing Ask Claude box is untouched",
       HTML.includes('onclick="toggleChat()"'));

console.log("\n== the whole conversation is sent each time ==");
// The endpoint keeps nothing between calls, so what is on screen IS the
// history. Sending only the last question would lose every follow-up.
truthy("history is posted, not just the question",
       A.includes("AS.msgs.filter"));
truthy("  and error bubbles are not sent back as if they were answers",
       A.includes("m.role === 'user' || m.role === 'assistant'"));

console.log("\n" + fails + " failed");
process.exit(fails ? 1 : 0);
