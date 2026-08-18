// static/js/navgroups.js — the sidebar's expanding master items.
//
//     "i want the tools to be arranged under the relevant master tool, like we
//      have in amazon, manage inventory expands into manage all inventory, sell
//      globally, fulfillment by amazon etc etc"
//
// A master row opens to reveal the screens under it, the way Seller Central's
// "Manage Inventory" does. The flat list had reached twenty-two items and every
// new one made the rest harder to find.
//
// This file only OPENS AND CLOSES things. It does not route, it does not touch
// navTo, and every navitem keeps the data-sec and onclick it already had — so
// the active-item highlight, the URL routing and the deep links are untouched
// by the regrouping. That separation is deliberate: nav that decides both which
// screen is showing and which drawer is open is nav that breaks both at once.

const NAVGRP_KEY = "navgroups.open";

// WHICH GROUP EACH SCREEN LIVES IN.
//
// Derived from the DOM rather than written out here. A hand-kept second list
// would be a copy of the sidebar that drifts from it the first time a screen
// moves, and the symptom — one screen whose group will not open — is invisible
// until someone happens to visit that screen.
function navGroupOf(sec) {
  if (!sec) return "";
  const el = document.querySelector('.navkids .navitem[data-sec="' + sec + '"]');
  const grp = el && el.closest(".navgroup");
  return grp ? (grp.dataset.grp || "") : "";
}

function navGroupOpenSet() {
  try {
    const raw = localStorage.getItem(NAVGRP_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch (e) {
    return new Set();
  }
}

function navGroupSave(set) {
  try {
    localStorage.setItem(NAVGRP_KEY, JSON.stringify(Array.from(set)));
  } catch (e) {}
}

function navGroupApply(name, open) {
  const grp = document.querySelector('.navgroup[data-grp="' + name + '"]');
  if (!grp) return;
  grp.classList.toggle("open", !!open);
  // Told out loud, not just drawn. A chevron is not announced by a screen
  // reader and neither is a CSS class.
  const master = grp.querySelector(".navmaster");
  if (master) master.setAttribute("aria-expanded", open ? "true" : "false");
  navGroupBadges();
}

function navGroupToggle(name) {
  const set = navGroupOpenSet();
  const willOpen = !set.has(name);
  if (willOpen) set.add(name);
  else set.delete(name);
  navGroupSave(set);
  navGroupApply(name, willOpen);
}

// A BADGE INSIDE A CLOSED GROUP IS A BADGE NOBODY SEES.
//
// Stock alerts and monitor alerts are the reason those screens exist, and
// collapsing a group would have hidden exactly the thing that needed
// attention — the one failure that makes grouping worse than the flat list it
// replaced. So while a group is shut, its children's badges are summed onto the
// master; when it is open the children speak for themselves and the master
// falls silent rather than saying it twice.
function navGroupBadges() {
  document.querySelectorAll(".navgroup").forEach(function (grp) {
    const dot = grp.querySelector(".navmbadge");
    if (!dot) return;
    if (grp.classList.contains("open")) {
      dot.style.display = "none";
      dot.textContent = "";
      return;
    }
    let total = 0;
    let any = false;
    grp.querySelectorAll(".navkids .navitem span[id$='_badge']").forEach(function (b) {
      if (!b || b.style.display === "none") return;
      any = true;
      const n = parseInt((b.textContent || "").replace(/[^0-9]/g, ""), 10);
      if (!isNaN(n)) total += n;
    });
    if (!any) {
      dot.style.display = "none";
      dot.textContent = "";
    } else {
      dot.style.display = "inline-block";
      dot.textContent = total > 0 ? String(total) : "";
      dot.classList.toggle("dotonly", !(total > 0));
    }
  });
}

// THE GROUP YOU ARE IN IS ALWAYS OPEN.
//
// Without this the highlight sits inside a closed drawer and the app looks like
// it has forgotten where you are. Called after every navTo, and on load, when
// the active screen may have come from a deep link into a group the user last
// left shut.
function navGroupSyncActive(sec) {
  const name = navGroupOf(sec || (typeof CUR_SEC !== "undefined" ? CUR_SEC : ""));
  if (!name) {
    navGroupBadges();
    return;
  }
  const set = navGroupOpenSet();
  if (!set.has(name)) {
    set.add(name);
    navGroupSave(set);
  }
  navGroupApply(name, true);
  // Mark the master too, so a collapsed group still shows which one holds you.
  document.querySelectorAll(".navgroup").forEach(function (g) {
    g.classList.toggle("hasactive", (g.dataset.grp || "") === name);
  });
}

function navGroupsInit() {
  const set = navGroupOpenSet();
  // FIRST RUN OPENS THE ONE YOU ARE IN, AND NOTHING ELSE. Opening everything
  // would reproduce the flat list the grouping exists to replace; opening
  // nothing would show a stranger seven closed drawers and no way to tell what
  // the app does. One open group demonstrates the pattern.
  document.querySelectorAll(".navgroup").forEach(function (g) {
    const name = g.dataset.grp || "";
    navGroupApply(name, set.has(name));
  });
  navGroupSyncActive(typeof CUR_SEC !== "undefined" ? CUR_SEC : "listings");
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", navGroupsInit);
  } else {
    navGroupsInit();
  }
}
