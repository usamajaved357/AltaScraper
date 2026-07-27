/* Amazon <-> App sync UI (feature 2).
   Pull = Amazon -> app; Push = app -> Amazon. Both PROPOSE a side-by-side; nothing is
   overwritten without a per-field choice. Push buttons are locked until unlocked, and the
   backend refuses the actual write (halted + borrowed-cred refusal). Gated on the live
   capability matrix. Status pills show "Unknown -- never pulled" before a first pull. */

let SYNC_PUSH_UNLOCKED = false;
let SYNC_LAST = null;   // {sku, amazon, stored, status} stashed on a pull, for apply

function _syncToast(msg){
  var t=document.getElementById('toast'); if(!t){ return; }
  t.textContent=msg; t.classList.add('show');
  clearTimeout(window._syncTt); window._syncTt=setTimeout(function(){ t.classList.remove('show'); }, 3200);
}

function _syncPill(status){
  var m={
    confirmed:['#1f3d2e','#4caf7d','Authorised'],
    synced:['#1f3d2e','#4caf7d','Synced'],
    'unknown-never-pulled':['#33384a','#aab3c5','Unknown — never pulled'],
    'regenerated-not-on-amazon':['#3a3320','#e3b768','Regenerated — not on Amazon'],
    'changed-on-amazon':['#1e3350','#6ea8fe','Changed on Amazon — app behind'],
    deactivated:['#3d1f22','#e0696b','Deactivated (temporary)'],
    role_gap:['#3d1f22','#e0696b','No read role'],
    blocked_unconfirmed:['#3a3320','#e3b768','Blocked — reason unconfirmed'],
    borrowed:['#33384a','#aab3c5','Borrowed (catalogue-only)'],
    not_connected:['#33384a','#aab3c5','Not connected'],
    untested:['#33384a','#aab3c5','Not read-tested']
  };
  var p=m[status]||['#33384a','#aab3c5',status||'?'];
  return '<span style="background:'+p[0]+';color:'+p[1]+';padding:2px 9px;border-radius:10px;font-size:11px;font-weight:600;white-space:nowrap">'+esc(p[2])+'</span>';
}

function syncOnOpen(){ syncRenderMatrix(); }

async function syncRenderMatrix(){
  var el=document.getElementById('sync_matrix'); if(!el) return;
  el.innerHTML='<span class="genspin"></span> Loading capabilities…';
  try{
    var j=await (await fetch('/sync/capabilities')).json();
    if(!j.ok){ el.innerHTML='<div class="cc" style="color:#e0696b">could not load</div>'; return; }
    var h='<table class="ishtable" style="width:100%"><thead><tr><th>Account</th><th>Status</th><th>Pull</th><th>Push</th></tr></thead><tbody>';
    (j.accounts||[]).forEach(function(a){
      h+='<tr><td><b>'+esc(a.label)+'</b></td>'
        +'<td>'+_syncPill(a.status)+'</td>'
        +'<td title="'+esc(a.reason)+'">'+(a.pull_enabled?'<span style="color:#4caf7d">active</span>':'<span style="color:#e0696b">disabled</span>')+'</td>'
        +'<td>'+(a.push_enabled?'<span style="color:#e3b768">inferred</span>':'<span style="color:#8b93a5">—</span>')+'</td></tr>';
    });
    h+='</tbody></table>'
      +'<div class="cc" style="font-size:11px;opacity:.7;margin-top:6px">Pull reflects a live read-test. Push is inferred until a real push. Re-check / mark-cause apply to the <b>active workspace</b>.</div>'
      +'<div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">'
      +'<button class="btn" onclick="syncRecheck()">Re-check active account (read-test)</button>'
      +'<button class="btn" onclick="syncMarkCause()">Mark cause…</button></div>';
    el.innerHTML=h;
  }catch(e){ el.innerHTML='<div class="cc" style="color:#e0696b">error loading capabilities</div>'; }
}

