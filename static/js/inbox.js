// ===================== CUSTOMER MESSAGES =====================
//
// Owner, 30 Sep 2026: "add the customer messages section in the app, if i
// receive any message i should be able to see it in the app".
//
// Amazon's API cannot read buyer messages, so they are read from the mailbox
// Seller Central emails them to (routes/buyer_inbox_routes.py,
// domain/buyer_inbox.py). This screen only READS: opening a conversation marks
// it read in this app, never in the mailbox, and nothing here sends anything to
// a buyer -- the reply link opens Seller Central.
//
// EVERY REQUEST NAMES ITS ACCOUNT (CLAUDE.md Rule 14) and every reply is
// checked against screenScope() before it is drawn, so one account's customers
// can never appear under another. INBOX is reset in screenstate.js.

let INBOX = {data: null, threads: [], openKey: "", thread: null, loading: false,
             error: "", reloadError: "", seq: 0, tseq: 0, loadedFor: "", unread: 0,
             checking: false};

function _ibxAcct(){ return (typeof acctId === "function") ? acctId() : ""; }

// A url naming the open account, plus any extra query values.
function _ibxUrl(path, extra){
  const qs = [];
  const a = _ibxAcct();
  if(a) qs.push("account=" + encodeURIComponent(a));
  Object.keys(extra || {}).forEach(function(k){
    if(extra[k]) qs.push(encodeURIComponent(k) + "=" + encodeURIComponent(extra[k]));
  });
  return path + (qs.length ? "?" + qs.join("&") : "");
}

function _ibxPost(path, obj){
  return fetch(path, {method: "POST", headers: {"Content-Type": "application/json"},
                      body: JSON.stringify(acctBody(obj || {}))});
}

// A stored time (UTC ISO) in the viewer's own clock.
function _ibxWhen(iso){
  if(!iso) return "";
  const d = new Date(iso);
  if(isNaN(d.getTime())) return String(iso);
  const now = new Date();
  const same = d.toDateString() === now.toDateString();
  return same ? d.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})
              : d.toLocaleDateString([], {day: "numeric", month: "short"}) + " "
                + d.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
}

function _ibxThreadOf(key){
  return (INBOX.threads || []).find(function(t){ return t.key === key; }) || null;
}

function inboxOnOpen(){
  if(!INBOX.data || INBOX.loadedFor !== _ibxAcct()) return inboxLoad();
  inboxRender();
}

async function inboxLoad(){
  const body = document.getElementById("ibx_body");
  if(!body) return;
  const sc = (typeof screenScope === "function") ? screenScope() : null;
  const mine = ++INBOX.seq;
  INBOX.loading = true;
  INBOX.error = "";
  if(!INBOX.data) body.innerHTML = '<div class="cc ibx-wait"><span class="genspin"></span> '
    + 'Reading stored messages…</div>';
  let j = null, status = 0;
  try{
    const r = await fetch(_ibxUrl("/inbox/threads"));
    status = r.status;
    j = await r.json();
  }catch(e){ j = {ok: false, error: String(e)}; }
  if(mine !== INBOX.seq) return;
  if(sc && typeof screenStillIn === "function" && !screenStillIn(sc)) return;
  INBOX.loading = false;
  if(!j || !j.ok){
    const why = (j && j.error) || ("The server answered " + status);
    // A RELOAD THAT FAILS KEEPS WHAT IS SHOWN, and says so above it. Only a
    // screen with nothing on it yet becomes the error.
    if(INBOX.data && INBOX.loadedFor === _ibxAcct()){ INBOX.reloadError = why; }
    else { INBOX.error = why; INBOX.data = null; }
    inboxRender();
    _ibxRefocus(INBOX.openKey);
    return;
  }
  INBOX.data = j;
  INBOX.reloadError = "";
  INBOX.threads = j.threads || [];
  INBOX.loadedFor = _ibxAcct();
  inboxSetBadge(j.connected ? j.unread : 0);
  if(INBOX.openKey && !_ibxThreadOf(INBOX.openKey)){ INBOX.openKey = ""; INBOX.thread = null; }
  inboxRender();
  _ibxRefocus(INBOX.openKey);
}

