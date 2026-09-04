// static/js/permissions.js — user permissions, laid out the way Seller Central
// lays them out.
//
//     "make the user permission a separate page exact copy paste of like amazon
//      and how amazon distributes the permissions columns ... the current
//      permission page is too messy and do not looks good"
//
// It was seventeen dropdowns stacked in a modal. Seller Central puts the same
// decision in a TABLE: the thing being controlled down the left, and three
// columns across the top — None, View, View & Edit — with one radio per row.
// The difference is not decoration. A column of radios can be read down: you
// see at a glance that this person has View on everything in Money and nothing
// in Operations. Seventeen dropdowns each have to be opened to be read.
//
// AND A GROUP CAN BE SET IN ONE GO, which is how Amazon does it too, because
// the honest unit of a decision is usually "can they see the money" rather than
// "can they see Hourly Sales".
//
// WHAT THIS PAGE DOES NOT DO: decide anything. Every level here is saved to the
// server and enforced there (auth/guard.py). Hiding a screen in the browser is
// courtesy; refusing the request is the security.

let PERM = { users: [], accounts: [], meta: null, editing: null, draft: null,
             note: "", loading: false };

const PERM_LEVELS = [
  { v: "none", label: "No access",
    why: "The screen is not shown at all — not greyed out, no trace of it." },
  { v: "view", label: "View only",
    why: "They can open it and read it. Buttons that change anything are gone." },
  { v: "edit", label: "View &amp; edit",
    why: "Full use of that area." },
];

function _pesc(s) { return (typeof esc === "function") ? esc(s) : String(s == null ? "" : s); }

async function permLoad() {
  PERM.loading = true; PERM.note = ""; permRender();
  try {
    // /users/list, and the vocabulary comes back at the TOP LEVEL rather than
    // under a `meta` key -- checked against the route rather than assumed, so
    // this page cannot list a feature that no longer exists or miss one that
    // was just added.
    const j = await (await fetch("/users/list")).json();
    if (j && j.ok) {
      PERM.users = j.users || [];
      PERM.meta = j;
    } else {
      PERM.note = (j && j.error) || "Could not read the users.";
    }
  } catch (e) {
    PERM.note = "Could not read the users: " + e;
  }
  // The accounts, for the outer boundary. A separate call because /users/list
  // does not carry them, and this page cannot ask somebody to choose accounts
  // it has not been told about.
  try {
    const a = await (await fetch("/accounts/list")).json();
    PERM.accounts = (a && (a.accounts || a.views)) || [];
  } catch (e) {
    PERM.accounts = [];
  }
  PERM.loading = false;
  permRender();
}

function permEdit(userId) {
  const u = PERM.users.find(function (x) { return String(x.id) === String(userId); });
  if (!u) return;
  PERM.editing = u;
  // A DRAFT, so nothing is saved until Save is pressed. A permissions screen
  // that writes as you click is one where a mis-click is a live change.
  PERM.draft = {
    features: Object.assign({}, u.features || {}),
    workspaces: (u.workspaces || []).slice(),
    role: u.role || "lister",
  };
  permRender();
}

function permBack() {
  PERM.editing = null; PERM.draft = null;
  permRender();
}

function permSet(feat, level) {
  if (!PERM.draft) return;
  if (level === "") delete PERM.draft.features[feat];   // inherit = absent
  else PERM.draft.features[feat] = level;
  permRender();
}

/* Set every feature in a group at once. The honest unit of most decisions.
 *
 * NAMED permDraftSetGroup, NOT permSetGroup, and that is a bug fix rather than
 * a preference. users.js has its own top-level `function permSetGroup(gid,
 * level)` -- a DIFFERENT function taking a different first argument (a group
 * id, and it sets <select> values on the Users screen). Both files share one
 * global scope, users.js loads second, so its version replaced this one.
 *
 * The buttons on this screen were therefore calling the Users screen's
 * function with a group TITLE where it expects an id. It looks for
 * `.permgroup[data-gid="<title>"]`, finds nothing, and returns -- so setting a
 * whole group's level here did nothing at all, silently, with no error.
 *
 * Found by driving the app in a browser, and now caught by
 * test_global_name_clashes.py.
 */
function permDraftSetGroup(title, level) {
  if (!PERM.draft || !PERM.meta) return;
  const g = (PERM.meta.feature_groups || []).find(function (x) { return x.title === title; });
  if (!g) return;
  (g.features || []).forEach(function (f) {
    if (level === "") delete PERM.draft.features[f];
    else PERM.draft.features[f] = level;
  });
  permRender();
}

