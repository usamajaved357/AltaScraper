/* static/js/drppc_console.js -- the Dr PPC(tm) Console.
 *
 * Three pages behind one sub-sidebar, built to DR-PPC-SETUP-BUILD-PROMPT.md,
 * DR-PPC-CURRENT-STATE-BUILD-PROMPT.md and DR-PPC-GOALS-STRATEGY-BUILD-PROMPT.md:
 *
 *     Setup + readiness    ten measured checks, the lane rules, the evidence
 *     Current state        the mirrored Amazon structure, campaign by campaign
 *     Goals + strategy     the plan, saved as immutable revisions
 *
 * The other four items in the spec's sidebar (Products, Performance, Analysis,
 * Activity) are drawn and marked "not built", not hidden. A sidebar that shows
 * only what exists makes a half-built console look finished.
 *
 * TWO THINGS THIS FILE WILL NOT DO.
 *
 * It never renders an unknown as nought. The server sends null for the four
 * entity counts nothing mirrors and for every child count it cannot derive, and
 * those draw as "—" with the reason on hover. "0 negative keywords" on an
 * account with 254 campaigns is a claim, and a false one.
 *
 * It never writes to Amazon, and nothing here can (Rule 8). Saving a plan,
 * activating one and adding a rule all write to this app's own tables; the
 * screen says so where a person might reasonably assume otherwise.
 *
 * The palette lives in static/css/drppc.css -- static/js may not name a colour
 * (test_one_palette.py).
 */

const DRPC = {
  page: "setup",
  setup: null, state: null, plan: null, perf: null, act: null,
  actKind: "all", actActor: "all",
  loading: false,
  // Current state's own filters.
  q: "", type: "All", st: "All", openCamp: null, detail: {},
  // The plan editor's working copy. Never written back to the server until Save
  // is pressed, and Save always makes a NEW revision.
  draft: null, vocab: null, history: [],
};

function _dEsc(s){
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* An unknown, with its reason. NOT a zero -- see the header. */
function drpcUnk(why){
  return '<span class="drp-unk"' + (why ? ' title="' + _dEsc(why) + '"' : '')
       + '>—</span>';
}

function drpcNum(v, why){
  return (v === null || v === undefined) ? drpcUnk(why)
       : Number(v).toLocaleString();
}

function drpcMoney(v){
  if(v === null || v === undefined) return drpcUnk();
  const cur = (typeof WS_CURRENCY !== "undefined" && WS_CURRENCY) ? WS_CURRENCY
            : ((typeof WS_MARKET !== "undefined" && WS_MARKET === "US")
               ? "USD" : "GBP");
  return ppcMoney(v, cur);
}

/* Ages a timestamp the way the sidebar foot wants it: "Synced 1h ago". */
function drpcAgo(ts){
  if(!ts) return "never synced";
  const t = Date.parse(String(ts).replace(" ", "T"));
  if(isNaN(t)) return _dEsc(ts);
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  if(mins < 60) return "Synced " + mins + "m ago";
  if(mins < 60 * 48) return "Synced " + Math.round(mins / 60) + "h ago";
  return "Synced " + Math.round(mins / 1440) + "d ago";
}

/* ---- the shell ------------------------------------------------------------ */

const DRPC_NAV = [
  ["setup",   "⚙",  "Setup + readiness", 1],
  ["state",   "📋", "Current state",     1],
  ["plan",    "🎯", "Goals + strategy",  1],
  ["products", "📦", "Products",         0],
  ["perf",    "📈", "Performance",       1],
  ["analysis", "🔬", "Analysis + proposals", 0],
  ["activity", "⚡", "Activity + decisions", 1],
];

/* A PAGE THAT SHOWS NOTHING AT ALL IS THE ONE FAILURE WITH NO DIAGNOSIS.
 *
 *     "the dr ppc console displays no content, it is working not at all"
 *
 * Everything here drew into #drpc_main, which only exists once drpcShell() has
 * run. So any failure BEFORE that -- and any failure of drpcShell itself --
 * wrote its error message into a node that was not there, and the screen stayed
 * empty with nothing in it to say why. An error you cannot see is worse than
 * the error.
 *
 * Three changes, all of them about never being silent:
 *   the shell is rebuilt whenever the main pane is missing, not only when the
 *     host looks empty -- a host holding stray whitespace used to skip it
 *   drpcMain falls back to the host itself when the main pane is absent
 *   every render is wrapped, so a fault in one panel reports itself instead of
 *     taking the page down with it
 */
function drpcOnOpen(){
  const host = document.getElementById("drppcconsole_body");
  if(!host) return;
  // Rebuilt when the frame is not actually there, rather than when the host
  // merely looks non-empty. Whitespace between the tags in the template is
  // enough to make innerHTML truthy, and that alone would have skipped the
  // shell for ever and left every later write with nowhere to go.
  if(!document.getElementById("drpc_main")) drpcShell();
  if(!document.getElementById("drpc_main")){
    // The frame itself could not be built. Say so where somebody will see it.
    // No hex fallback: static/js may not name a colour (test_one_palette.py),
    // and if the stylesheet really is missing the browser's default text colour
    // is readable anyway -- which is the case this message exists for.
    host.innerHTML = '<div style="padding:22px;color:var(--ppc-red)">'
      + 'The Dr PPC Console could not draw its frame. Reload the page; if it '
      + 'persists the console\'s stylesheet or script did not load.</div>';
    return;
  }
  drpcLoad();
}

function drpcShell(){
  const host = document.getElementById("drppcconsole_body");
  if(!host) return;
  const acct = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT
                && CUR_ACCOUNT.label) ? CUR_ACCOUNT.label : "no account";
  const mkt = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? WS_MARKET : "";
  host.innerHTML =
    '<div class="drp-shell">'
    + '<div class="drp-side">'
    +   '<div class="drp-side-head">'
    +     '<div class="drp-avatar">🤖</div>'
    +     '<div class="drp-side-title">Dr PPC™ Console</div>'
    +     '<div class="drp-side-acct">' + _dEsc(acct)
    +       (mkt ? " · " + _dEsc(mkt) : "") + '</div>'
    /* Deliberately not a button that does something. Manual apply describes a
     * policy -- a person may press apply -- and this app cannot write to Amazon
     * at all, so a live button here would promise what does not exist. */
    +     '<button class="drp-apply" disabled title="Policy, not a switch: a '
    +       'person may apply a change by hand. Nothing in this console writes '
    +       'to Amazon.">Manual apply ▸</button>'
    +   '</div>'
    +   '<div class="drp-nav" id="drpc_nav">' + drpcNav() + '</div>'
    +   '<div class="drp-side-foot" id="drpc_foot">'
    +     '<span class="drp-dot off"></span> reading…</div>'
    + '</div>'
    + '<div class="drp-main" id="drpc_main"></div>'
    + '</div>';
}

function drpcNav(){
  return DRPC_NAV.map(function(n){
    if(!n[3]){
      return '<a class="soon" title="In the spec\'s sidebar, not built yet. '
        + 'Shown so a half-built console does not look finished.">'
        + '<span class="ic">' + n[1] + '</span> ' + _dEsc(n[2]) + '</a>';
    }
    return '<a href="#" class="' + (DRPC.page === n[0] ? "on" : "") + '" '
      + 'onclick="return drpcGo(' + jsArg(n[0]) + ')">'
      + '<span class="ic">' + n[1] + '</span> ' + _dEsc(n[2]) + '</a>';
  }).join("");
}

function drpcGo(page){
  DRPC.page = page;
  const nav = document.getElementById("drpc_nav");
  if(nav) nav.innerHTML = drpcNav();
  drpcLoad();
  return false;
}

function drpcMain(html){
  const m = document.getElementById("drpc_main");
  if(m){ m.innerHTML = html; return; }
  // NOWHERE TO DRAW IS NOT A REASON TO DRAW NOWHERE. This used to return
  // quietly, so a message meant for the reader -- including every error message
  // -- disappeared. The host is always there; use it.
  const host = document.getElementById("drppcconsole_body");
  if(host) host.innerHTML = html;
}

function drpcFoot(ts, ok){
  const f = document.getElementById("drpc_foot");
  if(f) f.innerHTML = '<span class="drp-dot' + (ok ? "" : " off") + '"></span> '
    + _dEsc(drpcAgo(ts));
}

function drpcSpin(what){
  drpcMain('<div style="padding:22px;color:var(--ppc-muted)">'
    + '<span class="genspin"></span> ' + _dEsc(what) + '</div>');
}

function drpcErr(msg){
  drpcMain('<div style="padding:22px;color:var(--ppc-red)">' + _dEsc(msg)
    + '</div>');
}

async function drpcLoad(force){
  if(DRPC.loading) return;
  DRPC.loading = true;
  try{
    if(DRPC.page === "setup"){
      if(!DRPC.setup || force){
        drpcSpin("Measuring what this account is ready for…");
        const j = await (await fetch("/drppc/console/setup?" + ppcQS())).json();
        if(!j || !j.ok){ drpcErr((j && j.error) || "Could not read the console."); return; }
        DRPC.setup = j;
      }
      drpcSetup();
    }else if(DRPC.page === "state"){
      if(!DRPC.state || force){
        drpcSpin("Reading the mirrored Amazon structure…");
        const j = await (await fetch("/drppc/console/state?" + ppcQS())).json();
        if(!j || !j.ok){ drpcErr((j && j.error) || "Could not read the mirror."); return; }
        DRPC.state = j;
      }
      drpcState();
    }else if(DRPC.page === "perf"){
      if(!DRPC.perf || force){
        drpcSpin("Scoring the latest complete day against this account's own "
                 + "baseline…");
        const j = await (await fetch("/drppc/console/performance?"
                                     + ppcQS())).json();
        if(!j || !j.ok){
          drpcErr((j && j.error) || "Could not read performance."); return; }
        DRPC.perf = j;
      }
      drpcPerf();
    }else if(DRPC.page === "activity"){
      if(!DRPC.act || force){
        drpcSpin("Reading the ledger…");
        const j = await (await fetch("/drppc/console/activity?"
          + ppcQS({kind: DRPC.actKind, actor: DRPC.actActor}))).json();
        if(!j || !j.ok){
          drpcErr((j && j.error) || "Could not read the ledger."); return; }
        DRPC.act = j;
      }
      drpcActivity();
    }else{
      if(!DRPC.plan || force){
        drpcSpin("Reading the plan…");
        const j = await (await fetch("/drppc/console/plan?" + ppcQS())).json();
        if(!j || !j.ok){ drpcErr((j && j.error) || "Could not read the plan."); return; }
        DRPC.plan = j;
        DRPC.vocab = j.vocab;
        DRPC.history = j.history || [];
        DRPC.draft = drpcSeed(j.plan);
      }
      drpcPlan();
    }
  }catch(e){
    drpcErr("Could not reach the console: " + e);
  }finally{
    DRPC.loading = false;
  }
}

