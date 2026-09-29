// static/js/team.js -- the Team screen (read.txt Priority 3, 29 Sep 2026).
//
// THE ONE PLACE TEAM MEMBERS ARE MANAGED. It is not a second user editor: the
// list, the add form, invites, enable/disable, delete and the editor are all
// users.js (renderUsers and friends), which now draws into #teambody when this
// screen exists. The "Users" button opens this screen instead of the old modal.
// This file adds only what a whole-team view needs: a summary line and the
// search/state filter, both applied to rows renderUsers already drew.
//
// Who may open it: people with manage_users -- the same as /users/* on the
// server (auth/guard.py), so the screen and the requests agree.

function teamOnOpen(){ renderUsers(); }

// The rows renderUsers drew carry data-team-* attributes; filtering hides rows,
// never refetches, so typing in the search box costs nothing.
function teamFilter(){
  const q = ((document.getElementById("team_q")||{}).value||"").trim().toLowerCase();
  const st = (document.getElementById("team_state")||{}).value||"";
  let shown = 0, total = 0;
  document.querySelectorAll("#teambody tr[data-team-id]").forEach(function(tr){
    total++;
    const hay = (tr.getAttribute("data-team-search")||"");
    const ok = (!q || hay.indexOf(q) >= 0) && (!st || tr.getAttribute("data-team-state") === st);
    tr.style.display = ok ? "" : "none";
    if(ok) shown++;
  });
  const host = document.getElementById("team_summary");
  if(host && total && (q || st)) host.setAttribute("data-filtered", shown + " of " + total + " shown");
  else if(host) host.removeAttribute("data-filtered");
  // A filter that hides everybody says so where the list was, not only in the
  // summary line.
  const none = document.getElementById("team_nomatch");
  if(none) none.hidden = !(total && !shown);
  teamSummary();
}

// One line: how many people, in which state. Counted from the drawn rows so it
// always describes exactly what is on screen.
function teamSummary(){
  const host = document.getElementById("team_summary");
  if(!host) return;
  const rows = document.querySelectorAll("#teambody tr[data-team-id]");
  if(!rows.length){ host.textContent = ""; return; }
  const n = {active:0, invited:0, disabled:0, expired:0};
  rows.forEach(function(tr){ const s = tr.getAttribute("data-team-state"); if(n[s] !== undefined) n[s]++; });
  const bits = [rows.length + (rows.length === 1 ? " person" : " people"), n.active + " active"];
  if(n.invited) bits.push(n.invited + " not yet accepted their invite");
  if(n.expired) bits.push(n.expired + " with an expired invite");
  if(n.disabled) bits.push(n.disabled + " disabled");
  const f = host.getAttribute("data-filtered");
  host.textContent = bits.join(" · ") + (f ? " — " + f : "");
}