function _ibxMetaHtml(){
  const d = INBOX.data || {}, st = d.status || {}, n = (INBOX.threads || []).length;
  return n + " conversation" + (n === 1 ? "" : "s")
    + (d.unread ? " · <b>" + d.unread + " unread</b>" : "")
    + (st.last_ok_at ? " · checked " + esc(_ibxWhen(st.last_ok_at)) : "");
}

function inboxRender(){
  const body = document.getElementById("ibx_body");
  if(!body) return;
  if(INBOX.error){
    body.innerHTML = uiError("Could not load customer messages", INBOX.error, "inboxLoad", "inbox");
    return;
  }
  const d = INBOX.data;
  if(!d) return;
  const st = d.status || {};
  if(!d.connected){
    const admin = (typeof can !== "function") || can("manage_accounts");
    body.innerHTML = uiEmpty("No mailbox connected",
      esc("Connect the email address Seller Central sends buyer messages to."),
      admin ? '<button class="db-chip" onclick="inboxOpenSettings()"><i class="ti ti-plug-connected"></i> Connect mailbox</button>'
            : '<span class="cc">Ask the account owner to connect it under Settings.</span>');
    return;
  }
  let h = "";
  if(INBOX.reloadError) h += uiNote("bad", "Could not reload — showing what was already here", INBOX.reloadError);
  if(st.last_error){
    h += uiNote("bad", "The last mailbox check failed",
                st.last_error + (st.last_error_at ? " (" + _ibxWhen(st.last_error_at) + ")" : ""));
  }
  const threads = INBOX.threads || [];
  if(!threads.length){
    h += uiEmpty("No buyer messages yet",
      esc(st.last_ok_at ? ("Mailbox " + (d.mailbox_user || "") + " checked " + _ibxWhen(st.last_ok_at)
                           + ". New messages appear within 10 minutes.")
                        : "The mailbox has not been checked yet. It is checked every 10 minutes."),
      '<button class="db-chip" onclick="inboxRefresh()"><i class="ti ti-mail-down"></i> Check now</button>');
    body.innerHTML = h;
    return;
  }
  h += '<div class="ibx-meta cc" id="ibx_meta">' + _ibxMetaHtml() + "</div>";
  h += '<div class="ibx-split' + (INBOX.openKey ? " has-open" : "") + '">'
    + '<nav class="ibx-list" aria-label="Conversations">';
  threads.forEach(function(t){
    const on = t.key === INBOX.openKey;
    h += '<button type="button" class="ibx-row' + (t.unread ? " unread" : "") + (on ? " on" : "")
      + '" aria-current="' + (on ? "true" : "false") + '" data-key="' + esc(t.key)
      + '" onclick="inboxOpen(' + jsArg(t.key) + ')">'
      + '<span class="ibx-dot" aria-hidden="true"></span>'
      + '<span class="ibx-row-main"><span class="ibx-row-top">'
      + '<b class="ibx-oid">' + esc(t.order_id || t.from_alias || "") + "</b>"
      + (t.marketplace ? '<span class="ibx-mkt">' + esc(t.marketplace) + "</span>" : "")
      + '<span class="ibx-when">' + esc(_ibxWhen(t.last_at)) + "</span></span>"
      + '<span class="ibx-subj">' + esc(t.subject || "(no subject)") + "</span>"
      + '<span class="ibx-snip">' + esc(t.snippet || "") + "</span></span>"
      + (t.unread ? '<span class="ibx-count"><span class="ibx-sr">unread: </span>' + t.unread + "</span>" : "")
      + "</button>";
  });
  h += '</nav><section class="ibx-thread" id="ibx_thread" aria-label="Conversation">'
    + inboxThreadHtml() + "</section></div>";
  body.innerHTML = h;
}