/* ==========================================================================
 * Page 1 -- Setup + readiness
 * ======================================================================= */

function drpcSetup(){
  const j = DRPC.setup, w = j.workspace || {}, cls = j.classification || {};
  drpcFoot((j.runtime || []).reduce(function(a, r){
    return (r.key === "mirror" && r.note && r.note.indexOf("last synced") === 0)
      ? r.note.slice(12) : a; }, ""), !!w.ads_profile);

  let h =
    '<div class="drp-head"><div>'
    + '<h1>Setup + readiness</h1>'
    + '<div class="sub">Make the ' + _dEsc(w.display_name || "")
    +   ' proof legible before enabling analysis or Amazon execution. '
    +   'Every check below is measured against what is actually stored.</div>'
    + '</div>'
    + '<button class="drp-ghost" onclick="drpcLoad(true)">🔄 Refresh evidence</button>'
    + '</div>';

  /* --- Section 1: the white workspace panel ------------------------------- */
  h += '<div class="drp-light">'
    + '<div class="drp-light-head"><div>'
    +   '<h3>Workspace configuration</h3>'
    +   '<div class="desc">These controls only determine eligibility. Saving '
    +     'them does not run analysis or touch Amazon.</div></div>'
    +   '<button class="drp-gold-btn" onclick="drpcSaveConfig()">'
    +     'Save configuration</button>'
    + '</div>'
    + '<div class="drp-fields">'
    /* Read-only on purpose: Settings -> Accounts owns the name and the
     * credentials, and a second editor for one field is how two screens start
     * disagreeing about it. */
    +   '<div class="drp-f"><label>Display name</label>'
    +     '<input value="' + _dEsc(w.display_name || "") + '" disabled '
    +     'title="Edited in Settings → Accounts, which owns it."></div>'
    +   '<div class="drp-f"><label>Workspace status</label>'
    +     '<input value="' + _dEsc(w.status || "") + '" disabled '
    +     'title="Derived: active once an Advertising login resolves a profile.">'
    +   '</div>'
    +   '<div class="drp-f"><label>Analysis profile</label>'
    +     '<select id="drpc_profile">'
    +     ["Non-branded growth v1", "Branded defence v1", "Balanced v1"]
    .map(function(p){
      return '<option' + (w.analysis_profile === p ? " selected" : "") + '>'
        + _dEsc(p) + '</option>'; }).join("")
    +     '</select></div>'
    + '</div>'
    + '<div class="drp-fields one" style="max-width:520px">'
    +   '<div class="drp-f"><label>Amazon ads profile</label>'
    +     '<input value="' + _dEsc(w.ads_profile || (w.ads_profile_why || "not connected"))
    +     '" disabled title="Edited in Settings → Accounts."></div>'
    + '</div>'
    + '<div class="drp-toggles">'
    +   drpcToggle("sched", "Scheduled observation", !!w.scheduled_observation,
        "Lets the nightly advertising sync mirror this account on its own. It "
        + "reads; it never writes to Amazon.")
    +   drpcToggle("legacy", "Exclude legacy automation", !!w.exclude_legacy,
        "Keeps this console independent of the older Dr PPC checker, which "
        + "stays exactly where it was under Advertising → Dr PPC.")
    +   drpcToggle("apply", "Manual apply eligible", true,
        "Eligibility only, and not a switch: nothing in this app can write to "
        + "Amazon, so a person applies any change by hand.", true)
    + '</div>'
    + '</div>';

  /* --- Section 2: readiness ---------------------------------------------- */
  h += '<div class="drp-h2">Proof readiness</div>'
    + '<div class="drp-h2-sub">Green means the evidence or configuration '
    +   'exists. It never means execution is automatically enabled.</div>'
    + '<div class="drp-panel"><div class="drp-checks">'
    + (j.checks || []).map(function(c){
        return '<div class="drp-check' + (c.highlight ? " hl" : "") + '">'
          + '<div class="drp-ring' + (c.ok ? " ok" : "") + '">✓</div>'
          + '<div><div class="ct">' + _dEsc(c.title) + '</div>'
          + '<div class="cn">' + _dEsc(c.note || "") + '</div></div></div>';
      }).join("")
    + '</div></div>';

  if((j.todo || []).length){
    h += '<div class="drp-panel" style="margin-top:10px">'
      + '<div class="drp-panel-title" style="font-size:16px;font-weight:700;'
      +   'margin-bottom:8px">Backend next steps</div>'
      + '<ul class="drp-steps" style="margin:0 0 10px 18px;padding:0">'
      + j.todo.map(function(t){ return '<li>' + _dEsc(t) + '</li>'; }).join("")
      + '</ul>'
      + '<button class="drp-orange-link" onclick="drpcGo(\'plan\')">'
      +   'Open the plan form instead</button></div>';
  }

  /* --- Section 3: plan readiness ----------------------------------------- */
  const p = j.plan;
  h += '<div class="drp-h2">Plan readiness</div>'
    + '<div class="drp-h2-sub">A plan is what a scheduled review measures '
    +   'against. Without an active one there is nothing to score.</div>';
  if(p && p.status === "active"){
    h += '<div class="drp-panel" style="display:flex;justify-content:space-between;'
      + 'align-items:center;gap:14px"><div>'
      + '<div style="font-size:14px;font-weight:700">Revision ' + _dEsc(p.revision)
      +   ' is active</div>'
      + '<div style="font-size:12px;color:var(--ppc-muted);margin-top:3px">'
      +   _dEsc(p.title || "untitled") + '</div></div>'
      + '<span class="drp-pill green">● Plan can be scored</span></div>';
  }else{
    h += '<div class="drp-panel" style="display:flex;justify-content:space-between;'
      + 'align-items:center;gap:14px"><div>'
      + '<div style="font-size:14px;font-weight:700">'
      +   (p ? "Revision " + _dEsc(p.revision) + " is still a draft"
             : "No active plan") + '</div>'
      + '<div style="font-size:12px;color:var(--ppc-muted);margin-top:3px">'
      +   'Saving writes a revision; activating is a separate act.</div></div>'
      + '<span class="drp-pill red">● Plan cannot be scored</span></div>'
      + '<div class="drp-note bad">'
      + '<b>No active Goals + Strategy + Budget plan</b>'
      + 'Nothing here can be measured against an intention nobody has recorded. '
      + '<span class="drp-mono">Closed by Plan · activate a revision.</span> '
      + '<button class="drp-cyan-link" onclick="drpcGo(\'plan\')">Open the plan'
      + '</button></div>';
  }

  /* --- Section 4: runtime ------------------------------------------------- */
  h += '<div class="drp-h2">Runtime checks</div>'
    + '<div class="drp-h2-sub">What the console can actually reach right '
    +   'now.</div>'
    + '<div class="drp-cards">'
    + (j.runtime || []).map(function(r){
        return '<div class="drp-card">'
          + '<span class="drp-pill ' + (r.ok ? "green" : "orange") + '">'
          +   (r.ok ? "✓ " : "! ") + _dEsc(r.badge) + '</span>'
          + '<div class="t">' + _dEsc(r.title) + '</div>'
          + '<div class="s">' + _dEsc(r.note || "") + '</div>'
          + (r.note2 ? '<div class="s2">' + _dEsc(r.note2) + '</div>' : "")
          + '</div>';
      }).join("")
    + '</div>'
    + '<div class="drp-note good">✓ This console is read-only against Amazon. '
    +   'Plans, rules and settings are written here; bids, budgets and campaign '
    +   'states are not touched.</div>';

  /* --- Section 5: schedule and runs --------------------------------------- */
  const s = j.schedule || {}, job = s.job || {};
  h += '<div class="drp-h2">Automation schedule</div>'
    + '<div class="drp-h2-sub">The mirror runs first; anything that reads it '
    +   'runs after, and only if it succeeded.</div>'
    + '<div class="drp-sched">'
    +   '<div class="c"><div class="k">Daily sync</div>'
    +     '<div style="margin:6px 0"><span class="drp-pill '
    +       (s.running ? "green" : "orange") + '">'
    +       (s.running ? "✓ Scheduled" : "! Not scheduled") + '</span></div>'
    +     '<div style="font-size:12px;color:var(--ppc-muted);line-height:1.5">'
    +       'Advertising sync · mirrors campaigns and spend<br>'
    +       (job.last_run ? "Last run " + _dEsc(job.last_run) + " ("
    +         _dEsc(job.status || "") + ")" : "Never run")
    +       + (s.why ? "<br>" + _dEsc(s.why) : "")
    +     '</div></div>'
    +   '<div class="arrow"><div class="a">→</div>'
    +     '<div class="l">only after<br>success</div></div>'
    +   '<div class="c"><div class="k">Chained</div>'
    +     '<div style="margin:6px 0"><span class="drp-pill">Reads the mirror</span>'
    +     '</div>'
    +     '<div style="font-size:12px;color:var(--ppc-muted);line-height:1.5">'
    +       'Classification and readiness are computed on demand from what the '
    +       'sync stored — there is no second cron, so they can never be stale '
    +       'relative to it.</div></div>'
    + '</div>';

  h += '<div class="drp-h2">Recent automated runs</div>'
    + '<div class="drp-h2-sub">' + (j.runs || []).length
    +   ' shown, failures included — a list of successes is how a job that has '
    +   'been erroring for a fortnight goes unnoticed.</div>';
  if(!(j.runs || []).length){
    h += '<div class="drp-empty">No sync has run for this account yet.</div>';
  }else{
    h += (j.runs || []).map(function(r){
      const okay = (r.status === "ok");
      let res = "";
      if(r.result && typeof r.result === "object"){
        res = Object.keys(r.result).slice(0, 6).map(function(k){
          const v = r.result[k];
          return _dEsc(k) + " " + _dEsc(
            (v && typeof v === "object") ? JSON.stringify(v).slice(0, 40) : v);
        }).join(" · ");
      }
      return '<div class="drp-panel" style="margin-bottom:6px">'
        + '<div style="display:flex;align-items:center;gap:12px">'
        +   '<span style="font-size:12px;font-weight:700;color:var(--ppc-muted);'
        +     'text-transform:uppercase">'
        +     _dEsc(String(r.job_type || "").replace("_", " ")) + '</span>'
        +   '<span style="font-size:14px;font-weight:700">'
        +     _dEsc(r.last_run || "") + '</span>'
        +   '<span style="margin-left:auto;font-size:12px;color:var('
        +     (okay ? "--ppc-green" : "--ppc-red") + ')">'
        +     (okay ? "✓ Success" : "✗ " + _dEsc(r.status || "failed"))
        +   '</span></div>'
        + (res ? '<div style="font-size:12px;color:var(--ppc-muted);margin-top:6px">'
                 + res + '</div>' : "")
        + (r.error ? '<div style="font-size:12px;color:var(--ppc-red);'
                     + 'margin-top:6px" class="drp-mono">'
                     + _dEsc(String(r.error).slice(0, 300)) + '</div>' : "")
        + '</div>';
    }).join("");
  }

  /* --- Section 6: lane classification ------------------------------------- */
  const pct = cls.classified_pct;
  h += '<div class="drp-h2">Lane classification</div>'
    + '<div class="drp-h2-sub">Which spend is branded, which is not, and by '
    +   'whose decision. A term no rule matches stays unclassified — defaulting '
    +   'it to non-branded would quietly move somebody else\'s spend into the '
    +   'lane that carries the growth mandate.</div>'
    + '<div class="drp-panel">'
    +   '<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">'
    +     '<span style="font-size:26px;font-weight:700">'
    +       (pct === null || pct === undefined ? drpcUnk(
             "There are no search terms stored, so there is nothing to classify "
             + "— which is not the same as classifying nothing.")
            : Number(pct).toFixed(2) + "%") + '</span>'
    +     '<span style="font-size:13px;color:var(--ppc-muted)">classified spend'
    +     '</span>'
    +     (pct !== null && pct !== undefined && pct < (cls.confidence_bar || 80)
       ? '<span class="drp-pill orange">■ Below the '
         + Number(cls.confidence_bar || 80) + '% confidence bar</span>' : "")
    +   '</div>'
    +   '<div class="drp-meter"><div class="fill" style="width:'
    +     Math.max(0, Math.min(100, Number(pct || 0))) + '%"></div>'
    +     '<div class="bar" style="left:' + Number(cls.confidence_bar || 80)
    +     '%" title="The bar this console holds itself to before it calls a '
    +     'lane split usable."></div></div>'
    +   '<div style="font-size:12px;color:var(--ppc-muted)">'
    +     drpcMoney(cls.classified_spend) + ' classified · '
    +     drpcMoney(cls.unclassified_spend) + ' unclassified · '
    +     drpcNum(cls.total_terms, "No search terms are stored for this account "
              + "and marketplace yet.") + ' search terms'
    +   '</div></div>';

  const exact = (j.rules || []).filter(function(r){
    return r.evidence === "campaign_id"; });
  h += '<div class="drp-grid" style="display:grid;grid-template-columns:1fr 1fr;'
    + 'gap:16px;margin-top:10px">'
    + '<div class="drp-panel">'
    +   '<div style="font-size:16px;font-weight:700">Add a reviewed rule</div>'
    +   '<div style="font-size:12px;color:var(--ppc-muted);margin:4px 0 12px">'
    +     'A rule is a decision somebody made, kept with the reason they made '
    +     'it. It classifies from the moment it is saved.</div>'
    +   drpcRuleForm(j)
    + '</div>'
    + '<div class="drp-panel">'
    +   '<div style="font-size:16px;font-weight:700">Reviewed campaign lanes'
    +   '</div>'
    +   '<div style="font-size:12px;color:var(--ppc-muted);margin:4px 0 12px">'
    +     'Campaigns assigned to a lane by exact id, rather than by what people '
    +     'typed.</div>'
    +   '<div style="font-size:26px;font-weight:700">' + exact.length + '</div>'
    +   '<div style="font-size:12px;color:var(--ppc-muted);margin-bottom:10px">'
    +     'of ' + drpcNum(j.campaigns_total) + ' mirrored campaigns</div>'
    +   (exact.length
       ? '<div class="drp-chips">' + exact.map(function(r){
           return '<span class="drp-chip"><span class="kw">'
             + _dEsc(r.pattern) + '</span><span class="mu">' + _dEsc(r.lane)
             + '</span></span>'; }).join("") + '</div>'
       : '<div class="drp-empty">No exact campaign assignments yet.</div>')
    + '</div></div>';

  /* --- Section 7: the rules table ----------------------------------------- */
  h += '<div class="drp-h2">Priority-ordered rules</div>'
    + '<div class="drp-h2-sub">Every match remains visible with its source and '
    +   'rationale. The lowest priority number wins; the rest are still '
    +   'listed against the term.</div>'
    + '<div class="drp-panel">' + drpcRulesTable(j.rules || []) + '</div>';

  /* --- Section 8: the evidence -------------------------------------------- */
  h += '<div class="drp-h2">Search-term evidence</div>'
    + '<div class="drp-h2-sub">Highest-spend terms from the stored Search Term '
    +   'Report, with the exact rule that classified each one.</div>'
    + '<div class="drp-panel">' + drpcEvidence(j.evidence || []) + '</div>';

  drpcMain(h);
}

