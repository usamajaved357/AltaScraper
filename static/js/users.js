// ===================== USERS & PERMISSIONS =====================
// The admin screen for adding people and choosing what each of them can do.
//
// IMPORTANT: everything in this file is a COURTESY, not a control. Hiding a
// button stops nobody -- anyone can open the console and call /submit directly.
// The real enforcement is auth/guard.py, which checks every request on the
// server before the app does anything. This file only avoids showing people
// controls that would fail, and reports the reason plainly when one does.

let ME = null;              // {id,email,name,role,permissions,workspaces,...}
let USERS_META = null;      // {all_permissions:{...}, roles:{...}}

function _uesc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ---- who am I -----------------------------------------------------------
// Drives the top bar. Runs on every page load; failures are silent because a
// signed-out visitor is already being redirected to the sign-in screen.
async function loadMe(){
  try{
    const j = await (await fetch("/users/me")).json();
    if(!j || !j.ok) return;
    ME = j.user; USERS_META = {all_permissions:j.all_permissions, roles:j.roles};
    // Which store the app is on. Used for wording that is only correct on one
    // backend -- see the "not in your sheet" caption in miles_template.js.
    window.DATA_BACKEND = j.backend || "sheets";
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

// Dim the controls this person cannot use, rather than removing them, so the
// app does not look broken or subtly different for different people. The title
// says why. Anything missed here still fails safely at the server.
function applyPermissionsToUI(){
  if(!ME) return;
  const RULES = [
    ["publish",         '[onclick*="submitAll"],[onclick*="pushLive"],[onclick*="bulkHandling"]'],
    ["approve_delete",  '[onclick*="bulkStatus"],[onclick*="bulkDelete"],[onclick*="approve"]'],
    ["ppc",             '[data-sec="ppc"]'],
    ["manage_accounts", '#aibtn,[onclick*="openAccountEditor"],[onclick*="openCurrentAccountSettings"]'],
  ];
  RULES.forEach(function(r){
    if(can(r[0])) return;
    document.querySelectorAll(r[1]).forEach(function(el){
      el.style.opacity = ".45";
      el.style.pointerEvents = "none";
      el.title = "You do not have permission for this. Needs: "
               + ((USERS_META && USERS_META.all_permissions[r[0]]) || r[0]);
    });
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
  USERS_META = {all_permissions:j.all_permissions, roles:j.roles};

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
      +    '<button class="db-chip" onclick="userEdit('+JSON.stringify(u.id)+')">Edit</button>'
      +    '<button class="db-chip" onclick="userInvite('+JSON.stringify(u.id)+')" '
      +      'title="Issue a fresh one-time link. Also use this as a password reset — it clears the old password.">New link</button>'
      +    '<button class="db-chip" onclick="userToggle('+JSON.stringify(u.id)+','+(u.active?"false":"true")+')">'
      +      (u.active?"Disable":"Enable")+'</button>'
      +    '<button class="db-chip" style="color:var(--red);border-color:var(--red-line)" '
      +      'onclick="userDelete('+JSON.stringify(u.id)+')">Delete</button>'
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
    +  '<div class="cc" style="font-size:11.5px;margin-bottom:6px">What may they do?</div>'
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
                {id:"dropshipping", label:"Dropshipping"}]
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
      + '<div class="cc" style="font-size:11.5px;margin-bottom:6px">What may they do?</div>'
      + '<div style="display:flex;flex-direction:column;gap:4px;margin-bottom:10px">'
      +   permissionCheckboxes("ue"+id, u.permissions||[])
      + '</div>'
      + '<div class="cc" style="font-size:11.5px;margin-bottom:6px">Which workspaces?</div>'
      + '<div style="display:flex;flex-direction:column;gap:4px;margin-bottom:10px">'
      +   workspaceCheckboxes("ue"+id, u.workspaces||[])
      + '</div>'
      + '<button class="db-chip" onclick="userSave('+JSON.stringify(id)+')">Save changes</button>'
      + '<span id="uesave_'+_uesc(id)+'" class="cc" style="margin-left:8px;font-size:11px"></span>'
      + '</div>';
  });
}

async function userSave(id){
  const st = document.getElementById("uesave_"+id);
  if(st) st.textContent = "Saving…";
  const payload = {id:id,
                   permissions:_collect("ue"+id,"data-perm","perm"),
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
