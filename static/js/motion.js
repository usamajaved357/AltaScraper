// ===================== MOTION =====================
//
// "the visuals of it the animation it feels like it is lagging."
//
// Four small helpers, and a rule they all follow: motion covers a wait, it
// never creates one. Nothing here changes what a screen shows or does -- every
// function is safe to not call, and every one degrades to "the thing simply
// appears", which is what happens today.
//
// The CSS half lives at the end of static/css/dashboard.css.

// -- 1. STAGGERED ROWS ------------------------------------------------------
// Rows fade in one after another instead of as a single block. The delays are
// set here rather than as twenty nth-child rules, and they STOP after the
// twentieth: a two-hundred-row table that took six seconds to finish arriving
// would be the exact opposite of the point.
const ALTA_STAGGER_MAX = 20;
const ALTA_STAGGER_STEP = 30;      // ms between rows

function altaStagger(container, selector){
  if(!container) return;
  let rows;
  try{
    rows = container.querySelectorAll(selector || "tbody tr");
  }catch(e){ return; }
  for(let i = 0; i < rows.length; i++){
    rows[i].classList.add("trow-enter");
    // After the cap, no delay at all -- the remainder appear together.
    rows[i].style.animationDelay =
      (i < ALTA_STAGGER_MAX ? (i * ALTA_STAGGER_STEP) : 0) + "ms";
  }
}

// -- 2. NUMBERS THAT COUNT UP ----------------------------------------------
// Only worth doing for a number that has just arrived. Called on a number that
// is already on screen it would count from zero again, which reads as the
// figure having changed when it has not.
function altaCountUp(el, target, duration){
  if(!el) return;
  const to = Number(target);
  if(!isFinite(to)){ return; }
  // Respect the system preference here too: the CSS media query cannot reach a
  // number being written by JS.
  try{
    if(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches){
      el.textContent = Math.round(to).toLocaleString();
      return;
    }
  }catch(e){}
  // Counting to a huge number one frame at a time reads as a slot machine, and
  // small numbers do not need it at all.
  if(Math.abs(to) < 2 || Math.abs(to) > 1e7){
    el.textContent = Math.round(to).toLocaleString();
    return;
  }
  const ms = duration || 400;
  let start = null;
  const step = function(ts){
    if(start === null) start = ts;
    const p = Math.min((ts - start) / ms, 1);
    const eased = 1 - Math.pow(1 - p, 3);          // ease-out cubic
    el.textContent = Math.floor(eased * to).toLocaleString();
    if(p < 1) requestAnimationFrame(step);
    else el.textContent = Math.round(to).toLocaleString();   // land exactly
  };
  requestAnimationFrame(step);
}

// Count up every metric tile inside a container that has just been drawn.
//
// ONLY WHEN THE NUMBER HAS ACTUALLY CHANGED. These tiles are redrawn on every
// filter click and every render, and counting an unchanged figure up from zero
// each time says "this just changed" about something that did not -- which is
// worse than not animating at all, because it is a lie told in motion.
const _ALTA_LAST_N = {};

function altaCountMetrics(container){
  const host = container || document;
  let els;
  try{ els = host.querySelectorAll(".metric .n"); }catch(e){ return; }
  els.forEach(function(el, i){
    const raw = String(el.textContent || "").replace(/[^0-9.\-]/g, "");
    if(raw === "") return;
    const n = Number(raw);
    if(!isFinite(n)) return;
    // Keyed by the tile's own label, so reordering the tiles cannot make one
    // number inherit another's history.
    let key = "";
    try{
      const p = el.parentElement;
      key = ((p && p.querySelector(".l") && p.querySelector(".l").textContent) || ("#" + i)).trim();
    }catch(e){ key = "#" + i; }
    if(_ALTA_LAST_N[key] === n) return;         // unchanged: leave it alone
    _ALTA_LAST_N[key] = n;
    el.textContent = "0";
    altaCountUp(el, n);
  });
}

// The account changed, so every figure is about to describe something else.
// Called from the same place that forgets the loaded screens.
function altaCountReset(){
  for(const k in _ALTA_LAST_N){ delete _ALTA_LAST_N[k]; }
}

// -- 3. SKELETONS -----------------------------------------------------------
// A placeholder shaped like the thing that is coming, so the page does not
// jump when it lands. These replace spinners on the surfaces where the shape
// is known; a spinner is still right where it is not.
function altaSkeletonRows(n, height){
  const rows = [];
  for(let i = 0; i < (n || 7); i++){
    rows.push('<div class="skeleton skrow"'
      + (height ? ' style="height:' + height + 'px"' : '') + '></div>');
  }
  return rows.join("");
}