function drpcToggle(id, title, on, desc, locked){
  return '<div class="drp-toggle"><div class="t"><span>' + _dEsc(title)
    + '</span><button class="drp-sw' + (on ? " on" : "") + '" id="drpc_sw_' + id
    + '"' + (locked ? ' disabled' : ' onclick="drpcFlip(' + jsArg(id) + ')"')
    + ' title="' + _dEsc(locked ? "Not a switch — see the note below." : "Click to change, then Save configuration.")
    + '"></button></div>'
    + '<div class="d">' + _dEsc(desc) + '</div></div>';
}

function drpcFlip(id){
  const el = document.getElementById("drpc_sw_" + id);
  if(el) el.classList.toggle("on");
}

async function drpcSaveConfig(){
  const prof = document.getElementById("drpc_profile");
  const sw = function(id){
    const el = document.getElementById("drpc_sw_" + id);
    return !!(el && el.classList.contains("on"));
  };
  try{
    const j = await (await fetch("/drppc/console/settings?" + ppcQS(), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        analysis_profile: prof ? prof.value : "",
        scheduled_observation: sw("sched"),
        exclude_legacy: sw("legacy")})})).json();
    if(typeof toast === "function")
      toast((j && j.ok) ? j.note : ("Not saved: " + ((j && j.error) || "unknown")));
    if(j && j.ok) drpcLoad(true);
  }catch(e){
    if(typeof toast === "function") toast("Could not save: " + e);
  }
}

function drpcRuleForm(j){
  const opt = function(list, sel){
    return (list || []).map(function(v){
      return '<option value="' + _dEsc(v) + '"' + (v === sel ? " selected" : "")
        + '>' + _dEsc(String(v).replace(/_/g, " ")) + '</option>'; }).join("");
  };
  return '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">'
    + '<div><label class="drp-flab" style="display:block;font-size:10px;'
    +   'font-weight:700;text-transform:uppercase;color:var(--ppc-muted);'
    +   'margin-bottom:4px">Lane</label>'
    +   '<select class="drp-in" id="drpc_r_lane" style="width:100%">'
    +   opt(j.lanes, "branded") + '</select></div>'
    + '<div><label style="display:block;font-size:10px;font-weight:700;'
    +   'text-transform:uppercase;color:var(--ppc-muted);margin-bottom:4px">'
    +   'Evidence type</label>'
    +   '<select class="drp-in" id="drpc_r_ev" style="width:100%">'
    +   opt(j.evidence_types, "search_term") + '</select></div>'
    + '<div><label style="display:block;font-size:10px;font-weight:700;'
    +   'text-transform:uppercase;color:var(--ppc-muted);margin-bottom:4px">'
    +   'Match</label>'
    +   '<select class="drp-in" id="drpc_r_match" style="width:100%">'
    +   opt(j.matches, "contains") + '</select></div>'
    + '<div><label style="display:block;font-size:10px;font-weight:700;'
    +   'text-transform:uppercase;color:var(--ppc-muted);margin-bottom:4px">'
    +   'Priority</label>'
    +   '<input class="drp-in" id="drpc_r_pri" type="number" value="100" '
    +   'style="width:100%" title="Lowest number wins when two rules match."></div>'
    + '</div>'
    + '<div style="margin-top:10px"><label style="display:block;font-size:10px;'
    +   'font-weight:700;text-transform:uppercase;color:var(--ppc-muted);'
    +   'margin-bottom:4px">Pattern</label>'
    +   '<input class="drp-in" id="drpc_r_pat" style="width:100%" '
    +   'placeholder="e.g. a brand word, or an exact campaign id"></div>'
    + '<div style="margin-top:10px"><label style="display:block;font-size:10px;'
    +   'font-weight:700;text-transform:uppercase;color:var(--ppc-muted);'
    +   'margin-bottom:4px">Rationale</label>'
    +   '<textarea class="drp-in" id="drpc_r_why" rows="2" style="width:100%" '
    +   'placeholder="Why this belongs in that lane."></textarea></div>'
    + '<div style="text-align:right;margin-top:10px">'
    +   '<button class="drp-ghost" onclick="drpcAddRule()">Save reviewed rule'
    +   '</button></div>';
}

async function drpcAddRule(){
  const g = function(id){
    const el = document.getElementById(id); return el ? el.value : ""; };
  const pat = String(g("drpc_r_pat") || "").trim();
  if(!pat){
    if(typeof toast === "function") toast("Give the rule a pattern to match on.");
    return;
  }
  try{
    const j = await (await fetch("/drppc/console/rule?" + ppcQS(), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        lane: g("drpc_r_lane"), evidence: g("drpc_r_ev"),
        match_type: g("drpc_r_match"), pattern: pat,
        priority: g("drpc_r_pri"), rationale: g("drpc_r_why")})})).json();
    if(!j || !j.ok){
      if(typeof toast === "function")
        toast("Not saved: " + ((j && j.error) || "unknown"));
      return;
    }
    if(typeof toast === "function") toast(j.note);
    drpcLoad(true);
  }catch(e){
    if(typeof toast === "function") toast("Could not save that rule: " + e);
  }
}

