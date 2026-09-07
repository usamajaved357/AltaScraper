/* An edit to a live listing that never reached Amazon had nothing saying so.
 *
 *     "also see other buttons which seems like calling amazon but donot call
 *      amazon for a change"
 *
 * MEASURED across the whole app (probe_amazon_buttons.py): of 264 routes the
 * browser posts to, ELEVEN change anything on Amazon --
 *
 *     /handling/bulk_update  /stock/bulk_update  /listing/price/apply
 *     /listing/price/percent_apply  /sourcing/manual_price
 *     /listing/push_image  /listing/image_push  /optimize/push
 *     /variations/apply  /preview/enqueue  /preview/jobs
 *
 * -- and the one that misled hardest is the ordinary field edit. Typing a
 * Country of Origin or a Dangerous Goods value on a LIVE listing saved it here
 * and left Amazon untouched. Price and handling had push buttons; nothing else
 * did, so the same gesture reached Amazon for two fields and stopped at the app
 * for every other one.
 *
 * The comparison already existed -- lvVerdict has been marking fields "differs"
 * and the bar has been counting them -- so the fact was on screen with nothing
 * to do about it. This asserts there is now something to do about it, and that
 * it cannot do the wrong thing.
 */
const fs = require("fs");
const path = require("path");

const HERE = __dirname;
let fails = [];

function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(64) +
    (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }
function falsy(label, got) { check(label, !!got, false); }

const DA = fs.readFileSync(path.join(HERE, "static", "js", "drawer_attributes.js"), "utf8");
const CSS = fs.readFileSync(path.join(HERE, "static", "css", "drawer_attributes.css"), "utf8");

console.log("=== there is a way to send app values TO Amazon ===");
truthy("the push exists", DA.indexOf("async function lvPushChanges(") >= 0);
truthy("  and the bar offers it", DA.indexOf('onclick="lvPushChanges(') >= 0);
truthy("  named for what it does, not where it is",
  DA.indexOf("change(s) to Amazon") >= 0);
// It must not be mistaken for the button beside it, which pulls the other way.
truthy("  the opposite direction is still there",
  DA.indexOf("Fill ") >= 0 && DA.indexOf("lvFillEmpty") >= 0);
truthy("  and the two are styled apart", CSS.indexOf(".lv-push{") >= 0);

console.log("\n=== it sends only what differs, and never an emptiness ===");
truthy("the field list is its own function", DA.indexOf("function lvDiffFields(") >= 0);
const _df = DA.split("function lvDiffFields(")[1].split("\nasync function")[0];
truthy("  it asks the existing verdict (Rule 12)", _df.indexOf('lvVerdict(sku, k, a[k]) === "differs"') >= 0);
// A field empty here and set on Amazon belongs to the Fill button. Pushing an
// empty over Amazon's value would DELETE content nobody asked to remove.
truthy("  a blank on our side is never pushed",
  _df.indexOf('.trim() === "") return false') >= 0);
// Multi-value attributes (bullets, images) are not single scalars; the drawer
// has never compared them and pushing one as a scalar would flatten a list.
truthy("  and the multi-value attributes are left alone",
  _df.indexOf("(L.multi||{})[String(k).split(\".\")[0]]") >= 0);

console.log("\n=== nothing goes without being seen first ===");
const _pc = DA.split("async function lvPushChanges(")[1].split("\n/* The strip")[0];
truthy("it asks before sending", _pc.indexOf("uiConfirm(") >= 0);
// A patch is not undone by sending it again -- it is undone only by knowing the
// old value. So both sides are named, per field, before anything goes.
truthy("  showing Amazon's value and ours, per field",
  _pc.indexOf("Amazon's value → yours") >= 0);
truthy("  and saying it changes the live listing",
  _pc.indexOf("LIVE listing") >= 0);
truthy("  and how long Amazon takes", _pc.indexOf("5–30 minutes") >= 0);
check("  it stops when there is nothing to send",
  _pc.indexOf("Nothing to send") >= 0, true);

console.log("\n=== it reuses the gated push, and believes Amazon ===");
truthy("it posts to the existing patch route", _pc.indexOf('"/optimize/push"') >= 0);
truthy("  with the explicit confirm flag that route requires",
  _pc.indexOf("confirmed: true") >= 0);
// /optimize/push reads the account from `id`; acctBody stamps `account`.
// Getting this wrong sends the patch under whichever account the server has
// open -- the same class of fault as the handling-time write.
truthy("  and names the account in the key that route reads",
  _pc.indexOf("body.id = body.account") >= 0);
// ACCEPTED means Amazon RECEIVED the patch, not that it published it.
truthy("  an unreadable reply is not called success",
  _pc.indexOf("j.unknown") >= 0 && _pc.indexOf("Nothing here claims it worked") >= 0);
truthy("  and the comparison is re-read afterwards rather than assumed",
  _pc.indexOf("lvRefresh(sku)") >= 0);
// The success toast must sit INSIDE the j.ok branch. Written outside it, every
// push would report success including the refusals -- which is the fault
// /optimize/push's own comment describes ("a push that silently claims success
// is worse than one that fails").
const _okBranch = _pc.split("if(j && j.ok){")[1] || "";
truthy("  success is claimed only inside Amazon's own yes",
  _okBranch.split("}else")[0].indexOf("Amazon accepted") >= 0);
check("  and said exactly once", (_pc.match(/Amazon accepted/g) || []).length, 1);

console.log("\n=== the count says what it means ===");
truthy("the 'differ' count explains that editing does not send",
  DA.indexOf("Editing a field here does not send it") >= 0);

console.log("\nFAILURES: " + fails.length);
fails.forEach(f => console.log("  - " + f));
process.exit(fails.length ? 1 : 0);
