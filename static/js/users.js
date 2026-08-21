// ===================== USERS & PERMISSIONS =====================
// The admin screen for adding people and choosing what each of them can do.
//
// IMPORTANT: everything in this file is a COURTESY, not a control. Hiding a
// button stops nobody -- anyone can open the console and call /submit directly.
// The real enforcement is auth/guard.py, which checks every request on the
// server before the app does anything. This file only avoids showing people
// controls that would fail, and reports the reason plainly when one does.

let ME = null;              // {id,email,name,role,permissions,workspaces,...}
let USERS_META = null;      // the vocabulary the screens are drawn from

// The ONE place USERS_META is assembled. It was being built by hand in two
// places, and BOTH listed only all_permissions and roles -- so all_features,
// role_features and levels were thrown away the moment they arrived, even
// though the server had sent them. featureRows() then found nothing to draw and
// returned an empty string, so the whole "What may they SEE?" section silently
// vanished from both the Add form and the Edit panel. Saving then submitted an
// empty set of feature levels.
//
// It MERGES rather than replaces: whichever response carries a key, that key is
// kept. That is what makes the bug unrepeatable -- a future endpoint that omits
// a field can no longer erase what another endpoint already provided.
function _setMeta(j){
  const keep = ["all_permissions", "roles", "all_features", "role_features", "levels",
                "feature_parent", "feature_groups"];
  const next = USERS_META || {};
  keep.forEach(function(k){ if(j && j[k] != null) next[k] = j[k]; });
  USERS_META = next;
  return USERS_META;
}