async function drpcDelRule(id){
  if(typeof uiConfirm === "function"){
    const ok = await uiConfirm("Delete this rule? Terms it was classifying go "
      + "back to unclassified, which will move the coverage figure.");
    if(!ok) return;
  }
  try{
    const j = await (await fetch("/drppc/console/rule/delete?" + ppcQS(), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id: id})})).json();
    if(typeof toast === "function")
      toast((j && j.ok) ? "Rule deleted."
                        : ("Not deleted: " + ((j && j.error) || "unknown")));
    if(j && j.ok) drpcLoad(true);
  }catch(e){
    if(typeof toast === "function") toast("Could not delete: " + e);
  }
}

function drpcRulesTable(rules){
  if(!rules.length)
    return '<div class="drp-empty">No rules configured yet. Until one exists, '
      + 'every term is unclassified — which the coverage figure above reports '
      + 'honestly rather than hiding.</div>';
  return '<table class="drp-table"><thead><tr>'
    + ['Priority', 'Lane', 'Evidence', 'Match', 'Pattern / id', 'Source',
       'Rationale', ''].map(function(c, i){
        return '<th' + (i === 0 || i > 5 ? '' : ' style="text-align:left"') + '>'
          + _dEsc(c) + '</th>'; }).join("")
    + '</tr></thead><tbody>'
    + rules.map(function(r){
        return '<tr><td>' + _dEsc(r.priority) + '</td>'
          + '<td style="text-align:left">' + _dEsc(r.lane) + '</td>'
          + '<td style="text-align:left">'
          +   _dEsc(String(r.evidence || "").replace(/_/g, " ")) + '</td>'
          + '<td style="text-align:left">' + _dEsc(r.match_type) + '</td>'
          + '<td style="text-align:left" class="mono">' + _dEsc(r.pattern) + '</td>'
          + '<td style="text-align:left">' + _dEsc(r.source || "reviewed") + '</td>'
          + '<td style="text-align:left;font-size:12px;color:var(--ppc-muted)">'
          +   _dEsc(r.rationale || "") + '</td>'
          + '<td><button class="drp-del" onclick="drpcDelRule(' + Number(r.id)
          +   ')" title="Delete this rule">🗑</button></td></tr>';
      }).join("")
    + '</tbody></table>';
}

function drpcEvidence(rows){
  if(!rows.length)
    return '<div class="drp-empty">No search terms stored for this account and '
      + 'marketplace. Pull or upload a Search Term Report and this fills.</div>';
  return '<table class="drp-table"><thead><tr>'
    + '<th>Search term</th><th style="text-align:left">Lane</th>'
    + '<th style="text-align:left">Matched rule</th>'
    + '<th>Spend</th><th>Ad sales</th><th>Orders</th></tr></thead><tbody>'
    + rows.map(function(r){
        return '<tr><td class="mono">' + _dEsc(r.search_term) + '</td>'
          + '<td style="text-align:left' + (r.lane === "unclassified"
              ? ';color:var(--ppc-muted)' : '') + '">'
          +   _dEsc(String(r.lane).replace(/_/g, " ")) + '</td>'
          + '<td style="text-align:left;font-size:12px;color:var(--ppc-dim)">'
          +   (r.matched_rule
               ? _dEsc(r.matched_pattern)
                 + (r.other_matches && r.other_matches.length
                    ? ' <span title="Also matched by ' + r.other_matches.length
                      + ' other rule(s); the lowest priority number won.">(+'
                      + r.other_matches.length + ')</span>' : "")
               : "No reviewed rule") + '</td>'
          + '<td>' + drpcMoney(r.spend) + '</td>'
          + '<td>' + drpcMoney(r.sales) + '</td>'
          + '<td>' + drpcNum(r.orders) + '</td></tr>';
      }).join("")
    + '</tbody></table>';
}

/* ==========================================================================
 * Page 2 -- Current state
 * ======================================================================= */

const DRPC_COUNTS = [
  ["campaigns", "Campaigns"], ["ad_groups", "Ad groups"],
  ["product_ads", "Product ads"], ["keywords", "Keywords"],
  ["targets", "Targets"], ["negative_keywords", "Neg. keywords"],
  ["negative_targets", "Neg. targets"], ["portfolios", "Portfolios"],
];

function drpcState(){
  const j = DRPC.state, c = j.counts || {}, nm = j.not_mirrored || {};
  drpcFoot(j.last_synced, !!j.last_synced);

  let h = '<div class="drp-head"><div>'
    + '<h1>Current state</h1>'
    + '<div class="sub">The Amazon Ads structure as this app has it mirrored. '
    +   'Refreshed by the advertising sync — this page reads what that stored '
    +   'and never calls Amazon itself.</div>'
    + '<div class="sub" style="margin-top:6px">'
    +   (j.last_synced ? "Last synced " + _dEsc(j.last_synced)
                       : "Nothing mirrored for this account yet.") + '</div>'
    + '</div>'
    + '<button class="drp-ghost" onclick="drpcLoad(true)">🔄 Reread mirror'
    + '</button></div>';

  h += '<div class="drp-stats">'
    + DRPC_COUNTS.map(function(k){
        const v = c[k[0]];
        const why = nm[k[0]];
        return '<div class="drp-stat"' + (why ? ' title="' + _dEsc(why) + '"' : '')
          + '><div class="n' + (v === null || v === undefined ? " unk" : "")
          + '">' + (v === null || v === undefined ? "—"
                    : Number(v).toLocaleString()) + '</div>'
          + '<div class="l">' + _dEsc(k[1]) + '</div></div>';
      }).join("")
    + '</div>'
    + '<div class="drp-note">' + _dEsc(j.why || "") + '</div>';

  /* filters */
  const rows = drpcStateRows();
  h += '<div class="drp-filters" style="margin-top:18px">'
    + '<input class="drp-in" style="flex:1" placeholder="Search campaigns by '
    +   'name…" value="' + _dEsc(DRPC.q) + '" oninput="drpcFilter(\'q\',this.value)">'
    + '<select class="drp-in" onchange="drpcFilter(\'type\',this.value)">'
    +   ["All", "SP", "SB", "SD"].map(function(t){
        return '<option' + (DRPC.type === t ? " selected" : "") + '>' + t
          + '</option>'; }).join("") + '</select>'
    + '<select class="drp-in" onchange="drpcFilter(\'st\',this.value)">'
    +   ["All", "enabled", "paused", "archived"].map(function(t){
        return '<option' + (DRPC.st === t ? " selected" : "") + '>' + t
          + '</option>'; }).join("") + '</select>'
    + '<span class="drp-count">' + rows.length + ' of '
    +   (j.campaigns || []).length + ' campaigns</span>'
    + '</div>';

  h += '<div class="drp-panel" id="drpc_camps">' + drpcCampTable(rows) + '</div>';
  drpcMain(h);
}

/* SPONSORED_PRODUCTS -> SP. Amazon's own spelling, shortened for the badge;
 * "SPONSORED_BRANDS" does not contain the letters "SB", so a substring test
 * would filter every SB campaign out of an SB filter and look like the account
 * has none. */
function drpcAdType(v){
  const s = String(v || "").toUpperCase();
  if(s.indexOf("PRODUCT") >= 0) return "SP";
  if(s.indexOf("BRAND") >= 0) return "SB";
  if(s.indexOf("DISPLAY") >= 0) return "SD";
  return s ? s.slice(0, 2) : "";
}

function drpcStateRows(){
  const q = DRPC.q.toLowerCase();
  return ((DRPC.state && DRPC.state.campaigns) || []).filter(function(r){
    if(q && String(r.name || "").toLowerCase().indexOf(q) < 0) return false;
    if(DRPC.type !== "All" && drpcAdType(r.ad_product) !== DRPC.type)
      return false;
    if(DRPC.st !== "All"
       && String(r.status || "").toLowerCase() !== DRPC.st) return false;
    return true;
  });
}

function drpcFilter(k, v){
  DRPC[k] = v;
  drpcState();
}

function drpcCampTable(rows){
  if(!rows.length)
    return '<div class="drp-empty">No campaigns match. The mirror holds '
      + drpcNum((DRPC.state.campaigns || []).length) + ' for this account.</div>';
  const unkWhy = "Not stored: nothing in this app mirrors this entity, so a "
    + "number here would be a guess and a zero would be a false claim.";
  let h = '<table class="drp-table"><thead><tr>'
    + '<th>Campaign</th><th style="text-align:left">Type</th>'
    + '<th style="text-align:left">State</th><th>Daily budget</th>'
    + '<th>Spend</th><th>Ad groups</th><th>Keywords</th><th>Targets</th>'
    + '<th>Product ads</th><th>Negatives</th><th>Last seen</th>'
    + '</tr></thead><tbody>';
  rows.slice(0, 500).forEach(function(r){
    const t = drpcAdType(r.ad_product);
    const st = String(r.status || "").toLowerCase();
    const open = (DRPC.openCamp === r.name);
    h += '<tr class="row" onclick="drpcOpenCamp(' + jsArg(r.name) + ')">'
      + '<td title="' + _dEsc(r.name || "") + '">' + (open ? "▾ " : "▸ ")
      +   _dEsc(r.name || "(unnamed)") + '</td>'
      + '<td style="text-align:left">' + (t ? '<span class="drp-tag '
      +   _dEsc(t.toLowerCase()) + '">' + _dEsc(t) + '</span>'
      :   drpcUnk("The mirror has no ad product for this campaign.")) + '</td>'
      + '<td style="text-align:left">' + (st ? '<span class="drp-tag '
      +   _dEsc(st) + '">' + _dEsc(st.toUpperCase()) + '</span>' : drpcUnk())
      + '</td>'
      + '<td>' + drpcMoney(r.budget) + '</td>'
      + '<td>' + drpcMoney(r.spend) + '</td>'
      + '<td>' + drpcNum(r.ad_groups, "No search-term report row names an ad "
      +   "group for this campaign, so the count is unknown rather than nought.")
      + '</td>'
      + '<td>' + drpcNum(r.keywords, "Counted from the Search Term Report: "
      +   "keywords that actually fired. A keyword with no impressions is not "
      +   "in it.") + '</td>'
      + '<td>' + drpcUnk(unkWhy) + '</td>'
      + '<td>' + drpcUnk(unkWhy) + '</td>'
      + '<td>' + drpcUnk(unkWhy) + '</td>'
      + '<td style="font-size:12px;color:var(--ppc-muted)">'
      +   _dEsc(r.last_seen || "") + '</td></tr>';
    if(open){
      h += '<tr><td colspan="11" style="padding:0">'
        + '<div id="drpc_detail">' + drpcDetail(r) + '</div></td></tr>';
    }
  });
  h += '</tbody></table>';
  if(rows.length > 500){
    h += '<div style="font-size:12px;color:var(--ppc-muted);margin-top:9px">'
      + 'Drawing the first 500 of ' + rows.length + '.</div>';
  }
  return h;
}

