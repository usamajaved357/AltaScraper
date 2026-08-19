// static/js/notify.js — where alerts go when nobody has the app open.
//
// Everything this app produces has been in-app only. An alert nobody is looking
// at is not an alert.
//
// THE SCREEN'S JOB IS TO MAKE THE OUTWARD-FACING PART OBVIOUS. Adding an address
// and starting to broadcast to it are two separate actions here, in that order,
// because a mistyped webhook that begins receiving immediately is a small
// permanent leak into somebody else's channel. A new channel arrives switched
// off and has to be turned on deliberately, and "Send test" is right next to it
// so an address can be checked before it is trusted.
//
// The full webhook URL never comes back from the server — it is a bearer
// credential, and rendering it puts it in screenshots and support threads. Only
// a redacted form is ever drawn.

let NTF = { channels: [], log: [], quiet: 6, loading: false, note: "" };

function _ntfQs() { return (typeof scopeQs === "function") ? scopeQs() : ""; }

function ntfResult(r) {
  if (r === "sent") return '<span class="ld-pill ok">sent</span>';
  if (r === "failed") return '<span class="ld-pill off">failed</span>';
  if (r === "skipped") return '<span class="ld-pill unk">not repeated</span>';
  return '<span class="ld-pill unk">' + esc(r || "—") + "</span>";
}

function ntfRender() {
  const box = document.getElementById("ntf_body");
  if (!box) return;
  if (NTF.loading) { box.innerHTML = '<div class="cc" style="padding:14px">Loading…</div>'; return; }

  let html = "";

  // ---- how it stands ------------------------------------------------------
  // "On" is the number that matters and it is deliberately not the same as
  // "added": a channel arrives switched off, so added-but-never-turned-on is
  // the state where somebody believes they are being told and is not.
  const on = NTF.channels.filter(function (c) { return c.enabled; }).length;
  const failed = NTF.log.filter(function (e) { return e.result === "failed"; }).length;
  const sent = NTF.log.filter(function (e) { return e.result === "sent"; }).length;
  html += uiStats([
    { label: "Places to send to", value: NTF.channels.length,
      note: NTF.channels.length ? "added" : "alerts stay inside this app" },
    { label: "Switched on", value: on, tone: (NTF.channels.length && !on) ? "warn" : "",
      note: (NTF.channels.length && !on)
        ? "added but none broadcasting yet"
        : "receiving alerts" },
    { label: "Sent", value: sent,
      note: "of " + NTF.log.length + " logged send" + (NTF.log.length === 1 ? "" : "s") },
    { label: "Failed", value: failed, tone: failed ? "bad" : "",
      note: failed ? "reason is in the log below" : "none" }
  ]);

  // ---- add ----------------------------------------------------------------
  html += uiPanel("Add somewhere to send to",
    "Slack, or a webhook for anything else.",
    '<div style="display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap">' +
    '<div><label class="cc" style="display:block;font-size:11px">Type</label>' +
    '<select id="ntf_kind" class="ed" style="width:150px">' +
    '<option value="slack">Slack</option>' +
    '<option value="webhook">Webhook (anything else)</option>' +
    "</select></div>" +
    '<div style="flex:1;min-width:260px"><label class="cc" style="display:block;font-size:11px">Address</label>' +
    '<input id="ntf_url" class="ed" style="width:100%" placeholder="https://hooks.slack.com/services/…"></div>' +
    '<div><label class="cc" style="display:block;font-size:11px">Name it</label>' +
    '<input id="ntf_label" class="ed" style="width:150px" placeholder="Ops room"></div>' +
    '<button class="primary" onclick="ntfAdd()"><i class="ti ti-plus"></i> Add</button>' +
    "</div>" +
    '<div class="cc" style="font-size:11.5px;line-height:1.55;margin-top:9px;max-width:720px">' +
    "It arrives <b>switched off</b>. Send a test first, then turn it on — that way a " +
    "mistyped address never posts into somebody else's channel. For Slack, create an " +
    "<b>Incoming Webhook</b> in your workspace and paste the URL. For anything else " +
    "(Zapier, Make, n8n, a WhatsApp bridge) use Webhook and the whole alert is posted as JSON." +
    "</div>");

  // ---- channels -----------------------------------------------------------
  if (!NTF.channels.length) {
    html += uiEmpty("Nothing is set up",
      "Alerts are only visible inside this app until you add somewhere for them to go — " +
      "and an alert nobody is looking at is not an alert.");
  } else {
    let t = '<div style="overflow-x:auto">' +
      '<table class="stk-table"><thead><tr><th>Name</th><th>Type</th><th>Address</th>' +
      "<th>Events</th><th>Last</th><th>On</th><th></th></tr></thead><tbody>";
    NTF.channels.forEach(function (c) {
      t += "<tr>" +
        '<td style="font-weight:600">' + esc(c.label || "(unnamed)") + "</td>" +
        "<td>" + esc(c.kind) + "</td>" +
        // Redacted, always. The server never sends the whole thing.
        '<td class="cc" style="font-size:11px;font-family:monospace">' + esc(c.url_shown) + "</td>" +
        '<td class="cc" style="font-size:11px">' +
        (c.events && c.events.length ? esc(c.events.join(", ")) : "everything") + "</td>" +
        '<td class="cc" style="font-size:11px">' +
        (c.last_result ? ntfResult(c.last_result) + " " + esc(c.last_at || "") : "never") + "</td>" +
        '<td><label class="apmob"><input type="checkbox" ' + (c.enabled ? "checked" : "") +
        ' onchange="ntfEnable(' + c.id + ', this.checked)"> ' +
        (c.enabled ? "on" : "off") + "</label></td>" +
        '<td style="white-space:nowrap">' +
        '<button class="ib" title="Send a test message" onclick="ntfTest(' + c.id + ')">' +
        '<i class="ti ti-send"></i></button>' +
        '<button class="ib" title="Remove" onclick="ntfRemove(' + c.id + ')">' +
        '<i class="ti ti-trash"></i></button></td>' +
        "</tr>";
    });
    t += "</tbody></table></div>";
    html += uiPanel("Where alerts go", "The address is always shown redacted — the full " +
      "webhook URL is a password and never leaves the server.", t);
  }

  // ---- send now -----------------------------------------------------------
  html += uiToolbar(
    '<button class="db-chip" onclick="ntfSendNow()"><i class="ti ti-bell-ringing"></i> ' +
    "Send what is off target now</button>",
    '<div class="cc" style="font-size:11.5px;max-width:560px;text-align:right">Sends the ' +
    "current tracker alerts to every channel that is on. The same alert is not repeated " +
    "within " + NTF.quiet + " hours — an unchanged problem sent every hour is how a " +
    "channel ends up muted.</div>");

  // ---- log ----------------------------------------------------------------
  if (!NTF.log.length) {
    html += uiPanel("What has been sent", "Every send and every failure is recorded here.",
      '<div class="cc" style="padding:2px;font-size:12px">Nothing yet.</div>');
  } else {
    let t = '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>' +
      "<th>When</th><th>Where</th>" +
      "<th>What</th><th>Result</th><th>Detail</th></tr></thead><tbody>";
    NTF.log.forEach(function (e) {
      t += "<tr>" +
        '<td class="cc" style="font-size:11px">' + esc(e.at || "") + "</td>" +
        "<td>" + esc(e.channel || "") + "</td>" +
        "<td>" + esc(e.subject || "") + "</td>" +
        "<td>" + ntfResult(e.result) + "</td>" +
        // A failure's reason is shown, not swallowed. A notification system
        // whose failures are invisible turns "nobody told me" into "the app
        // said it was fine".
        '<td class="cc" style="font-size:11px;max-width:340px">' + esc(e.detail || "") + "</td>" +
        "</tr>";
    });
    t += "</tbody></table></div>";
    html += uiPanel("What has been sent",
      "A failure's reason is shown rather than swallowed — a notification system whose " +
      "failures are invisible turns “nobody told me” into “the app said it was fine”.", t);
  }

  box.innerHTML = html;
}