function _syncSku(){ var e=document.getElementById('sync_sku'); return e?(e.value||'').trim():''; }

async function syncCheckStatus(){
  var sku=_syncSku(); var pill=document.getElementById('sync_pill');
  if(!sku){ pill.innerHTML=''; return; }
  pill.innerHTML='<span class="genspin"></span>';
  try{
    var j=await (await fetch('/sync/status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sku:sku})})).json();
    pill.innerHTML = j.ok ? (_syncPill(j.status)+' <span class="cc" style="font-size:11px;opacity:.7">'+esc(j.detail||'')+'</span>')
                          : ('<span style="color:#e0696b">'+esc(j.error||'error')+'</span>');
  }catch(e){ pill.innerHTML='<span style="color:#e0696b">error</span>'; }
}

async function syncPull(){
  var sku=_syncSku(); if(!sku){ _syncToast('Enter a SKU'); return; }
  _syncToast('Pulling from Amazon…');
  try{
    var j=await (await fetch('/sync/pull',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sku:sku})})).json();
    if(!j.ok){ _syncToast(j.error||'pull failed'); return; }
    syncOpenModal('pull', sku, j.stored_copy||{}, j.amazon_copy||{}, j);
  }catch(e){ _syncToast('pull error'); }
}

async function syncPush(){
  if(!SYNC_PUSH_UNLOCKED){ _syncToast('Push is locked — tick "Unlock push" first.'); return; }
  var sku=_syncSku(); if(!sku){ _syncToast('Enter a SKU'); return; }
  try{
    var j=await (await fetch('/sync/push',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sku:sku})})).json();
    if(!j.ok){ _syncToast(j.error||'push blocked'); return; }
    syncOpenModal('push', sku, j.stored_copy||{}, j.amazon_copy||{}, j);
  }catch(e){ _syncToast('push error'); }
}

var _SYNC_FIELDS=[['title','Title'],['item_highlights','Item Highlights'],['bullet_1','Bullet 1'],
  ['bullet_2','Bullet 2'],['bullet_3','Bullet 3'],['bullet_4','Bullet 4'],['bullet_5','Bullet 5'],
  ['description','Description'],['search_terms','Search terms']];

function syncOpenModal(mode, sku, stored, amazon, meta){
  SYNC_LAST={sku:sku, amazon:amazon, stored:stored, status:(meta&&meta.status)};
  var h='<div class="cc" style="margin-bottom:8px">'+esc(sku)+' — '
    +(mode==='pull'?'PULL: tick the Amazon fields to bring into the app.':'PUSH: review what would go to Amazon (write is halted).')+'</div>';
  if(meta&&meta.warn){ h+='<div style="background:#3a3320;color:#e3b768;padding:8px 10px;border-radius:8px;margin-bottom:8px">'+esc(meta.warn)+'</div>'; }
  if(meta&&meta.status){ h+='<div style="margin-bottom:8px">Status: '+_syncPill(meta.status)+'</div>'; }
  var srcLbl=(mode==='pull')?'Amazon (incoming)':'App (would push)';
  var tgtLbl=(mode==='pull')?'App (current)':'Amazon (current)';
  h+='<table class="ishtable" style="width:100%;table-layout:fixed"><thead><tr>';
  if(mode==='pull') h+='<th style="width:34px"></th>';
  h+='<th style="width:120px">Field</th><th>'+esc(srcLbl)+'</th><th>'+esc(tgtLbl)+'</th></tr></thead><tbody>';
  _SYNC_FIELDS.forEach(function(fp){
    var f=fp[0], lbl=fp[1];
    var src=(mode==='pull'?amazon:stored)[f]||'';
    var tgt=(mode==='pull'?stored:amazon)[f]||'';
    var diff=(src!==tgt);
    h+='<tr style="'+(diff?'background:rgba(110,168,254,.06)':'')+'">';
    if(mode==='pull') h+='<td>'+(diff?'<input type="checkbox" class="sync_apply" data-f="'+f+'">':'')+'</td>';
    h+='<td class="cc" style="font-size:11px">'+esc(lbl)+(diff?' <span style="color:#6ea8fe">●</span>':'')+'</td>'
      +'<td style="font-size:11px;word-break:break-word">'+esc(String(src).slice(0,300))+'</td>'
      +'<td style="font-size:11px;word-break:break-word">'+esc(String(tgt).slice(0,300))+'</td></tr>';
  });
  h+='</tbody></table>';
  if(mode==='pull'){
    h+='<div style="margin-top:12px"><button class="btn primary" onclick="syncApplyPull()">Apply checked Amazon fields to app</button></div>';
  }else{
    h+='<div style="margin-top:12px;background:#3d1f22;color:#e0696b;padding:8px 10px;border-radius:8px">Push write is intentionally HALTED pending the reviewed one-listing first-push test. Nothing was sent to Amazon.</div>';
  }
  document.getElementById('sync_modal_title').textContent=(mode==='pull'?'Pull review':'Push review')+' — '+sku;
  document.getElementById('sync_modal_body').innerHTML=h;
  document.getElementById('sync_modal').classList.add('show');
}
function syncCloseModal(){ document.getElementById('sync_modal').classList.remove('show'); }