async function drpcOpenCamp(name){
  DRPC.openCamp = (DRPC.openCamp === name) ? null : name;
  drpcState();
  if(!DRPC.openCamp || DRPC.detail[name]) return;
  try{
    const j = await (await fetch("/drppc/console/state/campaign?"
      + ppcQS({campaign: name}))).json();
    if(j && j.ok){
      DRPC.detail[name] = j;
      const el = document.getElementById("drpc_detail");
      if(el && DRPC.openCamp === name){
        const row = ((DRPC.state && DRPC.state.campaigns) || []).filter(
          function(r){ return r.name === name; })[0] || {name: name};
        el.innerHTML = drpcDetail(row);
      }
    }
  }catch(e){ /* the row stays open showing the notice below */ }
}

function drpcDetail(r){
  const d = DRPC.detail[r.name];
  let h = '<div class="drp-detail">';

  /* BIDDING -- only what is stored. The mirror keeps budget and status; it has
   * never kept a bidding strategy or a placement adjustment, so the section
   * says that instead of drawing plausible chips. */
  h += '<h4>BIDDING</h4><div class="drp-chips">'
    + '<span class="drp-chip"><span class="mu">Daily budget</span>'
    +   '<span class="kw">' + drpcMoney(r.budget) + '</span></span>'
    + '<span class="drp-chip"><span class="mu">Status</span>'
    +   '<span class="kw">' + _dEsc(String(r.status || "unknown").toUpperCase())
    +   '</span></span>'
    + '<span class="drp-chip"><span class="mu">Spend in window</span>'
    +   '<span class="kw">' + drpcMoney(r.spend) + '</span></span>'
    + '</div>'
    + '<div class="drp-note">Bidding strategy and placement adjustments are '
    +   'not stored by this app — the advertising sync keeps a campaign\'s '
    +   'budget, status and daily spend. They are left out rather than '
    +   'guessed.</div>';

  if(!d){
    h += '<div class="drp-empty" style="margin-top:12px">'
      + '<span class="genspin"></span> Reading this campaign…</div></div>';
    return h;
  }

  if(!(d.ad_groups || []).length){
    h += '<div class="drp-empty" style="margin-top:12px">No search-term rows '
      + 'for this campaign, so there is nothing to show underneath it. That '
      + 'means nothing fired in the report\'s window — not that the campaign '
      + 'is empty.</div></div>';
    return h;
  }

  (d.ad_groups || []).forEach(function(g){
    h += '<div class="drp-group"><div class="gn">' + _dEsc(g.name) + '</div>'
      + '<h4 style="margin-top:10px">KEYWORDS (' + (g.keywords || []).length
      + ')</h4><div class="drp-chips">'
      + (g.keywords || []).map(function(k){
          return '<span class="drp-chip"><span class="kw">'
            + _dEsc(k.keyword || "(no keyword)") + '</span>'
            + '<span class="mu">' + _dEsc(k.match_type || "") + '</span>'
            + '<span class="mu">' + drpcMoney(k.spend) + '</span>'
            + '<span class="mu">' + drpcNum(k.clicks) + ' clicks</span>'
            + '</span>'; }).join("")
      + '</div></div>';
  });
  h += '<div class="drp-note">' + _dEsc(d.why || "") + '</div>';
  return h + '</div>';
}

/* ==========================================================================
 * Page 4 -- Performance
 *
 * Built to DR-PPC-PERFORMANCE-BUILD-PROMPT.md, with two of its assumptions
 * corrected against what this account actually has rather than drawn anyway:
 *
 *   the spec asks for a 60-day baseline -- there are 28 days of advertising
 *   history, so the page scores against what exists and PRINTS how long it is
 *
 *   the spec's "Today so far" bar wants today's spend and clicks -- Amazon's
 *   advertising feed runs two days behind, so there is no such figure and the
 *   bar says so instead of showing nought beside the word "spend"
 * ======================================================================= */

const DRPC_STATUS = {
  in_line:  ["ok",   "✓ in line with baseline"],
  drifting: ["warn", "⚠ drifting from baseline"],
  off:      ["bad",  "✗ off baseline"],
  unscored: ["dim",  "— not scored"],
  unknown:  ["dim",  "— not measured"],
};

function drpcVal(v, kind){
  if(v === null || v === undefined) return drpcUnk();
  if(kind === "money") return drpcMoney(v);
  if(kind === "points") return Number(v).toFixed(1) + "%";
  return Number(v).toLocaleString();
}

/* The delta beside the value. POINTS for a ratio, money for money -- "TACOS is
 * 2% above expected" and "TACOS is 2 points above expected" are different
 * statements and only one of them is what moved. */
function drpcDelta(v, kind){
  if(v === null || v === undefined)
    return '<span class="drp-unk" title="No expected value, so there is '
         + 'nothing to compare this against.">—</span>';
  const n = Number(v);
  const sign = n > 0 ? "+" : (n < 0 ? "−" : "");
  const mag = Math.abs(n);
  const txt = (kind === "money") ? drpcMoney(mag)
            : (kind === "points") ? mag.toFixed(1) + "pts"
            : mag.toLocaleString();
  return sign + txt + " vs expected";
}