function inboxThreadHtml(){
  if(!INBOX.openKey) return '<div class="ibx-pick cc"><i class="ti ti-message-circle"></i> Choose a conversation to read it.</div>';
  const t = _ibxThreadOf(INBOX.openKey) || {};
  const th = INBOX.thread;
  const url = (th && th.reply_url) || t.reply_url || (INBOX.data && INBOX.data.reply_url) || "";
  let h = '<div class="ibx-th-h">'
    + (t.order_id
        ? '<a href="#" class="ibx-order" onclick="return inboxOpenOrder(' + jsArg(t.order_id)
          + ')" title="Open this order on the Orders screen"><i class="ti ti-receipt"></i> ' + esc(t.order_id) + "</a>"
        : '<span class="ibx-order">' + esc(t.from_alias || "") + "</span>")
    + '<span class="ibx-th-sp"></span>'
    + (url ? '<a class="db-chip" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer" '
             + 'title="Replying is done in Seller Central"><i class="ti ti-external-link"></i> Reply in Seller Central</a>' : "")
    + '<button type="button" class="ibx-x" onclick="inboxClose()" aria-label="Close conversation"><i class="ti ti-x"></i></button>'
    + "</div>";
  if(!th) return h + '<div class="cc ibx-wait"><span class="genspin"></span> Opening…</div>';
  if(th.error) return h + uiError("Could not open this conversation", th.error, "inboxReopen", "inbox");
  h += '<div class="ibx-msgs">';
  (th.messages || []).forEach(function(m){
    const app = m.kind === "app";
    h += '<article class="ibx-msg' + (app ? " app" : "") + '">'
      + '<div class="ibx-msg-h"><b>' + esc(app ? "Sent by the app" + (m.sent_by ? " · " + m.sent_by : "") : "Buyer")
      + '</b><span class="cc">' + esc(_ibxWhen(m.at)) + "</span></div>"
      + (app ? '<div class="ibx-msg-sub cc">' + esc((m.action || "") + (m.ok ? "" : " — Amazon refused it: " + (m.error || ""))) + "</div>"
             : (m.subject ? '<div class="ibx-msg-sub">' + esc(m.subject) + "</div>" : ""))
      + '<div class="ibx-msg-b">' + esc(m.body_text || "") + "</div></article>";
  });
  return h + "</div>";
}

function _ibxDrawThread(){
  const el = document.getElementById("ibx_thread");
  if(el) el.innerHTML = inboxThreadHtml();
}

// A redraw replaces the focused row; put the keyboard back on it. On a phone
// the list steps aside for an open conversation, so the keyboard goes to the
// conversation's close button instead of into nothing.
function _ibxRefocus(key){
  if(!key) return;
  try{
    const rows = document.querySelectorAll("#ibx_body .ibx-row");
    for(let i = 0; i < rows.length; i++){
      if(rows[i].getAttribute("data-key") !== key) continue;
      if(rows[i].offsetParent !== null){ rows[i].focus(); return; }
      break;
    }
    if(INBOX.openKey === key){
      const x = document.querySelector("#ibx_thread .ibx-x");
      if(x) x.focus();
    }
  }catch(e){}
}

async function inboxOpen(key){
  const t = _ibxThreadOf(key);
  if(!t) return;
  INBOX.openKey = key;
  INBOX.thread = null;
  inboxRender();
  _ibxRefocus(key);
  const sc = (typeof screenScope === "function") ? screenScope() : null;
  const mine = ++INBOX.tseq;
  let j = null;
  try{
    const r = await fetch(_ibxUrl("/inbox/thread", t.order_id ? {order_id: t.order_id}
                                                               : {from_alias: t.from_alias}));
    j = await r.json();
  }catch(e){ j = {ok: false, error: String(e)}; }
  if(mine !== INBOX.tseq || INBOX.openKey !== key) return;
  if(sc && typeof screenStillIn === "function" && !screenStillIn(sc)) return;
  INBOX.thread = (j && j.ok) ? j : {error: (j && j.error) || "The conversation could not be read."};
  _ibxDrawThread();
  _ibxRefocus(key);
  if(j && j.ok && t.unread) inboxMarkRead(t, sc);
}