async function ntfLoad() {
  NTF.loading = true; ntfRender();
  try {
    const j = await (await fetch("/notify/channels" + _ntfQs())).json();
    if (j.ok) { NTF.channels = j.channels || []; NTF.quiet = j.quiet_hours || 6; }
    const l = await (await fetch("/notify/log?limit=40")).json();
    if (l.ok) NTF.log = l.log || [];
  } catch (e) {
    NTF.note = String(e);
  }
  NTF.loading = false;
  ntfRender();
}

async function ntfAdd() {
  const kind = (document.getElementById("ntf_kind") || {}).value || "slack";
  const url = ((document.getElementById("ntf_url") || {}).value || "").trim();
  const label = ((document.getElementById("ntf_label") || {}).value || "").trim();
  if (!url) { toast("Paste the address first."); return; }
  const j = await (await fetch("/notify/channels", {
    method: "POST", headers: { "Content-Type": "application/json" },
    // enabled is NOT sent: a new channel arrives switched off, always.
    body: JSON.stringify({ kind: kind, url: url, label: label })
  })).json();
  if (!j.ok) { toast(j.error || "Could not add that."); return; }
  const u = document.getElementById("ntf_url"); if (u) u.value = "";
  toast("Added, switched off. Send a test before turning it on.");
  ntfLoad();
}

async function ntfEnable(id, on) {
  const j = await (await fetch("/notify/channel", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: id, enabled: !!on })
  })).json();
  if (!j.ok) toast(j.error || "Could not change that.");
  ntfLoad();
}

async function ntfTest(id) {
  toast("Sending a test…");
  const j = await (await fetch("/notify/test", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: id })
  })).json();
  toast(j.ok ? "Test sent — check the channel." : ("Test failed: " + (j.detail || "")));
  ntfLoad();
}

async function ntfRemove(id) {
  if (!confirm("Remove this channel? Nothing will be sent to it again.")) return;
  await fetch("/notify/channel?id=" + encodeURIComponent(id), { method: "DELETE" });
  ntfLoad();
}

async function ntfSendNow() {
  const j = await (await fetch("/notify/send" + _ntfQs(), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  })).json();
  if (j.note) toast(j.note);
  else if (!j.ok) toast("Some sends failed — see the log below.");
  else toast(j.sent + " sent, " + j.skipped + " not repeated, " + j.failed + " failed");
  ntfLoad();
}
