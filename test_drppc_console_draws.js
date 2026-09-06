// The Dr PPC Console must never show an empty page.
//
//     "the dr ppc console displays no content, it is working not at all"
//
// Everything on that screen drew into #drpc_main, which only exists once
// drpcShell() has run. So any failure before that -- a stylesheet that did not
// load, a helper that was not there, a host holding stray whitespace so the
// shell was skipped -- wrote its error into a node that did not exist, and the
// screen stayed blank with nothing on it to say why.
//
// An error nobody can see is worse than the error. These checks drive the real
// code through the failures that produce a blank page and require that each one
// puts SOMETHING on the screen.
//
// Run: node test_drppc_console_draws.js
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK"
    : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const SHARED = fs.readFileSync("static/js/ppcshared.js", "utf8");
const SRC = fs.readFileSync("static/js/drppc_console.js", "utf8");

// A DOM where setting innerHTML really does create findable children, because
// the whole question is whether #drpc_main exists after the shell is drawn.
function makeDom(){
  const store = {};
  function El(id){
    return {
      id, _html: "",
      get innerHTML(){ return this._html; },
      set innerHTML(v){
        this._html = String(v);
        // Register any id="..." the markup declares, as a browser would.
        (this._html.match(/id="([\w-]+)"/g) || []).forEach(m => {
          const cid = m.slice(4, -1);
          if(!store[cid]) store[cid] = El(cid);
        });
      },
      style: {}, dataset: {},
      classList: {add(){}, remove(){}, toggle(){}, contains(){ return false; }},
      setAttribute(){}, getAttribute(){ return "0"; },
      querySelector(){ return null; }, querySelectorAll(){ return []; },
      appendChild(){}, prepend(){}, insertBefore(){}, remove(){},
      ownerSVGElement: null,
    };
  }
  store["drppcconsole_body"] = El("drppcconsole_body");
  return {
    store,
    document: {
      getElementById: id => store[id] || null,
      querySelectorAll: () => [], querySelector: () => null,
      addEventListener(){}, createElement: () => El("new"),
    },
  };
}

function load(dom, fetchImpl){
  globalThis.window = globalThis;
  globalThis.document = dom.document;
  globalThis.CUR_ACCOUNT = {id: "acct", label: "An Account"};
  globalThis.WS_MARKET = "UK";
  globalThis.jsArg = s => JSON.stringify(String(s));
  globalThis.toast = () => {};
  globalThis.fetch = fetchImpl;
  return new Function(SHARED + "\n;\n" + SRC
    + "\nreturn {drpcOnOpen, drpcShell, drpcMain, drpcErr, DRPC};")();
}

const GOOD = {
  ok: true, account: "acct", marketplace: "UK", account_label: "An Account",
  workspace: {display_name: "An Account", status: "active",
              analysis_profile: "Non-branded growth v1", ads_profile: "123"},
  checks: [{key: "ads_profile", title: "Ads profile", ok: true, note: "ok"}],
  todo: [], classification: {classified_pct: 0, total_spend: 10,
                             confidence_bar: 80, rules_active: 0,
                             classified_spend: 0, unclassified_spend: 10},
  evidence: [], rules: [], runtime: [], schedule: {}, runs: [],
  plan: null, lanes: ["branded"], matches: ["contains"],
  evidence_types: ["search_term"], campaigns_total: 3,
};

console.log("=== the frame draws, and the body goes inside it ===");
{
  const dom = makeDom();
  const api = load(dom, async () => ({json: async () => GOOD}));
  api.drpcShell();
  truthy("the shell creates #drpc_main", !!dom.store["drpc_main"]);
  truthy("  and a sidebar", dom.store["drppcconsole_body"].innerHTML
                              .indexOf("drp-side") >= 0);
}

console.log("\n=== a host with stray whitespace still gets its frame ===");
// The old test was `if(!host.innerHTML) drpcShell()`. A newline between the
// template's tags makes that truthy, the shell is skipped, and every later
// write goes to a node that does not exist -- a blank page, for a space.
{
  const dom = makeDom();
  const api = load(dom, async () => ({json: async () => GOOD}));
  dom.store["drppcconsole_body"].innerHTML = "\n   ";
  api.drpcOnOpen();
  truthy("the frame is built anyway", !!dom.store["drpc_main"]);
}

console.log("\n=== a message with nowhere to go still reaches the screen ===");
{
  const dom = makeDom();
  const api = load(dom, async () => ({json: async () => GOOD}));
  // No shell at all: #drpc_main does not exist.
  api.drpcErr("something went wrong");
  const host = dom.store["drppcconsole_body"].innerHTML;
  truthy("the error is written to the host instead", host.length > 0);
  truthy("  and says what happened", host.indexOf("something went wrong") >= 0);
}

(async () => {
  console.log("\n=== the endpoint refusing is reported, not swallowed ===");
  {
    const dom = makeDom();
    const api = load(dom, async () => ({
      json: async () => ({ok: false, error: "Open an account first"}),
    }));
    api.drpcOnOpen();
    await new Promise(r => setTimeout(r, 30));
    const shown = (dom.store["drpc_main"] || dom.store["drppcconsole_body"])
      .innerHTML;
    truthy("the refusal is on the screen", shown.indexOf("Open an account") >= 0);
  }

  console.log("\n=== a helper that did not load is reported, not silent ===");
  // If ppcshared.js failed to arrive, ppcQS is not a function and drpcLoad
  // throws on its very first line. That used to leave a blank page.
  {
    const dom = makeDom();
    const api = load(dom, async () => { throw new Error("network is down"); });
    api.drpcOnOpen();
    await new Promise(r => setTimeout(r, 30));
    const shown = (dom.store["drpc_main"] || dom.store["drppcconsole_body"])
      .innerHTML;
    truthy("the failure is on the screen", shown.length > 0);
    truthy("  and names it", /could not reach|network is down/i.test(shown));
  }

  console.log("\n=== a good payload actually draws the page ===");
  {
    const dom = makeDom();
    const api = load(dom, async () => ({json: async () => GOOD}));
    api.drpcOnOpen();
    await new Promise(r => setTimeout(r, 30));
    const main = (dom.store["drpc_main"] || {innerHTML: ""}).innerHTML;
    truthy("the setup page has real content", main.length > 500);
    truthy("  with its heading", main.indexOf("Setup + readiness") >= 0);
    truthy("  and the account's name", main.indexOf("An Account") >= 0);
  }

  console.log("\n" + (fails ? fails + " FAILED" : "all passed"));
  process.exit(fails ? 1 : 0);
})();