function inboxReopen(){ if(INBOX.openKey) inboxOpen(INBOX.openKey); }

function inboxClose(){
  const key = INBOX.openKey;
  INBOX.openKey = "";
  INBOX.thread = null;
  inboxRender();
  _ibxRefocus(key);
}

// Read IN THIS APP only. A view-only user is refused (it needs "edit"), which
// leaves the thread unread and says nothing -- reading it still worked.
async function inboxMarkRead(t, sc){
  let j = null;
  try{
    const r = await _ibxPost("/inbox/read", t.order_id ? {order_id: t.order_id}
                                                       : {from_alias: t.from_alias});
    j = await r.json();
  }catch(e){ return; }
  if(sc && typeof screenStillIn === "function" && !screenStillIn(sc)) return;
  if(!j || !j.ok) return;
  t.unread = 0;
  if(INBOX.data) INBOX.data.unread = j.unread;
  inboxSetBadge(j.unread);
  const meta = document.getElementById("ibx_meta");
  if(meta) meta.innerHTML = _ibxMetaHtml();
  const row = document.querySelector('#ibx_body .ibx-row[data-key="' + (window.CSS && CSS.escape ? CSS.escape(t.key) : t.key) + '"]');
  if(row){
    row.classList.remove("unread");
    const c = row.querySelector(".ibx-count");
    if(c) c.remove();
  }
}

async function inboxRefresh(){
  if(INBOX.checking) return;
  INBOX.checking = true;
  const btn = document.getElementById("ibx_check");
  if(btn) btn.disabled = true;
  const sc = (typeof screenScope === "function") ? screenScope() : null;
  let j = null, status = 0;
  try{
    const r = await _ibxPost("/inbox/refresh", {});
    status = r.status;
    j = await r.json();
  }catch(e){ j = {ok: false, error: String(e)}; }
  INBOX.checking = false;
  if(btn) btn.disabled = false;
  if(sc && typeof screenStillIn === "function" && !screenStillIn(sc)) return;
  if(j && j.ok){
    toast(j.new ? (j.new + " new message" + (j.new === 1 ? "" : "s")) : "No new messages");
  }else{
    toast("Mailbox check failed: " + ((j && j.error) || ("the server answered " + status)), {err: true});
  }
  inboxLoad();
}

function inboxOpenOrder(oid){
  if(typeof navTo === "function") navTo("orders");
  const q = document.getElementById("ord_q");
  if(q) q.value = oid;
  if(typeof ordersFilter === "function") ordersFilter(oid);
  return false;
}

async function inboxOpenSettings(){
  if(typeof openAISettings !== "function") return;
  await openAISettings();
  const box = document.getElementById("mbx_box");
  if(box && box.scrollIntoView) box.scrollIntoView({block: "start"});
}

// ---- the nav badge ----------------------------------------------------------
function inboxSetBadge(n){
  INBOX.unread = Number(n) || 0;
  const b = document.getElementById("ibx_badge");
  if(b){
    b.style.display = INBOX.unread > 0 ? "" : "none";
    b.textContent = INBOX.unread > 0 ? (INBOX.unread > 99 ? "99+" : String(INBOX.unread)) : "";
  }
  if(typeof navGroupBadges === "function") navGroupBadges();
}

async function inboxBadgePoll(){
  if(!_ibxAcct()) return;
  if(typeof sectionLevel === "function" && sectionLevel("inbox") === "none") return;
  const sc = (typeof screenScope === "function") ? screenScope() : null;
  try{
    const j = await (await fetch(_ibxUrl("/inbox/unread"))).json();
    if(sc && typeof screenStillIn === "function" && !screenStillIn(sc)) return;
    if(!j || !j.ok) return;
    inboxSetBadge(j.connected ? j.unread : 0);
  }catch(e){ /* a badge that cannot be read must not break the page */ }
}

(function(){
  if(typeof document === "undefined") return;
  const go = function(){
    inboxBadgePoll();
    // Every two minutes, not while the tab is hidden (poller.js).
    (typeof altaEvery === "function" ? altaEvery : setInterval)(inboxBadgePoll, 120000);
  };
  if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", go);
  else go();
})();