function permToggleWs(ws) {
  if (!PERM.draft) return;
  const at = PERM.draft.workspaces.indexOf(ws);
  if (at >= 0) PERM.draft.workspaces.splice(at, 1);
  else PERM.draft.workspaces.push(ws);
  permRender();
}

function _level(feat) {
  const parent = (PERM.meta && PERM.meta.feature_parent) || {};
  const has = Object.prototype.hasOwnProperty.call(PERM.draft.features, feat);
  if (has) return PERM.draft.features[feat];
  return parent[feat] ? "" : "view";   // a page inherits; an area defaults to view
}

function permRender() {
  const box = document.getElementById("perm_body");
  if (!box) return;
  if (PERM.loading) { box.innerHTML = '<div class="cc" style="padding:14px">Loading…</div>'; return; }
  if (PERM.note) { box.innerHTML = '<div class="sresfail">' + _pesc(PERM.note) + "</div>"; return; }

  if (!PERM.editing) { box.innerHTML = permListHtml(); return; }
  box.innerHTML = permEditHtml();
}

function permListHtml() {
  if (!PERM.users.length) {
    return '<div class="card" style="padding:18px"><div class="cc">No users yet. ' +
      "Invite somebody to give them access to specific accounts and areas.</div></div>";
  }
  let h = '<div class="card" style="overflow-x:auto"><table class="stk-table"><thead><tr>' +
    "<th>Name</th><th>Email</th><th>Role</th><th>Accounts</th><th>Access</th><th></th>" +
    "</tr></thead><tbody>";
  PERM.users.forEach(function (u) {
    const ws = (u.workspaces || []);
    const all = ws.indexOf("*") >= 0;
    // Count what they actually have, so the row says something at a glance.
    const feats = u.features || {};
    const none = Object.keys(feats).filter(function (k) { return feats[k] === "none"; }).length;
    h += "<tr>" +
      '<td style="font-weight:600">' + _pesc(u.name || "—") + "</td>" +
      '<td class="cc" style="font-size:11.5px">' + _pesc(u.email || "") + "</td>" +
      "<td>" + _pesc(u.role || "") + "</td>" +
      "<td>" + (all
        ? '<span class="ld-pill warn">every account</span>'
        : '<span class="ld-pill ok">' + ws.length + " account" + (ws.length === 1 ? "" : "s") + "</span>") +
      "</td>" +
      '<td class="cc" style="font-size:11.5px">' +
      (none ? none + " area" + (none === 1 ? "" : "s") + " hidden" : "everything") + "</td>" +
      '<td><button class="db-chip" onclick="permEdit(' + jsArg(String(u.id)) + ')">' +
      '<i class="ti ti-key"></i> Manage permissions</button></td>' +
      "</tr>";
  });
  h += "</tbody></table></div>";
  return h;
}