function drpcPerf(){
  const j = DRPC.perf, s = j.scorecard || {}, t = j.today || {},
        tr = j.trend || {}, b = s.baseline || {};
  drpcFoot(s.day, !!s.has_data);

  let h = '<div class="drp-head"><div>'
    + '<h1>Performance</h1>'
    + '<div class="sub">How the account is doing right now. The latest '
    +   'complete reporting day is the verdict; today is a partial pulse '
    +   'only.</div></div>'
    + (s.day ? '<span class="drp-pill cyan">Latest complete day: '
               + _dEsc(s.day) + '</span>' : "")
    + '</div>';

  if(!s.has_data){
    h += '<div class="drp-note bad"><b>Nothing to score</b>'
      + _dEsc(s.why || "") + '</div>';
    drpcMain(h);
    return;
  }

  /* --- 1: the six cards -------------------------------------------------- */
  h += '<div class="drp-h2">Latest complete day · ' + _dEsc(s.day) + '</div>'
    + '<div class="drp-h2-sub">Scored against this account\'s own baseline, '
    +   _dEsc(b.start || "") + ' to ' + _dEsc(b.end || "") + ' — '
    +   '<b>' + drpcNum(b.days_with_data) + ' advertising days found</b> of the '
    +   drpcNum(b.asked_days) + ' asked for. ' + _dEsc(s.why || "") + '</div>'
    + '<div class="drp-perf-cards">'
    + (s.cards || []).map(function(c){
        const st = DRPC_STATUS[c.status] || DRPC_STATUS.unknown;
        return '<div class="drp-perf-card ' + _dEsc(c.key) + '">'
          + '<div class="k">' + _dEsc(c.label) + '</div>'
          + '<div class="v">' + drpcVal(c.value, c.kind) + '</div>'
          + '<div class="d">' + drpcDelta(c.delta, c.kind) + '</div>'
          + '<span class="drp-state ' + st[0] + '" title="'
          +   _dEsc(c.why || "") + '">' + st[1] + '</span>'
          + '<div class="n">' + drpcNum(c.baseline_n) + ' baseline days'
          + (c.baseline_unmeasurable
             ? ' · <span title="Days that had advertising but could not produce '
               + 'this figure — a day with spend and no sales has no ACOS.">'
               + c.baseline_unmeasurable + ' unmeasurable</span>' : "")
          + '</div></div>';
      }).join("")
    + '</div>'
    + '<div class="drp-note">' + _dEsc((j.rule || {}).text || "") + '</div>';

  /* --- 2: today ---------------------------------------------------------- */
  h += '<div class="drp-panel" style="margin-top:16px">'
    + '<div style="display:flex;gap:16px;align-items:baseline;flex-wrap:wrap">'
    +   '<b style="font-size:14px">Today so far · ' + _dEsc(t.date) + '</b>'
    +   '<span style="font-size:13px;color:var(--ppc-muted)">total sales '
    +     drpcMoney(t.total_sales) + '</span>'
    +   '<span style="font-size:13px;color:var(--ppc-muted)">ad spend '
    +     (t.has_ads ? drpcMoney(t.spend)
                     : drpcUnk("Amazon has not reported today's advertising."))
    +   '</span>'
    +   '<span style="font-size:13px;color:var(--ppc-muted)">clicks '
    +     (t.has_ads ? drpcNum(t.clicks) : drpcUnk()) + '</span>'
    + '</div>'
    + (t.why ? '<div class="drp-note" style="margin-top:8px">' + _dEsc(t.why)
               + '</div>' : "")
    + '</div>';

  /* --- 3: lanes ---------------------------------------------------------- */
  const ln = j.lanes || {};
  h += '<div class="drp-h2">Strategy lanes</div>'
    + '<div class="drp-h2-sub">' + _dEsc(ln.why || "") + '</div>'
    + '<div class="drp-panel">'
    + (ln.rules_active
       ? '<div class="drp-chips">'
         + Object.keys(ln.by_lane || {}).map(function(k){
             const v = ln.by_lane[k];
             return '<span class="drp-chip"><span class="kw">'
               + _dEsc(k.replace(/_/g, " ")) + '</span><span class="mu">'
               + drpcMoney(v.spend) + '</span><span class="mu">'
               + drpcNum(v.terms) + ' terms</span></span>'; }).join("")
         + '</div>'
       : '<div class="drp-empty">No reviewed lane rules, so every term is '
         + 'unclassified — ' + drpcMoney(ln.total_spend) + ' across '
         + drpcNum((ln.by_lane && ln.by_lane.unclassified || {}).terms)
         + ' terms. <button class="drp-orange-link" '
         + 'onclick="drpcGo(\'setup\')">Review classification</button></div>')
    + '</div>';

  /* --- 4: the trend ------------------------------------------------------ */
  if(tr.has_data){
    const r = tr.recent, p = tr.prior, c = tr.change;
    const cell = function(v, kind, good){
      if(v === null || v === undefined)
        return '<td>' + drpcUnk("The week before had none of this, so there is "
                                + "no base to change from — that is not a "
                                + "change of nought.") + '</td>';
      const n = Number(v);
      const cls = (good === null) ? "" : ((n > 0) === (good === "up")
                                          ? "drp-good" : "drp-bad");
      return '<td class="' + cls + '" style="font-weight:600">'
        + (n > 0 ? "+" : "") + n.toFixed(1)
        + (kind === "points" ? "pts" : "%") + '</td>';
    };
    h += '<div class="drp-h2">' + tr.span + '-day trend</div>'
      + '<div class="drp-h2-sub">' + _dEsc(tr.why || "") + '</div>'
      + '<div class="drp-panel"><table class="drp-table"><thead><tr>'
      + '<th>Window</th><th>Spend</th><th>Ad sales</th><th>Total sales</th>'
      + '<th>Ad orders</th><th>ACOS</th><th>TACOS</th><th>PPC CVR</th>'
      + '</tr></thead><tbody>'
      + '<tr><td>Recent · ' + _dEsc(r.start) + ' to ' + _dEsc(r.end) + '</td>'
      +   '<td>' + drpcMoney(r.spend) + '</td><td>' + drpcMoney(r.ad_sales)
      +   '</td><td>' + drpcMoney(r.total_sales) + '</td><td>'
      +   drpcNum(r.orders) + '</td><td>' + drpcVal(r.acos_pct, "points")
      +   '</td><td>' + drpcVal(r.tacos_pct, "points") + '</td><td>'
      +   drpcVal(r.cvr_pct, "points") + '</td></tr>'
      + '<tr><td>Prior · ' + _dEsc(p.start) + ' to ' + _dEsc(p.end) + '</td>'
      +   '<td>' + drpcMoney(p.spend) + '</td><td>' + drpcMoney(p.ad_sales)
      +   '</td><td>' + drpcMoney(p.total_sales) + '</td><td>'
      +   drpcNum(p.orders) + '</td><td>' + drpcVal(p.acos_pct, "points")
      +   '</td><td>' + drpcVal(p.tacos_pct, "points") + '</td><td>'
      +   drpcVal(p.cvr_pct, "points") + '</td></tr>'
      + '<tr><td>Change</td>'
      +   cell(c.spend, "pct", null) + cell(c.ad_sales, "pct", "up")
      +   cell(c.total_sales, "pct", "up") + cell(c.orders, "pct", "up")
      +   cell(c.acos_pct, "points", "down")
      +   cell(c.tacos_pct, "points", "down")
      +   cell(c.cvr_pct, "points", "up")
      + '</tr></tbody></table></div>';
  }

  /* --- 5: what moved ----------------------------------------------------- */
  const dr = j.drivers || {};
  h += '<div class="drp-h2">Change drivers</div>'
    + '<div class="drp-h2-sub">' + _dEsc(dr.why || "") + ' Total movement '
    +   drpcMoney(dr.total_movement) + '.</div>'
    + '<div class="drp-panel">'
    + ((dr.rows || []).length
       ? '<table class="drp-table"><thead><tr><th>Campaign</th>'
         + '<th style="text-align:left">Type</th><th>Spend Δ</th>'
         + '<th>Movement share</th><th>Sales Δ</th><th>Orders Δ</th>'
         + '<th>Recent spend</th></tr></thead><tbody>'
         + dr.rows.map(function(r){
             return '<tr><td title="' + _dEsc(r.campaign) + '">'
               + _dEsc(r.campaign)
               + (r.state !== "continuing"
                  ? ' <span class="drp-tag ' + (r.state === "new"
                      ? "enabled" : "archived") + '">' + _dEsc(r.state)
                    + '</span>' : "")
               + '</td>'
               + '<td style="text-align:left"><span class="drp-tag '
               +   _dEsc(drpcAdType(r.ad_product).toLowerCase()) + '">'
               +   _dEsc(drpcAdType(r.ad_product)) + '</span></td>'
               // Spending LESS is green here: the column is about money going
               // out, and a campaign that pulled back released budget.
               + '<td class="' + (r.spend_delta < 0 ? "drp-good"
                                  : r.spend_delta > 0 ? "drp-bad" : "") + '">'
               +   (r.spend_delta > 0 ? "+" : "") + drpcMoney(r.spend_delta)
               + '</td>'
               + '<td>' + (r.movement_share_pct === null ? drpcUnk()
                           : r.movement_share_pct.toFixed(1) + "%") + '</td>'
               + '<td class="' + (r.sales_delta > 0 ? "drp-good"
                                  : r.sales_delta < 0 ? "drp-bad" : "") + '">'
               +   (r.sales_delta > 0 ? "+" : "") + drpcMoney(r.sales_delta)
               + '</td>'
               + '<td class="' + (r.orders_delta > 0 ? "drp-good"
                                  : r.orders_delta < 0 ? "drp-bad" : "") + '">'
               +   (r.orders_delta > 0 ? "+" : "") + drpcNum(r.orders_delta)
               + '</td>'
               + '<td>' + drpcMoney(r.recent_spend) + '</td></tr>';
           }).join("")
         + '</tbody></table>'
       : '<div class="drp-empty">Nothing moved between the two windows.</div>')
    + '</div>';

  /* --- 6: the big ones --------------------------------------------------- */
  const lg = j.largest || {};
  h += '<div class="drp-h2">Largest spenders</div>'
    + '<div class="drp-h2-sub">' + _dEsc(lg.start || "") + ' to '
    +   _dEsc(lg.end || "") + ', ' + drpcMoney(lg.total_spend) + ' in '
    +   'total.</div>'
    + '<div class="drp-panel">'
    + ((lg.rows || []).length
       ? '<table class="drp-table"><thead><tr><th>Campaign</th>'
         + '<th style="text-align:left">Type</th><th>Spend</th><th>Share</th>'
         + '<th>Ad sales</th><th>ACOS</th><th>Orders</th></tr></thead><tbody>'
         + lg.rows.map(function(r){
             const a = r.acos_pct;
             const cls = (a === null || a === undefined) ? ""
                       : (a > 40 ? "drp-bad" : a >= 30 ? "drp-warn" : "");
             return '<tr><td title="' + _dEsc(r.campaign) + '">'
               + _dEsc(r.campaign) + '</td>'
               + '<td style="text-align:left"><span class="drp-tag '
               +   _dEsc(drpcAdType(r.ad_product).toLowerCase()) + '">'
               +   _dEsc(drpcAdType(r.ad_product)) + '</span></td>'
               + '<td>' + drpcMoney(r.spend) + '</td>'
               + '<td>' + (r.share_pct === null ? drpcUnk()
                           : r.share_pct.toFixed(1) + "%") + '</td>'
               + '<td>' + drpcMoney(r.sales) + '</td>'
               + '<td class="' + cls + '">'
               +   (a === null || a === undefined
                    ? drpcUnk("This campaign made no attributed sales, so it "
                              + "has no ACOS. That is not an ACOS of nought — "
                              + "it spent " + drpcMoney(r.spend) + " and sold "
                              + "nothing.")
                    : a.toFixed(1) + "%") + '</td>'
               + '<td>' + drpcNum(r.orders) + '</td></tr>';
           }).join("")
         + '</tbody></table>'
       : '<div class="drp-empty">No campaign spent anything in this '
         + 'window.</div>')
    + '</div>';

  /* --- 7: the three plan-dependent panels -------------------------------- */
  const pl = j.plan || {};
  h += '<div class="drp-h2">Against the plan</div>'
    + '<div class="drp-perf-bottom">'
    + drpcPlanCard("budget", "Budget pacing", pl.has_plan && pl.budget
        ? '<div style="font-size:22px;font-weight:700">'
          + (pl.budget.pace_pct === null ? drpcUnk()
             : pl.budget.pace_pct.toFixed(0) + "%") + '</div>'
          + '<div class="s">' + drpcMoney(pl.budget.spent) + ' of '
          + drpcMoney(pl.budget.planned) + ' · day ' + pl.budget.days_elapsed
          + ' of ' + pl.budget.days_total
          + '<br>Above 100% means the money is going out faster than the '
          + 'calendar.</div>'
        : null, pl.budget_why || pl.why)
    + drpcPlanCard("goal", "Goal progress",
        (pl.has_plan && (pl.goals || []).length)
        ? pl.goals.map(function(g){
            return '<div style="margin-bottom:8px"><b style="font-size:13px">'
              + _dEsc(g.title || g.metric) + '</b><div class="s">'
              + (g.measurable
                 ? "now " + drpcNum(g.actual) + " · target "
                   + _dEsc(String(g.target))
                 : _dEsc(g.why)) + '</div></div>'; }).join("")
        : null, pl.why || "The active plan carries no goals.")
    + drpcPlanCard("rank", "Rank evidence", null,
        pl.rank_why || "Rank is not recorded by this app.")
    + '</div>';

  /* --- 8: the gaps ------------------------------------------------------- */
  if((j.gaps || []).length){
    h += '<div class="drp-h2">Evidence gaps</div>'
      + '<div class="drp-h2-sub">Derived from the sections above rather than '
      +   'kept by hand, so a gap disappears from this list the moment it '
      +   'closes.</div>'
      + '<div class="drp-panel"><ul class="drp-gaps">'
      + j.gaps.map(function(g){ return '<li>' + _dEsc(g) + '</li>'; }).join("")
      + '</ul></div>';
  }

  drpcMain(h);
}