// ---- the mailbox settings (AI & settings, per account) ----------------------
//
// The password is never sent back: only whether one is stored and its last four
// characters. A blank password box keeps the stored one.
function _mbxHead(){
  return '<div style="font-weight:600;margin-bottom:6px"><i class="ti ti-message-circle"></i> '
    + 'Customer messages mailbox <span class="cc">(per account)</span> '
    + uiHint("In Seller Central: Settings → Notification Preferences → Messaging → Buyer Messages, "
             + "set the email address below. The app reads that inbox every 10 minutes, keeps only "
             + "Amazon's buyer messages, and never marks anything read, moves or deletes it.")
    + "</div>";
}

async function mbxSettingsLoad(){
  const box = document.getElementById("mbx_box");
  if(!box) return;
  // Settings for whoever may change them (manage_accounts, auth/guard.py);
  // anyone else would only see a refusal here.
  if(typeof can === "function" && !can("manage_accounts")){ box.style.display = "none"; return; }
  box.style.display = "";
  const a = _ibxAcct();
  box.setAttribute("data-acct", "");
  if(!a){
    box.innerHTML = _mbxHead() + '<div class="cc">Open an account first — each account has its own mailbox.</div>';
    return;
  }
  box.innerHTML = _mbxHead() + '<div class="cc">Loading…</div>';
  let j = null;
  try{ j = await (await fetch(_ibxUrl("/settings/mailbox"))).json(); }
  catch(e){ j = {ok: false, error: String(e)}; }
  if(_ibxAcct() !== a) return;
  if(!j || !j.ok){
    box.innerHTML = _mbxHead() + '<div class="reqnote">' + esc((j && j.error) || "Could not load the mailbox settings.") + "</div>";
    return;
  }
  const pwNote = j.has_password
    ? ("•••• " + (j.password_tail || "") + " — leave blank to keep")
    : "the 16-letter app password";
  // THE FORM BELONGS TO THE ACCOUNT IT WAS DRAWN FOR. Save, Test and
  // Disconnect use this, never the account open at the moment of the click.
  box.setAttribute("data-acct", a);
  box.innerHTML = _mbxHead()
    + '<div class="reqnote" style="margin-bottom:8px">Saved to <b>' + esc(j.account || a) + "</b>. "
    + (j.configured ? '<span style="color:var(--ok)">✓ Connected</span>' : "Not connected yet.")
    + (j.has_password && j.sealed === false
        ? ' <span style="color:var(--warn)">The password is stored unencrypted (ALTA_TOKEN_KEY is not set).</span>' : "")
    + "</div>"
    + '<table class="kv">'
    + '<tr><td class="k">IMAP server</td><td class="v"><input class="ed" id="mbx_host" value="' + esc(j.host || "") + '" placeholder="imap.gmail.com"></td></tr>'
    + '<tr><td class="k">Port</td><td class="v"><input class="ed" id="mbx_port" inputmode="numeric" value="' + esc(String(j.port || 993)) + '"></td></tr>'
    + '<tr><td class="k">Email address</td><td class="v"><input class="ed" id="mbx_user" autocomplete="off" value="' + esc(j.user || "") + '" placeholder="the address Amazon emails buyer messages to"></td></tr>'
    + '<tr><td class="k">App password ' + uiHint("For Gmail: Google Account → Security → 2-Step Verification → App passwords. Never your real password.")
    + '</td><td class="v"><input class="ed" id="mbx_pw" type="password" autocomplete="new-password" placeholder="' + esc(pwNote) + '"></td></tr>'
    + "</table>"
    + '<div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">'
    + '<button class="primary" onclick="mbxSave()"><i class="ti ti-check"></i> Save mailbox</button>'
    + '<button onclick="mbxTest()"><i class="ti ti-plug-connected"></i> Test connection</button>'
    + (j.configured ? '<button class="ghost" onclick="mbxDisconnect()"><i class="ti ti-plug-x"></i> Disconnect</button>' : "")
    + '<span id="mbx_status" class="cc" role="status"></span></div>'
    + '<div id="mbx_result" style="margin-top:8px"></div>';
}

