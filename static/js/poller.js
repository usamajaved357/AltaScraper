/* static/js/poller.js -- one way to ask the server "is it done yet".
 *
 * WHY THIS EXISTS
 * Four screens each grew their own setInterval, and none of them ever stopped.
 * Measured while opening the Listings screen once: 84 requests, and 68 of them
 * were these four asking about work that was not running.
 *
 *     /miles/run_tail        every 2s   forever
 *     /run/health            every 3s   forever
 *     /genimage/jobs_active  every 2s   forever
 *     /preview/jobs          ~1.3s      forever
 *
 * Individually each is fast. Together they queue ahead of the calls the screen
 * is actually waiting for -- the twelve product-type schemas the grid cannot
 * draw without did not even START until 42 seconds in, behind that traffic.
 *
 * THREE RULES, IN ONE PLACE
 *
 *   1. NOTHING IS ASKED WHILE NOBODY IS LOOKING. A hidden tab polls not at all.
 *      This alone removes most of it: people leave the app open in a tab all
 *      day, and a background tab asking every two seconds is pure cost.
 *
 *   2. IDLE SLOWS DOWN, THEN STOPS. A run that is not running does not become
 *      more interesting the more often it is asked about, so the gap widens --
 *      2s, then 15s -- and after a long quiet stretch it gives up entirely.
 *      Anything that starts work calls wake() and it is instant again.
 *
 *   3. NEVER TWO AT ONCE. A slow reply used to overlap the next tick, so a
 *      struggling server got MORE requests exactly when it could least afford
 *      them. One in flight at a time, always.
 *
 * A tick returns true while there is something worth watching, false when there
 * is not. That single boolean is the whole contract.
 */

const _ALTA_POLLERS = [];

function altaPoller(opts){
  const o = opts || {};
  const P = {
    name: o.name || "poll",
    every: o.every || 2000,            // while something is happening
    idleEvery: o.idleEvery || 15000,   // once nothing is
    idleAfter: o.idleAfter || 3,       // ticks of quiet before slowing down
    stopAfter: o.stopAfter || 40,      // ticks of quiet before giving up
    tick: o.tick || function(){ return false; },
    timer: 0, inflight: false, idle: 0, running: false, errors: 0,
  };

  function delay(){
    // A failing server is asked less often, not more. Doubling per error up to
    // a minute stops a dead endpoint being hammered by every open tab.
    if(P.errors) return Math.min(60000, P.every * Math.pow(2, P.errors));
    return P.idle >= P.idleAfter ? P.idleEvery : P.every;
  }

  function schedule(){
    clearTimeout(P.timer);
    if(!P.running) return;
    if(P.idle >= P.stopAfter){ P.running = false; return; }   // given up; wake() revives it
    P.timer = setTimeout(run, delay());
  }

  async function run(){
    if(!P.running) return;
    // Nobody is looking. Come back when they are -- the visibility handler
    // below restarts this the moment the tab is shown again.
    if(typeof document !== "undefined" && document.hidden){ schedule(); return; }
    if(P.inflight){ schedule(); return; }
    P.inflight = true;
    try{
      const busy = await P.tick();
      P.errors = 0;
      P.idle = busy ? 0 : (P.idle + 1);
    }catch(e){
      P.errors = Math.min(P.errors + 1, 5);
    }finally{
      P.inflight = false;
      schedule();
    }
  }

  P.start = function(){
    if(P.running) return P;
    P.running = true; P.idle = 0; P.errors = 0;
    run();
    return P;
  };
  /* Something has started -- ask now, and go back to asking often. */
  P.wake = function(){
    P.idle = 0; P.errors = 0;
    if(!P.running){ P.start(); return P; }
    clearTimeout(P.timer);
    run();
    return P;
  };
  P.stop = function(){ P.running = false; clearTimeout(P.timer); return P; };

  _ALTA_POLLERS.push(P);
  return P;
}

/* Coming back to the tab should show the truth immediately, not after the next
 * scheduled gap -- which by then may be fifteen seconds away. */
if(typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("visibilitychange", function(){
    if(document.hidden) return;
    _ALTA_POLLERS.forEach(function(p){ if(p.running) p.wake(); });
  });
}

/* For the diagnostics screen: what is still asking, and how often. */
function altaPollerStatus(){
  return _ALTA_POLLERS.map(function(p){
    return {name: p.name, running: p.running, idle_ticks: p.idle,
            errors: p.errors, next_in_ms: p.running ? delayOf(p) : null};
  });
  function delayOf(p){
    if(p.errors) return Math.min(60000, p.every * Math.pow(2, p.errors));
    return p.idle >= p.idleAfter ? p.idleEvery : p.every;
  }
}