function permEditHtml() {
  const u = PERM.editing;
  const meta = PERM.meta || {};
  const F = meta.all_features || {};
  const parent = meta.feature_parent || {};
  const groups = meta.feature_groups || [];

  let h = '<div class="perm-head">' +
    '<button class="db-chip" onclick="permBack()"><i class="ti ti-arrow-left"></i> All users</button>' +
    '<div><div style="font-weight:650;font-size:15px">' + _pesc(u.name || u.email) + "</div>" +
    '<div class="cc" style="font-size:12px">' + _pesc(u.email || "") + "</div></div>" +
    '<div style="margin-left:auto;display:flex;gap:7px">' +
    '<button class="db-chip" onclick="permBack()">Cancel</button>' +
    '<button class="primary" onclick="permSave()"><i class="ti ti-check"></i> Save</button>' +
    "</div></div>";

  // ---- which accounts ----------------------------------------------------
  // First, because it is the bigger decision: no amount of feature access makes
  // another company's numbers your business.
  h += '<div class="card" style="padding:14px;margin-bottom:12px">' +
    '<div style="font-weight:600;margin-bottom:3px">Which accounts</div>' +
    '<div class="cc" style="font-size:11.5px;margin-bottom:9px;max-width:660px">' +
    "This is the outer boundary. Everything below only applies inside the accounts " +
    "chosen here — a person with no account has no access to anything, whatever " +
    "the table says." + "</div>" +
    '<div class="perm-ws">';
  const wsAll = PERM.draft.workspaces.indexOf("*") >= 0;
  h += '<label class="perm-wsopt' + (wsAll ? " on" : "") + '">' +
    '<input type="checkbox"' + (wsAll ? " checked" : "") +
    ' onchange="permToggleWs(\'*\')"> Every account (now and in future)</label>';
  (PERM.accounts || []).forEach(function (w) {
    const id = String(w.id || w);
    const on = PERM.draft.workspaces.indexOf(id) >= 0;
    h += '<label class="perm-wsopt' + (on ? " on" : "") + (wsAll ? " dim" : "") + '">' +
      '<input type="checkbox"' + (on ? " checked" : "") +
      (wsAll ? " disabled" : "") +
      ' onchange="permToggleWs(' + jsArg(id) + ')"> ' +
      _pesc(w.label || id) + "</label>";
  });
  h += "</div></div>";

  // ---- the permission table ----------------------------------------------
  h += '<div class="card" style="overflow-x:auto;padding:0">' +
    '<table class="perm-table"><thead><tr>' +
    "<th>Area</th>" +
    PERM_LEVELS.map(function (l) {
      return '<th class="perm-col" title="' + l.why.replace(/"/g, "") + '">' + l.label + "</th>";
    }).join("") +
    "<th></th></tr></thead><tbody>";

  const rowFor = function (k) {
    if (!F[k]) return "";
    const isChild = !!parent[k];
    const v = _level(k);
    let r = '<tr class="' + (isChild ? "perm-child" : "perm-area") + '">' +
      '<td><div style="font-weight:' + (isChild ? "400" : "600") + '">' +
      _pesc(F[k]) + "</div>" +
      (isChild
        ? '<div class="cc" style="font-size:10.5px">part of ' + _pesc(F[parent[k]] || parent[k]) + "</div>"
        : "") +
      "</td>";
    PERM_LEVELS.forEach(function (l) {
      r += '<td class="perm-col"><input type="radio" name="perm_' + _pesc(k) + '"' +
        (v === l.v ? " checked" : "") +
        ' onchange="permSet(' + jsArg(k) + ',' + jsArg(l.v) + ')"></td>';
    });
    // Inherit is only meaningful for a page that sits under an area, and it is
    // stored as ABSENT rather than as a word -- which is what makes it follow
    // its area on the server too.
    r += "<td>" + (isChild
      ? '<label class="perm-inherit' + (v === "" ? " on" : "") + '">' +
        '<input type="radio" name="perm_' + _pesc(k) + '"' + (v === "" ? " checked" : "") +
        ' onchange="permSet(' + jsArg(k) + ',\'\')"> follow ' +
        _pesc(F[parent[k]] || parent[k]) + "</label>"
      : "") + "</td></tr>";
    return r;
  };

  groups.forEach(function (g) {
    h += '<tr class="perm-group"><td>' + _pesc(g.title) + "</td>" +
      PERM_LEVELS.map(function (l) {
        return '<td class="perm-col"><button class="perm-all" title="Set every row ' +
          'in ' + _pesc(g.title) + ' to ' + l.label.replace(/&amp;/g, "&") + '" ' +
          'onclick="permDraftSetGroup(' + jsArg(g.title) + ',' + jsArg(l.v) + ')">' +
          "set all</button></td>";
      }).join("") + "<td></td></tr>";
    (g.features || []).forEach(function (k) { h += rowFor(k); });
  });
  h += "</tbody></table></div>";

  h += '<div class="cc" style="font-size:11.5px;margin-top:10px;max-width:720px;line-height:1.55">' +
    "<b>No access</b> means the screen is not shown at all — not greyed out, no trace " +
    "of it in the menu. <b>View only</b> keeps the screen and removes anything that " +
    "changes something. Nothing here is only a matter of what is drawn: the server " +
    "refuses the request as well, so an address typed by hand is refused too." +
    "</div>";
  return h;
}

async function permSave() {
  if (!PERM.editing || !PERM.draft) return;
  const body = {
    id: PERM.editing.id,
    features: PERM.draft.features,
    workspaces: PERM.draft.workspaces,
  };
  try {
    const j = await (await fetch("/users/update", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })).json();
    if (!j || !j.ok) {
      if (typeof toast === "function") toast((j && j.error) || "Could not save.");
      return;
    }
    if (typeof toast === "function") toast("Saved.");
    PERM.editing = null; PERM.draft = null;
    await permLoad();
  } catch (e) {
    if (typeof toast === "function") toast("Could not save: " + e);
  }
}

function permissionsOnOpen() { permLoad(); }