function _mbxForm(){
  const v = function(id){ return ((document.getElementById(id) || {}).value || "").trim(); };
  return {mailbox_host: v("mbx_host"), mailbox_port: v("mbx_port"),
          mailbox_user: v("mbx_user"), mailbox_password: v("mbx_pw")};
}

function _mbxSay(html){ const st = document.getElementById("mbx_status"); if(st) st.innerHTML = html; }

// The account the form was drawn for, or "" (and it says why) when another
// account has been opened since -- then nothing is sent.
function _mbxPinned(){
  const box = document.getElementById("mbx_box");
  const a = box ? (box.getAttribute("data-acct") || "") : "";
  if(!a) return "";
  if(a !== _ibxAcct()){
    const out = document.getElementById("mbx_result");
    if(out) out.innerHTML = uiNote("warn", "Another account was opened — nothing was sent",
      "This form was filled in for " + a + ". Reopen Settings to change the mailbox of the account now open.");
    return "";
  }
  return a;
}

async function mbxSave(){
  const a = _mbxPinned();
  if(!a) return;
  _mbxSay("Saving…");
  let j = null, status = 0;
  try{
    const r = await fetch(_ibxUrl("/settings/mailbox"), {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(Object.assign({account: a}, _mbxForm()))});
    status = r.status;
    j = await r.json();
  }catch(e){ j = {ok: false, error: String(e)}; }
  if(_ibxAcct() !== a) return;
  if(!j || !j.ok){
    _mbxSay("");
    const out = document.getElementById("mbx_result");
    if(out) out.innerHTML = uiNote("bad", "Not saved", (j && j.error) || ("HTTP " + status));
    return;
  }
  toast(j.configured ? "Mailbox saved — messages will be read every 10 minutes" : "Saved — add the app password to connect");
  INBOX.data = null;
  if(typeof screenStale === "function") screenStale("inbox");
  mbxSettingsLoad();
}

async function mbxTest(){
  const a = _mbxPinned();
  if(!a) return;
  const out = document.getElementById("mbx_result");
  _mbxSay("Signing in…");
  if(out) out.innerHTML = "";
  let j = null;
  try{
    const r = await fetch(_ibxUrl("/settings/mailbox/test"), {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(Object.assign({account: a}, _mbxForm()))});
    j = await r.json();
  }catch(e){ j = {ok: false, error: String(e)}; }
  if(_ibxAcct() !== a) return;
  _mbxSay("");
  if(!out) return;
  if(!j || !j.ok){
    out.innerHTML = uiNote("bad", "Not connected", (j && j.error) || "Unknown error");
    return;
  }
  out.innerHTML = uiNote("ok", "Connected — " + (j.amazon_recent || 0) + " Amazon message"
    + (j.amazon_recent === 1 ? "" : "s") + " in the last " + (j.days || 30) + " days",
    (j.total === null || j.total === undefined ? "" : j.total + " emails in the inbox. ")
    + "Nothing was changed in the mailbox.");
}

async function mbxDisconnect(){
  const a = _mbxPinned();
  if(!a) return;
  const yes = await uiConfirm("Stop reading this mailbox for " + a + "? Messages already here are kept.",
                              {title: "Disconnect the mailbox?", ok: "Disconnect"});
  if(!yes || _mbxPinned() !== a) return;
  let j = null;
  try{
    j = await (await fetch(_ibxUrl("/settings/mailbox"), {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({account: a, clear: true})})).json();
  }catch(e){ j = {ok: false, error: String(e)}; }
  if(_ibxAcct() !== a) return;
  if(!j || !j.ok){ toast("Could not disconnect: " + ((j && j.error) || "failed"), {err: true}); return; }
  toast("Mailbox disconnected");
  INBOX.data = null;
  if(typeof screenStale === "function") screenStale("inbox");
  mbxSettingsLoad();
}