async function syncApplyPull(){
  if(!SYNC_LAST){ return; }
  var fields={};
  document.querySelectorAll('#sync_modal_body .sync_apply:checked').forEach(function(cb){
    fields[cb.dataset.f]=(SYNC_LAST.amazon[cb.dataset.f]||'');
  });
  if(!Object.keys(fields).length){ _syncToast('Tick at least one field'); return; }
  var body={sku:SYNC_LAST.sku, fields:fields};
  try{
    var r=await fetch('/sync/pull/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    var j=await r.json();
    if(r.status===409 && j.blocked){
      if(!confirm((j.error||'This row was regenerated but not pushed.')+'\n\nApply anyway and DISCARD the regenerated copy?')){ return; }
      body.force=true;
      j=await (await fetch('/sync/pull/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    }
    _syncToast(j.ok?('Applied to app: '+((j.applied||[]).join(', ')||'nothing')):(j.error||'apply failed'));
    if(j.ok){ syncCloseModal(); syncCheckStatus(); }
  }catch(e){ _syncToast('apply error'); }
}

async function syncRecheck(){
  _syncToast('Re-testing active account…');
  try{
    var j=await (await fetch('/sync/read_test',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json();
    _syncToast(j.ok?('Pull: '+j.status+(j.pull_enabled?' (active)':' (disabled)')):(j.error||'read-test failed'));
    syncRenderMatrix();
  }catch(e){ _syncToast('read-test error'); }
}

async function syncMarkCause(){
  var c=prompt('Mark the pull-block cause for the ACTIVE workspace. Type one:\n'
    +'  deactivated          (temporary suspension -- clears on reinstatement)\n'
    +'  role_gap             (credentials genuinely lack the read role)\n'
    +'  blocked_unconfirmed  (reset -- reason unknown)');
  if(!c) return;
  var st=c.trim();
  if(['deactivated','role_gap','blocked_unconfirmed','untested'].indexOf(st)<0){ _syncToast('invalid status'); return; }
  var note=prompt('Optional note (e.g. "Section 3 suspension"):')||'';
  try{
    var j=await (await fetch('/sync/mark_status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:st,note:note})})).json();
    _syncToast(j.ok?'marked':(j.error||'failed')); syncRenderMatrix();
  }catch(e){ _syncToast('mark error'); }
}

function syncTogglePushLock(cb){
  SYNC_PUSH_UNLOCKED=!!cb.checked;
  var b=document.getElementById('sync_push_btn');
  if(b){ b.disabled=!cb.checked; b.title=cb.checked?'Push (backend write halted until the first-push test)':'Push is locked'; }
}
