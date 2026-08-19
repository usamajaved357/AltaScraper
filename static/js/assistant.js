/* static/js/assistant.js -- ask about this account, in plain English.
 *
 * The panel for POST /agent/ask. Everything it draws comes back from that one
 * endpoint; there is no business logic in this file and there must not be, or
 * the answer on screen and the answer in the trace could disagree.
 *
 * WHY THE TRACE IS DRAWN, AND NOT HIDDEN BEHIND A TOGGLE
 *
 * The answer is written by a model. The one thing that makes it checkable is
 * knowing WHICH screen each figure came from, so the owner can open that screen
 * and look. Every answer therefore carries the list of screens that were read,
 * in the order they were read, with failures shown as failures. An assistant
 * that shows only its conclusion is asking to be trusted; one that shows its
 * sources is asking to be checked, which is the correct request.
 *
 * This panel is SEPARATE from the "Ask Claude" chat at the bottom of the
 * Listings screen. That one helps fill in attribute values for one product and
 * can see a competitor image; this one reads the account's own figures and
 * cannot see an image at all. Sharing a panel between them would mean one box
 * that sometimes knows your sales and sometimes does not.
 */
var AS = {open: false, busy: false, msgs: [], scope: null, built: false};

function asEsc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* The answer arrives as markdown-ish text. Only the two marks the model
 * actually uses are honoured -- **bold** and paragraph breaks. Running a full
 * markdown parser over model output is how a stray underscore in a SKU turns
 * into italics halfway through a figure. */
function asText(s) {
  return asEsc(s)
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/\n\n+/g, '</p><p>')
    .replace(/\n/g, '<br>');
}

function asBuild() {
  if (AS.built) return;
  AS.built = true;
  var w = document.createElement('div');
  w.id = 'aswrap';
  w.style.cssText = 'position:fixed;right:18px;bottom:80px;width:430px;'
    + 'max-width:calc(100vw - 36px);height:min(620px,calc(100vh - 140px));'
    + 'display:none;flex-direction:column;background:#0d1220;'
    + 'border:1px solid #22304d;border-radius:14px;z-index:9600;'
    + 'box-shadow:0 18px 50px rgba(0,0,0,.55);overflow:hidden';
  w.innerHTML =
    '<div style="display:flex;align-items:center;gap:8px;padding:10px 12px;'
    + 'border-bottom:1px solid #1b2740;background:#111a2e">'
    + '<b style="font-size:13px">Ask about this account</b>'
    + '<span id="asscope" class="cc" style="font-size:11px"></span>'
    + '<span style="flex:1"></span>'
    + '<button onclick="asToggle()" title="Close" style="background:none;'
    + 'border:0;color:#8fa3c8;font-size:19px;cursor:pointer;line-height:1">'
    + '&times;</button></div>'
    + '<div id="aslog" style="flex:1;overflow-y:auto;padding:12px;'
    + 'font-size:12.5px;line-height:1.55"></div>'
    + '<div style="padding:10px 12px;border-top:1px solid #1b2740;'
    + 'background:#0b1020">'
    + '<div style="display:flex;gap:7px">'
    + '<textarea id="asinput" rows="1" placeholder="e.g. how did last month go?"'
    + ' onkeydown="asKey(event)" style="flex:1;resize:none;background:#0d1526;'
    + 'border:1px solid #22304d;border-radius:8px;color:#dbe6ff;padding:8px 10px;'
    + 'font-size:12.5px;font-family:inherit"></textarea>'
    + '<button id="assend" onclick="asSend()" style="background:#1f6feb;'
    + 'border:0;border-radius:8px;color:#fff;padding:0 14px;cursor:pointer;'
    + 'font-size:12.5px">Ask</button></div>'
    + '<div class="cc" style="font-size:10.5px;margin-top:7px">It reads this '
    + 'account\'s own screens and says which ones. It cannot change anything, '
    + 'and it answers only for the account you have open.</div></div>';
  document.body.appendChild(w);

  var b = document.createElement('button');
  b.id = 'asfab';
  b.textContent = '✦ Ask about this account';
  b.title = 'Ask a question about this account’s sales, stock and profit';
  b.onclick = asToggle;
  b.style.cssText = 'position:fixed;right:18px;bottom:22px;z-index:9599;'
    + 'background:#16203a;border:1px solid #2a3b5e;color:#cfe0ff;'
    + 'border-radius:22px;padding:9px 16px;cursor:pointer;font-size:12.5px;'
    + 'box-shadow:0 8px 24px rgba(0,0,0,.4)';
  document.body.appendChild(b);
}

function asToggle() {
  asBuild();
  AS.open = !AS.open;
  document.getElementById('aswrap').style.display = AS.open ? 'flex' : 'none';
  if (!AS.open) return;
  if (!AS.msgs.length) asEmpty();
  asScope();
  var i = document.getElementById('asinput');
  if (i) i.focus();
}

/* Which account is about to be read, said before the first question rather
 * than after the first answer. The panel is pinned to whatever is open, and a
 * person with four accounts should not have to infer which one replied. */