function altaSkeletonCards(n){
  const cards = [];
  for(let i = 0; i < (n || 4); i++){
    cards.push('<div class="skeleton skcard"></div>');
  }
  return '<div class="skgrid">' + cards.join("") + '</div>';
}

function altaSkeletonChart(){
  return '<div class="skeleton skchart"></div>';
}

// A whole screen's worth: the tiles across the top, then the list beneath.
// What most of these screens actually look like.
function altaSkeletonScreen(opts){
  const o = opts || {};
  return (o.cards === false ? "" : altaSkeletonCards(o.cards || 4))
       + (o.chart ? altaSkeletonChart() : "")
       + altaSkeletonRows(o.rows || 7);
}

// Put a skeleton into a container, if that container is empty. Never over the
// top of content that is already there: replacing real figures with grey
// blocks on a refresh is a downgrade, not a polish.
function altaSkeletonInto(id, opts){
  const el = (typeof id === "string") ? document.getElementById(id) : id;
  if(!el) return false;
  if((el.innerHTML || "").trim() !== "") return false;
  el.innerHTML = altaSkeletonScreen(opts);
  return true;
}

// -- 5. A CHART BELOW THE FOLD WAITS ITS TURN --------------------------------
//
// "the orbit graph shows a motion when i go and scroll up and down... see all
// graphs while scrolling i want this thing in my app".
//
// MEASURED on Orbit by watching its path DATA, not its CSS -- Recharts animates
// in JavaScript and a CSS probe reads `animation: none` throughout, which is
// how you come to conclude "it does not animate" about something that plainly
// does:
//
//     returning to the Sales page   ANIMATES
//     scrolling a chart back in     static
//     a plain reload                ANIMATES
//
// Ours already matched that exactly, verified the same way. So this is not a
// thing Orbit has. On both apps every chart animates the moment the screen
// opens, so the ones further down finish playing before anyone scrolls to them
// and the page is dead below the fold.
//
// This holds a chart that is BELOW THE FOLD at the start of its animation and
// releases it when it scrolls into view. ONCE: a chart that replays every time
// it crosses the edge of the screen is a distraction, not an entrance.
//
// Charts already on screen are never touched -- they animate immediately, as
// they do now. And if IntersectionObserver is missing, the class is never
// added, so the fallback is exactly today's behaviour rather than a chart that
// never animates at all.
function altaChartsInView(root){
  const host = root || document;
  let charts;
  try{ charts = host.querySelectorAll("svg.chartbox"); }catch(e){ return; }
  if(!charts.length) return;
  if(typeof IntersectionObserver !== "function") return;
  try{
    if(window.matchMedia &&
       window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  }catch(e){}

  const release = function(el){
    el.classList.remove("await-view");
    io.unobserve(el);
  };
  const io = new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      // OR SCROLLED CLEAN PAST. Measured while testing this: at a threshold of
      // 0.08 a fast scroll took the combo chart from entirely below the fold to
      // entirely above it without ever being 8% visible, so it was never
      // released and sat frozen part-drawn. A chart stuck mid-animation is
      // worse than one that never animated.
      //
      // threshold 0 fires on the first visible pixel, and the top check catches
      // anything that got past even that.
      if(e.isIntersecting || (e.boundingClientRect && e.boundingClientRect.top < 0)){
        release(e.target);
      }
    });
  }, {threshold: 0});

  charts.forEach(function(svg){
    if(svg._altaInView) return;
    svg._altaInView = true;
    let r;
    try{ r = svg.getBoundingClientRect(); }catch(e){ return; }
    const onScreen = r.top < (window.innerHeight || 0) && r.bottom > 0;
    if(onScreen) return;                 // let it play now, as it always has
    svg.classList.add("await-view");
    io.observe(svg);
  });
}

// -- 4. TOOLTIP EDGE HANDLING ----------------------------------------------
// The CSS positions a tooltip above and centred. Near the right-hand edge that
// would put it off the screen, so it is flipped -- measured at hover time,
// because a table can be scrolled sideways after the page is drawn.
function altaTipInit(root){
  const host = root || document;
  let tips;
  try{ tips = host.querySelectorAll(".tipwrap"); }catch(e){ return; }
  tips.forEach(function(w){
    if(w._altaTip) return;
    w._altaTip = true;
    w.addEventListener("mouseenter", function(){
      const tip = w.querySelector(".tip");
      if(!tip) return;
      w.classList.remove("tipleft", "tipbelow");
      const r = w.getBoundingClientRect();
      if(r.left + 130 > window.innerWidth) w.classList.add("tipleft");
      if(r.top < 90) w.classList.add("tipbelow");
    });
  });
}