/* ==========================================================================
 * Page 5 -- Activity + decisions
 *
 * The spec's example timeline describes another account's history -- entitlements
 * stamped, channels created, a brand onboarded. None of that happened here, so
 * none of it is drawn. What IS drawn is this account's real history, derived
 * from the rows that already hold it, which is why the page is full rather than
 * waiting for somebody to start using it.
 * ======================================================================= */

const DRPC_KIND_TAG = {
  plan: "sp", decision: "enabled", observation: "sb", system: "sb",
  action: "enabled", execution: "enabled", verification: "sd",
  recommendation: "sd",
};

function drpcActivity(){
  const j = DRPC.act, s = j.suggestions || {}, c = j.counts || {};
  drpcFoot((j.events || [])[0] && j.events[0].at, true);

  let h = '<div class="drp-head"><div>'
    + '<h1>Activity + decisions</h1>'
    + '<div class="sub">The durable history of plans, decisions, actions, '
    +   'attempts and verification.</div></div>'
    + '<span class="drp-pill">' + drpcNum((j.events || []).length)
    +   ' events shown of ' + drpcNum(c.total) + '</span></div>';

  h += '<div class="drp-note good"><b>Append-only ledger.</b> '
    + _dEsc(j.why || "") + ' Nothing here is edited or removed; a correction is '
    + 'a new entry.</div>';

  /* --- suggested changes -------------------------------------------------- */
  h += '<div class="drp-h2">Suggested changes</div>'
    + '<div class="drp-h2-sub">What is waiting for a person to approve.</div>'
    + '<div class="drp-panel" style="display:flex;gap:14px;align-items:center;'
    +   'flex-wrap:wrap">'
    +   '<span class="drp-pill green">✓ Manual apply</span>'
    +   '<div style="flex:1;min-width:220px">'
    +     '<div style="font-size:12px;color:var(--ppc-muted)">'
    +       'Read-only towards Amazon · a person applies any change by hand'
    +       (s.plan_active ? ' · plan active' : ' · no active plan') + '</div>'
    +     (s.plan_warning ? '<div style="font-size:12px;color:var(--ppc-orange);'
                           + 'margin-top:3px">' + _dEsc(s.plan_warning)
                           + '</div>' : "")
    +   '</div></div>'
    + '<div class="drp-panel" style="margin-top:8px">'
    +   '<div class="drp-empty">' + _dEsc(s.why || "") + '</div></div>';

  /* --- the timeline ------------------------------------------------------- */
  const sel = function(id, cur, list, fn, lead){
    return '<select class="drp-in" onchange="' + fn + '(this.value)">'
      + '<option value="all"' + (cur === "all" ? " selected" : "") + '>'
      + _dEsc(lead) + '</option>'
      + list.map(function(k){
          return '<option value="' + _dEsc(k) + '"'
            + (cur === k ? " selected" : "") + '>'
            + _dEsc(k.replace(/_/g, " ").replace(/^./, function(m){
                return m.toUpperCase(); }))
            + ((c.by_kind && c.by_kind[k]) ? " (" + c.by_kind[k] + ")" : "")
            + ((c.by_actor && c.by_actor[k]) ? " (" + c.by_actor[k] + ")" : "")
            + '</option>'; }).join("")
      + '</select>';
  };
  h += '<div class="drp-h2">Timeline</div>'
    + '<div class="drp-filters">'
    +   sel("kind", DRPC.actKind, j.kinds || [], "drpcActFilterKind",
            "All activity")
    +   sel("actor", DRPC.actActor, j.actors || [], "drpcActFilterActor",
            "All actors")
    + '</div>';

  if(!(j.events || []).length){
    h += '<div class="drp-empty">Nothing matches these filters.</div>';
    drpcMain(h);
    return;
  }

  h += '<div class="drp-timeline">'
    + j.events.map(function(e){
        return '<div class="drp-tl-item">'
          + '<span class="drp-tl-dot ' + _dEsc(e.kind) + '"></span>'
          + '<div class="drp-tl-card">'
          +   '<div class="drp-tl-head">'
          +     '<span><span class="drp-tag '
          +       _dEsc(DRPC_KIND_TAG[e.kind] || "archived") + '">'
          +       _dEsc(e.kind) + '</span> '
          +       '<span style="font-size:12px;color:var(--ppc-muted)">'
          +       _dEsc(String(e.action || "").replace(/_/g, " ")) + '</span>'
          +     '</span>'
          +     '<span style="font-size:12px;color:var(--ppc-dim)">'
          +       _dEsc(e.at) + '</span>'
          +   '</div>'
          +   '<div class="drp-tl-title">' + _dEsc(e.title) + '</div>'
          +   (e.detail ? '<div class="drp-tl-desc">' + _dEsc(e.detail)
                          + '</div>' : "")
          +   '<div class="drp-tl-meta">' + _dEsc(e.op || "—")
          +     ' · ' + _dEsc(e.actor)
          +     (e.who ? ' · ' + _dEsc(e.who) : "")
          +     (e.entity_type ? ' · ' + _dEsc(e.entity_type) + ' '
                                 + _dEsc(e.entity_id) : "")
          +   '</div>'
          + '</div></div>';
      }).join("")
    + '</div>';

  drpcMain(h);
}

function drpcActFilterKind(v){ DRPC.actKind = v; DRPC.act = null; drpcLoad(true); }
function drpcActFilterActor(v){ DRPC.actActor = v; DRPC.act = null; drpcLoad(true); }

function drpcPlanCard(kind, title, body, why){
  return '<div class="drp-perf-bottom-card ' + kind + '">'
    + '<div class="t">' + _dEsc(title) + '</div>'
    + (body ? body : '<div class="drp-empty" style="padding:14px">'
                     + _dEsc(why || "") + '</div>')
    + '</div>';
}

/* ==========================================================================
 * Page 3 -- Goals + Strategy + Budget
 * ======================================================================= */

/* A working copy. Seeded from the current revision when one exists; otherwise
 * an EMPTY plan, not a pre-filled one. The spec's four goals and four
 * allocations are its example data, and shipping them as defaults would put
 * numbers nobody chose in front of somebody about to activate a strategy. */
function drpcSeed(plan){
  const b = (plan && plan.body) || {};
  return {
    identity: Object.assign({title: "", period_start: "", period_end: ""},
                            b.identity || {}),
    strategy: b.strategy || "",
    goals: (b.goals || []).slice(),
    budget: Object.assign({currency: "", total: "", behaviour: "Flexible target",
                           reserve_pct: ""}, b.budget || {}),
    allocations: (b.allocations || []).slice(),
    constraints: (b.constraints || []).slice(),
  };
}

