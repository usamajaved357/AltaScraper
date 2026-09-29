/* static/js/ppccontrol.js -- campaign controls on Campaign Analytics.
 *
 *     "i also want an option to turn on or off the campaigns and change the
 *      budget, bids and rules and every other feature that we have in seller
 *      central, i want it here"                        -- owner, 30 Sep 2026
 *
 * EVERY CHANGE IS THE OWNER'S TYPED VALUE, CONFIRMED (CLAUDE.md Rule 8):
 *   - a money box starts EMPTY -- nothing is suggested or pre-filled;
 *   - the confirmation names the account, the marketplace, the thing, and
 *     Amazon's current value -> the new one;
 *   - the account and marketplace are taken before the first dialog and the
 *     change is refused if the screen moved (the confirm-then-write rule);
 *   - the server reads Amazon before, writes, reads back, and records each step
 *     in the Dr PPC ledger (domain/ppc_control). What it says is what is shown.
 *
 * Reads (the live list, one campaign's structure) change nothing.
 */

const PPCX = {structure: {}, loading: {}};

function _pxScope(){
  const d = (typeof PPCC !== "undefined" && PPCC.data) || {};
  return {account: (typeof acctId === "function") ? acctId()
                   : ((typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT) ? CUR_ACCOUNT.id : ""),
          marketplace: d.marketplace || ((typeof WS_MARKET !== "undefined") ? WS_MARKET : ""),
          label: (typeof ACTIVE_WS !== "undefined" && ACTIVE_WS && ACTIVE_WS.label) ? ACTIVE_WS.label : ""};
}

function _pxCur(){
  const d = (typeof PPCC !== "undefined" && PPCC.data) || {};
  return d.currency || "GBP";
}

async function _pxPost(url, body){
  const r = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"},
                              body: JSON.stringify(body)});
  return r.json();
}

/* Read every campaign's state and budget from Amazon now, then redraw. */
async function ppcxRefreshLive(btn){
  const old = btn ? btn.innerHTML : "";
  if(btn){ btn.disabled = true; btn.innerHTML = '<span class="genspin"></span> Reading Amazon…'; }
  const _sc = (typeof screenScope === "function") ? screenScope() : null;
  let j = null;
  try{ j = await (await fetch("/ppc/control/campaigns?" + ppcQS({}))).json(); }catch(e){ j = {ok: false, error: String(e)}; }
  if(btn){ btn.disabled = false; btn.innerHTML = old; }
  if(_sc && !screenStillIn(_sc)) return;
  if(!j || !j.ok){ toast("Could not read the campaign list: " + ((j && j.error) || "no reason given"), {err: true}); return; }
  toast("Read " + j.count + " campaign" + (j.count === 1 ? "" : "s") + " from Amazon");
  if(typeof ppccLoad === "function") ppccLoad();
}

/* One change, end to end. `what` names it for the dialogs. */
async function _pxChange(body, what, beforeTxt, afterTxt){
  const sc = _pxScope();
  const pin = (typeof screenScope === "function") ? screenScope() : null;
  const ok = await uiConfirm(
      what + "\n\n  now:  " + beforeTxt + "\n  new:  " + afterTxt
      + "\n\nAccount: " + (sc.label || sc.account) + " · " + sc.marketplace
      + "\n\nThis changes your LIVE advertising on Amazon now.",
      {title: "Change it on Amazon?", ok: "Change it", danger: true});
  if(!ok) return null;
  if(pin && !screenStillIn(pin)){
    toast("The account or marketplace changed while this was open, so nothing was changed.");
    return null;
  }
  let j;
  try{
    j = await _pxPost("/ppc/control/change",
      Object.assign({account: sc.account, marketplace: sc.marketplace, confirmed: true}, body));
  }catch(e){ j = {ok: false, error: String(e)}; }
  if(!j || !j.ok){
    await uiAlert("Nothing changed.\n\n" + ((j && j.error) || "no reason given"));
    return j;
  }
  toast(j.verified ? "Done — Amazon now shows " + afterTxt
                   : "Amazon accepted it; its read-back does not show it yet (it can take a minute)");
  return j;
}

/* Campaign on / off. */
async function ppcxSetState(campaignId, name, current){
  const to = (String(current).toUpperCase() === "ENABLED") ? "PAUSED" : "ENABLED";
  const j = await _pxChange({kind: "campaign", id: campaignId, campaign_id: campaignId, state: to},
                            (to === "PAUSED" ? "Pause" : "Turn on") + " campaign “" + name + "”",
                            String(current || "?"), to);
  if(j && j.ok && typeof ppccLoad === "function") ppccLoad();
}

/* A money value: the owner types it; the box starts empty. */
async function _pxAskMoney(label, current){
  const cur = _pxCur();
  const v = await uiPrompt(label + "\n\nNow: " + (current === null || current === undefined
                              ? "not known" : ppcMoney(current, cur).replace(/<[^>]*>/g, ""))
                           + "\nType the new amount.", "",
                           {type: "number", step: "0.01", min: "0.02", placeholder: "e.g. 12.50",
                            prefix: (typeof _ppcSym === "function") ? _ppcSym(cur) : ""});
  if(v === null) return null;
  const n = Number(String(v).trim());
  if(!(n > 0)){ toast("Type an amount above zero — nothing was changed."); return null; }
  return Math.round(n * 100) / 100;
}