function _uesc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// An argument for an inline onclick="..." handler.
//
// JSON.stringify was used here, and it returns a string wrapped in DOUBLE
// quotes -- the same character that delimits the attribute it was being pasted
// into. onclick="userSave("u_abc")" makes the browser read the handler as
// `userSave(` and stop, so the button did nothing at all: no error on screen,
// no request, no clue. Every button that passed an id was dead this way --
// Edit, Invite, Enable/Disable, Delete and Save changes -- while "Add", which
// takes no argument, kept working and made the screen look alive.
//
// So: quote for JavaScript with SINGLE quotes, then escape for the HTML
// attribute. The browser un-escapes the entities first, leaving valid JS.
//
// (onclick='...' with SINGLE quotes is fine and a few screens do that. This is
// for the double-quoted majority.)
//
// It lives here, in the file whose bug it was and whose tests cover it, and is
// exported under the neutral name jsArg because the same fault turned up in the
// image library's "Use as main". Classic scripts share one global scope and
// these are only ever called from a click, so load order does not matter --
// but keeping the definition where the test loads it does.
function jsArg(s){
  const js = String(s==null?"":s).replace(/\\/g,"\\\\").replace(/'/g,"\\'");
  return "'" + js.replace(/&/g,"&amp;").replace(/"/g,"&quot;")
                 .replace(/</g,"&lt;").replace(/>/g,"&gt;") + "'";
}
function _uarg(s){ return jsArg(s); }        // the name this file already used

// ---- who am I -----------------------------------------------------------
// Drives the top bar. Runs on every page load; failures are silent because a
// signed-out visitor is already being redirected to the sign-in screen.
async function loadMe(){
  try{
    const j = await (await fetch("/users/me")).json();
    if(!j || !j.ok) return;
    ME = j.user; _setMeta(j);
    // Which store the app is on. Used for wording that is only correct on one
    // backend -- see the "not in your sheet" caption in miles_template.js.
    window.DATA_BACKEND = j.backend || "sheets";
    window.DATA_BACKEND_SOURCE = j.backend_source || "";
    window.DATA_BACKEND_NOTE = j.backend_note || "";
    // The header describes the store, and it may have been drawn before this
    // answer arrived -- in which case it drew the spreadsheet version. Redraw it
    // now that the truth is known, rather than leaving whichever version won the
    // race on screen.
    if(typeof renderDataSource === "function"){ try{ renderDataSource(); }catch(e){} }
    // SAY IT ON SCREEN when the app fell back to spreadsheets.
    //
    // "Still using sheets" and "the migration failed" look identical from the
    // outside and need completely different actions. The usual cause is that the
    // database file is not where the app looked -- a deploy replaced the disk it
    // was on -- and that is invisible unless something says so. Shown only when
    // it is NOT on the database, because that is the only case worth a banner.
    if(window.DATA_BACKEND !== "db"){
      const host = document.getElementById("storebanner");
      if(host){
        host.style.display = "";
        host.innerHTML = '<i class="ti ti-alert-triangle"></i> '
          + 'This app is reading <b>Google Sheets</b>, not its database — '
          + (window.DATA_BACKEND_NOTE
              ? String(window.DATA_BACKEND_NOTE)
              : 'chosen by ' + String(window.DATA_BACKEND_SOURCE || 'the default'))
          + ' Anything generated goes to the sheet, and screens will say "your '
          + 'sheet" because that is where it really is.';
      }
    }
    const btn = document.getElementById("usersbtn");
    if(btn && can("manage_users")) btn.style.display = "";
    const who = document.getElementById("whoami");
    if(who && !j.bootstrap){
      who.style.display = "";
      who.textContent = ME.name || ME.email;
      who.title = "Signed in as " + (ME.email || "") + " · " + (ME.role || "");
    }
    const out = document.getElementById("signoutbtn");
    if(out && !j.bootstrap) out.style.display = "";
    applyPermissionsToUI();
  }catch(e){}
}

// Does the signed-in person hold this permission? While the app is still on the
// shared password there are no accounts yet, so everything is permitted -- which
// is exactly what the server does too.
function can(perm){
  if(!ME) return true;
  return (ME.permissions || []).indexOf(perm) >= 0;
}

// WHICH SECTION BELONGS TO WHICH FEATURE.
//
// Mirrors auth/guard.FEATURE_PATHS. It has to be stated on this side too
// because the sidebar is drawn in the browser and the server never sees it --
// but it is the SERVER that decides: everything below only hides things, and a
// screen hidden here is still refused there if somebody types its address.
const SECTION_FEATURE = {
  listings:"listings", generate:"generate", sync:"listings", variations:"variations",
  sellerimport:"sellerimport", miles:"listings",
  imagestudio:"images", imagerefs:"images", imagelib:"images",
  inventory:"inventory", sourcing:"repricer",
  // Reads /inventory/money-back, which the doorman guards as "inventory", so
  // the nav item has to hide on exactly the same permission. A link that is
  // visible and then refused is worse than one that was never shown.
  reimbursements:"inventory",
  orders:"orders", returns:"returns",
  sales:"sales", leading:"sales", hourly:"hourly",
  traffic:"traffic", sqp:"traffic", finance:"finance", aiusage:"aiusage",
  weekly:"sales", daily:"sales",
  ppc:"ppc", drppc:"ppc",
  monitor:"monitor", trackers:"monitor", alerts:"monitor",
  catalog:"listings", categories:"listings", compliance:"listings",
  notify:"accounts", setup:"accounts",
  // MEASURED: 36 sections in the nav, 34 in this map. The two missing ones were
  // not harmless. `brief` is the weekly business brief -- revenue, profit, what
  // moved -- so it belongs with sales, exactly as overview and leading do; it
  // was visible to a user with sales="none". `permissions` decides what
  // everyone else may do, so it sits with the account administration it
  // belongs to.
  //
  // A section absent from this map is never hidden, and nothing says so at the
  // time -- which is why both of these were missed. test_permission_coverage.py
  // now fails on an unmapped section rather than leaving it to be noticed.
  brief:"sales", permissions:"accounts",
  // Phase 1 analytics. Mapped ON ARRIVAL rather than left to be noticed later:
  // an unmapped section is never hidden, and that default is what let /brief
  // show revenue to a user with sales="none". These read Brand Analytics --
  // what the whole marketplace searches for and what converts on our listings
  // -- which is commercially sensitive in the same way turnover is, so they sit
  // with `traffic` (search performance), exactly as /sqp does.
  kwspy:"traffic", kwasin:"traffic", ranktracker:"traffic", kwhistory:"traffic",
  // ASIN Studio writes listing copy and creates a draft, so it is a
  // LISTINGS permission -- not traffic. Somebody who may read search data
  // should not thereby be able to create listings.
  asinstudio:"listings",
};

function featureLevel(feat){
  if(!ME) return "edit";
  const f = (ME.features || {});
  const v = f[feat];
  return (v === undefined || v === null || v === "") ? "edit" : String(v);
}

// HIDDEN, NOT DIMMED.
//
//     "when the user do not have access to a certain feature it should not be
//      displayed to it even not in grey color, he should not even see a sign
//      of it"
//
// This used to set opacity to .45, on the reasoning that the app should not
// look different for different people. That is the wrong trade for a tool being
// handed to people outside the business: a greyed-out control still tells you
// the feature exists, what it is called, and roughly what it does. For somebody
// who is only meant to see one account, the shape of everything else is itself
// information.
//
// So a feature set to `none` leaves NO trace: the nav item is removed, the
// group holding it disappears when it empties, and the controls go with it.
// Nothing here is a security boundary -- auth/guard refuses the request
// whatever the browser shows -- this is about not advertising what somebody
// cannot have.
/* MAY THIS PERSON OPEN THIS SCREEN AT ALL?
 *
 *     "the user with permissions should only be able to view the page for
 *      which the permission is aloted to him"
 *
 * Hiding the nav item was never the whole job, because the nav item is not the
 * only way in. Every screen has a real address (/w/<workspace>/<section>), and
 * there is also the bookmark bar, the browser Back button, and any link
 * somebody was sent. All of those call navTo() directly and none of them look
 * at the sidebar.
 *
 * The data was never exposed by that -- auth/guard.py refuses the requests, so
 * the screen would open empty or erroring. But "opens and then fails" is a bad
 * answer to "am I allowed in here": it looks like the app is broken rather than
 * like the answer is no, and it leaves the person guessing whether to report a
 * bug. Say no, plainly, at the door.
 *
 * Unknown sections are ALLOWED. A section missing from SECTION_FEATURE means
 * the map is incomplete, not that the user is banned -- failing open here and
 * failing the coverage test instead keeps a mapping mistake from locking people
 * out of a working screen.
 */
function maySeeSection(sec){
  try{
    if(typeof ME === "undefined" || !ME) return true;   // before /users/me lands
    const feat = SECTION_FEATURE[sec];
    if(!feat) return true;                              // unmapped -> not a ban
    return featureLevel(feat) !== "none";
  }catch(e){ return true; }
}

function applyPermissionsToUI(){
  if(!ME) return;

  // 1. Whole sections the person has no access to.
  document.querySelectorAll(".navitem[data-sec]").forEach(function(el){
    const feat = SECTION_FEATURE[el.dataset.sec];
    if(!feat) return;
    if(featureLevel(feat) === "none"){
      el.style.display = "none";
      el.setAttribute("data-hidden-by-permission", "1");
    }
  });

  // 2. A group whose children have all gone should go too -- an expander that
  //    opens onto nothing is worse than no expander.
  document.querySelectorAll(".navgroup").forEach(function(g){
    const kids = g.querySelectorAll(".navkids .navitem");
    const gone = g.querySelectorAll('.navkids .navitem[data-hidden-by-permission]');
    if(kids.length && kids.length === gone.length) g.style.display = "none";
  });

  // 3. Individual controls, by permission rather than by feature.
  const RULES = [
    ["publish",         '[onclick*="submitAll"],[onclick*="pushLive"],[onclick*="bulkHandling"]'],
    ["approve_delete",  '[onclick*="bulkStatus"],[onclick*="bulkDelete"],[onclick*="approve"]'],
    ["manage_accounts", '#aibtn,[onclick*="openAccountEditor"],[onclick*="openCurrentAccountSettings"]'],
  ];
  RULES.forEach(function(r){
    if(can(r[0])) return;
    document.querySelectorAll(r[1]).forEach(function(el){
      el.style.display = "none";
      el.setAttribute("data-hidden-by-permission", "1");
    });
  });

  // 4. A read-only feature keeps its screen and loses its buttons -- that is a
  //    different thing from having no access, and conflating them would hide
  //    screens from people who are meant to read them.
  document.querySelectorAll("[data-sec]").forEach(function(el){
    const feat = SECTION_FEATURE[el.dataset.sec];
    if(feat && featureLevel(feat) === "view") el.setAttribute("data-readonly", "1");
  });
}

// ---- the admin screen ---------------------------------------------------
function openUsers(){
  const m = document.getElementById("usersmodal");
  if(m) m.classList.add("open");
  renderUsers();
}
function closeUsers(){
  const m = document.getElementById("usersmodal");
  if(m) m.classList.remove("open");
}

async function renderUsers(){
  const body = document.getElementById("usersbody");
  if(!body) return;
  body.innerHTML = '<div class="cc" style="padding:16px"><span class="genspin"></span> Loading…</div>';
  let j;
  try{ j = await (await fetch("/users/list")).json(); }
  catch(e){ body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">Could not load users: '+_uesc(String(e))+'</div>'; return; }
  if(!j || !j.ok){
    body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'+_uesc((j&&j.error)||"Could not load users")+'</div>';
    return;
  }
  _setMeta(j);

  let h = '<div style="font-weight:600;font-size:15px;margin-bottom:2px">Users &amp; permissions</div>';

  if(j.bootstrap){
    h += '<div class="cc" style="font-size:12px;margin:6px 0 12px;padding:8px 10px;'
      +  'border:1px solid #4a3d1a;background:#2a2310;border-radius:6px">'
      +  '<b>Start by adding yourself as an owner.</b><br>'
      +  'The app is still using the single shared password, and it keeps working '
      +  'until an <i>owner</i> account exists — not merely until someone accepts. '
      +  'That is deliberate: if it stopped as soon as any VA accepted, you would '
      +  'be locked out of your own app with no account of your own. Add yourself '
      +  'with the <b>owner</b> role, open your own invite link, and the shared '
      +  'password stops working from that moment.</div>';
  }

  h += '<div class="cc" style="font-size:11.5px;margin:4px 0 14px">'
    +  'Add someone by email, then send them the one-time link the app gives you. '
    +  'They choose their own password — you never see it.</div>';

  // ---- existing users
  h += '<table class="kv" style="width:100%"><tbody>';
  if(!j.users.length){
    h += '<tr><td class="cc" style="padding:10px">Nobody added yet.</td></tr>';
  }
  j.users.forEach(function(u){
    const perms = (u.permissions||[]).map(function(p){
      return '<span class="db-chip" style="font-size:10px;padding:1px 6px">'
           + _uesc((USERS_META.all_permissions[p]||p).split(",")[0]) + '</span>';
    }).join(" ") || '<span class="cc" style="font-size:11px">read only</span>';
    const ws = (u.workspaces||[]).indexOf("*")>=0
      ? "all workspaces"
      : (u.workspaces||[]).join(", ");
    let state = "";
    if(!u.active)            state = '<span style="color:#e0a06b">disabled</span>';
    else if(u.invite_expired) state = '<span style="color:var(--red)">invite expired</span>';
    else if(u.pending_invite) state = '<span style="color:#e0c06b">invite not accepted</span>';
    else                      state = '<span style="color:var(--ok)">active</span>';

    h += '<tr><td style="padding:9px 6px;border-top:1px solid #26303f">'
      +  '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">'
      +  '<div style="flex:1;min-width:190px">'
      +    '<div style="font-weight:600;font-size:13px">'+_uesc(u.name||u.email)+'</div>'
      +    '<div class="cc" style="font-size:11px">'+_uesc(u.email)+' · '+_uesc(u.role)+' · '+state+'</div>'
      +    '<div style="margin-top:5px">'+perms+'</div>'
      +    '<div class="cc" style="font-size:11px;margin-top:4px">Workspaces: '+_uesc(ws)+'</div>'
      +  '</div>'
      +  '<div style="display:flex;gap:6px;flex-wrap:wrap">'
      +    '<button class="db-chip" onclick="userEdit('+_uarg(u.id)+')">Edit</button>'
      +    '<button class="db-chip" onclick="userInvite('+_uarg(u.id)+')" '
      +      'title="Issue a fresh one-time link. Also use this as a password reset — it clears the old password.">New link</button>'
      +    '<button class="db-chip" onclick="userToggle('+_uarg(u.id)+','+(u.active?"false":"true")+')">'
      +      (u.active?"Disable":"Enable")+'</button>'
      +    '<button class="db-chip" style="color:var(--red);border-color:var(--red-line)" '
      +      'onclick="userDelete('+_uarg(u.id)+')">Delete</button>'
      +  '</div></div>'
      +  '<div id="uedit_'+_uesc(u.id)+'"></div>'
      +  '</td></tr>';
  });
  h += '</tbody></table>';

  // ---- add form
  h += '<div style="margin-top:18px;border-top:1px solid #26303f;padding-top:14px">'
    +  '<div style="font-weight:600;font-size:13px;margin-bottom:8px">Add a person</div>'
    +  '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">'
    +    '<input class="rc-in" id="nu_email" placeholder="their@email.com" style="flex:1;min-width:200px;margin:0">'
    +    '<input class="rc-in" id="nu_name"  placeholder="Name (optional)" style="flex:1;min-width:140px;margin:0">'
    +    '<select class="rc-in" id="nu_role" style="width:auto;margin:0" onchange="userRolePreset()">'
    +      Object.keys(USERS_META.roles).map(function(r){
             return '<option value="'+_uesc(r)+'"'+(r==="lister"?" selected":"")+'>'+_uesc(r)+'</option>'; }).join("")
    +    '</select>'
    +  '</div>'
    +  '<div class="cc" style="font-size:11.5px;margin-bottom:6px">What may they SEE? '
    +    '(read-only or read-and-write, per area)</div>'
    +  '<div id="nu_feats" style="display:flex;flex-direction:column;gap:5px;margin-bottom:12px">'
    +    featureRows("nu", (USERS_META.role_features||{})["lister"])
    +  '</div>'
    +  '<div class="cc" style="font-size:11.5px;margin-bottom:6px">What may they DO? '
    +    '(these also need the matching area above)</div>'
    +  '<div id="nu_perms" style="display:flex;flex-direction:column;gap:4px;margin-bottom:10px">'
    +    permissionCheckboxes("nu", USERS_META.roles["lister"] || [])
    +  '</div>'
    +  '<div class="cc" style="font-size:11.5px;margin-bottom:6px">Which workspaces?</div>'
    +  '<div id="nu_ws" style="display:flex;flex-direction:column;gap:4px;margin-bottom:12px">'
    +    workspaceCheckboxes("nu", ["*"])
    +  '</div>'
    +  '<button class="db-chip" style="background:var(--accent);color:#fff;border-color:var(--accent)" '
    +    'onclick="userCreate()">Add and make an invite link</button>'
    +  '<div id="nu_result" style="margin-top:10px"></div>'
    +  '</div>';

  body.innerHTML = h;
}

// Per-feature access, the way Amazon's child accounts work: each area is None,
// View only, or View & edit. This is the "may they SEE it" axis -- the
// permissions below are the "may they DO it" axis, and both apply.
// PER PAGE, GROUPED, WITH INHERIT AS A REAL CHOICE.
//
// "give me an option to appoint the permissions to each user by page because we
//  have features of the apps available per page also"
//
// There are seventeen of these now rather than seven, so a flat list is a wall.
// They are grouped the way the sidebar groups them, and a page that sits under
// an area offers "Inherit" -- which is not the same as picking a level. Inherit
// means the page follows its area, so changing someone from manager to lister
// moves the whole group with it; picking a level pins that one page.
//
// Inherit is stored as ABSENT, not as a word, which is what makes it inherit on
// the server too (auth/users.py feature_level).
function featureRows(prefix, current){
  const F = (USERS_META && USERS_META.all_features) || {};
  const parent = (USERS_META && USERS_META.feature_parent) || {};
  const groups = (USERS_META && USERS_META.feature_groups) || null;
  const cur = current || {};

  const row = function(k){
    if(!F[k]) return "";
    const isChild = !!parent[k];
    const has = Object.prototype.hasOwnProperty.call(cur, k) && cur[k];
    // An area with nothing set still shows "view", which is what it resolves
    // to. A PAGE with nothing set shows Inherit, because that is what it is.
    const v = has ? cur[k] : (isChild ? "" : "view");
    const opt = (val, lbl) =>
      '<option value="'+val+'"'+(v===val?' selected':'')+'>'+lbl+'</option>';
    return '<div style="display:flex;align-items:center;gap:8px;font-size:12px'
      + (isChild ? ';padding-left:14px' : ';font-weight:600') + '">'
      + '<select class="'+prefix+'_feat" data-feat="'+_uesc(k)+'" '
      +   'style="width:132px;padding:3px 6px;font-size:12px">'
      +   (isChild ? opt("", "Inherit (" + _uesc(parent[k]) + ")") : "")
      +   opt("none","No access") + opt("view","View only") + opt("edit","View &amp; edit")
      + '</select>'
      + '<span class="cc" style="font-weight:400">'+_uesc(F[k])+'</span></div>';
  };

  if(groups && groups.length){
    return groups.map(function(g){
      const rows = (g.features||[]).map(row).join("");
      if(!rows) return "";
      return '<div class="cc" style="font-size:10.5px;text-transform:uppercase;'
        + 'letter-spacing:.06em;margin:8px 0 2px;opacity:.75">'+_uesc(g.title)+'</div>'
        + rows;
    }).join("");
  }
  return Object.keys(F).map(row).join("");
}

function _collectFeatures(prefix){
  const out = {};
  document.querySelectorAll("."+prefix+"_feat").forEach(function(s){
    const v = s.value;
    // An empty value is Inherit. It must be OMITTED rather than saved as a
    // level -- saving it would pin the page to whatever it happens to resolve
    // to today, and it would stop following its area from then on.
    if(v) out[s.getAttribute("data-feat")] = v;
  });
  return out;
}

function permissionCheckboxes(prefix, checked){
  const P = (USERS_META && USERS_META.all_permissions) || {};
  return Object.keys(P).map(function(k){
    const on = (checked||[]).indexOf(k) >= 0;
    return '<label style="display:flex;gap:8px;align-items:flex-start;font-size:12px;cursor:pointer">'
      + '<input type="checkbox" data-perm="'+_uesc(k)+'" class="'+prefix+'_perm"'+(on?" checked":"")+' style="margin-top:2px">'
      + '<span>'+_uesc(P[k])+'</span></label>';
  }).join("");
}

// The workspace list comes from the same ACCOUNTS the home screen draws, so it
// can never drift out of step with what actually exists.
//
// Note ACCOUNTS is declared `let` in shell.js, which does NOT put it on window --
// reading it as window.ACCOUNTS silently yields undefined and would leave this
// list showing no workspaces at all. Classic scripts share one global scope, so
// the bare name resolves correctly.
function workspaceCheckboxes(prefix, checked){
  const accounts = (typeof ACCOUNTS !== "undefined" && ACCOUNTS) ? ACCOUNTS : [];
  const list = [{id:"*", label:"All workspaces (including any added later)"},
                {id:"_no_account", label:"No account open"}]
    .concat(accounts.map(function(a){ return {id:a.id, label:a.label}; }));
  return list.map(function(w){
    const on = (checked||[]).indexOf(w.id) >= 0;
    return '<label style="display:flex;gap:8px;align-items:center;font-size:12px;cursor:pointer">'
      + '<input type="checkbox" data-ws="'+_uesc(w.id)+'" class="'+prefix+'_ws"'+(on?" checked":"")+'>'
      + '<span>'+_uesc(w.label)+'</span></label>';
  }).join("");
}

function _collect(prefix, attr, cls){
  return Array.prototype.slice.call(document.querySelectorAll("."+prefix+"_"+cls))
    .filter(function(c){ return c.checked; })
    .map(function(c){ return c.getAttribute(attr); });
}

function userRolePreset(){
  const role = (document.getElementById("nu_role")||{}).value || "lister";
  const preset = (USERS_META.roles||{})[role] || [];
  document.querySelectorAll(".nu_perm").forEach(function(c){
    c.checked = preset.indexOf(c.getAttribute("data-perm")) >= 0;
  });
  // Roles preset the AREA access too, so picking "lister" hides PPC and
  // credentials without anyone having to know that is what a lister means.
  const fpre = (USERS_META.role_features||{})[role] || {};
  document.querySelectorAll(".nu_feat").forEach(function(s){
    const k = s.getAttribute("data-feat");
    if(fpre[k]) s.value = fpre[k];
  });
}

async function userCreate(){
  const email = ((document.getElementById("nu_email")||{}).value||"").trim();
  const out = document.getElementById("nu_result");
  if(!email){ out.innerHTML = '<span style="color:var(--red)">Enter an email address.</span>'; return; }
  const payload = {
    email: email,
    name:  ((document.getElementById("nu_name")||{}).value||"").trim(),
    role:  (document.getElementById("nu_role")||{}).value || "lister",
    permissions: _collect("nu","data-perm","perm"),
    features:    _collectFeatures("nu"),
    workspaces:  _collect("nu","data-ws","ws"),
  };
  out.innerHTML = '<span class="cc">Creating…</span>';
  try{
    const j = await (await fetch("/users/create",{method:"POST",
      headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)})).json();
    if(!j.ok){ out.innerHTML = '<span style="color:var(--red)">'+_uesc(j.error||"failed")+'</span>'; return; }
    showInviteLink(out, j.invite_url, email);
    renderUsersKeepingResult(out.innerHTML);
  }catch(e){ out.innerHTML = '<span style="color:var(--red)">'+_uesc(String(e))+'</span>'; }
}

// The link is shown ONCE -- only its hash is stored, so it cannot be shown
// again later. Say so, so nobody closes the box expecting to find it again.
function showInviteLink(host, url, who){
  host.innerHTML =
      '<div style="border:1px solid #2f4a33;background:#16231a;border-radius:6px;padding:10px">'
    + '<div style="font-size:12px;font-weight:600;color:var(--ok);margin-bottom:6px">'
    + 'Invite link for '+_uesc(who)+'</div>'
    + '<div class="cc" style="font-size:11px;margin-bottom:6px">Send this to them. '
    + 'It works once and expires in 7 days. <b>It is not stored</b> — if you lose it, '
    + 'click “New link”.</div>'
    + '<input class="rc-in" id="invite_url" readonly value="'+_uesc(url)+'" style="margin:0 0 6px;font-size:11px">'
    + '<button class="db-chip" onclick="copyInvite()">Copy link</button></div>';
}

function copyInvite(){
  const el = document.getElementById("invite_url");
  if(!el) return;
  el.select();
  try{ document.execCommand("copy"); toast("Invite link copied"); }
  catch(e){ toast("Select the link and copy it manually"); }
}

// Redraw the list but keep the freshly-issued link on screen, because it can
// never be retrieved again once it is gone.
async function renderUsersKeepingResult(html){
  await renderUsers();
  const out = document.getElementById("nu_result");
  if(out && html) out.innerHTML = html;
}

function userEdit(id){
  const host = document.getElementById("uedit_"+id);
  if(!host) return;
  if(host.innerHTML.trim()){ host.innerHTML = ""; return; }   // toggle closed
  fetch("/users/list").then(r=>r.json()).then(function(j){
    const u = (j.users||[]).find(function(x){ return x.id===id; });
    if(!u) return;
    host.innerHTML =
        '<div style="margin:8px 0 4px;padding:10px;border:1px solid #26303f;border-radius:6px">'
      + '<div class="cc" style="font-size:11.5px;margin-bottom:6px">What may they SEE?</div>'
      + '<div style="display:flex;flex-direction:column;gap:5px;margin-bottom:10px">'
      +   featureRows("ue"+id, u.features||{})
      + '</div>'
      + '<div class="cc" style="font-size:11.5px;margin-bottom:6px">What may they do?</div>'
      + '<div style="display:flex;flex-direction:column;gap:4px;margin-bottom:10px">'
      +   permissionCheckboxes("ue"+id, u.permissions||[])
      + '</div>'
      + '<div class="cc" style="font-size:11.5px;margin-bottom:6px">Which workspaces?</div>'
      + '<div style="display:flex;flex-direction:column;gap:4px;margin-bottom:10px">'
      +   workspaceCheckboxes("ue"+id, u.workspaces||[])
      + '</div>'
      + '<button class="db-chip" onclick="userSave('+_uarg(id)+')">Save changes</button>'
      + '<span id="uesave_'+_uesc(id)+'" class="cc" style="margin-left:8px;font-size:11px"></span>'
      + '</div>';
  });
}

async function userSave(id){
  const st = document.getElementById("uesave_"+id);
  if(st) st.textContent = "Saving…";
  const payload = {id:id,
                   permissions:_collect("ue"+id,"data-perm","perm"),
                   features:   _collectFeatures("ue"+id),
                   workspaces: _collect("ue"+id,"data-ws","ws")};
  try{
    const j = await (await fetch("/users/update",{method:"POST",
      headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)})).json();
    if(!j.ok){ if(st) st.innerHTML = '<span style="color:var(--red)">'+_uesc(j.error)+'</span>'; return; }
    toast("Saved"); renderUsers();
  }catch(e){ if(st) st.innerHTML = '<span style="color:var(--red)">'+_uesc(String(e))+'</span>'; }
}

async function userInvite(id){
  try{
    const j = await (await fetch("/users/invite",{method:"POST",
      headers:{"Content-Type":"application/json"}, body:JSON.stringify({id:id})})).json();
    if(!j.ok){ toast(j.error||"Could not create a link"); return; }
    const out = document.getElementById("nu_result");
    if(out){ showInviteLink(out, j.invite_url, "this user");
             out.scrollIntoView({behavior:"smooth", block:"nearest"}); }
  }catch(e){ toast(String(e)); }
}

async function userToggle(id, active){
  try{
    const j = await (await fetch("/users/update",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:id, active:active})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    renderUsers();
  }catch(e){ toast(String(e)); }
}

async function userDelete(id){
  if(!confirm("Remove this person's access completely? They will not be able to sign in again.")) return;
  try{
    const j = await (await fetch("/users/delete",{method:"POST",
      headers:{"Content-Type":"application/json"}, body:JSON.stringify({id:id})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    toast("User removed"); renderUsers();
  }catch(e){ toast(String(e)); }
}

window.addEventListener("DOMContentLoaded", function(){ setTimeout(loadMe, 400); });