function drpcPlan(){
  const j = DRPC.plan, p = j.plan, d = DRPC.draft, v = DRPC.vocab || {};
  drpcFoot(p && p.created_at, !!(p && p.status === "active"));

  let h = '<div class="drp-head"><div>'
    + '<h1>Goals + Strategy + Budget</h1>'
    + '<div class="sub">What this business intends, written down so a review '
    +   'has something to measure against. Every save creates a new revision; '
    +   'only an activated revision is approved strategy.</div>'
    + '</div><div class="drp-rev">'
    + (p ? '<span class="drp-pill ' + (p.status === "active" ? "green" : "cyan")
           + '">R' + _dEsc(p.revision) + ' · '
           + _dEsc(String(p.status).toUpperCase()) + '</span>'
         : '<span class="drp-pill">No revision yet</span>')
    + '<button class="drp-ghost" onclick="drpcSavePlan()">📋 Save new draft'
    +   '</button>'
    + (p && p.status !== "active"
       ? '<button class="drp-green-btn" onclick="drpcActivate(' + Number(p.revision)
         + ')">✓ Activate r' + _dEsc(p.revision) + '</button>' : "")
    + '</div></div>';

  /* 1 -- identity */
  h += '<div class="drp-light">'
    + '<h3>Plan identity</h3>'
    + '<div class="desc">Every save creates an immutable revision. Only an '
    +   'activated revision is approved strategy — so saving often is safe, and '
    +   'nothing you save starts governing anything by itself.</div>'
    + '<div class="drp-fields two">'
    +   drpcF("Plan title", "text", "identity.title", d.identity.title)
    +   drpcF("Period start", "date", "identity.period_start",
             d.identity.period_start)
    +   drpcF("Period end", "date", "identity.period_end", d.identity.period_end)
    + '</div></div>';

  /* 2 -- operating constraints */
  h += '<div class="drp-light">'
    + '<div class="drp-light-head"><div>'
    +   '<h3>Operating constraints</h3>'
    +   '<div class="desc">Standing policy recorded when an operator rejects a '
    +     'proposal. Enforced rows also gate compilation, so a proposal that '
    +     'breaks one is never born.</div></div>'
    +   '<span class="drp-pill">' + d.constraints.length + ' active</span>'
    + '</div>'
    + (d.constraints.length
       ? d.constraints.map(function(c, i){
           return '<div class="drp-item"><div class="hd"><span>'
             + _dEsc(c.text || "") + '</span>'
             + '<button class="drp-del" onclick="drpcDrop(\'constraints\',' + i
             + ')">🗑</button></div></div>'; }).join("")
       : '<div class="drp-empty" style="margin-top:14px">No standing '
         + 'constraints yet. Rejecting a proposal and choosing "standing rule '
         + 'for future runs" records one here.</div>')
    + '</div>';

  /* 3 -- strategy document */
  h += '<div class="drp-light">'
    + '<div class="drp-light-head"><div>'
    +   '<h3>Strategy document</h3>'
    +   '<div class="desc">Narrative context belongs here. Measurable goals and '
    +     'spend allocations stay structured below, where something can '
    +     'actually check them.</div></div></div>'
    + '<div class="drp-f" style="margin-top:16px">'
    +   '<textarea class="drp-mono" rows="14" '
    +   'oninput="drpcSet(\'strategy\',this.value)" '
    +   'placeholder="# PPC strategy&#10;&#10;## Business context&#10;…">'
    +   _dEsc(d.strategy) + '</textarea></div></div>';

  /* 4 -- goals */
  h += '<div class="drp-light">'
    + '<div class="drp-light-head"><div>'
    +   '<h3>Goals</h3>'
    +   '<div class="desc">Machine-evaluable outcomes a future review can '
    +     'measure. A goal with no window and no aggregation cannot be scored, '
    +     'so both are asked for.</div></div>'
    +   '<button class="drp-light-ghost" onclick="drpcAdd(\'goals\')">+ Add goal'
    +   '</button></div>'
    + (d.goals.length ? d.goals.map(function(g, i){
        return '<div class="drp-item"><div class="hd"><span>Goal ' + (i + 1)
          + '</span><button class="drp-del" onclick="drpcDrop(\'goals\',' + i
          + ')">🗑</button></div>'
          + '<div class="drp-fields two">'
          +   drpcF("Title", "text", "goals." + i + ".title", g.title)
          +   drpcS("Scope", "goals." + i + ".scope", g.scope, v.scope)
          +   drpcF("Scope id", "text", "goals." + i + ".scope_id", g.scope_id)
          + '</div><div class="drp-fields four" style="margin-top:12px">'
          +   drpcF("Metric", "text", "goals." + i + ".metric", g.metric)
          +   drpcS("Operator", "goals." + i + ".operator", g.operator, v.operator)
          +   drpcF("Target", "number", "goals." + i + ".target", g.target)
          +   drpcF("Upper target", "number", "goals." + i + ".upper_target",
                   g.upper_target)
          + '</div><div class="drp-fields four" style="margin-top:12px">'
          +   drpcS("Unit", "goals." + i + ".unit", g.unit, v.unit)
          +   drpcS("Window", "goals." + i + ".window", g.window, v.window)
          +   drpcS("Aggregation", "goals." + i + ".aggregation", g.aggregation,
                   v.aggregation)
          +   drpcS("Priority", "goals." + i + ".priority", g.priority, v.priority)
          + '</div><div class="drp-fields one" style="margin-top:12px">'
          +   drpcT("Rationale", "goals." + i + ".rationale", g.rationale)
          + '</div></div>';
      }).join("")
      : '<div class="drp-empty" style="margin-top:14px">No goals yet. '
        + 'The plan can be saved without one, but a review will have nothing '
        + 'to score.</div>')
    + '</div>';

  /* 5 -- budget */
  const alloc = d.allocations.reduce(function(a, x){
    return a + (Number(x.percentage) || 0); }, 0);
  h += '<div class="drp-light">'
    + '<div class="drp-light-head"><div>'
    +   '<h3>Budget plan</h3>'
    +   '<div class="desc">Intended spend — not the sum of Amazon\'s campaign '
    +     'delivery ceilings, which is a different number and always higher.'
    +   '</div></div>'
    +   '<span class="drp-alloc-sum' + (alloc > 100 ? " over" : "") + '">'
    +     'Allocated: ' + alloc.toFixed(1) + '%'
    +     (alloc > 100 ? " — over 100%" : "") + '</span>'
    + '</div>'
    + '<div class="drp-fields four">'
    +   drpcF("Currency", "text", "budget.currency", d.budget.currency)
    +   drpcF("Total planned spend", "number", "budget.total", d.budget.total)
    +   drpcS("Budget behaviour", "budget.behaviour", d.budget.behaviour,
             ["Flexible target", "Hard ceiling", "Floor"])
    +   drpcF("Experiment reserve %", "number", "budget.reserve_pct",
             d.budget.reserve_pct)
    + '</div></div>';

  /* 6 -- allocations */
  h += '<div class="drp-light">'
    + '<div class="drp-light-head"><div><h3>Allocations</h3>'
    +   '<div class="desc">How the planned spend is meant to split. A split '
    +     'written here is an intention — the measured split lives on PPC '
    +     'Analytics.</div></div>'
    +   '<button class="drp-light-ghost" onclick="drpcAdd(\'allocations\')">'
    +   '+ Add allocation</button></div>'
    + (d.allocations.length ? d.allocations.map(function(a, i){
        return '<div class="drp-item"><div class="hd"><span>Allocation '
          + (i + 1) + '</span><button class="drp-del" '
          + 'onclick="drpcDrop(\'allocations\',' + i + ')">🗑</button></div>'
          + '<div class="drp-fields two">'
          +   drpcF("Label", "text", "allocations." + i + ".label", a.label)
          +   drpcS("Scope", "allocations." + i + ".scope", a.scope, v.scope)
          +   drpcF("Scope id", "text", "allocations." + i + ".scope_id",
                   a.scope_id)
          + '</div><div class="drp-fields" style="margin-top:12px">'
          +   drpcF("Amount", "number", "allocations." + i + ".amount", a.amount)
          +   drpcF("Percentage", "number", "allocations." + i + ".percentage",
                   a.percentage)
          +   drpcS("Priority", "allocations." + i + ".priority", a.priority,
                   v.priority)
          + '</div><div class="drp-fields one" style="margin-top:12px">'
          +   drpcT("Rationale", "allocations." + i + ".rationale", a.rationale)
          + '</div></div>';
      }).join("")
      : '<div class="drp-empty" style="margin-top:14px">No allocations yet.'
        + '</div>')
    + '</div>';

  /* the revision trail */
  if((DRPC.history || []).length){
    h += '<div class="drp-h2">Revision history</div>'
      + '<div class="drp-h2-sub">Kept in full. A superseded revision is what '
      +   'last month\'s proposals were made against, so deleting one would '
      +   'make them unexplainable.</div>'
      + '<div class="drp-panel"><table class="drp-table"><thead><tr>'
      + '<th>Revision</th><th style="text-align:left">Status</th>'
      + '<th style="text-align:left">Title</th>'
      + '<th style="text-align:left">Period</th>'
      + '<th style="text-align:left">Created</th><th></th></tr></thead><tbody>'
      + DRPC.history.map(function(r){
          return '<tr><td>r' + _dEsc(r.revision) + '</td>'
            + '<td style="text-align:left"><span class="drp-pill '
            +   (r.status === "active" ? "green" : "") + '">'
            +   _dEsc(r.status) + '</span></td>'
            + '<td style="text-align:left">' + _dEsc(r.title || "untitled")
            + '</td>'
            + '<td style="text-align:left">' + _dEsc(r.period_start || "—")
            +   ' → ' + _dEsc(r.period_end || "—") + '</td>'
            + '<td style="text-align:left;font-size:12px;color:var(--ppc-muted)">'
            +   _dEsc(r.created_at || "") + '</td>'
            + '<td>' + (r.status === "active" ? ""
                : '<button class="drp-cyan-link" onclick="drpcActivate('
                  + Number(r.revision) + ')">Activate</button>') + '</td></tr>';
        }).join("")
      + '</tbody></table></div>';
  }

  drpcMain(h);
}

/* A light-theme text field bound to a path in the draft. */
function drpcF(label, type, path, val){
  return '<div class="drp-f"><label>' + _dEsc(label) + '</label>'
    + '<input type="' + type + '" value="' + _dEsc(val == null ? "" : val)
    + '" oninput="drpcSet(' + jsArg(path) + ',this.value)"></div>';
}

function drpcT(label, path, val){
  return '<div class="drp-f"><label>' + _dEsc(label) + '</label>'
    + '<textarea rows="2" oninput="drpcSet(' + jsArg(path) + ',this.value)">'
    + _dEsc(val == null ? "" : val) + '</textarea></div>';
}

/* A dropdown whose options come from the SERVER's vocabulary, so a goal cannot
 * be saved with a window the evaluator has never heard of. */
function drpcS(label, path, val, list){
  return '<div class="drp-f"><label>' + _dEsc(label) + '</label>'
    + '<select onchange="drpcSet(' + jsArg(path) + ',this.value)">'
    + '<option value=""></option>'
    + (list || []).map(function(o){
        return '<option value="' + _dEsc(o) + '"' + (o === val ? " selected" : "")
          + '>' + _dEsc(String(o).replace(/_/g, " ").replace(/^./,
              function(m){ return m.toUpperCase(); })) + '</option>';
      }).join("")
    + '</select></div>';
}

/* Writes into the draft by path. Redraws ONLY when the change alters the shape
 * of the form -- typing in a field must not rebuild the panel under the cursor. */
function drpcSet(path, val){
  const parts = String(path).split(".");
  let o = DRPC.draft;
  for(let i = 0; i < parts.length - 1; i++) o = o[parts[i]];
  o[parts[parts.length - 1]] = val;
  if(path.indexOf("percentage") >= 0) drpcPlan();   // the allocated total moves
}

function drpcAdd(kind){
  DRPC.draft[kind].push(kind === "goals"
    ? {title: "", scope: "", scope_id: "", metric: "", operator: "",
       target: "", upper_target: "", unit: "", window: "", aggregation: "",
       priority: "", rationale: ""}
    : {label: "", scope: "", scope_id: "", amount: "", percentage: "",
       priority: "", rationale: ""});
  drpcPlan();
}

async function drpcDrop(kind, i){
  if(typeof uiConfirm === "function"){
    const ok = await uiConfirm("Remove this from the draft? Revisions already "
      + "saved keep theirs — this only changes what the next save writes.");
    if(!ok) return;
  }
  DRPC.draft[kind].splice(i, 1);
  drpcPlan();
}

async function drpcSavePlan(){
  try{
    const j = await (await fetch("/drppc/console/plan?" + ppcQS(), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({body: DRPC.draft})})).json();
    if(!j || !j.ok){
      if(typeof toast === "function")
        toast("Not saved: " + ((j && j.error) || "unknown"));
      return;
    }
    if(typeof toast === "function") toast(j.note);
    DRPC.plan = null;
    drpcLoad(true);
  }catch(e){
    if(typeof toast === "function") toast("Could not save the plan: " + e);
  }
}

async function drpcActivate(rev){
  if(typeof uiConfirm === "function"){
    const ok = await uiConfirm("Activate revision " + rev + "? It becomes the "
      + "approved strategy every future review measures against. The one it "
      + "replaces is kept, not deleted. Nothing is sent to Amazon.");
    if(!ok) return;
  }
  try{
    const j = await (await fetch("/drppc/console/plan/activate?" + ppcQS(), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({revision: rev})})).json();
    if(typeof toast === "function")
      toast((j && j.ok) ? j.note
                        : ("Not activated: " + ((j && j.error) || "unknown")));
    if(j && j.ok){
      DRPC.plan = null; DRPC.setup = null;
      drpcLoad(true);
    }
  }catch(e){
    if(typeof toast === "function") toast("Could not activate: " + e);
  }
}