async function ppcxSetBudget(campaignId, name, current){
  const n = await _pxAskMoney("Daily budget for “" + name + "”", current);
  if(n === null) return;
  const cur = _pxCur();
  const j = await _pxChange({kind: "campaign", id: campaignId, campaign_id: campaignId, amount: n},
                            "Daily budget for “" + name + "”",
                            current === null || current === undefined ? "not known" : ppcMoney(current, cur).replace(/<[^>]*>/g, ""),
                            ppcMoney(n, cur).replace(/<[^>]*>/g, ""));
  if(j && j.ok && typeof ppccLoad === "function") ppccLoad();
}

/* Ad group default bid, keyword bid, target bid, and their on/off. */
async function ppcxSetBid(kind, id, campaignId, label, current){
  const n = await _pxAskMoney((kind === "ad_group" ? "Default bid for ad group “" : "Bid for “") + label + "”", current);
  if(n === null) return;
  const cur = _pxCur();
  const j = await _pxChange({kind: kind, id: id, campaign_id: campaignId, amount: n},
                            (kind === "ad_group" ? "Default bid, ad group “" : "Bid, “") + label + "”",
                            current === null || current === undefined ? "not known" : ppcMoney(current, cur).replace(/<[^>]*>/g, ""),
                            ppcMoney(n, cur).replace(/<[^>]*>/g, ""));
  if(j && j.ok) ppcxLoadStructure(campaignId, true);
}

async function ppcxToggle(kind, id, campaignId, label, current){
  const to = (String(current).toUpperCase() === "ENABLED") ? "PAUSED" : "ENABLED";
  const j = await _pxChange({kind: kind, id: id, campaign_id: campaignId, state: to},
                            (to === "PAUSED" ? "Pause " : "Turn on ") + kind.replace("_", " ") + " “" + label + "”",
                            String(current || "?"), to);
  if(j && j.ok) ppcxLoadStructure(campaignId, true);
}

async function ppcxAddNegative(campaignId, adGroupId){
  const sc = _pxScope();
  const pin = (typeof screenScope === "function") ? screenScope() : null;
  const text = await uiPrompt("Negative keyword for this ad group\n\nSearches containing it (phrase) or "
                              + "exactly it (exact) will no longer show these ads.", "",
                              {placeholder: "e.g. free"});
  if(text === null || !String(text).trim()) return;
  const phrase = await uiConfirm("Match “" + String(text).trim() + "” as a PHRASE (any search containing it), "
                                 + "or only EXACTLY?", {title: "Negative match type", ok: "Phrase", cancel: "Exact"});
  const mt = phrase ? "phrase" : "exact";
  const ok = await uiConfirm("Add negative " + mt + " “" + String(text).trim() + "”?\n\nAccount: "
                             + (sc.label || sc.account) + " · " + sc.marketplace
                             + "\n\nThis changes your LIVE advertising on Amazon now.",
                             {title: "Add it on Amazon?", ok: "Add it", danger: true});
  if(!ok) return;
  if(pin && !screenStillIn(pin)){ toast("The account changed, so nothing was added."); return; }
  let j;
  try{
    j = await _pxPost("/ppc/control/negative", {account: sc.account, marketplace: sc.marketplace,
      confirmed: true, campaign_id: campaignId, ad_group_id: adGroupId, text: String(text).trim(), match_type: mt});
  }catch(e){ j = {ok: false, error: String(e)}; }
  if(!j || !j.ok){ await uiAlert("Nothing was added.\n\n" + ((j && j.error) || "no reason given")); return; }
  toast("Negative keyword added");
  ppcxLoadStructure(campaignId, true);
}

/* One campaign's ad groups, keywords, targets and negatives, live. */
async function ppcxLoadStructure(campaignId, force){
  if(PPCX.loading[campaignId]) return;
  if(PPCX.structure[campaignId] && !force){ if(typeof ppccRender === "function") ppccRender(); return; }
  PPCX.loading[campaignId] = true;
  const _sc = (typeof screenScope === "function") ? screenScope() : null;
  let j;
  try{ j = await (await fetch("/ppc/control/structure?" + ppcQS({campaign_id: campaignId}))).json(); }
  catch(e){ j = {ok: false, error: String(e)}; }
  PPCX.loading[campaignId] = false;
  if(_sc && !screenStillIn(_sc)) return;
  PPCX.structure[campaignId] = j || {ok: false};
  if(typeof ppccRender === "function") ppccRender();
}