function asScope() {
  fetch('/agent/tools').then(function (r) { return r.json(); }).then(function (j) {
    if (!j || !j.ok) return;
    AS.scope = j.scope || {};
    var el = document.getElementById('asscope');
    if (el) {
      el.textContent = (AS.scope.account_name || '') +
        (AS.scope.marketplace ? ' · ' + AS.scope.marketplace : '');
    }
  }).catch(function () {});
}

function asEmpty() {
  document.getElementById('aslog').innerHTML =
    '<div class="cc" style="font-size:12px">Ask about sales, profit, stock, '
    + 'returns, traffic or what needs doing today. It reads the same screens '
    + 'you can open, and it will tell you which ones it read.'
    + '<div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px">'
    + ['How did last month go?',
       'What is about to run out?',
       'Which products actually made money?',
       'Anything I need to do today?']
      .map(function (q) {
        return '<button onclick="asAsk(this.textContent)" style="background:'
          + '#16203a;border:1px solid #2a3b5e;color:#cfe0ff;border-radius:14px;'
          + 'padding:5px 11px;cursor:pointer;font-size:11.5px">'
          + asEsc(q) + '</button>';
      }).join('')
    + '</div></div>';
}

function asKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); asSend(); }
}

function asAsk(q) {
  var i = document.getElementById('asinput');
  if (i) i.value = q;
  asSend();
}

function asRender() {
  var log = document.getElementById('aslog');
  log.innerHTML = AS.msgs.map(function (m) {
    if (m.role === 'user') {
      return '<div style="margin:0 0 12px;text-align:right"><span style="'
        + 'display:inline-block;background:#1b2a47;border-radius:12px 12px 2px '
        + '12px;padding:7px 11px;max-width:85%;text-align:left">'
        + asEsc(m.text) + '</span></div>';
    }
    if (m.role === 'error') {
      return '<div style="margin:0 0 12px;background:#2a1620;border:1px solid '
        + '#5c2a33;border-radius:10px;padding:9px 11px;color:#ffb3b3">'
        + asEsc(m.text) + '</div>';
    }
    var trace = '';
    if (m.trace && m.trace.length) {
      /* The receipts. Named so they can be opened, not as endpoint paths --
       * "/inventory/coverage" means nothing to the person reading. */
      trace = '<div class="cc" style="margin-top:9px;padding-top:8px;'
        + 'border-top:1px solid #1b2740;font-size:10.5px">Read: '
        + m.trace.map(function (t) {
            var nice = String(t.tool).replace(/_/g, ' ');
            return t.ok
              ? asEsc(nice)
              : '<span style="color:#ffb3b3">' + asEsc(nice)
                + ' (could not read'
                + (t.error ? ': ' + asEsc(String(t.error).slice(0, 90)) : '')
                + ')</span>';
          }).join(', ')
        + '</div>';
    }
    return '<div style="margin:0 0 14px"><div style="background:#111a2e;'
      + 'border:1px solid #1b2740;border-radius:12px 12px 12px 2px;'
      + 'padding:10px 12px"><p style="margin:0">' + asText(m.text)
      + '</p>' + trace + '</div></div>';
  }).join('')
  + (AS.busy ? '<div class="cc" style="font-size:12px">Reading the screens'
      + '…</div>' : '');
  log.scrollTop = log.scrollHeight;
}

function asSend() {
  asBuild();
  if (AS.busy) return;
  var i = document.getElementById('asinput');
  var q = (i.value || '').trim();
  if (!q) return;
  i.value = '';
  AS.msgs.push({role: 'user', text: q});
  AS.busy = true;
  document.getElementById('assend').disabled = true;
  asRender();

  fetch('/agent/ask', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    /* The whole conversation goes each time -- the endpoint keeps nothing
     * between calls, so what is on screen IS the history. */
    body: JSON.stringify({
      messages: AS.msgs.filter(function (m) {
        return m.role === 'user' || m.role === 'assistant';
      }).map(function (m) { return {role: m.role, text: m.text}; })
    })
  }).then(function (r) { return r.json(); }).then(function (j) {
    AS.busy = false;
    document.getElementById('assend').disabled = false;
    if (!j || !j.ok) {
      AS.msgs.push({role: 'error',
                    text: (j && j.error) || 'Something went wrong.'});
    } else {
      AS.msgs.push({role: 'assistant', text: j.answer, trace: j.trace || []});
      if (j.scope) {
        AS.scope = j.scope;
        var el = document.getElementById('asscope');
        if (el) {
          el.textContent = (j.scope.account_name || '')
            + (j.scope.marketplace ? ' · ' + j.scope.marketplace : '');
        }
      }
    }
    asRender();
  }).catch(function (e) {
    AS.busy = false;
    document.getElementById('assend').disabled = false;
    AS.msgs.push({role: 'error', text: 'Could not reach the app: ' + e});
    asRender();
  });
}

document.addEventListener('DOMContentLoaded', asBuild);