/* The "Manage on Amazon" block inside an expanded campaign row. */
function ppcxManageHtml(r){
  const id = String(r.campaign_id);
  const s = PPCX.structure[id];
  const cur = _pxCur();
  let h = '<div class="ppcx-manage" style="margin-top:14px;border-top:1px solid var(--ppc-line);padding-top:12px">'
    + '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px">'
    + '<b style="font-size:13px">Manage on Amazon</b>'
    + '<button class="ppc-btn" onclick="event.stopPropagation();ppcxLoadStructure(' + jsArg(id) + ', true)">'
    +   (s ? 'Re-read' : 'Show ad groups, keywords and bids') + '</button>'
    + '<span style="font-size:11px;color:var(--ppc-muted)">every change asks you first, and is read back from Amazon</span>'
    + '</div>';
  if(PPCX.loading[id]) return h + '<div style="font-size:12px"><span class="genspin"></span> Reading Amazon…</div></div>';
  if(!s) return h + '</div>';
  if(!s.ok) return h + '<div style="font-size:12px;color:var(--ppc-red)">' + _pEsc(s.error || "Could not read it from Amazon.") + '</div></div>';
  const btn = function(label, onclick, title){
    return '<button class="ppc-btn" style="padding:2px 8px;font-size:11px" title="' + _pEsc(title || "")
      + '" onclick="event.stopPropagation();' + onclick + '">' + label + '</button>';
  };
  const stateChip = function(st){
    return String(st).toUpperCase() === "ENABLED" ? '<span class="ppc-badge enabled">ENABLED</span>'
         : '<span class="ppc-badge plain">' + _pEsc(st || "") + '</span>';
  };
  const table = function(title, rows, cols){
    if(rows === null) return '<div style="font-size:12px;color:var(--ppc-red)">' + _pEsc(title) + ': could not be read — '
                              + _pEsc(((s.errors || {})[title.toLowerCase().replace(/ /g, "_")]) || "") + '</div>';
    if(!rows.length) return '';
    return '<div style="font-size:12px;font-weight:600;margin:10px 0 4px">' + _pEsc(title) + ' (' + rows.length + ')</div>'
      + '<div style="overflow-x:auto"><table><tbody>' + rows.map(cols).join("") + '</tbody></table></div>';
  };
  (s.ad_groups || []).forEach(function(g){ g._label = g.name || g.ad_group_id; });
  h += table("Ad groups", s.ad_groups, function(g){
    return '<tr><td>' + _pEsc(g.name || g.ad_group_id) + '</td><td>' + stateChip(g.state) + '</td>'
      + '<td>default bid ' + ppcMoney(g.default_bid, cur) + '</td><td>'
      + btn("Change bid", "ppcxSetBid('ad_group'," + jsArg(g.ad_group_id) + "," + jsArg(id) + "," + jsArg(g.name || g.ad_group_id) + "," + (g.default_bid == null ? "null" : Number(g.default_bid)) + ")")
      + ' ' + btn(String(g.state).toUpperCase() === "ENABLED" ? "Pause" : "Turn on",
                  "ppcxToggle('ad_group'," + jsArg(g.ad_group_id) + "," + jsArg(id) + "," + jsArg(g.name || g.ad_group_id) + "," + jsArg(g.state) + ")")
      + ' ' + btn("+ Negative", "ppcxAddNegative(" + jsArg(id) + "," + jsArg(g.ad_group_id) + ")", "Add a negative keyword to this ad group")
      + '</td></tr>';
  });
  h += table("Keywords", s.keywords, function(k){
    return '<tr><td>' + _pEsc(k.text) + '</td><td style="font-size:11px">' + _pEsc(k.match_type) + '</td><td>' + stateChip(k.state) + '</td>'
      + '<td>bid ' + ppcMoney(k.bid, cur) + '</td><td>'
      + btn("Change bid", "ppcxSetBid('keyword'," + jsArg(k.keyword_id) + "," + jsArg(id) + "," + jsArg(k.text) + "," + (k.bid == null ? "null" : Number(k.bid)) + ")")
      + ' ' + btn(String(k.state).toUpperCase() === "ENABLED" ? "Pause" : "Turn on",
                  "ppcxToggle('keyword'," + jsArg(k.keyword_id) + "," + jsArg(id) + "," + jsArg(k.text) + "," + jsArg(k.state) + ")")
      + '</td></tr>';
  });
  h += table("Product targets", s.targets, function(t){
    return '<tr><td>' + _pEsc(t.label) + '</td><td>' + stateChip(t.state) + '</td>'
      + '<td>bid ' + ppcMoney(t.bid, cur) + '</td><td>'
      + btn("Change bid", "ppcxSetBid('target'," + jsArg(t.target_id) + "," + jsArg(id) + "," + jsArg(t.label) + "," + (t.bid == null ? "null" : Number(t.bid)) + ")")
      + ' ' + btn(String(t.state).toUpperCase() === "ENABLED" ? "Pause" : "Turn on",
                  "ppcxToggle('target'," + jsArg(t.target_id) + "," + jsArg(id) + "," + jsArg(t.label) + "," + jsArg(t.state) + ")")
      + '</td></tr>';
  });
  h += table("Negative keywords", s.negatives, function(n){
    return '<tr><td>' + _pEsc(n.text) + '</td><td style="font-size:11px">' + _pEsc(n.match_type) + '</td><td>' + stateChip(n.state) + '</td></tr>';
  });
  return h + '</div>';
}
